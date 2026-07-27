import unittest
from unittest.mock import patch

import pandas as pd

from stock_lookup import (
    _normalize_stock_code,
    _stock_price_history,
    get_stock_data,
)


class StockLookupTests(unittest.TestCase):
    def test_normalize_stock_code(self) -> None:
        self.assertEqual(_normalize_stock_code("600519"), "600519")
        self.assertEqual(_normalize_stock_code("03328"), "03328")
        with self.assertRaises(ValueError):
            _normalize_stock_code("6005")
        with self.assertRaises(ValueError):
            _normalize_stock_code("AAPL")

    @patch("stock_lookup.ak.stock_zh_a_hist")
    def test_stock_price_history_returns_close_curve(
        self,
        mocked_history,
    ) -> None:
        mocked_history.return_value = pd.DataFrame(
            [
                {
                    "日期": "2026-07-23",
                    "收盘": 10.2,
                    "换手率": 1.1,
                    "涨跌幅": 2.0,
                },
                {
                    "日期": "2026-07-24",
                    "收盘": 10.5,
                    "换手率": 1.4,
                    "涨跌幅": 2.94,
                },
            ]
        )

        rows, warning = _stock_price_history("000001", "1991-04-03")

        self.assertIsNone(warning)
        self.assertEqual(rows[-1]["收盘"], 10.5)
        self.assertEqual(rows[-1]["换手率"], 1.4)
        mocked_history.assert_called_once()
        self.assertEqual(
            mocked_history.call_args.kwargs["adjust"],
            "qfq",
        )

    @patch("stock_lookup.ak.stock_zh_a_hist_tx")
    @patch("stock_lookup.ak.stock_zh_a_hist")
    def test_stock_price_history_falls_back_to_tencent(
        self,
        mocked_history,
        mocked_tencent,
    ) -> None:
        mocked_history.side_effect = RuntimeError("eastmoney unavailable")
        mocked_tencent.return_value = pd.DataFrame(
            [
                {
                    "date": "2026-07-24",
                    "close": 10.5,
                    "turnover": 0.014,
                }
            ]
        )

        rows, warning = _stock_price_history("000001", None)

        self.assertEqual(rows[0]["收盘"], 10.5)
        self.assertEqual(rows[0]["换手率"], 1.4)
        self.assertIn("腾讯证券", warning)
        self.assertEqual(
            mocked_tencent.call_args.kwargs["symbol"],
            "sz000001",
        )

    @patch("stock_lookup._stock_price_history")
    @patch("stock_lookup._load_stock_fundamentals")
    @patch("stock_lookup._load_stock_quotes")
    @patch("stock_lookup.ak.stock_individual_info_em")
    def test_get_stock_data_combines_profile_metrics_and_history(
        self,
        mocked_info,
        mocked_quotes,
        mocked_fundamentals,
        mocked_history,
    ) -> None:
        mocked_info.return_value = pd.DataFrame(
            [
                {"item": "股票简称", "value": "平安银行"},
                {"item": "行业", "value": "银行"},
                {"item": "上市时间", "value": "19910403"},
                {"item": "总市值", "value": 200_000_000_000},
            ]
        )
        mocked_quotes.return_value = {
            "000001": {"最新价": 10.5, "行情日期": "2026-07-24"}
        }
        mocked_fundamentals.return_value = {
            "所属行业": "银行",
            "PE": 5.0,
            "PB": 0.5,
            "ROE": 10.0,
            "股息率": 4.0,
            "最新价": 10.5,
            "行情日期": "2026-07-24",
            "估值可用": True,
            "_行业错误": None,
            "_估值错误": None,
            "_分红错误": None,
        }
        mocked_history.return_value = (
            [
                {
                    "日期": "2026-07-23",
                    "收盘": 10.2,
                    "换手率": 1.1,
                    "涨跌幅": 2.0,
                },
                {
                    "日期": "2026-07-24",
                    "收盘": 10.5,
                    "换手率": 1.4,
                    "涨跌幅": 2.94,
                },
            ],
            None,
        )

        result = get_stock_data("000001")

        self.assertEqual(result["基础信息"]["名称"], "平安银行")
        self.assertEqual(result["基础信息"]["上市日期"], "1991-04-03")
        self.assertNotIn("总市值", result["基础信息"])
        self.assertNotIn("总股本", result["基础信息"])
        self.assertEqual(result["指标"]["PE"], 5.0)
        self.assertEqual(result["指标"]["换手率"], 1.4)
        self.assertEqual(result["价格趋势"]["数量"], 2)


if __name__ == "__main__":
    unittest.main()
