"""Compare current cleaning with a Git baseline on the tracked snapshot."""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from src.data_cleaner import standardize_panel
from src.factors import add_factors
from src.backtest import run_all_backtests
from src.utils import load_config

parser = argparse.ArgumentParser()
parser.add_argument("--baseline", default="d0ae972bcc9a21230b23e5f3d67251d7a2a5ab6a")
args = parser.parse_args()
namespace = {}
exec(subprocess.check_output(
    ["git", "show", f"{args.baseline}:src/data_cleaner.py"], text=True
), namespace)
config = load_config("config.yaml")
panel = pd.read_parquet(config["data"]["processed_path"])
kwargs = dict(min_observations=config["data"]["min_observations"],
              max_abs_daily_return=config["data"].get("max_abs_daily_return"))
old = namespace["standardize_panel"](panel, **kwargs)
new = standardize_panel(panel, **kwargs)
# The new parser standardizes microsecond input to nanoseconds, without changing keys.
old["date"] = old["date"].astype("datetime64[ns]")
pd.testing.assert_frame_equal(old, new)
old_f, new_f = add_factors(old, config), add_factors(new, config)
pd.testing.assert_frame_equal(old_f, new_f)
for before, after in zip(run_all_backtests(old_f, config), run_all_backtests(new_f, config)):
    pd.testing.assert_frame_equal(before, after)
print(f"PASS: {len(panel)} rows, {panel.symbol.nunique()} symbols; prices, daily keys, factors, NAV, weights and turnover identical (date dtype normalized).")
