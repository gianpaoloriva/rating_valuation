"""Long-term / short-term debt split — paper RAPD Section 4, extension (3).

The reduced V1 model uses a single debt pool with a uniform cost of
debt. The paper notes (Section 4) that a realistic capital structure
uses long-term debt to finance Capex and short-term debt to finance
NWC, with different costs (short < long typically).

This module implements the closed-form recursion from `debt_solver.py`
generalized to two tranches. The simulator does not yet use it by
default (the reduced model of Section 2 is what `simulator.py` runs),
but an Appendix-A runner can plug this in when needed.

Model
-----
Assume two independent tranches:

    D_long  — finances the net fixed assets (NFA), cost r_long
    D_short — finances the net working capital (NWC), cost r_short

Each tranche follows its own version of the closed-form equation [7]:

    β_X       = (1 − τ) · r_X / 2
    D_X,t     = [ D_X,{t-1}·(1+β_X) − NOPAT_X + ΔNIC_X − ΔCAP_X ] / (1 − β_X)

where ``NOPAT_X`` is the share of NOPAT allocated to tranche X. A
reasonable allocation is by NIC weight:

    NOPAT_long  = NOPAT · (NFA / NIC)
    NOPAT_short = NOPAT · (NWC / NIC)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from rating_valuation.agentic_credit_risk.debt_solver import (
    simulate_period_vectorized,
)


@dataclass(frozen=True)
class TrancheResult:
    debt_long_t: np.ndarray
    debt_short_t: np.ndarray
    cash_t: np.ndarray
    interest_long_t: np.ndarray
    interest_short_t: np.ndarray
    ocf_t: np.ndarray


def simulate_period_two_tranches(
    *,
    debt_long_prev: np.ndarray,
    debt_short_prev: np.ndarray,
    cash_prev: np.ndarray,
    nopat: np.ndarray,
    delta_nfa: np.ndarray,
    delta_nwc: np.ndarray,
    nfa: np.ndarray,
    nwc: np.ndarray,
    capital_increase: np.ndarray | float,
    cost_of_debt_long: float,
    cost_of_debt_short: float,
    tax_rate: float | np.ndarray,
) -> TrancheResult:
    """Single-period update with long-term / short-term debt split.

    Reuses :func:`simulate_period_vectorized` twice — once for the long
    tranche against NFA investments and once for the short tranche
    against NWC investments. Cash is updated from the long-tranche
    solver (short-term solver cannot clamp into cash independently
    without double-counting).
    """
    nic = nfa + nwc
    # Allocate NOPAT proportionally to the invested capital
    with np.errstate(divide="ignore", invalid="ignore"):
        weight_long = np.where(nic > 0, nfa / nic, 0.5)
        weight_short = 1.0 - weight_long
    nopat_long = nopat * weight_long
    nopat_short = nopat * weight_short

    # Long tranche finances Capex (ΔNFA)
    d_long, cash_after_long, int_long, ocf_long = simulate_period_vectorized(
        debt_prev=debt_long_prev,
        cash_prev=cash_prev,
        nopat=nopat_long,
        delta_nic=delta_nfa,
        capital_increase=capital_increase,
        cost_of_debt=cost_of_debt_long,
        tax_rate=tax_rate,
    )

    # Short tranche finances NWC; cash excess stays with the long solver
    d_short, _cash_after_short, int_short, ocf_short = simulate_period_vectorized(
        debt_prev=debt_short_prev,
        cash_prev=np.zeros_like(cash_prev),  # do not double-credit excess
        nopat=nopat_short,
        delta_nic=delta_nwc,
        capital_increase=0.0,
        cost_of_debt=cost_of_debt_short,
        tax_rate=tax_rate,
    )

    ocf_total = ocf_long + ocf_short
    return TrancheResult(
        debt_long_t=d_long,
        debt_short_t=d_short,
        cash_t=cash_after_long,
        interest_long_t=int_long,
        interest_short_t=int_short,
        ocf_t=ocf_total,
    )
