import unittest
from datetime import date

import pandas as pd

from fund_investor_return import (
    _fill_share_gaps,
    _modified_dietz,
    _parse_share_change,
    _quarter_reports,
    _summarize_one,
    _xirr,
    summarize_windows,
)


SAMPLE_SHARE_SECTION = """
§6 开放式基金份额变动
单位：份
项目  A类  C类
报告期期初基金份额总额  3,852,051,544.21 683,093,655.29
报告期期间基金总申购份额  139,653,357.08 68,291,249.72
减:报告期期间基金总赎回份额  268,510,054.46 87,937,470.24
报告期期末基金份额总额  3,723,194,846.83 663,447,434.77
"""


class ParseShareChangeTest(unittest.TestCase):
    def test_extracts_primary_class_four_values(self) -> None:
        shares = _parse_share_change(SAMPLE_SHARE_SECTION)
        self.assertAlmostEqual(shares["期初份额"], 3_852_051_544.21)
        self.assertAlmostEqual(shares["申购份额"], 139_653_357.08)
        self.assertAlmostEqual(shares["赎回份额"], 268_510_054.46)
        self.assertAlmostEqual(shares["期末份额"], 3_723_194_846.83)

    def test_returns_none_when_table_absent(self) -> None:
        shares = _parse_share_change("无份额变动表的正文")
        self.assertEqual(
            shares,
            {
                "期初份额": None,
                "申购份额": None,
                "赎回份额": None,
                "期末份额": None,
            },
        )


class QuarterReportsTest(unittest.TestCase):
    def test_filters_quarter_bodies_sorted_ascending(self) -> None:
        reports = pd.DataFrame(
            {
                "公告标题": [
                    "某基金2024年第2季度报告",
                    "某基金2024年第1季度报告",
                    "某基金2024年半年度报告",
                    "某基金2024年第2季度报告摘要",
                ],
                "报告ID": ["AN2", "AN1", "AN9", "AN8"],
                "公告日期": [
                    "2024-07-18",
                    "2024-04-22",
                    "2024-08-24",
                    "2024-07-18",
                ],
            }
        )
        result = _quarter_reports(reports)
        self.assertEqual([item["key"] for item in result], ["2024Q1", "2024Q2"])
        self.assertEqual(result[0]["期末日期"], "2024-03-31")
        self.assertEqual(result[1]["期末日期"], "2024-06-30")


class FillShareGapsTest(unittest.TestCase):
    def test_recovers_missing_cells_via_identities(self) -> None:
        records = [
            {
                "期初份额": 100.0,
                "申购份额": 30.0,
                "赎回份额": 10.0,
                "期末份额": None,  # 由 期初+申购-赎回 推出 = 120
            },
            {
                "期初份额": None,  # 由上一季期末推出 = 120
                "申购份额": 20.0,
                "赎回份额": None,  # 由 期初+申购-期末 推出 = 15
                "期末份额": 125.0,
            },
        ]
        _fill_share_gaps(records)
        self.assertAlmostEqual(records[0]["期末份额"], 120.0)
        self.assertAlmostEqual(records[1]["期初份额"], 120.0)
        self.assertAlmostEqual(records[1]["赎回份额"], 15.0)


class XirrTest(unittest.TestCase):
    def test_simple_one_year_doubling(self) -> None:
        rate = _xirr(
            [(date(2020, 1, 1), -100.0), (date(2021, 1, 1), 110.0)]
        )
        self.assertIsNotNone(rate)
        self.assertAlmostEqual(rate, 0.10, places=3)

    def test_returns_none_without_sign_change(self) -> None:
        self.assertIsNone(
            _xirr([(date(2020, 1, 1), -100.0), (date(2021, 1, 1), -50.0)])
        )


class ModifiedDietzTest(unittest.TestCase):
    def test_midpoint_flow(self) -> None:
        # 期初 100，期末 150，期间净流入 40：收益 = (150-100-40)/(100+20) = 10/120
        value = _modified_dietz(100.0, 150.0, 40.0)
        self.assertAlmostEqual(value, 10.0 / 120.0)


