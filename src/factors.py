"""Factor construction for momentum, crowding, and risk signals."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """Compute a rolling z-score using only trailing observations."""
    mean = series.rolling(window=window, min_periods=max(3, window // 2)).mean()
    std = series.rolling(window=window, min_periods=max(3, window // 2)).std(ddof=0)
    return (series - mean) / std.replace(0, np.nan)


def cross_sectional_rank(series: pd.Series, ascending: bool = True) -> pd.Series:
    """Return same-date cross-sectional percentile ranks normalized to 0-1."""
    ranked = series.rank(method="average", pct=True, ascending=ascending)
    return ranked.clip(0, 1)


def add_factors(panel: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Build momentum, crowding, volatility, and lagged tradable scores."""
    df = panel.copy().sort_values(["symbol", "date"])
    fcfg = config["factors"]
    df["daily_return"] = df.groupby("symbol")["close"].pct_change(fill_method=None)
    df["ret_5d"] = df.groupby("symbol")["close"].pct_change(int(fcfg["ret_short_window"]), fill_method=None)
    df["ret_20d"] = df.groupby("symbol")["close"].pct_change(int(fcfg["ret_long_window"]), fill_method=None)
    df["turnover_z"] = df.groupby("symbol")["turnover"].transform(lambda s: rolling_zscore(s, int(fcfg["crowding_window"])))
    df["amount_z"] = df.groupby("symbol")["amount"].transform(lambda s: rolling_zscore(s, int(fcfg["crowding_window"])))
    df["volume_z"] = df.groupby("symbol")["volume"].transform(lambda s: rolling_zscore(s, int(fcfg["crowding_window"])))
    df["vol_20d"] = df.groupby("symbol")["daily_return"].transform(
        lambda s: s.rolling(int(fcfg["volatility_window"]), min_periods=max(5, int(fcfg["volatility_window"]) // 2)).std()
    )

    grouped = df.groupby("date", group_keys=False)
    df["rank_ret_5d"] = grouped["ret_5d"].transform(lambda s: cross_sectional_rank(s, ascending=True))
    df["rank_ret_20d"] = grouped["ret_20d"].transform(lambda s: cross_sectional_rank(s, ascending=True))
    df["rank_turnover_z"] = grouped["turnover_z"].transform(lambda s: cross_sectional_rank(s, ascending=True))
    df["rank_amount_z"] = grouped["amount_z"].transform(lambda s: cross_sectional_rank(s, ascending=True))
    df["rank_volume_z"] = grouped["volume_z"].transform(lambda s: cross_sectional_rank(s, ascending=True))
    df["rank_vol_20d"] = grouped["vol_20d"].transform(lambda s: cross_sectional_rank(s, ascending=True))

    turnover_rank = df["rank_turnover_z"].fillna(df["rank_volume_z"]).fillna(df["rank_amount_z"])
    amount_rank = df["rank_amount_z"].fillna(df["rank_volume_z"]).fillna(df["rank_turnover_z"])
    df["crowding_score"] = turnover_rank * 0.4 + amount_rank * 0.3 + df["rank_ret_20d"] * 0.3
    df["rank_crowding_score"] = grouped["crowding_score"].transform(lambda s: cross_sectional_rank(s, ascending=True))
    score_weights = fcfg.get("score_weights", {})
    ret_5d_weight = float(score_weights.get("ret_5d", 1.0))
    ret_20d_weight = float(score_weights.get("ret_20d", 0.0))
    crowding_penalty = float(score_weights.get("crowding_penalty", 0.5))
    volatility_penalty = float(score_weights.get("volatility_penalty", 0.3))
    df["score"] = (
        ret_5d_weight * df["rank_ret_5d"]
        + ret_20d_weight * df["rank_ret_20d"]
        - crowding_penalty * df["rank_crowding_score"]
        - volatility_penalty * df["rank_vol_20d"]
    )

    lag_cols = ["ret_5d", "crowding_score", "score", "vol_20d"]
    for col in lag_cols:
        df[f"{col}_signal"] = df.groupby("symbol")[col].shift(1)
    return df.sort_values(["date", "symbol"]).reset_index(drop=True)
