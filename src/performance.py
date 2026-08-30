"""Performance analytics for strategy backtests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(nav: pd.Series) -> float:
    """Calculate maximum drawdown from a NAV series."""
    running_max = nav.cummax()
    drawdown = nav / running_max - 1.0
    return float(drawdown.min())


def monthly_return(nav_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate month-end returns for each strategy."""
    out = []
    for strategy, group in nav_df.groupby("strategy"):
        monthly_nav = group.set_index("date")["nav"].resample("ME").last()
        ret = monthly_nav.pct_change().dropna()
        out.extend({"month": idx.strftime("%Y-%m"), "strategy": strategy, "return": value} for idx, value in ret.items())
    return pd.DataFrame(out)


def annual_return_by_year(nav_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate calendar-year returns for each strategy."""
    out = []
    for strategy, group in nav_df.groupby("strategy"):
        yearly_nav = group.set_index("date")["nav"].resample("YE").last()
        ret = yearly_nav.pct_change().dropna()
        out.extend({"year": idx.year, "strategy": strategy, "return": value} for idx, value in ret.items())
    return pd.DataFrame(out)


def summarize_performance(
    nav_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    risk_free_rate: float = 0.0,
) -> pd.DataFrame:
    """Create performance metrics using arithmetic daily excess-return Sharpe."""
    if risk_free_rate <= -1.0:
        raise ValueError("risk_free_rate must be greater than -100%.")
    daily_risk_free_rate = (1.0 + float(risk_free_rate)) ** (1.0 / 252.0) - 1.0
    rows = []
    for strategy, group in nav_df.groupby("strategy"):
        group = group.sort_values("date")
        returns = group["return"].fillna(0.0)
        nav = group["nav"]
        years = max((group["date"].max() - group["date"].min()).days / 365.25, 1 / 252)
        ann_return = nav.iloc[-1] ** (1 / years) - 1
        ann_vol = returns.std(ddof=0) * np.sqrt(252)
        daily_vol = returns.std(ddof=0)
        sharpe = (returns.mean() - daily_risk_free_rate) / daily_vol * np.sqrt(252) if daily_vol > 0 else np.nan
        mdd = max_drawdown(nav)
        strategy_turnover = turnover_df[turnover_df["strategy"] == strategy] if not turnover_df.empty and "strategy" in turnover_df else pd.DataFrame()
        rows.append(
            {
                "strategy": strategy,
                "annual_return": ann_return,
                "annual_volatility": ann_vol,
                "sharpe": sharpe,
                "return_over_volatility": ann_return / ann_vol if ann_vol > 0 else np.nan,
                "max_drawdown": mdd,
                "calmar": ann_return / abs(mdd) if mdd < 0 else np.nan,
                "win_rate": float((returns > 0).mean()),
                "average_turnover": float(strategy_turnover["turnover"].mean()) if not strategy_turnover.empty else 0.0,
                "total_transaction_cost": float(strategy_turnover["transaction_cost"].sum()) if not strategy_turnover.empty else 0.0,
                "final_nav": float(nav.iloc[-1]),
            }
        )
    return pd.DataFrame(rows).sort_values("strategy").reset_index(drop=True)


def summarize_period_performance(
    nav_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    *,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    risk_free_rate: float = 0.0,
) -> pd.DataFrame:
    """Rebase NAV and summarize a requested date interval."""
    period_nav = nav_df.copy()
    period_turnover = turnover_df.copy()
    if start is not None:
        start_date = pd.Timestamp(start)
        period_nav = period_nav[period_nav["date"] >= start_date]
        period_turnover = period_turnover[period_turnover["date"] >= start_date]
    if end is not None:
        end_date = pd.Timestamp(end)
        period_nav = period_nav[period_nav["date"] <= end_date]
        period_turnover = period_turnover[period_turnover["date"] <= end_date]
    if period_nav.empty:
        return pd.DataFrame()
    period_nav = period_nav.copy()
    period_nav["nav"] = period_nav.groupby("strategy")["return"].transform(lambda values: (1.0 + values).cumprod())
    return summarize_performance(period_nav, period_turnover, risk_free_rate=risk_free_rate)


def transaction_cost_sensitivity(
    nav_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    *,
    strategy: str,
    base_cost_bps: float,
    scenarios_bps: list[float] | tuple[float, ...],
    risk_free_rate: float = 0.0,
) -> pd.DataFrame:
    """Reprice one strategy under alternative per-notional costs with fixed weights.

    Turnover is the full L1 traded notional, so replacing one fully invested
    portfolio with another can reach 2.0 and naturally charges both trade legs.
    """
    base_cost = float(base_cost_bps)
    scenarios = sorted({float(value) for value in scenarios_bps})
    if not np.isfinite(base_cost) or any(not np.isfinite(value) for value in scenarios):
        raise ValueError("Transaction-cost assumptions must be finite.")
    if base_cost < 0.0 or any(value < 0.0 for value in scenarios):
        raise ValueError("Transaction-cost assumptions must be non-negative.")
    if not scenarios:
        raise ValueError("At least one transaction-cost scenario is required.")

    selected_nav = nav_df[nav_df["strategy"] == strategy].copy()
    if selected_nav.empty:
        raise ValueError(f"Strategy '{strategy}' is missing from the NAV table.")
    selected_nav["date"] = pd.to_datetime(selected_nav["date"])
    selected_nav = selected_nav.sort_values("date")
    if selected_nav["date"].duplicated().any():
        raise ValueError(f"Strategy '{strategy}' has duplicate NAV dates.")
    required_turnover_columns = {"date", "strategy", "turnover"}
    if not turnover_df.empty and not required_turnover_columns.issubset(turnover_df.columns):
        missing = sorted(required_turnover_columns.difference(turnover_df.columns))
        raise ValueError(f"Turnover table is missing required columns: {missing}")

    selected_turnover = turnover_df[turnover_df["strategy"] == strategy].copy()
    if selected_turnover.empty:
        daily_costs = pd.DataFrame(columns=["date", "turnover", "recorded_transaction_cost"])
    else:
        selected_turnover["date"] = pd.to_datetime(selected_turnover["date"])
        selected_turnover["turnover"] = pd.to_numeric(selected_turnover["turnover"], errors="coerce")
        if not np.isfinite(selected_turnover["turnover"]).all():
            raise ValueError("L1 turnover must contain only finite values.")
        if (selected_turnover["turnover"] < 0.0).any():
            raise ValueError("L1 turnover must be non-negative.")
        if "transaction_cost" in selected_turnover:
            selected_turnover["recorded_transaction_cost"] = pd.to_numeric(
                selected_turnover["transaction_cost"], errors="coerce"
            ).fillna(selected_turnover["turnover"] * base_cost / 10000.0)
        else:
            selected_turnover["recorded_transaction_cost"] = selected_turnover["turnover"] * base_cost / 10000.0
        daily_costs = (
            selected_turnover.groupby("date", as_index=False)[["turnover", "recorded_transaction_cost"]]
            .sum()
            .sort_values("date")
        )
        unknown_dates = daily_costs.loc[~daily_costs["date"].isin(selected_nav["date"]), "date"]
        if not unknown_dates.empty:
            raise ValueError("Turnover table contains dates outside the selected NAV series.")
        expected_cost = daily_costs["turnover"] * base_cost / 10000.0
        if not np.allclose(
            daily_costs["recorded_transaction_cost"],
            expected_cost,
            rtol=1e-9,
            atol=1e-12,
        ):
            raise ValueError("Recorded transaction costs do not match base_cost_bps and L1 turnover.")

    repriced = selected_nav.merge(daily_costs, on="date", how="left")
    repriced[["turnover", "recorded_transaction_cost"]] = repriced[
        ["turnover", "recorded_transaction_cost"]
    ].fillna(0.0)
    gross_return = repriced["return"].fillna(0.0) + repriced["recorded_transaction_cost"]

    rows = []
    for cost_bps in scenarios:
        scenario_return = gross_return - repriced["turnover"] * cost_bps / 10000.0
        if (scenario_return <= -1.0).any():
            raise ValueError(f"The {cost_bps:g} bps scenario contains a daily return at or below -100%.")
        scenario_nav = repriced[["date", "strategy"]].copy()
        scenario_nav["return"] = scenario_return
        scenario_nav["nav"] = (1.0 + scenario_return).cumprod()

        scenario_turnover = daily_costs[["date", "turnover"]].copy()
        scenario_turnover["strategy"] = strategy
        scenario_turnover["transaction_cost"] = scenario_turnover["turnover"] * cost_bps / 10000.0
        metrics = summarize_performance(
            scenario_nav,
            scenario_turnover,
            risk_free_rate=risk_free_rate,
        ).iloc[0]
        rows.append(
            {
                "strategy": strategy,
                "transaction_cost_bps": cost_bps,
                "is_base_case": bool(np.isclose(cost_bps, base_cost)),
                "annual_return": metrics["annual_return"],
                "annual_volatility": metrics["annual_volatility"],
                "sharpe": metrics["sharpe"],
                "return_over_volatility": metrics["return_over_volatility"],
                "max_drawdown": metrics["max_drawdown"],
                "calmar": metrics["calmar"],
                "win_rate": metrics["win_rate"],
                "average_turnover": metrics["average_turnover"],
                "total_transaction_cost": metrics["total_transaction_cost"],
                "final_nav": metrics["final_nav"],
            }
        )
    return pd.DataFrame(rows)
