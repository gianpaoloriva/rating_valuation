"""Typed CSV loaders for the reference datasets.

All loaders validate that the expected columns are present and return pandas
DataFrames with the correct dtypes. Monetary values remain in the unit of the
source CSV (millions of the `currency` column for companies.csv).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# -----------------------------------------------------------------------------
# Default locations
# -----------------------------------------------------------------------------

# repo root = parent of src/ (package installed in editable mode from there)
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = _REPO_ROOT / "data"

COMPANIES_CSV = "companies.csv"
SECTORS_CSV = "sectors.csv"
MACRO_CSV = "macro.csv"
RATING_MASTER_SCALE_CSV = "rating_master_scale.csv"


# -----------------------------------------------------------------------------
# Expected schemas
# -----------------------------------------------------------------------------

COMPANY_NUMERIC_COLUMNS: tuple[str, ...] = (
    "revenues",
    "operating_costs",
    "ebitda",
    "depreciation_amortization",
    "ebit",
    "interest_expense",
    "pre_tax_income",
    "taxes",
    "net_income",
    "nopat",
    "net_fixed_assets",
    "net_working_capital",
    "net_invested_capital",
    "gross_debt",
    "cash",
    "net_debt",
    "equity",
    "total_assets",
    "capex",
    "cost_of_debt",
    "corporate_tax_rate",
)

COMPANY_IDENTIFIER_COLUMNS: tuple[str, ...] = (
    "company_id",
    "company_name",
    "is_target",
    "country",
    "currency",
    "gics_sector",
    "gics_sub_industry",
    "fiscal_year",
)

COMPANY_REQUIRED_COLUMNS = COMPANY_IDENTIFIER_COLUMNS + COMPANY_NUMERIC_COLUMNS + ("employees",)

SECTOR_REQUIRED_COLUMNS: tuple[str, ...] = (
    "gics_sector",
    "gics_sub_industry",
    "beta_unlevered",
    "weibull_revenues_shape",
    "weibull_opcosts_shape",
    "weibull_nfa_shape",
    "weibull_nwc_shape",
    "autocorr_revenues",
    "autocorr_opcosts",
    "autocorr_nfa",
    "autocorr_nwc",
    "corr_sales_opcosts",
    "corr_nfa_opcosts",
    "corr_sales_nfa",
    "corr_sales_nwc",
)

MACRO_REQUIRED_COLUMNS: tuple[str, ...] = (
    "country",
    "year",
    "gdp_real_growth",
    "inflation_rate",
    "gdp_nominal_growth_5y_avg",
    "risk_free_rate_10y",
    "market_risk_premium",
    "credit_spread_bbb",
)

RATING_REQUIRED_COLUMNS: tuple[str, ...] = ("rating", "rating_ordinal", "pd_1y")


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class SchemaError(ValueError):
    """Raised when a CSV is missing required columns."""


@dataclass(frozen=True)
class DataBundle:
    """Convenience container for all reference datasets."""

    companies: pd.DataFrame
    sectors: pd.DataFrame
    macro: pd.DataFrame
    rating_master_scale: pd.DataFrame


# -----------------------------------------------------------------------------
# Validation helper
# -----------------------------------------------------------------------------


def _validate_columns(df: pd.DataFrame, required: tuple[str, ...], source: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaError(f"{source}: missing required columns: {missing}")


# -----------------------------------------------------------------------------
# Individual loaders
# -----------------------------------------------------------------------------


def load_companies(path: Path | str | None = None) -> pd.DataFrame:
    """Load companies.csv with enforced dtypes and schema validation."""
    csv_path = Path(path) if path else DEFAULT_DATA_DIR / COMPANIES_CSV
    df = pd.read_csv(csv_path)
    _validate_columns(df, COMPANY_REQUIRED_COLUMNS, str(csv_path))

    df["is_target"] = df["is_target"].astype(int)
    df["fiscal_year"] = df["fiscal_year"].astype(int)
    df["employees"] = df["employees"].astype("Int64")

    for col in COMPANY_NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="raise")

    return df.sort_values(["company_id", "fiscal_year"]).reset_index(drop=True)


def load_sectors(path: Path | str | None = None) -> pd.DataFrame:
    csv_path = Path(path) if path else DEFAULT_DATA_DIR / SECTORS_CSV
    df = pd.read_csv(csv_path)
    _validate_columns(df, SECTOR_REQUIRED_COLUMNS, str(csv_path))
    return df


def load_macro(path: Path | str | None = None) -> pd.DataFrame:
    csv_path = Path(path) if path else DEFAULT_DATA_DIR / MACRO_CSV
    df = pd.read_csv(csv_path)
    _validate_columns(df, MACRO_REQUIRED_COLUMNS, str(csv_path))
    df["year"] = df["year"].astype(int)
    return df.sort_values(["country", "year"]).reset_index(drop=True)


def load_rating_master_scale(path: Path | str | None = None) -> pd.DataFrame:
    csv_path = Path(path) if path else DEFAULT_DATA_DIR / RATING_MASTER_SCALE_CSV
    df = pd.read_csv(csv_path)
    _validate_columns(df, RATING_REQUIRED_COLUMNS, str(csv_path))
    df["rating_ordinal"] = df["rating_ordinal"].astype(int)
    df["pd_1y"] = pd.to_numeric(df["pd_1y"], errors="raise")
    return df.sort_values("rating_ordinal").reset_index(drop=True)


def load_all(data_dir: Path | str | None = None) -> DataBundle:
    """Load all four reference datasets from a single directory."""
    base = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    return DataBundle(
        companies=load_companies(base / COMPANIES_CSV),
        sectors=load_sectors(base / SECTORS_CSV),
        macro=load_macro(base / MACRO_CSV),
        rating_master_scale=load_rating_master_scale(base / RATING_MASTER_SCALE_CSV),
    )


# -----------------------------------------------------------------------------
# Convenience selectors
# -----------------------------------------------------------------------------


def peer_sample(
    companies: pd.DataFrame,
    gics_sub_industry: str,
    fiscal_year: int | None = None,
    exclude_target: bool = True,
) -> pd.DataFrame:
    """Return the peer sample used to build the BMS for a given sub-industry.

    Parameters
    ----------
    companies : pd.DataFrame
        Output of `load_companies`.
    gics_sub_industry : str
        The target sub-industry.
    fiscal_year : int, optional
        If provided, filters to the given year.
    exclude_target : bool, default True
        If True, drops rows where `is_target == 1`.
    """
    df = companies[companies["gics_sub_industry"] == gics_sub_industry]
    if fiscal_year is not None:
        df = df[df["fiscal_year"] == fiscal_year]
    if exclude_target:
        df = df[df["is_target"] == 0]
    return df.reset_index(drop=True)


def target_row(
    companies: pd.DataFrame,
    fiscal_year: int | None = None,
) -> pd.DataFrame:
    """Return the row(s) for the target company (is_target == 1)."""
    df = companies[companies["is_target"] == 1]
    if fiscal_year is not None:
        df = df[df["fiscal_year"] == fiscal_year]
    return df.reset_index(drop=True)
