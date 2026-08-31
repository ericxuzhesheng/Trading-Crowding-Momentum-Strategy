"""Canonical display labels for backtest strategies."""

from __future__ import annotations


STRATEGY_LABELS: dict[str, dict[str, str]] = {
    "all_index_equal_weight": {"zh": "全配置资产等权参照", "en": "Configured-Universe EW Reference"},
    "crowding_top_quantile": {"zh": "复合拥挤度得分对照", "en": "Composite Crowding-Score Control"},
    "csi300_etf_buy_hold": {"zh": "沪深300 ETF 买入持有", "en": "CSI 300 Buy & Hold"},
    "momentum_crowding_penalty": {"zh": "动量 - 拥挤度 top30 上限等权", "en": "Capped Top-30% Mom-Crowding"},
    "momentum_crowding_penalty_trend": {
        "zh": "动量 - 拥挤度 top30 上限等权 + 趋势过滤",
        "en": "Capped Top-30% Mom-Crowding + Trend",
    },
    "momentum_crowding_convex": {"zh": "凸优化动量 - 拥挤度", "en": "Convex Mom-Crowding"},
    "momentum_crowding_convex_trend": {
        "zh": "凸优化动量 - 拥挤度 + 趋势过滤",
        "en": "Convex Mom-Crowding + Trend",
    },
    "momentum_top_quantile": {"zh": "5 日动量对照", "en": "5D Momentum Control"},
}


def strategy_label(strategy: str, language: str = "en") -> str:
    """Return a stable human-readable strategy label."""
    return STRATEGY_LABELS.get(strategy, {}).get(language, strategy)
