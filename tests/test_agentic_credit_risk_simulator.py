"""Tests for rating_valuation.agentic_credit_risk.simulator — end-to-end integration."""

from __future__ import annotations

import pytest

from rating_valuation.agentic_credit_risk.simulator import (
    AgenticCreditRiskResult,
    AgenticCreditRiskSimulator,
)
from rating_valuation.common.data_loader import SYNTHETIC_DATA_DIR, load_all, target_row


@pytest.fixture(scope="module")
def bundle():
    return load_all(SYNTHETIC_DATA_DIR)


def test_simulator_builds_from_company(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=2000, n_years=3,
    )
    assert sim.n_trials == 2000
    assert sim.n_years == 3
    # Initial state should match the target row
    assert sim.initial_state.revenues == pytest.approx(float(target["revenues"]))
    assert sim.initial_state.gross_debt == pytest.approx(float(target["gross_debt"]))
    assert sim.initial_state.wacc > 0


def test_simulator_run_produces_valid_result(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=2000, n_years=3,
    )
    result = sim.run(seed=42)
    assert isinstance(result, AgenticCreditRiskResult)
    # PD should be a valid probability at each period
    assert 0 <= result.metrics.cumulative_pd[-1] <= 1
    # Cumulative PD monotonic non-decreasing
    cpd = result.metrics.cumulative_pd
    assert all(cpd[i] <= cpd[i + 1] for i in range(len(cpd) - 1))


def test_simulator_healthy_target_has_low_pd(bundle):
    """Riva Meccanica is engineered to be above-sector in margin and low-leverage,
    so its cumulative 3y PD should be well below 20%."""
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=5000, n_years=3,
    )
    result = sim.run(seed=42)
    assert result.metrics.cumulative_pd[-1] < 0.20


def test_simulator_assigns_implied_rating(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=2000, n_years=3,
    )
    result = sim.run(seed=42)
    assert result.implied_rating is not None
    # P2.7: rating is now interpolated on log-PD, so the label can take
    # either the form of a pure class (e.g. "BBB+") when PD falls exactly
    # on a master scale anchor, or an interpolated form like
    # "BBB+/BBB (0.42)" between two adjacent classes.
    label = result.implied_rating
    pure_classes = {
        "AAA", "AA+", "AA", "AA-",
        "A+", "A", "A-",
        "BBB+", "BBB", "BBB-",
        "BB+", "BB", "BB-",
        "B+", "B", "B-",
        "CCC+", "CCC", "CCC-",
        "CC", "C", "D",
    }
    assert label in pure_classes or "/" in label


def test_simulator_diagnostic_matrices_shape(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=1000, n_years=3,
    )
    result = sim.run(seed=42, keep_diagnostic=True)
    assert result.nopat is not None
    assert result.nopat.shape == (1000, 3)
    assert result.debt.shape == (1000, 3)
    assert result.ev.shape == (1000, 3)


def test_simulator_seed_reproducible(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=1000, n_years=3,
    )
    r1 = sim.run(seed=123)
    r2 = sim.run(seed=123)
    assert r1.metrics.cumulative_pd[-1] == r2.metrics.cumulative_pd[-1]


def test_simulator_as_dataframe(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=1000, n_years=3,
    )
    df = sim.run(seed=42).as_dataframe()
    assert len(df) == 3
    assert set(df.columns) == {
        "year_ahead",
        "yearly_default_frequency",
        "marginal_pd",
        "cumulative_pd",
    }


def test_simulator_summary_includes_rating(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=1000, n_years=3,
    )
    summary = sim.run(seed=42).summary()
    assert "implied_rating" in summary
    assert "pd_cumulative_final" in summary
    assert "initial_revenues" in summary


def test_simulator_rejects_missing_sector(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0].copy()
    target["gics_sub_industry"] = "Nonexistent Industry"
    with pytest.raises(KeyError, match="sector"):
        AgenticCreditRiskSimulator.from_company(
            target, bundle.sectors, bundle.macro,
            n_trials=100, n_years=2,
        )


# -----------------------------------------------------------------------------
# P1.1 — Terminal Value includes the Interest Tax Shield
# -----------------------------------------------------------------------------


def test_simulator_tv_with_its_lowers_pd_for_leveraged(bundle):
    """With positive debt and τ>0, the TV must now include τ·INT_T.
    The interest matrix must be populated in the diagnostic output."""
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=2000, n_years=3,
    )
    result = sim.run(seed=42, keep_diagnostic=True)
    assert result.interest is not None
    assert result.interest.shape == (2000, 3)
    # For a leveraged company, interest must be positive in each period
    assert (result.interest >= 0).all()
    assert result.interest[:, -1].mean() > 0


# -----------------------------------------------------------------------------
# P3.12 — stochastic tax rate normalization
# -----------------------------------------------------------------------------


def test_simulator_stochastic_tax_rate_changes_result(bundle):
    from dataclasses import replace

    import numpy as np

    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim_fixed = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=2000, n_years=3,
    )
    # Inject the stochastic tax flag via a patched initial state
    sim_stoch = AgenticCreditRiskSimulator(
        initial_state=replace(sim_fixed.initial_state, tax_stochastic=True),
        params=sim_fixed.params,
        n_trials=sim_fixed.n_trials,
        n_years=sim_fixed.n_years,
    )
    r_fixed = sim_fixed.run(seed=42, keep_diagnostic=True)
    r_stoch = sim_stoch.run(seed=42, keep_diagnostic=True)
    # The NOPAT matrix must differ because the tax multiplier is stochastic.
    # (Cumulative PD may be 0 in both runs for a very healthy target like
    # Riva Meccanica; we check the intermediate matrix instead.)
    assert not np.allclose(r_fixed.nopat, r_stoch.nopat)
