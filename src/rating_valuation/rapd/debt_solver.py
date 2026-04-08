"""Endogenous debt solver — RAPD equation [7].

Given the operating state at time t and the previous period's debt, this
module determines the end-of-period debt under the financial equilibrium
constraint (cash inflow == cash outflow).

Derivation (Montesi/Papiro, eqs. 3-5-7):

    OCF_t       = NOPAT_t − ΔNIC_t + τ · INT_t             [3]
    INT_t       = r_d · (D_{t-1} + D_t) / 2                [4]
    D_t         = max(0, D_{t-1} − OCF_t + INT_t − ΔCAP_t) [5]

Substituting [3] then [4] into [5] and solving for D_t gives the paper's
closed-form expression [7]. This module implements the equivalent (and
easier to read) arrangement:

    β          = (1 − τ) · r_d / 2
    D_raw      = (D_{t-1}·(1+β) − NOPAT_t + ΔNIC_t − ΔCAP_t) / (1 − β)
    D_t        = max(0, D_raw)

Both scalar and vectorized (numpy) variants are provided — the vectorized
version is what the Monte Carlo simulator uses for speed.
"""

from __future__ import annotations

import numpy as np


def solve_debt_scalar(
    *,
    debt_prev: float,
    nopat: float,
    delta_nic: float,
    capital_increase: float,
    cost_of_debt: float,
    tax_rate: float,
) -> float:
    """Single-period recursive debt update (scalar version).

    Parameters
    ----------
    debt_prev : float
        Stock of debt at the start of the period (``D_{t-1}``).
    nopat : float
        NOPAT for the period (``NOPAT_t``).
    delta_nic : float
        Change in net invested capital (``ΔNIC_t = NIC_t − NIC_{t-1}``).
    capital_increase : float
        Additional equity raised in the period (``ΔCAP_t``, often 0).
    cost_of_debt : float
        Pre-tax cost of debt (``r_d``).
    tax_rate : float
        Corporate tax rate (``τ``), decimal.

    Returns
    -------
    float
        End-of-period debt ``D_t``, floored at 0.
    """
    if cost_of_debt < 0 or tax_rate < 0 or tax_rate >= 1:
        raise ValueError(
            f"Invalid inputs: cost_of_debt={cost_of_debt}, tax_rate={tax_rate}"
        )
    beta = (1.0 - tax_rate) * cost_of_debt / 2.0
    denom = 1.0 - beta
    if denom <= 0:
        raise ValueError(
            f"Denominator (1 - beta) is non-positive: beta={beta}. "
            "Cost of debt too high relative to tax rate."
        )
    numerator = debt_prev * (1.0 + beta) - nopat + delta_nic - capital_increase
    raw = numerator / denom
    return max(0.0, raw)


def solve_debt_vectorized(
    *,
    debt_prev: np.ndarray,
    nopat: np.ndarray,
    delta_nic: np.ndarray,
    capital_increase: np.ndarray | float,
    cost_of_debt: float,
    tax_rate: float,
) -> np.ndarray:
    """Vectorized version of :func:`solve_debt_scalar` across Monte Carlo trials.

    All array parameters must have the same shape (typically ``(n_trials,)``).
    ``capital_increase`` can be a scalar (broadcast).
    """
    if cost_of_debt < 0 or tax_rate < 0 or tax_rate >= 1:
        raise ValueError(
            f"Invalid inputs: cost_of_debt={cost_of_debt}, tax_rate={tax_rate}"
        )
    beta = (1.0 - tax_rate) * cost_of_debt / 2.0
    denom = 1.0 - beta
    if denom <= 0:
        raise ValueError(
            f"Denominator (1 - beta) is non-positive: beta={beta}"
        )
    numerator = debt_prev * (1.0 + beta) - nopat + delta_nic - capital_increase
    return np.maximum(0.0, numerator / denom)


def interest_expense(
    *,
    debt_prev: float | np.ndarray,
    debt_now: float | np.ndarray,
    cost_of_debt: float,
) -> float | np.ndarray:
    """Average-stock interest expense: ``INT_t = r_d · (D_{t-1} + D_t) / 2`` (eq. [4])."""
    return cost_of_debt * (debt_prev + debt_now) / 2.0


