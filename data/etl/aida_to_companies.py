"""ETL: export AIDA (data/real/20XX-ME.xlsx) -> CSV principali dello schema (data/).

I CSV in data/ sono il dataset PRINCIPALE della suite (dati reali AIDA); il dataset
sintetico per test/demo vive in data/synthetic/ (rigenerabile con
data/generators/seed_companies.py).

Regole concordate (v. data/mapping_iv_directive.md per il dettaglio voce per voce):
- valori AIDA in migliaia EUR -> convertiti in milioni (schema);
- outlier esclusi: societa' con immob. finanziarie > 10% dell'attivo in almeno un anno valido;
- immob. finanziarie residue (<=10%) incluse nel NFA;
- interest_expense = saldo negativo della gestione finanziaria (proxy, AIDA non separa gli oneri lordi);
- NWC ricavato come residuo NIC - NFA con NIC = PN + PFN, cosi' gli invarianti di
  common/invariants.py chiudono per costruzione (TFR/fondi restano impliciti nel NWC);
- target scelto casualmente (seed fisso) tra le societa' con panel 2020-2024 completo.

Uso:  python3 data/etl/aida_to_companies.py
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
REAL_DIR = REPO / "data" / "real"
OUT_DIR = REPO / "data"

YEARS = (2020, 2021, 2022, 2023, 2024)
THOUSANDS_TO_MILLIONS = 1_000.0
FIN_ASSETS_MAX_RATIO = 0.10      # decisione gruppo di lavoro 2026-07: outlier fuori campione
CORPORATE_TAX_RATE = 0.279       # IRES 24% + IRAP 3.9%
TARGET_SEED = 42

GICS_SECTOR = "Industrials"
GICS_SUB_INDUSTRY = "Metals Wholesale (ATECO 4672)"

# colonne AIDA identificate dalla prima riga dell'header (prima del newline)
COL = {
    "name": "Ragione sociale",
    "piva": "Partita IVA",
    "vdp": "TOT. VAL. DELLA PRODUZIONE",
    "revenues": "Ricavi vendite e prestazioni",
    "materie": "Materie prime e consumo",
    "var_materie": "Variazione materie",
    "servizi": "Servizi",
    "personale": "Totale costi del personale",
    "oneri_diversi": "Oneri diversi di gestione",
    "godimento": "Godimento beni di terzi",
    "ammortamenti": "TOT Ammortamenti e svalut.",
    "acc_rischi": "Accantonamenti per rischi",
    "acc_altri": "Altri accantonamenti",
    "saldo_finanziario": "TOTALE PROVENTI E ONERI FINANZIARI",
    "imposte": "Totale Imposte sul reddito correnti, differite e anticipate",
    "utile": "UTILE/PERDITA DI ESERCIZIO",
    "dipendenti": "Dipendenti",
    "attivo": "TOTALE ATTIVO",
    "pn": "TOTALE PATRIMONIO NETTO",
    "debiti_fin": "Debiti Finanziari",
    "liquidita": "TOT. DISPON. LIQUIDE",
    "att_fin_correnti": "TOTALE ATTIVITA' FINANZIARIE",
    "imm_immateriali": "TOTALE IMMOB. IMMATERIALI",
    "imm_materiali": "TOTALE IMMOB. MATERIALI",
    "imm_finanziarie": "TOTALE IMMOB. FINANZIARIE",
}

# macro Italia 2020-2024 — stime da fonti pubbliche (ISTAT, Banca d'Italia, ICE BofA
# BBB euro spread); MRP 5% come da paper Montesi/Papiro. Da raffinare se necessario.
MACRO_IT = [
    # year, gdp_real, inflation, gdp_nom_5y_avg, rf_10y, mrp, spread_bbb
    (2020, -0.090, -0.002, -0.001, 0.0115, 0.050, 0.016),
    (2021, 0.083, 0.019, 0.016, 0.0081, 0.050, 0.012),
    (2022, 0.040, 0.081, 0.025, 0.0317, 0.050, 0.022),
    (2023, 0.007, 0.057, 0.034, 0.0427, 0.050, 0.019),
    (2024, 0.007, 0.010, 0.038, 0.0370, 0.050, 0.015),
]

# beta unlevered Trading Companies & Distributors Europa (Damodaran, gen 2025)
BETA_UNLEVERED = 0.75
WEIBULL_DEFAULTS = dict(
    weibull_revenues_shape=2.0,
    weibull_opcosts_shape=3.5,
    weibull_nfa_shape=3.5,
    weibull_nwc_shape=3.0,
    autocorr_revenues=0.20,
    autocorr_opcosts=0.30,
    autocorr_nfa=0.50,
    autocorr_nwc=0.40,
    corr_sales_opcosts=-0.40,
    corr_nfa_opcosts=-0.20,
    corr_sales_nfa=0.20,
    corr_sales_nwc=-0.30,
)


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return re.sub(r"_+", "_", s)


def num(value) -> float:
    return float(value) if isinstance(value, (int, float)) else np.nan


def read_year(path: Path) -> pd.DataFrame:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Risultati"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    header = [str(c).split("\n")[0].strip() if c else "" for c in rows[0]]
    idx: dict[str, int] = {}
    for key, label in COL.items():
        idx[key] = header.index(label)  # ValueError se il tracciato AIDA cambia
    records = []
    for row in rows[1:]:
        if not row[idx["name"]]:
            continue
        rec = {key: row[i] for key, i in idx.items()}
        records.append(rec)
    df = pd.DataFrame(records)
    for key in COL:
        if key not in ("name", "piva"):
            df[key] = df[key].map(num)
    df["piva"] = df["piva"].astype(str)
    return df


def build_companies() -> pd.DataFrame:
    frames = []
    for year in YEARS:
        df = read_year(REAL_DIR / f"{year}-ME.xlsx")
        df["fiscal_year"] = year
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)

    valid = (
        raw["revenues"].notna() & (raw["revenues"] > 0)
        & raw["attivo"].notna() & (raw["attivo"] > 0)
        & raw["pn"].notna()
    )
    raw = raw[valid].copy()

    # esclusione outlier: immob. finanziarie > 10% attivo in almeno un anno valido
    raw["fin_ratio"] = raw["imm_finanziarie"].fillna(0) / raw["attivo"]
    outliers = set(raw.loc[raw["fin_ratio"] > FIN_ASSETS_MAX_RATIO, "piva"])
    kept = raw[~raw["piva"].isin(outliers)].copy()
    print(f"righe valide: {len(raw)}  |  societa' escluse (immob.fin >10%): {len(outliers)}")

    k = THOUSANDS_TO_MILLIONS
    out = pd.DataFrame()
    out["piva"] = kept["piva"]
    out["company_name"] = kept["name"].astype(str).str.strip()
    out["fiscal_year"] = kept["fiscal_year"]

    out["revenues"] = kept["revenues"] / k
    opcost_items = (
        kept["materie"].fillna(0) + kept["var_materie"].fillna(0)
        + kept["servizi"].fillna(0) + kept["godimento"].fillna(0)
        + kept["personale"].fillna(0) + kept["oneri_diversi"].fillna(0)
    )
    ebitda = (kept["vdp"].fillna(kept["revenues"]) - opcost_items) / k
    out["ebitda"] = ebitda
    out["operating_costs"] = out["revenues"] - out["ebitda"]
    out["depreciation_amortization"] = (
        kept["ammortamenti"].fillna(0) + kept["acc_rischi"].fillna(0) + kept["acc_altri"].fillna(0)
    ) / k
    out["ebit"] = out["ebitda"] - out["depreciation_amortization"]
    out["interest_expense"] = (-kept["saldo_finanziario"].fillna(0)).clip(lower=0) / k + 0.0
    out["taxes"] = kept["imposte"].fillna(0) / k
    out["net_income"] = kept["utile"].fillna(0) / k
    out["pre_tax_income"] = out["net_income"] + out["taxes"]

    eff_rate = np.where(
        out["pre_tax_income"] > 0,
        (out["taxes"] / out["pre_tax_income"]).clip(0, 0.60),
        CORPORATE_TAX_RATE,
    )
    out["nopat"] = out["ebit"] * (1 - eff_rate)

    out["total_assets"] = kept["attivo"] / k
    out["equity"] = kept["pn"] / k
    out["gross_debt"] = kept["debiti_fin"].fillna(0) / k
    out["cash"] = (kept["liquidita"].fillna(0) + kept["att_fin_correnti"].fillna(0)) / k
    out["net_debt"] = out["gross_debt"] - out["cash"]
    out["net_fixed_assets"] = (
        kept["imm_immateriali"].fillna(0) + kept["imm_materiali"].fillna(0)
        + kept["imm_finanziarie"].fillna(0)
    ) / k
    out["net_invested_capital"] = out["equity"] + out["net_debt"]
    out["net_working_capital"] = out["net_invested_capital"] - out["net_fixed_assets"]
    out["employees"] = kept["dipendenti"].round().astype("Int64")

    # capex = delta NFA + D&A; primo anno disponibile: proxy manutentivo = D&A
    out = out.sort_values(["piva", "fiscal_year"]).reset_index(drop=True)
    delta_nfa = out.groupby("piva")["net_fixed_assets"].diff()
    out["capex"] = delta_nfa + out["depreciation_amortization"]
    out["capex"] = out["capex"].fillna(out["depreciation_amortization"])

    # costo del debito: oneri finanziari (proxy) / debito lordo; fallback rf + spread BBB
    macro = {y: rf + sp for y, _, _, _, rf, _, sp in MACRO_IT}
    fallback = out["fiscal_year"].map(macro)
    ratio = np.where(out["gross_debt"] > 0.05, out["interest_expense"] / out["gross_debt"], np.nan)
    out["cost_of_debt"] = pd.Series(ratio, index=out.index).clip(0.0, 0.15).fillna(fallback)

    out["corporate_tax_rate"] = CORPORATE_TAX_RATE
    out["country"] = "IT"
    out["currency"] = "EUR"
    out["gics_sector"] = GICS_SECTOR
    out["gics_sub_industry"] = GICS_SUB_INDUSTRY
    out["data_source"] = "aida"

    # company_id univoco: slug ragione sociale (+ suffisso P.IVA in caso di collisione)
    id_map = {}
    for piva, name in out.drop_duplicates("piva")[["piva", "company_name"]].itertuples(index=False):
        slug = slugify(name)
        if slug in id_map.values():
            slug = f"{slug}_{piva[-4:]}"
        id_map[piva] = slug
    out["company_id"] = out["piva"].map(id_map)

    # target casuale (seed fisso) tra le societa' con panel completo
    counts = out.groupby("piva")["fiscal_year"].nunique()
    complete = sorted(counts[counts == len(YEARS)].index)
    rng = np.random.default_rng(TARGET_SEED)
    target_piva = rng.choice(complete)
    out["is_target"] = (out["piva"] == target_piva).astype(int)
    print(f"societa' con panel completo {YEARS[0]}-{YEARS[-1]}: {len(complete)}")
    print(f"TARGET (seed={TARGET_SEED}): {id_map[target_piva]}  (P.IVA {target_piva})")

    cols = [
        "company_id", "company_name", "is_target", "country", "currency",
        "gics_sector", "gics_sub_industry", "fiscal_year",
        "revenues", "operating_costs", "ebitda", "depreciation_amortization", "ebit",
        "interest_expense", "pre_tax_income", "taxes", "net_income", "nopat",
        "net_fixed_assets", "net_working_capital", "net_invested_capital",
        "gross_debt", "cash", "net_debt", "equity", "total_assets",
        "capex", "cost_of_debt", "corporate_tax_rate", "employees", "data_source",
    ]
    out = out[cols].sort_values(["company_id", "fiscal_year"]).reset_index(drop=True)
    money_cols = [c for c in cols if c not in
                  ("company_id", "company_name", "is_target", "country", "currency",
                   "gics_sector", "gics_sub_industry", "fiscal_year", "employees", "data_source")]
    out[money_cols] = out[money_cols].round(6)
    return out


def build_sectors() -> pd.DataFrame:
    return pd.DataFrame([{
        "gics_sector": GICS_SECTOR,
        "gics_sub_industry": GICS_SUB_INDUSTRY,
        "beta_unlevered": BETA_UNLEVERED,
        **WEIBULL_DEFAULTS,
    }])


def build_macro() -> pd.DataFrame:
    return pd.DataFrame(
        MACRO_IT,
        columns=["year", "gdp_real_growth", "inflation_rate", "gdp_nominal_growth_5y_avg",
                 "risk_free_rate_10y", "market_risk_premium", "credit_spread_bbb"],
    ).assign(country="IT")[
        ["country", "year", "gdp_real_growth", "inflation_rate", "gdp_nominal_growth_5y_avg",
         "risk_free_rate_10y", "market_risk_premium", "credit_spread_bbb"]
    ]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    companies = build_companies()
    companies.to_csv(OUT_DIR / "companies.csv", index=False)
    build_sectors().to_csv(OUT_DIR / "sectors.csv", index=False)
    build_macro().to_csv(OUT_DIR / "macro.csv", index=False)
    print(f"scritti {len(companies)} record in {OUT_DIR}")


if __name__ == "__main__":
    main()
