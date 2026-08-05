import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from fund_cache import FundFileCache, SHANGHAI_TZ


class FundFileCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.cache_directory = Path(self.temporary_directory.name)
        self.cache = FundFileCache(self.cache_directory)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_persists_fund_payload_by_code(self) -> None:
        now = datetime(2026, 7, 24, 10, tzinfo=SHANGHAI_TZ)
        payload = {
            "基础信息": {"代码": "000001"},
            "净值信息": {"日期": "2026-07-23"},
        }

        record = self.cache.write("000001", payload, now=now)
        reloaded = FundFileCache(self.cache_directory).read("000001")

        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["payload"], payload)
        self.assertEqual(reloaded["cached_at"], record["cached_at"])
        self.assertIsNone(self.cache.read("000002"))

    def test_refreshes_only_after_weekday_close(self) -> None:
        friday_morning = datetime(
            2026,
            7,
            24,
            10,
            tzinfo=SHANGHAI_TZ,
        )
        record = self.cache.write(
            "000001",
            {"基础信息": {"代码": "000001"}},
            now=friday_morning,
        )

        self.assertEqual(
            record["next_refresh_at"],
            "2026-07-24T20:00:00+08:00",
        )
        self.assertEqual(
            self.cache.state(
                record,
                now=friday_morning.replace(hour=19, minute=59),
            ),
            "FRESH",
        )
        self.assertEqual(
            self.cache.state(
                record,
                now=friday_morning.replace(hour=20, minute=0),
            ),
            "EXPIRED",
        )

    def test_after_friday_close_waits_until_monday_close(self) -> None:
        friday_after_close = datetime(
            2026,
            7,
            24,
            21,
            tzinfo=SHANGHAI_TZ,
        )

        self.assertEqual(
            self.cache.next_refresh(friday_after_close).isoformat(),
            "2026-07-27T20:00:00+08:00",
        )

    def test_stale_record_retries_after_backoff(self) -> None:
        now = datetime(2026, 7, 24, 16, tzinfo=SHANGHAI_TZ)
        record = self.cache.write(
            "000001",
            {"基础信息": {"代码": "000001"}},
            now=now - timedelta(days=1),
        )
        stale = self.cache.defer_stale(
            "000001",
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
        self.cache.write(
            "000001",
            {"基础信息": {"代码": "000001"}},
        )
        contents = json.loads(
            (self.cache_directory / "000001.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contents["fund_code"], "000001")
        self.assertNotIn("holdings_limit", contents)

    def test_rejects_cache_from_before_manager_history(self) -> None:
        now = datetime(2026, 8, 2, 10, tzinfo=SHANGHAI_TZ)
        record = self.cache.write(
            "001717",
            {"基础资料": {"名称": "工银前沿医疗股票A"}},
            now=now,
        )
        record["version"] = 7
        (self.cache_directory / "001717.json").write_text(
            json.dumps(record, ensure_ascii=False),
            encoding="utf-8",
        )

        self.assertIsNone(self.cache.read("001717"))


if __name__ == "__main__":
    unittest.main()
