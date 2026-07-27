"""基于缓存的基金 payload 计算 AI 友好的一键复制摘要。

所有数据均来自 FundFileCache 缓存的 payload，不再查询下游。
回撤分析与年周期涨幅算法与前端 static/app.js 保持一致。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


# 阶段涨幅：展示标签 -> 历史业绩字段
_STAGE_KEYS = [
    ("近1月", "近1月"),
    ("近3月", "近3月"),
    ("近6月", "近6月"),
    ("今年以来", "今年以来"),
    ("近1年", "近1年"),
    ("近3年", "近3年"),
    ("成立以来", "成立以来"),
]

# 回撤区间：展示标签 -> 累计收益率区间 key（今年以来单独处理）
_DRAWDOWN_RANGES = [
    ("近1月", "1m"),
    ("近3月", "3m"),
    ("近6月", "6m"),
    ("今年以来", "ytd"),
    ("近1年", "1y"),
    ("近3年", "3y"),
    ("成立以来", "all"),
]


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:  # NaN
        return None
    return numeric


def _fmt_pct(value: Any) -> str:
    numeric = _num(value)
    if numeric is None:
        return "—"
    sign = "+" if numeric > 0 else ""
    return f"{sign}{numeric:.2f}%"


def _fmt_ratio(value: Any) -> str:
    """占比类数值不带正负号。"""
    numeric = _num(value)
    if numeric is None:
        return "—"
    return f"{numeric:.2f}%"


def _fmt_value(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _days_between(start: str, end: str) -> int:
    try:
        start_date = datetime.strptime(start[:10], "%Y-%m-%d")
        end_date = datetime.strptime(end[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return 0
    return max(0, (end_date - start_date).days)


def _analyze_drawdown(return_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """移植前端 analyzeDrawdownRows：计算最大回撤与修复天数。"""
    selected: list[dict[str, Any]] = []
    for row in return_rows:
        date = row.get("日期")
        ret = _num(row.get("累计收益率"))
        if date and ret is not None:
            selected.append({"日期": str(date), "累计收益率": ret})
    selected.sort(key=lambda item: item["日期"])

    if not selected:
        return {
            "maxDrawdown": 0.0,
            "recoveryDays": None,
            "elapsedRecoveryDays": None,
            "peakDate": None,
            "troughDate": None,
            "recoveryDate": None,
        }

    running_peak = 1 + selected[0]["累计收益率"] / 100
    running_peak_index = 0
    max_drawdown = 0.0
    max_peak_index = 0
    trough_index = 0
    max_peak_value = running_peak

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(selected):
        return_index = 1 + row["累计收益率"] / 100
        if return_index > running_peak:
            running_peak = return_index
            running_peak_index = index
        drawdown = (
            (return_index / running_peak - 1) * 100 if running_peak > 0 else 0.0
        )
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_peak_index = running_peak_index
            trough_index = index
            max_peak_value = running_peak
        rows.append({"日期": row["日期"], "收益指数": return_index})

    recovery_index: int | None = None
    if max_drawdown < -0.000001:
        for index in range(trough_index + 1, len(rows)):
            if rows[index]["收益指数"] >= max_peak_value * (1 - 1e-10):
                recovery_index = index
                break

    recovery_days = (
        None
        if recovery_index is None
        else _days_between(rows[trough_index]["日期"], rows[recovery_index]["日期"])
    )
    elapsed_recovery_days = (
        _days_between(rows[trough_index]["日期"], rows[-1]["日期"])
        if max_drawdown < -0.000001 and recovery_index is None
        else None
    )

    return {
        "maxDrawdown": max_drawdown,
        "recoveryDays": recovery_days,
        "elapsedRecoveryDays": elapsed_recovery_days,
        "peakDate": rows[max_peak_index]["日期"],
        "troughDate": rows[trough_index]["日期"],
        "recoveryDate": (
            rows[recovery_index]["日期"] if recovery_index is not None else None
        ),
    }


def _rebase_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把区间首个累计收益率视为 0，衔接跨期收益。"""
    cleaned = [
        {"日期": str(row.get("日期")), "累计收益率": _num(row.get("累计收益率"))}
        for row in rows
        if row.get("日期") and _num(row.get("累计收益率")) is not None
    ]
    if len(cleaned) < 2:
        return []
    base_index = 1 + cleaned[0]["累计收益率"] / 100
    if base_index <= 0:
        return []
    return [
        {
            "日期": row["日期"],
            "累计收益率": ((1 + row["累计收益率"] / 100) / base_index - 1) * 100,
        }
        for row in cleaned
    ]


