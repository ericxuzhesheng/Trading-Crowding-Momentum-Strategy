"""Canonical display labels for backtest strategies."""

from __future__ import annotations


STRATEGY_LABELS: dict[str, dict[str, str]] = {
    "all_index_equal_weight": {"zh": "全 ETF 等权", "en": "All-ETF Equal Weight"},
    "crowding_top_quantile": {"zh": "纯拥挤度 top30 对照组", "en": "Pure Crowding"},
    "csi300_etf_buy_hold": {"zh": "沪深300 ETF 买入持有", "en": "CSI 300 Buy & Hold"},
    "momentum_crowding_penalty": {"zh": "动量 - 拥挤度惩罚", "en": "Mom-Crowding Equal Weight"},
    "momentum_crowding_penalty_trend": {
        "zh": "动量 - 拥挤度惩罚 + 趋势过滤",
        "en": "Mom-Crowding Equal Weight + Trend",
    },
    "momentum_crowding_convex": {"zh": "凸优化动量 - 拥挤度", "en": "Convex Mom-Crowding"},
    "momentum_crowding_convex_trend": {
        "zh": "凸优化动量 - 拥挤度 + 趋势过滤",
        "en": "Convex Mom-Crowding + Trend",
    },
    "momentum_top_quantile": {"zh": "纯 5 日动量 top30", "en": "Pure 5D Momentum"},
}


def strategy_label(strategy: str, language: str = "en") -> str:
    """Return a stable human-readable strategy label."""
    return STRATEGY_LABELS.get(strategy, {}).get(language, strategy)
