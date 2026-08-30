"""Tests for convex portfolio construction."""

import numpy as np
import pandas as pd

from src.optimizer import estimate_covariance, optimize_convex_weights


def test_covariance_is_finite_symmetric_and_psd() -> None:
    """Shrinkage and eigenvalue flooring should stabilize incomplete histories."""
    returns = pd.DataFrame(
        {
            "A": [0.01, 0.02, np.nan, 0.00],
            "B": [0.02, 0.04, np.nan, 0.00],
            "C": [0.00, 0.00, 0.00, 0.00],
        }
    )
    covariance = estimate_covariance(returns, shrinkage=0.2, ridge=1e-5, annualization_factor=252)
    values = covariance.to_numpy()
    assert np.isfinite(values).all()
    np.testing.assert_allclose(values, values.T, atol=1e-12)
    assert np.linalg.eigvalsh(values).min() >= 1e-5 - 1e-10


def test_optimizer_respects_budget_bounds_and_signal_order() -> None:
    """With negligible risk, stronger alpha should receive the binding upper weight."""
    symbols = pd.Index(["A", "B", "C"])
    weights, diagnostics = optimize_convex_weights(
        pd.Series([3.0, 2.0, 1.0], index=symbols),
        pd.DataFrame(np.eye(3) * 1e-8, index=symbols, columns=symbols),
        exposure=1.0,
        max_weight=0.6,
        signal_scale=0.1,
        risk_aversion=0.0,
        crowding_aversion=0.0,
        turnover_penalty_bps=0.0,
    )
    assert diagnostics["status"] == "solved"
    assert abs(weights.sum() - 1.0) < 1e-7
    assert (weights >= -1e-9).all()
    assert (weights <= 0.6 + 1e-7).all()
    assert weights["A"] > weights["B"] > weights["C"] - 1e-8
    assert weights["A"] > 0.59


def test_exposure_is_reduced_when_weight_capacity_is_insufficient() -> None:
    """A small eligible universe should keep cash instead of making the QP infeasible."""
    symbols = pd.Index(["A", "B"])
    weights, diagnostics = optimize_convex_weights(
        pd.Series([2.0, 1.0], index=symbols),
        pd.DataFrame(np.eye(2), index=symbols, columns=symbols),
        exposure=1.0,
        max_weight=0.3,
        turnover_penalty_bps=0.0,
    )
    assert abs(weights.sum() - 0.6) < 1e-7
    assert diagnostics["target_exposure"] == 0.6


def test_risk_penalty_reduces_high_variance_weight() -> None:
    """At equal alpha, a higher-variance asset should receive less weight."""
    symbols = pd.Index(["high_risk", "low_risk"])
    covariance = pd.DataFrame([[0.20, 0.0], [0.0, 0.02]], index=symbols, columns=symbols)
    weights, _ = optimize_convex_weights(
        pd.Series([1.0, 1.0], index=symbols),
        covariance,
        exposure=1.0,
        max_weight=1.0,
        signal_scale=0.0,
        risk_aversion=4.0,
        crowding_aversion=0.0,
        turnover_penalty_bps=0.0,
    )
    assert weights["low_risk"] > weights["high_risk"]


def test_turnover_penalty_and_cap_control_trading() -> None:
    """L1 costs and a hard cap should keep the target closer to current holdings."""
    symbols = pd.Index(["A", "B", "C"])
    scores = pd.Series([0.0, 0.0, 5.0], index=symbols)
    covariance = pd.DataFrame(np.eye(3) * 1e-5, index=symbols, columns=symbols)
    previous = pd.Series([0.5, 0.5, 0.0], index=symbols)

    unconstrained, _ = optimize_convex_weights(
        scores,
        covariance,
        previous,
        exposure=1.0,
        max_weight=0.8,
        risk_aversion=0.0,
        crowding_aversion=0.0,
        turnover_penalty_bps=0.0,
    )
    controlled, diagnostics = optimize_convex_weights(
        scores,
        covariance,
        previous,
        exposure=1.0,
        max_weight=0.8,
        risk_aversion=0.0,
        crowding_aversion=0.0,
        turnover_penalty_bps=1000.0,
        max_turnover=0.2,
    )
    uncontrolled_turnover = float((unconstrained - previous).abs().sum())
    controlled_turnover = float((controlled - previous).abs().sum())
    assert controlled_turnover <= 0.2 + 1e-6
    assert controlled_turnover < uncontrolled_turnover
    assert diagnostics["turnover_slack"] >= -1e-6


def test_cash_and_volatility_cap_form_a_feasible_convex_risk_control() -> None:
    """A QCQP volatility cap should reduce exposure when full investment is too risky."""
    symbols = pd.Index(["A", "B", "C"])
    covariance = pd.DataFrame(np.eye(3) * 0.09, index=symbols, columns=symbols)
    weights, diagnostics = optimize_convex_weights(
        pd.Series([3.0, 2.0, 1.0], index=symbols),
        covariance,
        exposure=1.0,
        max_weight=0.6,
        signal_scale=0.1,
        risk_aversion=1.0,
        crowding_aversion=0.0,
        turnover_penalty_bps=0.0,
        allow_cash=True,
        max_ex_ante_volatility=0.10,
    )
    realized_volatility = float(np.sqrt(weights.to_numpy() @ covariance.to_numpy() @ weights.to_numpy()))
    assert weights.sum() < 1.0
    assert realized_volatility <= 0.10 + 1e-6
    assert diagnostics["volatility_slack"] >= -1e-6
