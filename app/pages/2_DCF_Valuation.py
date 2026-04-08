"""Streamlit page 2 — DCF valuation with coherence checks."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
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
from rating_valuation.common.financial import WACCInputs, wacc_after_tax
from rating_valuation.dcf import (
    Severity,
    check_coherence,
    value_three_stage,
    value_two_stage_coherent,
)
from rating_valuation.dcf.three_stage import ThreeStageInputs

st.set_page_config(page_title="DCF Valuation", page_icon="💰", layout="wide")


def _severity_badge(severity: Severity) -> str:
    if severity == Severity.PASS:
        return "✅ PASS"
    if severity == Severity.WARNING:
        return "⚠️ WARNING"
    return "❌ ERROR"


def main() -> None:
    page_header(
        "DCF Valuation",
        subtitle="Valutazione DCF a 2 / 3 stadi con Terminal Value coerente e validatore automatico",
        icon="💰",
    )
    bundle = load_bundle()

    # ------------------------------------------------------------------
    # Sidebar: target selection + parameters
    # ------------------------------------------------------------------
    st.sidebar.header("Target")
    sub_industry = sector_selector(bundle, key="dcf_sector")
    year = year_selector(bundle, sub_industry, key="dcf_year")
    target = target_selector(bundle, sub_industry, year, key="dcf_target")

    st.sidebar.header("Parametri DCF")
    model = st.sidebar.radio("Modello", ["2 stadi (coerente)", "3 stadi con convergenza"])
    explicit_years = st.sidebar.slider("Anni di previsione esplicita", 3, 10, 5)
    g_explicit = st.sidebar.slider(
        "Crescita esplicita (%)", 0.0, 15.0, 6.0, step=0.5
    ) / 100.0
    g_terminal = st.sidebar.slider(
        "g lungo periodo (%)", 0.0, 5.0, 2.5, step=0.1
    ) / 100.0

    if model.startswith("3 stadi"):
        n_convergence = st.sidebar.slider("Anni di convergenza", 3, 10, 5)
        roic_start = st.sidebar.slider(
            "ROIC marginale iniziale stadio 2 (%)", 5.0, 40.0, 18.0, step=0.5
        ) / 100.0
        g_stage2 = st.sidebar.slider(
            "Crescita NOPAT stadio 2 (%)", 0.0, 10.0, 4.0, step=0.1
        ) / 100.0

    # ------------------------------------------------------------------
    # Derive WACC
    # ------------------------------------------------------------------
    macro_row = bundle.macro[
        (bundle.macro["country"] == target["country"])
        & (bundle.macro["year"] == int(target["fiscal_year"]))
    ]
    if macro_row.empty:
        st.error(f"Dati macro assenti per {target['country']}/{target['fiscal_year']}")
        return
    macro = macro_row.iloc[0]

    sector_row = bundle.sectors[bundle.sectors["gics_sub_industry"] == sub_industry]
    if sector_row.empty:
        st.error(f"Parametri di settore assenti per {sub_industry}")
        return
    sector = sector_row.iloc[0]

    equity = float(target["equity"])
    debt = float(target["gross_debt"])
    de_ratio = debt / equity if equity > 0 else 0.0
    wacc_inputs = WACCInputs(
        risk_free_rate=float(macro["risk_free_rate_10y"]),
        market_risk_premium=float(macro["market_risk_premium"]),
        beta_unlevered=float(sector["beta_unlevered"]),
        target_debt_to_equity=de_ratio,
        cost_of_debt_pretax=float(target["cost_of_debt"]),
        tax_rate=float(target["corporate_tax_rate"]),
    )
    wacc = wacc_after_tax(wacc_inputs)

    st.subheader(f"Target: {target['company_name']} ({sub_industry}, FY{year})")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fatturato", fmt_money(target["revenues"]))
    c2.metric("NOPAT", fmt_money(target["nopat"]))
    c3.metric("Net Debt", fmt_money(target["net_debt"]))
    c4.metric("WACC after-tax", f"{wacc * 100:.2f}%")

    # ------------------------------------------------------------------
    # Build projections
    # ------------------------------------------------------------------
    nopat_0 = float(target["nopat"])
    fcff_explicit = [
        nopat_0 * (1 + g_explicit) ** (t + 1) * 0.70  # crude FCFF proxy
        for t in range(explicit_years)
    ]
    nopat_t_plus_1 = nopat_0 * (1 + g_explicit) ** (explicit_years + 1)

    # ------------------------------------------------------------------
    # Run valuation
    # ------------------------------------------------------------------
    if model.startswith("2 stadi"):
        roic_ni = wacc  # coherent steady-state assumption
        result = value_two_stage_coherent(
            fcff_explicit=fcff_explicit,
            nopat_t_plus_1=nopat_t_plus_1,
            wacc=wacc,
            terminal_growth=g_terminal,
            roic_new_investments=roic_ni,
            net_debt_today=float(target["net_debt"]),
        )
        ev_components = {
            "PV esplicito": result.explicit_pv,
            "PV stadio convergenza": 0.0,
            "TV scontato": result.terminal_value_pv,
        }
        implied_reinvestment = g_terminal / roic_ni if roic_ni else 0.0
        roic_marginal_final = roic_ni
        explicit_table = None
    else:
        inputs = ThreeStageInputs(
            fcff_explicit=tuple(fcff_explicit),
            nopat_at_t1=nopat_0 * (1 + g_explicit) ** explicit_years,
            wacc=wacc,
            n_convergence_years=n_convergence,
            roic_marginal_start=roic_start,
            growth_stage2=g_stage2,
            terminal_growth=g_terminal,
            net_debt_today=float(target["net_debt"]),
        )
        result_3s = value_three_stage(inputs)
        result = result_3s
        ev_components = {
            "PV esplicito": result_3s.explicit_pv,
            "PV stadio convergenza": result_3s.convergence_pv,
            "TV scontato": result_3s.terminal_value_pv,
        }
        implied_reinvestment = g_terminal / wacc  # steady state
        roic_marginal_final = wacc
        explicit_table = pd.DataFrame([
            {
                "anno": f.year_index,
                "stadio": f.stage,
                "nopat": f.nopat,
                "roic_marginale": f.roic_marginal,
                "reinvestment_h": f.reinvestment_rate,
                "operating_cash_flow": f.operating_cash_flow,
                "discount_factor": f.discount_factor,
                "pv": f.present_value,
            }
            for f in result_3s.flows
        ])

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    st.subheader("Risultati")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Enterprise Value", fmt_money(result.enterprise_value))
    c2.metric("Equity Value", fmt_money(result.equity_value))
    c3.metric("TV weight", f"{result.tv_weight * 100:.1f}%")
    c4.metric("WACC", f"{wacc * 100:.2f}%")

    # EV decomposition waterfall
    waterfall_df = pd.DataFrame(
        {"componente": list(ev_components.keys()), "valore": list(ev_components.values())}
    )
    fig = go.Figure(
        go.Bar(
            x=waterfall_df["componente"],
            y=waterfall_df["valore"],
            text=[f"{v:,.1f}" for v in waterfall_df["valore"]],
            textposition="auto",
            marker_color=["#2E86AB", "#A23B72", "#F18F01"],
        )
    )
    fig.update_layout(
        title="Scomposizione dell'Enterprise Value",
        yaxis_title="EUR M",
    )
    st.plotly_chart(fig, use_container_width=True)

    if explicit_table is not None:
        st.markdown("#### Dettaglio flussi stadio per stadio")
        st.dataframe(
            explicit_table.style.format(
                {
                    "nopat": "{:,.2f}",
                    "roic_marginale": "{:.2%}",
                    "reinvestment_h": "{:.2%}",
                    "operating_cash_flow": "{:,.2f}",
                    "discount_factor": "{:.4f}",
                    "pv": "{:,.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    # ------------------------------------------------------------------
    # Coherence check
    # ------------------------------------------------------------------
    st.subheader("Validatore coerenza Terminal Value")
    report = check_coherence(
        wacc=wacc,
        growth=g_terminal,
        roic_new_investments=roic_marginal_final,
        implied_reinvestment=implied_reinvestment,
        tv_weight=result.tv_weight,
        roic_marginal_final=roic_marginal_final,
        nopat_t_plus_1=nopat_t_plus_1,
        gdp_nominal_5y_avg=float(macro["gdp_nominal_growth_5y_avg"]),
        used_coherent_formula=True,
        inflation=float(macro["inflation_rate"]),
    )

    checks_df = pd.DataFrame(
        [
            {
                "Code": c.code,
                "Check": c.name,
                "Esito": _severity_badge(c.severity),
                "Dettaglio": c.message,
            }
            for c in report.checks
        ]
    )
    st.dataframe(checks_df, use_container_width=True, hide_index=True)

    verdict = report.verdict
    if verdict == Severity.PASS:
        st.success("Verdict: PASS — tutti i check di coerenza rispettati")
    elif verdict == Severity.WARNING:
        st.warning("Verdict: WARNING — da rivedere ma utilizzabile con cautela")
    else:
        st.error("Verdict: ERROR — valutazione incoerente, non utilizzare")


main()
