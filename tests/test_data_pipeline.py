"""Tests for adjusted ETF prices and data-quality guards."""

import logging

import pandas as pd
import pytest

from src import data_loader
from src.data_cleaner import REQUIRED_COLUMNS, standardize_panel


def _panel_rows(closes: list[float]) -> pd.DataFrame:
    rows = []
    for idx, close in enumerate(closes):
        rows.append(
            {
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=idx),
                "symbol": "ETF",
                "name": "ETF",
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1000,
                "amount": 10000,
                "turnover": 1.0,
            }
        )
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


def test_adjusted_price_guard_rejects_split_like_jump() -> None:
    """A unit conversion must not silently become a portfolio return."""
    with pytest.raises(ValueError, match="Adjusted-price validation failed"):
        standardize_panel(_panel_rows([1.0, 1.01, 0.10]), 2, max_abs_daily_return=0.30)


def test_akshare_receives_configured_price_adjustment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ETF history request should explicitly use forward-adjusted prices."""
    calls = {}

    class FakeAkshare:
        @staticmethod
        def fund_etf_hist_em(**kwargs):
            calls.update(kwargs)
            return pd.DataFrame(
                {
                    "日期": ["2024-01-01", "2024-01-02"],
                    "开盘": [1.0, 1.01],
                    "最高": [1.0, 1.01],
                    "最低": [1.0, 1.01],
                    "收盘": [1.0, 1.01],
                    "成交量": [1000, 1100],
                    "成交额": [10000, 11110],
                    "换手率": [1.0, 1.1],
                }
            )

    monkeypatch.setattr(data_loader, "_optional_import", lambda module_name: FakeAkshare())
    config = {
        "data": {
            "default_asset": "FD",
            "price_adjustment": "qfq",
            "start_date": "20240101",
            "end_date": "20240102",
        }
    }
    result = data_loader._fetch_akshare_one(
        {"symbol": "510300.SH", "name": "CSI300 ETF", "asset": "FD"},
        config,
        logging.getLogger("test"),
    )
    assert calls["adjust"] == "qfq"
    assert list(result["close"]) == [1.0, 1.01]


def test_tushare_fund_factors_remove_unit_conversion_jump() -> None:
    """QFQ scaling should turn a 10:1 unit consolidation into a continuous return path."""
    daily = pd.DataFrame(
        {
            "trade_date": ["20250318", "20250319"],
            "open": [10.495, 105.001],
            "high": [10.495, 105.001],
            "low": [10.495, 105.001],
            "close": [10.495, 105.001],
        }
    )
    factors = pd.DataFrame(
        {
            "trade_date": ["20250318", "20250319"],
            "adj_factor": [11.1758, 1.1176],
        }
    )
    adjusted = data_loader._adjust_tushare_fund_prices(daily, factors, "qfq")
    daily_return = adjusted["close"].pct_change().iloc[-1]
    assert abs(daily_return) < 0.01
