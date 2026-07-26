import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from benchmark_cache import BenchmarkFileCache, SHANGHAI_TZ


class BenchmarkFileCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.cache_directory = Path(self.temporary_directory.name)
        self.cache = BenchmarkFileCache(self.cache_directory)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_persists_and_can_be_read_by_a_new_instance(self) -> None:
        now = datetime(2026, 7, 24, 10, tzinfo=SHANGHAI_TZ)
        payload = {
            "key": "hs300",
            "结束日": "2026-07-23",
            "明细": [{"日期": "2026-07-23", "指数值": 100}],
        }

        record = self.cache.write("hs300", payload, now=now)
        reloaded = BenchmarkFileCache(self.cache_directory).read("hs300")

        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["payload"], payload)
        self.assertEqual(reloaded["cached_at"], record["cached_at"])

    def test_refreshes_at_20_on_a_weekday(self) -> None:
        friday_morning = datetime(
            2026,
            7,
            24,
            10,
            tzinfo=SHANGHAI_TZ,
        )
        record = self.cache.write(
            "hs300",
            {"key": "hs300"},
            now=friday_morning,
        )

        self.assertEqual(
            record["next_refresh_at"],
            "2026-07-24T20:00:00+08:00",
        )
        self.assertEqual(
            self.cache.state(
                record,
                now=friday_morning.replace(hour=19),
            ),
            "FRESH",
        )
        self.assertEqual(
            self.cache.state(
                record,
                now=friday_morning.replace(hour=20, minute=1),
            ),
            "EXPIRED",
        )

    def test_after_friday_close_next_refresh_is_monday(self) -> None:
        friday_night = datetime(
            2026,
            7,
            24,
            21,
            tzinfo=SHANGHAI_TZ,
        )
        sunday = datetime(
            2026,
            7,
            26,
            12,
            tzinfo=SHANGHAI_TZ,
        )

        self.assertEqual(
            self.cache.next_refresh(friday_night).isoformat(),
            "2026-07-27T20:00:00+08:00",
        )
        self.assertEqual(
            self.cache.next_refresh(sunday).isoformat(),
            "2026-07-27T20:00:00+08:00",
        )

    def test_stale_cache_retries_after_backoff(self) -> None:
        now = datetime(2026, 7, 24, 21, tzinfo=SHANGHAI_TZ)
        record = self.cache.write(
            "hs300",
            {"key": "hs300"},
            now=now - timedelta(days=7),
        )
        stale = self.cache.defer_stale(
            "hs300",
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
        self.assertEqual(stale["last_error"], "upstream unavailable")

    def test_ignores_corrupt_cache_file(self) -> None:
        path = self.cache_directory / "hs300.json"
        path.write_text("{invalid", encoding="utf-8")

        self.assertIsNone(self.cache.read("hs300"))

    def test_written_file_is_valid_json(self) -> None:
        self.cache.write("csi500", {"名称": "中证500"})

        contents = json.loads(
            (self.cache_directory / "csi500.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contents["payload"]["名称"], "中证500")


if __name__ == "__main__":
    unittest.main()
