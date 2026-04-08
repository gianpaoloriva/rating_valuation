"""Streamlit page 6 — Backtest comparator (Agentic Credit Risk vs Altman Z)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from app._common import load_bundle, page_header, sector_selector, year_selector
from rating_valuation.backtest import BacktestRunner

st.set_page_config(page_title="Backtest Comparator", page_icon="🏁", layout="wide")


def main() -> None:
    page_header(
        "Backtest Comparator",
        subtitle="Confronto Agentic Credit Risk vs Altman Z-score su un campione selezionato",
        icon="🏁",
    )
    bundle = load_bundle()

    st.sidebar.header("Campione")
    sub_industry = sector_selector(bundle, key="bt_sector")
    year = year_selector(bundle, sub_industry, key="bt_year")
    n_trials = st.sidebar.select_slider(
        "Trial Monte Carlo per azienda",
        options=[500, 1000, 2500, 5000],
        value=1000,
    )
    n_years = st.sidebar.slider("Orizzonte (anni)", 1, 5, 3)

    sample = bundle.companies[
        (bundle.companies["gics_sub_industry"] == sub_industry)
        & (bundle.companies["fiscal_year"] == year)
    ].copy()

    st.subheader(f"Campione: {sub_industry} — FY{year} ({len(sample)} aziende)")

    # ------------------------------------------------------------------
    # Choose which companies to label as "defaulted" (manual for demo)
    # ------------------------------------------------------------------
    st.markdown("Seleziona le aziende da etichettare come 'defaulted' (serve per calcolare Gini/AUROC):")
    default_cols = st.columns(3)
    defaulted_set: set[str] = set()
    for i, (_, row) in enumerate(sample.iterrows()):
        col = default_cols[i % 3]
        checked = col.checkbox(
            f"{row['company_name']} ({row['company_id']})",
            key=f"def_{row['company_id']}",
            value=False,
        )
        if checked:
            defaulted_set.add(str(row["company_id"]))

    run = st.button("▶ Esegui backtest", type="primary")
    if not run:
        st.info("Configura il campione e premi ▶ Esegui backtest")
        return

    with st.spinner(f"Backtest di {len(sample)} aziende × {n_trials} trial..."):
        runner = BacktestRunner(
            bundle.sectors,
            bundle.macro,
            rating_master_scale=bundle.rating_master_scale,
            n_trials=n_trials,
            n_years=n_years,
        )
        result = runner.run(sample, defaulted_ids=defaulted_set, seed=42)

    st.success(result.summary())

    # ------------------------------------------------------------------
    # Per-company table
    # ------------------------------------------------------------------
    st.markdown("### Risultati per azienda")
    df = result.as_dataframe()
    st.dataframe(
        df.style.format(
            {
                "acr_pd": "{:.2%}",
                "altman_z": "{:.2f}",
                "altman_pd": "{:.2%}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ------------------------------------------------------------------
    # Metrics table (if both labels present)
    # ------------------------------------------------------------------
    if defaulted_set and (len(defaulted_set) < len(sample)):
        st.markdown("### Metriche di discriminazione")
        metrics = result.metrics_table()
        st.dataframe(
            metrics.style.format(
                {
                    "auroc": "{:.3f}",
                    "gini": "{:.3f}",
                    "ks": "{:.3f}",
                    "mean_pd_defaulted": "{:.2%}",
                    "mean_pd_performing": "{:.2%}",
                    "median_pd_defaulted": "{:.2%}",
                    "median_pd_performing": "{:.2%}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "Seleziona almeno una azienda defaulted e almeno una performing "
            "per calcolare AUROC/Gini/KS."
        )

    # ------------------------------------------------------------------
    # Scatter: Agentic Credit Risk PD vs Altman PD
    # ------------------------------------------------------------------
    st.markdown("### Confronto Agentic Credit Risk vs Altman Z''")
    plot_df = df.copy()
    plot_df["label"] = plot_df["is_defaulted"].map({0: "Performing", 1: "Defaulted"})
    fig = px.scatter(
        plot_df,
        x="altman_pd",
        y="acr_pd",
        color="label",
        size=[40] * len(plot_df),
        hover_name="company_name",
        log_x=True,
        log_y=True,
        title="PD implicite a confronto (scala log)",
        labels={"altman_pd": "Altman Z'' PD", "acr_pd": "Agentic Credit Risk PD cum. 3y"},
    )
    # 45° reference line
    fig.add_shape(
        type="line",
        x0=0.0001, y0=0.0001, x1=1, y1=1,
        line=dict(dash="dash", color="gray"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ------------------------------------------------------------------
    # Rating distribution
    # ------------------------------------------------------------------
    st.markdown("### Distribuzione dei rating implicati")
    rating_counts_acr = df["acr_rating"].value_counts().reset_index()
    rating_counts_acr.columns = ["rating", "count"]
    rating_counts_acr["model"] = "Agentic Credit Risk"
    rating_counts_altman = df["altman_rating"].value_counts().reset_index()
    rating_counts_altman.columns = ["rating", "count"]
    rating_counts_altman["model"] = "Altman Z''"
    combined = pd.concat([rating_counts_acr, rating_counts_altman], ignore_index=True)
    fig2 = px.bar(
        combined,
        x="rating",
        y="count",
        color="model",
        barmode="group",
        title="Rating assegnati da ciascun modello",
    )
    st.plotly_chart(fig2, use_container_width=True)


main()