def _return_rows_for_range(nav_curve: dict[str, Any], range_key: str) -> list[dict[str, Any]]:
    """取指定区间的累计收益率序列，缺失时用单位净值首日归零降级。"""
    intervals = ((nav_curve.get("累计收益率") or {}).get("区间")) or {}

    if range_key == "ytd":
        source = intervals.get("all") or intervals.get("1y") or []
        if source:
            latest = source[-1].get("日期")
            if latest:
                year_start = f"{str(latest)[:4]}-01-01"
                filtered = [
                    row for row in source if str(row.get("日期")) >= year_start
                ]
                rebased = _rebase_rows(filtered)
                if len(rebased) >= 2:
                    return rebased
        return []

    rows = intervals.get(range_key) or []
    if len(rows) >= 2:
        return [
            {"日期": row.get("日期"), "累计收益率": row.get("累计收益率")}
            for row in rows
        ]

    # 降级：单位净值首日归零。
    unit_rows = ((nav_curve.get("单位净值") or {}).get("明细")) or []
    filtered = _filter_unit_rows(unit_rows, range_key)
    if len(filtered) >= 2:
        base = _num(filtered[0].get("单位净值"))
        if base and base > 0:
            return [
                {
                    "日期": row.get("日期"),
                    "累计收益率": (_num(row.get("单位净值")) / base - 1) * 100,
                }
                for row in filtered
                if _num(row.get("单位净值")) is not None
            ]
    return []


def _filter_unit_rows(rows: list[dict[str, Any]], range_key: str) -> list[dict[str, Any]]:
    if not rows or range_key == "all":
        return rows
    latest = rows[-1].get("日期")
    if not latest:
        return rows
    try:
        latest_date = datetime.strptime(str(latest)[:10], "%Y-%m-%d")
    except ValueError:
        return rows
    months = {"1m": 1, "3m": 3, "6m": 6}
    years = {"1y": 1, "3y": 3, "5y": 5}
    if range_key in months:
        cutoff = _shift_months(latest_date, -months[range_key])
    elif range_key in years:
        cutoff = latest_date.replace(year=latest_date.year - years[range_key])
    else:
        return rows
    cutoff_iso = cutoff.strftime("%Y-%m-%d")
    return [row for row in rows if str(row.get("日期")) >= cutoff_iso]


def _shift_months(value: datetime, delta_months: int) -> datetime:
    month_index = value.month - 1 + delta_months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, 28)
    return value.replace(year=year, month=month, day=day)


def _compute_annual_returns(nav_curve: dict[str, Any]) -> list[dict[str, Any]]:
    """移植前端 computePeriodicReturns('year')：按自然年计算独立涨跌幅。"""
    rows: list[dict[str, Any]] = []
    for row in ((nav_curve.get("累计净值") or {}).get("明细")) or []:
        date = row.get("日期")
        value = _num(row.get("累计净值"))
        if date and value is not None:
            rows.append({"日期": str(date), "value": value})
    rows.sort(key=lambda item: item["日期"])
    if len(rows) < 2:
        return []

    buckets: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for row in rows:
        key = row["日期"][:4]
        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = {"key": key, "first": row, "last": row}
            ordered_keys.append(key)
        else:
            bucket["last"] = row

    ordered = [buckets[key] for key in sorted(ordered_keys)]
    result: list[dict[str, Any]] = []
    for index, bucket in enumerate(ordered):
        base = ordered[index - 1]["last"]["value"] if index > 0 else bucket["first"]["value"]
        change = (
            (bucket["last"]["value"] / base - 1) * 100
            if base and base != 0
            else None
        )
        result.append(
            {
                "年份": bucket["key"],
                "涨幅": change,
                "partial": index == 0,
            }
        )
    return result


