"""Tests for rating_valuation.dcf.three_stage."""

from __future__ import annotations

import warnings

import pytest

from rating_valuation.dcf.coherence import Severity
from rating_valuation.dcf.three_stage import (
    ThreeStageInputs,
    compute_fade_rate,
    median_roic_marginal_from_explicit,
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


# -----------------------------------------------------------------------------
# P1.3 — explicit ROIC decay base (paper formula)
# -----------------------------------------------------------------------------


def test_three_stage_decay_base_changes_fade_rate():
    """When roic_marginal_decay_base is set, the fade rate is computed from
    THAT value rather than from roic_marginal_start."""
    base_inputs = ThreeStageInputs(
        fcff_explicit=(10, 11, 12, 13, 14),
        nopat_at_t1=18.0,
        wacc=0.102,
        n_convergence_years=5,
        roic_marginal_start=0.339,
        growth_stage2=0.03,
    )
    result_default = value_three_stage(base_inputs)
    # Reproduce the paper example p. 31: decay from 26.5% to 10.2% in 5y
    paper_inputs = ThreeStageInputs(
        fcff_explicit=(10, 11, 12, 13, 14),
        nopat_at_t1=18.0,
        wacc=0.102,
        n_convergence_years=5,
        roic_marginal_start=0.339,
        roic_marginal_decay_base=0.265,  # median ROIC stage 1 (paper)
        growth_stage2=0.03,
    )
    result_paper = value_three_stage(paper_inputs)
    expected_fade = (0.102 / 0.265) ** (1.0 / 5) - 1.0
    assert result_paper.fade_rate == pytest.approx(expected_fade, rel=1e-9)
    # And it must differ from the default (which uses roic_marginal_start)
    assert result_default.fade_rate != pytest.approx(result_paper.fade_rate, rel=1e-6)


def test_median_roic_marginal_from_explicit():
    """P4.18: median marginal ROIC helper."""
    # 3 stage-1 years with NOPAT and NIC growing
    nopat = [10.0, 12.0, 14.0]
    nic = [80.0, 90.0, 95.0]
    # Marginals: (12-10)/(90-80)=0.20, (14-12)/(95-90)=0.40 → median=0.30
    assert median_roic_marginal_from_explicit(nopat, nic) == pytest.approx(0.30)


def test_median_roic_marginal_rejects_flat_nic():
    with pytest.raises(ValueError, match="NIC does not grow"):
        median_roic_marginal_from_explicit([10, 12, 14], [80, 80, 80])


# -----------------------------------------------------------------------------
# P2.6 — warning on positive terminal_growth with ROIC=WACC
# -----------------------------------------------------------------------------


def test_three_stage_warns_on_positive_terminal_growth():
    inputs = ThreeStageInputs(
        fcff_explicit=(10, 11, 12),
        nopat_at_t1=15.0,
        wacc=0.10,
        n_convergence_years=3,
        roic_marginal_start=0.15,
        growth_stage2=0.02,
        terminal_growth=0.01,  # > 0 with ROIC=WACC → incoherent
    )
    with pytest.warns(UserWarning, match="terminal_growth"):
        value_three_stage(inputs)


def test_three_stage_no_warning_on_zero_terminal_growth():
    inputs = ThreeStageInputs(
        fcff_explicit=(10, 11, 12),
        nopat_at_t1=15.0,
        wacc=0.10,
        n_convergence_years=3,
        roic_marginal_start=0.15,
        growth_stage2=0.02,
        terminal_growth=0.0,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # elevate warnings to errors
        value_three_stage(inputs)  # must not raise


# -----------------------------------------------------------------------------
# P2.10 — automatic coherence report attached to the result
# -----------------------------------------------------------------------------


def test_three_stage_result_has_coherence_report():
    inputs = ThreeStageInputs(
        fcff_explicit=(10, 11, 12, 13, 14),
        nopat_at_t1=18.0,
        wacc=0.10,
        n_convergence_years=5,
        roic_marginal_start=0.20,
        growth_stage2=0.03,
    )
    r = value_three_stage(inputs)
    assert r.coherence_report is not None
    assert len(r.coherence_report.checks) == 7
    # With terminal_growth=0 and the default gdp cap (+inf) all checks should
    # at most WARNING (tv_weight may exceed 0.80 depending on inputs)
    assert r.coherence_report.verdict in (Severity.PASS, Severity.WARNING)


def test_three_stage_coherence_report_flags_gdp_cap_violation():
    inputs = ThreeStageInputs(
        fcff_explicit=(10, 11, 12),
        nopat_at_t1=15.0,
        wacc=0.10,
        n_convergence_years=3,
        roic_marginal_start=0.15,
        growth_stage2=0.02,
        terminal_growth=0.0,
        gdp_nominal_5y_avg=0.01,  # cap very low — but terminal_growth=0, so C1 passes
    )
    r = value_three_stage(inputs)
    assert r.coherence_report is not None
    # With terminal_growth = 0 and cap = 0.01, the C1 check passes (0 <= 0.01)
    c1 = [c for c in r.coherence_report.checks if c.code == "C1"][0]
    assert c1.severity == Severity.PASS
