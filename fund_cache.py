"""基金详情的本地日维度文件缓存。"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_FUND_CODE = re.compile(r"\d{6}")
_PERIOD_KEY = re.compile(r"20\d{2}Q[1-4]")


class FundFileCache:
    """按基金代码持久化，并在工作日收盘后更新。"""

    VERSION = 4

    def __init__(
        self,
        directory: Path,
        *,
        refresh_hour: int = 15,
        refresh_minute: int = 30,
        stale_retry_minutes: int = 30,
        holdings_ttl_seconds: int = 10 * 60,
    ) -> None:
        self.directory = directory
        self.refresh_hour = refresh_hour
        self.refresh_minute = refresh_minute
        self.stale_retry_minutes = stale_retry_minutes
        self.holdings_ttl_seconds = holdings_ttl_seconds
        # 保护同一文件的读改写：基金主体与季度持仓分区可能来自不同请求线程。
        self._file_locks: dict[str, threading.Lock] = {}
        self._file_locks_guard = threading.Lock()

    def _file_lock(self, fund_code: str) -> threading.Lock:
        with self._file_locks_guard:
            return self._file_locks.setdefault(fund_code, threading.Lock())

    def _read_raw(self, fund_code: str) -> dict[str, Any] | None:
        """读取原始记录（不做版本/字段校验），供内部读改写复用。"""
        path = self._path(fund_code)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return record if isinstance(record, dict) else None

    def read(self, fund_code: str) -> dict[str, Any] | None:
        record = self._read_raw(fund_code)
        if (
            not isinstance(record, dict)
            or record.get("version") != self.VERSION
            or record.get("fund_code") != fund_code
            or not isinstance(record.get("payload"), dict)
            or not isinstance(record.get("next_refresh_at"), str)
        ):
            return None
        return record

    def write(
        self,
        fund_code: str,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = self._now(now)
        with self._file_lock(fund_code):
            # 保留季度持仓分区：基金主体刷新不应抹掉已缓存的持仓估值。
            existing = self._read_raw(fund_code)
            holdings_periods = (
                existing.get("holdings_periods")
                if isinstance(existing, dict)
                else None
            )
            record = {
                "version": self.VERSION,
                "fund_code": fund_code,
                "cached_at": current.isoformat(),
                "checked_at": current.isoformat(),
                "next_refresh_at": self.next_refresh(current).isoformat(),
                "stale": False,
                "payload": payload,
            }
            if isinstance(holdings_periods, dict) and holdings_periods:
                record["holdings_periods"] = holdings_periods
            self._write_record(fund_code, record)
        return record

    def read_holdings_period(
        self,
        fund_code: str,
        period: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """读取季度持仓分区；超过独立 TTL 视为失效。"""
        current = self._now(now)
        with self._file_lock(fund_code):
            record = self._read_raw(fund_code)
            if not isinstance(record, dict):
                return None
            periods = record.get("holdings_periods")
            if not isinstance(periods, dict):
                return None
            entry = periods.get(period)
            if not isinstance(entry, dict):
                return None
            cached_at = entry.get("cached_at")
            value = entry.get("value")
            if not isinstance(cached_at, str) or not isinstance(value, dict):
                return None
            try:
                stored_at = datetime.fromisoformat(cached_at)
            except ValueError:
                return None
            if stored_at.tzinfo is None:
                stored_at = stored_at.replace(tzinfo=SHANGHAI_TZ)
            age = (current - stored_at.astimezone(SHANGHAI_TZ)).total_seconds()
            if age > self.holdings_ttl_seconds:
                return None
            return value

    def write_holdings_period(
        self,
        fund_code: str,
        period: str,
        value: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> None:
        """写入季度持仓分区，保留基金主体与其它季度。

        若尚无基金主体记录则不创建骨架，直接跳过——季度持仓依附于
        主体文件存在，避免产生只有持仓、缺主体的半成品记录。
        """
        if _PERIOD_KEY.fullmatch(period) is None:
            raise ValueError("报告期必须使用 YYYYQ1 至 YYYYQ4 格式。")
        current = self._now(now)
        with self._file_lock(fund_code):
            record = self._read_raw(fund_code)
            if (
                not isinstance(record, dict)
                or record.get("version") != self.VERSION
                or not isinstance(record.get("payload"), dict)
            ):
                return
            periods = record.get("holdings_periods")
            if not isinstance(periods, dict):
                periods = {}
            periods[period] = {
                "cached_at": current.isoformat(),
                "value": value,
            }
            record["holdings_periods"] = periods
            self._write_record(fund_code, record)

    def defer_stale(
        self,
        fund_code: str,
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
        self._write_record(fund_code, stale_record)
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

    def _path(self, fund_code: str) -> Path:
        if _FUND_CODE.fullmatch(fund_code) is None:
            raise ValueError("基金代码必须是 6 位数字。")
        return self.directory / f"{fund_code}.json"

    def _write_record(
        self,
        fund_code: str,
        record: dict[str, Any],
    ) -> None:
        path = self._path(fund_code)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{fund_code}.",
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
