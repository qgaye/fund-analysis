import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from benchmarks import (
    _composite_series,
    _source_series,
    get_composite_benchmark,
    get_track_benchmark,
    match_performance_benchmark,
    parse_composite_spec,
    parse_performance_benchmark,
    recommend_track_benchmark,
    track_benchmark_catalog,
)


class TrackBenchmarkTests(unittest.TestCase):
    def test_catalog_contains_requested_equity_indices(self) -> None:
        catalog = {row["key"]: row for row in track_benchmark_catalog()}

        self.assertEqual(catalog["hs300"]["名称"], "沪深300")
        self.assertEqual(catalog["csi500"]["名称"], "中证500")
        self.assertEqual(catalog["csi800"]["名称"], "中证800")
        self.assertEqual(catalog["csi1000"]["名称"], "中证1000")
        self.assertEqual(catalog["csi2000"]["名称"], "中证2000")
        self.assertEqual(catalog["chinext"]["名称"], "创业板指")
        self.assertEqual(catalog["star50"]["名称"], "科创50")
        self.assertEqual(catalog["csi_dividend"]["名称"], "中证红利")
        self.assertEqual(catalog["money_fund"]["简称"], "货币基金")
        self.assertEqual(catalog["money_fund"]["类型"], "货币现金")
        self.assertEqual(
            catalog["equity_bond_80_20"]["说明"],
            "80%沪深300 + 20%中债新综合财富，每日定权复合",
        )

    def test_recommends_money_fund_benchmark_for_money_market_fund(
        self,
    ) -> None:
        recommendation = recommend_track_benchmark(
            "示例货币基金A",
            "货币型",
        )

        self.assertEqual(recommendation["key"], "money_fund")

    def test_recommends_mid_long_benchmark_for_long_bond_fund(
        self,
    ) -> None:
        recommendation = recommend_track_benchmark(
            "示例中长债债券A",
            "债券型-长债",
        )

        self.assertEqual(recommendation["key"], "cbond_mid_long")

    def test_recommends_mid_short_benchmark_for_short_bond_fund(self) -> None:
        recommendation = recommend_track_benchmark(
            "示例短债A",
            "债券型-短债",
        )

        self.assertEqual(recommendation["key"], "cbond_mid_short")

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

        self.assertEqual(recommendation["key"], "performance_composite")
        self.assertEqual(
            recommendation["复合"],
            {"hs300": 0.95, "money_fund": 0.05},
        )
        self.assertIn("业绩比较基准", recommendation["理由"])

    def test_matches_supported_disclosed_benchmarks(self) -> None:
        cases = {
            "中证500指数收益率×90%": "csi500",
            "中证 800 指数收益率": "csi800",
            "中证1000指数收益率×95%": "csi1000",
            "中证2000指数收益率": "csi2000",
            "创业板指数收益率×90%": "chinext",
            "科创50指数收益率": "star50",
            "中证红利指数收益率×80%": "csi_dividend",
            "中债-新综合财富（1-3年）指数收益率": "cbond_mid_short",
            "中债-新综合财富（5-7年）指数收益率": "cbond_mid_long",
        }

        for disclosed, expected in cases.items():
            with self.subTest(disclosed=disclosed):
                recommendation = recommend_track_benchmark(
                    "示例基金",
                    "混合型",
                    performance_benchmark=disclosed,
                )
                self.assertEqual(recommendation["key"], expected)

    def test_recommends_style_benchmarks_by_fund_descriptor(self) -> None:
        cases = {
            ("示例科创板50ETF", "股票型"): "star50",
            ("示例创业板成长", "股票型"): "chinext",
            ("示例红利低波", "股票型"): "csi_dividend",
            ("示例中证2000指数", "指数型"): "csi2000",
            ("示例小盘精选", "股票型"): "csi1000",
            ("示例中小盘混合", "混合型"): "csi500",
            ("示例价值蓝筹", "混合型"): "csi_dividend",
        }

        for (name, fund_type), expected in cases.items():
            with self.subTest(name=name):
                recommendation = recommend_track_benchmark(name, fund_type)
                self.assertEqual(recommendation["key"], expected)

    def test_recommends_mid_short_benchmark_for_generic_bond_fund(
        self,
    ) -> None:
        recommendation = recommend_track_benchmark(
            "示例纯债债券A",
            "债券型-中长期纯债",
        )

        self.assertEqual(recommendation["key"], "cbond_mid_short")

    @patch("benchmarks.ak.stock_zh_index_daily_tx")
    def test_equity_history_prefers_tencent_source(
        self,
        mocked_tx,
    ) -> None:
        recent = date.today().strftime("%Y-%m-%d")
        mocked_tx.return_value = pd.DataFrame(
            {
                "date": ["2026-01-01", recent],
                "close": [100.0, 101.0],
            }
        )

        result = _source_series("hs300")

        self.assertEqual(result.iloc[-1], 101.0)
        mocked_tx.assert_called_once_with(symbol="sh000300")

    @patch("benchmarks.ak.stock_zh_index_hist_csindex")
    @patch("benchmarks.ak.index_zh_a_hist")
    @patch("benchmarks.ak.stock_zh_index_daily")
    @patch("benchmarks.ak.stock_zh_index_daily_em")
    @patch("benchmarks.ak.stock_zh_index_daily_tx")
    def test_equity_history_falls_back_to_secondary_source(
        self,
        mocked_tx,
        mocked_em,
        mocked_sina,
        mocked_cn_hist,
        mocked_csindex,
    ) -> None:
        recent = date.today().strftime("%Y-%m-%d")
        mocked_tx.side_effect = IndexError("list index out of range")
        mocked_em.side_effect = RuntimeError("primary unavailable")
        mocked_cn_hist.return_value = pd.DataFrame(
            {
                "日期": ["2026-01-01", recent],
                "收盘": [100.0, 101.0],
            }
        )

        result = _source_series("hs300")

        self.assertEqual(result.iloc[-1], 101.0)
        mocked_csindex.assert_not_called()
        mocked_sina.assert_not_called()

    @patch("benchmarks.ak.stock_zh_index_hist_csindex")
    @patch("benchmarks.ak.index_zh_a_hist")
    @patch("benchmarks.ak.stock_zh_index_daily")
    @patch("benchmarks.ak.stock_zh_index_daily_em")
    @patch("benchmarks.ak.stock_zh_index_daily_tx")
    def test_equity_history_uses_csindex_for_new_index(
        self,
        mocked_tx,
        mocked_em,
        mocked_sina,
        mocked_cn_hist,
        mocked_csindex,
    ) -> None:
        recent = date.today().strftime("%Y-%m-%d")
        # 中证2000 不被腾讯/东财/新浪支持，需由中证官网兜底。
        mocked_tx.side_effect = IndexError("list index out of range")
        mocked_em.return_value = pd.DataFrame()
        mocked_cn_hist.side_effect = ConnectionError("blocked")
        mocked_csindex.return_value = pd.DataFrame(
            {
                "日期": ["2026-01-01", recent],
                "收盘": [1000.0, 1010.0],
            }
        )

        result = _source_series("csi2000")

        self.assertEqual(result.iloc[-1], 1010.0)
        mocked_sina.assert_not_called()
        mocked_csindex.assert_called_once_with(
            symbol="932000",
            start_date="19900101",
            end_date=date.today().strftime("%Y%m%d"),
        )

    @patch("benchmarks.ak.stock_zh_index_hist_csindex")
    @patch("benchmarks.ak.index_zh_a_hist")
    @patch("benchmarks.ak.stock_zh_index_daily")
    @patch("benchmarks.ak.stock_zh_index_daily_em")
    @patch("benchmarks.ak.stock_zh_index_daily_tx")
    def test_equity_history_skips_stale_source_for_fresh_one(
        self,
        mocked_tx,
        mocked_em,
        mocked_sina,
        mocked_cn_hist,
        mocked_csindex,
    ) -> None:
        recent = date.today().strftime("%Y-%m-%d")
        # 腾讯源虽有数据，但停更在数年前，应被跳过并采用新鲜的中证历史源。
        mocked_tx.return_value = pd.DataFrame(
            {
                "date": ["2018-12-28", "2019-01-30"],
                "close": [3990.0, 4000.74],
            }
        )
        mocked_em.return_value = pd.DataFrame()
        mocked_cn_hist.return_value = pd.DataFrame(
            {
                "日期": ["2026-01-01", recent],
                "收盘": [5400.0, 5434.0],
            }
        )

        result = _source_series("csi_dividend")

        self.assertEqual(result.iloc[-1], 5434.0)
        mocked_sina.assert_not_called()

    @patch("benchmarks.ak.stock_zh_index_hist_csindex")
    @patch("benchmarks.ak.index_zh_a_hist")
    @patch("benchmarks.ak.stock_zh_index_daily")
    @patch("benchmarks.ak.stock_zh_index_daily_em")
    @patch("benchmarks.ak.stock_zh_index_daily_tx")
    def test_equity_history_returns_freshest_when_all_stale(
        self,
        mocked_tx,
        mocked_em,
        mocked_sina,
        mocked_cn_hist,
        mocked_csindex,
    ) -> None:
        # 所有源都过期时，返回其中最新鲜的一份而非首个命中的。
        mocked_tx.return_value = pd.DataFrame(
            {"date": ["2017-01-01"], "close": [3000.0]}
        )
        mocked_em.return_value = pd.DataFrame(
            {"date": ["2016-01-01"], "close": [2800.0]}
        )
        mocked_cn_hist.return_value = pd.DataFrame(
            {"日期": ["2019-01-30"], "收盘": [4000.74]}
        )
        mocked_csindex.return_value = pd.DataFrame(
            {"日期": ["2018-06-01"], "收盘": [3500.0]}
        )
        mocked_sina.return_value = pd.DataFrame(
            {"date": ["2017-06-01"], "close": [3200.0]}
        )

        result = _source_series("csi_dividend")

        self.assertEqual(result.iloc[-1], 4000.74)

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