class SummarizeOneTest(unittest.TestCase):
    def test_behavior_gap_negative_when_buying_high(self) -> None:
        # 两季：先大涨后大跌，且资金在高点大量涌入 → 持有人应显著跑输净值。
        records = [
            {
                "报告期": "2020年第1季度",
                "期初日期": "2020-01-01",
                "期末日期": "2020-03-31",
                "期初份额": 100.0,
                "净申赎份额": 900.0,
                "期末份额": 1000.0,
                "期初累计净值": 1.0,
                "期末累计净值": 2.0,
            },
            {
                "报告期": "2020年第2季度",
                "期初日期": "2020-04-01",
                "期末日期": "2020-06-30",
                "期初份额": 1000.0,
                "净申赎份额": 0.0,
                "期末份额": 1000.0,
                "期初累计净值": 2.0,
                "期末累计净值": 1.0,
            },
        ]
        summary = _summarize_one(records)
        self.assertIsNotNone(summary)
        holder = summary["持有人收益率"]["年化"]
        nav = summary["基金净值收益率"]["年化"]
        self.assertLess(holder, nav)
        self.assertLess(summary["行为差距"]["年化"], 0)
        # 份额变化改为区间净申赎加总（900 + 0 = 900），相对期初 100 → +900%。
        share = summary["份额变化"]
        self.assertAlmostEqual(share["净申赎份额"], 900.0)
        self.assertAlmostEqual(share["净申赎比例"], 900.0)


class SummarizeWindowsTest(unittest.TestCase):
    def test_windows_present_and_scoped(self) -> None:
        series = [
            {
                "报告期": f"{year}年第4季度",
                "期初日期": f"{year}-10-01",
                "期末日期": f"{year}-12-31",
                "期初份额": 1000.0,
                "净申赎份额": 0.0,
                "期末份额": 1000.0,
                "期初累计净值": 1.0 + idx * 0.1,
                "期末累计净值": 1.1 + idx * 0.1,
            }
            for idx, year in enumerate((2021, 2022, 2023, 2024))
        ]
        windows = summarize_windows(series, as_of=date(2025, 1, 1))
        self.assertEqual(
            set(windows), {"近1年", "近3年", "近5年", "成立以来"}
        )
        self.assertIsNotNone(windows["成立以来"])
        # 近1年只应纳入 2024Q4 一季。
        self.assertEqual(windows["近1年"]["季度数"], 1)
        # 存续约 3.25 年：近3年有数据，近5年不足年限应置空。
        self.assertIsNotNone(windows["近3年"])
        self.assertIsNone(windows["近5年"])

    def test_short_lived_fund_hides_long_windows(self) -> None:
        # 仅存续约 1.25 年：近3年 / 近5年 与成立以来重合，应置空。
        series = [
            {
                "报告期": f"2024年第{q}季度",
                "期初日期": start,
                "期末日期": end,
                "期初份额": 1000.0,
                "净申赎份额": 0.0,
                "期末份额": 1000.0,
                "期初累计净值": 1.0 + idx * 0.05,
                "期末累计净值": 1.05 + idx * 0.05,
            }
            for idx, (q, start, end) in enumerate(
                (
                    (1, "2024-01-01", "2024-03-31"),
                    (2, "2024-04-01", "2024-06-30"),
                    (3, "2024-07-01", "2024-09-30"),
                    (4, "2024-10-01", "2024-12-31"),
                )
            )
        ]
        windows = summarize_windows(series, as_of=date(2025, 3, 31))
        self.assertIsNotNone(windows["成立以来"])
        self.assertIsNotNone(windows["近1年"])
        self.assertIsNone(windows["近3年"])
        self.assertIsNone(windows["近5年"])


if __name__ == "__main__":
    unittest.main()
