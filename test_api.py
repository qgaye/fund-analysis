import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import (
    benchmark_catalog,
    benchmark_history,
    fund_detail,
    health,
)


class FundApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_health(self) -> None:
        self.assertEqual(await health(), {"status": "ok"})

    async def test_rejects_invalid_code(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await fund_detail("123", holdings_limit=20, refresh=False)
        self.assertEqual(raised.exception.status_code, 422)

    async def test_benchmark_catalog_contains_equity_and_bond_tracks(
        self,
    ) -> None:
        result = await benchmark_catalog()
        keys = {row["key"] for row in result["基准"]}
        self.assertIn("hs300", keys)
        self.assertIn("cbond_composite", keys)

    @patch("app.get_track_benchmark")
    async def test_returns_benchmark_history(self, mocked_lookup) -> None:
        mocked_lookup.return_value = {
            "key": "hs300",
            "名称": "沪深300",
            "明细": [{"日期": "2026-01-01", "指数值": 100}],
        }

        response = await benchmark_history("hs300")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["key"], "hs300")

    @patch("app.get_fund_data")
    async def test_returns_fund_data(self, mocked_lookup) -> None:
        mocked_lookup.return_value = {
            "基础资料": {"名称": "测试基金", "代码": "000001"},
            "净值信息": {"单位净值": 1.25},
            "历史业绩": {"近1年": 10.5},
            "基金持仓": {"明细": []},
        }

        response = await fund_detail(
            "000001",
            holdings_limit=10,
            refresh=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Cache"], "MISS")
        payload = json.loads(response.body)
        self.assertEqual(payload["基础资料"]["名称"], "测试基金")
        mocked_lookup.assert_called_once_with("000001", 10)


if __name__ == "__main__":
    unittest.main()
