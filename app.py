"""基金查询 HTTP API 与前端静态页面。"""

from __future__ import annotations

import asyncio
import copy
import re
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from benchmark_cache import BenchmarkFileCache
from benchmarks import (
    TRACK_BENCHMARKS,
    get_track_benchmark,
    track_benchmark_catalog,
)
from fund_cache import FundFileCache
from fund_lookup import (
    FundLookupError,
    get_fund_data,
    get_fund_holdings_by_period,
)
from stock_cache import StockFileCache
from stock_lookup import StockLookupError, get_stock_data


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

_period_holdings_cache: dict[
    tuple[str, str, int],
    tuple[float, dict[str, Any]],
] = {}
_period_holdings_cache_lock = threading.Lock()
_fund_file_cache = FundFileCache(
    BASE_DIR / ".cache" / "funds",
)
_fund_request_locks: dict[str, asyncio.Lock] = {}
_benchmark_file_cache = BenchmarkFileCache(
    BASE_DIR / ".cache" / "benchmarks",
)
_benchmark_request_locks: dict[str, asyncio.Lock] = {}
_stock_file_cache = StockFileCache(
    BASE_DIR / ".cache" / "stocks",
)
_stock_request_locks: dict[str, asyncio.Lock] = {}


def _read_period_holdings_cache(
    key: tuple[str, str, int],
) -> dict[str, Any] | None:
    now = time.monotonic()
    with _period_holdings_cache_lock:
        cached = _period_holdings_cache.get(key)
        if cached is None:
            return None
        stored_at, value = cached
        if now - stored_at > CACHE_TTL_SECONDS:
            _period_holdings_cache.pop(key, None)
            return None
        return copy.deepcopy(value)


def _write_period_holdings_cache(
    key: tuple[str, str, int],
    value: dict[str, Any],
) -> None:
    with _period_holdings_cache_lock:
        _period_holdings_cache[key] = (
            time.monotonic(),
            copy.deepcopy(value),
        )


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/benchmarks", summary="赛道基准目录")
async def benchmark_catalog() -> dict[str, Any]:
    return {"基准": track_benchmark_catalog()}


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

    cached = _fund_file_cache.read(code)
    if not refresh and cached is not None:
        state = _fund_file_cache.state(cached)
        if state != "EXPIRED":
            return _fund_response(
                cached,
                cache_result="STALE" if state == "STALE" else "HIT",
            )

    lock = _fund_request_locks.setdefault(code, asyncio.Lock())
    async with lock:
        cached = _fund_file_cache.read(code)
        if not refresh and cached is not None:
            state = _fund_file_cache.state(cached)
            if state != "EXPIRED":
                return _fund_response(
                    cached,
                    cache_result=(
                        "STALE" if state == "STALE" else "HIT"
                    ),
                )
        try:
            result = await run_in_threadpool(
                get_fund_data,
                code,
                FUND_HOLDINGS_LIMIT,
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
                return _fund_response(stale, cache_result="STALE")
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
        return _fund_response(record, cache_result="MISS")


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
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(
            status_code=422,
            detail="股票代码必须是 6 位数字，例如 600519。",
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

    cache_key = (code, period_key, holdings_limit)
    if not refresh:
        cached = _read_period_holdings_cache(cache_key)
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

    _write_period_holdings_cache(cache_key, result)
    return JSONResponse(
        jsonable_encoder(result),
        headers={"X-Cache": "MISS"},
    )
