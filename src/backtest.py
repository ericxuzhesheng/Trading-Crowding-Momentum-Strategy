"""Weekly rotation backtest engine with transaction costs and trend filtering."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_transaction_cost(turnover: float, cost_bps: float) -> float:
    """Calculate one-way transaction cost from portfolio turnover and bps cost."""
    return float(turnover) * float(cost_bps) / 10000.0


def _wide_prices(factors: pd.DataFrame, field: str) -> pd.DataFrame:
    """Pivot a long panel field into a date by symbol matrix."""
    return factors.pivot(index="date", columns="symbol", values=field).sort_index()


def _weekly_rebalance_dates(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Select the last available trading date in each calendar week."""
    date_series = pd.Series(dates, index=dates)
    return pd.DatetimeIndex(date_series.groupby(date_series.index.to_period("W-FRI")).max().dropna())


def _select_weights(scores: pd.Series, top_quantile: float, max_weight: float, exposure: float) -> pd.Series:
    """Build capped equal weights from top-ranked scores."""
    valid = scores.dropna().sort_values(ascending=False)
    if valid.empty:
        return scores.fillna(0.0)
    n_select = max(1, int(np.ceil(len(valid) * top_quantile)))
    selected = valid.iloc[:n_select].index
    raw_weight = min(1.0 / n_select, max_weight)
    weights = pd.Series(0.0, index=scores.index)
    weights.loc[selected] = raw_weight
    total = weights.sum()
    if total > 0:
        weights = weights / total * min(exposure, total)
    return weights


def _score_column(strategy_name: str) -> str:
    """Map a strategy name to the lagged signal used for selection."""
    return {
        "momentum_top20": "ret_5d_signal",
        "crowding_top20": "crowding_score_signal",
        "momentum_crowding_penalty": "score_signal",
        "momentum_crowding_penalty_trend": "score_signal",
    }[strategy_name]


def run_single_strategy(
    factors: pd.DataFrame,
    config: dict,
    strategy_name: str,
    trend_filter: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run a weekly top-quantile rotation strategy and return NAV, weights, and turnover."""
    scfg = config["strategy"]
    close = _wide_prices(factors, "close")
    returns = close.pct_change().fillna(0.0)
    dates = close.index
    symbols = close.columns
    score_matrix = _wide_prices(factors, _score_column(strategy_name))
    weekly_dates = _weekly_rebalance_dates(dates)
    benchmark = str(scfg["benchmark_symbol"])
    benchmark_ma = close[benchmark].rolling(int(scfg["benchmark_ma_window"]), min_periods=20).mean() if benchmark in close else None

    desired = pd.DataFrame(0.0, index=dates, columns=symbols)
    rebalance_rows = []
    turnover_rows = []
    previous = pd.Series(0.0, index=symbols)

    for signal_date in weekly_dates:
        pos = dates.get_loc(signal_date)
        if pos + 1 >= len(dates):
            continue
        trade_date = dates[pos + 1]
        exposure = float(scfg["risk_on_exposure"])
        if trend_filter and benchmark_ma is not None and close.loc[signal_date, benchmark] < benchmark_ma.loc[signal_date]:
            exposure = float(scfg["risk_off_exposure"])

        target = _select_weights(
            score_matrix.loc[signal_date],
            float(scfg["top_quantile"]),
            float(scfg["max_weight"]),
            exposure,
        )
        turnover = (target - previous).abs().sum()
        cost = calculate_transaction_cost(turnover, float(scfg["transaction_cost_bps"]))
        desired.loc[trade_date] = target
        previous = target
        rebalance_rows.extend(
            {"date": trade_date, "symbol": symbol, "weight": weight, "strategy": strategy_name}
            for symbol, weight in target[target > 0].items()
        )
        turnover_rows.append({"date": trade_date, "turnover": turnover, "transaction_cost": cost, "strategy": strategy_name})

    weights = desired.replace(0.0, np.nan).ffill().fillna(0.0)
    daily_turnover = pd.DataFrame(turnover_rows).set_index("date") if turnover_rows else pd.DataFrame(columns=["turnover", "transaction_cost", "strategy"])
    strategy_ret = (weights.shift(1).fillna(0.0) * returns).sum(axis=1)
    if not daily_turnover.empty:
        strategy_ret = strategy_ret.sub(daily_turnover["transaction_cost"].reindex(strategy_ret.index).fillna(0.0), fill_value=0.0)
    nav = (1.0 + strategy_ret).cumprod()
    nav_df = pd.DataFrame({"date": dates, "strategy": strategy_name, "return": strategy_ret.values, "nav": nav.values})
    weights_df = pd.DataFrame(rebalance_rows)
    turnover_df = pd.DataFrame(turnover_rows)
    return nav_df, weights_df, turnover_df


def run_buy_and_hold(factors: pd.DataFrame, benchmark_symbol: str) -> pd.DataFrame:
    """Build benchmark buy-and-hold NAV from a single symbol close series."""
    close = _wide_prices(factors, "close")
    if benchmark_symbol not in close:
        raise ValueError(f"Benchmark symbol {benchmark_symbol} is missing from panel.")
    ret = close[benchmark_symbol].pct_change().fillna(0.0)
    return pd.DataFrame({"date": close.index, "strategy": "hs300_buy_hold", "return": ret.values, "nav": (1 + ret).cumprod().values})


def run_equal_weight(factors: pd.DataFrame) -> pd.DataFrame:
    """Build an all-index equal-weight daily rebalanced benchmark."""
    close = _wide_prices(factors, "close")
    returns = close.pct_change().fillna(0.0)
    ret = returns.mean(axis=1)
    return pd.DataFrame({"date": close.index, "strategy": "all_index_equal_weight", "return": ret.values, "nav": (1 + ret).cumprod().values})


def run_all_backtests(factors: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run all benchmarks and strategy ablations required by the project."""
    navs = [run_buy_and_hold(factors, config["strategy"]["benchmark_symbol"]), run_equal_weight(factors)]
    weight_frames = []
    turnover_frames = []
    for name, trend in [
        ("momentum_top20", False),
        ("crowding_top20", False),
        ("momentum_crowding_penalty", False),
        ("momentum_crowding_penalty_trend", True),
    ]:
        nav, weights, turnover = run_single_strategy(factors, config, name, trend_filter=trend)
        navs.append(nav)
        weight_frames.append(weights)
        turnover_frames.append(turnover)

    nav_df = pd.concat(navs, ignore_index=True)
    weights_df = pd.concat(weight_frames, ignore_index=True) if weight_frames else pd.DataFrame()
    turnover_df = pd.concat(turnover_frames, ignore_index=True) if turnover_frames else pd.DataFrame()
    return nav_df, weights_df, turnover_df