class PerformanceBenchmarkParsingTests(unittest.TestCase):
    def test_parse_extracts_names_and_weights(self) -> None:
        components = parse_performance_benchmark(
            "中证800成长指数收益率*70%+中债-综合全价(总值)指数收益率*30%"
        )

        self.assertEqual(len(components), 2)
        self.assertEqual(components[0]["权重"], 0.7)
        self.assertEqual(components[1]["权重"], 0.3)
        self.assertIn("中证800", components[0]["原文"])

    def test_parse_normalizes_fullwidth_symbols(self) -> None:
        components = parse_performance_benchmark(
            "沪深 300 指数收益率×95%＋银行活期存款利率（税后）×5%"
        )

        self.assertEqual([c["权重"] for c in components], [0.95, 0.05])

    def test_parse_single_component_defaults_full_weight(self) -> None:
        components = parse_performance_benchmark("中证500指数收益率")

        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["权重"], 1.0)

    def test_match_maps_dividend_and_cash_to_composite(self) -> None:
        matched = match_performance_benchmark(
            "中证沪港深红利成长低波动指数收益率*95%"
            "+银行活期存款利率(税后)*5%"
        )

        self.assertIsNotNone(matched)
        self.assertAlmostEqual(matched["components"]["csi_dividend"], 0.95)
        self.assertAlmostEqual(matched["components"]["money_fund"], 0.05)

    def test_match_returns_none_when_component_unmatched(self) -> None:
        # 中证白酒无对应赛道基准，应整体放弃。
        matched = match_performance_benchmark(
            "中证白酒指数收益率*95%"
            "+金融机构人民币活期存款基准利率(税后)*5%"
        )

        self.assertIsNone(matched)

    def test_recommend_returns_composite_for_multi_component(self) -> None:
        recommendation = recommend_track_benchmark(
            "示例红利低波基金",
            "指数型-股票",
            performance_benchmark=(
                "中证红利指数收益率*90%+银行活期存款利率(税后)*10%"
            ),
        )

        self.assertEqual(recommendation["key"], "performance_composite")
        self.assertAlmostEqual(recommendation["复合"]["csi_dividend"], 0.9)
        self.assertAlmostEqual(recommendation["复合"]["money_fund"], 0.1)

    def test_recommend_falls_back_when_unmatched(self) -> None:
        recommendation = recommend_track_benchmark(
            "示例白酒指数基金",
            "指数型-股票",
            performance_benchmark="中证白酒指数收益率*95%",
        )

        self.assertNotEqual(recommendation["key"], "performance_composite")

    def test_parse_composite_spec_normalizes_weights(self) -> None:
        components = parse_composite_spec("csi_dividend:0.95,money_fund:0.05")

        self.assertAlmostEqual(components["csi_dividend"], 0.95)
        self.assertAlmostEqual(components["money_fund"], 0.05)

    def test_parse_composite_spec_rejects_unknown_key(self) -> None:
        with self.assertRaises(ValueError):
            parse_composite_spec("not_a_key:1")

    @patch("benchmarks._source_series")
    def test_get_composite_benchmark_serializes(self, mocked_source) -> None:
        dates = pd.to_datetime(["2026-01-01", "2026-01-02"])
        mocked_source.side_effect = [
            pd.Series([100.0, 110.0], index=dates),
            pd.Series([100.0, 100.0], index=dates),
        ]

        result = get_composite_benchmark({"hs300": 0.8, "money_fund": 0.2})

        self.assertEqual(result["key"], "performance_composite")
        self.assertEqual(result["数量"], 2)
        self.assertEqual(len(result["构成"]), 2)
        # 80% 涨 10% + 20% 持平 = 8%。
        self.assertAlmostEqual(result["明细"][-1]["指数值"], 108.0)


if __name__ == "__main__":
    unittest.main()
