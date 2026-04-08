"""Tests for rating_valuation.rapd.credit_metrics."""

from __future__ import annotations

import numpy as np
import pytest

from rating_valuation.rapd.credit_metrics import compute_metrics


def test_no_defaults_returns_zero_metrics():
    # EV always above debt → no defaults
    ev = np.array([[100.0, 110.0, 120.0]] * 1000)
    debt = np.full_like(ev, 50.0)
    cash = np.zeros_like(ev)
    m = compute_metrics(ev=ev, debt=debt, cash=cash)
    assert m.cumulative_pd[-1] == 0.0
    assert m.n_default_scenarios == 0
    assert m.lgd_mean == 0.0
    assert m.expected_loss == 0.0


def test_all_defaults_pd_one():
    # EV always below debt → every trial defaults in year 0
    ev = np.full((500, 3), 10.0)
    debt = np.full((500, 3), 100.0)
    cash = np.zeros_like(ev)
    m = compute_metrics(ev=ev, debt=debt, cash=cash)
    assert m.cumulative_pd[0] == pytest.approx(1.0)
    assert m.cumulative_pd[-1] == pytest.approx(1.0)
    assert m.yearly_marginal_default[0] == pytest.approx(1.0)
    # After period 0, everybody has already defaulted → marginal = 0
    assert m.yearly_marginal_default[1] == pytest.approx(0.0)
    assert m.yearly_marginal_default[2] == pytest.approx(0.0)


def test_cumulative_pd_monotonic_nondecreasing():
    rng = np.random.default_rng(42)
    n_trials, n_years = 2000, 3
    ev = rng.normal(50, 30, (n_trials, n_years))
    debt = rng.normal(60, 20, (n_trials, n_years))
    cash = np.zeros_like(ev)
    m = compute_metrics(ev=ev, debt=debt, cash=cash)
    for t in range(1, n_years):
        assert m.cumulative_pd[t] >= m.cumulative_pd[t - 1]


def test_lgd_mean_and_quantiles():
    # Manual scenario: 4 default scenarios with clear LGD values
    ev = np.array(
        [
            [10.0, 100.0, 100.0],  # trial 0 defaults at t=0 with LGD=90
            [100.0, 20.0, 100.0],  # trial 1 defaults at t=1 with LGD=80
            [100.0, 100.0, 30.0],  # trial 2 defaults at t=2 with LGD=70
            [50.0, 100.0, 100.0],  # trial 3 defaults at t=0 with LGD=50
            [100.0, 100.0, 100.0], # trial 4 survives
        ]
    )
    debt = np.full_like(ev, 100.0)
    cash = np.zeros_like(ev)
    m = compute_metrics(ev=ev, debt=debt, cash=cash)

    # 4 default trials out of 5
    assert m.n_default_scenarios == 4
    assert m.cumulative_pd[-1] == pytest.approx(0.8)
    # LGD values: 90, 80, 70, 50 → mean 72.5, median 75
    assert m.lgd_mean == pytest.approx(72.5)
    assert m.lgd_median == pytest.approx(75.0)
    # Max (q99) should be near 90
    assert m.lgd_quantiles[0.99] >= 80.0


def test_first_default_used_for_lgd():
    # Trial defaults at both t=0 and t=2; only t=0 LGD should be counted
    ev = np.array([[20.0, 100.0, 10.0]])
    debt = np.full_like(ev, 100.0)
    cash = np.zeros_like(ev)
    m = compute_metrics(ev=ev, debt=debt, cash=cash)
    # First default at t=0 with EV=20 → LGD = 100 - 20 = 80
    assert m.lgd_mean == pytest.approx(80.0)


def test_cash_offsets_default_condition():
    ev = np.full((100, 1), 50.0)
    debt = np.full((100, 1), 100.0)
    cash_low = np.full((100, 1), 10.0)   # threshold = 100 - 10 = 90, EV 50 < 90 → default
    cash_high = np.full((100, 1), 60.0)  # threshold = 100 - 60 = 40, EV 50 > 40 → safe

    m_low = compute_metrics(ev=ev, debt=debt, cash=cash_low)
    m_high = compute_metrics(ev=ev, debt=debt, cash=cash_high)

    assert m_low.cumulative_pd[-1] == 1.0
    assert m_high.cumulative_pd[-1] == 0.0


def test_input_shape_mismatch_raises():
    ev = np.zeros((10, 3))
    debt = np.zeros((10, 2))
    cash = np.zeros((10, 3))
    with pytest.raises(ValueError, match="same shape"):
        compute_metrics(ev=ev, debt=debt, cash=cash)


def test_summary_keys_present():
    ev = np.array([[10.0, 100.0]] * 10)
    debt = np.full_like(ev, 100.0)
    cash = np.zeros_like(ev)
    m = compute_metrics(ev=ev, debt=debt, cash=cash)
    summary = m.summary()
    expected_keys = {
        "trials", "horizon_years", "pd_cumulative_final",
        "yearly_default_frequency", "marginal_pd", "cumulative_pd",
        "lgd_mean", "lgd_median", "lgd_std",
        "expected_loss", "unexpected_loss_95", "unexpected_loss_99",
        "default_scenarios",
    }
    assert expected_keys.issubset(summary.keys())
