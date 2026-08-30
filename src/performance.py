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
