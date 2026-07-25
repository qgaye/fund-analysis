"""基金查询 HTTP API 与前端静态页面。"""

from __future__ import annotations

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

from benchmarks import (
    get_track_benchmark,
    track_benchmark_catalog,
)
from fund_lookup import FundLookupError, get_fund_data


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CACHE_TTL_SECONDS = 10 * 60

app = FastAPI(
    title="基金透镜 API",
    description="通过 AKShare 查询中国公募基金基础资料、净值、业绩和持仓。",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()
_benchmark_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_benchmark_cache_lock = threading.Lock()


def _read_cache(key: tuple[str, int]) -> dict[str, Any] | None:
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is None:
            return None
        stored_at, value = cached
        if now - stored_at > CACHE_TTL_SECONDS:
            _cache.pop(key, None)
            return None
        return copy.deepcopy(value)


def _write_cache(key: tuple[str, int], value: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic(), copy.deepcopy(value))


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/benchmarks", summary="赛道基准目录")
async def benchmark_catalog() -> dict[str, Any]:
    return {"基准": track_benchmark_catalog()}


@app.get("/api/benchmarks/{benchmark_key}", summary="赛道基准历史行情")
async def benchmark_history(benchmark_key: str) -> JSONResponse:
    now = time.monotonic()
    with _benchmark_cache_lock:
        cached = _benchmark_cache.get(benchmark_key)
        if cached is not None and now - cached[0] <= CACHE_TTL_SECONDS:
            return JSONResponse(
                jsonable_encoder(copy.deepcopy(cached[1])),
                headers={"X-Cache": "HIT"},
            )
    try:
        result = await run_in_threadpool(
            get_track_benchmark,
            benchmark_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未知的赛道基准。") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"赛道基准上游查询失败：{exc}",
        ) from exc
    with _benchmark_cache_lock:
        _benchmark_cache[benchmark_key] = (now, copy.deepcopy(result))
    return JSONResponse(
        jsonable_encoder(result),
        headers={"X-Cache": "MISS"},
    )


@app.get(
    "/api/funds/{fund_code}",
    summary="查询单只基金",
    response_description="基金基础资料、净值、历史业绩和最新持仓",
)
async def fund_detail(
    fund_code: str,
    holdings_limit: int = Query(default=20, ge=1, le=100),
    refresh: bool = Query(default=False, description="跳过十分钟内的缓存"),
) -> JSONResponse:
    code = fund_code.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(
            status_code=422,
            detail="基金代码必须是 6 位数字，例如 000001。",
        )

    cache_key = (code, holdings_limit)
    if not refresh:
        cached = _read_cache(cache_key)
        if cached is not None:
            return JSONResponse(
                jsonable_encoder(cached),
                headers={"X-Cache": "HIT"},
            )

    try:
        result = await run_in_threadpool(
            get_fund_data,
            code,
            holdings_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FundLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AKShare 上游查询失败：{exc}",
        ) from exc

    _write_cache(cache_key, result)
    return JSONResponse(
        jsonable_encoder(result),
        headers={"X-Cache": "MISS"},
    )
