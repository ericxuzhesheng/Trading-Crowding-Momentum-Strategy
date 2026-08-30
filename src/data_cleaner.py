"""Data cleaning routines for daily ETF panels."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = ["date", "symbol", "name", "open", "high", "low", "close", "volume", "amount", "turnover"]


def standardize_panel(
    df: pd.DataFrame,
    min_observations: int,
    logger: logging.Logger | None = None,
    max_abs_daily_return: float | None = None,
) -> pd.DataFrame:
    """Validate, clean, and sort a long-format daily panel."""
    if df.empty:
        raise ValueError("No daily data was downloaded from any source.")

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Panel is missing required columns: {missing}")

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    for col in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["date", "symbol", "close"])
    out = out.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"], keep="last")
    out["turnover"] = out["turnover"].replace([np.inf, -np.inf], np.nan)

    kept = []
    skipped = []
    for symbol, group in out.groupby("symbol", sort=False):
        valid_rows = int(group["close"].notna().sum())
        if valid_rows >= min_observations:
            kept.append(group)
        else:
            skipped.append((symbol, valid_rows))

    if skipped and logger:
        for symbol, rows in skipped:
            logger.warning("Skipping %s because only %s valid rows are available.", symbol, rows)

    if not kept:
        raise ValueError(f"No symbol has at least {min_observations} observations.")

    cleaned = pd.concat(kept, ignore_index=True)
    cleaned["turnover"] = cleaned.groupby("symbol")["turnover"].transform(lambda s: s.fillna(s.median()))
    cleaned["turnover"] = cleaned["turnover"].fillna(0.0)
    if max_abs_daily_return is not None:
        threshold = float(max_abs_daily_return)
        if threshold <= 0.0:
            raise ValueError("max_abs_daily_return must be positive when supplied.")
        daily_return = cleaned.groupby("symbol")["close"].pct_change(fill_method=None)
        extreme = cleaned.loc[daily_return.abs() > threshold, ["date", "symbol", "close"]].copy()
        if not extreme.empty:
            extreme["daily_return"] = daily_return.loc[extreme.index]
            sample = extreme.head(10).to_dict("records")
            raise ValueError(
                "Adjusted-price validation failed: "
                f"{len(extreme)} daily returns exceed {threshold:.1%}. Sample: {sample}"
            )
    return cleaned[REQUIRED_COLUMNS].sort_values(["date", "symbol"]).reset_index(drop=True)
