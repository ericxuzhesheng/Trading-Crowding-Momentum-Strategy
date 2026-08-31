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
    lines.append("|:---|---:|---:|---:|---:|---:|")
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
    split_label = split_date.strftime("%Y-%m-%d")
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
    earlier_row = _selected_row(earlier, primary)
    later_row = _selected_row(later, primary)
    optimizer = config["strategy"]["convex_optimizer"]

    if language == "zh":
        return "\n".join(
            [
                f"- 主实验「{strategy_label(primary, 'zh')}」在全样本记录年化 {_fmt_pct(full['annual_return'])}、标准 Sharpe {full['sharpe']:.2f}、最大回撤 {_fmt_pct(full['max_drawdown'])}，周均 L1 换手为 {full['average_turnover']:.3f}。",
                f"- 在相同信号定义下，旧 top30% 上限等权配置的 Sharpe 为 {comparison['sharpe']:.2f}、最大回撤为 {_fmt_pct(comparison['max_drawdown'])}；凸优化配置对应 {full['sharpe']:.2f} 和 {_fmt_pct(full['max_drawdown'])}。两种配置的资产纳入、持仓上限和实际总暴露均有差异，因此这里只报告观察到的比较。",
                f"- 以 {split_label} 为界进行时间切分，较早区间 Sharpe 为 {earlier_row['sharpe']:.2f}，较晚区间为 {later_row['sharpe']:.2f}。这个结果用于检查时间稳定性，不代表完全未观察的样本外检验。",
                f"- 优化器使用 {float(optimizer['max_weight']):.0%} 单标的上限与 {float(optimizer['turnover_penalty_bps']):g} bp-equivalent 的 L1 换手正则。该系数控制交易稳定性，实际成本假设另按每单位成交名义本金计费。",
            ]
        )
    return "\n".join(
        [
            f"- The main {strategy_label(primary)} experiment records {_fmt_pct(full['annual_return'])} annualized return, a standard Sharpe of {full['sharpe']:.2f}, {_fmt_pct(full['max_drawdown'])} max drawdown, and {full['average_turnover']:.3f} average weekly L1 turnover over the full sample.",
            f"- Under the same signal definition, the legacy capped top-30% configuration records Sharpe of {comparison['sharpe']:.2f} and max drawdown of {_fmt_pct(comparison['max_drawdown'])}; the convex configuration records {full['sharpe']:.2f} and {_fmt_pct(full['max_drawdown'])}. Eligible assets, position caps, and resulting exposure also differ, so the comparison does not isolate a causal effect.",
            f"- A {split_label} temporal split reports Sharpe of {earlier_row['sharpe']:.2f} in the earlier segment and {later_row['sharpe']:.2f} in the later segment. This stability diagnostic does not establish a fully untouched out-of-sample test.",
            f"- The optimizer uses a {float(optimizer['max_weight']):.0%} single-instrument cap and {float(optimizer['turnover_penalty_bps']):g} bp-equivalent L1 turnover regularizer. Realized transaction costs are modeled separately per unit of traded notional.",
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
    panel_dates = pd.to_datetime(panel["date"])
    start_date = panel_dates.min().strftime("%Y-%m-%d")
    end_date = panel_dates.max().strftime("%Y-%m-%d")
    num_rows = len(panel)
    num_assets = panel["symbol"].nunique()
    text = readme_path.read_text(encoding="utf-8")

    text = re.sub(
        r'https://img\.shields\.io/badge/[^\"]+(?=" alt="Period")',
        _badge("Period", f"{panel_dates.min().year}-{panel_dates.max().year} | {num_rows} obs"),
        text,
    )
    text = re.sub(
        r"本次(?:真实|前复权)数据运行覆盖 \d{4}-\d{2}-\d{2} 至 \d{4}-\d{2}-\d{2}，(?:共|配置中共有) \d+ 只.*?。",
        f"本次前复权数据运行覆盖 {start_date} 至 {end_date}，配置中共有 {num_assets} 只场内基金，各标的按可用历史进入，合计 {num_rows} 条日频记录。",
        text,
        count=1,
    )
    text = re.sub(
        r"The latest (?:real-data|forward-adjusted) run covers \d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2}(?:, with \d+ ETFs| and contains \d+ daily observations across \d+ configured (?:ETFs|listed funds)).*?\.",
        f"The latest forward-adjusted run covers {start_date} to {end_date} and contains {num_rows} daily observations across {num_assets} configured listed funds over their available histories.",
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
