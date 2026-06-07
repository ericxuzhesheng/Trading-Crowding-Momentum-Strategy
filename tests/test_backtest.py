"""Unit tests for backtest and performance behavior."""

import pandas as pd

from src.backtest import build_daily_weights, calculate_transaction_cost, run_single_strategy
from src.factors import add_factors
from src.performance import max_drawdown


def test_max_drawdown() -> None:
    """Maximum drawdown should capture the worst peak-to-trough loss."""
    nav = pd.Series([1.0, 1.2, 0.9, 1.1])
    assert round(max_drawdown(nav), 6) == -0.25


def test_transaction_cost_calculation() -> None:
    """A 50 percent one-way turnover at 3 bps costs 0.00015 NAV units."""
    assert calculate_transaction_cost(0.5, 3) == 0.00015


def test_no_lookahead_basic_check() -> None:
    """Changing today's score should not alter the return earned on the same date."""
    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    rows = []
    for symbol, offset in [("000300.SH", 0), ("A", 1), ("B", 2), ("C", 3), ("D", 4), ("E", 5)]:
        for i, date in enumerate(dates):
            rows.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "name": symbol,
                    "open": 100 + i + offset,
                    "high": 101 + i + offset,
                    "low": 99 + i + offset,
                    "close": 100 + i + offset,
                    "volume": 1000 + i + offset,
                    "amount": 100000 + i * 100 + offset,
                    "turnover": 1 + i * 0.01 + offset * 0.01,
                }
            )
    config = {
        "factors": {"ret_short_window": 5, "ret_long_window": 20, "crowding_window": 60, "volatility_window": 20},
        "strategy": {
            "benchmark_symbol": "000300.SH",
            "benchmark_ma_window": 60,
            "risk_on_exposure": 1.0,
            "risk_off_exposure": 0.3,
            "top_quantile": 0.2,
            "max_weight": 0.1,
            "transaction_cost_bps": 3,
        },
    }
    factors = add_factors(pd.DataFrame(rows), config)
    nav1, _, _ = run_single_strategy(factors, config, "momentum_crowding_penalty", trend_filter=False)
    mutated = factors.copy()
    first_valid_date = mutated["date"].sort_values().unique()[80]
    mutated.loc[mutated["date"] == first_valid_date, "score_signal"] = 999
    nav2, _, _ = run_single_strategy(mutated, config, "momentum_crowding_penalty", trend_filter=False)
    before_or_same = nav1["date"] <= first_valid_date
    pd.testing.assert_series_equal(nav1.loc[before_or_same, "return"], nav2.loc[before_or_same, "return"], check_names=False)


def test_rebalance_zero_weight_sells_position() -> None:
    """A zero target at a rebalance must sell the previous holding instead of forward filling it."""
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    symbols = ["000300.SH", "A", "B", "C", "D"]
    rows = []
    for symbol in symbols:
        for i, date in enumerate(dates):
            score = 10 if symbol == "A" and i < 10 else 0
            score = 10 if symbol == "B" and i >= 10 else score
            rows.append({"date": date, "symbol": symbol, "close": 100 + i, "score_signal": score})
    factors = pd.DataFrame(rows)
    config = {
        "strategy": {
            "benchmark_symbol": "000300.SH",
            "benchmark_ma_window": 3,
            "risk_on_exposure": 1.0,
            "risk_off_exposure": 0.0,
            "top_quantile": 0.2,
            "max_weight": 1.0,
            "transaction_cost_bps": 0,
        }
    }
    weights = build_daily_weights(factors, config, "momentum_crowding_penalty", trend_filter=False)
    assert weights["A"].iloc[-1] == 0.0
    assert weights["B"].iloc[-1] > 0.0
