"""赛道基准的本地文件缓存。"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_SAFE_KEY = re.compile(r"[A-Za-z0-9_-]+")


class BenchmarkFileCache:
    """将每个赛道基准保存为独立 JSON，并按每日收盘更新窗口刷新。"""

    VERSION = 1

    def __init__(
        self,
        directory: Path,
        *,
        refresh_hour: int = 20,
        stale_retry_minutes: int = 30,
    ) -> None:
        self.directory = directory
        self.refresh_hour = refresh_hour
        self.stale_retry_minutes = stale_retry_minutes

    def read(self, benchmark_key: str) -> dict[str, Any] | None:
        path = self._path(benchmark_key)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

        if (
            not isinstance(record, dict)
            or record.get("version") != self.VERSION
            or record.get("benchmark_key") != benchmark_key
            or not isinstance(record.get("payload"), dict)
            or not isinstance(record.get("next_refresh_at"), str)
        ):
            return None
        return record

    def write(
        self,
        benchmark_key: str,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = self._now(now)
        record = {
            "version": self.VERSION,
            "benchmark_key": benchmark_key,
            "cached_at": current.isoformat(),
            "checked_at": current.isoformat(),
            "next_refresh_at": self.next_refresh(current).isoformat(),
            "stale": False,
            "payload": payload,
        }
        self._write_record(benchmark_key, record)
        return record

    def defer_stale(
        self,
        benchmark_key: str,
        record: dict[str, Any],
        *,
        error: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = self._now(now)
        stale_record = dict(record)
        stale_record.update(
            {
                "checked_at": current.isoformat(),
                "next_refresh_at": (
                    current + timedelta(minutes=self.stale_retry_minutes)
                ).isoformat(),
                "stale": True,
                "last_error": error,
            }
        )
        self._write_record(benchmark_key, stale_record)
        return stale_record

    def state(
        self,
        record: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> str:
        current = self._now(now)
        try:
            refresh_at = datetime.fromisoformat(record["next_refresh_at"])
        except (KeyError, TypeError, ValueError):
            return "EXPIRED"
        if refresh_at.tzinfo is None:
            refresh_at = refresh_at.replace(tzinfo=SHANGHAI_TZ)
        if current >= refresh_at.astimezone(SHANGHAI_TZ):
            return "EXPIRED"
        return "STALE" if record.get("stale") else "FRESH"

    def next_refresh(self, now: datetime | None = None) -> datetime:
        current = self._now(now)
        candidate = current.replace(
            hour=self.refresh_hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        if current >= candidate:
            candidate += timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    def _path(self, benchmark_key: str) -> Path:
        if _SAFE_KEY.fullmatch(benchmark_key) is None:
            raise ValueError("赛道基准 key 包含不安全字符。")
        return self.directory / f"{benchmark_key}.json"

    def _write_record(
        self,
        benchmark_key: str,
        record: dict[str, Any],
    ) -> None:
        path = self._path(benchmark_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{benchmark_key}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    record,
                    stream,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    @staticmethod
    def _now(value: datetime | None = None) -> datetime:
        if value is None:
            return datetime.now(SHANGHAI_TZ)
        if value.tzinfo is None:
            return value.replace(tzinfo=SHANGHAI_TZ)
        return value.astimezone(SHANGHAI_TZ)
