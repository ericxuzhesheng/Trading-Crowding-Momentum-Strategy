"""Holding-period IC and a matched crowding ablation, using the existing engine."""
from copy import deepcopy

import numpy as np
import pandas as pd

from .backtest import _weekly_rebalance_dates, run_single_strategy
from .factors import add_factors
from .performance import summarize_period_performance


def matched_factors(panel, config):
    baseline = add_factors(panel, config)
    without_config = deepcopy(config)
    without_config["factors"].setdefault("score_weights", {})["crowding_penalty"] = 0.0
    without_config["strategy"].setdefault("convex_optimizer", {})["crowding_aversion"] = 0.0
    without = add_factors(panel, without_config)
    # Removing a factor must not change the available universe or warm-up period.
    for column in ("score", "score_signal"):
        without.loc[baseline[column].isna(), column] = np.nan
    return baseline, without, without_config


def holding_period_ic(factors, min_assets=5):
    """Match the engine: lagged score at week-end, next close to next rebalance close.

    The engine sets weights on the next available trading date and applies
    weights.shift(1) to close returns. These are executable-period diagnostics
    under that convention, not Friday-close to Friday-close returns.
    """
    close = factors.pivot(index="date", columns="symbol", values="close").sort_index()
    score = factors.pivot(index="date", columns="symbol", values="score_signal").reindex(close.index)
    dates = close.index
    decisions = _weekly_rebalance_dates(dates)
    rows = []
    for decision, next_decision in zip(decisions[:-1], decisions[1:]):
        entry_pos = dates.get_loc(decision) + 1
        exit_pos = dates.get_loc(next_decision) + 1
        if exit_pos >= len(dates):
            continue  # No observed endpoint: never turn a partial week into a full one.
        future = close.iloc[exit_pos] / close.iloc[entry_pos] - 1.0
        complete = close.iloc[entry_pos:exit_pos + 1].notna().all()
        valid = complete & np.isfinite(future) & np.isfinite(score.loc[decision])
        x, y = score.loc[decision, valid], future.loc[valid]
        ic = x.corr(y, method="spearman") if len(x) >= min_assets and x.nunique() > 1 and y.nunique() > 1 else np.nan
        rows.append({"signal_date": decision, "entry_date": dates[entry_pos],
                     "exit_date": dates[exit_pos], "assets": int(valid.sum()), "spearman_ic": ic})
    return pd.DataFrame(rows, columns=["signal_date", "entry_date", "exit_date", "assets", "spearman_ic"])


def run_matched_ablation(panel, config):
    baseline, without, without_config = matched_factors(panel, config)
    summaries, navs, turnovers, ics = [], [], [], []
    split = pd.Timestamp(config.get("performance", {}).get("validation_split_date", "2023-01-01"))
    for label, factors, settings in (("with_crowding", baseline, config),
                                     ("without_crowding", without, without_config)):
        nav, _, turnover = run_single_strategy(factors, settings, "momentum_crowding_convex")
        nav["strategy"] = label
        turnover["strategy"] = label
        navs.append(nav)
        turnovers.append(turnover)
        for period, start, end in (("full", None, None), ("earlier", None, split - pd.Timedelta(days=1)),
                                    ("later", split, None)):
            summary = summarize_period_performance(nav, turnover, start=start, end=end,
                risk_free_rate=float(config.get("performance", {}).get("risk_free_rate", 0)))
            if not summary.empty:
                summary.insert(0, "period", period)
                summaries.append(summary)
        ic = holding_period_ic(factors)
        ic.insert(0, "strategy", label)
        ics.append(ic)
    return pd.concat(summaries, ignore_index=True), pd.concat(navs, ignore_index=True), pd.concat(turnovers, ignore_index=True), pd.concat(ics, ignore_index=True)