def operating_cash_flow(
    *,
    nopat: float | np.ndarray,
    delta_nic: float | np.ndarray,
    interest: float | np.ndarray,
    tax_rate: float,
) -> float | np.ndarray:
    """Capital cash flow (Ruback 2002): ``OCF_t = NOPAT_t − ΔNIC_t + τ · INT_t`` (eq. [3])."""
    return nopat - delta_nic + tax_rate * interest


# -----------------------------------------------------------------------------
# Full-period update with dynamic cash (eq. [6])
# -----------------------------------------------------------------------------


def simulate_period_vectorized(
    *,
    debt_prev: np.ndarray,
    cash_prev: np.ndarray,
    nopat: np.ndarray,
    delta_nic: np.ndarray,
    capital_increase: np.ndarray | float,
    cost_of_debt: float,
    tax_rate: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized single-period update of (debt, cash, interest, OCF).

    Implements the full dynamics described by Montesi/Papiro equations
    [3]-[4]-[5]-[6]:

    * Unclamped debt is computed from the closed-form [7].
    * If unclamped >= 0 the company still carries debt; cash remains at
      its previous level (no endogenous cash generation/retention modelled
      in this simplified V1).
    * If unclamped < 0 the debt is floored at zero and the excess is
      credited to cash via equation [6]:
      ``CASH_t = CASH_{t-1} + (D_t - D_{t-1} + OCF_t - INT_t + ΔCAP_t)``
      with ``D_t = 0`` and interest computed on the half-stock average
      (0 + D_{t-1})/2.

    Returns
    -------
    (debt_t, cash_t, interest_t, ocf_t)
        Four arrays of the same shape as ``debt_prev``.
    """
    if cost_of_debt < 0 or tax_rate < 0 or tax_rate >= 1:
        raise ValueError(
            f"Invalid inputs: cost_of_debt={cost_of_debt}, tax_rate={tax_rate}"
        )

    beta = (1.0 - tax_rate) * cost_of_debt / 2.0
    denom = 1.0 - beta
    if denom <= 0:
        raise ValueError(
            f"Denominator (1 - beta) is non-positive: beta={beta}"
        )

    # Unclamped recursive debt from the closed form
    raw_debt = (
        debt_prev * (1.0 + beta) - nopat + delta_nic - capital_increase
    ) / denom

    # Case A: unclamped >= 0 → company still has debt
    debt_normal = np.maximum(raw_debt, 0.0)  # same as raw where raw >= 0, else 0
    int_normal = cost_of_debt * (debt_prev + debt_normal) / 2.0
    ocf_normal = nopat - delta_nic + tax_rate * int_normal

    # Case B: unclamped < 0 → debt clamped to 0 and excess goes to cash
    debt_clamped = np.zeros_like(debt_prev)
    int_clamped = cost_of_debt * debt_prev / 2.0  # only on the previous stock
    ocf_clamped = nopat - delta_nic + tax_rate * int_clamped
    # Eq [6] excess cash generated this period:
    excess_cash = (
        debt_clamped - debt_prev + ocf_clamped - int_clamped + capital_increase
    )

    # Select per element
    is_clamped = raw_debt < 0
    debt_t = np.where(is_clamped, debt_clamped, debt_normal)
    int_t = np.where(is_clamped, int_clamped, int_normal)
    ocf_t = np.where(is_clamped, ocf_clamped, ocf_normal)
    # Cash grows only when excess is generated (max with 0 to protect from
    # numerical noise at the boundary).
    cash_t = cash_prev + np.where(is_clamped, np.maximum(excess_cash, 0.0), 0.0)

    return debt_t, cash_t, int_t, ocf_t


def simulate_period_scalar(
    *,
    debt_prev: float,
    cash_prev: float,
    nopat: float,
    delta_nic: float,
    capital_increase: float,
    cost_of_debt: float,
    tax_rate: float,
) -> tuple[float, float, float, float]:
    """Scalar convenience wrapper around :func:`simulate_period_vectorized`."""
    d, c, i, o = simulate_period_vectorized(
        debt_prev=np.array([debt_prev]),
        cash_prev=np.array([cash_prev]),
        nopat=np.array([nopat]),
        delta_nic=np.array([delta_nic]),
        capital_increase=capital_increase,
        cost_of_debt=cost_of_debt,
        tax_rate=tax_rate,
    )
    return float(d[0]), float(c[0]), float(i[0]), float(o[0])
