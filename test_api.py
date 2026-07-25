import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import fund_detail, health


class FundApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_health(self) -> None:
        self.assertEqual(await health(), {"status": "ok"})

    async def test_rejects_invalid_code(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await fund_detail("123", holdings_limit=20, refresh=False)
        self.assertEqual(raised.exception.status_code, 422)

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
