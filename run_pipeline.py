"""Command-line entry point for the trading crowding momentum strategy pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.backtest import run_all_backtests
from src.data_loader import download_panel
from src.factors import add_factors
from src.performance import (
    annual_return_by_year,
    monthly_return,
    summarize_performance,
    summarize_period_performance,
    transaction_cost_sensitivity,
)
from src.plotting import make_all_plots
from src.strategy_metadata import strategy_label
from src.utils import ensure_directories, load_config, setup_logging


def _write_report(
    config: dict,
    summary: pd.DataFrame,
    nav: pd.DataFrame,
    turnover: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    failures_path: Path | None = None,
) -> None:
    """Write a compact Markdown backtest report."""
    report_path = Path(config["outputs"]["reports_dir"]) / "backtest_report.md"
    primary = config["strategy"].get("primary_strategy", "momentum_crowding_convex")
    risk_free_rate = float(config.get("performance", {}).get("risk_free_rate", 0.0))
    split_date = pd.Timestamp(config.get("performance", {}).get("validation_split_date", "2023-01-01"))
    display_summary = summary.copy()
    turnover_untracked = {"all_index_equal_weight", "csi300_etf_buy_hold"}
    display_summary.loc[
        display_summary["strategy"].isin(turnover_untracked), "average_turnover"
    ] = pd.NA
    display_summary["strategy"] = display_summary["strategy"].map(strategy_label)
    display_columns = [
        "strategy",
        "annual_return",
        "annual_volatility",
        "sharpe",
        "max_drawdown",
        "average_turnover",
        "final_nav",
    ]
    performance_display = display_summary[display_columns].rename(
        columns={
            "strategy": "Strategy",
            "annual_return": "Annual Return",
            "annual_volatility": "Annual Vol",
            "sharpe": "Sharpe",
            "max_drawdown": "Max Drawdown",
            "average_turnover": "Average Turnover",
            "final_nav": "Final NAV",
        }
    )
    performance_display["Annual Return"] = performance_display["Annual Return"].map(
        lambda value: f"{value:.2%}"
    )
    performance_display["Annual Vol"] = performance_display["Annual Vol"].map(
        lambda value: f"{value:.2%}"
    )
    performance_display["Sharpe"] = performance_display["Sharpe"].map(lambda value: f"{value:.3f}")
    performance_display["Max Drawdown"] = performance_display["Max Drawdown"].map(
        lambda value: f"{value:.2%}"
    )
    performance_display["Average Turnover"] = performance_display["Average Turnover"].map(
        lambda value: "N/A" if pd.isna(value) else f"{value:.3f}"
    )
    performance_display["Final NAV"] = performance_display["Final NAV"].map(lambda value: f"{value:.3f}")
    earlier = summarize_period_performance(
        nav,
        turnover,
        end=split_date - pd.Timedelta(days=1),
        risk_free_rate=risk_free_rate,
    )
    later = summarize_period_performance(
        nav,
        turnover,
        start=split_date,
        risk_free_rate=risk_free_rate,
    )
    validation_rows = []
    split_label = split_date.strftime("%Y-%m-%d")
    for label, frame in [(f"Before {split_label}", earlier), (f"From {split_label}", later)]:
        selected = frame[frame["strategy"] == primary]
        if not selected.empty:
            row = selected.iloc[0]
            validation_rows.append(
                {
                    "period": label,
                    "annual_return": row["annual_return"],
                    "annual_volatility": row["annual_volatility"],
                    "sharpe": row["sharpe"],
                    "max_drawdown": row["max_drawdown"],
                }
            )
    validation = pd.DataFrame(validation_rows)
    validation_display = validation.copy()
    if not validation_display.empty:
        validation_display = validation_display.rename(
            columns={
                "period": "Period",
                "annual_return": "Annual Return",
                "annual_volatility": "Annual Vol",
                "sharpe": "Sharpe",
                "max_drawdown": "Max Drawdown",
            }
        )
        validation_display["Annual Return"] = validation_display["Annual Return"].map(
            lambda value: f"{value:.2%}"
        )
        validation_display["Annual Vol"] = validation_display["Annual Vol"].map(
            lambda value: f"{value:.2%}"
        )
        validation_display["Sharpe"] = validation_display["Sharpe"].map(lambda value: f"{value:.3f}")
        validation_display["Max Drawdown"] = validation_display["Max Drawdown"].map(
            lambda value: f"{value:.2%}"
        )
    cost_display = pd.DataFrame(
        {
            "Cost per Traded Notional": cost_sensitivity["transaction_cost_bps"].map(lambda value: f"{value:g} bps"),
            "Case": cost_sensitivity["is_base_case"].map({True: "Base", False: "Scenario"}),
            "Annual Return": cost_sensitivity["annual_return"].map(lambda value: f"{value:.2%}"),
            "Annual Vol": cost_sensitivity["annual_volatility"].map(lambda value: f"{value:.2%}"),
            "Sharpe": cost_sensitivity["sharpe"].map(lambda value: f"{value:.3f}"),
            "Max Drawdown": cost_sensitivity["max_drawdown"].map(lambda value: f"{value:.2%}"),
            "Final NAV": cost_sensitivity["final_nav"].map(lambda value: f"{value:.3f}"),
        }
    )
    optimizer_config = config["strategy"].get("convex_optimizer", {})
    primary_turnover = turnover[turnover["strategy"] == primary]
    solver_note = "Solver status was not available in the turnover output."
    if "optimizer_status" in primary_turnover.columns:
        status = primary_turnover["optimizer_status"].fillna("")
        solver_note = (
            f"The optimizer solved {(status == 'solved').sum()} of {len(primary_turnover)} rebalance dates. "
            f"A deterministic insufficient-history fallback handled "
            f"{(status == 'fallback_insufficient_history').sum()} dates."
        )
    lines = [
        "# Research Backtest Report",
        "",
        "This report is generated by `python run_pipeline.py --config config.yaml`.",
        "",
        f"The main experiment is **{strategy_label(primary)}** (`{primary}`).",
        "All results below are historical backtests within the tracked design, not a live-performance record.",
        solver_note,
        "",
        "Sharpe uses annualized arithmetic daily excess returns under "
        f"`sqrt(252) * mean(r - rf_daily) / std(r)`, with annual risk-free rate {risk_free_rate:.2%}.",
        "",
        "## Performance Summary",
        "",
        performance_display.to_markdown(index=False, floatfmt=".3f"),
        "",
        "The Configured-Universe EW Reference averages all configured return slots each day, fills unavailable "
        "returns with zero, and does not estimate turnover or costs. Benchmark turnover shown as N/A was not modeled.",
        "",
        "## Temporal Split Diagnostics",
        "",
        validation_display.to_markdown(index=False, floatfmt=".3f")
        if not validation_display.empty
        else "No temporal split rows were available.",
        "",
        "This is a single descriptive time split. It does not establish a frozen or fully untouched out-of-sample test.",
        "",
        "## Transaction-Cost Sensitivity",
        "",
        cost_display.to_markdown(index=False, floatfmt=".3f"),
        "",
        "Each rate is charged per unit of gross L1 traded notional. A complete switch from one fully invested "
        "portfolio to another has L1 turnover of 2.0 and therefore charges both sell and buy legs.",
        "",
        "The scenarios hold signals and target weights fixed under the current backtest convention. They reprice "
        "scheduled target changes without re-optimizing the portfolio.",
        "",
        "## Convex Optimizer Defaults",
        "",
        f"- **Maximum single-instrument weight** {float(optimizer_config.get('max_weight', config['strategy']['max_weight'])):.0%}",
        f"- **Covariance window and shrinkage** {int(optimizer_config.get('covariance_window', 120))} days and {float(optimizer_config.get('covariance_shrinkage', 0.1)):.0%}",
        f"- **Risk aversion** {float(optimizer_config.get('risk_aversion', 4.0)):g}",
        f"- **L1 turnover regularization** {float(optimizer_config.get('turnover_penalty_bps', 0.0)):g} bp-equivalent, used as a stability regularizer and separate from realized trading cost",
        f"- **Base execution-cost assumption** {float(config['strategy']['transaction_cost_bps']):g} bps per traded notional",
        "",
        "## Data Diagnostics",
        "",
    ]
    if failures_path and failures_path.exists():
        lines.append(f"Some symbols failed to download. See `{failures_path.as_posix()}` and `outputs/reports/pipeline.log`.")
    else:
        lines.append(
            "No symbol-level failure file was present for the data snapshot used by this report. Individual provider "
            "attempts may still have failed before a fallback source succeeded."
        )
    lines.extend(
        [
            "",
            "## Generated Figures",
            "",
            "- `outputs/figures/nav_comparison.png`",
            "- `outputs/figures/drawdown.png`",
            "- `outputs/figures/yearly_returns.png`",
            "- `outputs/figures/monthly_return_heatmap.png`",
            "- `outputs/figures/holding_count.png`",
            "- `outputs/figures/turnover.png`",
            "- `outputs/figures/transaction_cost_sensitivity.png`",
            "- `outputs/figures/factor_ic.png` when enough cross-sectional observations exist",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Run the full data, factor, backtest, analytics, plotting, and report pipeline."""
    parser = argparse.ArgumentParser(description="Trading crowding momentum strategy research pipeline.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config.")
    args = parser.parse_args()

    config = load_config(args.config)
    ensure_directories(config)
    logger = setup_logging(Path(config["outputs"]["reports_dir"]) / "pipeline.log")
    logger.info("Starting pipeline.")

    panel = download_panel(config, logger)
    factors = add_factors(panel, config)
    factor_path = Path(config["outputs"]["tables_dir"]) / "factor_values.csv"
    factors.to_csv(factor_path, index=False, encoding="utf-8-sig")
    logger.info("Saved factor values to %s.", factor_path)

    nav, weights, turnover = run_all_backtests(factors, config)
    nav_path = Path(config["outputs"]["tables_dir"]) / "portfolio_nav.csv"
    weights_path = Path(config["outputs"]["tables_dir"]) / "weekly_weights.csv"
    turnover_path = Path(config["outputs"]["tables_dir"]) / "turnover.csv"
    nav.to_csv(nav_path, index=False, encoding="utf-8-sig")
    weights.to_csv(weights_path, index=False, encoding="utf-8-sig")
    turnover.to_csv(turnover_path, index=False, encoding="utf-8-sig")
    logger.info("Saved backtest tables.")

    risk_free_rate = float(config.get("performance", {}).get("risk_free_rate", 0.0))
    summary = summarize_performance(
        nav,
        turnover,
        risk_free_rate=risk_free_rate,
    )
    monthly = monthly_return(nav)
    yearly = annual_return_by_year(nav)
    primary = str(config["strategy"].get("primary_strategy", "momentum_crowding_convex"))
    cost_sensitivity = transaction_cost_sensitivity(
        nav,
        turnover,
        strategy=primary,
        base_cost_bps=float(config["strategy"]["transaction_cost_bps"]),
        scenarios_bps=config["strategy"].get("transaction_cost_sensitivity_bps", [0, 1, 2, 3, 5, 10]),
        risk_free_rate=risk_free_rate,
    )
    summary.to_csv(Path(config["outputs"]["tables_dir"]) / "performance_summary.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(Path(config["outputs"]["tables_dir"]) / "monthly_returns.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(Path(config["outputs"]["tables_dir"]) / "yearly_returns.csv", index=False, encoding="utf-8-sig")
    cost_sensitivity.to_csv(
        Path(config["outputs"]["tables_dir"]) / "transaction_cost_sensitivity.csv",
        index=False,
        encoding="utf-8-sig",
    )
    logger.info("Saved performance tables.")

    ic = make_all_plots(nav, weights, turnover, factors, monthly, yearly, config, cost_sensitivity)
    if not ic.empty:
        ic.to_csv(Path(config["outputs"]["tables_dir"]) / "factor_ic.csv", index=False, encoding="utf-8-sig")
    failures_path = Path(config["outputs"]["reports_dir"]) / "data_failures.csv"
    _write_report(
        config,
        summary,
        nav,
        turnover,
        cost_sensitivity,
        failures_path if failures_path.exists() else None,
    )
    logger.info("Pipeline finished successfully.")


if __name__ == "__main__":
    main()
