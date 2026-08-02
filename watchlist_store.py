"""自选基金组合的本地 JSON 文件存储。"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
WATCHLIST_VERSION = 1


class WatchlistFileStore:
    """用单个 JSON 文件维护自选基金，写入时使用原子替换。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "version": WATCHLIST_VERSION,
            "updated_at": None,
            "funds": [],
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(SHANGHAI_TZ).isoformat(timespec="seconds")

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"自选组合文件读取失败：{exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("funds"), list):
            raise RuntimeError("自选组合文件格式无效。")
        payload.setdefault("version", WATCHLIST_VERSION)
        payload.setdefault("updated_at", None)
        return payload

    def _write_unlocked(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(serialized)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = temporary.name
            os.replace(temporary_path, self.path)
        except OSError as exc:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)
            raise RuntimeError(f"自选组合文件写入失败：{exc}") from exc

    def read(self) -> dict[str, Any]:
        with self._lock:
            payload = self._read_unlocked()
            return json.loads(json.dumps(payload, ensure_ascii=False))

    def upsert(
        self,
        code: str,
        *,
        name: str,
        fund_type: str,
        category: str,
        custom_name: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._lock:
            payload = self._read_unlocked()
            now = self._now()
            existing = next(
                (item for item in payload["funds"] if item.get("code") == code),
                None,
            )
            if existing is None:
                existing = {"code": code, "added_at": now}
                payload["funds"].insert(0, existing)
            existing.update(
                {
                    "name": name,
                    "fund_type": fund_type,
                    "category": category,
                    "custom_name": custom_name,
                    "updated_at": now,
                }
            )
            payload["updated_at"] = now
            self._write_unlocked(payload)
            return dict(existing), payload

    def remove(self, code: str) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            payload = self._read_unlocked()
            original_count = len(payload["funds"])
            payload["funds"] = [
                item for item in payload["funds"] if item.get("code") != code
            ]
            removed = len(payload["funds"]) != original_count
            if removed:
                payload["updated_at"] = self._now()
                self._write_unlocked(payload)
            return removed, payload
