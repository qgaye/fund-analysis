import json
import tempfile
import unittest
from pathlib import Path

from watchlist_store import WatchlistFileStore


class WatchlistFileStoreTests(unittest.TestCase):
    def test_upserts_and_removes_funds_in_a_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watchlist.json"
            store = WatchlistFileStore(path)

            item, payload = store.upsert(
                "000001",
                name="华夏成长",
                fund_type="混合型",
                category="偏股",
                custom_name="成长观察",
            )
            self.assertEqual(item["custom_name"], "成长观察")
            self.assertEqual(len(payload["funds"]), 1)
            self.assertTrue(path.exists())

            updated, payload = store.upsert(
                "000001",
                name="华夏成长",
                fund_type="混合型",
                category="核心仓",
                custom_name="长期成长",
            )
            self.assertEqual(updated["category"], "核心仓")
            self.assertEqual(len(payload["funds"]), 1)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["funds"][0][
                    "custom_name"
                ],
                "长期成长",
            )

            removed, payload = store.remove("000001")
            self.assertTrue(removed)
            self.assertEqual(payload["funds"], [])

    def test_missing_file_reads_as_an_empty_watchlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = WatchlistFileStore(Path(directory) / "watchlist.json")
            self.assertEqual(store.read()["funds"], [])


if __name__ == "__main__":
    unittest.main()
