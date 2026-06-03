"""Data download layer with Tushare priority and AKShare fallback."""

from __future__ import annotations

import importlib
import logging
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from .data_cleaner import standardize_panel
from .utils import normalize_date_string


class DataDownloadError(RuntimeError):
    """Raised when all configured market data providers fail."""


def _optional_import(module_name: str) -> Any:
    """Import an optional provider module and raise a clear error if unavailable."""
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise DataDownloadError(f"Required optional package '{module_name}' is not installed.") from exc


def _save_raw(df: pd.DataFrame, raw_dir: str | Path, source: str, symbol: str) -> None:
    """Persist raw provider data for reproducibility and diagnostics."""
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.replace(".", "_").replace("/", "_")
    df.to_csv(Path(raw_dir) / f"{source}_{safe_symbol}.csv", index=False, encoding="utf-8-sig")


def _normalize_tushare(df: pd.DataFrame, symbol: str, name: str) -> pd.DataFrame:
    """Normalize Tushare index daily or pro_bar output to the project schema."""
    mapping = {
        "trade_date": "date",
        "vol": "volume",
        "amount": "amount",
        "turnover_rate": "turnover",
        "turnover_rate_f": "turnover",
    }
    out = df.rename(columns=mapping).copy()
    if "date" not in out.columns:
        raise DataDownloadError(f"Tushare data for {symbol} has no trade_date/date column.")
    for col in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
        if col not in out.columns:
            out[col] = pd.NA
    out["symbol"] = symbol
    out["name"] = name
    return out[["date", "symbol", "name", "open", "high", "low", "close", "volume", "amount", "turnover"]]


def _normalize_akshare(df: pd.DataFrame, symbol: str, name: str) -> pd.DataFrame:
    """Normalize AKShare index output with tolerant Chinese/English field mapping."""
    aliases = {
        "date": ["date", "日期"],
        "open": ["open", "开盘"],
        "high": ["high", "最高"],
        "low": ["low", "最低"],
        "close": ["close", "收盘"],
        "volume": ["volume", "成交量"],
        "amount": ["amount", "成交额"],
        "turnover": ["turnover", "换手率"],
    }
    rename = {}
    lower_cols = {str(col).lower(): col for col in df.columns}
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in df.columns:
                rename[candidate] = target
                break
            if candidate.lower() in lower_cols:
                rename[lower_cols[candidate.lower()]] = target
                break
    out = df.rename(columns=rename).copy()
    if "date" not in out.columns:
        raise DataDownloadError(f"AKShare data for {symbol} has no date column. Columns: {list(df.columns)}")
    for col in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
        if col not in out.columns:
            out[col] = pd.NA
    out["symbol"] = symbol
    out["name"] = name
    return out[["date", "symbol", "name", "open", "high", "low", "close", "volume", "amount", "turnover"]]


def _fetch_tushare_one(item: dict[str, str], config: dict[str, Any], logger: logging.Logger) -> pd.DataFrame:
    """Fetch one index from Tushare using pro_bar first, then index_daily."""
    ts = _optional_import("tushare")
    token_env = config["data"].get("tushare_token_env", "TUSHARE_TOKEN")
    token = os.getenv(token_env)
    if not token:
        raise DataDownloadError(f"Environment variable {token_env} is not set.")

    pro = ts.pro_api(token)
    symbol = item["symbol"]
    start_date = normalize_date_string(config["data"].get("start_date"))
    end_date = normalize_date_string(config["data"].get("end_date"))

    errors = []
    try:
        df = ts.pro_bar(ts_code=symbol, api=pro, asset="I", freq="D", start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            return _normalize_tushare(df, symbol, item["name"])
        errors.append("pro_bar returned empty data")
    except Exception as exc:
        errors.append(f"pro_bar failed: {exc}")

    try:
        df = pro.index_daily(ts_code=symbol, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            return _normalize_tushare(df, symbol, item["name"])
        errors.append("index_daily returned empty data")
    except Exception as exc:
        errors.append(f"index_daily failed: {exc}")

    raise DataDownloadError(f"Tushare failed for {symbol}: {'; '.join(errors)}")


def _fetch_akshare_one(item: dict[str, str], config: dict[str, Any], logger: logging.Logger) -> pd.DataFrame:
    """Fetch one index from AKShare historical index daily endpoints."""
    ak = _optional_import("akshare")
    ak_symbol = item.get("ak_symbol") or item["symbol"].lower().replace(".sh", "").replace(".sz", "")
    if "." in item["symbol"]:
        market = item["symbol"].split(".")[-1].lower()
        code = item["symbol"].split(".")[0]
        fallback_symbol = f"{market}{code}"
    else:
        fallback_symbol = ak_symbol

    errors = []
    for func_name in ["stock_zh_index_daily_em", "stock_zh_index_daily_tx"]:
        if not hasattr(ak, func_name):
            continue
        for candidate in [ak_symbol, fallback_symbol]:
            try:
                df = getattr(ak, func_name)(symbol=candidate)
                if df is not None and not df.empty:
                    out = _normalize_akshare(df, item["symbol"], item["name"])
                    start = pd.to_datetime(str(config["data"].get("start_date", "")), errors="coerce")
                    end = pd.to_datetime(str(config["data"].get("end_date", "")), errors="coerce")
                    out["date"] = pd.to_datetime(out["date"])
                    if pd.notna(start):
                        out = out[out["date"] >= start]
                    if pd.notna(end):
                        out = out[out["date"] <= end]
                    return out
                errors.append(f"{func_name}({candidate}) returned empty data")
            except Exception as exc:
                errors.append(f"{func_name}({candidate}) failed: {exc}")
    raise DataDownloadError(f"AKShare failed for {item['symbol']}: {'; '.join(errors)}")


def download_panel(config: dict[str, Any], logger: logging.Logger) -> pd.DataFrame:
    """Download, clean, save, and return the long-format daily index panel."""
    panels = []
    failures = []
    raw_dir = config["data"]["raw_dir"]
    prefer_tushare = bool(config["data"].get("prefer_tushare", True))
    failure_path = Path(config["outputs"]["reports_dir"]) / "data_failures.csv"
    if failure_path.exists():
        failure_path.unlink()

    for item in config["data"]["indices"]:
        source_order = ["tushare", "akshare"] if prefer_tushare else ["akshare", "tushare"]
        last_error = None
        for source in source_order:
            try:
                logger.info("Fetching %s %s from %s.", item["symbol"], item["name"], source)
                df = _fetch_tushare_one(item, config, logger) if source == "tushare" else _fetch_akshare_one(item, config, logger)
                _save_raw(df, raw_dir, source, item["symbol"])
                panels.append(df)
                logger.info("Fetched %s rows for %s from %s.", len(df), item["symbol"], source)
                break
            except Exception as exc:
                last_error = exc
                logger.warning("%s failed for %s: %s", source, item["symbol"], exc)
                time.sleep(float(config["data"].get("sleep_seconds", 0)))
        else:
            failures.append({"symbol": item["symbol"], "name": item["name"], "reason": str(last_error)})

    if failures:
        pd.DataFrame(failures).to_csv(failure_path, index=False, encoding="utf-8-sig")
        logger.warning("Saved data failure diagnostics to %s.", failure_path)

    if not panels:
        raise DataDownloadError("All data providers failed. See outputs/reports/data_failures.csv and pipeline.log.")

    panel = standardize_panel(pd.concat(panels, ignore_index=True), config["data"]["min_observations"], logger)
    output_path = Path(config["data"]["processed_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(output_path, index=False)
    logger.info("Saved processed panel to %s with %s rows.", output_path, len(panel))
    return panel
