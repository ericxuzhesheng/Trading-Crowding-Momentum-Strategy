"""Plotting helpers for strategy diagnostics and reports."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from .strategy_metadata import strategy_label


def _save_current(path: Path) -> None:
    """Save and close the active matplotlib figure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def plot_nav(nav_df: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot strategy NAV comparison."""
    plot_data = nav_df.assign(strategy_label=nav_df["strategy"].map(strategy_label))
    plt.figure(figsize=(12, 6))
    ax = sns.lineplot(data=plot_data, x="date", y="nav", hue="strategy_label")
    plt.title("NAV Comparison")
    ax.set(xlabel="Date", ylabel="Net Asset Value")
    ax.legend(title="Strategy")
    _save_current(Path(figures_dir) / "nav_comparison.png")


def plot_drawdown(nav_df: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot drawdown curves for each strategy."""
    dd = nav_df.copy()
    dd["drawdown"] = dd.groupby("strategy")["nav"].transform(lambda s: s / s.cummax() - 1)
    dd["strategy_label"] = dd["strategy"].map(strategy_label)
    plt.figure(figsize=(12, 6))
    ax = sns.lineplot(data=dd, x="date", y="drawdown", hue="strategy_label")
    plt.title("Drawdown")
    ax.set(xlabel="Date", ylabel="Drawdown")
    ax.legend(title="Strategy")
    _save_current(Path(figures_dir) / "drawdown.png")


def plot_yearly_returns(yearly: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot annual returns by strategy."""
    if yearly.empty:
        return
    plot_data = yearly.assign(strategy_label=yearly["strategy"].map(strategy_label))
    plt.figure(figsize=(12, 6))
    ax = sns.barplot(data=plot_data, x="year", y="return", hue="strategy_label")
    plt.title("Annual Returns")
    ax.set(xlabel="Year", ylabel="Return")
    ax.legend(title="Strategy")
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
    ax = sns.heatmap(
        pivot,
        annot=True,
        fmt=".1%",
        cmap="RdYlGn",
        center=0,
        cbar_kws={"label": "Return"},
    )
    plt.title(f"Monthly Returns - {strategy_label(strategy)}")
    ax.set(xlabel="Month", ylabel="Year")
    _save_current(Path(figures_dir) / "monthly_return_heatmap.png")


def plot_holding_count(weights: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot number of holdings at each rebalance."""
    if weights.empty:
        return
    counts = weights.groupby(["date", "strategy"])["symbol"].nunique().reset_index(name="holding_count")
    counts["strategy_label"] = counts["strategy"].map(strategy_label)
    plt.figure(figsize=(12, 5))
    ax = sns.lineplot(data=counts, x="date", y="holding_count", hue="strategy_label")
    plt.title("Holding Count")
    ax.set(xlabel="Date", ylabel="Number of Holdings")
    ax.legend(title="Strategy")
    _save_current(Path(figures_dir) / "holding_count.png")


def plot_turnover(turnover: pd.DataFrame, figures_dir: str | Path) -> None:
    """Plot portfolio turnover by rebalance date."""
    if turnover.empty:
        return
    plot_data = turnover.assign(strategy_label=turnover["strategy"].map(strategy_label))
    plt.figure(figsize=(12, 5))
    ax = sns.lineplot(data=plot_data, x="date", y="turnover", hue="strategy_label")
    plt.title("Turnover")
    ax.set(xlabel="Date", ylabel="One-Way Turnover")
    ax.legend(title="Strategy")
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
        ax = sns.lineplot(data=ic, x="date", y="ic")
        plt.axhline(0, color="black", linewidth=1)
        plt.title("Factor IC")
        ax.set(xlabel="Date", ylabel="Spearman IC")
        _save_current(Path(figures_dir) / "factor_ic.png")
    return ic


def make_all_plots(nav_df: pd.DataFrame, weights: pd.DataFrame, turnover: pd.DataFrame, factors: pd.DataFrame, monthly: pd.DataFrame, yearly: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Generate all configured figures and return IC diagnostics."""
    figures_dir = config["outputs"]["figures_dir"]
    plot_nav(nav_df, figures_dir)
    plot_drawdown(nav_df, figures_dir)
    plot_yearly_returns(yearly, figures_dir)
    plot_monthly_heatmap(monthly, figures_dir, config["strategy"].get("primary_strategy", "momentum_crowding_convex"))
    plot_holding_count(weights, figures_dir)
    plot_turnover(turnover, figures_dir)
    return plot_factor_ic(factors, figures_dir)
