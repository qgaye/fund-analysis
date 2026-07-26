import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from stock_cache import SHANGHAI_TZ, StockFileCache


class StockFileCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.cache_directory = Path(self.temporary_directory.name)
        self.cache = StockFileCache(self.cache_directory)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_persists_stock_payload(self) -> None:
        now = datetime(2026, 7, 24, 10, tzinfo=SHANGHAI_TZ)
        payload = {
            "基础信息": {"代码": "600519"},
            "价格趋势": {"结束日": "2026-07-23"},
        }

        record = self.cache.write("600519", payload, now=now)
        reloaded = StockFileCache(self.cache_directory).read("600519")

        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["payload"], payload)
        self.assertEqual(reloaded["cached_at"], record["cached_at"])

    def test_refreshes_only_after_weekday_close(self) -> None:
        friday_morning = datetime(
            2026,
            7,
            24,
            10,
            tzinfo=SHANGHAI_TZ,
        )
        record = self.cache.write(
            "600519",
            {"基础信息": {"代码": "600519"}},
            now=friday_morning,
        )

        self.assertEqual(
            record["next_refresh_at"],
            "2026-07-24T15:30:00+08:00",
        )
        self.assertEqual(
            self.cache.state(
                record,
                now=friday_morning.replace(hour=15, minute=29),
            ),
            "FRESH",
        )
        self.assertEqual(
            self.cache.state(
                record,
                now=friday_morning.replace(hour=15, minute=30),
            ),
            "EXPIRED",
        )

    def test_after_friday_close_waits_until_monday_close(self) -> None:
        friday_after_close = datetime(
            2026,
            7,
            24,
            16,
            tzinfo=SHANGHAI_TZ,
        )

        self.assertEqual(
            self.cache.next_refresh(friday_after_close).isoformat(),
            "2026-07-27T15:30:00+08:00",
        )

    def test_stale_record_retries_after_backoff(self) -> None:
        now = datetime(2026, 7, 24, 16, tzinfo=SHANGHAI_TZ)
        record = self.cache.write(
            "600519",
            {"基础信息": {"代码": "600519"}},
            now=now - timedelta(days=1),
        )
        stale = self.cache.defer_stale(
            "600519",
            record,
            error="upstream unavailable",
            now=now,
        )

        self.assertEqual(
            self.cache.state(stale, now=now + timedelta(minutes=29)),
            "STALE",
        )
        self.assertEqual(
            self.cache.state(stale, now=now + timedelta(minutes=30)),
            "EXPIRED",
        )

    def test_written_file_is_valid_json(self) -> None:
        self.cache.write("000001", {"基础信息": {"代码": "000001"}})
        contents = json.loads(
            (self.cache_directory / "000001.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contents["stock_code"], "000001")


if __name__ == "__main__":
    unittest.main()
