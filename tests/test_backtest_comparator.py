"""Tests for rating_valuation.backtest.comparator."""

from __future__ import annotations

import numpy as np
import pytest

from rating_valuation.backtest import (
    BacktestResult,
    BacktestRunner,
    auroc,
    gini_coefficient,
    kolmogorov_smirnov,
)
from rating_valuation.common.data_loader import load_all


# -----------------------------------------------------------------------------
# Metrics
# -----------------------------------------------------------------------------


def test_auroc_perfect_discrimination():
    scores = np.array([0.1, 0.2, 0.3, 0.8, 0.9, 1.0])
    labels = np.array([0, 0, 0, 1, 1, 1])
    assert auroc(scores, labels) == pytest.approx(1.0)


def test_auroc_all_ties_is_half():
    # Everyone has identical score → ties everywhere → AUROC = 0.5
    scores = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
    labels = np.array([0, 0, 0, 1, 1, 1])
    assert auroc(scores, labels) == pytest.approx(0.5)


def test_auroc_inverted_discrimination():
    # High scores for non-defaulters, low scores for defaulters → 0.0
    scores = np.array([0.9, 0.8, 0.7, 0.1, 0.2, 0.3])
    labels = np.array([0, 0, 0, 1, 1, 1])
    assert auroc(scores, labels) == pytest.approx(0.0)


def test_gini_from_auroc():
    scores = np.array([0.1, 0.2, 0.3, 0.8, 0.9, 1.0])
    labels = np.array([0, 0, 0, 1, 1, 1])
    assert gini_coefficient(scores, labels) == pytest.approx(1.0)


def test_kolmogorov_smirnov_perfect_separation():
    scores = np.array([0.1, 0.2, 0.3, 0.8, 0.9, 1.0])
    labels = np.array([0, 0, 0, 1, 1, 1])
    assert kolmogorov_smirnov(scores, labels) == pytest.approx(1.0)


def test_auroc_nan_when_single_class():
    scores = np.array([0.1, 0.2, 0.3])
    labels = np.array([0, 0, 0])
    assert np.isnan(auroc(scores, labels))
    assert np.isnan(gini_coefficient(scores, labels))


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bundle():
    return load_all()


def test_runner_produces_results_for_every_row(bundle):
    # Score 3 companies × 1 year = 3 rows
    sample = bundle.companies[bundle.companies["fiscal_year"] == 2024].head(3).copy()
    runner = BacktestRunner(
        bundle.sectors,
        bundle.macro,
        rating_master_scale=bundle.rating_master_scale,
        n_trials=500,
        n_years=3,
    )
    result = runner.run(sample, seed=1)
    assert isinstance(result, BacktestResult)
    assert len(result.rows) == 3
    for row in result.rows:
        assert 0.0 <= row.acr_pd <= 1.0
        assert 0.0 <= row.altman_pd <= 1.0
        assert row.altman_rating != "N/A"


def test_runner_labels_defaulted(bundle):
    sample = bundle.companies[bundle.companies["fiscal_year"] == 2024].head(5).copy()
    defaulted = {"mec_alpha", "tecnomec"}
    runner = BacktestRunner(
        bundle.sectors,
        bundle.macro,
        rating_master_scale=bundle.rating_master_scale,
        n_trials=500,
        n_years=3,
    )
    result = runner.run(sample, defaulted_ids=defaulted, seed=1)
    df = result.as_dataframe()
    assert df[df["is_defaulted"] == 1]["company_id"].tolist() == sorted(defaulted)[:2] or \
           set(df[df["is_defaulted"] == 1]["company_id"]) <= defaulted


def test_runner_metrics_table_shape(bundle):
    sample = bundle.companies[bundle.companies["fiscal_year"] == 2024].head(5).copy()
    defaulted = {"mec_alpha"}
    runner = BacktestRunner(
        bundle.sectors,
        bundle.macro,
        rating_master_scale=bundle.rating_master_scale,
        n_trials=500,
        n_years=3,
    )
    result = runner.run(sample, defaulted_ids=defaulted, seed=1)
    metrics = result.metrics_table()
    assert set(metrics["model"]) == {"Agentic Credit Risk", "Altman Z''"}
    expected_cols = {
        "model", "auroc", "gini", "ks",
        "mean_pd_defaulted", "mean_pd_performing",
        "median_pd_defaulted", "median_pd_performing",
    }
    assert expected_cols.issubset(metrics.columns)


def test_runner_summary_string(bundle):
    sample = bundle.companies[bundle.companies["fiscal_year"] == 2024].head(3).copy()
    runner = BacktestRunner(
        bundle.sectors,
        bundle.macro,
        rating_master_scale=bundle.rating_master_scale,
        n_trials=500,
        n_years=3,
    )
    result = runner.run(sample, seed=1)
    s = result.summary()
    assert "3 companies" in s
    assert "500 trials" in s
