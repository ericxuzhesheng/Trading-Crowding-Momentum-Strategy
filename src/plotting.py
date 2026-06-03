"""Plotting helpers for strategy diagnostics and reports."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def _save_current(path: Path) -> None:
    """Save and close the active matplotlib figure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def plot_nav(nav_df: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot strategy NAV comparison."""
    plt.figure(figsize=(12, 6))
    sns.lineplot(data=nav_df, x="date", y="nav", hue="strategy")
    plt.title("NAV Comparison")
    _save_current(Path(figures_dir) / "nav_comparison.png")


def plot_drawdown(nav_df: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot drawdown curves for each strategy."""
    dd = nav_df.copy()
    dd["drawdown"] = dd.groupby("strategy")["nav"].transform(lambda s: s / s.cummax() - 1)
    plt.figure(figsize=(12, 6))
    sns.lineplot(data=dd, x="date", y="drawdown", hue="strategy")
    plt.title("Drawdown")
    _save_current(Path(figures_dir) / "drawdown.png")


def plot_yearly_returns(yearly: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot annual returns by strategy."""
    if yearly.empty:
        return
    plt.figure(figsize=(12, 6))
    sns.barplot(data=yearly, x="year", y="return", hue="strategy")
    plt.title("Annual Returns")
    _save_current(Path(figures_dir) / "yearly_returns.png")


def plot_monthly_heatmap(monthly: pd.DataFrame, figures_dir: str | Path, strategy: str) -> None:
    """Plot monthly return heatmap for one selected strategy."""
    selected = monthly[monthly["strategy"] == strategy].copy()
    if selected.empty:
        return
    selected["year"] = selected["month"].str.slice(0, 4)
    selected["mon"] = selected["month"].str.slice(5, 7)
    pivot = selected.pivot(index="year", columns="mon", values="return")
    plt.figure(figsize=(10, 5))
    sns.heatmap(pivot, annot=True, fmt=".1%", cmap="RdYlGn", center=0)
    plt.title(f"Monthly Returns - {strategy}")
    _save_current(Path(figures_dir) / "monthly_return_heatmap.png")


def plot_holding_count(weights: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot number of holdings at each rebalance."""
    if weights.empty:
        return
    counts = weights.groupby(["date", "strategy"])["symbol"].nunique().reset_index(name="holding_count")
    plt.figure(figsize=(12, 5))
    sns.lineplot(data=counts, x="date", y="holding_count", hue="strategy")
    plt.title("Holding Count")
    _save_current(Path(figures_dir) / "holding_count.png")


def plot_turnover(turnover: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot portfolio turnover by rebalance date."""
    if turnover.empty:
        return
    plt.figure(figsize=(12, 5))
    sns.lineplot(data=turnover, x="date", y="turnover", hue="strategy")
    plt.title("Turnover")
    _save_current(Path(figures_dir) / "turnover.png")


def plot_factor_ic(factors: pd.DataFrame, figures_dir: str | Path) -> pd.DataFrame:
    """Calculate and plot daily cross-sectional IC between score signal and next return."""
    df = factors.copy().sort_values(["symbol", "date"])
    df["next_return"] = df.groupby("symbol")["daily_return"].shift(-1)
    rows = []
    for date, group in df.groupby("date"):
        valid = group[["score_signal", "next_return"]].dropna()
        if len(valid) >= 5:
            rows.append({"date": date, "ic": valid["score_signal"].corr(valid["next_return"], method="spearman")})
    ic = pd.DataFrame(rows)
    if not ic.empty:
        plt.figure(figsize=(12, 5))
        sns.lineplot(data=ic, x="date", y="ic")
        plt.axhline(0, color="black", linewidth=1)
        plt.title("Factor IC")
        _save_current(Path(figures_dir) / "factor_ic.png")
    return ic


def make_all_plots(nav_df: pd.DataFrame, weights: pd.DataFrame, turnover: pd.DataFrame, factors: pd.DataFrame, monthly: pd.DataFrame, yearly: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Generate all configured figures and return IC diagnostics."""
    figures_dir = config["outputs"]["figures_dir"]
    plot_nav(nav_df, figures_dir)
    plot_drawdown(nav_df, figures_dir)
    plot_yearly_returns(yearly, figures_dir)
    plot_monthly_heatmap(monthly, figures_dir, "momentum_crowding_penalty_trend")
    plot_holding_count(weights, figures_dir)
    plot_turnover(turnover, figures_dir)
    return plot_factor_ic(factors, figures_dir)
