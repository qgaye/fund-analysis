"""查询 A 股基础资料、估值指标与前复权收盘价历史。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import akshare as ak
import pandas as pd

from fund_lookup import (
    _clean,
    _finite_float,
    _item_value_map,
    _load_stock_fundamentals,
    _load_stock_quotes,
)


class StockLookupError(RuntimeError):
    """股票资料不可用。"""


def _normalize_stock_code(stock_code: str) -> str:
    code = str(stock_code).strip()
    if len(code) != 6 or not code.isdigit():
        raise ValueError("股票代码必须是 6 位数字，例如 600519。")
    return code


def _stock_market(code: str) -> str:
    if code.startswith(("4", "8", "92")):
        return "北京证券交易所"
    if code.startswith(("5", "6", "9")):
        return "上海证券交易所"
    return "深圳证券交易所"


def _date_text(value: Any) -> str | None:
    if value is None or str(value).strip() in {"", "nan", "None", "--"}:
        return None
    raw = str(value).strip()
    if raw.isdigit() and len(raw) == 8:
        try:
            return datetime.strptime(raw, "%Y%m%d").date().isoformat()
        except ValueError:
            pass
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date().isoformat()


def _stock_price_history(
    code: str,
    listed_date: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    start_date = (listed_date or "1990-01-01").replace("-", "")
    end_date = date.today().strftime("%Y%m%d")
    fallback_note = None
    source = "eastmoney"
    try:
        frame = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
        if frame is None or frame.empty:
            raise ValueError("东方财富历史行情为空")
    except Exception:
        source = "tencent"
        market_prefix = "bj" if code.startswith(("4", "8", "92")) else (
            "sh" if code.startswith(("5", "6", "9")) else "sz"
        )
        frame = ak.stock_zh_a_hist_tx(
            symbol=f"{market_prefix}{code}",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
            timeout=10,
        )
        fallback_note = "东方财富历史行情不可用，已切换腾讯证券备用源。"
    if frame is None or frame.empty:
        return [], "未取得该股票的历史收盘价。"
    date_column = "日期" if "日期" in frame.columns else "date"
    close_column = "收盘" if "收盘" in frame.columns else "close"
    turnover_column = "换手率" if "换手率" in frame.columns else "turnover"
    change_column = "涨跌幅" if "涨跌幅" in frame.columns else None
    if not {date_column, close_column}.issubset(frame.columns):
        return [], "历史行情缺少日期或收盘价字段。"

    selected = frame.copy()
    selected["_日期"] = pd.to_datetime(
        selected[date_column],
        errors="coerce",
    )
    selected["_收盘"] = pd.to_numeric(
        selected[close_column],
        errors="coerce",
    )
    if turnover_column in selected:
        selected["_换手率"] = pd.to_numeric(
            selected[turnover_column],
            errors="coerce",
        )
        if source == "tencent":
            selected["_换手率"] *= 100
    selected = (
        selected.dropna(subset=["_日期", "_收盘"])
        .sort_values("_日期")
        .drop_duplicates(subset=["_日期"], keep="last")
    )

    rows: list[dict[str, Any]] = []
    for _, row in selected.iterrows():
        item: dict[str, Any] = {
            "日期": row["_日期"].date().isoformat(),
            "收盘": round(float(row["_收盘"]), 4),
        }
        turnover = _finite_float(row.get("_换手率"))
        if turnover is not None:
            item["换手率"] = round(turnover, 4)
        change = _finite_float(row.get(change_column)) if change_column else None
        if change is not None:
            item["涨跌幅"] = round(change, 4)
        rows.append(item)
    return rows, fallback_note


def get_stock_data(stock_code: str) -> dict[str, Any]:
    """返回一只 A 股的资料、当前指标和完整收盘价趋势。"""
    code = _normalize_stock_code(stock_code)
    warnings: list[str] = []

    info: dict[str, Any] = {}
    try:
        info_frame = ak.stock_individual_info_em(symbol=code, timeout=10)
        info = _item_value_map(info_frame)
    except Exception:
        warnings.append("股票基础资料暂不可用，已展示其他公开数据。")

    listed_date = _date_text(
        info.get("上市时间")
        or info.get("上市日期")
    )

    try:
        quotes = _load_stock_quotes([code])
    except Exception:
        quotes = {}
        warnings.append("新浪最新行情暂不可用，价格将使用最新收盘价。")

    metrics = _load_stock_fundamentals(code, quotes.get(code))
    if metrics.get("_行业错误"):
        warnings.append("所属行业暂不可用。")
    if metrics.get("_估值错误"):
        warnings.append("PE/PB 暂不可用。")
    if metrics.get("_分红错误"):
        warnings.append("分红数据暂不可用。")

    try:
        history, history_warning = _stock_price_history(code, listed_date)
        if history_warning:
            warnings.append(history_warning)
    except Exception:
        history = []
        warnings.append("历史行情暂不可用。")

    latest_history = history[-1] if history else {}
    latest_price = _finite_float(metrics.get("最新价"))
    if latest_price is None:
        latest_price = _finite_float(latest_history.get("收盘"))
    quote_date = metrics.get("行情日期") or latest_history.get("日期")

    name = (
        info.get("股票简称")
        or info.get("股票名称")
        or info.get("证券简称")
        or quotes.get(code, {}).get("名称")
    )
    industry = metrics.get("所属行业") or info.get("行业")
    if not name and not history and not metrics.get("估值可用"):
        details = "；".join(warnings[-3:]) or "上游未返回数据"
        raise StockLookupError(f"未找到股票 {code}：{details}")

    latest_turnover = _finite_float(latest_history.get("换手率"))
    latest_change = _finite_float(latest_history.get("涨跌幅"))
    if latest_change is None and len(history) >= 2:
        previous_close = _finite_float(history[-2].get("收盘"))
        latest_close = _finite_float(history[-1].get("收盘"))
        if (
            previous_close is not None
            and previous_close > 0
            and latest_close is not None
        ):
            latest_change = (latest_close / previous_close - 1) * 100
    fundamental_values = {
        key: (
            round(value, 4)
            if (value := _finite_float(metrics.get(key))) is not None
            else None
        )
        for key in ("PE", "PB", "ROE", "股息率")
    }
    fundamental_values["换手率"] = (
        round(latest_turnover, 4)
        if latest_turnover is not None
        else None
    )

    return {
        "基础信息": {
            "名称": _clean(name),
            "代码": code,
            "行业": _clean(industry),
            "市场": _stock_market(code),
            "上市日期": listed_date,
        },
        "行情": {
            "最新价": (
                round(latest_price, 4)
                if latest_price is not None
                else None
            ),
            "行情日期": quote_date,
            "涨跌幅": (
                round(latest_change, 4)
                if latest_change is not None
                else None
            ),
        },
        "指标": {
            **fundamental_values,
            "说明": (
                "PE 为 TTM、PB 为 MRQ；ROE 按 PB÷PE 推算；"
                "股息率按近 12 个月已除息现金分红÷最新价计算；"
                "换手率为最新可用交易日数据。"
            ),
        },
        "价格趋势": {
            "复权方式": "前复权",
            "起始日": history[0]["日期"] if history else None,
            "结束日": history[-1]["日期"] if history else None,
            "数量": len(history),
            "明细": history,
        },
        "数据来源": [
            "AKShare.stock_individual_info_em（东方财富）",
            "AKShare.stock_profile_cninfo（巨潮资讯，行业）",
            "AKShare.stock_zh_valuation_comparison_em（东方财富估值）",
            "AKShare.stock_history_dividend_detail（现金分红）",
            "AKShare.stock_zh_a_hist（东方财富前复权日线）",
            "AKShare.stock_zh_a_hist_tx（腾讯证券备用日线）",
            "新浪财经批量行情",
        ],
        "查询时间": datetime.now().astimezone().isoformat(timespec="seconds"),
        "提示": warnings,
    }
