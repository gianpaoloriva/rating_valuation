"""Tests for rating_valuation.common.financial."""

from __future__ import annotations

import pytest

from rating_valuation.common.financial import (
    WACCInputs,
    discount_factor,
    implied_growth,
    nopat_from_ebit,
    perpetuity,
    present_value,
    reinvestment_rate,
    relever_beta,
    roic,
    terminal_value_gordon,
    wacc_after_tax,
    wacc_pre_tax,
)


def test_relever_beta_hamada():
    # beta_L = beta_U * (1 + (1-t)*D/E)
    assert relever_beta(1.0, 1.0, 0.3) == pytest.approx(1.7)
    assert relever_beta(0.8, 0.5, 0.28) == pytest.approx(0.8 * (1 + 0.72 * 0.5))


def test_wacc_after_tax_sanity():
    w = wacc_after_tax(
        WACCInputs(
            risk_free_rate=0.04,
            market_risk_premium=0.05,
            beta_unlevered=1.0,
            target_debt_to_equity=0.5,
            cost_of_debt_pretax=0.045,
            tax_rate=0.28,
        )
    )
    # should be a positive rate, smaller than pre-tax counterpart
    assert 0.03 < w < 0.15
    w_pre = wacc_pre_tax(
        WACCInputs(
            risk_free_rate=0.04,
            market_risk_premium=0.05,
            beta_unlevered=1.0,
            target_debt_to_equity=0.5,
            cost_of_debt_pretax=0.045,
            tax_rate=0.28,
        )
    )
    assert w_pre > w  # tax shield NOT applied → higher


def test_discount_factor_and_pv():
    assert discount_factor(0.10, 1) == pytest.approx(1 / 1.10)
    assert discount_factor(0.10, 2) == pytest.approx(1 / 1.21)
    # PV of [100, 100, 100] @10% ≈ 248.685
    assert present_value([100, 100, 100], 0.10) == pytest.approx(248.6852, rel=1e-4)


def test_perpetuity_rejects_g_geq_r():
    with pytest.raises(ValueError):
        perpetuity(100, 0.05, 0.06)


def test_perpetuity_gordon_growth():
    # PV = 100 / (0.10 - 0.03) = 1428.571
    assert perpetuity(100, 0.10, 0.03) == pytest.approx(1428.5714, rel=1e-4)


def test_terminal_value_gordon_formula():
    # TV = FCFF_T * (1+g) / (wacc - g)
    tv = terminal_value_gordon(fcff_last=100, wacc=0.10, growth=0.03)
    assert tv == pytest.approx(100 * 1.03 / (0.10 - 0.03), rel=1e-6)


def test_nopat_and_roic():
    assert nopat_from_ebit(100, 0.28) == pytest.approx(72.0)
    assert roic(nopat=72, net_invested_capital=600) == pytest.approx(0.12)


def test_reinvestment_identity_roundtrip():
    # g = ROIC * h  <=>  h = g / ROIC
    g, r = 0.03, 0.15
    h = reinvestment_rate(g, r)
    assert h == pytest.approx(0.20)
    assert implied_growth(r, h) == pytest.approx(g)


def test_reinvestment_rate_rejects_h_above_one():
    """P1.4: h > 1 means more than 100% of NOPAT is reinvested — insostenibile."""
    with pytest.raises(ValueError, match=r"out of \[0, 1\]"):
        reinvestment_rate(growth=0.03, roic_new_investments=0.02)


def test_reinvestment_rate_accepts_boundaries():
    # h == 1 exactly (g == ROIC) → no growth value creation
    assert reinvestment_rate(0.10, 0.10) == pytest.approx(1.0)
    # h == 0 exactly (g == 0)
    assert reinvestment_rate(0.0, 0.15) == pytest.approx(0.0)


def test_discount_factor_rejects_non_integer_t():
    """P2.9: mid-year discounting is not supported; t must be int."""
    with pytest.raises(ValueError, match="non-negative integer"):
        discount_factor(0.08, 0.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative integer"):
        discount_factor(0.08, -1)
    # Booleans are technically int in Python but must be rejected
    with pytest.raises(ValueError, match="non-negative integer"):
        discount_factor(0.08, True)  # type: ignore[arg-type]
