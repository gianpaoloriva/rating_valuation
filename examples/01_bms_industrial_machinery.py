"""Example 01 — Build a BMS for the Industrial Machinery sector.

Runs the BMSBuilder on the fake dataset (15 peers + 1 target, 3 years) and
prints:
  1. The BMS CE and SP for fiscal_year 2024
  2. The historical time series of BMS revenues and EBITDA margin
  3. A first-glance differential of the target (Riva Meccanica SpA) vs the BMS

Run:
    python3 examples/01_bms_industrial_machinery.py
"""

from __future__ import annotations

import pandas as pd

from rating_valuation.bms import BMSBuilder
from rating_valuation.bms.builder import build_bms_timeseries
from rating_valuation.common.data_loader import (
    load_companies,
    peer_sample,
    target_row,
)


def main() -> None:
    pd.set_option("display.float_format", lambda x: f"{x:,.2f}")

    companies = load_companies()

    # --- 1) BMS 2024 --------------------------------------------------------
    peers = peer_sample(companies, "Industrial Machinery", fiscal_year=2024)
    result = BMSBuilder(peers, min_sample_size=15).build()

    print("=" * 78)
    print(f"BMS Industrial Machinery — FY{result.fiscal_year}")
    print("=" * 78)
    print(f"Numero imprese nel campione:   {result.n_companies}")
    print(f"Fatturato medio:               {result.average_revenues:>12,.2f} EUR M")
    print(f"Totale attivo medio:           {result.average_total_assets:>12,.2f} EUR M")
    if result.below_min_sample:
        print(f"(!) Campione sotto la soglia di {result.min_sample_size} imprese "
              "(warning, non errore)")
    print()

    print("--- Conto Economico BMS (EUR M) ---")
    ce = pd.DataFrame(
        {
            "valore": result.income_statement.values,
            "% su fatturato": result.income_statement_shares.values,
        },
        index=result.income_statement.index,
    )
    ce["% su fatturato"] = ce["% su fatturato"].map(lambda x: f"{x*100:,.2f}%")
    print(ce.to_string())
    print()

    print("--- Stato Patrimoniale BMS (EUR M) ---")
    sp = pd.DataFrame(
        {
            "valore": result.balance_sheet.values,
            "% su totale attivo": result.balance_sheet_shares.values,
        },
        index=result.balance_sheet.index,
    )
    sp["% su totale attivo"] = sp["% su totale attivo"].map(lambda x: f"{x*100:,.2f}%")
    print(sp.to_string())
    print()

    # --- 2) Time series -----------------------------------------------------
    print("=" * 78)
    print("Serie storica BMS (2022-2024)")
    print("=" * 78)
    timeseries = build_bms_timeseries(
        companies, "Industrial Machinery", min_sample_size=15
    )
    ts_rows = []
    for year, r in sorted(timeseries.items()):
        ts_rows.append(
            {
                "anno": year,
                "n_imprese": r.n_companies,
                "fatturato_medio": r.average_revenues,
                "ebitda_margin": r.income_statement_shares["ebitda"],
                "ebit_margin": r.income_statement_shares["ebit"],
                "leva_D/TA": r.balance_sheet_shares["gross_debt"],
                "equity_on_TA": r.balance_sheet_shares["equity"],
            }
        )
    ts_df = pd.DataFrame(ts_rows).set_index("anno")
    for col in ("ebitda_margin", "ebit_margin", "leva_D/TA", "equity_on_TA"):
        ts_df[col] = ts_df[col].map(lambda x: f"{x*100:,.2f}%")
    print(ts_df.to_string())
    print()

    # --- 3) Differential (teaser) ------------------------------------------
    print("=" * 78)
    print("Differenziale target vs BMS (FY2024)")
    print("=" * 78)
    target = target_row(companies, fiscal_year=2024).iloc[0]

    def _margin(row: pd.Series, num: str, den: str) -> float:
        return float(row[num]) / float(row[den])

    def _bms_margin(num: str, den: str) -> float:
        if den == "revenues":
            return float(result.income_statement[num] / result.average_revenues)
        return float(result.balance_sheet[num] / result.average_total_assets)

    comparisons = [
        ("Fatturato (M)", float(target["revenues"]), result.average_revenues),
        ("EBITDA margin", _margin(target, "ebitda", "revenues"), _bms_margin("ebitda", "revenues")),
        ("EBIT margin", _margin(target, "ebit", "revenues"), _bms_margin("ebit", "revenues")),
        ("NOPAT margin", _margin(target, "nopat", "revenues"), _bms_margin("nopat", "revenues")),
        (
            "Debito/Attivo",
            float(target["gross_debt"]) / float(target["total_assets"]),
            _bms_margin("gross_debt", "total_assets"),
        ),
        (
            "Equity/Attivo",
            float(target["equity"]) / float(target["total_assets"]),
            _bms_margin("equity", "total_assets"),
        ),
    ]
    diff_df = pd.DataFrame(comparisons, columns=["indicatore", "target", "BMS"])
    diff_df["delta"] = diff_df["target"] - diff_df["BMS"]

    def _fmt(label: str, target_val: float, bms_val: float, delta_val: float) -> tuple:
        if "margin" in label or "/Attivo" in label:
            return (
                f"{target_val * 100:,.2f}%",
                f"{bms_val * 100:,.2f}%",
                f"{delta_val * 100:+.2f} p.p.",
            )
        return (f"{target_val:,.2f}", f"{bms_val:,.2f}", f"{delta_val:+,.2f}")

    formatted = pd.DataFrame(
        [
            dict(
                zip(
                    ("indicatore", "target", "BMS", "delta"),
                    (row["indicatore"], *_fmt(row["indicatore"], row["target"], row["BMS"], row["delta"])),
                )
            )
            for _, row in diff_df.iterrows()
        ]
    )
    print(formatted.to_string(index=False))
    print()
    print("Nota: l'analisi differenziale completa (attribuzione del valore alle "
          "singole leve) è implementata dal modulo differential, non ancora attivo.")


if __name__ == "__main__":
    main()
