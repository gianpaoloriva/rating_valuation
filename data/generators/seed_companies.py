"""
Fake data generator for companies.csv — deterministic test fixture.

Produces a realistic dataset for the Italian Industrial Machinery sector:
15 sample companies + 1 target (Riva Meccanica SpA), 3 years each (2022-2024).

Numbers are internally consistent:
    ebitda == revenues - operating_costs
    ebit == ebitda - da
    nic == nfa + nwc
    net_debt == gross_debt - cash
    equity == nic - net_debt  (financial equilibrium)
    nopat == ebit * (1 - tax_rate)

Run:
    python3 data/generators/seed_companies.py
Output:
    data/companies.csv
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, asdict
from pathlib import Path

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

SEED = 20260408
YEARS = [2022, 2023, 2024]
COUNTRY = "IT"
CURRENCY = "EUR"
GICS_SECTOR = "Industrials"
GICS_SUB_INDUSTRY = "Industrial Machinery"
CORPORATE_TAX_RATE = 0.28  # IRES 24% + IRAP ~3.9% semplificato
COST_OF_DEBT = 0.045

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "companies.csv"


# -----------------------------------------------------------------------------
# Company archetypes (base parameters in year 2022)
# -----------------------------------------------------------------------------

@dataclass
class Archetype:
    company_id: str
    company_name: str
    is_target: int
    base_revenues: float          # 2022 revenues, EUR M
    revenue_growth: float         # annual YoY growth rate
    ebitda_margin: float          # EBITDA / Revenues
    da_pct: float                 # D&A / Revenues
    nfa_pct: float                # NFA / Revenues
    nwc_pct: float                # NWC / Revenues
    debt_to_nic: float            # gross_debt / NIC
    cash_pct: float               # Cash / Revenues
    employees_base: int


ARCHETYPES: list[Archetype] = [
    # --- Sample companies (sector peers) --------------------------------------
    Archetype("mec_alpha", "MecAlpha SpA", 0,
              base_revenues=94.0, revenue_growth=0.040,
              ebitda_margin=0.155, da_pct=0.050,
              nfa_pct=0.400, nwc_pct=0.220,
              debt_to_nic=0.420, cash_pct=0.050, employees_base=420),
    Archetype("tecnomec", "TecnoMec Industriale Srl", 0,
              base_revenues=81.0, revenue_growth=0.048,
              ebitda_margin=0.145, da_pct=0.048,
              nfa_pct=0.380, nwc_pct=0.235,
              debt_to_nic=0.380, cash_pct=0.055, employees_base=360),
    Archetype("lombardia_mach", "Lombardia Machinery SpA", 0,
              base_revenues=73.0, revenue_growth=0.032,
              ebitda_margin=0.135, da_pct=0.052,
              nfa_pct=0.420, nwc_pct=0.245,
              debt_to_nic=0.450, cash_pct=0.040, employees_base=325),
    Archetype("nordest_eng", "NordEst Engineering Srl", 0,
              base_revenues=66.0, revenue_growth=0.058,
              ebitda_margin=0.170, da_pct=0.055,
              nfa_pct=0.410, nwc_pct=0.200,
              debt_to_nic=0.360, cash_pct=0.065, employees_base=280),
    Archetype("precisione_mec", "PrecisioneMec SpA", 0,
              base_revenues=59.0, revenue_growth=0.042,
              ebitda_margin=0.150, da_pct=0.050,
              nfa_pct=0.395, nwc_pct=0.230,
              debt_to_nic=0.400, cash_pct=0.050, employees_base=255),
    Archetype("automa_ita", "AutomaIta Srl", 0,
              base_revenues=54.0, revenue_growth=0.050,
              ebitda_margin=0.120, da_pct=0.045,
              nfa_pct=0.360, nwc_pct=0.260,
              debt_to_nic=0.430, cash_pct=0.045, employees_base=240),
    Archetype("veneto_ind", "Veneto Industrial Group SpA", 0,
              base_revenues=47.0, revenue_growth=0.038,
              ebitda_margin=0.135, da_pct=0.050,
              nfa_pct=0.400, nwc_pct=0.225,
              debt_to_nic=0.400, cash_pct=0.050, employees_base=210),
    Archetype("bresciana_mach", "Bresciana Macchine SpA", 0,
              base_revenues=42.0, revenue_growth=0.030,
              ebitda_margin=0.160, da_pct=0.055,
              nfa_pct=0.430, nwc_pct=0.215,
              debt_to_nic=0.370, cash_pct=0.055, employees_base=185),
    Archetype("emilia_tech", "Emilia Tech Srl", 0,
              base_revenues=37.0, revenue_growth=0.052,
              ebitda_margin=0.148, da_pct=0.048,
              nfa_pct=0.385, nwc_pct=0.235,
              debt_to_nic=0.410, cash_pct=0.045, employees_base=165),
    Archetype("toscana_mecc", "Toscana Mecc SpA", 0,
              base_revenues=34.0, revenue_growth=0.035,
              ebitda_margin=0.130, da_pct=0.050,
              nfa_pct=0.405, nwc_pct=0.250,
              debt_to_nic=0.460, cash_pct=0.040, employees_base=150),
    Archetype("industria_nord", "Industria Nord Srl", 0,
              base_revenues=30.0, revenue_growth=0.045,
              ebitda_margin=0.122, da_pct=0.045,
              nfa_pct=0.370, nwc_pct=0.240,
              debt_to_nic=0.440, cash_pct=0.045, employees_base=135),
    Archetype("alfamec", "AlfaMec SpA", 0,
              base_revenues=27.0, revenue_growth=0.060,
              ebitda_margin=0.158, da_pct=0.052,
              nfa_pct=0.395, nwc_pct=0.220,
              debt_to_nic=0.380, cash_pct=0.055, employees_base=120),
    Archetype("betamec", "BetaMec Srl", 0,
              base_revenues=24.0, revenue_growth=0.038,
              ebitda_margin=0.140, da_pct=0.050,
              nfa_pct=0.400, nwc_pct=0.230,
              debt_to_nic=0.415, cash_pct=0.050, employees_base=105),
    Archetype("gammamec", "GammaMec SpA", 0,
              base_revenues=21.0, revenue_growth=0.028,
              ebitda_margin=0.125, da_pct=0.048,
              nfa_pct=0.380, nwc_pct=0.245,
              debt_to_nic=0.445, cash_pct=0.040, employees_base=95),
    Archetype("deltamec", "DeltaMec Industriale Srl", 0,
              base_revenues=19.0, revenue_growth=0.050,
              ebitda_margin=0.148, da_pct=0.055,
              nfa_pct=0.415, nwc_pct=0.225,
              debt_to_nic=0.395, cash_pct=0.050, employees_base=85),

    # --- Target company -------------------------------------------------------
    # Riva Meccanica: media dimensione, margine leggermente sopra-media,
    # crescita sopra-media, leva sotto-media  ->  target interessante per
    # l'analisi differenziale vs IMS.
    Archetype("riva_meccanica", "Riva Meccanica SpA", 1,
              base_revenues=48.0, revenue_growth=0.068,
              ebitda_margin=0.175, da_pct=0.050,
              nfa_pct=0.405, nwc_pct=0.215,
              debt_to_nic=0.340, cash_pct=0.060, employees_base=215),
]


# -----------------------------------------------------------------------------
# Row builder
# -----------------------------------------------------------------------------

CSV_FIELDS = [
    "company_id",
    "company_name",
    "is_target",
    "country",
    "currency",
    "gics_sector",
    "gics_sub_industry",
    "fiscal_year",
    "revenues",
    "operating_costs",
    "ebitda",
    "depreciation_amortization",
    "ebit",
    "interest_expense",
    "pre_tax_income",
    "taxes",
    "net_income",
    "nopat",
    "net_fixed_assets",
    "net_working_capital",
    "net_invested_capital",
    "gross_debt",
    "cash",
    "net_debt",
    "equity",
    "total_assets",
    "capex",
    "cost_of_debt",
    "corporate_tax_rate",
    "employees",
]


def _round(x: float, decimals: int = 3) -> float:
    return round(x, decimals)


def build_row(arc: Archetype, year: int, prev_nfa: float | None, rng: random.Random) -> dict:
    year_index = year - YEARS[0]

    # --- noise to make years/companies slightly less mechanical ---------------
    growth_noise = rng.uniform(-0.005, 0.005)
    margin_noise = rng.uniform(-0.005, 0.005)
    nfa_noise = rng.uniform(-0.010, 0.010)
    nwc_noise = rng.uniform(-0.010, 0.010)

    revenues = arc.base_revenues * (1 + arc.revenue_growth + growth_noise) ** year_index
    ebitda_margin = arc.ebitda_margin + margin_noise
    ebitda = revenues * ebitda_margin
    operating_costs = revenues - ebitda
    da = revenues * arc.da_pct
    ebit = ebitda - da

    nfa = revenues * (arc.nfa_pct + nfa_noise)
    nwc = revenues * (arc.nwc_pct + nwc_noise)
    nic = nfa + nwc

    gross_debt = nic * arc.debt_to_nic
    cash = revenues * arc.cash_pct
    net_debt = gross_debt - cash

    interest_expense = gross_debt * COST_OF_DEBT
    pre_tax_income = ebit - interest_expense
    taxes = pre_tax_income * CORPORATE_TAX_RATE
    net_income = pre_tax_income - taxes
    nopat = ebit * (1 - CORPORATE_TAX_RATE)

    equity = nic - net_debt
    total_assets = nfa + nwc + cash  # riclassificato semplificato

    if prev_nfa is None:
        capex = da  # steady state assumption for first year
    else:
        capex = da + (nfa - prev_nfa)

    employees = int(round(arc.employees_base * (1 + arc.revenue_growth) ** year_index))

    return {
        "company_id": arc.company_id,
        "company_name": arc.company_name,
        "is_target": arc.is_target,
        "country": COUNTRY,
        "currency": CURRENCY,
        "gics_sector": GICS_SECTOR,
        "gics_sub_industry": GICS_SUB_INDUSTRY,
        "fiscal_year": year,
        "revenues": _round(revenues),
        "operating_costs": _round(operating_costs),
        "ebitda": _round(ebitda),
        "depreciation_amortization": _round(da),
        "ebit": _round(ebit),
        "interest_expense": _round(interest_expense),
        "pre_tax_income": _round(pre_tax_income),
        "taxes": _round(taxes),
        "net_income": _round(net_income),
        "nopat": _round(nopat),
        "net_fixed_assets": _round(nfa),
        "net_working_capital": _round(nwc),
        "net_invested_capital": _round(nic),
        "gross_debt": _round(gross_debt),
        "cash": _round(cash),
        "net_debt": _round(net_debt),
        "equity": _round(equity),
        "total_assets": _round(total_assets),
        "capex": _round(capex),
        "cost_of_debt": COST_OF_DEBT,
        "corporate_tax_rate": CORPORATE_TAX_RATE,
        "employees": employees,
    }, nfa


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> None:
    rng = random.Random(SEED)

    rows: list[dict] = []
    for arc in ARCHETYPES:
        prev_nfa: float | None = None
        for year in YEARS:
            row, prev_nfa = build_row(arc, year, prev_nfa, rng)
            rows.append(row)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows for {len(ARCHETYPES)} companies to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
