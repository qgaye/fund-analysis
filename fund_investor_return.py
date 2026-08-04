"""基金“持有人收益率”（金额加权 / 投资者收益率）计算。

背景
----
基金公布的收益率是 **时间加权收益率（TWR）**，衡量基金本身业绩，与申赎
时点无关；而 **持有人收益率** 是把全体持有人的申购、赎回现金流按发生时点
纳入计算得到的 **金额加权收益率（XIRR / 内部收益率）**，衡量“买这只基金的
人实际赚到没有”。由于追涨杀跌，持有人收益率通常低于基金净值收益率，二者
之差即 **行为差距（Behavior Gap）**。

数据来源
--------
现金流来自每期定期报告“开放式基金份额变动”表：报告期期初份额、期间总申购
份额、期间总赎回份额、报告期期末份额。季报每季度披露一次，覆盖最全，因此
以季报为基础重建现金流序列。估值统一使用 **累计净值（复权）**，使持有人侧与
基金净值侧口径一致，避免分红造成的口径偏差。

设计
----
* :func:`build_quarterly_series` 是耗时的“承接”方法：需要逐份下载季报 PDF，
  因此支持传入已缓存的季度序列做 **增量更新**——只下载尚未收录的新季度。
* 季度序列保留季度维度的全部原始与派生指标（份额变化、累计净值、单季持有人
  收益率与净值收益率）。
* :func:`summarize_windows` 在季度序列之上聚合出近 1 年 / 3 年 / 5 年 /
  成立以来的持有人收益率、净值收益率与行为差距，不再触发任何网络请求。
"""

from __future__ import annotations

import io
import re
from datetime import date, timedelta
from typing import Any, Callable, Iterable

import akshare as ak
import pandas as pd
import requests
from pypdf import PdfReader


# 各窗口对应的回溯年数；None 表示成立以来（全区间）。
_WINDOWS: dict[str, int | None] = {
    "近1年": 1,
    "近3年": 3,
    "近5年": 5,
    "成立以来": None,
}

_PDF_URL = "https://pdf.dfcfw.com/pdf/H2_{report_id}_1.pdf"
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
_QUARTER_START = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}


def _to_float(text: str) -> float:
    return float(text.replace(",", ""))


def _quarter_reports(reports: pd.DataFrame) -> list[dict[str, Any]]:
    """从公告列表筛出季度报告正文，按报告期升序返回其 key / 期末日期 / ID。"""
    required = {"公告标题", "报告ID"}
    if reports.empty or not required.issubset(reports.columns):
        return []

    quarter_map = {"一": "1", "二": "2", "三": "3", "四": "4"}
    pattern = re.compile(
        r"(?P<year>20\d{2})年第?(?P<quarter>[一二三四1-4])季度报告\s*$"
    )
    seen: dict[str, dict[str, Any]] = {}
    for _, row in reports.iterrows():
        title = str(row.get("公告标题") or "").strip()
        report_id = str(row.get("报告ID") or "").strip()
        if "摘要" in title or not re.fullmatch(r"AN\d+", report_id):
            continue
        matched = pattern.search(title)
        if not matched:
            continue
        year = int(matched.group("year"))
        quarter = int(
            quarter_map.get(matched.group("quarter"), matched.group("quarter"))
        )
        key = f"{year}Q{quarter}"
        month, day = _QUARTER_END[quarter]
        start_month, start_day = _QUARTER_START[quarter]
        # 同一报告期可能有更正版，保留公告最新的一份。
        existing = seen.get(key)
        announced = str(row.get("公告日期") or "")
        if existing is not None and announced < existing["_公告日期"]:
            continue
        seen[key] = {
            "key": key,
            "年度": year,
            "季度": quarter,
            "报告期": f"{year}年第{quarter}季度",
            "期初日期": date(year, start_month, start_day).isoformat(),
            "期末日期": date(year, month, day).isoformat(),
            "报告ID": report_id,
            "_公告日期": announced,
        }
    return sorted(seen.values(), key=lambda item: item["期末日期"])


def _parse_share_change(report_text: str) -> dict[str, float | None]:
    """解析“开放式基金份额变动”表的首列（主份额）四项份额。"""
    anchor = report_text.find("开放式基金份额变动")
    section = report_text[anchor : anchor + 800] if anchor >= 0 else ""

    def grab(label: str) -> float | None:
        matched = re.search(
            label + r"[^\d\-]*(-?[\d,]+\.\d+)",
            section,
        )
        return _to_float(matched.group(1)) if matched else None

    return {
        "期初份额": grab("报告期期初基金份额总额"),
        "申购份额": grab("报告期期间基金总申购份额"),
        "赎回份额": grab("报告期期间基金总赎回份额"),
        "期末份额": grab("报告期期末基金份额总额"),
    }


