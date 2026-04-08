"""Rating & Valuation Suite — Streamlit home page.

This file is the multipage entry point. Streamlit displays its filename
in the sidebar navigation, so it must be named after how we want the app
to appear: "Rating Valuation Suite".

Launch:
    streamlit run app/Rating_Valuation_Suite.py
"""

from __future__ import annotations

# Ensure the repo root is importable whether we run inside Docker
# (PYTHONPATH=/app) or locally from the repo root.
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from app._common import fmt_money, load_bundle, page_header

st.set_page_config(
    page_title="Rating & Valuation Suite",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    page_header(
        "Rating & Valuation Suite",
        subtitle="Valutazione d'impresa e credit risk forward-looking basati su BMS, DCF, Terminal Value coerente e Agentic Credit Risk",
    )

    bundle = load_bundle()

    # ------------------------------------------------------------------
    # Dataset overview
    # ------------------------------------------------------------------

    st.subheader("Dataset caricato")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Aziende",
        f"{bundle.companies['company_id'].nunique()}",
        help="Numero di company_id distinti in companies.csv",
    )
    col2.metric(
        "Righe (company × anno)",
        f"{len(bundle.companies):,}",
    )
    col3.metric(
        "Settori (GICS sub-industry)",
        f"{bundle.companies['gics_sub_industry'].nunique()}",
    )
    years = sorted(bundle.companies["fiscal_year"].unique().tolist())
    col4.metric(
        "Anni coperti",
        f"{years[0]}-{years[-1]}",
    )

    # ------------------------------------------------------------------
    # Settori e peer
    # ------------------------------------------------------------------
    st.markdown("### Settori disponibili nel campione")
    sector_counts = (
        bundle.companies.groupby("gics_sub_industry")
        .agg(
            aziende=("company_id", "nunique"),
            righe=("company_id", "size"),
            fatturato_medio=("revenues", "mean"),
        )
        .reset_index()
        .sort_values("aziende", ascending=False)
    )
    sector_counts["fatturato_medio"] = sector_counts["fatturato_medio"].map(
        lambda x: fmt_money(x)
    )
    st.dataframe(sector_counts, use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------
    # Target company (if any)
    # ------------------------------------------------------------------
    targets = bundle.companies[bundle.companies["is_target"] == 1]
    if not targets.empty:
        st.markdown("### Azienda target del dataset")
        st.dataframe(
            targets[
                [
                    "company_id",
                    "company_name",
                    "fiscal_year",
                    "gics_sub_industry",
                    "revenues",
                    "ebitda",
                    "ebit",
                    "nopat",
                    "gross_debt",
                    "equity",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    # ------------------------------------------------------------------
    # Navigation guide
    # ------------------------------------------------------------------
    st.markdown("### Navigazione")
    st.info(
        """
        Usa il menu laterale per accedere ai sette moduli:

        1. **BMS Builder** — costruzione del Bilancio Medio Standardizzato sul campione peer.
        2. **DCF Valuation** — valutazione a 2 / 3 stadi con Terminal Value coerente e validatore.
        3. **Differential Analysis** — confronto target vs Impresa Media Standard.
        4. **Agentic Credit Risk** — simulazione stocastica Monte Carlo per PD / LGD / EL / UL.
        5. **Rating Mapper** — conversioni Rating ↔ PD, CDS → PD, Altman Z → rating.
        6. **Backtest Comparator** — confronto Agentic Credit Risk vs Altman Z-score.
        7. **Data Manager** — download dei template CSV e upload di dataset personalizzati.
        """
    )

    with st.expander("Riferimenti metodologici"):
        st.markdown(
            """
            - **BMS** — Scarano A., Brughera G.L.G., *Valutazione di una PMI con approccio settoriale*, Rivista AIAF n. 65, 2008.
            - **Terminal Value** — Scarano A., Di Napoli G., *Calcolo del Terminal Value e rispetto delle condizioni di coerenza*, Rivista AIAF n. 66, 2008.
            - **Agentic Credit Risk** — basato su Montesi G., Papiro G., *Risk Analysis Probability of Default: A Stochastic Simulation Model*, Draft, 2014.

            Vedi `overview.md` per la sintesi completa.
            """
        )


if __name__ == "__main__":
    main()
