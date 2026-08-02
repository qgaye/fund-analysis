import unittest
from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
from bs4 import BeautifulSoup

from fund_lookup import (
    _bond_credit_structure,
    _clean,
    _compare_share_class_costs,
    _dividend_history,
    _enrich_stock_holdings,
    _extract_related_etf_code,
    _extract_scale_details,
    _extract_fund_company,
    _fund_age,
    _holdings_for_period,
    _latest_holdings,
    _latest_industry_allocation,
    _load_stock_fundamentals,
    _load_stock_quotes,
    _load_return_comparison_em,
    _load_sales_service_fee_rate,
    _nav_history,
    _normalize_code,
    _parse_asset_allocation_report,
    _parse_bond_type_structure,
    _parse_fof_fund_holdings,
    _parse_target_fund_holdings,
    _parse_holder_structure,
    _parse_fund_manager_index,
    _parse_holding_period_bounds,
    _parse_purchase_fee_table,
    _parse_manager_profile,
    _parse_redeem_fee_table,
    _pick,
    _report_period,
    _quarter_end_from_period,
    _quarter_report_catalog,
    _year_to_date_return,
    search_funds,
)


class FundLookupTests(unittest.TestCase):
    @patch("fund_lookup._fund_search_catalog_for")
    def test_search_funds_supports_code_chinese_and_pinyin(
        self,
        mocked_catalog,
    ) -> None:
        mocked_catalog.return_value = (
            {
                "code": "000001",
                "name": "华夏成长混合",
                "fund_type": "混合型-灵活",
                "code_search": "000001",
                "name_search": "华夏成长混合",
                "pinyin_short": "HXCZHH",
                "pinyin_full": "HUAXIACHENGZHANGHUNHE",
            },
            {
                "code": "000011",
                "name": "华夏大盘精选混合A",
                "fund_type": "混合型-灵活",
                "code_search": "000011",
                "name_search": "华夏大盘精选混合A",
                "pinyin_short": "HXDPJXHHA",
                "pinyin_full": "HUAXIADAPANJINGXUANHUNHEA",
            },
        )

        self.assertEqual(search_funds("000001")["基金"][0]["代码"], "000001")
        self.assertEqual(search_funds("华夏成长")["基金"][0]["代码"], "000001")
        self.assertEqual(search_funds("HXCZ")["基金"][0]["代码"], "000001")

    def test_normalize_code_preserves_leading_zero(self) -> None:
        self.assertEqual(_normalize_code("000001"), "000001")

    def test_normalize_code_rejects_invalid_value(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_code("12345")

    def test_pick_skips_empty_values(self) -> None:
        self.assertEqual(_pick(None, "", "--", 1.25), 1.25)

    def test_clean_serializes_date(self) -> None:
        self.assertEqual(_clean(date(2026, 7, 25)), "2026-07-25")

    @patch("fund_lookup.requests.get")
    def test_load_return_comparison_returns_fund_series(self, mocked_get) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "Data": [
                {
                    "name": "测试基金",
                    "data": [
                        [1735689600000, 0.0],
                        [1767225600000, 12.0],
                    ],
                },
                {
                    "name": "同类平均",
                    "data": [
                        [1735689600000, 0.0],
                        [1767225600000, 10.0],
                    ],
                },
                {"name": "沪深300", "data": []},
            ]
        }
        mocked_get.return_value = response

        frame = _load_return_comparison_em("000001", "1年")

        self.assertEqual(list(frame.columns), ["日期", "累计收益率"])
        self.assertEqual(frame.iloc[-1]["累计收益率"], 12.0)

    def test_fund_age_uses_complete_months(self) -> None:
        self.assertEqual(
            _fund_age("2019-12-10", today=date(2026, 7, 25)),
            "6年7个月",
        )

    def test_parse_fund_manager_index(self) -> None:
        html = """
        <div class="jl_intro">
          <a href="//fund.eastmoney.com/manager/30040527.html"><img src="//img.test/a.jpg"></a>
          <div class="text">
            <p><strong>姓名：</strong><a>郑晓辉</a></p>
            <p><strong>上任日期：</strong>2024-12-26</p>
            <p>郑晓辉先生，博士，现任基金经理。</p>
          </div>
        </div>
        """

        managers = _parse_fund_manager_index(html)

        self.assertEqual(len(managers), 1)
        self.assertEqual(managers[0]["经理ID"], "30040527")
        self.assertEqual(managers[0]["姓名"], "郑晓辉")
        self.assertEqual(managers[0]["上任日期"], "2024-12-26")
        self.assertEqual(managers[0]["照片"], "https://img.test/a.jpg")

    def test_parse_manager_profile_includes_experience_and_fund_tenure(self) -> None:
        html = """
        <div class="jlinfo">
          <div class="right ms"><p><span>基金经理简介：</span>测试简介</p></div>
          <div class="right jd">
            <span>累计任职时间：</span>14年又236天<br>
            <span>任职起始日期：</span>2006-11-29<br>
            <span>现任基金公司：</span><a href="//fund.eastmoney.com/company/80000222.html">华夏基金管理有限公司</a>
            <div class="gmleft gmlefts"><span class="redText">116.55</span></div>
          </div>
        </div>
        <h3 id="name_1">郑晓辉</h3>
        <table><tbody><tr>
          <td><a href="//fund.eastmoney.com/000001.html">000001</a></td>
          <td>华夏成长混合</td><td>相关链接</td><td>混合型</td><td>39.38</td>
          <td>2024-12-26 ~ 至今</td><td>1年又219天</td><td>51.74%</td>
        </tr></tbody></table>
        """

        profile = _parse_manager_profile(html, "000001")

        self.assertEqual(profile["从业年限"], "14年又236天")
        self.assertEqual(profile["本基金任期"], "1年又219天")
        self.assertEqual(profile["本基金任职回报"], "51.74%")
        self.assertEqual(profile["公司ID"], "80000222")
        self.assertEqual(profile["现任基金资产总规模"], 116.55)

    def test_extract_fund_company_matches_company_overview(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "基金公司": "华夏基金管理有限公司",
                    "成立时间": date(1998, 4, 9),
                    "全部管理规模": 19218.42,
                    "全部基金数": 984,
                    "全部经理数": 134,
                    "更新日期": "07-21",
                }
            ]
        )

        company = _extract_fund_company(frame, "华夏基金")

        self.assertEqual(company["成立日期"], "1998-04-09")
        self.assertEqual(company["管理规模"], 19218.42)
        self.assertEqual(company["基金数量"], 984)
        self.assertEqual(company["基金经理数量"], 134)

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

    def test_load_sales_service_fee_rate_including_zero(self) -> None:
        c_soup = BeautifulSoup(
            "<table><tr><td>销售服务费率</td><td>0.60%</td></tr></table>",
            "html.parser",
        )
        a_soup = BeautifulSoup(
            "<table><tr><td>销售服务费率</td><td>0.00%</td></tr></table>",
            "html.parser",
        )

        self.assertEqual(_load_sales_service_fee_rate(c_soup, []), 0.6)
        self.assertEqual(_load_sales_service_fee_rate(a_soup, []), 0.0)

    def test_parse_redeem_fee_table_by_holding_period(self) -> None:
        frame = pd.DataFrame(
            [
                {"适用期限": "小于7天", "赎回费率": "1.50%"},
                {"适用期限": "大于等于7天，小于等于29天", "赎回费率": "0.75%"},
                {"适用期限": "大于等于730天", "赎回费率": "0.00%"},
            ]
        )

        fees = _parse_redeem_fee_table(frame)

        self.assertTrue(fees["可用"])
        self.assertEqual(len(fees["明细"]), 3)
        self.assertEqual(fees["明细"][0]["适用条件"], "小于7天")
        self.assertEqual(fees["明细"][0]["赎回费率"], "1.50%")
        self.assertEqual(fees["明细"][0]["起始天数"], 1)
        self.assertEqual(fees["明细"][0]["结束天数"], 6)
        self.assertEqual(fees["明细"][1]["起始天数"], 7)
        self.assertEqual(fees["明细"][1]["结束天数"], 29)
        self.assertEqual(fees["明细"][2]["赎回费率"], "0.00%")
        self.assertEqual(fees["明细"][2]["起始天数"], 730)
        self.assertIsNone(fees["明细"][2]["结束天数"])

    def test_parse_holding_period_bounds_supports_symbolic_range(self) -> None:
        self.assertEqual(_parse_holding_period_bounds("7天≤N＜30天"), (7, 29))
        self.assertEqual(_parse_holding_period_bounds("30天以上（含30天）"), (30, None))

    def test_compare_share_class_costs_includes_redeem_fee_tiers(self) -> None:
        a_redeem = _parse_redeem_fee_table(
            pd.DataFrame(
                [
                    {"适用期限": "小于7天", "赎回费率": "1.50%"},
                    {
                        "适用期限": "大于等于7天，小于30天",
                        "赎回费率": "0.50%",
                    },
                    {"适用期限": "大于等于30天", "赎回费率": "0.00%"},
                ]
            )
        )
        c_redeem = _parse_redeem_fee_table(
            pd.DataFrame(
                [
                    {"适用期限": "小于7天", "赎回费率": "1.50%"},
                    {
                        "适用期限": "大于等于7天，小于30天",
                        "赎回费率": "0.75%",
                    },
                    {"适用期限": "大于等于30天", "赎回费率": "0.00%"},
                ]
            )
        )

        periods = _compare_share_class_costs(
            a_purchase_rate=0.10,
            c_purchase_rate=0.0,
            a_sales_rate=0.0,
            c_sales_rate=0.40,
            a_redeem_fee=a_redeem,
            c_redeem_fee=c_redeem,
        )

        self.assertEqual(
            [
                (item["起始天数"], item["结束天数"], item["更省份额"])
                for item in periods
            ],
            [
                (1, 6, "C"),
                (7, 29, "A"),
                (30, 90, "C"),
                (91, 91, "相同"),
                (92, None, "A"),
            ],
        )
        self.assertEqual(periods[1]["A赎回费率"], 0.5)
        self.assertEqual(periods[1]["C赎回费率"], 0.75)

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

    @patch("fund_lookup.requests.get")
    def test_load_stock_quotes_parses_batch_response(self, mocked_get) -> None:
        response = Mock()
        response.content = (
            'var hq_str_sh600519="贵州茅台,1300,1290,1297.41,0,0,0,0,0,0,'
            '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,'
            '2026-07-24,15:00:00";'
        ).encode("gbk")
        response.raise_for_status.return_value = None
        mocked_get.return_value = response

        quotes = _load_stock_quotes(["600519"])

        self.assertEqual(quotes["600519"]["最新价"], 1297.41)
        self.assertEqual(quotes["600519"]["行情日期"], "2026-07-24")

    @patch("fund_lookup.ak.stock_profile_cninfo")
    @patch("fund_lookup.ak.stock_individual_info_em")
    @patch("fund_lookup.ak.stock_history_dividend_detail")
    @patch("fund_lookup.ak.stock_zh_valuation_comparison_em")
    def test_load_stock_fundamentals_calculates_roe_and_dividend_yield(
        self,
        mocked_valuation,
        mocked_dividend,
        mocked_stock_info,
        mocked_profile,
    ) -> None:
        mocked_valuation.return_value = pd.DataFrame(
            [
                {
                    "代码": "行业平均",
                    "市盈率-TTM": 2.9,
                    "市净率-MRQ": 2.5,
                },
                {
                    "代码": "600519",
                    "市盈率-TTM": 20.0,
                    "市净率-MRQ": 2.0,
                }
            ]
        )
        mocked_dividend.return_value = pd.DataFrame(
            [
                {"除权除息日": "2026-06-20", "派息": 5.0},
                {"除权除息日": "2025-06-20", "派息": 8.0},
            ]
        )
        mocked_profile.return_value = pd.DataFrame(
            [{"A股代码": "600519", "所属行业": "酒、饮料和精制茶制造业"}]
        )

        metrics = _load_stock_fundamentals(
            "600519",
            {"最新价": 10.0, "行情日期": "2026-07-24"},
        )

        self.assertEqual(metrics["PE"], 20.0)
        self.assertEqual(metrics["PB"], 2.0)
        self.assertEqual(metrics["ROE"], 10.0)
        self.assertEqual(metrics["股息率"], 5.0)
        self.assertEqual(metrics["所属行业"], "酒、饮料和精制茶制造业")
        mocked_stock_info.assert_not_called()

    @patch("fund_lookup.ak.stock_profile_cninfo")
    @patch("fund_lookup.ak.stock_individual_info_em")
    @patch("fund_lookup.ak.stock_history_dividend_detail")
    @patch("fund_lookup.requests.get")
    @patch("fund_lookup.ak.stock_zh_valuation_comparison_em")
    def test_stock_fundamentals_falls_back_to_raw_valuation_response(
        self,
        mocked_valuation,
        mocked_get,
        mocked_dividend,
        mocked_stock_info,
        mocked_profile,
    ) -> None:
        mocked_valuation.side_effect = KeyError("missing comparison column")
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "result": {
                "data": [
                    {
                        "CORRE_SECURITY_CODE": "000001",
                        "PE_TTM": 5.0,
                        "PB_MRQ": 0.5,
                    }
                ]
            }
        }
        mocked_get.return_value = response
        mocked_dividend.return_value = pd.DataFrame()
        mocked_profile.side_effect = RuntimeError("cninfo unavailable")
        mocked_stock_info.return_value = pd.DataFrame(
            [{"item": "行业", "value": "银行"}]
        )

        metrics = _load_stock_fundamentals(
            "000001",
            {"最新价": 10.0, "行情日期": "2026-07-24"},
        )

        self.assertEqual(metrics["PE"], 5.0)
        self.assertEqual(metrics["PB"], 0.5)
        self.assertEqual(metrics["ROE"], 10.0)
        self.assertEqual(metrics["所属行业"], "银行")

    @patch("fund_lookup._load_stock_fundamentals")
    @patch("fund_lookup._load_stock_quotes")
    def test_enrich_stock_holdings_builds_weighted_summary(
        self,
        mocked_quotes,
        mocked_fundamentals,
    ) -> None:
        mocked_quotes.return_value = {}
        metrics = {
            "000001": {
                "PE": 10.0,
                "PB": 1.0,
                "ROE": 10.0,
                "股息率": 4.0,
                "最新价": 12.0,
                "行情日期": "2026-07-24",
                "_估值错误": None,
                "_分红错误": None,
            },
            "000002": {
                "PE": 20.0,
                "PB": 2.0,
                "ROE": 10.0,
                "股息率": 2.0,
                "最新价": 8.0,
                "行情日期": "2026-07-24",
                "_估值错误": None,
                "_分红错误": None,
            },
        }
        mocked_fundamentals.side_effect = (
            lambda code, quote: metrics[code]
        )

        rows, summary = _enrich_stock_holdings(
            [
                {"股票代码": "000001", "占净值比例": 6.0},
                {"股票代码": "000002", "占净值比例": 4.0},
            ],
            [],
        )

        self.assertEqual(rows[0]["PE"], 10.0)
        self.assertEqual(summary["覆盖数量"], 2)
        self.assertEqual(summary["组合指标"]["PE"], 12.5)
        self.assertEqual(summary["组合指标"]["股息率"], 3.2)

    def test_holdings_for_period_selects_requested_quarter(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "序号": 1,
                    "股票代码": "000001",
                    "占净值比例": 3.0,
                    "季度": "2025年1季度股票投资明细",
                },
                {
                    "序号": 2,
                    "股票代码": "000002",
                    "占净值比例": 5.0,
                    "季度": "2025年2季度股票投资明细",
                },
            ]
        )

        holdings, period = _holdings_for_period(
            frame,
            2025,
            2,
            limit=20,
        )

        self.assertEqual(period, "2025年2季度股票投资明细")
        self.assertEqual([row["股票代码"] for row in holdings], ["000002"])

    def test_quarter_report_catalog_builds_pdf_links(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "公告标题": "测试基金2025年第2季度报告",
                    "公告日期": date(2025, 7, 21),
                    "报告ID": "AN202507210001",
                },
                {
                    "公告标题": "测试基金2025年中期报告",
                    "公告日期": date(2025, 8, 30),
                    "报告ID": "AN202508300001",
                },
                {
                    "公告标题": "测试基金2025年第1季度报告",
                    "公告日期": date(2025, 4, 21),
                    "报告ID": "AN202504210001",
                },
            ]
        )

        reports = _quarter_report_catalog(frame)

        self.assertEqual([report["key"] for report in reports], ["2025Q2", "2025Q1"])
        self.assertEqual(reports[0]["报告期"], "2025年第2季度")
        self.assertEqual(
            reports[0]["链接"],
            "https://pdf.dfcfw.com/pdf/H2_AN202507210001_1.pdf",
        )

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

    def test_parse_asset_allocation_allows_omitted_fund_investment(self) -> None:
        report_text = """
        5.1 报告期末基金资产组合情况
        1 权益投资 46,823,250,741.18 99.45
        2 固定收益投资 - -
        7 其他资产 19,778,958.11 0.04
        8 合计 47,083,706,213.55 100.00
        注：上表中的权益投资含可退替代款估值增值。
        5.2期末投资目标基金明细
        """

        allocation = _parse_asset_allocation_report(report_text)

        self.assertEqual(allocation[0], {"资产类别": "股票", "占比": 99.45})
        self.assertEqual(allocation[2], {"资产类别": "基金", "占比": 0.0})
        self.assertEqual(allocation[3], {"资产类别": "其他", "占比": 0.55})

    def test_parse_asset_allocation_skips_table_of_contents(self) -> None:
        report_text = """
        目录
        5.1 报告期末基金资产组合情况 ............................ 9
        5.2 报告期末按行业分类的股票投资组合 ............ 9
        正文
        5.1 报告期末基金资产组合情况
        1 权益投资 - -
        2 基金投资 - -
        3 固定收益投资 1,617,847,474.20 99.85
        7 银行存款和结算备付金合计 2,364,134.23 0.15
        9 合计 1,620,219,708.07 100.00
        5.2 报告期末按行业分类的股票投资组合
        """

        allocation = _parse_asset_allocation_report(report_text)

        self.assertEqual(allocation[1], {"资产类别": "债券", "占比": 99.85})
        self.assertEqual(allocation[3], {"资产类别": "其他", "占比": 0.15})

    def test_parse_target_fund_holding(self) -> None:
        report_text = """
        2.1.1目标基金基本情况
        基金名称             易方达创业板交易型开放式指数证券投资基金
        基金主代码            159915
        基金运作方式           交易型开放式（ETF）
        2.1.2目标基金产品说明

        5.2期末投资目标基金明细
        序号 基金名称 基金类型 运作方式 管理人 公允价值（元） 占基金资产净值比例（%）
        1 易方达创业板交易型开放式指数证券投资基金
          股票型 交易型开放式（ETF） 易方达基金管理有限公司
          9,996,761,826.23 93.87
        5.3 报告期末按行业分类的股票投资组合
        """

        holdings = _parse_target_fund_holdings(report_text)

        self.assertEqual(
            holdings,
            [
                {
                    "持仓排名": 1,
                    "持仓类型": "目标ETF",
                    "基金代码": "159915",
                    "基金名称": "易方达创业板交易型开放式指数证券投资基金",
                    "运作方式": "交易型开放式（ETF）",
                    "占净值比例": 93.87,
                    "持仓市值": 999676.18,
                }
            ],
        )

    def test_parse_fof_fund_holdings(self) -> None:
        report_text = """
        §6 基金中基金
        6.1 报告期末按公允价值占基金资产净值比例大小排序的前十名基金投资明细
        序号 基金代码 基金名称 运作方式 持有份额 公允价值 占基金资产净值比例 是否关联方
        1 020009 国泰金鹏蓝筹混合 契约型开放式 2,985,861.52 6,568,895.34 7.12 否
        2 014642 摩根新兴动力混合C 契约型开放式 450,824.00 6,008,537.19 6.51 否
        3 024170 信澳新能源产业股票C 契约型开放式
          598,281.14 5,617,859.90 6.09 否
        6.2 当期交易及持有基金产生的费用
        """

        holdings = _parse_fof_fund_holdings(report_text)

        self.assertEqual(
            [(row["基金代码"], row["占净值比例"]) for row in holdings],
            [("020009", 7.12), ("014642", 6.51), ("024170", 6.09)],
        )
        self.assertTrue(all(row["持仓类型"] == "FOF" for row in holdings))

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

    def test_year_to_date_return_uses_previous_year_end(self) -> None:
        result = _year_to_date_return(
            [
                {"日期": "2025-12-31", "累计收益率": 10.0},
                {"日期": "2026-01-05", "累计收益率": 11.0},
                {"日期": "2026-07-24", "累计收益率": 21.0},
            ]
        )

        self.assertEqual(result, 10.0)

    def test_year_to_date_return_falls_back_to_inception(self) -> None:
        result = _year_to_date_return(
            [
                {"日期": "2026-03-02", "累计收益率": 0.0},
                {"日期": "2026-07-24", "累计收益率": 4.25},
            ]
        )

        self.assertEqual(result, 4.25)


if __name__ == "__main__":
    unittest.main()
