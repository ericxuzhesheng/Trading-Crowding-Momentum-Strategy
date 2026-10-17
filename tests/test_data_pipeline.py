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


def test_mixed_dates_preserve_prices_returns_and_alignment():
    from datetime import date
    from src.backtest import _wide_prices
    rows = _panel_rows([1.0, 1.01, 1.02, 1.03, 1.04])
    expected = standardize_panel(rows, 1)
    rows["date"] = pd.Series(
        ["20240101", "2024-01-02", 20240103, date(2024, 1, 4), pd.Timestamp("2024-01-05")],
        dtype=object,
    )
    actual = standardize_panel(rows.iloc[::-1], 1)
    pd.testing.assert_frame_equal(actual, expected)
    pd.testing.assert_frame_equal(_wide_prices(actual, "close"), _wide_prices(expected, "close"))
    pd.testing.assert_series_equal(
        actual.groupby("symbol")["close"].pct_change(fill_method=None),
        expected.groupby("symbol")["close"].pct_change(fill_method=None),
    )


@pytest.mark.parametrize("bad", [
    None, pd.NA, pd.NaT, float("nan"), "", "20240230", "2024-02-30",
    "01/02/2024", 1704067200, 20240101.0, "2024011",
    pd.Timestamp("2024-01-01 12:00"), pd.Timestamp("2024-01-01", tz="UTC"),
])
def test_bad_dates_raise_without_silently_losing_rows(bad):
    rows = _panel_rows([1.0, 1.01])
    rows["date"] = rows["date"].astype(object)
    rows.loc[1, "date"] = bad
    with pytest.raises(ValueError, match="Invalid or missing daily dates"):
        standardize_panel(rows, 1)


def test_leap_day_and_duplicate_index():
    from src.data_cleaner import parse_daily_dates
    dates = pd.Series(["20240229", "2024-03-01"], index=[7, 7])
    result = parse_daily_dates(dates)
    assert list(result) == [pd.Timestamp("2024-02-29"), pd.Timestamp("2024-03-01")]
    assert list(result.index) == [7, 7]


@pytest.mark.parametrize("factor", [0, -1, float("inf"), None])
def test_invalid_adjustment_factor_is_rejected(factor):
    daily = pd.DataFrame({"trade_date": ["20240101"], "close": [1.0]})
    factors = pd.DataFrame({"trade_date": ["2024-01-01"], "adj_factor": [factor]})
    with pytest.raises(data_loader.DataDownloadError):
        data_loader._adjust_tushare_fund_prices(daily, factors, "qfq")


def test_adjustment_merge_accepts_mixed_date_keys():
    daily = pd.DataFrame({"trade_date": ["20240101", "2024-01-02"], "close": [2.0, 1.0]})
    factors = pd.DataFrame({"trade_date": ["2024-01-01", "20240102"], "adj_factor": [1.0, 2.0]})
    adjusted = data_loader._adjust_tushare_fund_prices(daily, factors, "qfq")
    assert list(adjusted["close"]) == [1.0, 1.0]


def test_etf_never_falls_back_to_index(monkeypatch):
    class FakeAk:
        def fund_etf_hist_em(self, **kwargs):
            return pd.DataFrame()
        def stock_zh_index_daily_em(self, **kwargs):
            pytest.fail("ETF must not use index history")
    monkeypatch.setattr(data_loader, "_optional_import", lambda _: FakeAk())
    with pytest.raises(data_loader.DataDownloadError, match="index fallback is prohibited"):
        data_loader._fetch_akshare_one(
            {"symbol": "510300.SH", "name": "ETF", "asset": "FD"}, {"data": {}}, logging.getLogger("test")
        )


def _download_config(tmp_path):
    return {"data": {
        "indices": [{"symbol": "ETF", "name": "ETF"}],
        "raw_dir": str(tmp_path / "raw"),
        "processed_path": str(tmp_path / "panel.parquet"),
        "min_observations": 2, "sleep_seconds": 0,
    }, "outputs": {"reports_dir": str(tmp_path / "reports")}}


def test_invalid_primary_uses_validated_fallback(monkeypatch, tmp_path):
    config = _download_config(tmp_path)
    bad = _panel_rows([1.0, 1.01])
    bad["date"] = ["20240101", "bad"]
    good = _panel_rows([1.0, 1.01])
    monkeypatch.setattr(data_loader, "_fetch_tushare_one", lambda *args: bad)
    monkeypatch.setattr(data_loader, "_fetch_akshare_one", lambda *args: good)
    result = data_loader.download_panel(config, logging.getLogger("test"))
    pd.testing.assert_frame_equal(result, standardize_panel(good, 2))


def test_partial_universe_preserves_snapshot(monkeypatch, tmp_path):
    config = _download_config(tmp_path)
    config["data"]["indices"].append({"symbol": "MISSING", "name": "Missing"})
    path = tmp_path / "panel.parquet"
    path.write_bytes(b"previous snapshot")
    def fetch(item, *args):
        if item["symbol"] == "MISSING":
            raise ConnectionError("offline")
        return _panel_rows([1.0, 1.01])
    monkeypatch.setattr(data_loader, "_fetch_tushare_one", fetch)
    monkeypatch.setattr(data_loader, "_fetch_akshare_one", fetch)
    with pytest.raises(data_loader.DataDownloadError, match="Incomplete configured universe"):
        data_loader.download_panel(config, logging.getLogger("test"))
    assert path.read_bytes() == b"previous snapshot"
    assert (tmp_path / "reports/data_failures.csv").exists()


def test_truncated_history_preserves_snapshot(monkeypatch, tmp_path):
    config = _download_config(tmp_path)
    path = tmp_path / "panel.parquet"
    _panel_rows([1.0, 1.01, 1.02]).to_parquet(path)
    original = path.read_bytes()
    monkeypatch.setattr(data_loader, "_fetch_tushare_one", lambda *args: _panel_rows([1.0, 1.01]))
    with pytest.raises(data_loader.DataDownloadError, match="existing daily keys"):
        data_loader.download_panel(config, logging.getLogger("test"))
    assert path.read_bytes() == original


def test_conflicting_duplicates_fail():
    rows = pd.concat([_panel_rows([1.0]), _panel_rows([2.0])], ignore_index=True)
    rows["date"] = ["20240101", "2024-01-01"]
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        standardize_panel(rows, 1)


def test_missing_factor_coverage_is_not_filled():
    daily = pd.DataFrame({"trade_date": ["20240101", "20240102"], "close": [1.0, 1.01]})
    factors = pd.DataFrame({"trade_date": ["20240101"], "adj_factor": [1.0]})
    with pytest.raises(data_loader.DataDownloadError, match="cover every daily price row"):
        data_loader._adjust_tushare_fund_prices(daily, factors, "qfq")
