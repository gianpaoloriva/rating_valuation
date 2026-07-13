"""Guard tests for the primary dataset in data/ (real AIDA data).

The synthetic fixture in data/synthetic/ has its own dedicated tests; here we
only verify that the ETL output keeps satisfying the schema, the balance-sheet
invariants and the minimum BMS sample size.
"""

from __future__ import annotations

import pytest

from rating_valuation.common.data_loader import (
    DEFAULT_DATA_DIR,
    load_all,
    peer_sample,
    target_row,
)
from rating_valuation.common.invariants import check_invariants

pytestmark = pytest.mark.skipif(
    not (DEFAULT_DATA_DIR / "companies.csv").exists(),
    reason="primary dataset missing — run data/etl/aida_to_companies.py",
)


@pytest.fixture(scope="module")
def bundle():
    return load_all()


def test_primary_dataset_invariants(bundle):
    assert check_invariants(bundle.companies) == []


def test_primary_dataset_single_target(bundle):
    tgt = target_row(bundle.companies)
    assert tgt["company_id"].nunique() == 1


def test_primary_dataset_sector_keys_consistent(bundle):
    company_keys = set(bundle.companies["gics_sub_industry"])
    sector_keys = set(bundle.sectors["gics_sub_industry"])
    assert company_keys <= sector_keys


def test_primary_dataset_peer_sample_above_bms_threshold(bundle):
    sub = target_row(bundle.companies)["gics_sub_industry"].iloc[0]
    latest = int(bundle.companies["fiscal_year"].max())
    peers = peer_sample(bundle.companies, sub, fiscal_year=latest)
    assert len(peers) >= 20


def test_primary_dataset_macro_covers_company_years(bundle):
    years = set(bundle.companies["fiscal_year"])
    macro_it = set(bundle.macro.loc[bundle.macro["country"] == "IT", "year"])
    assert years <= macro_it
