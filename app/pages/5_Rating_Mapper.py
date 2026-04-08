"""Streamlit page 5 — Rating mapper (master scale, CDS → PD, Altman Z → rating)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from app._common import load_bundle, page_header
from rating_valuation.rating import (
    RatingLookup,
    altman_z_double_prime_non_manufacturing,
    altman_z_score_manufacturing,
)

st.set_page_config(page_title="Rating Mapper", page_icon="🎯", layout="wide")


def main() -> None:
    page_header(
        "Rating Mapper",
        subtitle="Conversioni Rating ↔ PD, CDS spread → PD, Altman Z-score → rating implicito",
        icon="🎯",
    )
    bundle = load_bundle()
    lookup = RatingLookup.from_csv()

    # ------------------------------------------------------------------
    # Master scale display
    # ------------------------------------------------------------------
    st.subheader("Master scale Rating ↔ PD (1 anno)")
    ms = bundle.rating_master_scale.copy()
    ms["pd_pct"] = ms["pd_1y"] * 100
    st.dataframe(
        ms[["rating", "rating_ordinal", "pd_1y", "notes"]].style.format({"pd_1y": "{:.4%}"}),
        use_container_width=True,
        hide_index=True,
    )

    fig = px.line(
        ms,
        x="rating_ordinal",
        y="pd_pct",
        markers=True,
        log_y=True,
        title="Master scale in scala logaritmica",
        labels={"rating_ordinal": "Classe rating (ordinale)", "pd_pct": "PD 1y (%)"},
    )
    fig.update_traces(text=ms["rating"], textposition="top center")
    st.plotly_chart(fig, use_container_width=True)

    # ------------------------------------------------------------------
    # PD → Rating converter
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("PD → Rating")
    pd_input = st.number_input(
        "PD a 1 anno (decimale)",
        min_value=0.0, max_value=1.0, value=0.005, step=0.001, format="%.5f",
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Rating implicito", lookup.rating_of_pd(pd_input))
    bracket = lookup.rating_of_pd_interpolated(pd_input)
    c2.metric(
        "Intervallo",
        f"{bracket[0]} → {bracket[1]}",
    )
    c3.metric("Frazione", f"{bracket[2]:.2f}")

    # ------------------------------------------------------------------
    # CDS → PD
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("CDS spread → PD (formula paper RAPD)")
    col1, col2, col3 = st.columns(3)
    cds_bps = col1.number_input(
        "CDS spread (bps)", min_value=0, max_value=5000, value=150, step=10
    )
    recovery = col2.slider("Recovery rate", 0.0, 1.0, 0.40, 0.05)
    maturity = col3.number_input("Maturity (anni)", min_value=0.5, max_value=10.0, value=1.0, step=0.5)

    lgd = 1.0 - recovery
    cds_decimal = cds_bps / 10_000.0
    pd_cds = RatingLookup.pd_from_cds(cds_decimal, lgd=lgd, maturity_years=maturity)
    rating_cds = lookup.rating_of_pd(pd_cds)

    c1, c2, c3 = st.columns(3)
    c1.metric("PD derivata", f"{pd_cds * 100:.4f}%")
    c2.metric("LGD assunta", f"{lgd * 100:.0f}%")
    c3.metric("Rating implicito", rating_cds)
    st.caption(f"Formula: PD = 1 − exp(−(CDS/LGD)·T) = 1 − exp(−({cds_decimal:.4f}/{lgd:.2f})·{maturity})")

    # ------------------------------------------------------------------
    # Altman Z → Rating
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("Altman Z-score → Rating")
    model_type = st.radio(
        "Modello",
        ["Z-score Original (manufacturing, quoted)", "Z''-score (non-manufacturing / private)"],
    )

    if model_type.startswith("Z-score Original"):
        c1, c2, c3 = st.columns(3)
        wc = c1.number_input("Working capital", value=30.0)
        re = c1.number_input("Retained earnings", value=50.0)
        ebit = c2.number_input("EBIT", value=15.0)
        mv = c2.number_input("Market value equity", value=120.0)
        sales = c3.number_input("Sales", value=200.0)
        ta = c3.number_input("Total assets", value=150.0)
        tl = c3.number_input("Total liabilities", value=60.0)
        try:
            z = altman_z_score_manufacturing(
                working_capital=wc, retained_earnings=re, ebit=ebit,
                market_value_equity=mv, sales=sales,
                total_assets=ta, total_liabilities=tl,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
    else:
        c1, c2, c3 = st.columns(3)
        wc = c1.number_input("Working capital", value=30.0)
        re = c1.number_input("Retained earnings", value=50.0)
        ebit = c2.number_input("EBIT", value=15.0)
        bv = c2.number_input("Book value equity", value=80.0)
        ta = c3.number_input("Total assets", value=150.0)
        tl = c3.number_input("Total liabilities", value=70.0)
        try:
            z = altman_z_double_prime_non_manufacturing(
                working_capital=wc, retained_earnings=re, ebit=ebit,
                book_value_equity=bv,
                total_assets=ta, total_liabilities=tl,
            )
        except ValueError as exc:
            st.error(str(exc))
            return

    rating_z = RatingLookup.rating_from_z_score(z)
    pd_z = lookup.pd_of(rating_z)
    c1, c2, c3 = st.columns(3)
    c1.metric("Z-score", f"{z:.2f}")
    c2.metric("Rating", rating_z)
    c3.metric("PD 1y", f"{pd_z * 100:.3f}%")


main()
