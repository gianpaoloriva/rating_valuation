"""Tests for rating_valuation.dcf.coherence."""

from __future__ import annotations

import pandas as pd

from rating_valuation.dcf.coherence import (
    CoherenceCheck,
    Severity,
    check_bounds,
    check_coherence,
    check_g_below_gdp,
    check_g_below_gdp_from_macro,
    check_reinvestment_bounds,
    check_reinvestment_identity,
    check_roic_convergence,
    check_tv_formula_used,
    check_tv_weight,
)


# -----------------------------------------------------------------------------
# Individual checks
# -----------------------------------------------------------------------------


def test_g_below_gdp_pass():
    c = check_g_below_gdp(growth=0.025, gdp_nominal_5y_avg=0.035)
    assert c.severity == Severity.PASS


def test_g_below_gdp_error():
    c = check_g_below_gdp(growth=0.05, gdp_nominal_5y_avg=0.035)
    assert c.severity == Severity.ERROR
    assert "PIL" in c.message


def test_reinvestment_identity_pass():
    # g = ROIC * h → 0.03 = 0.15 * 0.20
    c = check_reinvestment_identity(growth=0.03, roic_new_investments=0.15, implied_reinvestment=0.20)
    assert c.severity == Severity.PASS


def test_reinvestment_identity_error():
    c = check_reinvestment_identity(growth=0.03, roic_new_investments=0.15, implied_reinvestment=0.40)
    assert c.severity == Severity.ERROR
    assert "incoerente" in c.message.lower()


def test_reinvestment_identity_invalid_roic():
    c = check_reinvestment_identity(growth=0.03, roic_new_investments=0.0, implied_reinvestment=0.10)
    assert c.severity == Severity.ERROR


def test_tv_formula_coherent_accepted():
    c = check_tv_formula_used(used_coherent_formula=True, roic_new_investments=0.15, wacc=0.10)
    assert c.severity == Severity.PASS


def test_tv_formula_naive_flagged():
    c = check_tv_formula_used(used_coherent_formula=False, roic_new_investments=0.15, wacc=0.10)
    assert c.severity == Severity.WARNING


def test_tv_formula_steady_state_shortcut_ok():
    # ROIC ≈ WACC → naive formula coincides with steady state
    c = check_tv_formula_used(used_coherent_formula=False, roic_new_investments=0.10, wacc=0.10)
    assert c.severity == Severity.PASS


def test_tv_weight_pass_and_warning():
    assert check_tv_weight(0.60).severity == Severity.PASS
    assert check_tv_weight(0.85).severity == Severity.WARNING


def test_roic_convergence_pass_and_warning():
    assert check_roic_convergence(roic_marginal_final=0.105, wacc=0.10).severity == Severity.PASS
    assert check_roic_convergence(roic_marginal_final=0.20, wacc=0.10).severity == Severity.WARNING


def test_bounds_pass():
    c = check_bounds(wacc=0.10, growth=0.02, nopat_t_plus_1=15.0, inflation=0.02)
    assert c.severity == Severity.PASS


def test_bounds_error_wacc_below_growth():
    c = check_bounds(wacc=0.02, growth=0.05, nopat_t_plus_1=10.0)
    assert c.severity == Severity.ERROR
    assert "WACC" in c.message


def test_bounds_error_negative_nopat():
    c = check_bounds(wacc=0.10, growth=0.02, nopat_t_plus_1=-5.0)
    assert c.severity == Severity.ERROR


# -----------------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------------


def test_full_report_all_pass():
    report = check_coherence(
        wacc=0.10,
        growth=0.025,
        roic_new_investments=0.10,  # equals WACC → shortcut lecito
        implied_reinvestment=0.025 / 0.10,  # 0.25
        tv_weight=0.60,
        roic_marginal_final=0.105,
        nopat_t_plus_1=20.0,
        gdp_nominal_5y_avg=0.035,
        used_coherent_formula=True,
        inflation=0.02,
    )
    assert report.verdict == Severity.PASS
    assert len(report.errors()) == 0
    assert len(report.warnings()) == 0
    assert len(report.checks) == 7  # now includes C7 reinvestment bounds


