"""Tests for rating_valuation.dcf.two_stage."""

from __future__ import annotations

import pytest

from rating_valuation.dcf.two_stage import (
    TwoStageInputs,
    terminal_value_coherent,
    value_two_stage,
    value_two_stage_coherent,
)


def test_basic_two_stage_valuation():
    inputs = TwoStageInputs(
        fcff_explicit=(10, 11, 12, 13, 14),
        wacc=0.10,
        terminal_growth=0.02,
        net_debt_today=20.0,
    )
    r = value_two_stage(inputs)
    # Enterprise value positive and larger than explicit PV
    assert r.enterprise_value > r.explicit_pv
    # Equity value = EV - net debt
    assert r.equity_value == pytest.approx(r.enterprise_value - 20.0)
    # TV weight between 0 and 1
    assert 0.0 < r.tv_weight < 1.0


def test_two_stage_tv_formula():
    # TV = FCFF_T * (1+g) / (wacc - g)
    # FCFF_T=14, g=0.02, wacc=0.10 → TV = 14*1.02/0.08 = 178.5
    inputs = TwoStageInputs(
        fcff_explicit=(10, 11, 12, 13, 14),
        wacc=0.10,
        terminal_growth=0.02,
    )
    r = value_two_stage(inputs)
    assert r.terminal_value == pytest.approx(14 * 1.02 / 0.08, rel=1e-6)


def test_rejects_g_geq_wacc():
    with pytest.raises(ValueError, match="WACC"):
        value_two_stage(
            TwoStageInputs(
                fcff_explicit=(10,),
                wacc=0.05,
                terminal_growth=0.06,
            )
        )


def test_rejects_empty_explicit():
    with pytest.raises(ValueError, match="at least one year"):
        value_two_stage(TwoStageInputs(fcff_explicit=(), wacc=0.1, terminal_growth=0.02))


def test_terminal_value_coherent_roic_equals_wacc():
    # When ROIC == WACC, the reinvestment-adjusted TV collapses to NOPAT/wacc
    tv = terminal_value_coherent(
        nopat_t_plus_1=100, wacc=0.10, growth=0.03, roic_new_investments=0.10
    )
    # Expected: NOPAT * (1 - g/ROIC) / (wacc - g) = 100 * (1-0.3)/(0.07) = 1000
    # Equivalent to NOPAT/WACC = 100/0.10 = 1000
    assert tv == pytest.approx(1000.0, rel=1e-6)


def test_terminal_value_coherent_high_roic():
    # ROIC > WACC → TV larger than the ROIC=WACC case
    tv_equal = terminal_value_coherent(
        nopat_t_plus_1=100, wacc=0.10, growth=0.03, roic_new_investments=0.10
    )
    tv_high = terminal_value_coherent(
        nopat_t_plus_1=100, wacc=0.10, growth=0.03, roic_new_investments=0.20
    )
    assert tv_high > tv_equal


def test_value_two_stage_coherent_sample():
    r = value_two_stage_coherent(
        fcff_explicit=[10, 11, 12, 13, 14],
        nopat_t_plus_1=15.0,
        wacc=0.10,
        terminal_growth=0.02,
        roic_new_investments=0.12,
        net_debt_today=20.0,
    )
    assert r.enterprise_value > 0
    assert r.equity_value == pytest.approx(r.enterprise_value - 20.0)
    assert 0 < r.tv_weight < 1


def test_coherent_tv_rejects_invalid_roic():
    with pytest.raises(ValueError):
        terminal_value_coherent(nopat_t_plus_1=100, wacc=0.10, growth=0.03, roic_new_investments=0)


def test_coherent_tv_rejects_h_above_one():
    """P1.4: if g > ROIC_NI the implied h > 1 → meaningless TV."""
    with pytest.raises(ValueError, match=r"out of \[0, 1\]"):
        terminal_value_coherent(
            nopat_t_plus_1=100,
            wacc=0.10,
            growth=0.05,
            roic_new_investments=0.04,  # ROIC < g → h > 1
        )


def test_coherent_tv_accepts_h_exactly_one():
    """Boundary: h = 1 (g == ROIC_NI) is accepted (and FCFF normalized = 0)."""
    tv = terminal_value_coherent(
        nopat_t_plus_1=100, wacc=0.15, growth=0.10, roic_new_investments=0.10
    )
    # FCFF_normalized = 100 · (1 - 1) = 0 → TV = 0
    assert tv == pytest.approx(0.0)


def test_two_stage_equity_value_with_excess_cash():
    r = value_two_stage(
        TwoStageInputs(
            fcff_explicit=(10, 11, 12),
            wacc=0.10,
            terminal_growth=0.02,
            net_debt_today=30.0,
            excess_cash_today=5.0,
        )
    )
    assert r.equity_value == pytest.approx(r.enterprise_value - 30.0 + 5.0)
