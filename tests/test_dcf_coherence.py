"""Tests for rating_valuation.dcf.coherence."""

from __future__ import annotations

from rating_valuation.dcf.coherence import (
    CoherenceCheck,
    Severity,
    check_bounds,
    check_coherence,
    check_g_below_gdp,
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
    assert len(report.checks) == 6


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


def test_coherence_check_as_table_has_six_rows():
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
    assert len(table) == 6
    assert {row["code"] for row in table} == {"C1", "C2", "C3", "C4", "C5", "C6"}
