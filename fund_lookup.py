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

from benchmarks import recommend_track_benchmark

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


def _holdings_for_period(
    frame: pd.DataFrame,
    year: int,
    quarter: int,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """从接口返回的一整年持仓中提取指定季度。"""
    if frame.empty or "季度" not in frame.columns:
        return [], None

    periods = frame["季度"].astype("string")
    parsed = periods.str.extract(
        r"(?P<year>\d{4})年(?P<quarter>[1-4])季度"
    )
    matches = (
        pd.to_numeric(parsed["year"], errors="coerce").eq(year)
        & pd.to_numeric(parsed["quarter"], errors="coerce").eq(quarter)
    )
    selected = frame.loc[matches].copy()
    if selected.empty:
        return [], None

    period = str(periods.loc[selected.index[0]])
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
    return (
        [
            {str(key): _clean(value) for key, value in row.items()}
            for row in selected.to_dict(orient="records")
        ],
        period,
    )


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _stock_market_prefix(code: str) -> str:
    if code.startswith(("4", "8", "92")):
        return "BJ"
    if code.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


def _load_stock_quotes(codes: list[str]) -> dict[str, dict[str, Any]]:
    """通过新浪批量行情一次取得持仓股票的最新价与行情日期。"""
    symbols = [
        f"{_stock_market_prefix(code).lower()}{code}"
        for code in dict.fromkeys(codes)
        if re.fullmatch(r"\d{6}", code)
    ]
    if not symbols:
        return {}

    response = requests.get(
        f"https://hq.sinajs.cn/list={','.join(symbols)}",
        headers={
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=10,
    )
    response.raise_for_status()
    text_data = response.content.decode("gbk", errors="ignore")
    quotes: dict[str, dict[str, Any]] = {}
    for symbol, payload in re.findall(
        r'var hq_str_([a-z]{2}\d{6})="([^"]*)";',
        text_data,
        flags=re.IGNORECASE,
    ):
        values = payload.split(",")
        if len(values) < 32:
            continue
        code = symbol[-6:]
        current = _finite_float(values[3])
        previous = _finite_float(values[2])
        price = current if current and current > 0 else previous
        quotes[code] = {
            "名称": values[0].strip() or None,
            "最新价": price,
            "行情日期": values[30] or None,
        }
    return quotes


def _load_stock_fundamentals(
    code: str,
    quote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """查询单股估值与分红，并计算 ROE、近十二个月股息率。

    东方财富的估值比较接口会同时返回目标个股、行业平均、行业中值和
    若干同行股票，因此这里只接受证券代码与目标代码完全一致的记录。
    """
    result: dict[str, Any] = {
        "所属行业": None,
        "PE": None,
        "PB": None,
        "ROE": None,
        "股息率": None,
        "最新价": _finite_float((quote or {}).get("最新价")),
        "行情日期": (quote or {}).get("行情日期"),
    }

    industry_error = None
    try:
        profile = ak.stock_profile_cninfo(symbol=code)
        if profile is not None and not profile.empty and "所属行业" in profile:
            selected = profile
            if "A股代码" in selected.columns:
                matched = selected.loc[
                    selected["A股代码"].astype(str).str.strip().str.zfill(6)
                    == code
                ]
                if not matched.empty:
                    selected = matched
            industry = _clean(selected.iloc[0].get("所属行业"))
            if industry is not None and str(industry).strip():
                result["所属行业"] = str(industry).strip()
    except Exception as exc:
        industry_error = str(exc)
    if result["所属行业"] is None:
        try:
            stock_info = ak.stock_individual_info_em(symbol=code, timeout=10)
            industry = _item_value_map(stock_info).get("行业")
            if industry is not None and str(industry).strip():
                result["所属行业"] = str(industry).strip()
                industry_error = None
        except Exception as exc:
            industry_error = (
                f"巨潮资讯：{industry_error}；东方财富：{exc}"
                if industry_error
                else str(exc)
            )

    valuation_error = None
    try:
        valuation = ak.stock_zh_valuation_comparison_em(
            symbol=f"{_stock_market_prefix(code)}{code}"
        )
        if valuation is not None and not valuation.empty:
            if "代码" not in valuation.columns:
                raise ValueError("估值比较结果缺少证券代码列")
            matched = valuation.loc[
                valuation["代码"].astype(str).str.strip().str.zfill(6) == code
            ]
            if matched.empty:
                raise ValueError(f"估值比较结果中未找到目标个股 {code}")
            row = matched.iloc[0]
            result["PE"] = _finite_float(row.get("市盈率-TTM"))
            result["PB"] = _finite_float(
                _pick(row.get("市净率-MRQ"), row.get("市净率-24A"))
            )
            pe = result["PE"]
            pb = result["PB"]
            if pe not in (None, 0) and pb is not None:
                result["ROE"] = pb / pe * 100
    except Exception as exc:
        try:
            market = _stock_market_prefix(code)
            response = requests.get(
                "https://datacenter.eastmoney.com/securities/api/data/v1/get",
                params={
                    "reportName": "RPT_PCF10_INDUSTRY_CVALUE",
                    "columns": "ALL",
                    "quoteColumns": "",
                    "filter": f'(SECUCODE="{code}.{market}")',
                    "pageNumber": "",
                    "pageSize": "",
                    "sortTypes": "1",
                    "sortColumns": "PAIMING",
                    "source": "HSF10",
                    "client": "PC",
                },
                timeout=10,
            )
            response.raise_for_status()
            records = response.json().get("result", {}).get("data", [])
            row = next(
                (
                    item
                    for item in records
                    if str(item.get("CORRE_SECURITY_CODE") or "") == code
                ),
                None,
            )
            if row:
                result["PE"] = _finite_float(row.get("PE_TTM"))
                result["PB"] = _finite_float(
                    _pick(row.get("PB_MRQ"), row.get("PB"))
                )
                pe = result["PE"]
                pb = result["PB"]
                if pe not in (None, 0) and pb is not None:
                    result["ROE"] = pb / pe * 100
            else:
                valuation_error = str(exc)
        except Exception as fallback_exc:
            valuation_error = f"{exc}；备用接口：{fallback_exc}"

    dividend_error = None
    try:
        dividends = ak.stock_history_dividend_detail(
            symbol=code,
            indicator="分红",
        )
        price = result["最新价"]
        if price and price > 0 and dividends is not None:
            if dividends.empty:
                result["股息率"] = 0.0
            elif "派息" in dividends.columns:
                date_column = (
                    "除权除息日"
                    if "除权除息日" in dividends.columns
                    else "公告日期"
                )
                dates = pd.to_datetime(
                    dividends.get(date_column),
                    errors="coerce",
                )
                quote_date = pd.to_datetime(
                    result["行情日期"],
                    errors="coerce",
                )
                if pd.isna(quote_date):
                    quote_date = pd.Timestamp.now().normalize()
                start_date = quote_date - pd.Timedelta(days=365)
                cash = pd.to_numeric(
                    dividends["派息"],
                    errors="coerce",
                )
                # 新浪“派息”为每 10 股现金分红。
                ttm_cash_per_share = (
                    cash.loc[
                        dates.notna()
                        & dates.le(quote_date)
                        & dates.gt(start_date)
                    ].dropna().sum()
                    / 10
                )
                result["股息率"] = ttm_cash_per_share / price * 100
    except Exception as exc:
        dividend_error = str(exc)

    result["估值可用"] = any(
        result[key] is not None
        for key in ("PE", "PB", "ROE", "股息率")
    )
    result["_行业错误"] = industry_error
    result["_估值错误"] = valuation_error
    result["_分红错误"] = dividend_error
    return result


def _weighted_stock_metric(
    rows: list[dict[str, Any]],
    metric: str,
) -> tuple[float | None, int, float]:
    weighted_sum = 0.0
    weighted_inverse_sum = 0.0
    total_weight = 0.0
    count = 0
    for row in rows:
        value = _finite_float(row.get(metric))
        weight = _finite_float(row.get("占净值比例"))
        if value is None or weight is None or weight <= 0:
            continue
        if metric in ("PE", "PB") and value <= 0:
            continue
        weighted_sum += value * weight
        if metric in ("PE", "PB"):
            weighted_inverse_sum += weight / value
        total_weight += weight
        count += 1
    if total_weight <= 0:
        return None, 0, 0.0
    value = (
        total_weight / weighted_inverse_sum
        if metric in ("PE", "PB") and weighted_inverse_sum > 0
        else weighted_sum / total_weight
    )
    return value, count, total_weight


def _enrich_stock_holdings(
    holdings: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """补充股票指标，并按披露持仓权重汇总组合估值。"""
    if not holdings:
        return holdings, {}

    enriched = [dict(row) for row in holdings]
    codes = [
        str(row.get("股票代码") or "").strip().zfill(6)
        for row in enriched
    ]
    try:
        quotes = _load_stock_quotes(codes)
    except Exception as exc:
        quotes = {}
        warnings.append(f"持仓股票最新价格获取失败：{exc}")

    metrics_by_code: dict[str, dict[str, Any]] = {}
    valid_codes = sorted(
        {
            code
            for code in codes
            if re.fullmatch(r"\d{6}", code)
        }
    )
    with ThreadPoolExecutor(max_workers=min(6, len(valid_codes) or 1)) as executor:
        futures = {
            executor.submit(
                _load_stock_fundamentals,
                code,
                quotes.get(code),
            ): code
            for code in valid_codes
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                metrics_by_code[code] = future.result()
            except Exception as exc:
                metrics_by_code[code] = {
                    "估值可用": False,
                    "_行业错误": str(exc),
                    "_估值错误": str(exc),
                    "_分红错误": None,
                }

    industry_failures = 0
    valuation_failures = 0
    dividend_failures = 0
    quote_dates: list[str] = []
    for row, code in zip(enriched, codes):
        metrics = metrics_by_code.get(code, {})
        for key in ("PE", "PB", "ROE", "股息率", "最新价"):
            numeric = _finite_float(metrics.get(key))
            row[key] = round(numeric, 4) if numeric is not None else None
        row["所属行业"] = metrics.get("所属行业")
        row["行情日期"] = metrics.get("行情日期")
        if metrics.get("_行业错误"):
            industry_failures += 1
        if metrics.get("_估值错误"):
            valuation_failures += 1
        if metrics.get("_分红错误"):
            dividend_failures += 1
        if metrics.get("行情日期"):
            quote_dates.append(str(metrics["行情日期"]))

    if industry_failures:
        warnings.append(
            f"{industry_failures} 只持仓股票的所属行业暂不可用。"
        )
    if valuation_failures:
        warnings.append(
            f"{valuation_failures} 只持仓股票的 PE/PB 数据暂不可用。"
        )
    if dividend_failures:
        warnings.append(
            f"{dividend_failures} 只持仓股票的分红数据暂不可用。"
        )

    aggregate: dict[str, Any] = {}
    coverage: dict[str, Any] = {}
    for metric in ("PE", "PB", "ROE", "股息率"):
        value, count, weight = _weighted_stock_metric(enriched, metric)
        aggregate[metric] = round(value, 4) if value is not None else None
        coverage[metric] = {
            "数量": count,
            "占净值比例": round(weight, 4),
        }

    available_count = sum(
        any(row.get(key) is not None for key in ("PE", "PB", "ROE", "股息率"))
        for row in enriched
    )
    summary = {
        "可用": available_count > 0,
        "持仓数量": len(enriched),
        "覆盖数量": available_count,
        "估值日期": max(quote_dates) if quote_dates else None,
        "组合指标": aggregate,
        "指标覆盖": coverage,
        "口径": "按已披露股票占净值比例，对可用指标分别加权",
        "说明": (
            "PE 为 TTM、PB 为 MRQ，组合值按持仓权重调和汇总；"
            "ROE 按 PB÷PE 推算 TTM 口径；股息率按近 12 个月已除息"
            "现金分红÷最新价计算，组合 ROE 与股息率按持仓权重算术加权。"
            "指标为查询时点数据，不是基金报告期时点数据。"
        ),
    }
    return enriched, summary


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


def _industry_allocation_for_period(
    frame: pd.DataFrame,
    year: int,
    quarter: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """提取指定季度末的股票行业配置。"""
    required = {"行业类别", "占净值比例", "截止时间"}
    if frame.empty or not required.issubset(frame.columns):
        return [], None

    selected = frame.copy()
    dates = pd.to_datetime(selected["截止时间"], errors="coerce")
    period_number = dates.dt.year * 10 + ((dates.dt.month - 1) // 3 + 1)
    selected = selected.loc[period_number.eq(year * 10 + quarter)].copy()
    dates = dates.loc[selected.index]
    if selected.empty or not dates.notna().any():
        return [], None

    latest_date = dates.max()
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
    return (
        [
            {str(key): _clean(value) for key, value in row.items()}
            for row in selected.to_dict(orient="records")
        ],
        latest_date.date().isoformat(),
    )


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
        r"(.*?)(?=\n\s*5[\.．]\s*2(?:\s|报|期))",
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
        if candidates:
            allocation[category] = round(candidates[-1], 2)
        elif category not in found:
            allocation[category] = 0.0
        found.add(category)

    if not found:
        return []
    primary_total = sum(allocation.values())
    if primary_total > 100.1:
        return []
    allocation["其他"] = round(max(100 - primary_total, 0), 2)
    return [
        {"资产类别": category, "占比": allocation[category]}
        for category in ("股票", "债券", "基金", "其他")
    ]


def _parse_target_fund_holdings(
    report_text: str,
) -> list[dict[str, Any]]:
    """从 ETF 联接基金季报提取其期末目标基金持仓。"""
    target_match = re.search(
        r"2[\.．]\s*1[\.．]\s*1\s*目标基金基本情况"
        r"(.*?)(?=2[\.．]\s*1[\.．]\s*2\s*目标基金产品说明)",
        report_text,
        flags=re.DOTALL,
    )
    holding_match = re.search(
        r"5[\.．]\s*\d+\s*期末投资目标基金明细"
        r"(.*?)(?=\n\s*5[\.．]\s*\d+(?:[\.．]\d+)?(?:\s|报|期))",
        report_text,
        flags=re.DOTALL,
    )
    if not target_match or not holding_match:
        return []

    target_section = target_match.group(1)
    holding_section = holding_match.group(1)
    name_match = re.search(r"基金名称\s+([^\n]+)", target_section)
    code_match = re.search(r"基金主代码\s+(\d{6})", target_section)
    operation_match = re.search(r"基金运作方式\s+([^\n]+)", target_section)
    if not name_match:
        return []

    market_values = re.findall(
        r"\d{1,3}(?:,\d{3})+\.\d{2}",
        holding_section,
    )
    percentages = [
        float(value)
        for value in re.findall(r"(?<![\d,])\d+\.\d+(?![\d,])", holding_section)
        if 0 <= float(value) <= 100
    ]
    if not market_values or not percentages:
        return []

    market_value_yuan = float(market_values[-1].replace(",", ""))
    return [
        {
            "持仓排名": 1,
            "持仓类型": "目标ETF",
            "基金代码": code_match.group(1) if code_match else None,
            "基金名称": name_match.group(1).strip(),
            "运作方式": (
                operation_match.group(1).strip() if operation_match else None
            ),
            "占净值比例": round(percentages[-1], 2),
            "持仓市值": round(market_value_yuan / 10_000, 2),
        }
    ]


def _parse_fof_fund_holdings(report_text: str) -> list[dict[str, Any]]:
    """从 FOF 季报的“基金中基金”章节提取前十大基金投资。"""
    section_match = re.search(
        r"6[\.．]\s*1\s*报告期末按公允价值占基金资产净值比例"
        r"大小排序的前十名基金投资明细"
        r"(.*?)(?=\n\s*6[\.．]\s*2(?:\s|当))",
        report_text,
        flags=re.DOTALL,
    )
    if not section_match:
        return []

    section = section_match.group(1)
    row_matches = list(
        re.finditer(r"(?m)^\s*(\d{1,2})\s+(\d{6})\b", section)
    )
    holdings: list[dict[str, Any]] = []
    for index, matched in enumerate(row_matches):
        end = (
            row_matches[index + 1].start()
            if index + 1 < len(row_matches)
            else len(section)
        )
        row_text = section[matched.start() : end]
        weight_match = re.search(
            r"(\d+(?:\.\d+)?)\s+(?:是|否)(?:\s|$)",
            row_text,
        )
        if not weight_match:
            continue
        holdings.append(
            {
                "持仓排名": int(matched.group(1)),
                "持仓类型": "FOF",
                "基金代码": matched.group(2),
                "基金名称": None,
                "基金类型": None,
                "运作方式": None,
                "占净值比例": round(float(weight_match.group(1)), 2),
                "持仓市值": None,
            }
        )
    return holdings


@lru_cache(maxsize=1)
def _fund_name_catalog() -> dict[str, dict[str, Any]]:
    """批量加载基金代码、名称及类型，用于补全 FOF 的 PDF 持仓表。"""
    frame = ak.fund_name_em()
    if frame is None or frame.empty or "基金代码" not in frame.columns:
        return {}
    catalog: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        code = str(row.get("基金代码") or "").strip().zfill(6)
        if not re.fullmatch(r"\d{6}", code):
            continue
        catalog[code] = {
            "基金名称": _clean(row.get("基金简称")),
            "基金类型": _clean(row.get("基金类型")),
        }
    return catalog


def _fund_investment_group(
    holdings: list[dict[str, Any]],
    report_period: str | None,
) -> dict[str, Any]:
    holding_type = (
        str(holdings[0].get("持仓类型") or "") if holdings else None
    )
    is_target_etf = holding_type == "目标ETF"
    return {
        "报告期": report_period,
        "数量": len(holdings),
        "类型": holding_type,
        "明细": holdings,
        "口径": (
            "季度报告披露的期末目标基金投资"
            if is_target_etf
            else "FOF 季度报告披露的前十大基金投资"
        ),
        "说明": (
            "该基金实际持有一只目标 ETF；资产分布保留基金投资，"
            "股票矩阵优先展示目标 ETF 穿透持仓。"
            if is_target_etf
            else "展示 FOF 实际持有的多只基金，不穿透为底层股票。"
        ),
    }


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


def _quarter_key(value: str) -> tuple[int, int]:
    matched = re.fullmatch(r"(?P<year>20\d{2})Q(?P<quarter>[1-4])", value)
    if not matched:
        raise ValueError("报告期必须使用 YYYYQ1 至 YYYYQ4 格式。")
    return int(matched.group("year")), int(matched.group("quarter"))


def _quarter_key_from_period(value: str | None) -> str | None:
    if not value:
        return None
    matched = re.search(
        r"(?P<year>20\d{2})年(?:第)?(?P<quarter>[1-4])季度",
        value,
    )
    if not matched:
        return None
    return f"{matched.group('year')}Q{matched.group('quarter')}"


def _quarter_report_catalog(
    reports: pd.DataFrame,
) -> list[dict[str, Any]]:
    """整理季度报告目录，并生成可直接访问的原始 PDF 链接。"""
    required = {"公告标题", "公告日期", "报告ID"}
    if reports.empty or not required.issubset(reports.columns):
        return []

    entries: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?P<year>20\d{2})年第?(?P<quarter>[一二三四1-4])季度报告\s*$"
    )
    quarter_map = {"一": "1", "二": "2", "三": "3", "四": "4"}
    for _, row in reports.iterrows():
        title = str(row.get("公告标题") or "").strip()
        matched = pattern.search(title)
        report_id = str(row.get("报告ID") or "").strip()
        if not matched or not re.fullmatch(r"AN\d+", report_id):
            continue
        year = int(matched.group("year"))
        quarter = int(
            quarter_map.get(
                matched.group("quarter"),
                matched.group("quarter"),
            )
        )
        entries.append(
            {
                "key": f"{year}Q{quarter}",
                "年度": year,
                "季度": quarter,
                "报告期": f"{year}年第{quarter}季度",
                "公告标题": title,
                "公告日期": _clean(row.get("公告日期")),
                "报告ID": report_id,
                "链接": f"https://pdf.dfcfw.com/pdf/H2_{report_id}_1.pdf",
            }
        )
    entries.sort(
        key=lambda item: (item["年度"], item["季度"]),
        reverse=True,
    )
    return entries


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
    code: str,
    warnings: list[str],
    period_key: str | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """下载最新或指定季报，返回组合结构、报告目录及基金投资明细。"""
    reports = _safe_call(
        "基金季度报告",
        ak.fund_announcement_report_em,
        warnings,
        symbol=code,
    )
    required = {"公告标题", "报告ID"}
    if reports.empty or not required.issubset(reports.columns):
        return {}, {}, [], []

    report_catalog = _quarter_report_catalog(reports)
    if period_key is not None:
        selected_report = next(
            (
                item
                for item in report_catalog
                if item["key"] == period_key
            ),
            None,
        )
        selected = reports.loc[
            reports["报告ID"].astype(str)
            == str((selected_report or {}).get("报告ID") or "")
        ].copy()
    else:
        selected = reports.loc[
            reports["公告标题"].astype(str).str.contains(r"季度报告\s*$")
        ].copy()
    if selected.empty:
        return {}, {}, report_catalog, []
    if "公告日期" in selected.columns:
        selected["_公告日期"] = pd.to_datetime(
            selected["公告日期"], errors="coerce"
        )
        selected = selected.sort_values("_公告日期", ascending=False)
    latest = selected.iloc[0]
    report_id = str(latest["报告ID"]).strip()
    if not re.fullmatch(r"AN\d+", report_id):
        warnings.append("基金组合结构获取失败：季报 ID 格式异常。")
        return {}, {}, report_catalog, []

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
        return {}, {}, report_catalog, []

    asset_details = _parse_asset_allocation_report(report_text)
    bond_details = _parse_bond_type_structure(report_text)
    fund_holdings = _parse_target_fund_holdings(report_text)
    if not fund_holdings:
        fund_holdings = _parse_fof_fund_holdings(report_text)
        if fund_holdings:
            try:
                catalog = _fund_name_catalog()
                for row in fund_holdings:
                    details = catalog.get(str(row.get("基金代码") or ""), {})
                    row["基金名称"] = details.get("基金名称")
                    row["基金类型"] = details.get("基金类型")
            except Exception as exc:
                warnings.append(f"FOF 持仓基金名称补全失败：{exc}")
    if not asset_details:
        warnings.append("基金资产分布获取失败：未能解析最新季度报告。")

    title = str(latest["公告标题"]).strip()
    announcement_date = _clean(latest.get("公告日期"))
    report_period = _report_period(title)
    report_scope = "指定季度报告" if period_key else "最新季度报告"
    asset_allocation = (
        {
            "可用": True,
            "口径": "占基金总资产比例",
            "报告期": report_period,
            "公告日期": announcement_date,
            "明细": asset_details,
            "来源报告": title,
            "说明": (
                f"来自{report_scope}的基金资产组合；其他包含现金、"
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
                f"来自{report_scope}的完整债券品种结构；债券杠杆会使"
                "合计占基金净值超过 100%。"
            ),
        }
        if bond_details
        else {}
    )
    return asset_allocation, bond_structure, report_catalog, fund_holdings


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


def _year_to_date_return(
    rows: list[dict[str, Any]],
) -> float | None:
    """从累计收益率曲线计算最新年份年初至今涨幅。"""
    valid: list[tuple[str, float]] = []
    for row in rows:
        date_value = str(row.get("日期") or "")
        try:
            return_value = float(row.get("累计收益率"))
        except (TypeError, ValueError):
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
            valid.append((date_value, return_value))
    if not valid:
        return None

    valid.sort(key=lambda item: item[0])
    latest_year = valid[-1][0][:4]
    year_start = f"{latest_year}-01-01"
    current_year = [item for item in valid if item[0] >= year_start]
    if not current_year:
        return None

    previous = [item for item in valid if item[0] < year_start]
    base_return = previous[-1][1] if previous else current_year[0][1]
    latest_return = current_year[-1][1]
    base_index = 1 + base_return / 100
    latest_index = 1 + latest_return / 100
    if base_index <= 0:
        return None
    return round((latest_index / base_index - 1) * 100, 2)


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


def _return_series_frame(
    series: dict[str, Any] | None,
    value_column: str,
) -> pd.DataFrame:
    points = (series or {}).get("data") or []
    if not points:
        return pd.DataFrame(columns=["日期", value_column])
    frame = pd.DataFrame(points, columns=["日期", value_column])
    frame["日期"] = pd.to_datetime(
        frame["日期"], unit="ms", utc=True, errors="coerce"
    ).dt.tz_convert("Asia/Shanghai").dt.date
    frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce")
    return frame.dropna(subset=["日期", value_column])


def _load_return_comparison_em(
    symbol: str,
    period: str,
) -> pd.DataFrame:
    """同时取得基金与东方财富同类平均的累计收益率曲线。"""
    period_map = {
        "1月": "m",
        "3月": "q",
        "6月": "hy",
        "1年": "y",
        "3年": "try",
        "5年": "fiy",
        "今年来": "sy",
        "成立来": "se",
    }
    response = requests.get(
        "https://api.fund.eastmoney.com/pinzhong/LJSYLZS",
        params={
            "fundCode": symbol,
            "indexcode": "000300",
            "type": period_map[period],
        },
        headers={"Referer": "https://fund.eastmoney.com/"},
        timeout=20,
    )
    response.raise_for_status()
    series = response.json().get("Data") or []
    if not series:
        return pd.DataFrame()

    fund_series = next(
        (
            item
            for item in series
            if str(item.get("name") or "") not in ("同类平均", "沪深300")
        ),
        series[0],
    )
    peer_series = next(
        (
            item
            for item in series
            if str(item.get("name") or "") == "同类平均"
        ),
        None,
    )
    fund_frame = _return_series_frame(fund_series, "累计收益率")
    peer_frame = _return_series_frame(peer_series, "同类平均")
    if fund_frame.empty or peer_frame.empty:
        return fund_frame
    return fund_frame.merge(peer_frame, on="日期", how="outer").sort_values("日期")


def _build_peer_performance(
    peer_type: Any,
    achievement: pd.DataFrame,
    return_frames: dict[str, pd.DataFrame],
    performance: dict[str, Any],
) -> dict[str, Any]:
    """整合同类平均、周期排名及相对同类差异。"""
    rank_by_period: dict[str, str] = {}
    if not achievement.empty and {
        "周期",
        "周期收益同类排名",
    }.issubset(achievement.columns):
        for _, row in achievement.iterrows():
            period = str(row.get("周期") or "").strip()
            rank = str(row.get("周期收益同类排名") or "").strip()
            if period and re.fullmatch(r"\d+\s*/\s*\d+", rank):
                rank_by_period[period] = re.sub(r"\s+", "", rank)

    range_by_period = {
        "近1月": "1m",
        "近3月": "3m",
        "近6月": "6m",
        "今年以来": "ytd",
        "近1年": "1y",
        "近3年": "3y",
        "成立以来": "all",
    }
    details: dict[str, dict[str, Any]] = {}
    for period, range_key in range_by_period.items():
        frame = return_frames.get(range_key, pd.DataFrame())
        peer_values = (
            pd.to_numeric(frame["同类平均"], errors="coerce").dropna()
            if "同类平均" in frame.columns
            else pd.Series(dtype=float)
        )
        peer_average = (
            round(float(peer_values.iloc[-1]), 4)
            if not peer_values.empty
            else None
        )
        fund_return = _finite_float(performance.get(period))
        relative_ratio = None
        excess_return = None
        if fund_return is not None and peer_average is not None:
            excess_return = round(fund_return - peer_average, 4)
            if abs(peer_average) > 1e-12:
                relative_ratio = round(
                    (fund_return - peer_average) / abs(peer_average) * 100,
                    4,
                )

        rank_text = rank_by_period.get(period)
        rank_value = None
        peer_count = None
        percentile = None
        if rank_text:
            rank_value, peer_count = (
                int(value) for value in rank_text.split("/", maxsplit=1)
            )
            if peer_count > 0:
                percentile = round(rank_value / peer_count * 100, 4)

        details[period] = {
            "同类平均": peer_average,
            "相对同类差异比例": relative_ratio,
            "超额收益": excess_return,
            "同类排名": rank_text,
            "排名": rank_value,
            "同类数量": peer_count,
            "排名分位": percentile,
        }

    return {
        "可用": any(
            row["同类平均"] is not None or row["同类排名"]
            for row in details.values()
        ),
        "同类": _clean(peer_type),
        "阶段": details,
        "相对差异口径": "（基金涨幅－同类平均）÷同类平均绝对值",
        "说明": (
            "同类由下游数据源按基金类型划分，不等同于跟踪同一指数的"
            "严格赛道；同类平均来自东方财富，同类排名来自雪球基金。"
        ),
    }


def _fallback_performance(
    code: str,
    warnings: list[str],
    unit_nav: pd.DataFrame | None = None,
    cumulative_nav: pd.DataFrame | None = None,
    achievement: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """排行接口不可用时，从单基金接口补充净值和区间业绩。"""
    performance: dict[str, Any] = {}
    net_value: dict[str, Any] = {}

    if achievement is None:
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


def get_fund_holdings_by_period(
    fund_code: str,
    period_key: str,
    holdings_limit: int | None = None,
) -> dict[str, Any]:
    """按需查询基金指定季度的公开披露持仓。"""
    code = _normalize_code(fund_code)
    year, quarter = _quarter_key(period_key)
    if holdings_limit is not None and holdings_limit <= 0:
        raise ValueError("holdings_limit 必须大于 0。")

    warnings: list[str] = []
    stock_frame = _safe_call(
        "股票持仓",
        ak.fund_portfolio_hold_em,
        warnings,
        symbol=code,
        date=str(year),
    )
    bond_frame = _safe_call(
        "债券持仓",
        ak.fund_portfolio_bond_hold_em,
        warnings,
        symbol=code,
        date=str(year),
    )
    stock_holdings, stock_period = _holdings_for_period(
        stock_frame,
        year,
        quarter,
        limit=holdings_limit,
    )
    bond_holdings, bond_period = _holdings_for_period(
        bond_frame,
        year,
        quarter,
        limit=holdings_limit,
    )

    industry_frame = (
        _safe_call(
            "股票行业配置",
            ak.fund_portfolio_industry_allocation_em,
            warnings,
            symbol=code,
            date=str(year),
        )
        if stock_holdings
        else pd.DataFrame()
    )
    industry, industry_period = _industry_allocation_for_period(
        industry_frame,
        year,
        quarter,
    )
    (
        asset_allocation,
        bond_type_structure,
        report_catalog,
        fund_holdings,
    ) = _load_portfolio_report(
        code,
        warnings,
        period_key=period_key,
    )
    bond_holdings, bond_maturity_structure = _enrich_bond_holdings(
        bond_holdings,
        bond_period,
    )
    stock_holdings, stock_valuation_summary = _enrich_stock_holdings(
        stock_holdings,
        warnings,
    )
    current_report = next(
        (
            report
            for report in report_catalog
            if report["key"] == period_key
        ),
        None,
    )
    fund_holdings_period = (
        asset_allocation.get("报告期") if fund_holdings else None
    )
    primary_holdings = fund_holdings or stock_holdings or bond_holdings
    period_label = f"{year}年第{quarter}季度"
    return {
        "季度Key": period_key,
        "报告期": period_label,
        "数量": len(stock_holdings) + len(bond_holdings) + len(fund_holdings),
        "资产分布": asset_allocation,
        "资产分类": [
            asset_type
            for asset_type, rows in (
                ("股票", stock_holdings),
                ("债券", bond_holdings),
                ("基金", fund_holdings),
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
            "报告期": stock_period or period_label,
            "数量": len(stock_holdings),
            "明细": stock_holdings,
            "估值概览": stock_valuation_summary,
        },
        "债券持仓": {
            "报告期": bond_period or period_label,
            "数量": len(bond_holdings),
            "明细": bond_holdings,
            "品种结构": bond_type_structure,
            "期限结构": bond_maturity_structure,
        },
        "基金投资": _fund_investment_group(
            fund_holdings,
            fund_holdings_period or period_label,
        ),
        "板块配置": {
            "可用": bool(industry),
            "口径": "基金定期报告中的股票行业配置",
            "报告期": industry_period or period_label,
            "数量": len(industry),
            "明细": industry,
            "说明": (
                "板块数据来自基金指定季度的定期报告披露。"
                if industry
                else "该季度暂无可用的股票行业配置。"
            ),
        },
        "季报列表": report_catalog,
        "当前季报": current_report,
        "提示": warnings,
    }


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
    achievement_frame = _safe_call(
        "单基金阶段业绩",
        ak.fund_individual_achievement_xq,
        warnings,
        symbol=code,
    )

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
        "今年以来": _pick(
            rank_row.get("今年来"),
            rank_row.get("今年以来"),
        ),
        "近1年": _pick(rank_row.get("近1年")),
        "近3年": _pick(rank_row.get("近3年")),
        "单位": "%",
    }

    nav_requests: dict[str, dict[str, Any]] = {
        "单位净值": {"indicator": "单位净值走势"},
        "累计净值": {"indicator": "累计净值走势"},
        "分红": {"indicator": "分红送配详情"},
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
    return_periods = {
        "all": "成立来",
        "5y": "5年",
        "3y": "3年",
        "1y": "1年",
        "6m": "6月",
        "3m": "3月",
        "1m": "1月",
        "ytd": "今年来",
    }
    return_frames = {
        range_key: _safe_call(
            f"历史收益_{range_key}",
            _load_return_comparison_em,
            warnings,
            symbol=code,
            period=period,
        )
        for range_key, period in return_periods.items()
    }
    nav_frames.update(
        {
            f"收益_{range_key}": frame
            for range_key, frame in return_frames.items()
        }
    )

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
            achievement=achievement_frame,
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

    if performance.get("今年以来") is None:
        performance["今年以来"] = _year_to_date_return(
            cumulative_returns.get("1y")
            or cumulative_returns.get("all")
            or []
        )

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
    (
        asset_allocation,
        bond_type_structure,
        quarter_reports,
        fund_holdings,
    ) = _load_portfolio_report(code, warnings)
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

    stock_holdings, stock_valuation_summary = _enrich_stock_holdings(
        stock_holdings,
        warnings,
    )
    target_etf_holdings, target_etf_valuation_summary = _enrich_stock_holdings(
        target_etf_holdings,
        warnings,
    )
    target_etf_row = _first_row(target_etf_overview)
    target_etf_name = _pick(
        target_etf_row.get("基金简称"),
        target_etf_row.get("基金全称"),
    )
    fund_holdings_period = (
        asset_allocation.get("报告期") if fund_holdings else None
    )
    primary_holdings = fund_holdings or stock_holdings or bond_holdings
    primary_period = (
        fund_holdings_period or stock_holdings_period or bond_holdings_period
    )

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
    peer_performance = _build_peer_performance(
        xq.get("基金类型") or basic["类型"],
        achievement_frame,
        return_frames,
        performance,
    )

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
        "同类表现": peer_performance,
        "赛道基准建议": recommend_track_benchmark(
            str(basic["名称"] or ""),
            str(basic["类型"] or ""),
            bond_type_structure.get("明细", []),
            performance_benchmark=str(basic["业绩比较基准"] or ""),
        ),
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
            "季度Key": _quarter_key_from_period(primary_period),
            "报告期": primary_period,
            "数量": (
                len(stock_holdings) + len(bond_holdings) + len(fund_holdings)
            ),
            "资产分布": asset_allocation,
            "季报列表": quarter_reports,
            "当前季报": next(
                (
                    report
                    for report in quarter_reports
                    if report["key"]
                    == _quarter_key_from_period(primary_period)
                ),
                None,
            ),
            "资产分类": [
                asset_type
                for asset_type, rows in (
                    ("股票", stock_holdings),
                    ("债券", bond_holdings),
                    ("基金", fund_holdings),
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
                "估值概览": stock_valuation_summary,
            },
            "债券持仓": {
                "报告期": bond_holdings_period,
                "数量": len(bond_holdings),
                "明细": bond_holdings,
                "品种结构": bond_type_structure,
                "期限结构": bond_maturity_structure,
            },
            "基金投资": _fund_investment_group(
                fund_holdings,
                fund_holdings_period,
            ),
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
                "估值概览": target_etf_valuation_summary,
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
            "同类表现": (
                "东方财富同类平均累计收益率 + "
                "AKShare.fund_individual_achievement_xq 同类排名"
            ),
            "持仓": [
                "AKShare.fund_portfolio_hold_em",
                "AKShare.fund_portfolio_bond_hold_em",
                "AKShare.fund_portfolio_industry_allocation_em",
                "AKShare.fund_announcement_report_em + 最新季度报告 PDF",
                "AKShare.bond_info_detail_cm（中国货币网债券详情）",
                "巨潮资讯/东方财富个股行业与估值、AKShare/Sina 股票分红及新浪批量行情",
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
