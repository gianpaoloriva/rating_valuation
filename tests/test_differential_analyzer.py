"""Tests for rating_valuation.differential.analyzer."""

from __future__ import annotations

import pytest

from rating_valuation.bms.builder import BMSBuilder
from rating_valuation.common.data_loader import load_companies, peer_sample, target_row
from rating_valuation.differential.analyzer import (
    DEFAULT_INDICATORS,
    DifferentialAnalyzer,
    DifferentialReport,
    IndicatorComparison,
)


@pytest.fixture(scope="module")
def bms_2024():
    df = load_companies()
    peers = peer_sample(df, "Industrial Machinery", fiscal_year=2024)
    return BMSBuilder(peers, min_sample_size=10).build()


@pytest.fixture(scope="module")
def target_2024():
    df = load_companies()
    return target_row(df, fiscal_year=2024).iloc[0]


def test_analyze_returns_report(bms_2024, target_2024):
    analyzer = DifferentialAnalyzer(bms_2024)
    report = analyzer.analyze(target_2024)
    assert isinstance(report, DifferentialReport)
    assert report.target_name == "Riva Meccanica SpA"
    assert report.fiscal_year == 2024
    assert report.bms_fiscal_year == 2024
    assert len(report.comparisons) == len(DEFAULT_INDICATORS)


def test_all_indicators_computed(bms_2024, target_2024):
    analyzer = DifferentialAnalyzer(bms_2024)
    report = analyzer.analyze(target_2024)
    for comp in report.comparisons:
        assert isinstance(comp, IndicatorComparison)
        assert comp.target == comp.target  # not NaN
        assert comp.bms == comp.bms        # not NaN


def test_target_ebitda_margin_above_bms(bms_2024, target_2024):
    """Riva Meccanica is engineered to have 17% margin vs ~14% sector."""
    analyzer = DifferentialAnalyzer(bms_2024)
    report = analyzer.analyze(target_2024)
    margin = next(c for c in report.comparisons if c.key == "ebitda_margin")
    assert margin.target > margin.bms
    assert margin.delta > 0
    assert margin.favorable is True


def test_target_leverage_below_bms(bms_2024, target_2024):
    """Target has lower debt-to-assets than the average peer."""
    analyzer = DifferentialAnalyzer(bms_2024)
    report = analyzer.analyze(target_2024)
    lev = next(c for c in report.comparisons if c.key == "debt_to_ta")
    assert lev.target < lev.bms
    assert lev.delta < 0
    assert lev.favorable is True  # lower is better


def test_categories_cover_core_dimensions(bms_2024, target_2024):
    analyzer = DifferentialAnalyzer(bms_2024)
    report = analyzer.analyze(target_2024)
    buckets = report.by_category()
    assert "margin" in buckets
    assert "capital_intensity" in buckets
    assert "leverage" in buckets
    assert "efficiency" in buckets


def test_roic_derived_indicator(bms_2024, target_2024):
    analyzer = DifferentialAnalyzer(bms_2024)
    report = analyzer.analyze(target_2024)
    roic = next(c for c in report.comparisons if c.key == "roic")
    # Both should be positive for a healthy sample
    assert roic.target > 0
    assert roic.bms > 0


def test_as_dataframe_has_all_rows(bms_2024, target_2024):
    analyzer = DifferentialAnalyzer(bms_2024)
    report = analyzer.analyze(target_2024)
    df = report.as_dataframe()
    assert len(df) == len(DEFAULT_INDICATORS)
    assert set(df.columns) == {
        "key", "label", "category", "unit",
        "target", "bms", "delta", "delta_pct", "favorable",
    }


def test_summary_line(bms_2024, target_2024):
    analyzer = DifferentialAnalyzer(bms_2024)
    report = analyzer.analyze(target_2024)
    summary = report.summary_line()
    assert "Riva Meccanica" in summary
    assert "2024" in summary


def test_favorable_majority_for_better_target(bms_2024, target_2024):
    """The engineered target is better than average on most dimensions."""
    analyzer = DifferentialAnalyzer(bms_2024)
    report = analyzer.analyze(target_2024)
    assert report.favorable_count() > report.unfavorable_count()