def _fetch_report_text(report_id: str, *, timeout: int = 30) -> str:
    response = requests.get(
        _PDF_URL.format(report_id=report_id),
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=timeout,
    )
    response.raise_for_status()
    return "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(response.content)).pages
    )


def _fill_share_gaps(records: list[dict[str, Any]]) -> None:
    """借助恒等式补全 PDF 偶发漏解析的单元格（就地修改）。

    利用两条关系：同一季 期初+申购-赎回=期末；相邻季 上期末=下期初。
    多轮传播直到不再有新值补出。
    """
    for _ in range(3):
        changed = False
        for index, record in enumerate(records):
            begin = record.get("期初份额")
            subscribe = record.get("申购份额")
            redeem = record.get("赎回份额")
            end = record.get("期末份额")
            if begin is None and index > 0:
                begin = records[index - 1].get("期末份额")
            if end is None and index + 1 < len(records):
                end = records[index + 1].get("期初份额")
            if (
                end is None
                and None not in (begin, subscribe, redeem)
            ):
                end = begin + subscribe - redeem
            if (
                redeem is None
                and None not in (begin, subscribe, end)
            ):
                redeem = begin + subscribe - end
            if (
                subscribe is None
                and None not in (begin, redeem, end)
            ):
                subscribe = end - begin + redeem
            if (
                begin is None
                and None not in (subscribe, redeem, end)
            ):
                begin = end - subscribe + redeem
            updated = {
                "期初份额": begin,
                "申购份额": subscribe,
                "赎回份额": redeem,
                "期末份额": end,
            }
            if updated != {k: record.get(k) for k in updated}:
                record.update(updated)
                changed = True
        if not changed:
            break


class _NavSeries:
    """累计净值（复权）序列，支持按日期取“最近可用净值”。"""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._dates: list[str] = []
        self._values: list[float] = []
        if (
            not frame.empty
            and {"净值日期", "累计净值"}.issubset(frame.columns)
        ):
            ordered = frame.dropna(subset=["累计净值"]).copy()
            ordered["净值日期"] = ordered["净值日期"].astype(str)
            ordered = ordered.sort_values("净值日期")
            self._dates = ordered["净值日期"].tolist()
            self._values = [float(value) for value in ordered["累计净值"]]

    def __bool__(self) -> bool:
        return bool(self._dates)

    def as_of(self, target: str) -> float | None:
        """返回不晚于 target 的最近一个累计净值。"""
        import bisect

        if not self._dates:
            return None
        index = bisect.bisect_right(self._dates, target) - 1
        if index < 0:
            return None
        return self._values[index]

    @property
    def latest_date(self) -> str | None:
        return self._dates[-1] if self._dates else None


def _modified_dietz(
    begin_value: float,
    end_value: float,
    net_flow: float,
) -> float | None:
    """单季持有人收益率（修正 Dietz），假设净流量发生在季度中点。"""
    denominator = begin_value + 0.5 * net_flow
    if denominator <= 0:
        return None
    return (end_value - begin_value - net_flow) / denominator


