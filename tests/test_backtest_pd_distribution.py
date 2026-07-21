"""Tests for the sample-wide PD distribution (backtest sanity-check chart)."""

import numpy as np
import pytest

from rating_valuation.backtest import PDDistribution, pd_distribution


def test_unimodal_bell_detected():
    rng = np.random.default_rng(42)
    # Log-normal-ish cloud of PDs around 1% → single bell in log space
    pds = np.clip(10 ** rng.normal(-2.0, 0.4, size=200), 0.0, 1.0)
    dist = pd_distribution(pds)
    assert isinstance(dist, PDDistribution)
    assert dist.n_modes == 1
    assert not dist.is_bimodal
    assert dist.density.size == 300
    assert dist.log10_pd.size == 200


def test_bimodal_double_saddle_detected():
    rng = np.random.default_rng(42)
    # Two well-separated populations: healthy (~0.1%) and distressed (~20%)
    healthy = 10 ** rng.normal(-3.0, 0.25, size=150)
    distressed = 10 ** rng.normal(-0.7, 0.15, size=80)
    pds = np.clip(np.concatenate([healthy, distressed]), 0.0, 1.0)
    dist = pd_distribution(pds)
    assert dist.n_modes == 2
    assert dist.is_bimodal


def test_zero_pd_clipped_at_floor():
    pds = [0.0, 0.0, 0.01, 0.02, 0.05]
    dist = pd_distribution(pds, floor=1e-5)
    assert np.isclose(dist.log10_pd.min(), -5.0)
    assert dist.floor == 1e-5


def test_degenerate_samples_skip_kde():
    # Too few points
    tiny = pd_distribution([0.01, 0.02])
    assert tiny.density.size == 0
    assert tiny.n_modes == 0
    # Zero spread
    flat = pd_distribution([0.01] * 10)
    assert flat.density.size == 0
    assert flat.n_modes == 0


def test_nan_dropped_and_validation():
    dist = pd_distribution([0.01, float("nan"), 0.02, 0.03])
    assert dist.log10_pd.size == 3

    with pytest.raises(ValueError):
        pd_distribution([])
    with pytest.raises(ValueError):
        pd_distribution([float("nan")])
    with pytest.raises(ValueError):
        pd_distribution([0.01, 1.5])
    with pytest.raises(ValueError):
        pd_distribution([-0.1, 0.5])


def test_density_integrates_to_one():
    rng = np.random.default_rng(0)
    pds = np.clip(10 ** rng.normal(-2.0, 0.5, size=100), 0.0, 1.0)
    dist = pd_distribution(pds)
    integral = np.trapezoid(dist.density, dist.grid)
    assert 0.9 < integral < 1.1