def _line(label: str, value: Any) -> str:
    return f"- {label}：{_fmt_value(value)}"


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _build_holding_ratio(
    rows: list[dict[str, Any]],
    kind: str,
    weight_scope: str,
) -> dict[str, Any] | None:
    """把某类持仓组装成占比明细（占净值比例，降序）。"""

    def name_of(row: dict[str, Any]) -> str:
        if kind == "债券":
            return row.get("债券名称") or "未知债券"
        if kind == "基金":
            return row.get("基金名称") or "未知基金"
        return row.get("股票名称") or "未知股票"

    def code_of(row: dict[str, Any]) -> Any:
        if kind == "债券":
            return row.get("债券代码")
        if kind == "基金":
            return row.get("基金代码")
        return row.get("股票代码")

    items: list[dict[str, Any]] = []
    for row in rows:
        weight = _num(row.get("占净值比例"))
        if weight is None or weight <= 0:
            continue
        item: dict[str, Any] = {
            "name": name_of(row),
            "code": code_of(row),
            "占净值比例": _round(weight, 2),
        }
        if kind == "股票":
            item["industry"] = row.get("所属行业")
        items.append(item)

    if not items:
        return None

    items.sort(key=lambda item: item["占净值比例"], reverse=True)
    total = sum(item["占净值比例"] for item in items)

    return {
        "类型": kind,
        "权重口径": weight_scope,
        "合计占比": _round(total, 2),
        "数量": len(items),
        "明细": items,
    }


