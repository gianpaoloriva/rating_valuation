"""Streamlit page 4 — Agentic Credit Risk stochastic simulation."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app._common import (
    fmt_money,
    load_bundle,
    page_header,
    sector_selector,
    target_selector,
    year_selector,
)
from rating_valuation.agentic_credit_risk.simulator import AgenticCreditRiskSimulator

st.set_page_config(page_title="Agentic Credit Risk", page_icon="⚡", layout="wide")


def main() -> None:
    page_header(
        "Agentic Credit Risk",
        subtitle="Simulazione stocastica Monte Carlo della PD forward-looking (Montesi/Papiro 2014)",
        icon="⚡",
    )
    bundle = load_bundle()

    # ------------------------------------------------------------------
    # Sidebar — target + parameters
    # ------------------------------------------------------------------
    st.sidebar.header("Target")
    sub_industry = sector_selector(bundle, key="acr_sector")
    year = year_selector(bundle, sub_industry, key="acr_year")
    target = target_selector(bundle, sub_industry, year, key="acr_target")

    st.sidebar.header("Simulazione Monte Carlo")
    n_trials = st.sidebar.select_slider(
        "Numero trial", options=[1000, 2500, 5000, 10000, 20000], value=5000
    )
    n_years = st.sidebar.slider("Orizzonte (anni)", 1, 5, 3)
    seed = st.sidebar.number_input("Seed", value=42, step=1)

    st.sidebar.header("Stress delta (min distribuzioni)")
    rev_delta = st.sidebar.slider("Δ min crescita ricavi (p.p.)", 0.0, 20.0, 5.0) / 100.0
    margin_delta = st.sidebar.slider("Δ min EBITDA margin (p.p.)", 0.0, 15.0, 3.0) / 100.0
    nfa_delta = st.sidebar.slider("Δ min NFA/Fatturato (p.p.)", 0.0, 20.0, 8.0) / 100.0
    nwc_delta = st.sidebar.slider("Δ min NWC/Fatturato (p.p.)", 0.0, 15.0, 5.0) / 100.0

    run = st.sidebar.button("▶ Esegui simulazione", type="primary")

    # ------------------------------------------------------------------
    # Summary of the target
    # ------------------------------------------------------------------
    st.subheader(f"{target['company_name']} — {sub_industry} FY{year}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Fatturato", fmt_money(target["revenues"]))
    c2.metric("EBITDA margin", f"{target['ebitda'] / target['revenues'] * 100:.2f}%")
    c3.metric("Debito lordo", fmt_money(target["gross_debt"]))
    c4.metric("Cash", fmt_money(target["cash"]))
    c5.metric("Equity", fmt_money(target["equity"]))

    if not run:
        st.info("Configura i parametri nella sidebar e premi ▶ Esegui simulazione")
        return

    # ------------------------------------------------------------------
    # Run simulation
    # ------------------------------------------------------------------
    with st.spinner(f"Simulazione {n_trials:,} trial × {n_years} anni..."):
        simulator = AgenticCreditRiskSimulator.from_company(
            target,
            bundle.sectors,
            bundle.macro,
            revenue_growth_min_delta=rev_delta,
            margin_min_delta=margin_delta,
            nfa_min_delta=nfa_delta,
            nwc_min_delta=nwc_delta,
            n_trials=int(n_trials),
            n_years=int(n_years),
        )
        result = simulator.run(seed=int(seed))

    metrics = result.metrics

    # ------------------------------------------------------------------
    # KPI
    # ------------------------------------------------------------------
    st.markdown("### Risultato")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "PD cumulata finale",
        f"{metrics.cumulative_pd[-1] * 100:.2f}%",
    )
    c2.metric("Rating implicito", result.implied_rating or "N/A")
    c3.metric(
        "Scenari di default",
        f"{metrics.n_default_scenarios:,} / {n_trials:,}",
    )
    c4.metric(
        "LGD media",
        f"{metrics.lgd_mean:,.2f}",
    )

    # ------------------------------------------------------------------
    # PD evolution chart
    # ------------------------------------------------------------------
    st.markdown("### Evoluzione PD sull'orizzonte")
    pd_df = pd.DataFrame(
        {
            "anno": list(range(1, n_years + 1)),
            "yearly_freq": metrics.yearly_default_frequency * 100,
            "marginal": metrics.yearly_marginal_default * 100,
            "cumulata": metrics.cumulative_pd * 100,
        }
    )
    fig = go.Figure()
    fig.add_trace(go.Bar(x=pd_df["anno"], y=pd_df["marginal"], name="PD marginale"))
    fig.add_trace(go.Scatter(
        x=pd_df["anno"], y=pd_df["cumulata"],
        mode="lines+markers", name="PD cumulata", yaxis="y2"
    ))
    fig.update_layout(
        xaxis_title="Anno",
        yaxis=dict(title="PD marginale (%)"),
        yaxis2=dict(title="PD cumulata (%)", overlaying="y", side="right"),
        title="PD marginale e cumulata",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        result.as_dataframe().style.format(
            {
                "yearly_default_frequency": "{:.2%}",
                "marginal_pd": "{:.2%}",
                "cumulative_pd": "{:.2%}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ------------------------------------------------------------------
    # LGD / EL
    # ------------------------------------------------------------------
    st.markdown("### Perdita attesa e distribuzione LGD")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected Loss", fmt_money(metrics.expected_loss))
    c2.metric("UL 95%", fmt_money(metrics.unexpected_loss_95))
    c3.metric("UL 99%", fmt_money(metrics.unexpected_loss_99))
    c4.metric("Recovery rate", f"{metrics.recovery_rate_mean * 100:.2f}%")

    if metrics.n_default_scenarios > 0 and result.debt is not None:
        import numpy as np
        ev = result.ev
        debt = result.debt
        cash = result.cash_matrix
        default_mask = ev < (debt - cash)
        any_def = default_mask.any(axis=1)
        if any_def.any():
            first = default_mask.argmax(axis=1)
            trial_idx = np.where(any_def)[0]
            first_sel = first[trial_idx]
            ead = debt[trial_idx, first_sel]
            ev_sel = ev[trial_idx, first_sel]
            cash_sel = cash[trial_idx, first_sel]
            lgd_sample = np.maximum(0, ead - ev_sel - cash_sel)
            fig_h = px.histogram(
                pd.DataFrame({"LGD": lgd_sample}),
                x="LGD",
                nbins=40,
                title="Distribuzione LGD sugli scenari di default (EUR M)",
            )
            st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.success("Nessuno scenario di default osservato con i parametri correnti — target robusto.")

    # ------------------------------------------------------------------
    # Raw summary
    # ------------------------------------------------------------------
    with st.expander("Summary grezzo"):
        st.json(result.summary())


main()
