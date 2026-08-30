"""Update README badges, result tables, and validation text from generated outputs."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.performance import summarize_period_performance  # noqa: E402
from src.strategy_metadata import strategy_label  # noqa: E402
from src.utils import load_config  # noqa: E402


BADGE_LABEL_MAP = {
    "评估区间": "Period",
    "主策略": "Main Strategy",
}


def _fmt_pct(value: float) -> str:
    """Format a decimal as a percentage string."""
    return f"{value * 100:.2f}%"


def _badge(label: str, message: str, color: str = "4caf50") -> str:
    """Build a shields.io badge URL with percent-encoded content."""
    safe_label = BADGE_LABEL_MAP.get(label, label)
    return (
        f"https://img.shields.io/badge/{quote(safe_label, safe='')}"
        f"-{quote(message, safe='')}-{color}?style=for-the-badge&labelColor=4a4f59"
    )


def _build_performance_table(summary: pd.DataFrame, language: str) -> str:
    """Render the complete performance summary as Markdown."""
    if language == "zh":
        lines = ["| 策略 | 年化收益 | 年化波动 | Sharpe | 最大回撤 | 最终净值 |"]
    else:
        lines = ["| Strategy | Annual Return | Annual Vol | Sharpe | Max Drawdown | Final NAV |"]
    lines.append("|:--|--:|--:|--:|--:|--:|")
    for _, row in summary.iterrows():
        lines.append(
            f"| {strategy_label(str(row['strategy']), language)} "
            f"| {_fmt_pct(float(row['annual_return']))} "
            f"| {_fmt_pct(float(row['annual_volatility']))} "
            f"| {float(row['sharpe']):.2f} "
            f"| {_fmt_pct(float(row['max_drawdown']))} "
            f"| {float(row['final_nav']):.3f} |"
        )
    return "\n".join(lines)


def _build_cost_sensitivity_table(
    sensitivity: pd.DataFrame,
    language: str,
    base_cost_bps: float,
) -> str:
    """Render fixed-weight transaction-cost scenarios as Markdown."""
    data = sensitivity.sort_values("transaction_cost_bps")
    if language == "zh":
        lines = [
            "以下情景保持信号和目标权重不变，仅按计划调仓日的完整 L1 成交名义本金重算成本。",
            "",
            "| 每单位成交成本 | 口径 | 年化收益 | 年化波动 | Sharpe | 最大回撤 | 最终净值 |",
            "|---:|:---|---:|---:|---:|---:|---:|",
        ]
        for _, row in data.iterrows():
            case = "基准" if abs(float(row["transaction_cost_bps"]) - base_cost_bps) < 1e-12 else "情景"
            lines.append(
                f"| {float(row['transaction_cost_bps']):g} bps | {case} "
                f"| {_fmt_pct(float(row['annual_return']))} "
                f"| {_fmt_pct(float(row['annual_volatility']))} "
                f"| {float(row['sharpe']):.3f} "
                f"| {_fmt_pct(float(row['max_drawdown']))} "
                f"| {float(row['final_nav']):.3f} |"
            )
        return "\n".join(lines)

    lines = [
        "These scenarios hold signals and target weights fixed and only reprice gross L1 traded notional on scheduled rebalance dates.",
        "",
        "| Cost per Traded Notional | Case | Annual Return | Annual Vol | Sharpe | Max Drawdown | Final NAV |",
        "|---:|:---|---:|---:|---:|---:|---:|",
    ]
    for _, row in data.iterrows():
        case = "Base" if abs(float(row["transaction_cost_bps"]) - base_cost_bps) < 1e-12 else "Scenario"
        lines.append(
            f"| {float(row['transaction_cost_bps']):g} bps | {case} "
            f"| {_fmt_pct(float(row['annual_return']))} "
            f"| {_fmt_pct(float(row['annual_volatility']))} "
            f"| {float(row['sharpe']):.3f} "
            f"| {_fmt_pct(float(row['max_drawdown']))} "
            f"| {float(row['final_nav']):.3f} |"
        )
    return "\n".join(lines)


def _selected_row(summary: pd.DataFrame, strategy: str) -> pd.Series:
    selected = summary[summary["strategy"] == strategy]
    if selected.empty:
        raise ValueError(f"Strategy '{strategy}' is missing from the performance summary.")
    return selected.iloc[0]


def _build_dynamic_summary(
    summary: pd.DataFrame,
    nav: pd.DataFrame,
    turnover: pd.DataFrame,
    config: dict,
    language: str,
) -> str:
    """Build the answer-first result bullets for one README language."""
    primary = str(config["strategy"]["primary_strategy"])
    baseline = "momentum_crowding_penalty"
    full = _selected_row(summary, primary)
    comparison = _selected_row(summary, baseline)
    risk_free_rate = float(config.get("performance", {}).get("risk_free_rate", 0.0))
    split_date = pd.Timestamp(config.get("performance", {}).get("validation_split_date", "2023-01-01"))
    train = summarize_period_performance(
        nav,
        turnover,
        end=split_date - pd.Timedelta(days=1),
        risk_free_rate=risk_free_rate,
    )
    holdout = summarize_period_performance(
        nav,
        turnover,
        start=split_date,
        risk_free_rate=risk_free_rate,
    )
    train_row = _selected_row(train, primary)
    holdout_row = _selected_row(holdout, primary)
    optimizer = config["strategy"]["convex_optimizer"]

    if language == "zh":
        return "\n".join(
            [
                f"- 推荐主策略「{strategy_label(primary, 'zh')}」全样本年化 {_fmt_pct(full['annual_return'])}、标准 Sharpe {full['sharpe']:.2f}、最大回撤 {_fmt_pct(full['max_drawdown'])}，周均 L1 换手 {full['average_turnover']:.3f}。",
                f"- 相比原等权组合构建，Sharpe 从 {comparison['sharpe']:.2f} 提高到 {full['sharpe']:.2f}，最大回撤从 {_fmt_pct(comparison['max_drawdown'])} 收窄到 {_fmt_pct(full['max_drawdown'])}。",
                f"- 时间切分结果：2018–2022 参数选择段 Sharpe {train_row['sharpe']:.2f}；2023 年起时间留出段 Sharpe {holdout_row['sharpe']:.2f}。分阶段表现仍有差异，不能把 Sharpe 1 视为承诺。",
                f"- 优化器使用 {float(optimizer['max_weight']):.0%} 单 ETF 上限与 {float(optimizer['turnover_penalty_bps']):g} bp-equivalent 的 L1 换手正则；后者是控制交易稳定性的正则强度，不是实际交易费率。",
            ]
        )
    return "\n".join(
        [
            f"- The recommended {strategy_label(primary)} strategy delivers {_fmt_pct(full['annual_return'])} annualized return, a standard Sharpe of {full['sharpe']:.2f}, {_fmt_pct(full['max_drawdown'])} max drawdown, and {full['average_turnover']:.3f} average weekly L1 turnover over the full sample.",
            f"- Versus the original equal-weight portfolio construction, Sharpe rises from {comparison['sharpe']:.2f} to {full['sharpe']:.2f}, while max drawdown improves from {_fmt_pct(comparison['max_drawdown'])} to {_fmt_pct(full['max_drawdown'])}.",
            f"- Temporal validation: Sharpe is {train_row['sharpe']:.2f} for the 2018–2022 parameter-selection period and {holdout_row['sharpe']:.2f} for the 2023+ holdout. Regime results vary, so Sharpe 1 is not a promise.",
            f"- The optimizer uses a {float(optimizer['max_weight']):.0%} ETF cap and {float(optimizer['turnover_penalty_bps']):g} bp-equivalent L1 turnover regularizer. The latter is a stability penalty, not the realized transaction-cost assumption.",
        ]
    )


def _replace_marked_block(text: str, marker: str, replacement: str) -> str:
    """Replace text between a stable pair of README markers."""
    start = f"<!-- {marker}_START -->"
    end = f"<!-- {marker}_END -->"
    pattern = re.escape(start) + r".*?" + re.escape(end)
    updated, count = re.subn(pattern, f"{start}\n{replacement}\n{end}", text, flags=re.DOTALL)
    if count != 1:
        raise ValueError(f"README marker pair {marker} was not found exactly once.")
    return updated


def update_readme(
    readme_path: Path,
    summary: pd.DataFrame,
    panel: pd.DataFrame,
    nav: pd.DataFrame,
    turnover: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    config: dict,
) -> str:
    """Return README content synchronized with the latest generated outputs."""
    primary = str(config["strategy"]["primary_strategy"])
    main = _selected_row(summary, primary)
    panel_dates = pd.to_datetime(panel["date"])
    start_date = panel_dates.min().strftime("%Y-%m-%d")
    end_date = panel_dates.max().strftime("%Y-%m-%d")
    num_rows = len(panel)
    num_assets = panel["symbol"].nunique()
    text = readme_path.read_text(encoding="utf-8")

    text = re.sub(
        r'https://img\.shields\.io/badge/[^\"]+(?=" alt="Period")',
        _badge("Period", f"{panel_dates.min().year}–{panel_dates.max().year} · {num_rows} obs"),
        text,
    )
    text = re.sub(
        r'https://img\.shields\.io/badge/[^\"]+(?=" alt="Main Strategy")',
        _badge(
            "Main Strategy",
            f"Sharpe {float(main['sharpe']):.2f} | MaxDD {_fmt_pct(float(main['max_drawdown'])).replace('-', '--')}",
            "9853e6",
        ),
        text,
    )
    text = re.sub(
        r"本次真实数据运行覆盖 \d{4}-\d{2}-\d{2} 至 \d{4}-\d{2}-\d{2}，共 \d+ 只.*?。",
        f"本次前复权数据运行覆盖 {start_date} 至 {end_date}，共 {num_assets} 只 ETF，合计 {num_rows} 条日频记录。",
        text,
        count=1,
    )
    text = re.sub(
        r"The latest real-data run covers \d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2}, with \d+ ETFs.*?\.",
        f"The latest forward-adjusted run covers {start_date} to {end_date}, with {num_assets} ETFs and {num_rows} daily observations.",
        text,
        count=1,
    )
    text = re.sub(
        r"\|\s*策略\s*\|.*?\|\n\|:--.*?\n(?:\|.*?\|\n)+",
        lambda match: _build_performance_table(summary, "zh") + "\n",
        text,
        count=1,
    )
    text = re.sub(
        r"\|\s*Strategy\s*\|.*?\|\n\|:--.*?\n(?:\|.*?\|\n)+",
        lambda match: _build_performance_table(summary, "en") + "\n",
        text,
        count=1,
    )
    text = _replace_marked_block(text, "OPTIMIZED_SUMMARY_ZH", _build_dynamic_summary(summary, nav, turnover, config, "zh"))
    text = _replace_marked_block(text, "OPTIMIZED_SUMMARY_EN", _build_dynamic_summary(summary, nav, turnover, config, "en"))
    base_cost_bps = float(config["strategy"]["transaction_cost_bps"])
    text = _replace_marked_block(
        text,
        "COST_SENSITIVITY_ZH",
        _build_cost_sensitivity_table(cost_sensitivity, "zh", base_cost_bps),
    )
    text = _replace_marked_block(
        text,
        "COST_SENSITIVITY_EN",
        _build_cost_sensitivity_table(cost_sensitivity, "en", base_cost_bps),
    )
    return text


if __name__ == "__main__":
    config = load_config(REPO_ROOT / "config.yaml")
    summary = pd.read_csv(REPO_ROOT / "outputs" / "tables" / "performance_summary.csv")
    panel = pd.read_parquet(REPO_ROOT / "data" / "processed" / "panel_daily.parquet")
    nav = pd.read_csv(REPO_ROOT / "outputs" / "tables" / "portfolio_nav.csv", parse_dates=["date"])
    turnover = pd.read_csv(REPO_ROOT / "outputs" / "tables" / "turnover.csv", parse_dates=["date"])
    cost_sensitivity = pd.read_csv(REPO_ROOT / "outputs" / "tables" / "transaction_cost_sensitivity.csv")
    readme_path = REPO_ROOT / "README.md"
    updated = update_readme(readme_path, summary, panel, nav, turnover, cost_sensitivity, config)
    readme_path.write_text(updated, encoding="utf-8")
    print("README.md updated successfully.")