def build_ai_summary(payload: dict[str, Any]) -> str:
    """把缓存 payload 组装成 AI 友好的 Markdown 文本。"""
    basic = payload.get("基础资料") or {}
    performance = payload.get("历史业绩") or {}
    nav_curve = payload.get("净值曲线") or {}
    holdings = payload.get("基金持仓") or {}

    lines: list[str] = []

    name = _fmt_value(basic.get("名称"))
    code = _fmt_value(basic.get("代码"))
    lines.append(f"# 基金分析摘要：{name}（{code}）")
    lines.append("")

    # ---- 基金基础信息 ----
    lines.append("## 一、基金基础信息")
    lines.append(_line("名称", basic.get("名称")))
    lines.append(_line("代码", basic.get("代码")))
    lines.append(_line("业绩比较基准", basic.get("业绩比较基准")))
    lines.append(_line("类型", basic.get("类型")))
    lines.append(_line("成立日期", basic.get("成立日期")))
    lines.append(_line("成立时间", basic.get("成立时间")))

    scale = basic.get("基金规模") or {}
    scale_text = _fmt_value(scale.get("最新净资产"))
    if scale.get("净资产截止日"):
        scale_text = f"{scale_text}（截止 {scale.get('净资产截止日')}）"
    lines.append(_line("最新规模", scale_text))

    holder = basic.get("持有人结构") or {}
    institution = holder.get("机构持有比例")
    individual = holder.get("个人持有比例")
    if institution is not None or individual is not None:
        holder_text = (
            f"机构 {_fmt_ratio(institution)} / 个人 {_fmt_ratio(individual)}"
        )
        if holder.get("报告期"):
            holder_text = f"{holder_text}（{holder.get('报告期')}）"
    else:
        holder_text = "—"
    lines.append(_line("个人/机构持有比例", holder_text))

    lines.append(_line("基金公司（管理人）", basic.get("管理人")))
    lines.append(_line("托管人", basic.get("托管人")))
    lines.append(_line("管理费率", basic.get("管理费率")))
    lines.append(_line("托管费率", basic.get("托管费率")))

    purchase_fee = basic.get("买入费率") or {}
    fee_details = purchase_fee.get("明细") or []
    if fee_details:
        lines.append("- 申购费率：")
        for item in fee_details:
            condition = _fmt_value(item.get("适用条件"))
            original = _fmt_value(item.get("原费率"))
            discount = item.get("天天基金优惠费率")
            fee_text = f"  - {condition}：{original}"
            if discount:
                fee_text += f"（优惠 {discount}）"
            lines.append(fee_text)
    else:
        lines.append(_line("申购费率", None))
    lines.append("")

    # ---- 净值与收益 ----
    lines.append("## 二、净值与收益")
    lines.append("")
    lines.append("### 阶段涨幅")
    for label, key in _STAGE_KEYS:
        lines.append(_line(label, _fmt_pct(performance.get(key))))
    lines.append("")

    lines.append("### 周期涨幅（自然年）")
    annual = _compute_annual_returns(nav_curve)
    if annual:
        for entry in reversed(annual):
            suffix = "（区间起点，非完整年）" if entry["partial"] else ""
            lines.append(f"- {entry['年份']}年：{_fmt_pct(entry['涨幅'])}{suffix}")
    else:
        lines.append("- 暂无数据")
    lines.append("")

    lines.append("### 回撤修复")
    for label, range_key in _DRAWDOWN_RANGES:
        return_rows = _return_rows_for_range(nav_curve, range_key)
        analysis = _analyze_drawdown(return_rows)
        max_dd = analysis["maxDrawdown"]
        if max_dd >= -0.000001:
            lines.append(f"- {label}：区间内无明显回撤")
            continue
        detail = f"最大回撤 {max_dd:.2f}%"
        if analysis["recoveryDays"] is not None:
            detail += f"，已修复（用时 {analysis['recoveryDays']} 天）"
        elif analysis["elapsedRecoveryDays"] is not None:
            detail += f"，尚未修复（已过 {analysis['elapsedRecoveryDays']} 天）"
        lines.append(f"- {label}：{detail}")
    lines.append("")

    # ---- 基金持仓 ----
    lines.append("## 三、基金持仓")
    report_period = holdings.get("报告期")
    lines.append(_line("报告期", report_period))

    current_report = holdings.get("当前季报") or {}
    report_link = current_report.get("链接")
    if not report_link:
        quarter_reports = holdings.get("季报列表") or []
        if quarter_reports:
            report_link = quarter_reports[0].get("链接")
    lines.append(_line("最新季报链接", report_link))
    lines.append("")

    # 资产分布
    lines.append("### 资产分布")
    asset_details = ((holdings.get("资产分布") or {}).get("明细")) or []
    if asset_details:
        for item in asset_details:
            lines.append(
                f"- {_fmt_value(item.get('资产类别'))}：{_fmt_ratio(item.get('占比'))}"
            )
    else:
        lines.append("- 暂无数据")
    lines.append("")

    # 持仓比例（占净值比例，降序）
    lines.append("### 持仓比例（占净值比例）")
    stock_group = holdings.get("股票持仓") or {}
    stock_details = stock_group.get("明细") or []
    bond_group = holdings.get("债券持仓") or {}
    bond_details = bond_group.get("明细") or []
    fund_group = holdings.get("基金投资") or {}
    fund_details = fund_group.get("明细") or []

    holding_ratios: list[dict[str, Any]] = []
    stock_ratio = _build_holding_ratio(stock_details, "股票", "基金净值")
    if stock_ratio:
        holding_ratios.append(stock_ratio)
    bond_ratio = _build_holding_ratio(bond_details, "债券", "基金净值")
    if bond_ratio:
        holding_ratios.append(bond_ratio)
    fund_ratio = _build_holding_ratio(fund_details, "基金", "基金净值")
    if fund_ratio:
        holding_ratios.append(fund_ratio)

    if holding_ratios:
        for group in holding_ratios:
            lines.append("")
            lines.append(
                f"**{group['类型']}持仓**（合计 {_fmt_ratio(group['合计占比'])}，"
                f"共 {group['数量']} 只）"
            )
            for item in group["明细"]:
                name = _fmt_value(item.get("name"))
                code = item.get("code")
                label = f"{name}（{code}）" if code else name
                ratio = _fmt_ratio(item.get("占净值比例"))
                industry = item.get("industry")
                suffix = f" · {industry}" if industry else ""
                lines.append(f"- {label}：{ratio}{suffix}")
    else:
        lines.append("- 暂无持仓明细")
    lines.append("")

    # 债券品种与信用属性
    if bond_details:
        bond_structure = bond_group.get("品种结构") or {}
        variety_details = bond_structure.get("明细") or []
        credit_details = ((bond_structure.get("信用属性") or {}).get("明细")) or []
        if variety_details:
            lines.append("### 债券品种结构（占净值比例）")
            for item in variety_details:
                lines.append(
                    f"- {_fmt_value(item.get('债券品种'))}："
                    f"{_fmt_ratio(item.get('占净值比例'))}"
                )
            lines.append("")
        if credit_details:
            lines.append("### 债券信用属性（占净值比例）")
            for item in credit_details:
                lines.append(
                    f"- {_fmt_value(item.get('信用属性'))}："
                    f"{_fmt_ratio(item.get('占净值比例'))}"
                )
            lines.append("")

    # 股票行业配置
    if stock_details:
        sector = holdings.get("板块配置") or {}
        sector_details = sector.get("明细") or []
        if sector_details:
            lines.append("### 股票行业配置（占净值比例）")
            for item in sector_details:
                lines.append(
                    f"- {_fmt_value(item.get('行业类别'))}："
                    f"{_fmt_ratio(item.get('占净值比例'))}"
                )
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
