from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from src.research_validation import holding_period_ic, matched_factors


def test_ic_uses_next_trade_close_and_omits_unfinished_week():
    dates = pd.bdate_range("2024-01-01", periods=16)
    rows = []
    for j, symbol in enumerate("ABC"):
        prices = np.full(len(dates), 100.0)
        prices[5] = 50.0 + 50.0 * j  # entry Monday
        prices[10:] = prices[5] * (1 + 0.1 * (j + 1))
        for i, day in enumerate(dates):
            rows.append({"date": day, "symbol": symbol, "close": prices[i], "score_signal": j})
    factors = pd.DataFrame(rows)
    ic = holding_period_ic(factors, min_assets=3)
    assert len(ic) == 2
    assert ic.iloc[0].entry_date == dates[5]
    assert ic.iloc[0].exit_date == dates[10]
    assert ic.iloc[0].spearman_ic == pytest.approx(1.0)
    factors.loc[factors.date == dates[4], "close"] *= 100  # decision-day close is not the return entry
    assert holding_period_ic(factors, 3).iloc[0].spearman_ic == pytest.approx(1.0)


def test_ablation_preserves_config_eligibility_and_momentum():
    dates = pd.bdate_range("2024-01-01", periods=40)
    panel = pd.DataFrame([{"date": d, "symbol": s, "close": 100 + i + j,
                          "turnover": i + 1, "volume": i + 10, "amount": i * 10 + 100}
                         for j, s in enumerate("ABC") for i, d in enumerate(dates)])
    config = {"factors": {"ret_short_window": 5, "ret_long_window": 20, "crowding_window": 20,
               "volatility_window": 20, "score_weights": {"ret_5d": 1, "ret_20d": 1, "crowding_penalty": .65}},
              "strategy": {"convex_optimizer": {"crowding_aversion": 0}}}
    original = deepcopy(config)
    baseline, without, changed = matched_factors(panel, config)
    assert config == original
    assert changed["factors"]["score_weights"]["crowding_penalty"] == 0
    pd.testing.assert_series_equal(baseline.score_signal.isna(), without.score_signal.isna())
    np.testing.assert_allclose((without.score - baseline.score).dropna(),
                               (.65 * baseline.rank_crowding_score)[baseline.score.notna()])
