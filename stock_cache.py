"""股票详情的本地日维度文件缓存。"""

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
_STOCK_CODE = re.compile(r"\d{5,6}")


class StockFileCache:
    """按股票代码持久化，并在交易日收盘后进入下一次更新窗口。"""

    VERSION = 1

    def __init__(
        self,
        directory: Path,
        *,
        refresh_hour: int = 18,
        refresh_minute: int = 0,
        stale_retry_minutes: int = 30,
    ) -> None:
        self.directory = directory
        self.refresh_hour = refresh_hour
        self.refresh_minute = refresh_minute
        self.stale_retry_minutes = stale_retry_minutes

    def read(self, stock_code: str) -> dict[str, Any] | None:
        path = self._path(stock_code)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        if (
            not isinstance(record, dict)
            or record.get("version") != self.VERSION
            or record.get("stock_code") != stock_code
            or not isinstance(record.get("payload"), dict)
            or not isinstance(record.get("next_refresh_at"), str)
        ):
            return None
        return record

    def write(
        self,
        stock_code: str,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = self._now(now)
        record = {
            "version": self.VERSION,
            "stock_code": stock_code,
            "cached_at": current.isoformat(),
            "checked_at": current.isoformat(),
            "next_refresh_at": self.next_refresh(current).isoformat(),
            "stale": False,
            "payload": payload,
        }
        self._write_record(stock_code, record)
        return record

    def defer_stale(
        self,
        stock_code: str,
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
        self._write_record(stock_code, stale_record)
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
            minute=self.refresh_minute,
            second=0,
            microsecond=0,
        )
        if current >= candidate:
            candidate += timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    def _path(self, stock_code: str) -> Path:
        if _STOCK_CODE.fullmatch(stock_code) is None:
            raise ValueError("股票代码必须是 6 位数字（A 股）或 5 位数字（港股）。")
        return self.directory / f"{stock_code}.json"

    def _write_record(
        self,
        stock_code: str,
        record: dict[str, Any],
    ) -> None:
        path = self._path(stock_code)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{stock_code}.",
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
