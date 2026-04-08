"""Streamlit page 1 — Bilancio Medio Standardizzato."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from app._common import fmt_money, load_bundle, page_header, sector_selector, year_selector
from rating_valuation.bms.builder import BMSBuilder, build_bms_timeseries
from rating_valuation.common.data_loader import peer_sample

st.set_page_config(page_title="BMS Builder", page_icon="🏗️", layout="wide")


def main() -> None:
    page_header(
        "BMS Builder",
        subtitle="Costruzione del Bilancio Medio Standardizzato secondo la metodologia Scarano/Brughera (AIAF n. 65)",
        icon="🏗️",
    )
    bundle = load_bundle()

    # ------------------------------------------------------------------
    # Sidebar parameters
    # ------------------------------------------------------------------
    st.sidebar.header("Parametri")
    sub_industry = sector_selector(bundle, key="bms_sector")
    year = year_selector(bundle, sub_industry, key="bms_year")
    min_sample = st.sidebar.slider(
        "Soglia minima campione",
        min_value=5, max_value=30, value=15,
        help="Il paper suggerisce ≥20 imprese. Sotto soglia il BMS è calcolato ma flaggato.",
    )

    # ------------------------------------------------------------------
    # Build BMS
    # ------------------------------------------------------------------
    peers = peer_sample(bundle.companies, sub_industry, fiscal_year=year)
    if peers.empty:
        st.error(f"Nessun peer trovato per {sub_industry} / {year}")
        return

    result = BMSBuilder(peers, min_sample_size=min_sample).build()

    if result.below_min_sample:
        st.warning(
            f"Campione di {result.n_companies} imprese, sotto la soglia di {min_sample}. "
            "Il BMS è calcolato ma la significatività è limitata."
        )

    # ------------------------------------------------------------------
    # KPI
    # ------------------------------------------------------------------
    st.subheader(f"BMS {sub_industry} — FY{year}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Peer nel campione", result.n_companies)
    c2.metric("Fatturato medio", fmt_money(result.average_revenues))
    c3.metric(
        "EBITDA margin",
        f"{result.income_statement_shares['ebitda'] * 100:.2f}%",
    )
    c4.metric(
        "EBIT margin",
        f"{result.income_statement_shares['ebit'] * 100:.2f}%",
    )

    # ------------------------------------------------------------------
    # CE and SP tables
    # ------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Conto Economico", "Stato Patrimoniale", "Peer composition", "Serie storica"]
    )

    with tab1:
        ce = pd.DataFrame(
            {
                "Voce": result.income_statement.index,
                "Valore (EUR M)": result.income_statement.values,
                "% su fatturato": result.income_statement_shares.values,
            }
        )
        ce["% su fatturato"] = ce["% su fatturato"].map(lambda x: f"{x * 100:.2f}%")
        ce["Valore (EUR M)"] = ce["Valore (EUR M)"].map(lambda x: f"{x:,.2f}")
        st.dataframe(ce, use_container_width=True, hide_index=True)

        # Waterfall-like bar chart of CE items as % of revenues
        ce_chart = pd.DataFrame(
            {
                "Voce": result.income_statement_shares.index,
                "% su fatturato": result.income_statement_shares.values * 100,
            }
        )
        fig = px.bar(
            ce_chart,
            x="Voce",
            y="% su fatturato",
            title="Composizione del Conto Economico BMS (%)",
            text_auto=".1f",
        )
        fig.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        sp = pd.DataFrame(
            {
                "Voce": result.balance_sheet.index,
                "Valore (EUR M)": result.balance_sheet.values,
                "% su totale attivo": result.balance_sheet_shares.values,
            }
        )
        sp["% su totale attivo"] = sp["% su totale attivo"].map(lambda x: f"{x * 100:.2f}%")
        sp["Valore (EUR M)"] = sp["Valore (EUR M)"].map(lambda x: f"{x:,.2f}")
        st.dataframe(sp, use_container_width=True, hide_index=True)

        sp_chart = pd.DataFrame(
            {
                "Voce": result.balance_sheet_shares.index,
                "% su totale attivo": result.balance_sheet_shares.values * 100,
            }
        )
        fig = px.bar(
            sp_chart,
            x="Voce",
            y="% su totale attivo",
            title="Composizione dello Stato Patrimoniale BMS (%)",
            text_auto=".1f",
        )
        fig.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.caption(
            "Distribuzione delle voci normalizzate su ciascuna impresa del campione. "
            "Aiuta a identificare peer outlier."
        )
        peer_shares = result.peer_income_shares.copy()
        st.dataframe(peer_shares, use_container_width=True, hide_index=True)

        ebitda_chart = peer_shares[["company_id", "ebitda"]].copy()
        ebitda_chart["ebitda"] *= 100
        fig = px.bar(
            ebitda_chart.sort_values("ebitda", ascending=True),
            x="ebitda",
            y="company_id",
            orientation="h",
            title="EBITDA margin per peer (%)",
            text_auto=".1f",
        )
        fig.add_vline(
            x=result.income_statement_shares["ebitda"] * 100,
            line_dash="dash",
            line_color="red",
            annotation_text="BMS media",
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.caption("Serie storica del BMS per il sotto-settore selezionato.")
        timeseries = build_bms_timeseries(
            bundle.companies, sub_industry, min_sample_size=min_sample
        )
        if not timeseries:
            st.info("Nessuna serie storica disponibile")
        else:
            ts_rows = [
                {
                    "anno": y,
                    "fatturato_medio": r.average_revenues,
                    "ebitda_margin": r.income_statement_shares["ebitda"],
                    "ebit_margin": r.income_statement_shares["ebit"],
                    "nopat_margin": r.income_statement_shares["nopat"],
                    "leverage_D/TA": r.balance_sheet_shares["gross_debt"],
                }
                for y, r in sorted(timeseries.items())
            ]
            ts_df = pd.DataFrame(ts_rows)

            st.dataframe(
                ts_df.assign(
                    fatturato_medio=ts_df["fatturato_medio"].map(lambda x: f"{x:,.2f}"),
                    ebitda_margin=ts_df["ebitda_margin"].map(lambda x: f"{x * 100:.2f}%"),
                    ebit_margin=ts_df["ebit_margin"].map(lambda x: f"{x * 100:.2f}%"),
                    nopat_margin=ts_df["nopat_margin"].map(lambda x: f"{x * 100:.2f}%"),
                    **{"leverage_D/TA": ts_df["leverage_D/TA"].map(lambda x: f"{x * 100:.2f}%")},
                ),
                use_container_width=True,
                hide_index=True,
            )

            fig = px.line(
                ts_df,
                x="anno",
                y=["ebitda_margin", "ebit_margin", "nopat_margin"],
                title="Evoluzione dei margini di settore",
                markers=True,
            )
            fig.update_yaxes(tickformat=".1%")
            st.plotly_chart(fig, use_container_width=True)


main()
