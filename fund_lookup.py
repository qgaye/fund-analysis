#!/usr/bin/env python3
"""通过 AKShare 查询单只中国公募基金的常用信息。"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Callable

import akshare as ak
import pandas as pd
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


class FundLookupError(RuntimeError):
    """基金查询失败。"""


def _clean(value: Any) -> Any:
    """把 pandas/numpy 值转换成可 JSON 序列化的 Python 值。"""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def _normalize_code(fund_code: str) -> str:
    code = str(fund_code).strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("基金代码必须是 6 位数字，例如 000001。")
    return code


def _safe_call(
    label: str,
    func: Callable[..., pd.DataFrame],
    warnings: list[str],
    **kwargs: Any,
) -> pd.DataFrame:
    try:
        result = func(**kwargs)
        if result is None:
            return pd.DataFrame()
        return result
    except Exception as exc:  # AKShare 上游站点异常种类不固定
        warnings.append(f"{label}获取失败：{exc}")
        return pd.DataFrame()


def _item_value_map(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or not {"item", "value"}.issubset(frame.columns):
        return {}
    return {
        str(row["item"]).strip(): _clean(row["value"])
        for _, row in frame.iterrows()
    }


def _first_row(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    return {str(key): _clean(value) for key, value in frame.iloc[0].items()}


def _pick(*values: Any) -> Any:
    for value in values:
        cleaned = _clean(value)
        if cleaned not in (None, "", "--", "---"):
            return cleaned
    return None


def _extract_found_date(overview: dict[str, Any], xq: dict[str, Any]) -> Any:
    direct = _pick(xq.get("成立时间"), overview.get("成立日期"))
    if direct:
        return direct
    combined = _clean(overview.get("成立日期/规模"))
    if not combined:
        return None
    return re.split(r"\s*/\s*", str(combined), maxsplit=1)[0].strip()


def _fund_age(found_date: Any, today: date | None = None) -> str | None:
    """把成立日期转换成“X年Y个月”的基金成立时长。"""
    parsed = pd.to_datetime(found_date, errors="coerce")
    if pd.isna(parsed):
        return None
    start = parsed.date()
    end = today or date.today()
    if start > end:
        return None
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    years, remaining_months = divmod(max(months, 0), 12)
    if years and remaining_months:
        return f"{years}年{remaining_months}个月"
    if years:
        return f"{years}年"
    return f"{remaining_months}个月"


def _extract_scale_details(
    overview: dict[str, Any], xq: dict[str, Any]
) -> dict[str, Any]:
    """整理成立份额、最新净资产规模、份额规模和各自截止日。"""
    founded = _clean(overview.get("成立日期/规模"))
    founded_scale = None
    if founded:
        parts = re.split(r"\s*/\s*", str(founded), maxsplit=1)
        if len(parts) == 2:
            founded_scale = parts[1].strip()

    net_assets_raw = _pick(
        overview.get("净资产规模"), xq.get("最新规模")
    )
    shares_raw = _clean(overview.get("份额规模"))

    def split_value_and_date(value: Any) -> tuple[Any, str | None]:
        if value in (None, ""):
            return None, None
        value_text = str(value).strip()
        date_match = re.search(
            r"截止至[：:]\s*(\d{4})年(\d{2})月(\d{2})日", value_text
        )
        cutoff = (
            "-".join(date_match.groups()) if date_match else None
        )
        clean_value = re.split(r"[（(]\s*截止至", value_text, maxsplit=1)[0]
        return clean_value.strip(), cutoff

    net_assets, net_assets_date = split_value_and_date(net_assets_raw)
    shares, shares_date = split_value_and_date(shares_raw)
    return {
        "最新净资产": net_assets,
        "净资产截止日": net_assets_date,
        "最新份额": shares,
        "份额截止日": shares_date,
        "成立份额": founded_scale,
    }


def _parse_holder_structure(page_text: str) -> dict[str, Any]:
    """解析天天基金单只基金最新持有人结构。"""
    row_match = re.search(
        r"<tbody>\s*<tr>\s*"
        r"<td>(?P<date>\d{4}-\d{2}-\d{2})</td>\s*"
        r"<td[^>]*>(?P<institution>[\d.]+)%</td>\s*"
        r"<td[^>]*>(?P<individual>[\d.]+)%</td>\s*"
        r"<td[^>]*>(?P<internal>[\d.]+)%</td>\s*"
        r"<td[^>]*>(?P<shares>[\d.]+)</td>",
        page_text,
        flags=re.DOTALL,
    )
    if not row_match:
        return {}
    return {
        "报告期": row_match.group("date"),
        "机构持有比例": float(row_match.group("institution")),
        "个人持有比例": float(row_match.group("individual")),
        "内部持有比例": float(row_match.group("internal")),
        "总份额": float(row_match.group("shares")),
        "总份额单位": "亿份",
        "说明": "内部持有比例为补充披露，不与机构、个人比例相加。",
    }


def _load_holder_structure(
    code: str, warnings: list[str]
) -> dict[str, Any]:
    try:
        response = requests.get(
            "https://fundf10.eastmoney.com/FundArchivesDatas.aspx",
            params={"type": "cyrjg", "code": code},
            headers={
                "Referer": f"https://fundf10.eastmoney.com/cyrjg_{code}.html",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=20,
        )
        response.raise_for_status()
    except Exception as exc:
        warnings.append(f"持有人结构获取失败：{exc}")
        return {}

    structure = _parse_holder_structure(response.text)
    if not structure:
        warnings.append("持有人结构获取失败：未找到最新披露数据。")
    return structure


def _parse_purchase_fee_table(
    frame: pd.DataFrame, title: str
) -> dict[str, Any]:
    """把申购费率表整理成统一的金额分档结构。"""
    if frame.empty:
        return {}
    details: list[dict[str, Any]] = []
    for raw_row in frame.to_dict(orient="records"):
        row = {str(key): _clean(value) for key, value in raw_row.items()}
        condition = _pick(
            row.get("适用金额"),
            row.get("适用期限"),
            row.get("条件或名称"),
        )
        combined = _pick(
            row.get("原费率|天天基金优惠费率"),
            row.get("原费率|天天基金优惠费率 银行卡购买|活期宝购买"),
        )
        original = _pick(row.get("原费率"), row.get("费率"), row.get("申购费率"))
        discount = _pick(
            row.get("天天基金优惠费率"),
            row.get("天天基金优惠费率-银行卡购买"),
        )
        if combined:
            fee_parts = [
                part.strip()
                for part in str(combined).split("|")
                if part.strip()
            ]
            original = fee_parts[0] if fee_parts else original
            discount = fee_parts[1] if len(fee_parts) > 1 else discount
        if not any((condition, original, discount)):
            continue
        details.append(
            {
                "适用条件": condition,
                "原费率": original,
                "天天基金优惠费率": discount,
            }
        )
    if not details:
        return {}
    return {
        "可用": True,
        "收费方式": "前端收费" if "前端" in title else "申购费率",
        "明细": details,
        "说明": (
            "优惠费率仅指天天基金销售渠道，实际费率以购买平台确认结果为准。"
        ),
    }


def _load_purchase_fee(code: str, warnings: list[str]) -> dict[str, Any]:
    try:
        response = requests.get(
            f"https://fundf10.eastmoney.com/jjfl_{code}.html",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, features="html.parser")
        candidates: list[tuple[str, Any]] = []
        for heading in soup.find_all("h4", class_="t"):
            title = re.sub(
                r"\s+", " ", heading.get_text(" ", strip=True)
            ).strip()
            if title == "申购费率" or title.startswith("申购费率（前端）"):
                candidates.append((title, heading.find_next("table")))
        if not candidates or candidates[0][1] is None:
            return {}
        title, table = candidates[0]
        fee_frame = pd.read_html(io.StringIO(str(table)))[0]
    except Exception as exc:
        warnings.append(f"买入费率获取失败：{exc}")
        return {}

    fees = _parse_purchase_fee_table(fee_frame, title)
    if not fees:
        warnings.append("买入费率获取失败：未找到可用申购费率表。")
    return fees


@lru_cache(maxsize=1)
def _fund_name_directory() -> pd.DataFrame:
    """全量基金名录（代码 / 简称 / 类型），用于 A/C 份额配对。"""
    frame = ak.fund_name_em()
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["基金代码", "基金简称", "基金类型"])
    frame = frame.copy()
    frame["基金代码"] = (
        frame["基金代码"].astype("string").str.extract(r"(\d{6})", expand=False)
    )
    return frame.dropna(subset=["基金代码"])


# A / C 后缀识别：匹配名称结尾的份额类别标记，如 “……混合A”“……债券C”。
_SHARE_CLASS_PATTERN = re.compile(r"^(?P<base>.+?)([ 　\-]*)(?P<cls>[AC])$")


def _split_share_class(name: str) -> tuple[str, str] | None:
    """把基金简称拆成 (基名, 份额类别)。无法识别则返回 None。"""
    cleaned = re.sub(r"\s+", "", str(name or ""))
    if not cleaned:
        return None
    match = _SHARE_CLASS_PATTERN.match(cleaned)
    if not match:
        return None
    return match.group("base"), match.group("cls")


def _find_share_class_sibling(
    code: str, fund_name: str, warnings: list[str]
) -> dict[str, Any] | None:
    """根据基金简称的 A/C 后缀，查找配对的另一类份额。"""
    parsed = _split_share_class(fund_name)
    if not parsed:
        return None
    base_name, current_cls = parsed
    sibling_cls = "C" if current_cls == "A" else "A"
    try:
        directory = _fund_name_directory()
    except Exception as exc:  # AKShare 名录接口异常
        warnings.append(f"A/C 份额配对失败：{exc}")
        return None

    for _, row in directory.iterrows():
        candidate_code = str(row["基金代码"])
        if candidate_code == code:
            continue
        candidate = _split_share_class(row["基金简称"])
        if not candidate:
            continue
        cand_base, cand_cls = candidate
        if cand_base == base_name and cand_cls == sibling_cls:
            return {
                "代码": candidate_code,
                "名称": _clean(row["基金简称"]),
                "类别": sibling_cls,
            }
    return None


def _load_sales_service_fee_rate(code: str, warnings: list[str]) -> float | None:
    """从东财费率页“运作费用”表提取年销售服务费率（百分比数值）。"""
    try:
        response = requests.get(
            f"https://fundf10.eastmoney.com/jjfl_{code}.html",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
    except Exception as exc:
        warnings.append(f"销售服务费获取失败：{exc}")
        return None

    # 原始 HTML 里“销售服务费率”与数值间夹着表格标签，需先转成纯文本再匹配。
    text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    match = re.search(r"销售服务费率[^\d%]*([\d.]+)\s*%", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _first_percent(*values: Any) -> float | None:
    """从费率文本里取第一个百分比数值，如 “0.15%” -> 0.15。"""
    for value in values:
        match = re.search(r"([\d.]+)\s*%", str(value or ""))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _build_share_class_advice(
    code: str,
    fund_name: str,
    current_purchase_fee: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any] | None:
    """构建 A/C 份额选择建议：定位配对份额并测算临界持有天数。"""
    parsed = _split_share_class(fund_name)
    if not parsed:
        return None
    current_cls = parsed[1]
    sibling = _find_share_class_sibling(code, fund_name, warnings)
    if not sibling:
        return None

    sibling_code = sibling["代码"]
    sibling_purchase_fee = _load_purchase_fee(sibling_code, warnings)

    # 归类出 A 类与 C 类各自的代码、名称、申购费明细。
    classes = {
        current_cls: {
            "代码": code,
            "名称": fund_name,
            "申购费": current_purchase_fee,
        },
        sibling["类别"]: {
            "代码": sibling_code,
            "名称": sibling["名称"],
            "申购费": sibling_purchase_fee,
        },
    }
    a_info = classes.get("A")
    c_info = classes.get("C")
    if not a_info or not c_info:
        return None

    # A 类首档申购费率（优先渠道优惠费率）。
    a_rows = (a_info["申购费"] or {}).get("明细") or []
    a_purchase_rate = None
    if a_rows:
        a_purchase_rate = _first_percent(
            a_rows[0].get("天天基金优惠费率"), a_rows[0].get("原费率")
        )
    # C 类年销售服务费率。
    c_sales_rate = _load_sales_service_fee_rate(c_info["代码"], warnings)

    threshold_days = None
    if a_purchase_rate and c_sales_rate and c_sales_rate > 0:
        # 临界天数：A 类一次性申购费 == C 类持有期销售服务费累计。
        threshold_days = round(a_purchase_rate / (c_sales_rate / 365))

    if threshold_days:
        summary = (
            f"预计持有超过约 {threshold_days} 天时，A 类（{a_info['名称']}）"
            f"综合成本更低；短于该天数则 C 类（{c_info['名称']}）更划算。"
        )
    else:
        summary = (
            f"已找到配对份额：A 类 {a_info['名称']}（{a_info['代码']}）、"
            f"C 类 {c_info['名称']}（{c_info['代码']}）。"
            "因费率数据不足，暂无法测算精确临界天数——"
            "通常长期持有选 A 类、短期持有选 C 类。"
        )

    return {
        "可用": True,
        "当前份额": current_cls,
        "A类": {
            "代码": a_info["代码"],
            "名称": a_info["名称"],
            "申购费率": a_purchase_rate,
        },
        "C类": {
            "代码": c_info["代码"],
            "名称": c_info["名称"],
            "年销售服务费率": c_sales_rate,
        },
        "临界持有天数": threshold_days,
        "建议": summary,
        "说明": (
            "临界天数按 A 类优惠申购费率与 C 类年销售服务费率估算，"
            "未计入赎回费与持有期收益差异，实际以购买平台费率为准。"
        ),
    }


def _find_code_row(frame: pd.DataFrame, code: str) -> dict[str, Any]:
    if frame.empty or "基金代码" not in frame.columns:
        return {}
    codes = (
        frame["基金代码"]
        .astype("string")
        .str.extract(r"(\d{6})", expand=False)
    )
    matched = frame.loc[codes == code]
    return _first_row(matched)


def _load_rank_row(code: str, warnings: list[str]) -> tuple[dict[str, Any], str]:
    sources: list[tuple[str, Callable[..., pd.DataFrame], dict[str, Any], str]] = [
        (
            "开放式基金排行",
            ak.fund_open_fund_rank_em,
            {"symbol": "全部"},
            "AKShare.fund_open_fund_rank_em",
        ),
        (
            "场内基金排行",
            ak.fund_exchange_rank_em,
            {},
            "AKShare.fund_exchange_rank_em",
        ),
        (
            "货币基金排行",
            ak.fund_money_rank_em,
            {},
            "AKShare.fund_money_rank_em",
        ),
    ]
    for label, func, kwargs, source in sources:
        frame = _safe_call(label, func, warnings, **kwargs)
        row = _find_code_row(frame, code)
        if row:
            return row, source
    return {}, ""


def _latest_holdings(
    frame: pd.DataFrame, limit: int | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    if frame.empty:
        return [], None

    selected = frame.copy()
    period = None
    if "季度" in selected.columns:
        periods = selected["季度"].astype("string")
        parsed = periods.str.extract(r"(?P<year>\d{4})年(?P<quarter>[1-4])季度")
        valid = parsed.dropna()
        if not valid.empty:
            order = valid["year"].astype(int) * 10 + valid["quarter"].astype(int)
            latest_index = order.idxmax()
            period = str(periods.loc[latest_index])
            selected = selected.loc[periods == period]
        elif periods.notna().any():
            period = str(periods.dropna().iloc[0])

    if "占净值比例" in selected.columns:
        selected = selected.sort_values("占净值比例", ascending=False)
    elif "序号" in selected.columns:
        selected = selected.sort_values("序号")
    if limit is not None:
        selected = selected.head(limit)

    selected = selected.reset_index(drop=True)
    if "序号" in selected.columns:
        selected = selected.drop(columns=["序号"])
    selected.insert(0, "持仓排名", range(1, len(selected) + 1))

    records = [
        {str(key): _clean(value) for key, value in row.items()}
        for row in selected.to_dict(orient="records")
    ]
    return records, period


def _load_bond_holdings(code: str, warnings: list[str]) -> pd.DataFrame:
    """按年度回溯，获取基金最新可用的债券持仓披露。"""
    errors: list[str] = []
    current_year = datetime.now().year
    for year in range(current_year, current_year - 5, -1):
        try:
            frame = ak.fund_portfolio_bond_hold_em(
                symbol=code, date=str(year)
            )
        except Exception as exc:  # AKShare 上游站点异常种类不固定
            errors.append(f"{year} 年：{exc}")
            continue
        if frame is not None and not frame.empty:
            return frame

    if errors:
        warnings.append(f"债券持仓获取失败：{errors[-1]}")
    return pd.DataFrame()


def _latest_industry_allocation(
    frame: pd.DataFrame,
) -> tuple[list[dict[str, Any]], str | None]:
    """提取最新报告期的股票行业配置，并剔除零占比项目。"""
    required = {"行业类别", "占净值比例"}
    if frame.empty or not required.issubset(frame.columns):
        return [], None

    selected = frame.copy()
    period = None
    if "截止时间" in selected.columns:
        dates = pd.to_datetime(selected["截止时间"], errors="coerce")
        if dates.notna().any():
            latest_date = dates.max()
            period = latest_date.date().isoformat()
            selected = selected.loc[dates == latest_date]

    selected["占净值比例"] = pd.to_numeric(
        selected["占净值比例"], errors="coerce"
    )
    selected = (
        selected.dropna(subset=["行业类别", "占净值比例"])
        .loc[lambda value: value["占净值比例"] > 0]
        .sort_values("占净值比例", ascending=False)
        .reset_index(drop=True)
    )
    if "序号" in selected.columns:
        selected = selected.drop(columns=["序号"])
    selected.insert(0, "配置排名", range(1, len(selected) + 1))

    records = [
        {str(key): _clean(value) for key, value in row.items()}
        for row in selected.to_dict(orient="records")
    ]
    return records, period


def _load_industry_allocation(
    code: str, warnings: list[str]
) -> pd.DataFrame:
    """按年度回溯，获取基金最新可用的股票行业配置。"""
    errors: list[str] = []
    current_year = datetime.now().year
    for year in range(current_year, current_year - 5, -1):
        try:
            frame = ak.fund_portfolio_industry_allocation_em(
                symbol=code, date=str(year)
            )
        except Exception as exc:  # AKShare 上游空数据有时会触发解析异常
            errors.append(f"{year} 年：{exc}")
            continue
        if frame is not None and not frame.empty:
            return frame

    if errors:
        warnings.append(f"股票行业配置获取失败：{errors[-1]}")
    return pd.DataFrame()


def _extract_related_etf_code(page_html: str) -> str | None:
    """从东方财富联接基金详情页提取“查看相关ETF”的目标代码。"""
    matched = re.search(
        r'href=["\']https?://fund\.eastmoney\.com/(\d{6})\.html["\']'
        r"[^>]*>\s*查看相关ETF",
        page_html,
        flags=re.IGNORECASE,
    )
    return matched.group(1) if matched else None


def _load_related_etf_code(code: str, warnings: list[str]) -> str | None:
    try:
        response = requests.get(
            f"https://fund.eastmoney.com/{code}.html",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
    except Exception as exc:
        warnings.append(f"目标 ETF 识别失败：{exc}")
        return None

    target_code = _extract_related_etf_code(response.text)
    if not target_code:
        warnings.append("未在基金详情页识别到目标 ETF。")
    return target_code


def _parse_asset_allocation_report(report_text: str) -> list[dict[str, Any]]:
    """从季报“基金资产组合情况”提取按总资产计算的四类资产占比。"""
    section_match = re.search(
        r"5[\.．]\s*1\s*报告期末基金资产组合情况"
        r"(.*?)(?=\n\s*5[\.．]\s*2(?:\s|报))",
        report_text,
        flags=re.DOTALL,
    )
    if not section_match:
        return []

    section = section_match.group(1)
    category_labels = {
        "权益投资": "股票",
        "固定收益投资": "债券",
        "基金投资": "基金",
    }
    allocation = {label: 0.0 for label in ("股票", "债券", "基金")}
    found: set[str] = set()
    for line in section.splitlines():
        category_match = re.search(
            r"(权益投资|固定收益投资|基金投资)", line
        )
        if not category_match:
            continue
        category = category_labels[category_match.group(1)]
        tail = line[category_match.end() :]
        numbers = re.findall(
            r"(?<![\d,])\d+(?:,\d{3})*(?:\.\d+)?(?![\d,])", tail
        )
        candidates = [
            float(number.replace(",", ""))
            for number in numbers
            if float(number.replace(",", "")) <= 100
        ]
        allocation[category] = round(candidates[-1], 2) if candidates else 0.0
        found.add(category)

    if found != {"股票", "债券", "基金"}:
        return []
    primary_total = sum(allocation.values())
    if primary_total > 100.1:
        return []
    allocation["其他"] = round(max(100 - primary_total, 0), 2)
    return [
        {"资产类别": category, "占比": allocation[category]}
        for category in ("股票", "债券", "基金", "其他")
    ]


def _parse_bond_type_structure(report_text: str) -> list[dict[str, Any]]:
    """从季报提取完整债券组合的品种结构，并拆出政策性金融债。"""
    section_match = re.search(
        r"5[\.．]\s*4\s*报告期末按债券品种分类的债券投资组合"
        r"(.*?)(?=\n\s*5[\.．]\s*5(?:\s|报))",
        report_text,
        flags=re.DOTALL,
    )
    if not section_match:
        return []

    section = section_match.group(1)
    category_pattern = re.compile(
        r"(政策性金融债|企业短期融资券|可转债（可交换债）|"
        r"国家债券|央行票据|金融债券|企业债券|中期票据|"
        r"同业存单|资产支持证券|其他|合计)"
    )
    parsed: dict[str, float] = {}
    for line in section.splitlines():
        category_match = category_pattern.search(line)
        if not category_match:
            continue
        category = category_match.group(1)
        tail = line[category_match.end() :]
        numbers = re.findall(
            r"(?<![\d,])\d+(?:,\d{3})*(?:\.\d+)?(?![\d,])", tail
        )
        candidates = [
            float(number.replace(",", ""))
            for number in numbers
            if float(number.replace(",", "")) <= 1000
        ]
        if candidates:
            parsed[category] = round(candidates[-1], 2)

    parsed.pop("合计", None)
    if "金融债券" in parsed and "政策性金融债" in parsed:
        parsed["金融债（不含政策性）"] = round(
            max(parsed["金融债券"] - parsed["政策性金融债"], 0),
            2,
        )
        parsed.pop("金融债券")
    elif "金融债券" in parsed:
        parsed["金融债"] = parsed.pop("金融债券")

    if parsed.get("其他") and re.search(
        r"其他(?:为|主要为).*?地方政府债", section
    ):
        parsed["地方政府债"] = parsed.pop("其他")

    display_order = (
        "国家债券",
        "央行票据",
        "政策性金融债",
        "地方政府债",
        "金融债（不含政策性）",
        "金融债",
        "企业债券",
        "企业短期融资券",
        "中期票据",
        "同业存单",
        "资产支持证券",
        "可转债（可交换债）",
        "其他",
    )
    return [
        {"债券品种": category, "占净值比例": parsed[category]}
        for category in display_order
        if parsed.get(category, 0) > 0
    ]


def _bond_credit_structure(
    details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把季报债券品种归为利率债、信用债及其他可识别类别。"""
    rate_types = {
        "国家债券",
        "央行票据",
        "政策性金融债",
        "地方政府债",
    }
    credit_types = {
        "金融债（不含政策性）",
        "金融债",
        "企业债券",
        "企业短期融资券",
        "中期票据",
    }
    separate_types = {
        "同业存单": "同业存单",
        "资产支持证券": "资产支持证券",
        "可转债（可交换债）": "可转债",
    }
    totals: dict[str, float] = {}
    for row in details:
        category = str(row.get("债券品种") or "")
        weight = float(row.get("占净值比例") or 0)
        if category in rate_types:
            group = "利率债"
        elif category in credit_types:
            group = "信用债"
        else:
            group = separate_types.get(category, "其他")
        totals[group] = totals.get(group, 0) + weight
    return [
        {"信用属性": category, "占净值比例": round(weight, 2)}
        for category, weight in totals.items()
        if weight > 0
    ]


