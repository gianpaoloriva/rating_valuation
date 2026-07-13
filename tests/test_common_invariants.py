"""Tests for rating_valuation.common.invariants."""

from __future__ import annotations

import pytest

from rating_valuation.common.data_loader import SYNTHETIC_DATA_DIR, load_companies
from rating_valuation.common.invariants import (
    assert_invariants,
    check_invariants,
)


def test_fake_dataset_passes_all_invariants():
    df = load_companies(SYNTHETIC_DATA_DIR / "companies.csv")
    violations = check_invariants(df)
    assert violations == []


def test_assert_invariants_no_raise():
    df = load_companies(SYNTHETIC_DATA_DIR / "companies.csv")
    assert_invariants(df)  # should not raise


def test_detects_ebitda_violation():
    df = load_companies(SYNTHETIC_DATA_DIR / "companies.csv").copy()
    # break one row: set ebitda to a wrong value
    idx = df.index[0]
    df.loc[idx, "ebitda"] = df.loc[idx, "ebitda"] + 10
    violations = check_invariants(df)
    assert len(violations) >= 1
    assert any("ebitda" in v.rule for v in violations)


def test_assert_invariants_raises_on_violation():
    df = load_companies(SYNTHETIC_DATA_DIR / "companies.csv").copy()
    idx = df.index[0]
    df.loc[idx, "net_invested_capital"] = -1  # clearly wrong
    with pytest.raises(AssertionError, match="invariants violated"):
        assert_invariants(df)


def test_tolerance_respected():
    df = load_companies(SYNTHETIC_DATA_DIR / "companies.csv").copy()
    idx = df.index[0]
    # nudge below default tolerance (0.01)
    df.loc[idx, "ebitda"] = df.loc[idx, "ebitda"] + 0.005
    assert check_invariants(df) == []
    # exceed it
    df.loc[idx, "ebitda"] = df.loc[idx, "ebitda"] + 0.020
    assert len(check_invariants(df)) >= 1
