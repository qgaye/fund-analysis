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
                tags=["偏股", "成长"],
            )
            self.assertEqual(item["tags"], ["偏股", "成长"])
            self.assertNotIn("custom_name", item)
            self.assertNotIn("category", item)
            self.assertEqual(len(payload["funds"]), 1)
            self.assertTrue(path.exists())

            updated, payload = store.upsert(
                "000001",
                name="不应覆盖的名称",
                fund_type="混合型",
                tags=["偏股", "价值", "价值"],
            )
            self.assertEqual(updated["name"], "华夏成长")
            self.assertEqual(updated["tags"], ["偏股", "价值"])
            self.assertEqual(len(payload["funds"]), 1)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["funds"][0]["name"],
                "华夏成长",
            )

            removed, payload = store.remove("000001")
            self.assertTrue(removed)
            self.assertEqual(payload["funds"], [])

    def test_migrates_legacy_category_and_discards_custom_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watchlist.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "updated_at": None,
                        "funds": [
                            {
                                "code": "006212",
                                "name": "平安短债债券A",
                                "fund_type": "债券型",
                                "category": "稳健仓",
                                "custom_name": "我的短债",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = WatchlistFileStore(path).read()
            item = payload["funds"][0]

            self.assertEqual(payload["version"], 2)
            self.assertEqual(item["name"], "平安短债债券A")
            self.assertEqual(item["tags"], ["债基", "稳健仓"])
            self.assertNotIn("category", item)
            self.assertNotIn("custom_name", item)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["version"],
                2,
            )

    def test_missing_file_reads_as_an_empty_watchlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = WatchlistFileStore(Path(directory) / "watchlist.json")
            self.assertEqual(store.read()["funds"], [])


if __name__ == "__main__":
    unittest.main()
