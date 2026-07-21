"""Shared utilities for the Streamlit dashboard pages.

Kept intentionally small: data loading with Streamlit caching and a few
formatting helpers. All heavy lifting is delegated to the
``rating_valuation`` library.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from rating_valuation.common.data_loader import DataBundle, load_all, peer_sample

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
# data/ = dataset principale (reale, AIDA); override con RV_DATA_DIR
# (es. RV_DATA_DIR=data/synthetic per la demo sul dataset sintetico)
DATA_DIR = Path(os.environ.get("RV_DATA_DIR", REPO_ROOT / "data"))


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


_TARGET_STATE_KEY = "rv_target_company_id"


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
    # La scelta è condivisa tra le pagine: chi cambia target su una pagina
    # se lo ritrova selezionato anche sulle altre (fallback: is_target=1).
    remembered = st.session_state.get(_TARGET_STATE_KEY)
    default_idx = options.index(remembered) if remembered in options else 0
    selected = st.sidebar.selectbox(
        "Azienda target",
        options,
        index=default_idx,
        format_func=lambda cid: labels[cid],
        key=key,
    )
    st.session_state[_TARGET_STATE_KEY] = selected
    return subset[subset["company_id"] == selected].iloc[0]


def peer_sample_for_target(
    bundle: DataBundle,
    gics_sub_industry: str,
    fiscal_year: int,
    target: pd.Series,
) -> pd.DataFrame:
    """Peer sample that excludes both the flagged target and the selected one.

    ``peer_sample`` drops only ``is_target == 1``: if the user picks a
    different company from the dropdown, that company must not stay inside
    the BMS it is compared against.
    """
    peers = peer_sample(bundle.companies, gics_sub_industry, fiscal_year=fiscal_year)
    return peers[peers["company_id"] != target["company_id"]].reset_index(drop=True)
