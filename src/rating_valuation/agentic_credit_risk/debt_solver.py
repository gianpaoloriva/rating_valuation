"""Endogenous debt solver — Agentic Credit Risk equation [7].

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
    tax_rate: float | np.ndarray,
    cash_yield: float = 0.0,
    payout_ratio: float = 0.0,
    debt_floor: float | np.ndarray = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized single-period update of (debt, cash, interest, OCF).

    Implements the full dynamics described by Montesi/Papiro equations
    [3]-[4]-[5]-[6]-[8]-[9]:

    * Unclamped debt is computed from the closed-form [7], optionally
      augmented with dividends [9] and a debt floor [8].
    * If unclamped >= the floor, the company still carries debt; cash can
      grow through the yield on the previous cash stock (extension from
      Appendix A: ``yield = risk-free on CASH_{t-1}``).
    * If unclamped < floor the debt is clamped to the floor and the
      excess is credited to cash via equation [6]. Conversely, a negative
      free cash flow that would deplete the cash is allowed to reduce it
      down to the ``cash ≥ 0`` floor — this is a correction to the
      previous V1 which kept cash monotonically non-decreasing.

    Parameters
    ----------
    cash_yield : float
        Interest rate accrued on the previous period cash stock (Appendix A
        of the RAPD paper: "yield equal to risk-free rates"). Taxed at
        ``tax_rate``. Default 0 for backward compatibility.
    payout_ratio : float
        Dividend payout as a fraction of after-tax profit (paper eq. [9]):
        ``dividend = d · (NOPAT − INT·(1−τ))``. Default 0.
    debt_floor : float or array
        Minimum debt level in the period (paper eq. [8]): ``D_t = max(D_bar, …)``.
        Default 0.

    Returns
    -------
    (debt_t, cash_t, interest_t, ocf_t)
        Four arrays of the same shape as ``debt_prev``.
    """
    if cost_of_debt < 0:
        raise ValueError(f"Invalid cost_of_debt: {cost_of_debt}")
    if np.any(np.asarray(tax_rate) < 0) or np.any(np.asarray(tax_rate) >= 1):
        raise ValueError(f"Invalid tax_rate: {tax_rate}")
    if cash_yield < 0:
        raise ValueError(f"Invalid cash_yield: {cash_yield}")
    if not 0.0 <= payout_ratio <= 1.0:
        raise ValueError(f"payout_ratio must be in [0, 1], got {payout_ratio}")

    beta = (1.0 - tax_rate) * cost_of_debt / 2.0
    denom = 1.0 - beta
    if np.any(denom <= 0):
        raise ValueError(
            f"Denominator (1 - beta) is non-positive: beta={beta}"
        )

    # After-tax yield on previous cash stock (paper Appendix A extension).
    cash_income = cash_yield * cash_prev * (1.0 - tax_rate)

    # Dividend payout (paper eq. [9]) — applied to the previous-debt
    # interest proxy as in Montesi/Papiro (before the endogenous D_t is
    # known, the cash-flow treatment of interest uses the INT on D_{t-1}).
    # This preserves backward compatibility when payout_ratio=0.
    int_prev_proxy = cost_of_debt * debt_prev / 2.0
    after_tax_profit_proxy = nopat - int_prev_proxy * (1.0 - tax_rate)
    dividend = payout_ratio * np.maximum(after_tax_profit_proxy, 0.0)

    # Unclamped recursive debt from the closed form [7], extended with
    # dividends [9] and the cash yield on previous cash:
    raw_debt = (
        debt_prev * (1.0 + beta) - nopat + delta_nic - capital_increase
        + dividend - cash_income
    ) / denom

    floor_arr = np.asarray(debt_floor, dtype=float)

    # Case A: unclamped >= floor → company still carries debt
    debt_normal = np.maximum(raw_debt, floor_arr)
    int_normal = cost_of_debt * (debt_prev + debt_normal) / 2.0
    ocf_normal = nopat - delta_nic + tax_rate * int_normal + cash_income

    # Case B: unclamped < floor → debt clamped to the floor and excess
    # goes (or is drawn from) cash.
    debt_clamped = np.broadcast_to(floor_arr, debt_prev.shape).copy()
    int_clamped = cost_of_debt * (debt_prev + debt_clamped) / 2.0
    ocf_clamped = nopat - delta_nic + tax_rate * int_clamped + cash_income
    # Eq [6] excess/deficit cash generated this period:
    excess_cash = (
        debt_clamped - debt_prev + ocf_clamped - int_clamped + capital_increase
        - dividend
    )

    # Select per element
    is_clamped = raw_debt < floor_arr
    debt_t = np.where(is_clamped, debt_clamped, debt_normal)
    int_t = np.where(is_clamped, int_clamped, int_normal)
    ocf_t = np.where(is_clamped, ocf_clamped, ocf_normal)

    # Cash dynamics (paper [6]): cash changes by the signed delta when
    # debt is clamped, and is otherwise unchanged. Apply a physical floor
    # at 0 (cash cannot be negative) but no longer forbid the cash from
    # decreasing — a stress scenario that erodes liquidity must be
    # allowed to do so, as the paper's own derivation prescribes.
    cash_t = cash_prev + np.where(is_clamped, excess_cash, 0.0)
    cash_t = np.maximum(cash_t, 0.0)

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
    cash_yield: float = 0.0,
    payout_ratio: float = 0.0,
    debt_floor: float = 0.0,
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
        cash_yield=cash_yield,
        payout_ratio=payout_ratio,
        debt_floor=debt_floor,
    )
    return float(d[0]), float(c[0]), float(i[0]), float(o[0])
