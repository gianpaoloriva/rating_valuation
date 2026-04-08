# Data Schema

Questa cartella contiene tutti i dataset di input per gli strumenti di analisi descritti in `overview.md`. Il principio è: **una sola fonte di verità, CSV normalizzati con campi definiti**, in modo che BMS, DCF, RAPD e Rating Mapper leggano gli stessi dati senza duplicazioni.

Tutti i CSV usano:
- separatore: `,`
- encoding: `UTF-8`
- decimal separator: `.`
- valori mancanti: vuoto (no `NaN`, `NA`, `NULL`)
- date: anno fiscale come intero (`YYYY`)
- valori monetari: **milioni di unità nella colonna `currency`** (salvo diversa indicazione)
- percentuali e tassi: **decimali** (es. 0.28 = 28%)

---

## 1. `companies.csv` — Bilanci riclassificati

Una riga per **coppia (company, fiscal_year)**. Contiene il bilancio riclassificato gestionale necessario per tutti i tool.

| Campo | Tipo | Unità | Descrizione |
|---|---|---|---|
| `company_id` | string | — | Identificativo stabile (snake_case, no spazi) |
| `company_name` | string | — | Ragione sociale |
| `is_target` | int (0/1) | — | 1 = impresa obiettivo della valutazione; 0 = sample di settore |
| `country` | string | ISO-3166 α-2 | Codice paese |
| `currency` | string | ISO-4217 | Valuta (es. `EUR`, `USD`) |
| `gics_sector` | string | — | Settore GICS livello 1 |
| `gics_sub_industry` | string | — | Sotto-settore GICS livello 4 |
| `fiscal_year` | int | YYYY | Anno di bilancio |
| **Conto Economico** | | | |
| `revenues` | float | M cur | Ricavi netti (Fatturato) |
| `operating_costs` | float | M cur | Costi operativi (COGS + SG&A), **esclusi D&A** |
| `ebitda` | float | M cur | = `revenues − operating_costs` |
| `depreciation_amortization` | float | M cur | Ammortamenti e svalutazioni |
| `ebit` | float | M cur | = `ebitda − depreciation_amortization` |
| `interest_expense` | float | M cur | Oneri finanziari |
| `pre_tax_income` | float | M cur | = `ebit − interest_expense` (semplificato) |
| `taxes` | float | M cur | Imposte sul reddito |
| `net_income` | float | M cur | Utile netto |
| `nopat` | float | M cur | = `ebit × (1 − effective_tax_rate)` |
| **Stato Patrimoniale (riclassificato)** | | | |
| `net_fixed_assets` | float | M cur | Immobilizzazioni nette (NFA), incluso goodwill |
| `net_working_capital` | float | M cur | Capitale circolante netto operativo (NWC) |
| `net_invested_capital` | float | M cur | NIC = NFA + NWC |
| `gross_debt` | float | M cur | Debito finanziario lordo (short + long term) |
| `cash` | float | M cur | Cassa e equivalenti |
| `net_debt` | float | M cur | = `gross_debt − cash` |
| `equity` | float | M cur | Patrimonio netto |
| `total_assets` | float | M cur | Totale attivo contabile |
| **Flussi e altro** | | | |
| `capex` | float | M cur | Investimenti netti (uscite di cassa per immobilizzazioni) |
| `cost_of_debt` | float | decimale | Costo medio del debito lordo (`r_d`) |
| `corporate_tax_rate` | float | decimale | Aliquota fiscale nominale del paese |
| `employees` | int | — | Organico (fine anno), opzionale |

**Invarianti attese** (il generatore li soddisfa, i tool li verificano):
- `ebitda == revenues - operating_costs`
- `ebit == ebitda - depreciation_amortization`
- `net_invested_capital == net_fixed_assets + net_working_capital`
- `net_debt == gross_debt - cash`
- `nopat == ebit × (1 - corporate_tax_rate)` (approssimazione uniforme; per dati reali usare `effective_tax_rate = taxes/pre_tax_income`)
- `equity ≈ net_invested_capital − net_debt` (equilibrio di bilancio riclassificato)

**Nota sull'identificazione del target**: `is_target=1` marca l'impresa da valutare. Tutte le altre righe con `is_target=0` e stesso `gics_sub_industry` costituiscono il campione per il BMS.

---

## 2. `sectors.csv` — Parametri di settore

