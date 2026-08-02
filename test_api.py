import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from benchmark_cache import BenchmarkFileCache, SHANGHAI_TZ
from fund_cache import FundFileCache
from stock_cache import StockFileCache
from watchlist_store import WatchlistFileStore
from app import (
    benchmark_catalog,
    benchmark_history,
    bond_official_link,
    fund_detail,
    fund_holdings_by_period,
    fund_search,
    health,
    stock_detail,
    WatchlistFundInput,
    watchlist_detail,
    watchlist_remove,
    watchlist_upsert,
)


class FundApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_health(self) -> None:
        self.assertEqual(await health(), {"status": "ok"})

    @patch("app.search_funds")
    async def test_searches_local_fund_directory(self, mocked_search) -> None:
        mocked_search.return_value = {
            "基金": [{"代码": "000001", "名称": "华夏成长混合", "类型": "混合型"}],
            "匹配总数": 1,
            "目录月份": "202608",
        }

        result = await fund_search(q="华夏成长", limit=8)

        self.assertEqual(result["基金"][0]["代码"], "000001")
        self.assertEqual(result["查询"], "华夏成长")
        mocked_search.assert_called_once_with("华夏成长", 8)

    async def test_bond_official_link_redirects_to_google_search(self) -> None:
        response = await bond_official_link(
            name="24电网MTN001",
            code="102480901",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["location"],
            "https://www.google.com/search?"
            "q=24%E7%94%B5%E7%BD%91MTN001%20102480901",
        )

    async def test_watchlist_uses_local_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = WatchlistFileStore(Path(directory) / "watchlist.json")
            with patch("app._watchlist_store", store):
                saved = await watchlist_upsert(
                    "000001",
                    WatchlistFundInput(
                        name=" 测试基金 ",
                        fund_type="混合型",
                        category=" 偏股 ",
                        custom_name=" 核心仓 ",
                    ),
                )
                listed = await watchlist_detail()
                removed = await watchlist_remove("000001")

        self.assertEqual(saved["基金项"]["category"], "偏股")
        self.assertEqual(saved["基金项"]["custom_name"], "核心仓")
        self.assertEqual(listed["总数"], 1)
        self.assertEqual(listed["基金"][0]["code"], "000001")
        self.assertTrue(removed["已移除"])
        self.assertEqual(removed["总数"], 0)

    async def test_watchlist_rejects_invalid_fund_code(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await watchlist_upsert("123", WatchlistFundInput())
        self.assertEqual(raised.exception.status_code, 422)

    async def test_rejects_invalid_code(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await fund_detail("123", refresh=False)
        self.assertEqual(raised.exception.status_code, 422)

    async def test_benchmark_catalog_contains_equity_bond_and_money_tracks(
        self,
    ) -> None:
        result = await benchmark_catalog()
        keys = {row["key"] for row in result["基准"]}
        self.assertIn("hs300", keys)
        self.assertIn("cbond_mid_short", keys)
        self.assertIn("money_fund", keys)
        self.assertIn("equity_bond_80_20", keys)

    @patch("app.get_track_benchmark")
    async def test_returns_benchmark_history(self, mocked_lookup) -> None:
        mocked_lookup.return_value = {
            "key": "hs300",
            "名称": "沪深300",
            "结束日": "2026-07-24",
            "明细": [{"日期": "2026-01-01", "指数值": 100}],
        }

        with tempfile.TemporaryDirectory() as directory:
            file_cache = BenchmarkFileCache(Path(directory))
            with patch("app._benchmark_file_cache", file_cache):
                response = await benchmark_history("hs300")
                cached_response = await benchmark_history("hs300")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Cache"], "MISS")
        self.assertEqual(response.headers["X-Cache-Status"], "FRESH")
        self.assertEqual(response.headers["X-Data-Date"], "2026-07-24")
        self.assertEqual(cached_response.headers["X-Cache"], "HIT")
        payload = json.loads(response.body)
        self.assertEqual(payload["key"], "hs300")
        mocked_lookup.assert_called_once_with("hs300")

    @patch("app.get_track_benchmark")
    async def test_returns_stale_file_when_upstream_fails(
        self,
        mocked_lookup,
    ) -> None:
        mocked_lookup.side_effect = RuntimeError("upstream unavailable")
        old_payload = {
            "key": "hs300",
            "结束日": "2026-07-01",
            "明细": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            file_cache = BenchmarkFileCache(Path(directory))
            file_cache.write(
                "hs300",
                old_payload,
                now=datetime(2020, 1, 1, tzinfo=SHANGHAI_TZ),
            )
            with patch("app._benchmark_file_cache", file_cache):
                response = await benchmark_history("hs300")
                retry_response = await benchmark_history("hs300")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Cache"], "STALE")
        self.assertEqual(response.headers["X-Cache-Status"], "STALE")
        self.assertEqual(response.headers["X-Data-Date"], "2026-07-01")
        self.assertEqual(retry_response.headers["X-Cache"], "STALE")
        self.assertEqual(json.loads(response.body), old_payload)
        mocked_lookup.assert_called_once_with("hs300")

    async def test_rejects_unknown_benchmark_without_creating_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file_cache = BenchmarkFileCache(Path(directory))
            with patch("app._benchmark_file_cache", file_cache):
                with self.assertRaises(HTTPException) as raised:
                    await benchmark_history("../../unsafe")

        self.assertEqual(raised.exception.status_code, 404)

    @patch("app.get_fund_data")
    async def test_returns_fund_data(self, mocked_lookup) -> None:
        mocked_lookup.return_value = {
            "基础资料": {"名称": "测试基金", "代码": "000001"},
            "净值信息": {"单位净值": 1.25},
            "历史业绩": {"近1年": 10.5},
            "基金持仓": {"明细": []},
        }

        with tempfile.TemporaryDirectory() as directory:
            file_cache = FundFileCache(Path(directory))
            with patch("app._fund_file_cache", file_cache):
                response = await fund_detail(
                    "000001",
                    refresh=True,
                )
                cached_response = await fund_detail(
                    "000001",
                    refresh=False,
                )
                forced_response = await fund_detail(
                    "000001",
                    refresh=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Cache"], "MISS")
        self.assertEqual(response.headers["X-Cache-Status"], "FRESH")
        self.assertTrue(response.headers["X-Next-Refresh"])
        self.assertEqual(cached_response.headers["X-Cache"], "HIT")
        self.assertEqual(forced_response.headers["X-Cache"], "MISS")
        payload = json.loads(response.body)
        self.assertEqual(payload["基础资料"]["名称"], "测试基金")
        self.assertEqual(mocked_lookup.call_count, 2)
        mocked_lookup.assert_called_with("000001", 20, enrich_stocks=False)

    @patch("app.get_fund_holdings_by_period")
    async def test_returns_requested_quarter_holdings(
        self,
        mocked_lookup,
    ) -> None:
        mocked_lookup.return_value = {
            "季度Key": "2025Q2",
            "报告期": "2025年第2季度",
            "股票持仓": {"明细": [{"股票代码": "000001"}]},
            "债券持仓": {"明细": []},
            "季报列表": [],
        }

        response = await fund_holdings_by_period(
            "000001",
            period="2025q2",
            holdings_limit=20,
            refresh=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Cache"], "MISS")
        payload = json.loads(response.body)
        self.assertEqual(payload["季度Key"], "2025Q2")
        mocked_lookup.assert_called_once_with("000001", "2025Q2", 20)

    async def test_rejects_invalid_quarter_period(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await fund_holdings_by_period(
                "000001",
                period="2025Q5",
                holdings_limit=20,
                refresh=False,
            )
        self.assertEqual(raised.exception.status_code, 422)

    @patch("app.get_stock_data")
    async def test_returns_stock_detail(self, mocked_lookup) -> None:
        mocked_lookup.return_value = {
            "基础信息": {"名称": "贵州茅台", "代码": "600519"},
            "指标": {"PE": 20.0},
            "价格趋势": {"明细": []},
        }

        with tempfile.TemporaryDirectory() as directory:
            file_cache = StockFileCache(Path(directory))
            with patch("app._stock_file_cache", file_cache):
                response = await stock_detail("600519", refresh=True)
                cached_response = await stock_detail(
                    "600519",
                    refresh=False,
                )
                forced_response = await stock_detail(
                    "600519",
                    refresh=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Cache"], "MISS")
        self.assertEqual(response.headers["X-Cache-Status"], "FRESH")
        self.assertTrue(response.headers["X-Next-Refresh"])
        self.assertEqual(cached_response.headers["X-Cache"], "HIT")
        self.assertEqual(forced_response.headers["X-Cache"], "MISS")
        payload = json.loads(response.body)
        self.assertEqual(payload["基础信息"]["名称"], "贵州茅台")
        self.assertEqual(mocked_lookup.call_count, 2)
        mocked_lookup.assert_called_with("600519")

    async def test_rejects_invalid_stock_code(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await stock_detail("6005", refresh=False)
        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
