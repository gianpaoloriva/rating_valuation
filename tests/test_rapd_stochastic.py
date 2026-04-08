"""Tests for rating_valuation.rapd.stochastic."""

from __future__ import annotations

import numpy as np
import pytest

from rating_valuation.rapd.stochastic import (
    N_VARS,
    StochasticParameters,
    WeibullParams,
    build_covariance_matrix,
    sample_scenarios,
)


# -----------------------------------------------------------------------------
# Weibull calibration
# -----------------------------------------------------------------------------


def test_weibull_from_mean_min_matches_target_mean():
    p = WeibullParams.from_mean_min(mean=0.15, minimum=0.05, shape=3.5)
    assert p.mean == pytest.approx(0.15, rel=1e-9)
    assert p.loc == pytest.approx(0.05)
    assert p.scale > 0


def test_weibull_rejects_mean_below_min():
    with pytest.raises(ValueError):
        WeibullParams.from_mean_min(mean=0.05, minimum=0.10, shape=2.0)


def test_weibull_ppf_respects_bounds():
    p = WeibullParams.from_mean_min(mean=0.15, minimum=0.05, shape=3.5)
    q = np.array([0.01, 0.5, 0.99])
    x = p.ppf(q)
    # All draws must be >= location
    assert (x >= p.loc - 1e-10).all()


# -----------------------------------------------------------------------------
# Covariance matrix structure
# -----------------------------------------------------------------------------


@pytest.fixture
def params():
    w = WeibullParams.from_mean_min(mean=0.05, minimum=0.00, shape=2.0)
    w2 = WeibullParams.from_mean_min(mean=0.15, minimum=0.05, shape=3.5)
    w3 = WeibullParams.from_mean_min(mean=0.40, minimum=0.30, shape=3.5)
    w4 = WeibullParams.from_mean_min(mean=0.22, minimum=0.15, shape=3.0)
    return StochasticParameters(
        growth=w, ebitda_margin=w2, nfa_ratio=w3, nwc_ratio=w4,
        autocorr_growth=0.20, autocorr_margin=0.30,
        autocorr_nfa=0.50, autocorr_nwc=0.40,
        corr_growth_margin=0.40,    # sign-flipped vs -0.4 paper
        corr_nfa_margin=0.20,       # sign-flipped vs -0.2
        corr_growth_nfa=0.20,
        corr_growth_nwc=-0.30,
    )


def test_covariance_has_correct_size(params):
    for n_years in (1, 2, 3, 5):
        cov = build_covariance_matrix(params, n_years)
        assert cov.shape == (N_VARS * n_years, N_VARS * n_years)


def test_covariance_diagonal_is_one(params):
    cov = build_covariance_matrix(params, n_years=3)
    np.testing.assert_allclose(np.diag(cov), 1.0)


def test_covariance_same_year_block_symmetric(params):
    cov = build_covariance_matrix(params, n_years=2)
    block = cov[:N_VARS, :N_VARS]
    np.testing.assert_allclose(block, block.T)


def test_covariance_autocorrelation_between_years(params):
    cov = build_covariance_matrix(params, n_years=3)
    # g_1 × g_2 should equal autocorr_growth
    assert cov[0, N_VARS] == pytest.approx(params.autocorr_growth)
    # g_1 × g_3 should equal autocorr_growth^2
    assert cov[0, 2 * N_VARS] == pytest.approx(params.autocorr_growth ** 2)


def test_covariance_is_positive_definite(params):
    cov = build_covariance_matrix(params, n_years=3)
    # Should admit a Cholesky decomposition
    np.linalg.cholesky(cov)


# -----------------------------------------------------------------------------
# Scenario sampling
# -----------------------------------------------------------------------------


def test_sample_scenarios_shape(params):
    scenarios = sample_scenarios(params, n_trials=100, n_years=3, seed=42)
    assert scenarios.shape == (100, 3, N_VARS)


def test_sample_scenarios_all_above_minimum(params):
    scenarios = sample_scenarios(params, n_trials=1000, n_years=3, seed=42)
    # growth >= params.growth.loc (which is 0.00)
    assert (scenarios[:, :, 0] >= params.growth.loc - 1e-9).all()
    # margin >= params.ebitda_margin.loc (0.05)
    assert (scenarios[:, :, 1] >= params.ebitda_margin.loc - 1e-9).all()
    # nfa_ratio >= 0.30
    assert (scenarios[:, :, 2] >= params.nfa_ratio.loc - 1e-9).all()
    # nwc_ratio >= 0.15
    assert (scenarios[:, :, 3] >= params.nwc_ratio.loc - 1e-9).all()


def test_sample_scenarios_empirical_means_close_to_target(params):
    scenarios = sample_scenarios(params, n_trials=20_000, n_years=3, seed=42)
    # Collapse years and trials into one sample per variable
    growth_mean = scenarios[:, :, 0].mean()
    margin_mean = scenarios[:, :, 1].mean()
    nfa_mean = scenarios[:, :, 2].mean()
    nwc_mean = scenarios[:, :, 3].mean()

    assert growth_mean == pytest.approx(params.growth.mean, rel=0.05)
    assert margin_mean == pytest.approx(params.ebitda_margin.mean, rel=0.05)
    assert nfa_mean == pytest.approx(params.nfa_ratio.mean, rel=0.05)
    assert nwc_mean == pytest.approx(params.nwc_ratio.mean, rel=0.05)


def test_sample_scenarios_seed_reproducible(params):
    a = sample_scenarios(params, n_trials=500, n_years=3, seed=123)
    b = sample_scenarios(params, n_trials=500, n_years=3, seed=123)
    np.testing.assert_allclose(a, b)


def test_sample_scenarios_seed_differentiates(params):
    a = sample_scenarios(params, n_trials=500, n_years=3, seed=123)
    b = sample_scenarios(params, n_trials=500, n_years=3, seed=456)
    # Two different seeds must give different samples
    assert not np.allclose(a, b)