Una riga per **sotto-settore GICS**. Contiene i parametri per WACC settoriale e per la parametrizzazione delle distribuzioni stocastiche del RAPD.

| Campo | Tipo | Unità | Descrizione |
|---|---|---|---|
| `gics_sector` | string | — | Settore GICS livello 1 |
| `gics_sub_industry` | string | — | Sotto-settore GICS livello 4 (chiave) |
| `beta_unlevered` | float | — | Beta unlevered mediano del settore (per CAPM) |
| `weibull_revenues_shape` | float | — | Shape parameter Weibull per crescita ricavi (default RAPD: 2) |
| `weibull_opcosts_shape` | float | — | Shape per OpCost/Revenues (default RAPD: 3.5) |
| `weibull_nfa_shape` | float | — | Shape per NFA/Revenues (default RAPD: 3.5) |
| `weibull_nwc_shape` | float | — | Shape per NWC/Revenues (default RAPD: 3) |
| `autocorr_revenues` | float | — | Autocorrelazione anno-su-anno dei ricavi (default: 0.2) |
| `autocorr_opcosts` | float | — | Autocorrelazione OpCost/Sales (default: 0.3) |
| `autocorr_nfa` | float | — | Autocorrelazione NFA/Sales (default: 0.5) |
| `autocorr_nwc` | float | — | Autocorrelazione NWC/Sales (default: 0.4) |
| `corr_sales_opcosts` | float | — | Correlazione Sales × OpCost/Sales (default: −0.4) |
| `corr_nfa_opcosts` | float | — | Correlazione NFA/Sales × OpCost/Sales (default: −0.2) |
| `corr_sales_nfa` | float | — | Correlazione Sales × NFA/Sales (default: 0.2) |
| `corr_sales_nwc` | float | — | Correlazione Sales × NWC/Sales (default: −0.3) |

I valori di default sono presi dal paper RAPD, Appendice A (back-testing comparativo).

---

## 3. `macro.csv` — Parametri macro country-year

Una riga per **coppia (country, year)**. Usata da:
- DCF per costruire il WACC (risk-free, MRP, inflation)
- RAPD per il centro della distribuzione dei ricavi (crescita PIL nominale media 5y) e per il costo del debito
- Terminal Value check per il vincolo `g ≤ g_PIL`

| Campo | Tipo | Unità | Descrizione |
|---|---|---|---|
| `country` | string | ISO-3166 α-2 | |
| `year` | int | YYYY | |
| `gdp_real_growth` | float | decimale | Crescita reale PIL |
| `inflation_rate` | float | decimale | Inflazione CPI |
| `gdp_nominal_growth_5y_avg` | float | decimale | Media 5y PIL nominale (per cap di `g` nel TV e centro RAPD) |
| `risk_free_rate_10y` | float | decimale | Rendimento govvy 10y |
| `market_risk_premium` | float | decimale | MRP (default 5% per Eurozona, paper RAPD) |
| `credit_spread_bbb` | float | decimale | Spread medio investment grade BBB |

---

## 4. `rating_master_scale.csv` — Master scale Rating ↔ PD

Una riga per **classe di rating**. Mapping usato dal Rating Mapper e dai tool di back-testing. Valori ripresi tal quali dal paper RAPD (Appendice A, tabella "Master Scale").

| Campo | Tipo | Unità | Descrizione |
|---|---|---|---|
| `rating` | string | — | Classe S&P (AAA, AA+, …, D) |
| `rating_ordinal` | int | — | Ordine numerico (AAA=1, AA+=2, …, D=22) per interpolazioni |
| `pd_1y` | float | decimale | Probabilità di default a 1 anno (master scale) |
| `notes` | string | — | Note (es. "ajusted via exponential interp") |

Le conversioni derivate (Z-score → rating → PD, CDS spread → PD) sono gestite in codice dal Rating Mapper; qui si memorizza solo la master scale base.

---

## 5. Convenzioni per dati reali

Quando si passa da fake a dati reali:
1. Mantenere lo stesso schema (stessi nomi campo, stessa unità).
2. Aggiungere un campo `data_source` in coda a `companies.csv` per tracciare provenienza (es. `aida`, `bloomberg`, `orbis`).
3. Se la riclassificazione parte da bilancio IV Direttiva, documentare nel commit il mapping voci → campi dello schema (una nota in `data/mapping_iv_directive.md`).
4. I tool non devono mai modificare i CSV in place; eventuali aggregazioni vanno in `data/processed/`.