def _report_period(title: str) -> str | None:
    matched = re.search(
        r"(?P<year>20\d{2})年第?(?P<quarter>[一二三四1-4])季度报告",
        title,
    )
    if not matched:
        return None
    quarter_map = {"一": "1", "二": "2", "三": "3", "四": "4"}
    quarter = quarter_map.get(
        matched.group("quarter"), matched.group("quarter")
    )
    return f"{matched.group('year')}年第{quarter}季度"


def _quarter_end_from_period(period: str | None) -> date | None:
    if not period:
        return None
    matched = re.search(
        r"(?P<year>20\d{2})年(?:第)?(?P<quarter>[1-4])季度", period
    )
    if not matched:
        return None
    year = int(matched.group("year"))
    quarter = int(matched.group("quarter"))
    month_day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    month, day = month_day[quarter]
    return date(year, month, day)


@lru_cache(maxsize=256)
def _bond_public_detail(bond_name: str) -> dict[str, Any]:
    """从中国货币网补充债券品种、到期日和原始期限。"""
    frame = ak.bond_info_detail_cm(symbol=bond_name)
    if frame is None or frame.empty:
        return {}
    if {"item", "value"}.issubset(frame.columns):
        return _item_value_map(frame)
    if frame.shape[1] < 2:
        return {}
    return {
        str(row.iloc[0]).strip(): _clean(row.iloc[1])
        for _, row in frame.iterrows()
    }


