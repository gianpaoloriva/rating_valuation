"""Streamlit page 3 — Differential analysis target vs BMS."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from app._common import (
    load_bundle,
    page_header,
    peer_sample_for_target,
    sector_selector,
    target_selector,
    year_selector,
)
from rating_valuation.bms.builder import BMSBuilder
from rating_valuation.differential import DifferentialAnalyzer

st.set_page_config(page_title="Differential Analysis", page_icon="🔀", layout="wide")


def main() -> None:
    page_header(
        "Differential Analysis",
        subtitle="Analisi differenziale del target rispetto al Bilancio Medio Standardizzato di settore",
        icon="🔀",
    )
    bundle = load_bundle()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    st.sidebar.header("Selezione")
    sub_industry = sector_selector(bundle, key="diff_sector")
    year = year_selector(bundle, sub_industry, key="diff_year")
    target = target_selector(bundle, sub_industry, year, key="diff_target")
    min_sample = st.sidebar.slider("Soglia min campione BMS", 5, 30, 15)

    # ------------------------------------------------------------------
    # Build BMS and differential
    # ------------------------------------------------------------------
    peers = peer_sample_for_target(bundle, sub_industry, year, target)
    if peers.empty:
        st.error(f"Nessun peer per {sub_industry}/{year}")
        return
    bms = BMSBuilder(peers, min_sample_size=min_sample).build()
    analyzer = DifferentialAnalyzer(bms)
    report = analyzer.analyze(target)

    # ------------------------------------------------------------------
    # Header metrics
    # ------------------------------------------------------------------
    st.subheader(report.summary_line())
    c1, c2, c3 = st.columns(3)
    c1.metric("Peer nel BMS", bms.n_companies)
    c2.metric(
        "Favorevoli",
        f"{report.favorable_count()} / {len(report.comparisons)}",
    )
    c3.metric(
        "Sfavorevoli",
        report.unfavorable_count(),
    )

    # ------------------------------------------------------------------
    # Comparison table
    # ------------------------------------------------------------------
    df = report.as_dataframe().copy()

    def format_value(unit: str, value: float) -> str:
        if unit == "pct":
            return f"{value * 100:.2f}%"
        if unit == "ratio":
            return f"{value:.3f}"
        return f"{value:,.2f}"

    formatted = pd.DataFrame(
        {
            "Indicatore": df["label"],
            "Categoria": df["category"],
            "Target": [format_value(u, v) for u, v in zip(df["unit"], df["target"])],
            "BMS": [format_value(u, v) for u, v in zip(df["unit"], df["bms"])],
            "Δ": [
                f"{(t - b) * 100:+.2f} p.p." if u == "pct" else f"{t - b:+,.3f}"
                for u, t, b in zip(df["unit"], df["target"], df["bms"])
            ],
            "Direzione": ["✅" if f else "❌" for f in df["favorable"]],
        }
    )
    st.dataframe(formatted, use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------
    # Delta chart (pct items only)
    # ------------------------------------------------------------------
    chart_df = df[df["unit"] == "pct"].copy()
    chart_df["delta_pp"] = chart_df["delta"] * 100
    chart_df = chart_df.sort_values("delta_pp", ascending=True)
    fig = px.bar(
        chart_df,
        x="delta_pp",
        y="label",
        color="favorable",
        color_discrete_map={True: "#2CA02C", False: "#D62728"},
        orientation="h",
        title="Scostamenti vs BMS (punti percentuali)",
        labels={"delta_pp": "Δ (p.p.)", "label": ""},
        text_auto=".2f",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ------------------------------------------------------------------
    # Breakdown by category
    # ------------------------------------------------------------------
    st.markdown("### Analisi per categoria")
    categories = report.by_category()
    for category, comps in categories.items():
        with st.expander(f"{category} ({len(comps)} indicatori)"):
            cat_df = pd.DataFrame([c.as_dict() for c in comps])
            st.dataframe(
                cat_df[["label", "target", "bms", "delta", "delta_pct", "favorable"]]
                .rename(columns={
                    "label": "Indicatore",
                    "target": "Target",
                    "bms": "BMS",
                    "delta": "Δ",
                    "delta_pct": "Δ %",
                    "favorable": "Favorevole",
                }),
                use_container_width=True,
                hide_index=True,
            )


main()
