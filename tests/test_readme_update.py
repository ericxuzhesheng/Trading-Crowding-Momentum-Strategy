"""Tests for keeping README claims synchronized with the configured primary strategy."""

from pathlib import Path

import pandas as pd

from scripts.update_readme import update_readme
from src.performance import summarize_performance, transaction_cost_sensitivity


def test_readme_update_uses_configured_convex_primary(tmp_path: Path) -> None:
    """The updater must not restore the legacy trend strategy or stale badge metrics."""
    dates = pd.date_range("2022-12-29", periods=6, freq="B")
    returns_by_strategy = {
        "momentum_crowding_convex": [0.0, 0.01, 0.002, 0.003, -0.001, 0.004],
        "momentum_crowding_penalty": [0.0, 0.002, -0.003, 0.001, -0.002, 0.001],
    }
    nav_rows = []
    turnover_rows = []
    for strategy, returns in returns_by_strategy.items():
        nav = (1.0 + pd.Series(returns)).cumprod()
        nav_rows.extend(
            {
                "date": date,
                "strategy": strategy,
                "return": daily_return,
                "nav": nav_value,
            }
            for date, daily_return, nav_value in zip(dates, returns, nav)
        )
        turnover_rows.extend(
            {"date": date, "strategy": strategy, "turnover": 0.1, "transaction_cost": 0.00003}
            for date in dates
        )
    nav_df = pd.DataFrame(nav_rows)
    turnover_df = pd.DataFrame(turnover_rows)
    summary = summarize_performance(nav_df, turnover_df)
    panel = pd.DataFrame({"date": dates, "symbol": ["ETF"] * len(dates)})
    config = {
        "strategy": {
            "primary_strategy": "momentum_crowding_convex",
            "transaction_cost_bps": 3,
            "transaction_cost_sensitivity_bps": [0, 1, 2, 3, 5, 10],
            "convex_optimizer": {"max_weight": 0.15, "turnover_penalty_bps": 750},
        },
        "performance": {"risk_free_rate": 0.0, "validation_split_date": "2023-01-01"},
    }
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                '<img src="https://img.shields.io/badge/old" alt="Period">',
                '<img src="https://img.shields.io/badge/old" alt="Main Strategy">',
                "本次真实数据运行覆盖 2020-01-01 至 2020-01-02，共 1 只 ETF，合计 2 条日频记录。",
                "| 策略 | 年化收益 | 年化波动 | Sharpe | 最大回撤 | 最终净值 |",
                "|:--|--:|--:|--:|--:|--:|",
                "| old | 0% | 0% | 0 | 0% | 1 |",
                "<!-- OPTIMIZED_SUMMARY_ZH_START -->",
                "old",
                "<!-- OPTIMIZED_SUMMARY_ZH_END -->",
                "<!-- COST_SENSITIVITY_ZH_START -->",
                "old",
                "<!-- COST_SENSITIVITY_ZH_END -->",
                "The latest real-data run covers 2020-01-01 to 2020-01-02, with 1 ETFs and 2 daily observations.",
                "| Strategy | Annual Return | Annual Vol | Sharpe | Max Drawdown | Final NAV |",
                "|:--|--:|--:|--:|--:|--:|",
                "| old | 0% | 0% | 0 | 0% | 1 |",
                "<!-- OPTIMIZED_SUMMARY_EN_START -->",
                "old",
                "<!-- OPTIMIZED_SUMMARY_EN_END -->",
                "<!-- COST_SENSITIVITY_EN_START -->",
                "old",
                "<!-- COST_SENSITIVITY_EN_END -->",
            ]
        ),
        encoding="utf-8",
    )
    sensitivity = transaction_cost_sensitivity(
        nav_df,
        turnover_df,
        strategy="momentum_crowding_convex",
        base_cost_bps=3,
        scenarios_bps=[0, 1, 2, 3, 5, 10],
    )
    updated = update_readme(readme, summary, panel, nav_df, turnover_df, sensitivity, config)
    assert "Main%20Strategy-Sharpe" in updated
    assert "凸优化动量 - 拥挤度" in updated
    assert "Convex Mom-Crowding" in updated
    assert "| 3 bps | 基准" in updated
    assert "| 10 bps | Scenario" in updated
    assert "| old |" not in updated