def _enrich_bond_holdings(
    holdings: list[dict[str, Any]],
    period: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """补充披露债券的到期信息，并按报告日计算剩余期限。"""
    if not holdings:
        return holdings, {}

    report_date = _quarter_end_from_period(period)
    enriched = [dict(row) for row in holdings]
    names = {
        index: str(row.get("债券名称") or "").strip()
        for index, row in enumerate(enriched)
        if row.get("债券名称")
    }
    details_by_index: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(5, len(names) or 1)) as executor:
        futures = {
            executor.submit(_bond_public_detail, name): index
            for index, name in names.items()
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                details_by_index[index] = future.result()
            except Exception:
                details_by_index[index] = {}

    maturity_totals: dict[str, float] = {}
    known_count = 0
    for index, row in enumerate(enriched):
        details = details_by_index.get(index, {})
        bond_type = _pick(details.get("bondType"), details.get("债券类型"))
        maturity_value = _pick(details.get("mrtyDate"), details.get("到期日"))
        original_period = _pick(
            details.get("bondPeriod"), details.get("债券期限")
        )
        if bond_type:
            row["债券类型"] = bond_type
        if original_period:
            row["原始期限"] = original_period

        maturity_date = pd.to_datetime(maturity_value, errors="coerce")
        maturity_bucket = "期限未知"
        if pd.notna(maturity_date):
            row["到期日"] = maturity_date.date().isoformat()
            if report_date:
                remaining_years = max(
                    (maturity_date.date() - report_date).days / 365.25,
                    0,
                )
                row["剩余期限年"] = round(remaining_years, 2)
                if remaining_years <= 1:
                    maturity_bucket = "短债（≤1年）"
                elif remaining_years <= 3:
                    maturity_bucket = "中期（1–3年）"
                else:
                    maturity_bucket = "长债（>3年）"
                row["期限分类"] = maturity_bucket
                known_count += 1

        weight = float(row.get("占净值比例") or 0)
        maturity_totals[maturity_bucket] = (
            maturity_totals.get(maturity_bucket, 0) + weight
        )

    maturity_order = (
        "短债（≤1年）",
        "中期（1–3年）",
        "长债（>3年）",
        "期限未知",
    )
    maturity_details = [
        {"期限分类": bucket, "占净值比例": round(maturity_totals[bucket], 2)}
        for bucket in maturity_order
        if maturity_totals.get(bucket, 0) > 0
    ]
    return enriched, {
        "可用": known_count > 0,
        "口径": "披露债券按最终到期日计算的剩余期限",
        "报告期": period,
        "截止日": report_date.isoformat() if report_date else None,
        "覆盖数量": known_count,
        "披露数量": len(enriched),
        "明细": maturity_details,
        "说明": (
            "仅基于最新报告披露的前几大债券，不代表全组合久期；"
            "含权债按最终到期日计算。"
        ),
    }


def _load_portfolio_report(
    code: str, warnings: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """下载最新季报，返回资产分布与完整债券品种结构。"""
    reports = _safe_call(
        "基金季度报告",
        ak.fund_announcement_report_em,
        warnings,
        symbol=code,
    )
    required = {"公告标题", "报告ID"}
    if reports.empty or not required.issubset(reports.columns):
        return {}, {}

    selected = reports.loc[
        reports["公告标题"].astype(str).str.contains(r"季度报告\s*$")
    ].copy()
    if selected.empty:
        return {}, {}
    if "公告日期" in selected.columns:
        selected["_公告日期"] = pd.to_datetime(
            selected["公告日期"], errors="coerce"
        )
        selected = selected.sort_values("_公告日期", ascending=False)
    latest = selected.iloc[0]
    report_id = str(latest["报告ID"]).strip()
    if not re.fullmatch(r"AN\d+", report_id):
        warnings.append("基金组合结构获取失败：季报 ID 格式异常。")
        return {}, {}

    try:
        response = requests.get(
            f"https://pdf.dfcfw.com/pdf/H2_{report_id}_1.pdf",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        response.raise_for_status()
        report_text = "\n".join(
            page.extract_text(extraction_mode="layout") or ""
            for page in PdfReader(io.BytesIO(response.content)).pages
        )
    except Exception as exc:
        warnings.append(f"基金组合结构获取失败：{exc}")
        return {}, {}

    asset_details = _parse_asset_allocation_report(report_text)
    bond_details = _parse_bond_type_structure(report_text)
    if not asset_details:
        warnings.append("基金资产分布获取失败：未能解析最新季度报告。")

    title = str(latest["公告标题"]).strip()
    announcement_date = _clean(latest.get("公告日期"))
    report_period = _report_period(title)
    asset_allocation = (
        {
            "可用": True,
            "口径": "占基金总资产比例",
            "报告期": report_period,
            "公告日期": announcement_date,
            "明细": asset_details,
            "来源报告": title,
            "说明": (
                "来自最新季度报告的基金资产组合；其他包含现金、"
                "买入返售、衍生品及其他各项资产。"
            ),
        }
        if asset_details
        else {}
    )
    bond_structure = (
        {
            "可用": True,
            "口径": "季度报告完整债券组合占基金净值比例",
            "报告期": report_period,
            "公告日期": announcement_date,
            "明细": bond_details,
            "信用属性": {
                "明细": _bond_credit_structure(bond_details),
                "口径": "按季报债券品种归并",
                "说明": (
                    "利率债含国债、央票、政策性金融债和地方政府债；"
                    "信用债含非政策性金融债、企业债、短融和中票。"
                ),
            },
            "来源报告": title,
            "说明": (
                "来自最新季度报告的完整债券品种结构；债券杠杆会使"
                "合计占基金净值超过 100%。"
            ),
        }
        if bond_details
        else {}
    )
    return asset_allocation, bond_structure


def _curve_history(
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
    output_value_key: str,
    max_points: int = 1600,
    extra_columns: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """整理历史曲线，并在数据过长时等距抽样供前端绘图。"""
    required = {date_column, value_column}
    if frame.empty or not required.issubset(frame.columns):
        return []

    selected = frame.copy()
    selected[date_column] = pd.to_datetime(
        selected[date_column], errors="coerce"
    )
    selected[value_column] = pd.to_numeric(
        selected[value_column], errors="coerce"
    )
    selected = (
        selected.dropna(subset=[date_column, value_column])
        .sort_values(date_column)
        .drop_duplicates(subset=[date_column], keep="last")
        .reset_index(drop=True)
    )
    if selected.empty:
        return []

    if len(selected) > max_points:
        indices = {
            round(index * (len(selected) - 1) / (max_points - 1))
            for index in range(max_points)
        }
        selected = selected.iloc[sorted(indices)]

    records: list[dict[str, Any]] = []
    for _, row in selected.iterrows():
        record = {
            "日期": row[date_column].strftime("%Y-%m-%d"),
            output_value_key: _clean(row[value_column]),
        }
        for source, target in (extra_columns or {}).items():
            if source in selected.columns:
                record[target] = _clean(row.get(source))
        records.append(record)
    return records


def _nav_history(
    frame: pd.DataFrame, max_points: int = 1600
) -> list[dict[str, Any]]:
    return _curve_history(
        frame,
        date_column="净值日期",
        value_column="单位净值",
        output_value_key="单位净值",
        max_points=max_points,
        extra_columns={"日增长率": "日涨幅"},
    )


def _dividend_history(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty or "除息日" not in frame.columns:
        return []
    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        ex_date = pd.to_datetime(row.get("除息日"), errors="coerce")
        if pd.isna(ex_date):
            continue
        description = _clean(
            row.get("每10份分红", row.get("每份分红"))
        )
        amount = None
        if description is not None:
            matched = re.search(r"现金\s*([\d.]+)\s*元", str(description))
            if matched:
                amount = round(float(matched.group(1)) / 10, 8)
        records.append(
            {
                "除息日": ex_date.strftime("%Y-%m-%d"),
                "每份分红": amount,
                "说明": description,
            }
        )
    return sorted(records, key=lambda record: record["除息日"])


def _fallback_performance(
    code: str,
    warnings: list[str],
    unit_nav: pd.DataFrame | None = None,
    cumulative_nav: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """排行接口不可用时，从单基金接口补充净值和区间业绩。"""
    performance: dict[str, Any] = {}
    net_value: dict[str, Any] = {}

    achievement = _safe_call(
        "单基金阶段业绩",
        ak.fund_individual_achievement_xq,
        warnings,
        symbol=code,
    )
    if not achievement.empty and {"周期", "本产品区间收益"}.issubset(
        achievement.columns
    ):
        for period in ("近1月", "近3月", "近6月", "近1年", "近3年", "成立以来"):
            rows = achievement.loc[achievement["周期"].astype(str) == period]
            if not rows.empty:
                performance[period] = _clean(rows.iloc[0]["本产品区间收益"])

    if unit_nav is None:
        unit_nav = _safe_call(
            "单位净值",
            ak.fund_open_fund_info_em,
            warnings,
            symbol=code,
            indicator="单位净值走势",
        )
    if cumulative_nav is None:
        cumulative_nav = _safe_call(
            "累计净值",
            ak.fund_open_fund_info_em,
            warnings,
            symbol=code,
            indicator="累计净值走势",
        )
    if not unit_nav.empty:
        unit_nav = unit_nav.sort_values("净值日期")
        latest = unit_nav.iloc[-1]
        net_value.update(
            {
                "日期": _clean(latest.get("净值日期")),
                "单位净值": _clean(latest.get("单位净值")),
            }
        )
        performance["日涨幅"] = _clean(latest.get("日增长率"))
    if not cumulative_nav.empty:
        cumulative_nav = cumulative_nav.sort_values("净值日期")
        net_value["累计净值"] = _clean(cumulative_nav.iloc[-1].get("累计净值"))

    return net_value, performance


def get_fund_data(
    fund_code: str, holdings_limit: int | None = None
) -> dict[str, Any]:
    """查询单只基金并返回适合 JSON 输出的字典。

    参数:
        fund_code: 六位基金代码。
        holdings_limit: 最多返回多少条最新持仓；None 表示全部返回。
    """
    code = _normalize_code(fund_code)
    if holdings_limit is not None and holdings_limit <= 0:
        raise ValueError("holdings_limit 必须大于 0。")

    warnings: list[str] = []

    overview_frame = _safe_call(
        "基金基本概况", ak.fund_overview_em, warnings, symbol=code
    )
    xq_frame = _safe_call(
        "基金投资目标", ak.fund_individual_basic_info_xq, warnings, symbol=code
    )
    overview = _first_row(overview_frame)
    xq = _item_value_map(xq_frame)
    found_date = _extract_found_date(overview, xq)
    scale_details = _extract_scale_details(overview, xq)
    holder_structure = _load_holder_structure(code, warnings)
    purchase_fee = _load_purchase_fee(code, warnings)

    rank_row, rank_source = _load_rank_row(code, warnings)
    net_value = {
        "日期": _pick(rank_row.get("日期")),
        "单位净值": _pick(rank_row.get("单位净值")),
        "累计净值": _pick(rank_row.get("累计净值")),
    }
    performance = {
        "日涨幅": _pick(rank_row.get("日增长率")),
        "近1月": _pick(rank_row.get("近1月")),
        "近3月": _pick(rank_row.get("近3月")),
        "近6月": _pick(rank_row.get("近6月")),
        "近1年": _pick(rank_row.get("近1年")),
        "近3年": _pick(rank_row.get("近3年")),
        "单位": "%",
    }

    nav_requests: dict[str, dict[str, Any]] = {
        "单位净值": {"indicator": "单位净值走势"},
        "累计净值": {"indicator": "累计净值走势"},
        "分红": {"indicator": "分红送配详情"},
        "收益_all": {"indicator": "累计收益率走势", "period": "成立来"},
        "收益_5y": {"indicator": "累计收益率走势", "period": "5年"},
        "收益_3y": {"indicator": "累计收益率走势", "period": "3年"},
        "收益_1y": {"indicator": "累计收益率走势", "period": "1年"},
        "收益_6m": {"indicator": "累计收益率走势", "period": "6月"},
        "收益_3m": {"indicator": "累计收益率走势", "period": "3月"},
        "收益_1m": {"indicator": "累计收益率走势", "period": "1月"},
    }
    nav_frames = {
        key: _safe_call(
            f"历史{key}",
            ak.fund_open_fund_info_em,
            warnings,
            symbol=code,
            **kwargs,
        )
        for key, kwargs in nav_requests.items()
    }

    nav_history_frame = nav_frames["单位净值"]
    cumulative_nav_frame = nav_frames["累计净值"]
    required_nav_fields = ("单位净值", "累计净值")
    required_performance_fields = (
        "日涨幅",
        "近1月",
        "近3月",
        "近6月",
        "近1年",
        "近3年",
    )
    needs_fallback = not rank_row or any(
        net_value.get(key) is None for key in required_nav_fields
    ) or any(performance.get(key) is None for key in required_performance_fields)
    if needs_fallback:
        fallback_nav, fallback_performance = _fallback_performance(
            code,
            warnings,
            unit_nav=nav_history_frame,
            cumulative_nav=cumulative_nav_frame,
        )
        for key, value in fallback_nav.items():
            if net_value.get(key) is None and value is not None:
                net_value[key] = value
        for key, value in fallback_performance.items():
            if performance.get(key) is None and value is not None:
                performance[key] = value
    net_value["单位"] = "元"
    nav_history = _nav_history(nav_history_frame, max_points=6000)
    cumulative_nav_history = _curve_history(
        cumulative_nav_frame,
        date_column="净值日期",
        value_column="累计净值",
        output_value_key="累计净值",
    )
    cumulative_returns = {
        range_key: _curve_history(
            nav_frames[f"收益_{range_key}"],
            date_column="日期",
            value_column="累计收益率",
            output_value_key="累计收益率",
            max_points=5000 if range_key == "all" else 1600,
        )
        for range_key in ("all", "5y", "3y", "1y", "6m", "3m", "1m")
    }
    dividends = _dividend_history(nav_frames["分红"])

    if performance.get("成立以来") is None:
        inception_curve = cumulative_returns.get("all") or []
        if inception_curve:
            performance["成立以来"] = _clean(
                inception_curve[-1].get("累计收益率")
            )

    stock_holdings_frame = _safe_call(
        "股票持仓",
        ak.fund_portfolio_hold_em,
        warnings,
        symbol=code,
        date="",
    )
    bond_holdings_frame = _load_bond_holdings(code, warnings)
    stock_holdings, stock_holdings_period = _latest_holdings(
        stock_holdings_frame, limit=holdings_limit
    )
    bond_holdings, bond_holdings_period = _latest_holdings(
        bond_holdings_frame, limit=holdings_limit
    )
    industry_frame = (
        _load_industry_allocation(code, warnings)
        if stock_holdings
        else pd.DataFrame()
    )
    industry_allocation, industry_period = _latest_industry_allocation(
        industry_frame
    )
    asset_allocation, bond_type_structure = _load_portfolio_report(
        code, warnings
    )
    bond_holdings, bond_maturity_structure = _enrich_bond_holdings(
        bond_holdings, bond_holdings_period
    )

    fund_full_name = str(
        _pick(
            overview.get("基金全称"),
            xq.get("基金全称"),
            overview.get("基金简称"),
            rank_row.get("基金简称"),
        )
        or ""
    )
    is_etf_link = "联接" in fund_full_name
    target_etf_code = (
        _load_related_etf_code(code, warnings) if is_etf_link else None
    )
    target_etf_overview = pd.DataFrame()
    target_etf_holdings: list[dict[str, Any]] = []
    target_etf_period = None
    target_etf_industry: list[dict[str, Any]] = []
    target_etf_industry_period = None
    if target_etf_code:
        target_etf_overview = _safe_call(
            "目标 ETF 基础资料",
            ak.fund_overview_em,
            warnings,
            symbol=target_etf_code,
        )
        target_etf_holdings_frame = _safe_call(
            "目标 ETF 股票持仓",
            ak.fund_portfolio_hold_em,
            warnings,
            symbol=target_etf_code,
            date="",
        )
        target_etf_holdings, target_etf_period = _latest_holdings(
            target_etf_holdings_frame, limit=holdings_limit
        )
        target_etf_industry_frame = _load_industry_allocation(
            target_etf_code, warnings
        )
        (
            target_etf_industry,
            target_etf_industry_period,
        ) = _latest_industry_allocation(target_etf_industry_frame)

    target_etf_row = _first_row(target_etf_overview)
    target_etf_name = _pick(
        target_etf_row.get("基金简称"),
        target_etf_row.get("基金全称"),
    )
    primary_holdings = stock_holdings or bond_holdings
    primary_period = stock_holdings_period or bond_holdings_period

    basic = {
        "名称": _pick(
            overview.get("基金简称"),
            xq.get("基金名称"),
            rank_row.get("基金简称"),
        ),
        "代码": code,
        "类型": _pick(overview.get("基金类型"), xq.get("基金类型")),
        "成立日": found_date,
        "成立日期": found_date,
        "成立时间": _fund_age(found_date),
        "基金规模": scale_details,
        "持有人结构": holder_structure,
        "买入费率": purchase_fee,
        "管理人": _pick(overview.get("基金管理人"), xq.get("基金公司")),
        "托管人": _pick(overview.get("基金托管人"), xq.get("托管银行")),
        "投资目标": _pick(xq.get("投资目标")),
        "业绩比较基准": _pick(
            overview.get("业绩比较基准"), xq.get("业绩比较基准")
        ),
        "管理费率": _pick(overview.get("管理费率"), xq.get("管理费")),
        "托管费率": _pick(overview.get("托管费率"), xq.get("托管费")),
    }

    if not any((basic["名称"], net_value["单位净值"], primary_holdings)):
        details = "；".join(warnings[-3:]) if warnings else "AKShare 未返回数据"
        raise FundLookupError(f"未找到基金 {code}：{details}")

    share_class_advice = _build_share_class_advice(
        code, str(basic["名称"] or ""), purchase_fee, warnings
    )
    if share_class_advice:
        basic["AC份额建议"] = share_class_advice

    return {
        "基础资料": basic,
        "净值信息": net_value,
        "历史业绩": performance,
        "净值曲线": {
            "指标": "单位净值",
            "数量": len(nav_history),
            "起始日": nav_history[0]["日期"] if nav_history else None,
            "结束日": nav_history[-1]["日期"] if nav_history else None,
            "单位": "元",
            "明细": nav_history,
            "默认指标": "累计收益率",
            "单位净值": {
                "单位": "元",
                "数量": len(nav_history),
                "明细": nav_history,
            },
            "累计净值": {
                "单位": "元",
                "数量": len(cumulative_nav_history),
                "明细": cumulative_nav_history,
            },
            "累计收益率": {
                "单位": "%",
                "区间": cumulative_returns,
            },
            "分红事件": dividends,
        },
        "基金持仓": {
            "报告期": primary_period,
            "数量": len(stock_holdings) + len(bond_holdings),
            "资产分布": asset_allocation,
            "资产分类": [
                asset_type
                for asset_type, rows in (
                    ("股票", stock_holdings),
                    ("债券", bond_holdings),
                )
                if rows
            ],
            "单位说明": {
                "占净值比例": "%",
                "持股数": "万股",
                "持仓市值": "万元",
            },
            "明细": primary_holdings,
            "股票持仓": {
                "报告期": stock_holdings_period,
                "数量": len(stock_holdings),
                "明细": stock_holdings,
            },
            "债券持仓": {
                "报告期": bond_holdings_period,
                "数量": len(bond_holdings),
                "明细": bond_holdings,
                "品种结构": bond_type_structure,
                "期限结构": bond_maturity_structure,
            },
            "板块配置": {
                "可用": bool(industry_allocation),
                "口径": "基金定期报告中的股票行业配置",
                "报告期": industry_period,
                "数量": len(industry_allocation),
                "明细": industry_allocation,
                "说明": (
                    "板块数据来自基金定期报告披露的股票行业配置。"
                    if industry_allocation
                    else "AKShare 暂无该基金的股票行业配置。"
                ),
            },
            "ETF穿透": {
                "适用": is_etf_link,
                "可用": bool(target_etf_holdings),
                "目标ETF": (
                    {
                        "代码": target_etf_code,
                        "名称": target_etf_name,
                    }
                    if target_etf_code
                    else None
                ),
                "报告期": target_etf_period,
                "数量": len(target_etf_holdings),
                "明细": target_etf_holdings,
                "权重口径": (
                    "目标 ETF 内部占净值比例，未乘以联接基金持有目标 ETF 的比例"
                ),
                "板块配置": {
                    "可用": bool(target_etf_industry),
                    "口径": "目标 ETF 定期报告中的股票行业配置",
                    "报告期": target_etf_industry_period,
                    "数量": len(target_etf_industry),
                    "明细": target_etf_industry,
                },
                "说明": (
                    "已穿透至目标 ETF 的底层股票持仓。"
                    if target_etf_holdings
                    else (
                        "该基金属于 ETF 联接基金，但暂未取得目标 ETF 持仓。"
                        if is_etf_link
                        else "该基金不是 ETF 联接基金，无需穿透。"
                    )
                ),
            },
        },
        "数据来源": {
            "基础资料": [
                "AKShare.fund_overview_em",
                "AKShare.fund_individual_basic_info_xq",
                "天天基金持有人结构及申购费率（AKShare 同源）",
            ],
            "净值及业绩": rank_source
            or "AKShare 单基金净值/业绩接口（降级路径）",
            "净值曲线": (
                "AKShare.fund_open_fund_info_em"
                "（累计收益率/累计净值/单位净值/分红送配）"
            ),
            "持仓": [
                "AKShare.fund_portfolio_hold_em",
                "AKShare.fund_portfolio_bond_hold_em",
                "AKShare.fund_portfolio_industry_allocation_em",
                "AKShare.fund_announcement_report_em + 最新季度报告 PDF",
                "AKShare.bond_info_detail_cm（中国货币网债券详情）",
                "东方财富基金详情页相关 ETF 链接",
            ],
            "查询时间": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "提示": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="输入基金代码，通过 AKShare 查询基础资料、净值、业绩和持仓。"
    )
    parser.add_argument("fund_code", help="六位基金代码，例如 000001")
    parser.add_argument(
        "--holdings-limit",
        type=int,
        default=None,
        help="限制返回的最新持仓数量；默认全部返回",
    )
    parser.add_argument(
        "--compact", action="store_true", help="输出紧凑 JSON"
    )
    args = parser.parse_args()

    try:
        result = get_fund_data(args.fund_code, args.holdings_limit)
    except (ValueError, FundLookupError) as exc:
        parser.error(str(exc))
        return 2

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
