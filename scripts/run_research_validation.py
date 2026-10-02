"""Offline, reproducible weekly IC and matched no-crowding experiment."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.research_validation import run_matched_ablation
from src.utils import load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    source = ROOT / config["data"]["processed_path"]
    panel = pd.read_parquet(source)
    panel["date"] = pd.to_datetime(panel["date"])
    if panel.duplicated(["date", "symbol"]).any():
        raise ValueError("Duplicate date/symbol in source panel")
    summary, nav, turnover, ic = run_matched_ablation(panel, config)
    out = ROOT / "outputs" / "research_validation"
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in (("ablation", summary), ("nav", nav), ("turnover", turnover), ("weekly_ic", ic)):
        frame.to_csv(out / f"{name}.csv", index=False)
    ic_summary = ic.groupby("strategy")["spearman_ic"].agg(["count", "mean", "std"])
    ic_summary.to_csv(out / "weekly_ic_summary.csv")
    provenance = {"input": source.relative_to(ROOT).as_posix(), "start": str(panel.date.min().date()),
                  "end": str(panel.date.max().date()), "rows": len(panel), "configuration": config,
                  "data_refresh": False, "parameter_search": False}
    (out / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    display = summary[["period", "strategy", "annual_return", "sharpe", "max_drawdown", "average_turnover"]]
    text = "# Weekly IC and matched crowding ablation / 周度 IC 与拥挤度对照\n\n"
    text += f"数据：{provenance['start']} 至 {provenance['end']}，{len(panel):,} 行；使用已保存面板，未重新调参。\n\n"
    text += "仅将复合得分的拥挤度系数及优化器拥挤度项置零，其余参数、资产可用性、风控、费用与执行时序相同。\n\n"
    text += display.to_markdown(index=False, floatfmt=".5f") + "\n\n" + ic_summary.to_markdown(floatfmt=".5f")
    text += "\n\nIC 使用周末决策日的已滞后一日得分，与下一交易日收盘至下次调仓收盘的个券收益对应；这与现有引擎的 weights.shift(1) 一致。排除没有完整终点或价格缺失的区间。IC 未加个券费用；组合表现已按配置扣费。\n\n"
    text += "比较采用相同配置和已观察样本，不构成事前样本外检验。当前静态资产池与引擎的恒定目标权重、计划调仓成本假设仍保留；该实验不验证实际成交或容量。IC 正负和两种组合的绩效差异应分别解释，不能将优化器收益直接归因于拥挤度预测力。\n\n"
    text += "复跑：`python scripts/run_research_validation.py`。CSV 为未四舍五入输出，provenance.json 保存本次完整配置。\n"
    (out / "report.md").write_text(text, encoding="utf-8")
    print(display.to_string(index=False))
    print(ic_summary.to_string())


if __name__ == "__main__":
    main()
