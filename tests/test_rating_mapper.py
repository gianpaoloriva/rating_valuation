"""Tests for rating_valuation.rating.mapper."""

from __future__ import annotations

from math import exp

import pytest

from rating_valuation.rating import (
    DEFAULT_LGD,
    RatingLookup,
    altman_z_double_prime_non_manufacturing,
    altman_z_score_manufacturing,
)


# -----------------------------------------------------------------------------
# Master scale loading
# -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def lookup() -> RatingLookup:
    return RatingLookup.from_csv()


def test_master_scale_has_22_classes(lookup: RatingLookup):
    assert len(lookup.rating_to_pd) == 22
    assert "AAA" in lookup.rating_to_pd
    assert "D" in lookup.rating_to_pd


def test_pd_bounds(lookup: RatingLookup):
    assert lookup.pd_of("AAA") == pytest.approx(0.0)
    assert lookup.pd_of("D") == pytest.approx(1.0)
    assert 0.001 < lookup.pd_of("BBB") < 0.01
    assert 0.05 < lookup.pd_of("B") < 0.10


def test_pd_monotone_in_rating(lookup: RatingLookup):
    prev = -1.0
    for ordinal in sorted(lookup.ordinal_to_rating):
        rating = lookup.ordinal_to_rating[ordinal]
        pd = lookup.pd_of(rating)
        assert pd >= prev, f"Non-monotonic at {rating}: {prev} -> {pd}"
        prev = pd


# -----------------------------------------------------------------------------
# PD -> Rating lookup
# -----------------------------------------------------------------------------


def test_rating_of_pd_exact_match(lookup: RatingLookup):
    # PD(BBB) = 0.00230 should map exactly to BBB
    assert lookup.rating_of_pd(0.00230) == "BBB"


def test_rating_of_pd_rounds_up(lookup: RatingLookup):
    # 0.005 is between BBB (0.0023) and BBB- (0.0038) → should return BBB-
    # (smallest class with PD >= input is BB+ at 0.0055)
    assert lookup.rating_of_pd(0.005) == "BB+"


def test_rating_of_pd_clipping(lookup: RatingLookup):
    assert lookup.rating_of_pd(-0.1) == "AAA"
    assert lookup.rating_of_pd(0.0) == "AAA"
    assert lookup.rating_of_pd(1.0) == "D"
    assert lookup.rating_of_pd(5.0) == "D"


def test_rating_of_pd_interpolated(lookup: RatingLookup):
    # value bracketed between BBB (0.0023) and BBB- (0.0038)
    lo, hi, frac = lookup.rating_of_pd_interpolated(0.003)
    assert lo == "BBB"
    assert hi == "BBB-"
    assert 0.0 <= frac <= 1.0


# -----------------------------------------------------------------------------
# CDS -> PD
# -----------------------------------------------------------------------------


def test_pd_from_cds_formula():
    # Paper formula: PD = 1 - exp(-CDS/LGD)
    # CDS = 120 bps (0.012), LGD = 0.6 -> PD = 1 - exp(-0.02) ≈ 0.01980
    pd = RatingLookup.pd_from_cds(0.012)
    expected = 1.0 - exp(-0.012 / 0.60)
    assert pd == pytest.approx(expected)


def test_pd_from_cds_zero_spread():
    assert RatingLookup.pd_from_cds(0.0) == pytest.approx(0.0)


def test_pd_from_cds_validates_inputs():
    with pytest.raises(ValueError):
        RatingLookup.pd_from_cds(-0.01)
    with pytest.raises(ValueError):
        RatingLookup.pd_from_cds(0.01, lgd=0.0)
    with pytest.raises(ValueError):
        RatingLookup.pd_from_cds(0.01, lgd=1.5)
    with pytest.raises(ValueError):
        RatingLookup.pd_from_cds(0.01, maturity_years=0)


def test_rating_from_cds(lookup: RatingLookup):
    # tight spread (10 bps / 0.6 LGD ≈ 0.167% PD) → investment grade (<= BBB-)
    rating_tight = lookup.rating_from_cds(0.001)  # 10 bps
    assert lookup.rating_to_ordinal[rating_tight] <= lookup.rating_to_ordinal["BBB-"]
    # very wide spread → non-investment grade
    rating_wide = lookup.rating_from_cds(0.10)  # 1000 bps
    assert lookup.rating_to_ordinal[rating_wide] >= lookup.rating_to_ordinal["B"]


# -----------------------------------------------------------------------------
# Altman Z-score
# -----------------------------------------------------------------------------


def test_altman_z_manufacturing_healthy():
    z = altman_z_score_manufacturing(
        working_capital=30,
        retained_earnings=50,
        ebit=15,
        market_value_equity=120,
        sales=200,
        total_assets=150,
        total_liabilities=60,
    )
    # Healthy firm should score above the safe zone (Z > 2.99)
    assert z > 2.99


def test_altman_z_manufacturing_distress():
    z = altman_z_score_manufacturing(
        working_capital=-5,
        retained_earnings=-20,
        ebit=-10,
        market_value_equity=5,
        sales=30,
        total_assets=100,
        total_liabilities=90,
    )
    assert z < 1.81  # distress zone


def test_altman_z_double_prime_non_manufacturing():
    z = altman_z_double_prime_non_manufacturing(
        working_capital=30,
        retained_earnings=50,
        ebit=15,
        book_value_equity=80,
        total_assets=150,
        total_liabilities=70,
    )
    assert z > 5.85  # safe zone per Altman's Z''


def test_altman_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        altman_z_score_manufacturing(
            working_capital=10, retained_earnings=10, ebit=5,
            market_value_equity=20, sales=50,
            total_assets=0, total_liabilities=10,
        )


def test_rating_from_z_score_monotone():
    # Higher Z → better rating (lower ordinal)
    high = RatingLookup.rating_from_z_score(8.0)
    mid = RatingLookup.rating_from_z_score(5.5)
    low = RatingLookup.rating_from_z_score(2.0)
    very_low = RatingLookup.rating_from_z_score(0.5)

    lookup = RatingLookup.from_csv()
    assert lookup.rating_to_ordinal[high] < lookup.rating_to_ordinal[mid]
    assert lookup.rating_to_ordinal[mid] < lookup.rating_to_ordinal[low]
    assert lookup.rating_to_ordinal[low] < lookup.rating_to_ordinal[very_low]


def test_pd_from_z_score_bounded(lookup: RatingLookup):
    assert 0.0 <= lookup.pd_from_z_score(10.0) < 0.01
    assert 0.0 < lookup.pd_from_z_score(2.0) < 1.0


def test_default_lgd_is_60_percent():
    assert DEFAULT_LGD == pytest.approx(0.60)