def build_quarterly_series(
    code: str,
    *,
    existing: Iterable[dict[str, Any]] | None = None,
    reports: pd.DataFrame | None = None,
    safe_call: Callable[..., pd.DataFrame] | None = None,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """构建并维护季度维度的持有人收益率基础序列（耗时的承接方法）。

    参数:
        code: 六位基金代码。
        existing: 已缓存的季度序列；只会下载其中缺失的新季度 PDF，实现增量更新。
        reports: 预取的公告报告 DataFrame；缺省时内部调用 AKShare。
        safe_call: 复用调用方的容错包装（如 fund_lookup._safe_call）。
        warnings: 收集告警信息的列表。

    返回:
        按报告期升序排列的季度记录列表，每条含份额变化、累计净值与单季收益率。
    """
    warnings = warnings if warnings is not None else []

    def _call(label: str, func: Callable[..., pd.DataFrame], **kwargs: Any):
        if safe_call is not None:
            return safe_call(label, func, warnings, **kwargs)
        try:
            result = func(**kwargs)
            return result if result is not None else pd.DataFrame()
        except Exception as exc:  # noqa: BLE001 - 上游异常种类不固定
            warnings.append(f"{label}获取失败：{exc}")
            return pd.DataFrame()

    if reports is None:
        reports = _call(
            "基金定期报告", ak.fund_announcement_report_em, symbol=code
        )
    quarter_reports = _quarter_reports(reports)
    if not quarter_reports:
        return []

    # 增量承接：已收录且份额四项齐全的季度直接复用，仅下载新增季度的 PDF。
    cached: dict[str, dict[str, Any]] = {}
    for item in existing or []:
        key = str(item.get("季度Key") or item.get("key") or "")
        if key:
            cached[key] = item

    records: list[dict[str, Any]] = []
    for report in quarter_reports:
        key = report["key"]
        prior = cached.get(key)
        if prior is not None and prior.get("_份额齐全"):
            shares = {
                "期初份额": prior.get("期初份额"),
                "申购份额": prior.get("申购份额"),
                "赎回份额": prior.get("赎回份额"),
                "期末份额": prior.get("期末份额"),
            }
        else:
            try:
                text = _fetch_report_text(report["报告ID"])
                shares = _parse_share_change(text)
            except Exception as exc:  # noqa: BLE001
                warnings.append(
                    f"{report['报告期']}份额变动解析失败：{exc}"
                )
                shares = {
                    "期初份额": None,
                    "申购份额": None,
                    "赎回份额": None,
                    "期末份额": None,
                }
        records.append(
            {
                "季度Key": key,
                "报告期": report["报告期"],
                "年度": report["年度"],
                "季度": report["季度"],
                "期初日期": report["期初日期"],
                "期末日期": report["期末日期"],
                "报告ID": report["报告ID"],
                **shares,
            }
        )

    _fill_share_gaps(records)

    nav = _NavSeries(
        _call(
            "累计净值",
            ak.fund_open_fund_info_em,
            symbol=code,
            indicator="累计净值走势",
        )
    )

    for record in records:
        begin_nav = nav.as_of(record["期初日期"]) if nav else None
        end_nav = nav.as_of(record["期末日期"]) if nav else None
        begin_share = record.get("期初份额")
        end_share = record.get("期末份额")
        subscribe = record.get("申购份额")
        redeem = record.get("赎回份额")
        net_flow_share = (
            subscribe - redeem
            if None not in (subscribe, redeem)
            else None
        )

        begin_value = (
            begin_share * begin_nav
            if None not in (begin_share, begin_nav)
            else None
        )
        end_value = (
            end_share * end_nav
            if None not in (end_share, end_nav)
            else None
        )
        net_flow_value = (
            net_flow_share * end_nav
            if None not in (net_flow_share, end_nav)
            else None
        )

        nav_return = (
            end_nav / begin_nav - 1
            if None not in (begin_nav, end_nav) and begin_nav
            else None
        )
        holder_return = (
            _modified_dietz(begin_value, end_value, net_flow_value)
            if None not in (begin_value, end_value, net_flow_value)
            else None
        )

        record.update(
            {
                "期初累计净值": begin_nav,
                "期末累计净值": end_nav,
                "净申赎份额": net_flow_share,
                "期末市值": end_value,
                "单季净值收益率": (
                    round(nav_return, 6) if nav_return is not None else None
                ),
                "单季持有人收益率": (
                    round(holder_return, 6)
                    if holder_return is not None
                    else None
                ),
                "_份额齐全": None
                not in (begin_share, subscribe, redeem, end_share),
            }
        )

    return records


def _xnpv(rate: float, flows: list[tuple[date, float]]) -> float:
    origin = flows[0][0]
    return sum(
        amount / ((1 + rate) ** ((when - origin).days / 365.0))
        for when, amount in flows
    )


def _xirr(flows: list[tuple[date, float]]) -> float | None:
    """二分法求解 XIRR；无符号变化或无解时返回 None。"""
    if len(flows) < 2:
        return None
    if not (
        any(amount > 0 for _, amount in flows)
        and any(amount < 0 for _, amount in flows)
    ):
        return None
    low, high = -0.9999, 10.0
    f_low = _xnpv(low, flows)
    f_high = _xnpv(high, flows)
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = _xnpv(mid, flows)
        if abs(f_mid) < 1e-4:
            return mid
        if f_low * f_mid < 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2


def _annualize(total_return: float, days: int) -> float | None:
    if days <= 0 or total_return <= -1:
        return None
    return (1 + total_return) ** (365.0 / days) - 1


def _pct(value: float | None, digits: int = 2) -> float | None:
    return round(value * 100, digits) if value is not None else None


def _summarize_one(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """对一段连续季度序列计算持有人收益率 / 净值收益率 / 行为差距。"""
    usable = [
        record
        for record in records
        if record.get("期初累计净值")
        and record.get("期末累计净值")
        and record.get("期初份额") is not None
        and record.get("净申赎份额") is not None
        and record.get("期末份额") is not None
    ]
    if len(usable) < 1:
        return None

    first, last = usable[0], usable[-1]
    start_date = date.fromisoformat(first["期初日期"])
    end_date = date.fromisoformat(last["期末日期"])
    days = (end_date - start_date).days
    if days <= 0:
        return None

    begin_value = first["期初份额"] * first["期初累计净值"]
    flows: list[tuple[date, float]] = [(start_date, -begin_value)]
    for record in usable:
        flow_value = record["净申赎份额"] * record["期末累计净值"]
        flows.append((date.fromisoformat(record["期末日期"]), -flow_value))
    flows.append((end_date, last["期末份额"] * last["期末累计净值"]))

    holder_annual = _xirr(flows)
    holder_cumulative = (
        (1 + holder_annual) ** (days / 365.0) - 1
        if holder_annual is not None
        else None
    )

    nav_cumulative = last["期末累计净值"] / first["期初累计净值"] - 1
    nav_annual = _annualize(nav_cumulative, days)

    gap_annual = (
        holder_annual - nav_annual
        if None not in (holder_annual, nav_annual)
        else None
    )

    begin_share = first["期初份额"]
    end_share = last["期末份额"]
    # 区间内持有人的净申购/赎回（各季净申赎份额加总），反映申赎行为本身，
    # 不含基金规模的自然增长；相对期初份额取比例便于横向比较。
    net_flow_share = sum(
        record["净申赎份额"] for record in usable
    )
    net_flow_ratio = (
        net_flow_share / begin_share if begin_share else None
    )

    return {
        "起始日期": first["期初日期"],
        "结束日期": last["期末日期"],
        "起始报告期": first["报告期"],
        "结束报告期": last["报告期"],
        "季度数": len(usable),
        "持有人收益率": {
            "年化": _pct(holder_annual),
            "累计": _pct(holder_cumulative),
        },
        "基金净值收益率": {
            "年化": _pct(nav_annual),
            "累计": _pct(nav_cumulative),
        },
        "行为差距": {
            "年化": _pct(gap_annual),
            "口径": "持有人收益率 − 基金净值收益率（均为年化）",
        },
        "份额变化": {
            "期初份额": begin_share,
            "期末份额": end_share,
            "净申赎份额": net_flow_share,
            "净申赎比例": _pct(net_flow_ratio),
            "口径": "区间各季净申赎份额加总（申购−赎回），相对期初份额取比例；正为净申购、负为净赎回",
        },
    }


def summarize_windows(
    series: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """在季度序列之上聚合近 1 年 / 3 年 / 5 年 / 成立以来的口径（不触网）。"""
    ordered = sorted(
        (record for record in series if record.get("期末日期")),
        key=lambda item: item["期末日期"],
    )
    result: dict[str, Any] = {}
    if not ordered:
        return {window: None for window in _WINDOWS}

    reference = as_of or date.fromisoformat(ordered[-1]["期末日期"])
    inception = date.fromisoformat(ordered[0]["期初日期"])
    for window, years in _WINDOWS.items():
        if years is None:
            subset = ordered
        else:
            # 基金存续不足窗口年限时，该区间与“成立以来”完全重合，直接不展示。
            if inception > reference - timedelta(days=365 * years):
                result[window] = None
                continue
            cutoff = (reference - timedelta(days=365 * years)).isoformat()
            # 取起点“期初”不早于窗口下界的季度；至少纳入最近一季。
            subset = [
                record
                for record in ordered
                if record.get("期初日期", "") >= cutoff
            ]
        result[window] = _summarize_one(subset) if subset else None
    return result


def compute_investor_return(
    code: str,
    *,
    existing: Iterable[dict[str, Any]] | None = None,
    reports: pd.DataFrame | None = None,
    safe_call: Callable[..., pd.DataFrame] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """一站式：构建季度序列并聚合各窗口，返回适合 JSON 输出的结构。"""
    warnings = warnings if warnings is not None else []
    series = build_quarterly_series(
        code,
        existing=existing,
        reports=reports,
        safe_call=safe_call,
        warnings=warnings,
    )
    windows = summarize_windows(series)
    return {
        "可用": bool(series),
        "口径": "金额加权收益率（XIRR），估值统一采用累计净值（复权）",
        "数据来源": "季度报告“开放式基金份额变动”表 + 累计净值走势",
        "季度序列": series,
        "区间汇总": windows,
        "说明": (
            "持有人收益率按全体持有人现金流的内部收益率计算，"
            "反映投资者实际回报；与基金净值收益率（时间加权）之差即行为差距。"
            "申赎按季度净额、发生于季末近似处理。"
        ),
        "提示": warnings,
    }
