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
WATCHLIST_VERSION = 2
WATCHLIST_TAG_LIMIT = 12
WATCHLIST_TAG_LENGTH = 24


def default_watchlist_tag(fund_type: str) -> str:
    """把详细基金类型归并为便于浏览的默认标签。"""

    value = str(fund_type or "")
    if "货币" in value:
        return "货币"
    if "QDII" in value or "海外" in value:
        return "QDII"
    if "债" in value or "固收" in value:
        return "债基"
    if "指数" in value or "ETF" in value or "联接" in value:
        return "指数"
    if "FOF" in value:
        return "FOF"
    if "股票" in value or "偏股" in value or "混合" in value:
        return "偏股"
    return "其他"


def normalize_watchlist_tags(values: Any) -> list[str]:
    """清洗、去重并限制本地自选标签。"""

    if not isinstance(values, (list, tuple, set)):
        values = []
    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = " ".join(str(value or "").strip().split())[:WATCHLIST_TAG_LENGTH]
        key = tag.casefold()
        if not tag or key in seen:
            continue
        seen.add(key)
        tags.append(tag)
        if len(tags) >= WATCHLIST_TAG_LIMIT:
            break
    return tags


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
        migrated = payload.get("version") != WATCHLIST_VERSION
        for item in payload["funds"]:
            if not isinstance(item, dict):
                continue
            tags = normalize_watchlist_tags(item.get("tags"))
            legacy_category = str(item.get("category") or "").strip()
            if not tags:
                initial_tags = [
                    default_watchlist_tag(str(item.get("fund_type") or ""))
                ]
                if legacy_category and legacy_category != "未分类":
                    initial_tags.append(legacy_category)
                tags = normalize_watchlist_tags(initial_tags)
            if item.get("tags") != tags:
                item["tags"] = tags
                migrated = True
            if "category" in item:
                item.pop("category", None)
                migrated = True
            if "custom_name" in item:
                item.pop("custom_name", None)
                migrated = True
        payload["version"] = WATCHLIST_VERSION
        payload.setdefault("updated_at", None)
        if migrated:
            self._write_unlocked(payload)
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
        tags: list[str],
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
            official_name = str(existing.get("name") or name)
            cleaned_tags = normalize_watchlist_tags(tags)
            if not cleaned_tags:
                cleaned_tags = [default_watchlist_tag(fund_type)]
            existing.update(
                {
                    "name": official_name,
                    "fund_type": fund_type,
                    "tags": cleaned_tags,
                    "updated_at": now,
                }
            )
            existing.pop("category", None)
            existing.pop("custom_name", None)
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
