"""Tests for rating_valuation.rapd.simulator — end-to-end integration."""

from __future__ import annotations

import pytest

from rating_valuation.common.data_loader import load_all, target_row
from rating_valuation.rapd.simulator import RAPDResult, RAPDSimulator


@pytest.fixture(scope="module")
def bundle():
    return load_all()


def test_simulator_builds_from_company(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = RAPDSimulator.from_company(
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
    sim = RAPDSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=2000, n_years=3,
    )
    result = sim.run(seed=42)
    assert isinstance(result, RAPDResult)
    # PD should be a valid probability at each period
    assert 0 <= result.metrics.cumulative_pd[-1] <= 1
    # Cumulative PD monotonic non-decreasing
    cpd = result.metrics.cumulative_pd
    assert all(cpd[i] <= cpd[i + 1] for i in range(len(cpd) - 1))


def test_simulator_healthy_target_has_low_pd(bundle):
    """Riva Meccanica is engineered to be above-sector in margin and low-leverage,
    so its cumulative 3y PD should be well below 20%."""
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = RAPDSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=5000, n_years=3,
    )
    result = sim.run(seed=42)
    assert result.metrics.cumulative_pd[-1] < 0.20


def test_simulator_assigns_implied_rating(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = RAPDSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=2000, n_years=3,
    )
    result = sim.run(seed=42)
    assert result.implied_rating is not None
    assert result.implied_rating in {
        "AAA", "AA+", "AA", "AA-",
        "A+", "A", "A-",
        "BBB+", "BBB", "BBB-",
        "BB+", "BB", "BB-",
        "B+", "B", "B-",
        "CCC+", "CCC", "CCC-",
        "CC", "C", "D",
    }


def test_simulator_diagnostic_matrices_shape(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = RAPDSimulator.from_company(
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
    sim = RAPDSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=1000, n_years=3,
    )
    r1 = sim.run(seed=123)
    r2 = sim.run(seed=123)
    assert r1.metrics.cumulative_pd[-1] == r2.metrics.cumulative_pd[-1]


def test_simulator_as_dataframe(bundle):
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    sim = RAPDSimulator.from_company(
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
    sim = RAPDSimulator.from_company(
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
        RAPDSimulator.from_company(
            target, bundle.sectors, bundle.macro,
            n_trials=100, n_years=2,
        )
