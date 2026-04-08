"""Tests for rating_valuation.bms.builder."""

from __future__ import annotations

import pandas as pd
import pytest

from rating_valuation.bms.builder import (
    BALANCE_SHEET_ITEMS,
    INCOME_STATEMENT_ITEMS,
    BMSBuilder,
    BMSResult,
    build_bms_timeseries,
)
from rating_valuation.common.data_loader import load_companies, peer_sample


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def companies() -> pd.DataFrame:
    return load_companies()


@pytest.fixture
def peers_2024(companies: pd.DataFrame) -> pd.DataFrame:
    return peer_sample(companies, "Industrial Machinery", fiscal_year=2024)


# -----------------------------------------------------------------------------
# Construction basics
# -----------------------------------------------------------------------------


def test_builder_rejects_empty_sample():
    with pytest.raises(ValueError, match="empty"):
        BMSBuilder(pd.DataFrame(columns=["company_id", "fiscal_year", "revenues"]))


def test_builder_rejects_multi_year_without_explicit_year(companies: pd.DataFrame):
    multi_year = companies[companies["gics_sub_industry"] == "Industrial Machinery"]
    multi_year = multi_year[multi_year["is_target"] == 0]
    with pytest.raises(ValueError, match="single fiscal year"):
        BMSBuilder(multi_year)


def test_builder_filters_on_fiscal_year(companies: pd.DataFrame):
    multi_year = companies[companies["gics_sub_industry"] == "Industrial Machinery"]
    multi_year = multi_year[multi_year["is_target"] == 0]
    builder = BMSBuilder(multi_year, fiscal_year=2024)
    assert builder.fiscal_year == 2024


# -----------------------------------------------------------------------------
# Structural properties of BMSResult
# -----------------------------------------------------------------------------


def test_bms_result_structure(peers_2024: pd.DataFrame):
    result = BMSBuilder(peers_2024).build()
    assert isinstance(result, BMSResult)
    assert result.fiscal_year == 2024
    assert result.n_companies == 15
    assert len(result.sample_ids) == 15

    # Series indexed on the expected items
    assert list(result.income_statement.index) == list(INCOME_STATEMENT_ITEMS)
    assert list(result.balance_sheet.index) == list(BALANCE_SHEET_ITEMS)

    # All values finite
    assert result.income_statement.notna().all()
    assert result.balance_sheet.notna().all()


def test_below_min_sample_flag(peers_2024: pd.DataFrame):
    # Default min is 20, we have 15 → flag must be True
    result = BMSBuilder(peers_2024).build()
    assert result.below_min_sample is True

    # With a lower threshold the flag clears
    result_lo = BMSBuilder(peers_2024, min_sample_size=10).build()
    assert result_lo.below_min_sample is False


# -----------------------------------------------------------------------------
# Numerical properties — the core of the Scarano/Brughera formula
# -----------------------------------------------------------------------------


def test_average_revenues_matches_mean(peers_2024: pd.DataFrame):
    result = BMSBuilder(peers_2024).build()
    assert result.average_revenues == pytest.approx(peers_2024["revenues"].mean())


def test_average_total_assets_matches_mean(peers_2024: pd.DataFrame):
    result = BMSBuilder(peers_2024).build()
    assert result.average_total_assets == pytest.approx(peers_2024["total_assets"].mean())


def test_income_statement_formula(peers_2024: pd.DataFrame):
    """
    BMS_i = (1/n · sum(voce/fatturato)) · (1/n · sum(fatturato))
    """
    result = BMSBuilder(peers_2024).build()
    n = len(peers_2024)
    avg_rev = peers_2024["revenues"].sum() / n

    for item in ("ebitda", "ebit", "nopat"):
        expected_share = (peers_2024[item] / peers_2024["revenues"]).sum() / n
        expected_value = expected_share * avg_rev
        assert result.income_statement_shares[item] == pytest.approx(expected_share)
        assert result.income_statement[item] == pytest.approx(expected_value)


def test_balance_sheet_formula(peers_2024: pd.DataFrame):
    result = BMSBuilder(peers_2024).build()
    n = len(peers_2024)
    avg_ta = peers_2024["total_assets"].sum() / n

    for item in ("net_fixed_assets", "net_working_capital", "equity"):
        expected_share = (peers_2024[item] / peers_2024["total_assets"]).sum() / n
        expected_value = expected_share * avg_ta
        assert result.balance_sheet_shares[item] == pytest.approx(expected_share)
        assert result.balance_sheet[item] == pytest.approx(expected_value)


def test_bms_revenues_equal_average_revenues(peers_2024: pd.DataFrame):
    """Since revenues/revenues = 1, the BMS 'revenues' line must equal the average."""
    result = BMSBuilder(peers_2024).build()
    assert result.income_statement["revenues"] == pytest.approx(result.average_revenues)
    assert result.income_statement_shares["revenues"] == pytest.approx(1.0)


def test_bms_total_assets_equal_average_total_assets(peers_2024: pd.DataFrame):
    result = BMSBuilder(peers_2024).build()
    assert result.balance_sheet["total_assets"] == pytest.approx(result.average_total_assets)
    assert result.balance_sheet_shares["total_assets"] == pytest.approx(1.0)


def test_line_by_line_sum_differs_from_bms(peers_2024: pd.DataFrame):
    """
    The line-by-line sum must NOT equal the BMS. The difference is exactly the
    dimensional distortion that the BMS method corrects (Scarano/Brughera).
    """
    result = BMSBuilder(peers_2024).build()
    n = len(peers_2024)

    # Line-by-line sum of ebitda vs n × bms_ebitda
    summed = result.line_by_line_sum_income["ebitda"]
    implied_from_bms = n * result.income_statement["ebitda"]
    # They will differ because larger companies distort the simple sum
    assert summed != pytest.approx(implied_from_bms, rel=1e-3)


def test_peer_shares_match_row_count(peers_2024: pd.DataFrame):
    result = BMSBuilder(peers_2024).build()
    assert len(result.peer_income_shares) == 15
    assert len(result.peer_balance_shares) == 15
    assert "company_id" in result.peer_income_shares.columns


# -----------------------------------------------------------------------------
# Conversion helpers
# -----------------------------------------------------------------------------


def test_as_dataframe_contains_both_statements(peers_2024: pd.DataFrame):
    result = BMSBuilder(peers_2024).build()
    df = result.as_dataframe()
    assert set(df["statement"]) == {"income_statement", "balance_sheet"}
    assert len(df) == len(INCOME_STATEMENT_ITEMS) + len(BALANCE_SHEET_ITEMS)


# -----------------------------------------------------------------------------
# Time series helper
# -----------------------------------------------------------------------------


def test_build_bms_timeseries_all_years(companies: pd.DataFrame):
    series = build_bms_timeseries(companies, "Industrial Machinery", min_sample_size=10)
    assert set(series.keys()) == {2022, 2023, 2024}
    for year, result in series.items():
        assert result.fiscal_year == year
        assert result.n_companies == 15


def test_bms_timeseries_revenues_grow_over_time(companies: pd.DataFrame):
    series = build_bms_timeseries(companies, "Industrial Machinery", min_sample_size=10)
    rev_22 = series[2022].average_revenues
    rev_24 = series[2024].average_revenues
    # Peer sample grows ~4.5% per year → 2024 strictly > 2022
    assert rev_24 > rev_22
