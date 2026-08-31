"""Weekly ETF backtests with convex portfolio construction and transaction costs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .optimizer import estimate_covariance, optimize_convex_weights


_CONVEX_STRATEGIES = {"momentum_crowding_convex", "momentum_crowding_convex_trend"}


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


def _moving_average(series: pd.Series, window: int) -> pd.Series:
    """Calculate a moving average with robust minimum periods for short windows."""
    return series.rolling(window, min_periods=min(20, window)).mean()


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


def _select_convex_weights(
    scores: pd.Series,
    crowding: pd.Series | None,
    return_history: pd.DataFrame,
    previous: pd.Series,
    config: dict,
    exposure: float,
) -> tuple[pd.Series, dict]:
    """Build convex-optimized weights, with the original selector as a safe fallback."""
    scfg = config["strategy"]
    ocfg = scfg.get("convex_optimizer", {})
    max_weight = float(ocfg.get("max_weight", scfg["max_weight"]))
    all_symbols = scores.index
    finite_scores = pd.to_numeric(scores, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    min_observations = int(ocfg.get("min_covariance_observations", 40))
    counts = return_history.reindex(columns=finite_scores.index).notna().sum()
    eligible = finite_scores.index[counts >= min_observations]

    if len(eligible) == 0:
        fallback = _select_weights(scores, float(scfg["top_quantile"]), max_weight, exposure)
        return fallback, {"status": "fallback_insufficient_history", "target_exposure": float(fallback.sum())}

    eligible_scores = finite_scores.reindex(eligible)
    covariance = estimate_covariance(
        return_history.reindex(columns=eligible),
        shrinkage=float(ocfg.get("covariance_shrinkage", 0.25)),
        ridge=float(ocfg.get("covariance_ridge", 1e-6)),
        annualization_factor=float(ocfg.get("annualization_factor", 252.0)),
    )
    previous_eligible = previous.reindex(eligible).fillna(0.0)
    fixed_turnover = float(previous.drop(index=eligible, errors="ignore").abs().sum())
    eligible_crowding = crowding.reindex(eligible) if crowding is not None else None
    max_turnover_value = ocfg.get("max_turnover")
    max_turnover = None if max_turnover_value is None else float(max_turnover_value)

    try:
        optimized, diagnostics = optimize_convex_weights(
            eligible_scores,
            covariance,
            previous_eligible,
            eligible_crowding,
            exposure=exposure,
            max_weight=max_weight,
            signal_scale=float(ocfg.get("signal_scale", 0.10)),
            risk_aversion=float(ocfg.get("risk_aversion", 4.0)),
            crowding_aversion=float(ocfg.get("crowding_aversion", 0.05)),
            turnover_penalty_bps=float(ocfg.get("turnover_penalty_bps", 10.0)),
            max_turnover=max_turnover,
            allow_cash=bool(ocfg.get("allow_cash", False)),
            max_ex_ante_volatility=(
                None
                if ocfg.get("max_ex_ante_volatility") is None
                else float(ocfg["max_ex_ante_volatility"])
            ),
            fixed_turnover=fixed_turnover,
            solver_tolerance=float(ocfg.get("solver_tolerance", 1e-9)),
            max_iterations=int(ocfg.get("max_iterations", 500)),
        )
    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
        fallback = _select_weights(scores, float(scfg["top_quantile"]), max_weight, exposure)
        return fallback, {
            "status": f"fallback_{type(exc).__name__}",
            "target_exposure": float(fallback.sum()),
        }

    target = pd.Series(0.0, index=all_symbols)
    target.loc[optimized.index] = optimized
    return target, diagnostics


def _target_weights(
    scores: pd.Series,
    crowding: pd.Series | None,
    returns: pd.DataFrame,
    signal_date: pd.Timestamp,
    previous: pd.Series,
    config: dict,
    strategy_name: str,
    exposure: float,
) -> tuple[pd.Series, dict]:
    """Route a rebalance to the legacy selector or the convex optimizer."""
    scfg = config["strategy"]
    if strategy_name not in _CONVEX_STRATEGIES:
        return (
            _select_weights(
                scores,
                float(scfg["top_quantile"]),
                float(scfg["max_weight"]),
                exposure,
            ),
            {},
        )
    covariance_window = int(scfg.get("convex_optimizer", {}).get("covariance_window", 120))
    return _select_convex_weights(
        scores,
        crowding,
        returns.loc[:signal_date].tail(covariance_window),
        previous,
        config,
        exposure,
    )


def _score_column(strategy_name: str) -> str:
    """Map a strategy name to the lagged signal used for selection."""
    return {
        "momentum_top20": "ret_5d_signal",
        "momentum_top_quantile": "ret_5d_signal",
        "crowding_top20": "crowding_score_signal",
        "crowding_top_quantile": "crowding_score_signal",
        "momentum_crowding_penalty": "score_signal",
        "momentum_crowding_penalty_trend": "score_signal",
        "momentum_crowding_convex": "score_signal",
        "momentum_crowding_convex_trend": "score_signal",
    }[strategy_name]


def run_single_strategy(
    factors: pd.DataFrame,
    config: dict,
    strategy_name: str,
    trend_filter: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run a weekly rotation strategy and return NAV, weights, and turnover."""
    scfg = config["strategy"]
    close = _wide_prices(factors, "close")
    raw_returns = close.pct_change(fill_method=None)
    returns = raw_returns.fillna(0.0)
    dates = close.index
    symbols = close.columns
    score_matrix = _wide_prices(factors, _score_column(strategy_name))
    crowding_matrix = _wide_prices(factors, "crowding_score_signal") if "crowding_score_signal" in factors else None
    weekly_dates = _weekly_rebalance_dates(dates)
    benchmark = str(scfg["benchmark_symbol"])
    benchmark_ma = _moving_average(close[benchmark], int(scfg["benchmark_ma_window"])) if benchmark in close else None

    desired = pd.DataFrame(np.nan, index=dates, columns=symbols)
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

        crowding = crowding_matrix.loc[signal_date] if crowding_matrix is not None else None
        target, optimizer_diagnostics = _target_weights(
            score_matrix.loc[signal_date],
            crowding,
            raw_returns,
            signal_date,
            previous,
            config,
            strategy_name,
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
        turnover_row = {"date": trade_date, "turnover": turnover, "transaction_cost": cost, "strategy": strategy_name}
        turnover_row.update({f"optimizer_{key}": value for key, value in optimizer_diagnostics.items()})
        turnover_rows.append(turnover_row)

    weights = desired.ffill().fillna(0.0)
    daily_turnover = pd.DataFrame(turnover_rows).set_index("date") if turnover_rows else pd.DataFrame(columns=["turnover", "transaction_cost", "strategy"])
    strategy_ret = (weights.shift(1).fillna(0.0) * returns).sum(axis=1)
    if not daily_turnover.empty:
        strategy_ret = strategy_ret.sub(daily_turnover["transaction_cost"].reindex(strategy_ret.index).fillna(0.0), fill_value=0.0)
    nav = (1.0 + strategy_ret).cumprod()
    nav_df = pd.DataFrame({"date": dates, "strategy": strategy_name, "return": strategy_ret.values, "nav": nav.values})
    weights_df = pd.DataFrame(rebalance_rows)
    turnover_df = pd.DataFrame(turnover_rows)
    return nav_df, weights_df, turnover_df


def build_daily_weights(factors: pd.DataFrame, config: dict, strategy_name: str, trend_filter: bool = False) -> pd.DataFrame:
    """Return daily held weights for diagnostics and tests."""
    scfg = config["strategy"]
    close = _wide_prices(factors, "close")
    dates = close.index
    symbols = close.columns
    score_matrix = _wide_prices(factors, _score_column(strategy_name))
    raw_returns = close.pct_change(fill_method=None)
    crowding_matrix = _wide_prices(factors, "crowding_score_signal") if "crowding_score_signal" in factors else None
    weekly_dates = _weekly_rebalance_dates(dates)
    benchmark = str(scfg["benchmark_symbol"])
    benchmark_ma = _moving_average(close[benchmark], int(scfg["benchmark_ma_window"])) if benchmark in close else None

    desired = pd.DataFrame(np.nan, index=dates, columns=symbols)
    previous = pd.Series(0.0, index=symbols)
    for signal_date in weekly_dates:
        pos = dates.get_loc(signal_date)
        if pos + 1 >= len(dates):
            continue
        trade_date = dates[pos + 1]
        exposure = float(scfg["risk_on_exposure"])
        if trend_filter and benchmark_ma is not None and close.loc[signal_date, benchmark] < benchmark_ma.loc[signal_date]:
            exposure = float(scfg["risk_off_exposure"])
        crowding = crowding_matrix.loc[signal_date] if crowding_matrix is not None else None
        target, _ = _target_weights(
            score_matrix.loc[signal_date],
            crowding,
            raw_returns,
            signal_date,
            previous,
            config,
            strategy_name,
            exposure,
        )
        desired.loc[trade_date] = target
        previous = target
    return desired.ffill().fillna(0.0)


def run_buy_and_hold(factors: pd.DataFrame, benchmark_symbol: str) -> pd.DataFrame:
    """Build benchmark buy-and-hold NAV from a single symbol close series."""
    close = _wide_prices(factors, "close")
    if benchmark_symbol not in close:
        raise ValueError(f"Benchmark symbol {benchmark_symbol} is missing from panel.")
    ret = close[benchmark_symbol].pct_change(fill_method=None).fillna(0.0)
    return pd.DataFrame({"date": close.index, "strategy": "csi300_etf_buy_hold", "return": ret.values, "nav": (1 + ret).cumprod().values})


def run_equal_weight(factors: pd.DataFrame) -> pd.DataFrame:
    """Average all configured return slots daily, filling unavailable returns with zero."""
    close = _wide_prices(factors, "close")
    returns = close.pct_change(fill_method=None).fillna(0.0)
    ret = returns.mean(axis=1)
    return pd.DataFrame({"date": close.index, "strategy": "all_index_equal_weight", "return": ret.values, "nav": (1 + ret).cumprod().values})


def run_all_backtests(factors: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run all benchmarks and strategy ablations required by the project."""
    navs = [run_buy_and_hold(factors, config["strategy"]["benchmark_symbol"]), run_equal_weight(factors)]
    weight_frames = []
    turnover_frames = []
    for name, trend in [
        ("momentum_top_quantile", False),
        ("crowding_top_quantile", False),
        ("momentum_crowding_penalty", False),
        ("momentum_crowding_penalty_trend", True),
        ("momentum_crowding_convex", False),
        ("momentum_crowding_convex_trend", True),
    ]:
        nav, weights, turnover = run_single_strategy(factors, config, name, trend_filter=trend)
        navs.append(nav)
        weight_frames.append(weights)
        turnover_frames.append(turnover)

    nav_df = pd.concat(navs, ignore_index=True)
    weights_df = pd.concat(weight_frames, ignore_index=True) if weight_frames else pd.DataFrame()
    turnover_df = pd.concat(turnover_frames, ignore_index=True) if turnover_frames else pd.DataFrame()
    return nav_df, weights_df, turnover_df
