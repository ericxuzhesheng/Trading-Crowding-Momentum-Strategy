"""Convex portfolio construction for crowding-adjusted momentum signals."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def estimate_covariance(
    returns: pd.DataFrame,
    shrinkage: float = 0.25,
    ridge: float = 1e-6,
    annualization_factor: float = 252.0,
) -> pd.DataFrame:
    """Estimate a symmetric PSD covariance matrix from an incomplete return panel."""
    if returns.shape[1] == 0:
        raise ValueError("At least one asset is required to estimate covariance.")
    if not 0.0 <= shrinkage <= 1.0:
        raise ValueError("shrinkage must be between 0 and 1.")
    if ridge < 0.0 or annualization_factor <= 0.0:
        raise ValueError("ridge must be non-negative and annualization_factor must be positive.")

    numeric = returns.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    means = numeric.mean(axis=0)
    centered = numeric.fillna(means).fillna(0.0).sub(means.fillna(0.0), axis=1)
    values = centered.to_numpy(dtype=float)
    denominator = max(len(centered) - 1, 1)
    sample = values.T @ values / denominator
    diagonal = np.diag(np.diag(sample))
    covariance = ((1.0 - shrinkage) * sample + shrinkage * diagonal) * annualization_factor
    covariance = (covariance + covariance.T) / 2.0

    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.maximum(eigenvalues, ridge)
    covariance = (eigenvectors * eigenvalues) @ eigenvectors.T
    covariance = (covariance + covariance.T) / 2.0
    return pd.DataFrame(covariance, index=returns.columns, columns=returns.columns)


def _project_capped_simplex(values: np.ndarray, total: float, upper: float) -> np.ndarray:
    """Project values onto {x | sum(x)=total, 0<=x<=upper}."""
    if total <= 0.0:
        return np.zeros_like(values, dtype=float)
    if total > len(values) * upper + 1e-10:
        raise ValueError("Requested exposure exceeds the portfolio's weight capacity.")

    lower_theta = float(np.min(values - upper))
    upper_theta = float(np.max(values))
    for _ in range(100):
        theta = (lower_theta + upper_theta) / 2.0
        projected = np.clip(values - theta, 0.0, upper)
        if projected.sum() > total:
            lower_theta = theta
        else:
            upper_theta = theta
    projected = np.clip(values - (lower_theta + upper_theta) / 2.0, 0.0, upper)

    residual = total - float(projected.sum())
    if residual > 0.0:
        room = upper - projected
        for idx in np.argsort(-room):
            addition = min(residual, float(room[idx]))
            projected[idx] += addition
            residual -= addition
            if residual <= 1e-12:
                break
    elif residual < 0.0:
        for idx in np.argsort(-projected):
            reduction = min(-residual, float(projected[idx]))
            projected[idx] -= reduction
            residual += reduction
            if residual >= -1e-12:
                break
    return projected


def _feasible_start(previous: np.ndarray, alpha: np.ndarray, total: float, upper: float) -> np.ndarray:
    """Construct a feasible, minimum-turnover starting point for SLSQP."""
    weights = np.clip(previous, 0.0, upper)
    difference = total - float(weights.sum())
    if difference > 0.0:
        for idx in np.argsort(-alpha):
            addition = min(difference, upper - float(weights[idx]))
            weights[idx] += addition
            difference -= addition
            if difference <= 1e-12:
                break
    elif difference < 0.0:
        for idx in np.argsort(alpha):
            reduction = min(-difference, float(weights[idx]))
            weights[idx] -= reduction
            difference += reduction
            if difference >= -1e-12:
                break
    if abs(difference) > 1e-9:
        raise ValueError("Unable to construct a feasible portfolio from the supplied bounds.")
    return weights


def optimize_convex_weights(
    scores: pd.Series,
    covariance: pd.DataFrame,
    previous_weights: pd.Series | None = None,
    crowding: pd.Series | None = None,
    *,
    exposure: float = 1.0,
    max_weight: float = 0.10,
    signal_scale: float = 0.10,
    risk_aversion: float = 4.0,
    crowding_aversion: float = 0.05,
    turnover_penalty_bps: float = 10.0,
    max_turnover: float | None = None,
    allow_cash: bool = False,
    max_ex_ante_volatility: float | None = None,
    fixed_turnover: float = 0.0,
    solver_tolerance: float = 1e-9,
    max_iterations: int = 500,
) -> tuple[pd.Series, dict[str, Any]]:
    """Solve a long-only convex portfolio problem with optional cash and volatility limits."""
    clean_scores = pd.to_numeric(scores, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean_scores.empty:
        raise ValueError("At least one finite score is required.")
    if max_weight <= 0.0 or exposure < 0.0:
        raise ValueError("max_weight must be positive and exposure must be non-negative.")
    if min(signal_scale, risk_aversion, crowding_aversion, turnover_penalty_bps, fixed_turnover) < 0.0:
        raise ValueError("Objective coefficients and fixed_turnover must be non-negative.")

    symbols = clean_scores.index
    exposure_limit = min(float(exposure), len(symbols) * float(max_weight))
    if exposure_limit <= 0.0:
        return pd.Series(0.0, index=symbols), {
            "status": "zero_exposure",
            "target_exposure": 0.0,
            "exposure_limit": 0.0,
            "objective": 0.0,
            "ex_ante_volatility": 0.0,
            "iterations": 0,
        }
    if max_ex_ante_volatility is not None and max_ex_ante_volatility <= 0.0:
        raise ValueError("max_ex_ante_volatility must be positive when supplied.")

    covariance = covariance.reindex(index=symbols, columns=symbols)
    covariance_values = covariance.to_numpy(dtype=float)
    if not np.isfinite(covariance_values).all():
        raise ValueError("covariance must contain only finite values.")
    covariance_values = (covariance_values + covariance_values.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(covariance_values)
    covariance_values = (eigenvectors * np.maximum(eigenvalues, 0.0)) @ eigenvectors.T

    score_values = clean_scores.to_numpy(dtype=float)
    score_std = float(score_values.std(ddof=0))
    alpha = np.zeros_like(score_values)
    if score_std > 1e-12:
        alpha = signal_scale * (score_values - float(score_values.mean())) / score_std

    if crowding is None:
        crowding_values = np.zeros(len(symbols), dtype=float)
    else:
        clean_crowding = pd.to_numeric(crowding.reindex(symbols), errors="coerce")
        crowding_values = clean_crowding.rank(method="average", pct=True).fillna(0.0).to_numpy(dtype=float)

    previous = (
        pd.Series(0.0, index=symbols)
        if previous_weights is None
        else pd.to_numeric(previous_weights.reindex(symbols), errors="coerce").fillna(0.0)
    ).to_numpy(dtype=float)
    turnover_penalty = turnover_penalty_bps / 10000.0
    n_assets = len(symbols)

    if allow_cash:
        initial_weights = np.clip(previous, 0.0, max_weight)
        if initial_weights.sum() > exposure_limit:
            initial_weights = _project_capped_simplex(initial_weights, exposure_limit, max_weight)
        if max_ex_ante_volatility is not None:
            initial_variance = float(initial_weights @ covariance_values @ initial_weights)
            if initial_variance > max_ex_ante_volatility**2:
                initial_weights *= max_ex_ante_volatility / np.sqrt(initial_variance)
    else:
        initial_weights = _feasible_start(previous, alpha, exposure_limit, max_weight)
    initial_turnover = float(np.abs(initial_weights - previous).sum()) + fixed_turnover
    if max_turnover is not None and initial_turnover > max_turnover + 1e-9:
        raise ValueError(
            f"max_turnover={max_turnover:.6f} is infeasible; minimum required turnover is {initial_turnover:.6f}."
        )
    initial_aux = np.abs(initial_weights - previous)
    initial = np.concatenate([initial_weights, initial_aux])

    def components(weights: np.ndarray, turnover_aux: np.ndarray) -> tuple[float, float, float, float]:
        signal_component = -float(alpha @ weights)
        risk_component = 0.5 * risk_aversion * float(weights @ covariance_values @ weights)
        crowding_component = 0.5 * crowding_aversion * float(crowding_values @ np.square(weights))
        turnover_component = turnover_penalty * (float(turnover_aux.sum()) + fixed_turnover)
        return signal_component, risk_component, crowding_component, turnover_component

    def objective(vector: np.ndarray) -> float:
        return float(sum(components(vector[:n_assets], vector[n_assets:])))

    def gradient(vector: np.ndarray) -> np.ndarray:
        weights = vector[:n_assets]
        weight_gradient = (
            -alpha
            + risk_aversion * covariance_values @ weights
            + crowding_aversion * crowding_values * weights
        )
        return np.concatenate([weight_gradient, np.full(n_assets, turnover_penalty)])

    budget_constraint = (
        {
            "type": "ineq",
            "fun": lambda vector: float(exposure_limit - vector[:n_assets].sum()),
            "jac": lambda vector: np.concatenate([-np.ones(n_assets), np.zeros(n_assets)]),
        }
        if allow_cash
        else {
            "type": "eq",
            "fun": lambda vector: float(vector[:n_assets].sum() - exposure_limit),
            "jac": lambda vector: np.concatenate([np.ones(n_assets), np.zeros(n_assets)]),
        }
    )
    constraints: list[dict[str, Any]] = [
        budget_constraint,
        {
            "type": "ineq",
            "fun": lambda vector: np.concatenate(
                [vector[n_assets:] - vector[:n_assets] + previous, vector[n_assets:] + vector[:n_assets] - previous]
            ),
            "jac": lambda vector: np.block(
                [
                    [-np.eye(n_assets), np.eye(n_assets)],
                    [np.eye(n_assets), np.eye(n_assets)],
                ]
            ),
        },
    ]
    if max_turnover is not None:
        constraints.append(
            {
                "type": "ineq",
                "fun": lambda vector: float(max_turnover - fixed_turnover - vector[n_assets:].sum()),
                "jac": lambda vector: np.concatenate([np.zeros(n_assets), -np.ones(n_assets)]),
            }
        )
    if max_ex_ante_volatility is not None:
        variance_limit = max_ex_ante_volatility**2
        constraints.append(
            {
                "type": "ineq",
                "fun": lambda vector: float(
                    variance_limit - vector[:n_assets] @ covariance_values @ vector[:n_assets]
                ),
                "jac": lambda vector: np.concatenate(
                    [-2.0 * covariance_values @ vector[:n_assets], np.zeros(n_assets)]
                ),
            }
        )

    auxiliary_upper = max(2.0, float(previous.sum()) + exposure_limit)
    bounds = [(0.0, max_weight)] * n_assets + [(0.0, auxiliary_upper)] * n_assets
    result = minimize(
        objective,
        initial,
        jac=gradient,
        bounds=bounds,
        constraints=constraints,
        method="SLSQP",
        options={"ftol": solver_tolerance, "maxiter": int(max_iterations), "disp": False},
    )
    if not result.success:
        raise RuntimeError(f"Convex optimizer failed: {result.message}")

    weights = np.clip(result.x[:n_assets], 0.0, max_weight)
    if allow_cash:
        if weights.sum() > exposure_limit + 1e-8:
            weights = _project_capped_simplex(weights, exposure_limit, max_weight)
    else:
        weights = _project_capped_simplex(weights, exposure_limit, max_weight)
    actual_turnover = float(np.abs(weights - previous).sum()) + fixed_turnover
    if max_turnover is not None and actual_turnover > max_turnover + 1e-6:
        raise RuntimeError("Convex optimizer returned a portfolio above max_turnover.")

    variance = max(float(weights @ covariance_values @ weights), 0.0)
    if max_ex_ante_volatility is not None and variance > max_ex_ante_volatility**2 + 1e-7:
        raise RuntimeError("Convex optimizer returned a portfolio above max_ex_ante_volatility.")

    actual_aux = np.abs(weights - previous)
    signal_component, risk_component, crowding_component, turnover_component = components(weights, actual_aux)
    diagnostics: dict[str, Any] = {
        "status": "solved",
        "target_exposure": float(weights.sum()),
        "exposure_limit": exposure_limit,
        "objective": signal_component + risk_component + crowding_component + turnover_component,
        "signal_component": signal_component,
        "risk_component": risk_component,
        "crowding_component": crowding_component,
        "turnover_component": turnover_component,
        "ex_ante_volatility": float(np.sqrt(variance)),
        "iterations": int(result.nit),
    }
    if max_turnover is not None:
        diagnostics["turnover_slack"] = float(max_turnover - actual_turnover)
    if max_ex_ante_volatility is not None:
        diagnostics["volatility_slack"] = float(max_ex_ante_volatility - np.sqrt(variance))
    return pd.Series(weights, index=symbols), diagnostics
