"""Unit tests for factor utilities."""

import pandas as pd

from src.factors import add_factors, cross_sectional_rank, rolling_zscore


def test_rolling_zscore() -> None:
    """The last rolling z-score should match the known trailing window value."""
    series = pd.Series([1.0, 2.0, 3.0, 4.0])
    result = rolling_zscore(series, window=4)
    assert round(result.iloc[-1], 6) == round((4.0 - 2.5) / series.std(ddof=0), 6)


def test_cross_sectional_rank() -> None:
    """Cross-sectional ranks should be normalized to 0-1 percentiles."""
    ranked = cross_sectional_rank(pd.Series([10, 20, 30], index=list("abc")))
    assert ranked.loc["a"] == 1 / 3
    assert ranked.loc["c"] == 1.0


def test_factor_signals_are_lagged() -> None:
    """Tradable score signals must be the prior day's raw score for each symbol."""
    rows = []
    for symbol in ["A", "B", "C", "D", "E"]:
        for i in range(90):
            rows.append(
                {
                    "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                    "symbol": symbol,
                    "name": symbol,
                    "open": 100 + i,
                    "high": 101 + i,
                    "low": 99 + i,
                    "close": 100 + i + ord(symbol) % 5,
                    "volume": 1000 + i * 10 + ord(symbol),
                    "amount": 100000 + i * 1000 + ord(symbol),
                    "turnover": 1 + i * 0.01 + (ord(symbol) % 3),
                }
            )
    factors = add_factors(pd.DataFrame(rows), {"factors": {"ret_short_window": 5, "ret_long_window": 20, "crowding_window": 60, "volatility_window": 20}})
    sample = factors[factors["symbol"] == "A"].sort_values("date").dropna(subset=["score", "score_signal"])
    assert sample["score_signal"].iloc[-1] == factors[factors["symbol"] == "A"].sort_values("date")["score"].shift(1).dropna().iloc[-1]
