"""基金赛道基准目录、历史行情和默认推荐。"""

from __future__ import annotations

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
    },
    "csi500": {
        "名称": "中证500",
        "说明": "沪深两市中小市值宽基",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sh000905",
    },
    "csi800": {
        "名称": "中证800",
        "说明": "沪深300与中证500合并的全市场宽基",
        "类型": "股票宽基",
        "source": "equity",
        "symbol": "sh000906",
    },
    "cbond_composite": {
        "名称": "中债-新综合财富（总值）指数",
        "简称": "中债新综合财富",
        "说明": "覆盖境内债券市场的综合型财富指数",
        "类型": "债券宽基",
        "source": "bond",
        "category": "新综合指数",
        "period": "总值",
    },
    "cbond_short": {
        "名称": "中债-新综合财富（1年以下）指数",
        "简称": "中债短久期财富",
        "说明": "待偿期1年以下的短久期债券赛道",
        "类型": "债券短久期",
        "source": "bond",
        "category": "新综合指数",
        "period": "1年以下",
    },
    "cbond_credit": {
        "名称": "中债-信用债总财富（总值）指数",
        "简称": "中债信用债财富",
        "说明": "信用债市场整体财富表现",
        "类型": "信用债",
        "source": "bond",
        "category": "信用债总指数",
        "period": "总值",
    },
    "cbond_rates": {
        "名称": "中债-国债及政策性银行债财富（总值）指数",
        "简称": "中债利率债财富",
        "说明": "国债与政策性金融债赛道",
        "类型": "利率债",
        "source": "bond",
        "category": "国债及政策性银行债指数",
        "period": "总值",
    },
    "fixed_income_plus_80_20": {
        "名称": "固收+ 80/20赛道基准",
        "简称": "固收+ 80/20",
        "说明": "80%中债新综合财富 + 20%沪深300，每日定权复合",
        "类型": "股债组合",
        "source": "composite",
        "components": {
            "cbond_composite": 0.8,
            "hs300": 0.2,
        },
    },
}


def track_benchmark_catalog() -> list[dict[str, Any]]:
    """返回可公开给前端的赛道基准目录。"""
    return [
        {
            "key": key,
            "名称": config["名称"],
            "简称": config.get("简称", config["名称"]),
            "说明": config["说明"],
            "类型": config["类型"],
        }
        for key, config in TRACK_BENCHMARKS.items()
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


def _source_series(key: str) -> pd.Series:
    config = TRACK_BENCHMARKS[key]
    source = config["source"]
    if source == "equity":
        try:
            frame = ak.stock_zh_index_daily_em(
                symbol=config["symbol"],
                start_date="19900101",
                end_date=date.today().strftime("%Y%m%d"),
            )
        except Exception:
            # 东财历史接口偶有连接波动，新浪日线作为同代码备用源。
            frame = ak.stock_zh_index_daily(symbol=config["symbol"])
        return _clean_history(frame, "date", "close")
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
) -> dict[str, str]:
    """根据基金类型与已披露债券结构给出赛道基准建议。"""
    descriptor = f"{fund_name or ''} {fund_type or ''}"
    if any(word in descriptor for word in ("固收+", "偏债混合", "混合二级")):
        return {
            "key": "fixed_income_plus_80_20",
            "理由": "该基金包含较稳定的债券底仓与权益增强，使用80/20股债组合更能反映固收+赛道。",
        }
    if "短债" in descriptor or "超短债" in descriptor:
        return {
            "key": "cbond_short",
            "理由": "短债基金的利率敏感度较低，使用1年以下债券财富指数更匹配其久期。",
        }
    if "债" in descriptor:
        credit_share = 0.0
        rates_share = 0.0
        for row in bond_structure or []:
            name = str(row.get("债券品种") or "")
            try:
                weight = float(row.get("占净值比例") or 0)
            except (TypeError, ValueError):
                continue
            if any(word in name for word in ("国债", "政策性", "地方政府债")):
                rates_share += weight
            elif any(
                word in name
                for word in (
                    "企业债",
                    "公司债",
                    "中期票据",
                    "短期融资",
                    "金融债（不含政策性）",
                    "同业存单",
                )
            ):
                credit_share += weight
        if credit_share > rates_share and credit_share > 0:
            return {
                "key": "cbond_credit",
                "理由": "最新披露组合以信用债为主，信用债总财富指数比股票宽基或全市场债券指数更贴近赛道。",
            }
        if rates_share > credit_share and rates_share > 0:
            return {
                "key": "cbond_rates",
                "理由": "最新披露组合以国债、政策性金融债等利率债为主，利率债财富指数更贴近赛道。",
            }
        return {
            "key": "cbond_composite",
            "理由": "该基金属于债券策略，使用覆盖全市场的中债新综合财富指数作为通用赛道基准。",
        }
    if any(word in descriptor for word in ("中小盘", "小盘")):
        return {
            "key": "csi500",
            "理由": "基金风格偏中小市值，中证500比大盘指数更匹配。",
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
