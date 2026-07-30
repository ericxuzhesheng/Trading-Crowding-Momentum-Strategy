"""Update README badges, tables, and key metrics from latest backtest results.

Reads performance_summary.csv and panel_daily.parquet, then rewrites the dynamic
sections of README.md: shields.io badges, data coverage sentences, performance
tables (Chinese + English), and summary statistics in the takeaways text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

STRATEGY_LABELS: dict[str, str] = {
    "all_index_equal_weight": "全 ETF 等权 / All-ETF EW",
    "crowding_top_quantile": "纯拥挤度 top30 对照组 / Pure Crowding",
    "csi300_etf_buy_hold": "沪深300 ETF 买入持有 / CSI 300 B&H",
    "momentum_crowding_penalty": "动量 - 拥挤度惩罚 / Mom-Crowding",
    "momentum_crowding_penalty_trend": "动量 - 拥挤度惩罚 + 趋势过滤 / Mom-Crowding+Trend",
    "momentum_top_quantile": "纯 5 日动量 top30 / Pure 5D Mom",
}


def _fmt_pct(value: float) -> str:
    """Format a decimal as a percentage string, e.g. 0.1196 -> "-11.96%"."""
    return f"{value * 100:.2f}%"


def _badge(label: str, msg: str, color: str = "4caf50") -> str:
    """Build a shields.io badge URL with percent-encoded message."""
    safe = msg.replace("%", "%25").replace(" ", "%20").replace("|", "%7C")
    return f"https://img.shields.io/badge/{label}-{safe}-{color}?style=for-the-badge&labelColor=4a4f59"


def _badge_range(label: str, msg: str, color: str = "4caf50") -> str:
    """Like _badge but leaves '--' intact for year-range display."""
    safe = msg.replace(" ", "%20").replace("|", "%7C").replace("%", "%25")
    return f"https://img.shields.io/badge/{label}-{safe}-{color}?style=for-the-badge&labelColor=4a4f59"


def _build_performance_table(summary: pd.DataFrame, lang: str) -> str:
    """Render the performance summary as a Markdown table."""
    if lang == "zh":
        lines = ["| 策略 | 年化收益 | 年化波动 | Sharpe | 最大回撤 | 最终净值 |"]
        lines.append("|:--|--:|--:|--:|--:|--:|")
    else:
        lines = ["| Strategy | Annual Return | Annual Vol | Sharpe | Max Drawdown | Final NAV |"]
        lines.append("|:--|--:|--:|--:|--:|--:|")

    for _, row in summary.iterrows():
        key = row["strategy"]
        label = STRATEGY_LABELS.get(key, key)
        if lang == "zh":
            label = label.split(" / ")[0]
        else:
            parts = label.split(" / ")
            label = parts[1] if len(parts) > 1 else parts[0]

        lines.append(
            f"| {label} "
            f"| {_fmt_pct(float(row['annual_return']))} "
            f"| {_fmt_pct(float(row['annual_volatility']))} "
            f"| {float(row['sharpe']):.2f} "
            f"| {_fmt_pct(float(row['max_drawdown']))} "
            f"| {float(row['final_nav']):.3f} |"
        )
    return "\n".join(lines)


def update_readme(readme_path: Path, summary: pd.DataFrame, panel: pd.DataFrame) -> str:
    """Return updated README content with live metrics injected."""

    main = summary[summary["strategy"] == "momentum_crowding_penalty_trend"]
    if main.empty:
        raise ValueError("Main strategy 'momentum_crowding_penalty_trend' not found in performance_summary.csv.")

    unfiltered = summary[summary["strategy"] == "momentum_crowding_penalty"]

    sharpe = float(main["sharpe"].iloc[0])
    mdd = float(main["max_drawdown"].iloc[0])
    ann_ret = float(main["annual_return"].iloc[0])

    panel_dates = pd.to_datetime(panel["date"])
    start_date = panel_dates.min().strftime("%Y-%m-%d")
    end_date = panel_dates.max().strftime("%Y-%m-%d")
    num_rows = len(panel)
    num_assets = panel["symbol"].nunique()
    start_year = panel_dates.min().year
    end_year = panel_dates.max().year

    text = readme_path.read_text(encoding="utf-8")

    # ---- 1. shields.io badges ----
    SHARPE_STR = f"{sharpe:.2f}"
    MDD_STR = _fmt_pct(mdd)

    text = re.sub(
        r'https://img\.shields\.io/badge/评估区间-[^"]+',
        _badge_range("评估区间", f"{start_year}--{end_year} · {num_rows}条日频记录"),
        text,
    )
    text = re.sub(
        r'https://img\.shields\.io/badge/主策略-[^"]+',
        _badge("主策略", f"Sharpe {SHARPE_STR} | MaxDD {MDD_STR}", "9853e6"),
        text,
    )
    text = re.sub(
        r'https://img\.shields\.io/badge/Period-[^"]+',
        _badge_range("Period", f"{start_year}--{end_year} · {num_rows} obs"),
        text,
    )
    text = re.sub(
        r'https://img\.shields\.io/badge/Main%20Strategy-[^"]+',
        _badge("Main Strategy", f"Sharpe {SHARPE_STR} | MaxDD {MDD_STR}", "9853e6"),
        text,
    )

    # ---- 2. Chinese data coverage sentence ----
    text = re.sub(
        r"本次真实数据运行覆盖 \d{4}-\d{2}-\d{2} 至 \d{4}-\d{2}-\d{2}，共 \d+ 只.*?成功下载。",
        f"本次真实数据运行覆盖 {start_date} 至 {end_date}，共 {num_assets} 只 ETF，合计 {num_rows} 条日频记录，数据由 Tushare 成功下载。",
        text,
    )

    # ---- 3. Chinese performance table ----
    text = re.sub(
        r"\|\s*策略\s*\|.*?\|\n\|:--.*?\n(?:\|.*?\|\n)+",
        lambda m: _build_performance_table(summary, "zh") + "\n",
        text,
        count=1,
    )

    # ---- 4. English data coverage sentence ----
    text = re.sub(
        r"The latest real-data run covers \d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2}, with \d+ ETFs.*?downloaded from Tushare\.",
        f"The latest real-data run covers {start_date} to {end_date}, with {num_assets} ETFs, {num_rows} daily observations downloaded from Tushare.",
        text,
    )

    # ---- 5. English performance table ----
    text = re.sub(
        r"\|\s*Strategy\s*\|.*?\|\n\|:--.*?\n(?:\|.*?\|\n)+",
        lambda m: _build_performance_table(summary, "en") + "\n",
        text,
        count=1,
    )

    # ---- 6. Key takeaways with live numbers ----
    if not unfiltered.empty:
        u_ret = _fmt_pct(float(unfiltered["annual_return"].iloc[0]))
        u_mdd = _fmt_pct(float(unfiltered["max_drawdown"].iloc[0]))
        u_sharpe = f'{float(unfiltered["sharpe"].iloc[0]):.2f}'

        text = re.sub(
            r"未加趋势过滤的惩罚动量版本年化 [\d.]+%、Sharpe [\d.]+",
            f"未加趋势过滤的惩罚动量版本年化 {u_ret}、Sharpe {u_sharpe}",
            text,
        )
        text = re.sub(
            r"unfiltered penalized momentum strategy earns [\d.]+% annualized with a [\d.]+ Sharpe",
            f"unfiltered penalized momentum strategy earns {u_ret} annualized with a {u_sharpe} Sharpe",
            text,
        )

    t_ret = _fmt_pct(ann_ret)
    t_sharpe = f"{sharpe:.2f}"
    t_mdd = _fmt_pct(mdd)
    text = re.sub(
        r"加入 MA200 趋势过滤后，年化为 [\d.]+%、Sharpe [\d.]+，最大回撤从未过滤版的 [-\d.]+% 降至 [-\d.]+%",
        f"加入 MA200 趋势过滤后，年化为 {t_ret}、Sharpe {t_sharpe}，最大回撤从未过滤版的 {u_mdd if not unfiltered.empty else '??'} 降至 {t_mdd}",
        text,
    )
    text = re.sub(
        r"trend filter lowers annual return to [\d.]+%, but reduces max drawdown from [-\d.]+% to [-\d.]+%",
        f"trend filter lowers annual return to {t_ret}, but reduces max drawdown from {u_mdd if not unfiltered.empty else '??'} to {t_mdd}",
        text,
    )

    return text


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    summary_path = repo_root / "outputs" / "tables" / "performance_summary.csv"
    panel_path = repo_root / "data" / "processed" / "panel_daily.parquet"
    readme_path = repo_root / "README.md"

    summary = pd.read_csv(summary_path)
    panel = pd.read_parquet(panel_path)

    updated = update_readme(readme_path, summary, panel)
    readme_path.write_text(updated, encoding="utf-8")
    print("README.md updated successfully.")