def test_full_report_with_errors():
    report = check_coherence(
        wacc=0.10,
        growth=0.07,  # exceeds GDP
        roic_new_investments=0.15,
        implied_reinvestment=0.80,  # wildly incoherent
        tv_weight=0.90,  # too high
        roic_marginal_final=0.20,  # not converged
        nopat_t_plus_1=15.0,
        gdp_nominal_5y_avg=0.035,
        used_coherent_formula=False,
        inflation=0.02,
    )
    assert report.verdict == Severity.ERROR
    assert len(report.errors()) >= 2
    assert len(report.warnings()) >= 1


def test_coherence_check_as_table_has_seven_rows():
    """After P1.4, check C7 (reinvestment bounds) is always part of the report."""
    report = check_coherence(
        wacc=0.10,
        growth=0.02,
        roic_new_investments=0.12,
        implied_reinvestment=0.02 / 0.12,
        tv_weight=0.5,
        roic_marginal_final=0.105,
        nopat_t_plus_1=10.0,
        gdp_nominal_5y_avg=0.03,
        used_coherent_formula=True,
    )
    table = report.as_table()
    assert len(table) == 7
    assert {row["code"] for row in table} == {
        "C1", "C2", "C3", "C4", "C5", "C6", "C7",
    }


# -----------------------------------------------------------------------------
# P1.4 — check_reinvestment_bounds (C7)
# -----------------------------------------------------------------------------


def test_reinvestment_bounds_pass():
    c = check_reinvestment_bounds(growth=0.03, roic_new_investments=0.15)
    assert c.severity == Severity.PASS
    assert c.code == "C7"


def test_reinvestment_bounds_error_h_above_one():
    c = check_reinvestment_bounds(growth=0.05, roic_new_investments=0.04)
    assert c.severity == Severity.ERROR
    assert "[0, 1]" in c.message


def test_reinvestment_bounds_error_roic_non_positive():
    c = check_reinvestment_bounds(growth=0.03, roic_new_investments=0.0)
    assert c.severity == Severity.ERROR


def test_reinvestment_bounds_boundary_values():
    # h = 1 exactly (g = ROIC_NI) → PASS (degenerate but algebraically OK)
    assert check_reinvestment_bounds(0.10, 0.10).severity == Severity.PASS
    # h = 0 exactly (g = 0)
    assert check_reinvestment_bounds(0.0, 0.15).severity == Severity.PASS


# -----------------------------------------------------------------------------
# P2.5 — check_g_below_gdp_from_macro (automatic lookup)
# -----------------------------------------------------------------------------


def test_check_g_below_gdp_from_macro_pass():
    macro = pd.DataFrame(
        [
            {"country": "IT", "year": 2024, "gdp_nominal_growth_5y_avg": 0.040},
        ]
    )
    c = check_g_below_gdp_from_macro(growth=0.02, country="IT", year=2024, macro_df=macro)
    assert c.severity == Severity.PASS


def test_check_g_below_gdp_from_macro_error_above_cap():
    macro = pd.DataFrame(
        [
            {"country": "IT", "year": 2024, "gdp_nominal_growth_5y_avg": 0.020},
        ]
    )
    c = check_g_below_gdp_from_macro(growth=0.05, country="IT", year=2024, macro_df=macro)
    assert c.severity == Severity.ERROR


def test_check_g_below_gdp_from_macro_missing_row():
    macro = pd.DataFrame(
        [
            {"country": "DE", "year": 2024, "gdp_nominal_growth_5y_avg": 0.020},
        ]
    )
    c = check_g_below_gdp_from_macro(growth=0.03, country="IT", year=2024, macro_df=macro)
    assert c.severity == Severity.ERROR
    assert "Nessun record" in c.message
