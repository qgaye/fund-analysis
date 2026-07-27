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


def _source_series(key: str) -> pd.Series:
    config = TRACK_BENCHMARKS[key]
    source = config["source"]
    if source == "equity":
        return _equity_series(config["symbol"])
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
    rows = [
        {
            "日期": timestamp.strftime("%Y-%m-%d"),
            "指数值": round(float(value), 6),
        }
        for timestamp, value in series.items()
    ]
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
            if config["source"] == "equity"
            else "中债指数、中证指数；系统按日定权复合"
        ),
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
    for pattern, key in DISCLOSED_BENCHMARK_PATTERNS:
        if re.search(pattern, disclosed, flags=re.IGNORECASE):
            name = TRACK_BENCHMARKS[key].get("简称", TRACK_BENCHMARKS[key]["名称"])
            return {
                "key": key,
                "理由": f"基金披露的业绩比较基准包含{name}，优先采用同一指数作为赛道基准。",
            }

    descriptor = f"{fund_name or ''} {fund_type or ''}"
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
            "key": "csi800",
            "理由": "基金可覆盖大中小市值股票，中证800适合作为全市场权益赛道基准。",
        }
    return {
        "key": "hs300",
        "理由": "未识别到更具体的赛道，默认使用代表性较强的沪深300。",
    }
