# Mapping bilancio IV Direttiva (export AIDA) → schema `companies.csv`

Documenta la riclassificazione applicata da `data/etl/aida_to_companies.py` ai file
`data/real/20XX-ME.xlsx` (export AIDA, foglio `Risultati`, valori in migliaia EUR).
Output: `data/companies.csv` + `sectors.csv` + `macro.csv` — il **dataset principale**
della suite (milioni EUR, schema di `data/schema.md`).

## Campione

- Fonte: AIDA (BvD), ATECO 4672 — commercio all'ingrosso di metalli; ricavi 2024 5–20 M€;
  Piemonte, Lombardia, Veneto, Liguria, Emilia-Romagna, Toscana. 320 società, esercizi 2020–2024.
- Righe scartate se prive di ricavi, totale attivo o patrimonio netto (bilanci non depositati).
- **Esclusione outlier (decisione gruppo di lavoro, lug 2026)**: società con
  `immobilizzazioni finanziarie / totale attivo > 10%` in almeno un anno valido → 43 società
  escluse, campione finale 277. Per le rimanenti le immobilizzazioni finanziarie (marginali)
  restano nel capitale investito (NFA).
- Target: `metal_d_s_r_l` (METAL D S.R.L.), scelto il 2026-07-21 via `--target` come società più
  vicina alle mediane di settore (EBITDA/NWC positivi tutti gli anni, debito materiale). In
  assenza di `--target` l'ETL estrae casualmente con seed 42 tra i panel completi (la vecchia
  estrazione dava `trafer_spa`, di fatto un broker, scartato perché non rappresentativo).

## Conto economico

| Campo schema | Voci AIDA | Note |
|---|---|---|
| `revenues` | Ricavi vendite e prestazioni | A1 |
| `ebitda` | Tot. valore produzione − (Materie prime + Variazione materie + Servizi + Godimento beni di terzi + Costi del personale + Oneri diversi di gestione) | include quindi A2–A5 (var. rimanenze prodotti, altri ricavi) nel margine |
| `operating_costs` | `revenues − ebitda` | per costruzione (convenzione schema) |
| `depreciation_amortization` | Tot. ammortamenti e svalutazioni + Accantonamenti per rischi + Altri accantonamenti | B12/B13 assimilati a poste valutative sotto l'EBITDA |
| `ebit` | `ebitda − depreciation_amortization` | |
| `interest_expense` | `max(0, −Saldo proventi e oneri finanziari)` | **proxy**: AIDA non espone gli oneri C.17 lordi; il saldo netta i proventi |
| `pre_tax_income` | Utile/perdita + Imposte | valore effettivo (non il semplificato `ebit − interest`) |
| `taxes`, `net_income` | voci dirette | |
| `nopat` | `ebit × (1 − aliquota effettiva)` | effettiva = imposte/pre-tax se pre-tax > 0 (cap 60%), altrimenti 27,9% |

Rettifiche di attività finanziarie e gestione straordinaria non entrano in EBITDA/EBIT;
restano implicite nella differenza tra `ebit − interest_expense` e il pre-tax effettivo.

## Stato patrimoniale riclassificato

| Campo schema | Voci AIDA | Note |
|---|---|---|
| `total_assets` | Totale attivo | contabile |
| `equity` | Totale patrimonio netto | contabile |
| `gross_debt` | Debiti finanziari | |
| `cash` | Disponibilità liquide + Totale attività finanziarie (C.III) | C.III include la tesoreria accentrata (verificato: mai doppio conteggio) |
| `net_debt` | `gross_debt − cash` | |
| `net_fixed_assets` | Immob. immateriali + materiali + finanziarie | finanziarie ≤ 10% attivo per costruzione del campione |
| `net_invested_capital` | `equity + net_debt` | dal lato delle fonti |
| `net_working_capital` | `net_invested_capital − net_fixed_assets` | **residuo**: equivale a rimanenze + crediti + ratei attivi − debiti operativi − ratei passivi − TFR e fondi. Garantisce gli invarianti di `common/invariants.py` per costruzione |

TFR e fondi rischi non sono esposti dall'export AIDA: restano impliciti (in riduzione) nel NWC.

## Flussi e altro

- `capex` = ΔNFA + D&A tra esercizi consecutivi; primo anno disponibile: proxy manutentivo = D&A.
- `cost_of_debt` = `interest_expense / gross_debt` (clip 0–15%); se debito ≈ 0, fallback
  `risk_free_10y + spread BBB` dell'anno da `macro.csv`.
- `corporate_tax_rate` = 0,279 (IRES 24% + IRAP 3,9%).
- `gics_sub_industry` = `Metals Wholesale (ATECO 4672)` — chiave coerente tra `companies.csv`
  e `sectors.csv` (il codice richiede solo coerenza della chiave, non la tassonomia GICS reale).
- `data_source` = `aida` (colonna aggiuntiva prevista da `data/schema.md` §5).

## Limiti noti

1. `interest_expense` è un saldo netto: sottostima gli oneri lordi per le società con
   proventi finanziari rilevanti; per ~metà del campione il saldo è positivo → oneri = 0.
2. Il simulatore Agentic Credit Risk richiede EBITDA margin atteso > 0: sulle società in
   perdita operativa (19 nel 2024) `from_company` solleva errore — filtrare a monte o
   parametrizzare manualmente.
3. Le stime macro IT 2020–2024 in `data/etl/aida_to_companies.py` (`MACRO_IT`) sono da
   fonti pubbliche approssimate; raffinare se servono valutazioni puntuali.
