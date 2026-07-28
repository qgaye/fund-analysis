"""基金赛道基准目录、历史行情和默认推荐。"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import akshare as ak
import pandas as pd


TRACK_BENCHMARKS: dict[str, dict[str, Any]] = {
    "hs300": {
        "名称": "沪深300",
        "说明": "沪深两市大盘蓝筹宽基",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sh000300",
        "指数代码": "000300",
        "编制": "沪深两市规模最大、流动性最好的 300 只龙头股，按自由流通市值加权。",
        "代表": "A股大盘蓝筹的整体表现，覆盖全市场约六成市值。",
        "适用": "大盘、价值或均衡风格的主动股票与偏股基金。",
    },
    "hs300_tr": {
        "名称": "沪深300全收益",
        "说明": "沪深300含股息再投资的全收益口径",
        "类型": "股票宽基",
        "source": "csindex",
        "symbol": "H00300",
        "指数代码": "H00300",
        "编制": "沪深300 成分股现金分红按除息日再投资计入，反映含股息的全收益。",
        "代表": "沪深300 含股息再投资的完整持有回报，可与债券财富指数同口径对齐。",
        "适用": "需与债券财富（全收益）口径对齐比较的大盘蓝筹基金。",
    },
    "csi500": {
        "名称": "中证500",
        "说明": "沪深两市中小市值宽基",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sh000905",
        "指数代码": "000905",
        "编制": "剔除沪深300成分后，规模排名前 500 的中盘股，按自由流通市值加权。",
        "代表": "A股中盘股整体表现，成长与周期特征较强。",
        "适用": "中盘风格、行业相对均衡的成长型基金。",
    },
    "csi800": {
        "名称": "中证800",
        "说明": "沪深300与中证500合并的全市场宽基",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sh000906",
        "指数代码": "000906",
        "编制": "沪深300 与中证500 成分合并，共 800 只大中盘股。",
        "代表": "覆盖大中盘的全市场宽基，兼顾蓝筹与成长。",
        "适用": "可同时投资大中盘的全市场权益基金。",
    },
    "csi800_tr": {
        "名称": "中证800全收益",
        "说明": "中证800含股息再投资的全收益口径",
        "类型": "股票宽基",
        "source": "csindex",
        "symbol": "H00906",
        "指数代码": "H00906",
        "编制": "中证800 成分股现金分红按除息日再投资计入，反映含股息的全收益。",
        "代表": "中证800 含股息再投资的完整持有回报，可与债券财富指数同口径对齐。",
        "适用": "需与债券财富（全收益）口径对齐比较的全市场权益基金。",
    },
    "csi1000": {
        "名称": "中证1000",
        "说明": "沪深两市小市值宽基",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sh000852",
        "指数代码": "000852",
        "编制": "剔除沪深300、中证500 后，规模排名前 1000 的小盘股。",
        "代表": "A股小市值股票整体表现，弹性大、波动高。",
        "适用": "小盘成长或量化选股风格的基金。",
    },
    "csi2000": {
        "名称": "中证2000",
        "说明": "沪深两市微小市值宽基",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sh932000",
        "指数代码": "932000",
        "编制": "剔除中证800、中证1000 后，规模靠前的 2000 只微小市值股。",
        "代表": "A股微盘股整体表现，弹性与波动更极端。",
        "适用": "微盘、小微盘量化风格的基金。",
    },
    "chinext": {
        "名称": "创业板指",
        "说明": "深市创业板成长风格代表宽基",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sz399006",
        "指数代码": "399006",
        "编制": "深交所创业板中市值大、流动性好的 100 只股票。",
        "代表": "创业板成长股表现，成长与科技属性突出。",
        "适用": "聚焦创业板、成长赛道的基金。",
    },
    "star50": {
        "名称": "科创50",
        "说明": "科创板硬科技龙头宽基",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sh000688",
        "指数代码": "000688",
        "编制": "科创板中市值大、流动性好的 50 只龙头股。",
        "代表": "科创板硬科技龙头表现，集中于半导体、生物医药等。",
        "适用": "科创主题、硬科技赛道的基金。",
    },
    "csi_dividend": {
        "名称": "中证红利",
        "说明": "高股息价值风格代表指数",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sh000922",
        "指数代码": "000922",
        "编制": "现金分红稳定、股息率较高的 100 只股票，按股息率加权。",
        "代表": "高股息价值风格表现，防御性较强。",
        "适用": "红利、价值、低波风格的基金。",
    },
    "money_fund": {
        "名称": "中证货币基金指数",
        "简称": "货币基金",
        "说明": "全市场货币基金平均收益基准",
        "类型": "货币现金",
        "source": "csindex",
        "symbol": "H11025",
        "指数代码": "H11025",
        "编制": "选取全市场存续货币基金，按规模加权反映其整体收益，走势持续平稳向上。",
        "代表": "货币基金整体收益水平，接近无风险的现金管理回报。",
        "适用": "货币基金、现金管理类及类活期理财产品。",
    },
    "cbond_mid_short": {
        "名称": "中债-新综合财富（1-3年）指数",
        "简称": "中债中短债财富",
        "说明": "待偿期1-3年的中短债赛道",
        "类型": "债券中短久期",
        "source": "bond",
        "category": "新综合指数",
        "period": "1-3年",
        "指数代码": "中债新综合·1-3年",
        "编制": "取中债新综合指数中待偿期 1-3 年的债券，财富口径已含票息再投资。",
        "代表": "中短久期债券的持有回报，利率敏感度中等偏低。",
        "适用": "中短债、稳健型债券基金。",
    },
    "cbond_mid_long": {
        "名称": "中债-新综合财富（5-7年）指数",
        "简称": "中债中长债财富",
        "说明": "待偿期5-7年的中长债赛道",
        "类型": "债券中长久期",
        "source": "bond",
        "category": "新综合指数",
        "period": "5-7年",
        "指数代码": "中债新综合·5-7年",
        "编制": "取中债新综合指数中待偿期 5-7 年的债券，财富口径已含票息再投资。",
        "代表": "中长久期债券持有回报，利率敏感度较高。",
        "适用": "中长久期、久期偏长的债券基金。",
    },
    "cbond_composite": {
        "名称": "中债-新综合财富（总值）指数",
        "简称": "中债新综合财富",
        "说明": "覆盖境内债券市场的综合型财富指数",
        "类型": "债券宽基",
        "source": "bond",
        "category": "新综合指数",
        "period": "总值",
        "hidden": True,
    },
    "fixed_income_plus_80_20": {
        "名称": "偏债混合赛道基准",
        "简称": "偏债混合",
        "说明": "80%中债新综合财富 + 20%沪深300，每日定权复合",
        "类型": "股债组合",
        "source": "composite",
        "components": {
            "cbond_composite": 0.8,
            "hs300": 0.2,
        },
        "编制": "80% 中债新综合财富 + 20% 沪深300，每日按目标权重再平衡复合。",
        "代表": "以债券打底、少量权益增强的“固收+”组合收益。",
        "适用": "偏债混合、二级债基、固收+ 类基金。",
    },
    "equity_bond_80_20": {
        "名称": "偏股混合赛道基准",
        "简称": "偏股混合",
        "说明": "80%沪深300 + 20%中债新综合财富，每日定权复合",
        "类型": "股债组合",
        "source": "composite",
        "components": {
            "hs300": 0.8,
            "cbond_composite": 0.2,
        },
        "编制": "80% 沪深300 + 20% 中债新综合财富，每日按目标权重再平衡复合。",
        "代表": "以权益为主、少量债券缓冲的偏股组合收益。",
        "适用": "偏股混合、灵活配置类基金。",
    },
}

DISCLOSED_BENCHMARK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"科创\s*50", "star50"),
    (r"创业板", "chinext"),
    (r"中证\s*红利", "csi_dividend"),
    (r"中证\s*2000", "csi2000"),
    (r"中证\s*1000", "csi1000"),
    (r"沪深\s*300", "hs300"),
    (r"中证\s*500", "csi500"),
    (r"中证\s*800", "csi800"),
    (r"中债.*(?:1\s*-\s*3\s*年|1\s*到\s*3\s*年|中短债)", "cbond_mid_short"),
    (r"中债.*(?:5\s*-\s*7\s*年|5\s*到\s*7\s*年|中长债)", "cbond_mid_long"),
)

# 业绩比较基准里，各成分指数名 → 赛道基准 key 的宽松匹配规则（按优先级从上到下）。
PERFORMANCE_COMPONENT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"科创\s*50", "star50"),
    (r"创业板", "chinext"),
    (r"红利", "csi_dividend"),
    (r"中证\s*2000", "csi2000"),
    (r"中证\s*1000", "csi1000"),
    (r"中证\s*800", "csi800"),
    (r"中证\s*500", "csi500"),
    (r"沪深\s*300", "hs300"),
    (r"中债.*(?:1\s*-\s*3\s*年|1\s*到\s*3\s*年|中短债)", "cbond_mid_short"),
    (r"中债.*(?:5\s*-\s*7\s*年|5\s*到\s*7\s*年|中长债)", "cbond_mid_long"),
    (r"中债", "cbond_composite"),
)

# 现金/存款类成分（如“银行活期存款利率”）近似为货币基金指数。
PERFORMANCE_CASH_PATTERN = re.compile(r"活期|定期|存款|现金|货币|七天通知|理财")


def _parse_component_weight(segment: str) -> float | None:
    """从形如 “×95%”“*70%” 的片段里提取权重（返回 0-1 的小数）。"""
    match = re.search(r"[*×xX]\s*(\d+(?:\.\d+)?)\s*%", segment)
    if match:
        return float(match.group(1)) / 100
    return None


def parse_performance_benchmark(text: str | None) -> list[dict[str, Any]]:
    """把业绩比较基准字符串拆成 [{"原文": 指数名, "权重": 0-1 或 None}]。"""
    raw = str(text or "").strip()
    if not raw:
        return []
    raw = raw.replace("＋", "+").replace("＊", "*").replace("％", "%")
    segments = [seg for seg in raw.split("+") if seg.strip()]
    components: list[dict[str, Any]] = []
    for segment in segments:
        weight = _parse_component_weight(segment)
        name = re.split(r"[*×]", segment)[0].strip()
        components.append({"原文": name or segment.strip(), "权重": weight})
    # 单一成分且未标注权重时，默认视为占比 100%。
    if len(components) == 1 and components[0]["权重"] is None:
        components[0]["权重"] = 1.0
    return components


def _match_component_key(name: str) -> str | None:
    for pattern, key in PERFORMANCE_COMPONENT_PATTERNS:
        if re.search(pattern, name):
            return key
    if PERFORMANCE_CASH_PATTERN.search(name):
        return "money_fund"
    return None


def match_performance_benchmark(text: str | None) -> dict[str, Any] | None:
    """解析业绩比较基准并匹配到赛道基准；任一成分无法匹配则整体返回 None。"""
    components = parse_performance_benchmark(text)
    if not components:
        return None
    matched: list[dict[str, Any]] = []
    for component in components:
        if component["权重"] is None:
            return None  # 多成分却缺少权重，无法可靠合成。
        key = _match_component_key(component["原文"])
        if key is None:
            return None  # 有成分匹配不到赛道基准，按约定整体放弃。
        matched.append({**component, "key": key})

    merged: dict[str, float] = {}
    order: list[str] = []
    for item in matched:
        if item["key"] not in merged:
            merged[item["key"]] = 0.0
            order.append(item["key"])
        merged[item["key"]] += item["权重"]

    total = sum(merged.values())
    if total <= 0:
        return None
    breakdown = [
        {
            "key": key,
            "简称": TRACK_BENCHMARKS[key].get("简称", TRACK_BENCHMARKS[key]["名称"]),
            "权重": round(merged[key] / total, 4),
        }
        for key in order
    ]
    return {
        "components": {key: merged[key] / total for key in order},
        "构成": breakdown,
    }


def parse_composite_spec(spec: str | None) -> dict[str, float]:
    """把 “csi_dividend:0.95,money_fund:0.05” 解析为归一化权重字典。"""
    components: dict[str, float] = {}
    order: list[str] = []
    for part in str(spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        key, separator, weight = part.partition(":")
        key = key.strip()
        if not separator or key not in TRACK_BENCHMARKS:
            raise ValueError(f"无效的复合基准片段：{part}")
        try:
            value = float(weight)
        except ValueError as exc:
            raise ValueError(f"无效的权重：{weight}") from exc
        if value <= 0:
            raise ValueError(f"权重必须为正数：{weight}")
        if key not in components:
            components[key] = 0.0
            order.append(key)
        components[key] += value
    if not components:
        raise ValueError("复合基准为空。")
    total = sum(components.values())
    return {key: components[key] / total for key in order}


def track_benchmark_catalog() -> list[dict[str, Any]]:
    """返回可公开给前端的赛道基准目录。"""
    return [
        {
            "key": key,
            "名称": config["名称"],
            "简称": config.get("简称", config["名称"]),
            "说明": config["说明"],
            "类型": config["类型"],
            "指数代码": config.get("指数代码", ""),
            "编制": config.get("编制", ""),
            "代表": config.get("代表", ""),
            "适用": config.get("适用", ""),
        }
        for key, config in TRACK_BENCHMARKS.items()
        if not config.get("hidden")
    ]


def _clean_history(
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
) -> pd.Series:
    if frame.empty or not {date_column, value_column}.issubset(frame.columns):
        return pd.Series(dtype=float)
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    values = pd.to_numeric(frame[value_column], errors="coerce")
    series = pd.Series(values.to_numpy(), index=dates)
    series = series[~series.index.isna()].dropna()
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series.astype(float)


_EQUITY_STALE_DAYS = 30


def _equity_series(symbol: str) -> pd.Series:
    """按 腾讯→东财日线→东财中证历史→中证官网→新浪 多级回退取指数收盘序列。

    多源设计考量：
    1. 东财接口偶发触发人机验证/限流；腾讯日线独立于东财、代码格式一致，
       放在首位可在东财不可用时顶上。
    2. 部分较新的中证指数（如中证2000）不在腾讯与新浪源中，需要东财中证
       历史或中证官网接口兜底；中证官网为权威源、覆盖最全，放在新浪之前。
    3. 新浪日线对红利等部分指数长期停更（数据停在数年前），因此降为最后
       兜底，且每级都做新鲜度校验：数据足够新才立即采纳，否则暂存候选、
       继续尝试更优源，全部尝试后返回其中最新鲜的一份。
    """
    numeric_code = re.sub(r"^[a-zA-Z]+", "", symbol)
    today = date.today().strftime("%Y%m%d")

    def from_tx() -> pd.Series:
        frame = ak.stock_zh_index_daily_tx(symbol=symbol)
        return _clean_history(frame, "date", "close")

    def from_em() -> pd.Series:
        frame = ak.stock_zh_index_daily_em(
            symbol=symbol,
            start_date="19900101",
            end_date=today,
        )
        return _clean_history(frame, "date", "close")

    def from_cn_hist() -> pd.Series:
        frame = ak.index_zh_a_hist(
            symbol=numeric_code,
            period="daily",
            start_date="19900101",
            end_date=today,
        )
        return _clean_history(frame, "日期", "收盘")

    def from_csindex() -> pd.Series:
        frame = ak.stock_zh_index_hist_csindex(
            symbol=numeric_code,
            start_date="19900101",
            end_date=today,
        )
        return _clean_history(frame, "日期", "收盘")

    def from_sina() -> pd.Series:
        frame = ak.stock_zh_index_daily(symbol=symbol)
        return _clean_history(frame, "date", "close")

    freshness_cutoff = pd.Timestamp(date.today()) - pd.Timedelta(
        days=_EQUITY_STALE_DAYS
    )
    best = pd.Series(dtype=float)
    for loader in (from_tx, from_em, from_cn_hist, from_csindex, from_sina):
        try:
            series = loader()
        except Exception:
            continue
        if series.empty:
            continue
        if series.index.max() >= freshness_cutoff:
            return series
        # 数据过期，暂存最新鲜的候选，继续尝试更可靠的源。
        if best.empty or series.index.max() > best.index.max():
            best = series
    return best


def _csindex_series(symbol: str) -> pd.Series:
    """按完整指数代码（含字母前缀，如 H11025）从中证官网取收盘序列。"""
    today = date.today().strftime("%Y%m%d")
    frame = ak.stock_zh_index_hist_csindex(
        symbol=symbol,
        start_date="19900101",
        end_date=today,
    )
    return _clean_history(frame, "日期", "收盘")


def _source_series(key: str) -> pd.Series:
    config = TRACK_BENCHMARKS[key]
    source = config["source"]
    if source == "equity":
        return _equity_series(config["symbol"])
    if source == "csindex":
        return _csindex_series(config["symbol"])
    if source == "bond":
        frame = ak.bond_index_general_cbond(
            index_category=config["category"],
            indicator="财富",
            period=config["period"],
        )
        return _clean_history(frame, "date", "value")
    raise ValueError(f"{key} 不是可直接获取的指数序列。")


def _composite_series(components: dict[str, float]) -> pd.Series:
    source = {
        key: _source_series(key)
        for key in components
    }
    aligned = pd.concat(source, axis=1).sort_index().ffill().dropna()
    if aligned.empty:
        return pd.Series(dtype=float)
    daily_returns = aligned.pct_change().fillna(0)
    weights = pd.Series(components, dtype=float)
    composite_returns = daily_returns.mul(weights, axis=1).sum(axis=1)
    return 100 * (1 + composite_returns).cumprod()


def _serialize_series(series: pd.Series) -> list[dict[str, Any]]:
    return [
        {
            "日期": timestamp.strftime("%Y-%m-%d"),
            "指数值": round(float(value), 6),
        }
        for timestamp, value in series.items()
    ]


def get_track_benchmark(key: str) -> dict[str, Any]:
    """获取一条赛道基准的完整日度历史。"""
    if key not in TRACK_BENCHMARKS:
        raise KeyError(key)
    config = TRACK_BENCHMARKS[key]
    series = (
        _composite_series(config["components"])
        if config["source"] == "composite"
        else _source_series(key)
    )
    rows = _serialize_series(series)
    return {
        "key": key,
        "名称": config["名称"],
        "简称": config.get("简称", config["名称"]),
        "说明": config["说明"],
        "类型": config["类型"],
        "来源": (
            "中债指数"
            if config["source"] == "bond"
            else "中证指数"
            if config["source"] in ("equity", "csindex")
            else "中债指数、中证指数；系统按日定权复合"
        ),
        "数量": len(rows),
        "起始日": rows[0]["日期"] if rows else None,
        "结束日": rows[-1]["日期"] if rows else None,
        "明细": rows,
    }


def get_composite_benchmark(components: dict[str, float]) -> dict[str, Any]:
    """按任意 {赛道基准 key: 权重} 合成一条复合基准的完整日度历史。"""
    if not components:
        raise ValueError("复合基准为空。")
    unknown = [key for key in components if key not in TRACK_BENCHMARKS]
    if unknown:
        raise KeyError(unknown[0])
    total = sum(components.values())
    weights = {key: value / total for key, value in components.items()}
    series = _composite_series(weights)
    rows = _serialize_series(series)
    breakdown = [
        {
            "key": key,
            "简称": TRACK_BENCHMARKS[key].get("简称", TRACK_BENCHMARKS[key]["名称"]),
            "权重": round(weight, 4),
        }
        for key, weight in weights.items()
    ]
    label = " + ".join(
        f"{item['简称']} {round(item['权重'] * 100)}%" for item in breakdown
    )
    return {
        "key": "performance_composite",
        "名称": f"业绩比较基准（{label}）",
        "简称": "业绩比较基准",
        "说明": f"按业绩比较基准每日定权复合：{label}",
        "类型": "业绩基准复合",
        "来源": "中债指数、中证指数；系统按业绩比较基准定权复合",
        "构成": breakdown,
        "数量": len(rows),
        "起始日": rows[0]["日期"] if rows else None,
        "结束日": rows[-1]["日期"] if rows else None,
        "明细": rows,
    }


def recommend_track_benchmark(
    fund_name: str | None,
    fund_type: str | None,
    bond_structure: list[dict[str, Any]] | None = None,
    performance_benchmark: str | None = None,
) -> dict[str, str]:
    """优先匹配基金业绩基准，再按基金类型与债券结构给出建议。"""
    disclosed = str(performance_benchmark or "")

    # 优先尝试按业绩比较基准解析出「指数+占比」并合成复合赛道基准。
    matched = match_performance_benchmark(disclosed)
    if matched is not None:
        breakdown = matched["构成"]
        label = " + ".join(
            f"{item['简称']} {round(item['权重'] * 100)}%" for item in breakdown
        )
        if len(breakdown) == 1:
            # 单一成分直接采用对应指数，沿用静态赛道选项。
            key = breakdown[0]["key"]
            name = TRACK_BENCHMARKS[key].get("简称", TRACK_BENCHMARKS[key]["名称"])
            return {
                "key": key,
                "理由": f"基金披露的业绩比较基准为{name}，直接采用同一指数作为赛道基准。",
            }
        return {
            "key": "performance_composite",
            "复合": matched["components"],
            "构成": breakdown,
            "理由": f"按业绩比较基准定权合成赛道基准：{label}。",
        }

    for pattern, key in DISCLOSED_BENCHMARK_PATTERNS:
        if re.search(pattern, disclosed, flags=re.IGNORECASE):
            name = TRACK_BENCHMARKS[key].get("简称", TRACK_BENCHMARKS[key]["名称"])
            return {
                "key": key,
                "理由": f"基金披露的业绩比较基准包含{name}，优先采用同一指数作为赛道基准。",
            }

    descriptor = f"{fund_name or ''} {fund_type or ''}"
    if any(word in descriptor for word in ("货币", "现金", "理财")):
        return {
            "key": "money_fund",
            "理由": "该基金属于货币现金类，使用中证货币基金指数作为赛道基准最贴近其收益特征。",
        }
    if any(word in descriptor for word in ("固收+", "偏债混合", "混合二级")):
        return {
            "key": "fixed_income_plus_80_20",
            "理由": "该基金包含较稳定的债券底仓与权益增强，使用偏债混合（80%债/20%股）更能反映其赛道。",
        }
    if "短债" in descriptor or "超短债" in descriptor:
        return {
            "key": "cbond_mid_short",
            "理由": "短债基金久期偏低，使用中债1-3年中短债财富指数更匹配其久期。",
        }
    if "债" in descriptor:
        if any(word in descriptor for word in ("长债", "中长债", "长久期")):
            return {
                "key": "cbond_mid_long",
                "理由": "该基金久期偏长，使用中债5-7年中长债财富指数更贴近赛道。",
            }
        return {
            "key": "cbond_mid_short",
            "理由": "该基金属于债券策略，默认使用久期适中的中债1-3年中短债财富指数作为赛道基准。",
        }
    if "科创" in descriptor:
        return {
            "key": "star50",
            "理由": "基金聚焦科创板硬科技标的，科创50比综合宽基更贴近赛道。",
        }
    if "创业板" in descriptor:
        return {
            "key": "chinext",
            "理由": "基金以创业板成长股为主，创业板指比综合宽基更贴近赛道。",
        }
    if any(word in descriptor for word in ("红利", "股息", "价值")):
        return {
            "key": "csi_dividend",
            "理由": "基金偏高股息价值风格，中证红利比综合宽基更能反映其收益特征。",
        }
    if any(word in descriptor for word in ("微盘", "小微", "中证2000")):
        return {
            "key": "csi2000",
            "理由": "基金聚焦微小市值股票，中证2000比中小盘指数更匹配。",
        }
    if "中小盘" in descriptor:
        return {
            "key": "csi500",
            "理由": "基金风格偏中小市值，中证500比大盘指数更匹配。",
        }
    if any(word in descriptor for word in ("小盘", "中证1000")):
        return {
            "key": "csi1000",
            "理由": "基金风格偏小市值，中证1000比大中盘指数更匹配。",
        }
    if any(word in descriptor for word in ("股票", "混合", "权益")):
        return {
            "key": "csi800_tr",
            "理由": "基金可覆盖大中小市值股票，中证800全收益（含股息再投资）适合作为全市场权益赛道基准，且与债券财富指数同口径。",
        }
    return {
        "key": "hs300_tr",
        "理由": "未识别到更具体的赛道，默认使用代表性较强的沪深300全收益（含股息再投资），与债券财富指数同口径便于对齐比较。",
    }
