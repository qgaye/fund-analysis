import unittest
from datetime import date

import pandas as pd

from fund_lookup import (
    _clean,
    _bond_credit_structure,
    _dividend_history,
    _extract_related_etf_code,
    _extract_scale_details,
    _fund_age,
    _latest_holdings,
    _latest_industry_allocation,
    _nav_history,
    _normalize_code,
    _parse_asset_allocation_report,
    _parse_bond_type_structure,
    _parse_holder_structure,
    _parse_purchase_fee_table,
    _pick,
    _report_period,
    _quarter_end_from_period,
)


class FundLookupTests(unittest.TestCase):
    def test_normalize_code_preserves_leading_zero(self) -> None:
        self.assertEqual(_normalize_code("000001"), "000001")

    def test_normalize_code_rejects_invalid_value(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_code("12345")

    def test_pick_skips_empty_values(self) -> None:
        self.assertEqual(_pick(None, "", "--", 1.25), 1.25)

    def test_clean_serializes_date(self) -> None:
        self.assertEqual(_clean(date(2026, 7, 25)), "2026-07-25")

    def test_fund_age_uses_complete_months(self) -> None:
        self.assertEqual(
            _fund_age("2019-12-10", today=date(2026, 7, 25)),
            "6年7个月",
        )

    def test_extract_scale_details(self) -> None:
        overview = {
            "成立日期/规模": "2019年12月10日 / 0.986亿份",
            "净资产规模": "22.08亿元（截止至：2026年06月30日）",
            "份额规模": "14.2284亿份（截止至：2026年06月30日）",
        }

        details = _extract_scale_details(overview, {})

        self.assertEqual(details["最新净资产"], "22.08亿元")
        self.assertEqual(details["净资产截止日"], "2026-06-30")
        self.assertEqual(details["成立份额"], "0.986亿份")

    def test_parse_holder_structure_selects_latest_row(self) -> None:
        payload = """
        var apidata={ content:"<table><tbody>
        <tr><td>2025-12-31</td><td class='tor'>5.83%</td>
        <td class='tor'>94.17%</td><td class='tor'>0.12%</td>
        <td class='tor'>10.81</td></tr>
        </tbody></table>"};
        """

        structure = _parse_holder_structure(payload)

        self.assertEqual(structure["报告期"], "2025-12-31")
        self.assertEqual(structure["机构持有比例"], 5.83)
        self.assertEqual(structure["个人持有比例"], 94.17)

    def test_parse_purchase_fee_table_splits_channel_discount(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "适用金额": "小于500万元",
                    "原费率|天天基金优惠费率": "1.00% | 0.10%",
                },
                {
                    "适用金额": "大于等于500万元",
                    "原费率|天天基金优惠费率": "每笔1000元",
                },
            ]
        )

        fees = _parse_purchase_fee_table(frame, "申购费率")

        self.assertEqual(fees["明细"][0]["原费率"], "1.00%")
        self.assertEqual(fees["明细"][0]["天天基金优惠费率"], "0.10%")
        self.assertEqual(fees["明细"][1]["原费率"], "每笔1000元")

    def test_latest_holdings_selects_latest_quarter_and_reranks(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "序号": 1,
                    "股票代码": "000001",
                    "占净值比例": 5.0,
                    "季度": "2025年1季度股票投资明细",
                },
                {
                    "序号": 2,
                    "股票代码": "000002",
                    "占净值比例": 3.0,
                    "季度": "2025年1季度股票投资明细",
                },
                {
                    "序号": 3,
                    "股票代码": "000003",
                    "占净值比例": 4.0,
                    "季度": "2025年2季度股票投资明细",
                },
                {
                    "序号": 4,
                    "股票代码": "000004",
                    "占净值比例": 6.0,
                    "季度": "2025年2季度股票投资明细",
                },
            ]
        )

        holdings, period = _latest_holdings(frame, limit=1)

        self.assertEqual(period, "2025年2季度股票投资明细")
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["持仓排名"], 1)
        self.assertEqual(holdings[0]["股票代码"], "000004")
        self.assertNotIn("序号", holdings[0])

    def test_latest_holdings_supports_bonds(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "序号": 1,
                    "债券代码": "102480865",
                    "债券名称": "24中化股MTN001",
                    "占净值比例": 2.5,
                    "持仓市值": 2500.0,
                    "季度": "2026年1季度债券投资明细",
                },
                {
                    "序号": 2,
                    "债券代码": "102480901",
                    "债券名称": "24电网MTN001",
                    "占净值比例": 4.8,
                    "持仓市值": 4800.0,
                    "季度": "2026年1季度债券投资明细",
                },
            ]
        )

        holdings, period = _latest_holdings(frame)

        self.assertEqual(period, "2026年1季度债券投资明细")
        self.assertEqual(holdings[0]["债券代码"], "102480901")
        self.assertEqual(holdings[0]["持仓排名"], 1)
        self.assertNotIn("序号", holdings[0])

    def test_latest_industry_allocation_selects_latest_period(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "序号": 1,
                    "行业类别": "制造业",
                    "占净值比例": 60.0,
                    "市值": 1000.0,
                    "截止时间": "2026-03-31",
                },
                {
                    "序号": 2,
                    "行业类别": "制造业",
                    "占净值比例": 72.0,
                    "市值": 1200.0,
                    "截止时间": "2026-06-30",
                },
                {
                    "序号": 3,
                    "行业类别": "采矿业",
                    "占净值比例": 0.0,
                    "市值": 0.0,
                    "截止时间": "2026-06-30",
                },
                {
                    "序号": 4,
                    "行业类别": "信息技术服务业",
                    "占净值比例": 7.2,
                    "市值": 120.0,
                    "截止时间": "2026-06-30",
                },
            ]
        )

        allocation, period = _latest_industry_allocation(frame)

        self.assertEqual(period, "2026-06-30")
        self.assertEqual(len(allocation), 2)
        self.assertEqual(allocation[0]["行业类别"], "制造业")
        self.assertEqual(allocation[0]["配置排名"], 1)
        self.assertNotIn("序号", allocation[0])

    def test_extract_related_etf_code(self) -> None:
        page_html = """
        <a href="http://fund.eastmoney.com/159549.html">
          查看相关ETF>
        </a>
        """

        self.assertEqual(_extract_related_etf_code(page_html), "159549")
        self.assertIsNone(_extract_related_etf_code("<p>普通基金</p>"))

    def test_parse_asset_allocation_report(self) -> None:
        report_text = """
        5.1 报告期末基金资产组合情况
        1 权益投资 245,818,353.83 4.31
        2 基金投资 5,097,248,562.99 89.41
        3 固定收益投资 - -
        7 银行存款和结算备付金合计 317,637,866.22 5.57
        8 其他资产 40,427,405.94 0.71
        9 合计 5,701,132,188.98 100.00
        5.2 报告期末按行业分类的股票投资组合
        """

        allocation = _parse_asset_allocation_report(report_text)

        self.assertEqual(
            allocation,
            [
                {"资产类别": "股票", "占比": 4.31},
                {"资产类别": "债券", "占比": 0.0},
                {"资产类别": "基金", "占比": 89.41},
                {"资产类别": "其他", "占比": 6.28},
            ],
        )

    def test_parse_asset_allocation_supports_compact_headings(self) -> None:
        report_text = """
        5.1报告期末基金资产组合情况
        1 权益投资 - -
        2 基金投资 - -
        3 固定收益投资 16,712,053,712.95 97.25
        9 合计 17,185,182,596.62 100.00
        5.2报告期末按行业分类的股票投资组合
        """

        allocation = _parse_asset_allocation_report(report_text)

        self.assertEqual(allocation[1], {"资产类别": "债券", "占比": 97.25})
        self.assertEqual(allocation[3], {"资产类别": "其他", "占比": 2.75})

    def test_parse_bond_type_structure_splits_policy_financial_bonds(
        self,
    ) -> None:
        report_text = """
        5.4 报告期末按债券品种分类的债券投资组合
        序号 债券品种 公允价值（元） 占基金资产净值比例（%）
        1 国家债券 - -
        2 央行票据 - -
        3 金融债券 1,800,000,000.00 49.18
        其中：政策性金融债 348,000,000.00 9.51
        4 企业债券 866,000,000.00 23.68
        5 企业短期融资券 - -
        6 中期票据 1,993,000,000.00 54.47
        7 可转债（可交换债） - -
        8 同业存单 - -
        9 其他 199,800,000.00 5.46
        10 合计 4,858,800,000.00 132.79
        注：其他为地方政府债。
        5.5 报告期末按公允价值占基金资产净值比例大小排序的
        """

        structure = _parse_bond_type_structure(report_text)

        self.assertEqual(
            structure,
            [
                {"债券品种": "政策性金融债", "占净值比例": 9.51},
                {"债券品种": "地方政府债", "占净值比例": 5.46},
                {
                    "债券品种": "金融债（不含政策性）",
                    "占净值比例": 39.67,
                },
                {"债券品种": "企业债券", "占净值比例": 23.68},
                {"债券品种": "中期票据", "占净值比例": 54.47},
            ],
        )

    def test_bond_credit_structure_keeps_credit_and_rate_debt_distinct(
        self,
    ) -> None:
        structure = _bond_credit_structure(
            [
                {"债券品种": "政策性金融债", "占净值比例": 10.0},
                {"债券品种": "企业债券", "占净值比例": 25.0},
                {"债券品种": "中期票据", "占净值比例": 40.0},
            ]
        )

        self.assertEqual(
            structure,
            [
                {"信用属性": "利率债", "占净值比例": 10.0},
                {"信用属性": "信用债", "占净值比例": 65.0},
            ],
        )

    def test_quarter_end_from_holding_period(self) -> None:
        self.assertEqual(
            _quarter_end_from_period("2026年2季度债券投资明细"),
            date(2026, 6, 30),
        )

    def test_report_period_normalizes_chinese_quarter(self) -> None:
        self.assertEqual(
            _report_period("某基金2026年第二季度报告"),
            "2026年第2季度",
        )

    def test_nav_history_sorts_cleans_and_preserves_endpoints(self) -> None:
        frame = pd.DataFrame(
            [
                {"净值日期": "2026-01-03", "单位净值": 1.03, "日增长率": 0.2},
                {"净值日期": "invalid", "单位净值": 1.02, "日增长率": 0.1},
                {"净值日期": "2026-01-01", "单位净值": 1.00, "日增长率": 0.0},
                {"净值日期": "2026-01-02", "单位净值": 1.01, "日增长率": 0.1},
            ]
        )

        history = _nav_history(frame, max_points=2)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["日期"], "2026-01-01")
        self.assertEqual(history[-1]["日期"], "2026-01-03")
        self.assertEqual(history[-1]["单位净值"], 1.03)

    def test_dividend_history_extracts_per_share_amount(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "除息日": "2025-04-10",
                    "每10份分红": "每10份派现金0.1400元",
                }
            ]
        )

        dividends = _dividend_history(frame)

        self.assertEqual(dividends[0]["除息日"], "2025-04-10")
        self.assertAlmostEqual(dividends[0]["每份分红"], 0.014)


if __name__ == "__main__":
    unittest.main()
