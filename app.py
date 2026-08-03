"""基金查询 HTTP API 与前端静态页面。"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from benchmark_cache import BenchmarkFileCache
from fund_ai_summary import build_ai_summary
from benchmarks import (
    TRACK_BENCHMARKS,
    get_composite_benchmark,
    get_track_benchmark,
    parse_composite_spec,
    track_benchmark_catalog,
)
from fund_cache import FundFileCache
from fund_lookup import (
    FundLookupError,
    get_fund_data,
    get_fund_holdings_by_period,
    search_funds,
)
from stock_cache import StockFileCache
from stock_lookup import StockLookupError, get_stock_data
from watchlist_store import (
    WatchlistFileStore,
    default_watchlist_tag,
    normalize_watchlist_tags,
)


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CACHE_TTL_SECONDS = 10 * 60
FUND_HOLDINGS_LIMIT = 20

app = FastAPI(
    title="基金透镜 API",
    description="通过 AKShare 查询中国公募基金基础资料、净值、业绩和持仓。",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_fund_file_cache = FundFileCache(
    BASE_DIR / ".cache" / "funds",
    holdings_ttl_seconds=CACHE_TTL_SECONDS,
)
_fund_request_locks: dict[str, asyncio.Lock] = {}
_fund_holdings_request_locks: dict[str, asyncio.Lock] = {}
_benchmark_file_cache = BenchmarkFileCache(
    BASE_DIR / ".cache" / "benchmarks",
)
_benchmark_request_locks: dict[str, asyncio.Lock] = {}
_stock_file_cache = StockFileCache(
    BASE_DIR / ".cache" / "stocks",
)
_stock_request_locks: dict[str, asyncio.Lock] = {}
_watchlist_store = WatchlistFileStore(BASE_DIR / ".data" / "watchlist.json")
WATCHLIST_TAG_SUGGESTIONS = ["持有中", "红利", "固收+", "成长", "价值", "低波"]


class WatchlistFundInput(BaseModel):
    """收藏基金使用官方名称，并允许维护多个本地标签。"""

    name: str = Field(default="", max_length=120)
    fund_type: str = Field(default="", max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=12)


def _clean_watchlist_text(value: str, *, fallback: str = "") -> str:
    cleaned = " ".join(value.strip().split())
    return cleaned or fallback


def _watchlist_payload(payload: dict[str, Any]) -> dict[str, Any]:
    tag_suggestions: list[str] = []
    seen_tags: set[str] = set()
    for item in payload.get("funds", []):
        if not isinstance(item, dict):
            continue
        values = item.get("tags", [])
        if not isinstance(values, list):
            continue
        for value in values:
            tag = str(value or "").strip()
            key = tag.casefold()
            if tag and key not in seen_tags:
                seen_tags.add(key)
                tag_suggestions.append(tag)
    for tag in WATCHLIST_TAG_SUGGESTIONS:
        key = tag.casefold()
        if key not in seen_tags:
            seen_tags.add(key)
            tag_suggestions.append(tag)
    try:
        storage_file = str(_watchlist_store.path.relative_to(BASE_DIR))
    except ValueError:
        storage_file = str(_watchlist_store.path)
    return {
        "基金": payload.get("funds", []),
        "总数": len(payload.get("funds", [])),
        "更新时间": payload.get("updated_at"),
        "标签建议": tag_suggestions,
        "存储文件": storage_file,
    }


def _benchmark_response(
    record: dict[str, Any],
    *,
    cache_result: str,
) -> JSONResponse:
    payload = record["payload"]
    return JSONResponse(
        jsonable_encoder(copy.deepcopy(payload)),
        headers={
            "X-Cache": cache_result,
            "X-Cache-Status": (
                "STALE" if record.get("stale") else "FRESH"
            ),
            "X-Data-Date": str(payload.get("结束日") or ""),
            "X-Next-Refresh": str(record.get("next_refresh_at") or ""),
        },
    )


def _fund_response(
    record: dict[str, Any],
    *,
    cache_result: str,
) -> JSONResponse:
    payload = record["payload"]
    data_date = (
        (payload.get("净值信息") or {}).get("日期")
        or (payload.get("数据来源") or {}).get("查询时间")
        or ""
    )
    return JSONResponse(
        jsonable_encoder(copy.deepcopy(payload)),
        headers={
            "X-Cache": cache_result,
            "X-Cache-Status": (
                "STALE" if record.get("stale") else "FRESH"
            ),
            "X-Data-Date": str(data_date),
            "X-Next-Refresh": str(record.get("next_refresh_at") or ""),
        },
    )


def _stock_response(
    record: dict[str, Any],
    *,
    cache_result: str,
) -> JSONResponse:
    payload = record["payload"]
    data_date = (
        (payload.get("价格趋势") or {}).get("结束日")
        or (payload.get("行情") or {}).get("行情日期")
        or ""
    )
    return JSONResponse(
        jsonable_encoder(copy.deepcopy(payload)),
        headers={
            "X-Cache": cache_result,
            "X-Cache-Status": (
                "STALE" if record.get("stale") else "FRESH"
            ),
            "X-Data-Date": str(data_date),
            "X-Next-Refresh": str(record.get("next_refresh_at") or ""),
        },
    )


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/watchlist", include_in_schema=False)
@app.get("/watchlist/", include_in_schema=False)
async def watchlist_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "watchlist.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/search", include_in_schema=False)
@app.get("/search/", include_in_schema=False)
async def search_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "search.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/watchlist", summary="读取本地自选基金组合")
async def watchlist_detail() -> dict[str, Any]:
    try:
        return _watchlist_payload(_watchlist_store.read())
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/watchlist/{fund_code}", summary="收藏或更新一只自选基金")
async def watchlist_upsert(
    fund_code: str,
    fund: WatchlistFundInput,
) -> dict[str, Any]:
    code = fund_code.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(
            status_code=422,
            detail="基金代码必须是 6 位数字，例如 000001。",
        )
    name = _clean_watchlist_text(fund.name)
    fund_type = _clean_watchlist_text(fund.fund_type)
    tags = normalize_watchlist_tags(fund.tags)
    if not tags:
        tags = [default_watchlist_tag(fund_type)]
    try:
        item, payload = _watchlist_store.upsert(
            code,
            name=name,
            fund_type=fund_type,
            tags=tags,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    response = _watchlist_payload(payload)
    response["基金项"] = item
    return response


@app.delete("/api/watchlist/{fund_code}", summary="从自选组合移除一只基金")
async def watchlist_remove(fund_code: str) -> dict[str, Any]:
    code = fund_code.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(
            status_code=422,
            detail="基金代码必须是 6 位数字，例如 000001。",
        )
    try:
        removed, payload = _watchlist_store.remove(code)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    response = _watchlist_payload(payload)
    response["已移除"] = removed
    return response


@app.get("/api/benchmarks", summary="赛道基准目录")
async def benchmark_catalog() -> dict[str, Any]:
    return {"基准": track_benchmark_catalog()}


@app.get("/api/benchmarks/composite", summary="按业绩比较基准合成的复合基准")
async def benchmark_composite(
    spec: str = Query(
        ...,
        description="复合权重规格，如 csi_dividend:0.95,money_fund:0.05",
    ),
) -> JSONResponse:
    try:
        components = parse_composite_spec(spec)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"无效的复合基准：{exc}") from exc

    canonical = ",".join(f"{key}:{components[key]:.6f}" for key in components)
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]
    cache_key = f"composite_{digest}"

    cached = _benchmark_file_cache.read(cache_key)
    if cached is not None:
        state = _benchmark_file_cache.state(cached)
        if state != "EXPIRED":
            return _benchmark_response(
                cached,
                cache_result="STALE" if state == "STALE" else "HIT",
            )

    lock = _benchmark_request_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        cached = _benchmark_file_cache.read(cache_key)
        if cached is not None:
            state = _benchmark_file_cache.state(cached)
            if state != "EXPIRED":
                return _benchmark_response(
                    cached,
                    cache_result="STALE" if state == "STALE" else "HIT",
                )
        try:
            result = await run_in_threadpool(
                get_composite_benchmark,
                components,
            )
        except Exception as exc:
            if cached is not None:
                stale = _benchmark_file_cache.defer_stale(
                    cache_key,
                    cached,
                    error=str(exc),
                )
                return _benchmark_response(stale, cache_result="STALE")
            raise HTTPException(
                status_code=502,
                detail=f"复合赛道基准上游查询失败：{exc}",
            ) from exc

        record = _benchmark_file_cache.write(cache_key, result)
        return _benchmark_response(record, cache_result="MISS")


@app.get("/api/benchmarks/{benchmark_key}", summary="赛道基准历史行情")
async def benchmark_history(benchmark_key: str) -> JSONResponse:
    if benchmark_key not in TRACK_BENCHMARKS:
        raise HTTPException(status_code=404, detail="未知的赛道基准。")

    cached = _benchmark_file_cache.read(benchmark_key)
    if cached is not None:
        state = _benchmark_file_cache.state(cached)
        if state != "EXPIRED":
            return _benchmark_response(
                cached,
                cache_result="STALE" if state == "STALE" else "HIT",
            )

    lock = _benchmark_request_locks.setdefault(
        benchmark_key,
        asyncio.Lock(),
    )
    async with lock:
        cached = _benchmark_file_cache.read(benchmark_key)
        if cached is not None:
            state = _benchmark_file_cache.state(cached)
            if state != "EXPIRED":
                return _benchmark_response(
                    cached,
                    cache_result=(
                        "STALE" if state == "STALE" else "HIT"
                    ),
                )
        try:
            result = await run_in_threadpool(
                get_track_benchmark,
                benchmark_key,
            )
        except Exception as exc:
            if cached is not None:
                stale = _benchmark_file_cache.defer_stale(
                    benchmark_key,
                    cached,
                    error=str(exc),
                )
                return _benchmark_response(
                    stale,
                    cache_result="STALE",
                )
            raise HTTPException(
                status_code=502,
                detail=f"赛道基准上游查询失败：{exc}",
            ) from exc

        record = _benchmark_file_cache.write(
            benchmark_key,
            result,
        )
        return _benchmark_response(record, cache_result="MISS")


async def _load_fund_record(
    code: str,
    *,
    refresh: bool = False,
) -> tuple[dict[str, Any], str]:
    """读取或按需查询基金记录，返回 (record, cache_result)。

    通过按基金代码维度的 asyncio.Lock 保证同一基金同时只有一个上游查询，
    fund_detail 与 ai-summary 等端点共用该锁。
    """

    cached = _fund_file_cache.read(code)
    if not refresh and cached is not None:
        state = _fund_file_cache.state(cached)
        if state != "EXPIRED":
            return cached, ("STALE" if state == "STALE" else "HIT")

    lock = _fund_request_locks.setdefault(code, asyncio.Lock())
    async with lock:
        cached = _fund_file_cache.read(code)
        if not refresh and cached is not None:
            state = _fund_file_cache.state(cached)
            if state != "EXPIRED":
                return cached, ("STALE" if state == "STALE" else "HIT")
        try:
            result = await run_in_threadpool(
                get_fund_data,
                code,
                FUND_HOLDINGS_LIMIT,
                enrich_stocks=False,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            if not refresh and cached is not None:
                stale = _fund_file_cache.defer_stale(
                    code,
                    cached,
                    error=str(exc),
                )
                return stale, "STALE"
            if isinstance(exc, FundLookupError):
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            raise HTTPException(
                status_code=502,
                detail=f"AKShare 上游查询失败：{exc}",
            ) from exc

        record = _fund_file_cache.write(
            code,
            result,
        )
        return record, "MISS"


@app.get("/api/funds/search", summary="按代码或名称搜索本地基金目录")
async def fund_search(
    q: str = Query(
        ...,
        min_length=1,
        max_length=80,
        description="基金代码、中文名称或拼音",
    ),
    limit: int = Query(default=10, ge=1, le=30),
) -> dict[str, Any]:
    try:
        result = await run_in_threadpool(search_funds, q, limit)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"本地基金目录搜索失败：{exc}",
        ) from exc
    return {"查询": q.strip(), **result}


@app.get(
    "/api/funds/{fund_code}",
    summary="查询单只基金",
    response_description="基金基础资料、净值、历史业绩和最新持仓",
)
async def fund_detail(
    fund_code: str,
    refresh: bool = Query(
        default=False,
        description="强制查询上游并跳过基金日缓存",
    ),
) -> JSONResponse:
    code = fund_code.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(
            status_code=422,
            detail="基金代码必须是 6 位数字，例如 000001。",
        )

    record, cache_result = await _load_fund_record(code, refresh=refresh)
    return _fund_response(record, cache_result=cache_result)


@app.get(
    "/api/funds/{fund_code}/ai-summary",
    summary="基金 AI 友好摘要（一键复制）",
    response_description="AI 友好 Markdown 文本；无缓存时自动查询基金数据",
)
async def fund_ai_summary(fund_code: str) -> PlainTextResponse:
    code = fund_code.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(
            status_code=422,
            detail="基金代码必须是 6 位数字，例如 000001。",
        )

    # 无缓存时主动查询基金数据；共用 fund_detail 的按代码锁，避免并发重复查询。
    record, cache_result = await _load_fund_record(code)

    payload = record.get("payload") or {}
    summary = build_ai_summary(payload)
    return PlainTextResponse(
        summary,
        media_type="text/markdown; charset=utf-8",
        headers={
            "X-Cache": cache_result,
            "X-Cache-Status": "STALE" if record.get("stale") else "FRESH",
            "X-Next-Refresh": str(record.get("next_refresh_at") or ""),
        },
    )


@app.get(
    "/api/bonds/official-link",
    summary="使用 Google 搜索债券",
    include_in_schema=False,
)
async def bond_official_link(
    name: str = Query(default="", max_length=80),
    code: str = Query(default="", max_length=24),
) -> RedirectResponse:
    bond_name = " ".join(name.strip().split())
    bond_code = code.strip()
    if not bond_name and not bond_code:
        raise HTTPException(status_code=422, detail="债券名称和代码不能同时为空。")
    if bond_code and not re.fullmatch(r"[A-Za-z0-9.]+", bond_code):
        raise HTTPException(status_code=422, detail="债券代码格式不正确。")

    query = " ".join(value for value in (bond_name, bond_code) if value)
    return RedirectResponse(
        f"https://www.google.com/search?q={quote(query, safe='')}",
        status_code=302,
    )


@app.get(
    "/api/stocks/{stock_code}",
    summary="查询 A 股详情",
    response_description="股票基础资料、估值指标和前复权收盘价趋势",
)
async def stock_detail(
    stock_code: str,
    refresh: bool = Query(
        default=False,
        description="强制查询上游并跳过股票日缓存",
    ),
) -> JSONResponse:
    code = stock_code.strip()
    if not re.fullmatch(r"\d{6}", code) and not re.fullmatch(r"\d{5}", code):
        raise HTTPException(
            status_code=422,
            detail="股票代码必须是 6 位数字（A 股）或 5 位数字（港股），例如 600519、03328。",
        )

    cached = _stock_file_cache.read(code)
    if not refresh and cached is not None:
        state = _stock_file_cache.state(cached)
        if state != "EXPIRED":
            return _stock_response(
                cached,
                cache_result="STALE" if state == "STALE" else "HIT",
            )

    lock = _stock_request_locks.setdefault(code, asyncio.Lock())
    async with lock:
        cached = _stock_file_cache.read(code)
        if not refresh and cached is not None:
            state = _stock_file_cache.state(cached)
            if state != "EXPIRED":
                return _stock_response(
                    cached,
                    cache_result=(
                        "STALE" if state == "STALE" else "HIT"
                    ),
                )
        try:
            result = await run_in_threadpool(get_stock_data, code)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except StockLookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            if not refresh and cached is not None:
                stale = _stock_file_cache.defer_stale(
                    code,
                    cached,
                    error=str(exc),
                )
                return _stock_response(stale, cache_result="STALE")
            raise HTTPException(
                status_code=502,
                detail=f"股票数据上游查询失败：{exc}",
            ) from exc

        record = _stock_file_cache.write(code, result)
        return _stock_response(record, cache_result="MISS")


@app.get(
    "/api/funds/{fund_code}/holdings",
    summary="按季度查询基金持仓",
    response_description="指定季度的股票、债券持仓和对应季报",
)
async def fund_holdings_by_period(
    fund_code: str,
    period: str = Query(
        ...,
        description="报告期，格式为 YYYYQ1 至 YYYYQ4",
    ),
    holdings_limit: int = Query(default=20, ge=1, le=100),
    refresh: bool = Query(default=False, description="跳过十分钟内的缓存"),
) -> JSONResponse:
    code = fund_code.strip()
    period_key = period.strip().upper()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(
            status_code=422,
            detail="基金代码必须是 6 位数字，例如 000001。",
        )
    if not re.fullmatch(r"20\d{2}Q[1-4]", period_key):
        raise HTTPException(
            status_code=422,
            detail="报告期必须使用 YYYYQ1 至 YYYYQ4 格式。",
        )

    if not refresh:
        cached = _fund_file_cache.read_holdings_period(code, period_key)
        if cached is not None:
            return JSONResponse(
                jsonable_encoder(cached),
                headers={"X-Cache": "HIT"},
            )

    lock = _fund_holdings_request_locks.setdefault(
        f"{code}:{period_key}",
        asyncio.Lock(),
    )
    async with lock:
        # 抢到锁后先复查本地缓存：并发的相同请求只需第一个查下游，
        # 其余请求在此直接命中缓存，避免重复穿透到下游。
        if not refresh:
            cached = _fund_file_cache.read_holdings_period(code, period_key)
            if cached is not None:
                return JSONResponse(
                    jsonable_encoder(cached),
                    headers={"X-Cache": "HIT"},
                )

        try:
            result = await run_in_threadpool(
                get_fund_holdings_by_period,
                code,
                period_key,
                holdings_limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"季度持仓上游查询失败：{exc}",
            ) from exc

        # 写入基金同一文件的季度持仓分区；若主体尚未缓存则跳过写入（依附主体存在）。
        _fund_file_cache.write_holdings_period(code, period_key, result)
        return JSONResponse(
            jsonable_encoder(result),
            headers={"X-Cache": "MISS"},
        )
