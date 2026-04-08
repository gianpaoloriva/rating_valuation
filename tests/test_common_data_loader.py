"""Tests for rating_valuation.common.data_loader."""

from __future__ import annotations

import pandas as pd
import pytest

from rating_valuation.common.data_loader import (
    COMPANY_NUMERIC_COLUMNS,
    DataBundle,
    SchemaError,
    load_all,
    load_companies,
    load_macro,
    load_rating_master_scale,
    load_sectors,
    peer_sample,
    target_row,
)


def test_load_companies_has_expected_shape():
    df = load_companies()
    assert len(df) == 48
    assert df["company_id"].nunique() == 16
    assert sorted(df["fiscal_year"].unique().tolist()) == [2022, 2023, 2024]


def test_load_companies_numeric_dtypes():
    df = load_companies()
    for col in COMPANY_NUMERIC_COLUMNS:
        assert pd.api.types.is_numeric_dtype(df[col]), f"{col} should be numeric"
    assert df["is_target"].dtype.kind in "iu"
    assert df["fiscal_year"].dtype.kind in "iu"


def test_load_companies_target_flag_unique():
    df = load_companies()
    targets = df[df["is_target"] == 1]
    assert targets["company_id"].nunique() == 1
    assert targets["company_name"].iloc[0] == "Riva Meccanica SpA"


def test_load_sectors_has_default_industrial_machinery():
    df = load_sectors()
    im = df[df["gics_sub_industry"] == "Industrial Machinery"]
    assert len(im) == 1
    assert 0.5 < im["beta_unlevered"].iloc[0] < 1.5


def test_load_macro_italy_years():
    df = load_macro()
    italy = df[df["country"] == "IT"]
    assert set(range(2022, 2027)).issubset(set(italy["year"]))


def test_load_rating_master_scale_boundaries():
    df = load_rating_master_scale()
    assert df["rating"].iloc[0] == "AAA"
    assert df["rating"].iloc[-1] == "D"
    assert df["pd_1y"].iloc[0] == pytest.approx(0.0)
    assert df["pd_1y"].iloc[-1] == pytest.approx(1.0)
    # monotonic non-decreasing
    assert df["pd_1y"].is_monotonic_increasing


def test_load_all_returns_bundle():
    bundle = load_all()
    assert isinstance(bundle, DataBundle)
    assert len(bundle.companies) > 0
    assert len(bundle.sectors) > 0
    assert len(bundle.macro) > 0
    assert len(bundle.rating_master_scale) == 22


def test_peer_sample_excludes_target():
    df = load_companies()
    peers = peer_sample(df, "Industrial Machinery", fiscal_year=2024)
    assert (peers["is_target"] == 0).all()
    assert len(peers) == 15
    assert (peers["fiscal_year"] == 2024).all()


def test_target_row_single_year():
    df = load_companies()
    tgt = target_row(df, fiscal_year=2024)
    assert len(tgt) == 1
    assert tgt["company_name"].iloc[0] == "Riva Meccanica SpA"


def test_schema_error_on_missing_columns(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("foo,bar\n1,2\n")
    with pytest.raises(SchemaError, match="missing required columns"):
        load_companies(csv_path)


def test_load_companies_accepts_file_like_object():
    """The loader must accept BytesIO/file-like inputs (used by the Streamlit
    Data Manager page for uploads)."""
    import io

    from rating_valuation.common.data_loader import DEFAULT_DATA_DIR

    raw = (DEFAULT_DATA_DIR / "companies.csv").read_bytes()
    df = load_companies(io.BytesIO(raw))
    assert len(df) == 48
    assert df["company_id"].nunique() == 16


def test_load_sectors_accepts_file_like_object():
    import io

    from rating_valuation.common.data_loader import DEFAULT_DATA_DIR

    raw = (DEFAULT_DATA_DIR / "sectors.csv").read_bytes()
    df = load_sectors(io.BytesIO(raw))
    assert len(df) >= 1
    assert "gics_sub_industry" in df.columns
