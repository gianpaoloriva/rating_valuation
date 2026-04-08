"""Example 02 — Full end-to-end pipeline on Riva Meccanica SpA.

Runs the entire suite on the target company:

    1. BMS Industrial Machinery FY2024 (15 peers)
    2. Differential analysis target vs BMS
    3. DCF two-stage + coherence check (simple projection from BMS data)
    4. Agentic Credit Risk Monte Carlo with 5 000 trials over 3 years
    5. Rating assignment via master scale

Run:
    python3 examples/02_full_pipeline_riva_meccanica.py
"""

from __future__ import annotations

import pandas as pd

from rating_valuation.bms import BMSBuilder
from rating_valuation.common.data_loader import (
    load_all,
    peer_sample,
    target_row,
)
from rating_valuation.common.financial import WACCInputs, wacc_after_tax
from rating_valuation.dcf import (
    Severity,
    check_coherence,
    value_two_stage_coherent,
)
from rating_valuation.agentic_credit_risk import AgenticCreditRiskSimulator
from rating_valuation.differential import DifferentialAnalyzer
from rating_valuation.rating import RatingLookup


def _section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    pd.set_option("display.float_format", lambda x: f"{x:,.2f}")
    bundle = load_all()

    # -------------------------------------------------------------------
    # 1. BMS
    # -------------------------------------------------------------------
    peers = peer_sample(bundle.companies, "Industrial Machinery", fiscal_year=2024)
    bms = BMSBuilder(peers, min_sample_size=15).build()

    _section("1. BMS Industrial Machinery FY2024")
    print(f"Peer nel campione:             {bms.n_companies}")
    print(f"Fatturato medio:               {bms.average_revenues:>12,.2f} EUR M")
    print(f"EBITDA margin medio:           {bms.income_statement_shares['ebitda']*100:>11.2f}%")
    print(f"EBIT margin medio:             {bms.income_statement_shares['ebit']*100:>11.2f}%")
    print(f"NOPAT margin medio:            {bms.income_statement_shares['nopat']*100:>11.2f}%")
    print(f"NIC/Fatturato:                 {bms.balance_sheet['net_invested_capital']/bms.average_revenues*100:>11.2f}%")
    print(f"Leva D/TA:                     {bms.balance_sheet_shares['gross_debt']*100:>11.2f}%")

    # -------------------------------------------------------------------
    # 2. Differential analysis
    # -------------------------------------------------------------------
    target = target_row(bundle.companies, fiscal_year=2024).iloc[0]
    analyzer = DifferentialAnalyzer(bms)
    diff = analyzer.analyze(target)

    _section("2. Analisi Differenziale — Riva Meccanica vs BMS")
    print(diff.summary_line())
    print()
    df_diff = diff.as_dataframe()
    for _, row in df_diff.iterrows():
        if row["unit"] == "pct":
            t = f"{row['target']*100:>8.2f}%"
            b = f"{row['bms']*100:>8.2f}%"
            d = f"{row['delta']*100:+7.2f} p.p."
        elif row["unit"] == "ratio":
            t = f"{row['target']:>8.3f}"
            b = f"{row['bms']:>8.3f}"
            d = f"{row['delta']:+7.3f}"
        else:
            t = f"{row['target']:>8.2f}"
            b = f"{row['bms']:>8.2f}"
            d = f"{row['delta']:+7.2f}"
        flag = "  [+]" if row["favorable"] else "  [-]"
        print(f"  {row['label']:<28} target={t}  BMS={b}  Δ={d}{flag}")
    print()
    print(f"Favorevoli: {diff.favorable_count()}/{len(diff.comparisons)}")

    # -------------------------------------------------------------------
    # 3. DCF two-stage with coherence check
    # -------------------------------------------------------------------
    _section("3. DCF Two-Stage + Terminal Value Coerente")
    # Projection: extend target's 2024 NOPAT for 5 years at 6% growth
    target_nopat_2024 = float(target["nopat"])
    explicit_growth = 0.06
    fcff_explicit = [
        target_nopat_2024 * (1 + explicit_growth) ** (t + 1) * 0.70  # crude FCFF proxy
        for t in range(5)
    ]
    nopat_t_plus_1 = target_nopat_2024 * (1 + explicit_growth) ** 6

    # WACC from sector + macro
    macro_2024 = bundle.macro[(bundle.macro["country"] == "IT") & (bundle.macro["year"] == 2024)].iloc[0]
    sector = bundle.sectors[bundle.sectors["gics_sub_industry"] == "Industrial Machinery"].iloc[0]
    wacc_inputs = WACCInputs(
        risk_free_rate=float(macro_2024["risk_free_rate_10y"]),
        market_risk_premium=float(macro_2024["market_risk_premium"]),
        beta_unlevered=float(sector["beta_unlevered"]),
        target_debt_to_equity=float(target["gross_debt"]) / float(target["equity"]),
        cost_of_debt_pretax=float(target["cost_of_debt"]),
        tax_rate=float(target["corporate_tax_rate"]),
    )
    wacc = wacc_after_tax(wacc_inputs)
    terminal_growth = 0.025
    roic_steady_state = wacc  # convergence: ROIC_NI = WACC

    dcf = value_two_stage_coherent(
        fcff_explicit=fcff_explicit,
        nopat_t_plus_1=nopat_t_plus_1,
        wacc=wacc,
        terminal_growth=terminal_growth,
        roic_new_investments=roic_steady_state,
        net_debt_today=float(target["net_debt"]),
    )
    print(f"WACC after-tax:                {wacc*100:>11.2f}%")
    print(f"Orizzonte esplicito:           5 anni @ g={explicit_growth*100:.1f}%")
    print(f"g lungo periodo:               {terminal_growth*100:>11.2f}%")
    print(f"PV esplicito:                  {dcf.explicit_pv:>12,.2f} EUR M")
    print(f"Terminal Value (T=5):          {dcf.terminal_value:>12,.2f} EUR M")
    print(f"TV scontato:                   {dcf.terminal_value_pv:>12,.2f} EUR M")
    print(f"Enterprise Value:              {dcf.enterprise_value:>12,.2f} EUR M")
    print(f"Equity Value:                  {dcf.equity_value:>12,.2f} EUR M")
    print(f"Peso TV su EV:                 {dcf.tv_weight*100:>11.1f}%")

    _section("3.b Coherence check (6 controlli)")
    # Reinvestment rate implied by explicit growth and steady-state ROIC
    implied_h = explicit_growth / roic_steady_state if roic_steady_state else 0.0
    # At steady state the implied h for the terminal_growth is what matters
    report = check_coherence(
        wacc=wacc,
        growth=terminal_growth,
        roic_new_investments=roic_steady_state,
        implied_reinvestment=terminal_growth / roic_steady_state if roic_steady_state else 0.0,
        tv_weight=dcf.tv_weight,
        roic_marginal_final=roic_steady_state,
        nopat_t_plus_1=nopat_t_plus_1,
        gdp_nominal_5y_avg=float(macro_2024["gdp_nominal_growth_5y_avg"]),
        used_coherent_formula=True,
        inflation=float(macro_2024["inflation_rate"]),
    )
    for c in report.checks:
        icon = "[OK]" if c.severity == Severity.PASS else (
            "[!]" if c.severity == Severity.WARNING else "[X]"
        )
        print(f"  {icon} {c.code}  {c.name:<45} {c.severity.value}")
    print(f"\nVerdict: {report.verdict.value}")

    # -------------------------------------------------------------------
    # 4. Agentic Credit Risk stochastic simulation
    # -------------------------------------------------------------------
    _section("4. Agentic Credit Risk Monte Carlo (5 000 trials, 3 anni)")
    sim = AgenticCreditRiskSimulator.from_company(
        target, bundle.sectors, bundle.macro,
        n_trials=5_000, n_years=3,
    )
    print(f"Pre-tax WACC:                  {sim.initial_state.wacc*100:>11.2f}%")
    print(f"NIC iniziale:                  {sim.initial_state.net_invested_capital:>12,.2f} EUR M")
    print(f"Debito iniziale:               {sim.initial_state.gross_debt:>12,.2f} EUR M")
    print(f"Cash iniziale:                 {sim.initial_state.cash:>12,.2f} EUR M")
    print(f"D&A / Fatturato:               {sim.initial_state.da_ratio*100:>11.2f}%")
    print()

    acr_result = sim.run(seed=42)
    acr_df = acr_result.as_dataframe()
    print("Evoluzione PD sull'orizzonte:")
    for _, row in acr_df.iterrows():
        print(
            f"  Anno {int(row['year_ahead'])}:"
            f"  YearlyFreq={row['yearly_default_frequency']*100:>6.2f}%"
            f"  Marginal={row['marginal_pd']*100:>6.2f}%"
            f"  Cumulata={row['cumulative_pd']*100:>6.2f}%"
        )
    print()

    m = acr_result.metrics
    print(f"Scenari di default:            {m.n_default_scenarios} / {sim.n_trials}")
    print(f"PD cumulata 3y:                {m.cumulative_pd[-1]*100:>11.2f}%")
    print(f"LGD media (€M):                {m.lgd_mean:>12,.2f}")
    print(f"LGD mediana (€M):              {m.lgd_median:>12,.2f}")
    print(f"Recovery rate medio:           {m.recovery_rate_mean*100:>11.2f}%")
    print(f"EAD media default (€M):        {m.ead_mean:>12,.2f}")
    print(f"Expected Loss (€M):            {m.expected_loss:>12,.2f}")
    print(f"UL 95% (€M):                   {m.unexpected_loss_95:>12,.2f}")
    print(f"UL 99% (€M):                   {m.unexpected_loss_99:>12,.2f}")

    # -------------------------------------------------------------------
    # 5. Rating assignment
    # -------------------------------------------------------------------
    _section("5. Rating implicito")
    lookup = RatingLookup.from_csv()
    rating = acr_result.implied_rating
    bracket = lookup.rating_of_pd_interpolated(float(m.cumulative_pd[-1]))
    print(f"PD cumulata 3y:                {m.cumulative_pd[-1]*100:.4f}%")
    print(f"Rating implicito:              {rating}")
    print(f"Posizionamento:                tra {bracket[0]} e {bracket[1]} (frazione {bracket[2]:.2f})")

    # -------------------------------------------------------------------
    # Final one-liner
    # -------------------------------------------------------------------
    _section("Sintesi")
    print(
        f"{target['company_name']} (FY2024, Industrial Machinery IT)\n"
        f"  Enterprise Value:   {dcf.enterprise_value:>10,.2f} EUR M\n"
        f"  Equity Value:       {dcf.equity_value:>10,.2f} EUR M\n"
        f"  PD cumulata 3y:     {m.cumulative_pd[-1]*100:>10.2f}%\n"
        f"  Rating:             {rating}\n"
        f"  Coerenza DCF:       {report.verdict.value}\n"
        f"  Posizionamento vs BMS: {diff.favorable_count()}/{len(diff.comparisons)} indicatori favorevoli"
    )


if __name__ == "__main__":
    main()
