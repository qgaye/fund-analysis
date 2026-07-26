import unittest
from unittest.mock import patch

import pandas as pd

from benchmarks import (
    _composite_series,
    _source_series,
    get_track_benchmark,
    recommend_track_benchmark,
    track_benchmark_catalog,
)


class TrackBenchmarkTests(unittest.TestCase):
    def test_catalog_contains_requested_equity_indices(self) -> None:
        catalog = {row["key"]: row for row in track_benchmark_catalog()}

        self.assertEqual(catalog["hs300"]["名称"], "沪深300")
        self.assertEqual(catalog["csi500"]["名称"], "中证500")
        self.assertEqual(catalog["csi800"]["名称"], "中证800")
        self.assertEqual(
            catalog["equity_bond_80_20"]["说明"],
            "80%沪深300 + 20%中债新综合财富，每日定权复合",
        )

    def test_recommends_credit_benchmark_for_credit_heavy_bond_fund(
        self,
    ) -> None:
        recommendation = recommend_track_benchmark(
            "示例纯债债券A",
            "债券型-长债",
            [
                {"债券品种": "中期票据", "占净值比例": 60},
                {"债券品种": "政策性金融债", "占净值比例": 10},
            ],
        )

        self.assertEqual(recommendation["key"], "cbond_credit")

    def test_recommends_short_benchmark_for_short_bond_fund(self) -> None:
        recommendation = recommend_track_benchmark(
            "示例短债A",
            "债券型-短债",
        )

        self.assertEqual(recommendation["key"], "cbond_short")

    def test_recommends_80_20_for_fixed_income_plus(self) -> None:
        recommendation = recommend_track_benchmark(
            "示例固收+基金",
            "债券型-混合二级",
        )

        self.assertEqual(
            recommendation["key"],
            "fixed_income_plus_80_20",
        )

    def test_disclosed_benchmark_takes_priority_over_fund_type(self) -> None:
        recommendation = recommend_track_benchmark(
            "示例纯债基金",
            "债券型-长债",
            [{"债券品种": "中期票据", "占净值比例": 90}],
            performance_benchmark=(
                "沪深 300 指数收益率×95%＋银行活期存款利率（税后）×5%"
            ),
        )

        self.assertEqual(recommendation["key"], "hs300")
        self.assertIn("业绩比较基准", recommendation["理由"])

    def test_matches_supported_disclosed_benchmarks(self) -> None:
        cases = {
            "中证500指数收益率×90%": "csi500",
            "中证 800 指数收益率": "csi800",
            "中债-新综合财富（1年以下）指数收益率": "cbond_short",
            "中债-信用债总财富（总值）指数收益率": "cbond_credit",
            "中债-国债及政策性银行债财富（总值）指数收益率": "cbond_rates",
            "中债-新综合财富（总值）指数收益率": "cbond_composite",
        }

        for disclosed, expected in cases.items():
            with self.subTest(disclosed=disclosed):
                recommendation = recommend_track_benchmark(
                    "示例基金",
                    "混合型",
                    performance_benchmark=disclosed,
                )
                self.assertEqual(recommendation["key"], expected)

    @patch("benchmarks.ak.stock_zh_index_daily")
    @patch("benchmarks.ak.stock_zh_index_daily_em")
    def test_equity_history_falls_back_to_secondary_source(
        self,
        mocked_primary,
        mocked_fallback,
    ) -> None:
        mocked_primary.side_effect = RuntimeError("primary unavailable")
        mocked_fallback.return_value = pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02"],
                "close": [100.0, 101.0],
            }
        )

        result = _source_series("hs300")

        self.assertEqual(result.iloc[-1], 101.0)
        mocked_fallback.assert_called_once_with(symbol="sh000300")

    @patch("benchmarks._source_series")
    def test_composite_series_uses_daily_fixed_weights(
        self,
        mocked_source,
    ) -> None:
        dates = pd.to_datetime(["2026-01-01", "2026-01-02"])
        mocked_source.side_effect = [
            pd.Series([100.0, 101.0], index=dates),
            pd.Series([100.0, 110.0], index=dates),
        ]

        result = _composite_series({"bond": 0.8, "stock": 0.2})

        self.assertAlmostEqual(result.iloc[-1], 102.8)

    @patch("benchmarks._source_series")
    def test_equity_bond_80_20_uses_eighty_percent_hs300(
        self,
        mocked_source,
    ) -> None:
        dates = pd.to_datetime(["2026-01-01", "2026-01-02"])
        mocked_source.side_effect = [
            pd.Series([100.0, 110.0], index=dates),
            pd.Series([100.0, 101.0], index=dates),
        ]

        result = get_track_benchmark("equity_bond_80_20")

        self.assertEqual(
            [call.args[0] for call in mocked_source.call_args_list],
            ["hs300", "cbond_composite"],
        )
        self.assertAlmostEqual(result["明细"][-1]["指数值"], 108.2)

    @patch("benchmarks._source_series")
    def test_get_track_benchmark_serializes_history(
        self,
        mocked_source,
    ) -> None:
        mocked_source.return_value = pd.Series(
            [100.0, 101.25],
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )

        result = get_track_benchmark("hs300")

        self.assertEqual(result["数量"], 2)
        self.assertEqual(result["明细"][-1]["指数值"], 101.25)


if __name__ == "__main__":
    unittest.main()
