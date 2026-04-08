"""Shared utilities for the Streamlit dashboard pages.

Kept intentionally small: data loading with Streamlit caching and a few
formatting helpers. All heavy lifting is delegated to the
``rating_valuation`` library.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from rating_valuation.common.data_loader import DataBundle, load_all


# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"


# -----------------------------------------------------------------------------
# Cached loaders
# -----------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def load_bundle() -> DataBundle:
    """Load all reference CSVs once per Streamlit session."""
    return load_all(DATA_DIR)


# -----------------------------------------------------------------------------
# Formatting helpers
# -----------------------------------------------------------------------------


def fmt_money(value: float, currency: str = "EUR M", decimals: int = 2) -> str:
    return f"{value:,.{decimals}f} {currency}"


def fmt_pct(value: float, decimals: int = 2, signed: bool = False) -> str:
    sign = "+" if signed and value >= 0 else ""
    return f"{sign}{value * 100:.{decimals}f}%"


def fmt_bps(value: float) -> str:
    return f"{value * 10_000:.0f} bps"


# -----------------------------------------------------------------------------
# Page header helper
# -----------------------------------------------------------------------------


def page_header(title: str, subtitle: str | None = None, icon: str | None = None) -> None:
    if icon:
        st.title(f"{icon} {title}")
    else:
        st.title(title)
    if subtitle:
        st.caption(subtitle)
    st.divider()


# -----------------------------------------------------------------------------
# Sidebar building blocks
# -----------------------------------------------------------------------------


def sector_selector(bundle: DataBundle, *, key: str) -> str:
    """Dropdown for selecting a GICS sub-industry from the dataset."""
    sub_industries = sorted(bundle.companies["gics_sub_industry"].unique().tolist())
    default_idx = 0
    if "Industrial Machinery" in sub_industries:
        default_idx = sub_industries.index("Industrial Machinery")
    return st.sidebar.selectbox(
        "GICS sub-industry",
        sub_industries,
        index=default_idx,
        key=key,
    )


def year_selector(
    bundle: DataBundle,
    gics_sub_industry: str,
    *,
    key: str,
    label: str = "Anno fiscale",
) -> int:
    years = sorted(
        bundle.companies[bundle.companies["gics_sub_industry"] == gics_sub_industry][
            "fiscal_year"
        ].unique().tolist()
    )
    return st.sidebar.selectbox(label, years, index=len(years) - 1, key=key)


def target_selector(
    bundle: DataBundle,
    gics_sub_industry: str,
    fiscal_year: int,
    *,
    key: str,
) -> pd.Series:
    subset = bundle.companies[
        (bundle.companies["gics_sub_industry"] == gics_sub_industry)
        & (bundle.companies["fiscal_year"] == fiscal_year)
    ]
    # Put the flagged target (if any) first
    subset = subset.sort_values("is_target", ascending=False)
    options = subset["company_id"].tolist()
    labels = {
        row["company_id"]: f"{row['company_name']}{' [TARGET]' if row['is_target'] else ''}"
        for _, row in subset.iterrows()
    }
    selected = st.sidebar.selectbox(
        "Azienda target",
        options,
        index=0,
        format_func=lambda cid: labels[cid],
        key=key,
    )
    return subset[subset["company_id"] == selected].iloc[0]
