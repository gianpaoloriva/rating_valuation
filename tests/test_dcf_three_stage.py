"""Tests for rating_valuation.dcf.three_stage."""

from __future__ import annotations

import pytest

from rating_valuation.dcf.three_stage import (
    ThreeStageInputs,
    compute_fade_rate,
    value_three_stage,
)


def test_compute_fade_rate_geometric():
    # Start at 20%, converge to 10% in 5 years
    fade = compute_fade_rate(roic_start=0.20, wacc=0.10, n_years=5)
    # final = start * (1+fade)^n → 0.20 * (1+fade)^5 = 0.10
    assert (0.20 * (1 + fade) ** 5) == pytest.approx(0.10, rel=1e-9)
    assert fade < 0  # decay (ROIC is shrinking)


def test_compute_fade_rate_rejects_zero_years():
    with pytest.raises(ValueError):
        compute_fade_rate(roic_start=0.15, wacc=0.10, n_years=0)


def test_three_stage_convergence_produces_nontrivial_stages():
    inputs = ThreeStageInputs(
        fcff_explicit=(10.0, 11.0, 12.0, 13.0, 14.0),
        nopat_at_t1=18.0,
        wacc=0.10,
        n_convergence_years=5,
        roic_marginal_start=0.25,
        growth_stage2=0.04,
    )
    r = value_three_stage(inputs)
    assert r.explicit_pv > 0
    assert r.convergence_pv > 0
    assert r.terminal_value > 0
    assert r.enterprise_value == pytest.approx(
        r.explicit_pv + r.convergence_pv + r.terminal_value_pv
    )
    # 5 explicit + 5 convergence + 1 terminal = 11 flows
    assert len(r.flows) == 11

    # Final convergence year should have ROIC ≈ WACC
    last_conv = [f for f in r.flows if f.stage == "convergence"][-1]
    assert last_conv.roic_marginal == pytest.approx(inputs.wacc, rel=1e-6)


def test_three_stage_tv_formula_with_zero_terminal_growth():
    inputs = ThreeStageInputs(
        fcff_explicit=(10.0, 10.0, 10.0),
        nopat_at_t1=15.0,
        wacc=0.08,
        n_convergence_years=3,
        roic_marginal_start=0.15,
        growth_stage2=0.03,
        terminal_growth=0.0,
    )
    r = value_three_stage(inputs)
    # After stage 2, NOPAT has grown by (1+0.03)^3. TV = NOPAT / WACC.
    last_conv = [f for f in r.flows if f.stage == "convergence"][-1]
    expected_tv = last_conv.nopat / inputs.wacc
    assert r.terminal_value == pytest.approx(expected_tv, rel=1e-9)


def test_three_stage_rejects_roic_below_wacc():
    with pytest.raises(ValueError, match="ROIC_marginal_start"):
        value_three_stage(
            ThreeStageInputs(
                fcff_explicit=(10.0,),
                nopat_at_t1=12.0,
                wacc=0.12,
                n_convergence_years=3,
                roic_marginal_start=0.10,  # below WACC
                growth_stage2=0.02,
            )
        )


def test_three_stage_rejects_empty_explicit():
    with pytest.raises(ValueError, match="at least one year"):
        value_three_stage(
            ThreeStageInputs(
                fcff_explicit=(),
                nopat_at_t1=12.0,
                wacc=0.10,
                n_convergence_years=3,
                roic_marginal_start=0.15,
                growth_stage2=0.02,
            )
        )


def test_three_stage_tv_weight_is_bounded():
    inputs = ThreeStageInputs(
        fcff_explicit=(10, 11, 12, 13, 14),
        nopat_at_t1=18.0,
        wacc=0.09,
        n_convergence_years=5,
        roic_marginal_start=0.20,
        growth_stage2=0.03,
    )
    r = value_three_stage(inputs)
    assert 0 < r.tv_weight < 1


def test_three_stage_equity_bridge():
    inputs = ThreeStageInputs(
        fcff_explicit=(10, 11, 12),
        nopat_at_t1=15.0,
        wacc=0.10,
        n_convergence_years=3,
        roic_marginal_start=0.15,
        growth_stage2=0.02,
        net_debt_today=25.0,
        excess_cash_today=5.0,
    )
    r = value_three_stage(inputs)
    assert r.equity_value == pytest.approx(r.enterprise_value - 25.0 + 5.0)
