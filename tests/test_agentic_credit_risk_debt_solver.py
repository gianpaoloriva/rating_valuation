"""Tests for rating_valuation.agentic_credit_risk.debt_solver."""

from __future__ import annotations

import numpy as np
import pytest

from rating_valuation.agentic_credit_risk.debt_solver import (
    interest_expense,
    operating_cash_flow,
    simulate_period_scalar,
    simulate_period_vectorized,
    solve_debt_scalar,
    solve_debt_vectorized,
)


# -----------------------------------------------------------------------------
# Scalar solver
# -----------------------------------------------------------------------------


def test_solve_debt_basic_positive_cashflow():
    # Strong NOPAT, no new investments → debt should decrease
    d = solve_debt_scalar(
        debt_prev=100.0,
        nopat=50.0,
        delta_nic=0.0,
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    assert d < 100.0
    assert d >= 0.0


def test_solve_debt_floored_at_zero():
    # Massive NOPAT should drive debt below zero → floored to 0
    d = solve_debt_scalar(
        debt_prev=10.0,
        nopat=500.0,
        delta_nic=0.0,
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    assert d == 0.0


def test_solve_debt_grows_with_investment():
    # Heavy investment and low NOPAT → debt increases
    d_no_inv = solve_debt_scalar(
        debt_prev=100.0,
        nopat=10.0,
        delta_nic=0.0,
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    d_with_inv = solve_debt_scalar(
        debt_prev=100.0,
        nopat=10.0,
        delta_nic=30.0,  # new investment
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    assert d_with_inv > d_no_inv


def test_solve_debt_capital_increase_reduces_debt():
    d_no_cap = solve_debt_scalar(
        debt_prev=100.0,
        nopat=5.0,
        delta_nic=15.0,
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    d_with_cap = solve_debt_scalar(
        debt_prev=100.0,
        nopat=5.0,
        delta_nic=15.0,
        capital_increase=20.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    assert d_with_cap < d_no_cap


def test_solve_debt_rejects_bad_tax_rate():
    with pytest.raises(ValueError):
        solve_debt_scalar(
            debt_prev=100.0, nopat=10.0, delta_nic=0.0, capital_increase=0.0,
            cost_of_debt=0.05, tax_rate=1.5,
        )
    with pytest.raises(ValueError):
        solve_debt_scalar(
            debt_prev=100.0, nopat=10.0, delta_nic=0.0, capital_increase=0.0,
            cost_of_debt=-0.01, tax_rate=0.28,
        )


def test_solve_debt_paper_formula_equivalence():
    """
    Verify our rearranged formula matches paper equation [7]:
    D_t = max(0, 2*(NOPAT - ΔNIC + ΔCAP - 2*D_{t-1})/(r_d(1-τ) - 2) - D_{t-1})
    """
    inputs = dict(
        debt_prev=120.0,
        nopat=15.0,
        delta_nic=10.0,
        capital_increase=5.0,
        cost_of_debt=0.05,
        tax_rate=0.27,
    )
    our = solve_debt_scalar(**inputs)

    r = inputs["cost_of_debt"]
    t = inputs["tax_rate"]
    num = 2 * (inputs["nopat"] - inputs["delta_nic"] + inputs["capital_increase"] - 2 * inputs["debt_prev"])
    den = r * (1 - t) - 2
    paper = max(0.0, num / den - inputs["debt_prev"])

    assert our == pytest.approx(paper, rel=1e-9)


# -----------------------------------------------------------------------------
# Vectorized solver
# -----------------------------------------------------------------------------


def test_vectorized_matches_scalar():
    debt_prev = np.array([100.0, 200.0, 50.0])
    nopat = np.array([20.0, 30.0, 15.0])
    delta_nic = np.array([5.0, 10.0, 3.0])
    v = solve_debt_vectorized(
        debt_prev=debt_prev,
        nopat=nopat,
        delta_nic=delta_nic,
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    scalars = np.array([
        solve_debt_scalar(
            debt_prev=float(debt_prev[i]),
            nopat=float(nopat[i]),
            delta_nic=float(delta_nic[i]),
            capital_increase=0.0,
            cost_of_debt=0.045,
            tax_rate=0.28,
        )
        for i in range(3)
    ])
    np.testing.assert_allclose(v, scalars, rtol=1e-9)


# -----------------------------------------------------------------------------
# OCF / INT helpers
# -----------------------------------------------------------------------------


def test_interest_expense_average_formula():
    i = interest_expense(debt_prev=100.0, debt_now=120.0, cost_of_debt=0.05)
    assert i == pytest.approx(0.05 * (100 + 120) / 2)


def test_operating_cash_flow_identity():
    """OCF = NOPAT - ΔNIC + τ·INT"""
    nopat = 50.0
    delta_nic = 20.0
    interest = 5.0
    tax_rate = 0.28
    ocf = operating_cash_flow(nopat=nopat, delta_nic=delta_nic, interest=interest, tax_rate=tax_rate)
    assert ocf == pytest.approx(nopat - delta_nic + tax_rate * interest)


# -----------------------------------------------------------------------------
# simulate_period (dynamic cash, eq. [6])
# -----------------------------------------------------------------------------


def test_simulate_period_with_debt_keeps_cash_constant():
    """When unclamped debt is positive, cash should remain at the previous level."""
    d, c, i, o = simulate_period_scalar(
        debt_prev=100.0,
        cash_prev=5.0,
        nopat=15.0,
        delta_nic=10.0,  # forces debt to increase or stay positive
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    assert d > 0  # debt still positive
    assert c == pytest.approx(5.0)  # cash unchanged
    assert i > 0
    assert o == pytest.approx(15.0 - 10.0 + 0.28 * i)


def test_simulate_period_clamped_debt_generates_cash():
    """When unclamped debt would go negative, it is floored at 0 and the
    excess is credited to cash."""
    d, c, i, o = simulate_period_scalar(
        debt_prev=10.0,
        cash_prev=5.0,
        nopat=500.0,  # massive NOPAT wipes out debt
        delta_nic=0.0,
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    assert d == 0.0
    assert c > 5.0  # cash has grown
    # Interest is only on the previous debt / 2
    assert i == pytest.approx(0.045 * 10.0 / 2.0)


def test_simulate_period_vectorized_matches_scalar():
    debt_prev = np.array([100.0, 10.0, 50.0])
    cash_prev = np.array([5.0, 3.0, 0.0])
    nopat = np.array([15.0, 500.0, 12.0])
    delta_nic = np.array([10.0, 0.0, 4.0])

    d_v, c_v, i_v, o_v = simulate_period_vectorized(
        debt_prev=debt_prev,
        cash_prev=cash_prev,
        nopat=nopat,
        delta_nic=delta_nic,
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )

    for idx in range(3):
        d_s, c_s, i_s, o_s = simulate_period_scalar(
            debt_prev=float(debt_prev[idx]),
            cash_prev=float(cash_prev[idx]),
            nopat=float(nopat[idx]),
            delta_nic=float(delta_nic[idx]),
            capital_increase=0.0,
            cost_of_debt=0.045,
            tax_rate=0.28,
        )
        assert d_v[idx] == pytest.approx(d_s)
        assert c_v[idx] == pytest.approx(c_s)
        assert i_v[idx] == pytest.approx(i_s)
        assert o_v[idx] == pytest.approx(o_s)


def test_simulate_period_cash_monotonic():
    """Cash is never allowed to decrease in this simplified model."""
    d, c, i, o = simulate_period_scalar(
        debt_prev=50.0,
        cash_prev=20.0,
        nopat=10.0,
        delta_nic=20.0,  # aggressive investment
        capital_increase=0.0,
        cost_of_debt=0.045,
        tax_rate=0.28,
    )
    assert c >= 20.0
