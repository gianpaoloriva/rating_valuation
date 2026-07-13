# TODO — Stato sviluppo e backlog post-audit

Tracker unificato delle funzionalità completate e delle correzioni fatte sul codice dopo l'audit del 2026-04-08 che ha confrontato linea per linea le formule implementate con i paper di riferimento.

Ultimo aggiornamento: 2026-07-13 — onboarding del dataset reale AIDA (ATECO 4672) come dataset principale; sintetico spostato in `data/synthetic/`. Test suite: **188 test passati in ~1s** (183 + 5 guardie sul dataset reale in `tests/test_real_dataset.py`).

---

## Completato

Stato al 2026-04-08 — tutte le voci sotto sono a produzione e coperte dalla test suite.

### Fondamenta

- [x] Schema dati normalizzato (`data/schema.md`) + fake dataset Industrial Machinery (16 aziende × 3 anni)
- [x] Tabelle di riferimento: `sectors.csv`, `macro.csv`, `rating_master_scale.csv`
- [x] Loader tipizzati con validazione di schema (`common/data_loader.py`)
- [x] Check di invarianti bilancio riclassificato (`common/invariants.py`)
- [x] Financial primitives (WACC pre/post tax, perpetuity, Gordon TV, ROIC, reinvestment rate)

### Tool analitici

- [x] **Tool A — BMS Builder**: costruzione Bilancio Medio Standardizzato + serie storica (`bms/builder.py`)
- [x] **Tool B — DCF Engine** 2 e 3 stadi con Terminal Value coerente e check di coerenza (`dcf/`)
- [x] **Tool C — Differential Analyzer** target vs Impresa Media Standard (`differential/analyzer.py`)
- [x] **Tool D — Agentic Credit Risk** Monte Carlo simulator con cash dinamico eq. [6] e debt closed-form eq. [7] (`agentic_credit_risk/`)
- [x] **Tool E — Rating Mapper** master scale, CDS → PD, Altman Z → rating (`rating/mapper.py`)
- [x] **Tool F — Backtest Comparator** Agentic Credit Risk vs Altman Z'' con AUROC / Gini / KS (`backtest/comparator.py`)

### Delivery e UX

- [x] Streamlit dashboard multi-page (Home + 6 pagine + Data Manager)
- [x] Dockerfile + docker-compose (Streamlit non-root, healthcheck `/_stcore/health`)
- [x] Claude Code subagent specializzati (bms-analyst, dcf-validator, agentic-credit-risk-simulator, data-curator, valuation-reporter, backtest-analyst)

### Correzioni post-audit (formule vs paper)

**Audit del 2026-04-08** — confronto line-by-line tra:

- `src/rating_valuation/bms/builder.py` vs Scarano/Brughera, AIAF n. 65 (2008)
- `src/rating_valuation/dcf/*.py` + `common/financial.py` vs Scarano/Di Napoli, AIAF n. 66 (2008)
- `src/rating_valuation/agentic_credit_risk/*.py` + `rating/mapper.py` vs Montesi/Papiro, RAPD (2014)

#### P1 — Formule con impatto quantitativo

- [x] **P1.1 — Terminal Value Agentic Credit Risk con Interest Tax Shield** (`agentic_credit_risk/simulator.py`). Il TV è ora `NOPAT_T/k + τ·INT_T` come prescritto dall'Appendice A del paper RAPD. La matrice `interest` è propagata in `AgenticCreditRiskResult` per ispezione. Effetto: PD non è più sistematicamente sovrastimata per aziende leveraged.
- [x] **P1.2 — Cash floor fisiologico in `simulate_period_vectorized`** (`agentic_credit_risk/debt_solver.py`). Il `max(0, excess_cash)` pre-floor è stato rimosso (l'eq. [6] del paper non lo prevede); resta solo il vincolo fisico `cash ≥ 0` sul livello finale. Nel modello ridotto la modifica è algebricamente no-op — l'`excess_cash` nel caso clamped è sempre non-negativo per costruzione — ma il codice ora rispecchia letteralmente la formula del paper.
- [x] **P1.3 — DCF 3-stage: base del tasso di decay ROIC configurabile** (`dcf/three_stage.py`). `ThreeStageInputs` espone il nuovo campo opzionale `roic_marginal_decay_base`: quando popolato con il ROIC mediano dello stadio 1 (come fa il paper Scarano/Di Napoli p. 31), il tasso di fade è calcolato a partire da quel valore. Helper `median_roic_marginal_from_explicit(nopat, nic)` per calcolarlo endogenamente dal forecast esplicito (che sarebbe la voce P4.18, integrata qui).
- [x] **P1.4 — Enforcement `h_T ∈ [0, 1]`** (`common/financial.py`, `dcf/two_stage.py`, `dcf/coherence.py`). `reinvestment_rate` e `terminal_value_coherent` ora sollevano `ValueError` quando `h_T = g/ROIC_NI` esce dall'intervallo `[0, 1]`. Aggiunto il nuovo check `C7 — check_reinvestment_bounds` in `coherence.py`, invocato automaticamente da `check_coherence`.

#### P2 — Qualità / robustezza

- [x] **P2.5 — Aggancio automatico `check_g_below_gdp_from_macro`** (`dcf/coherence.py`). Wrapper che legge `gdp_nominal_growth_5y_avg` direttamente da `data/macro.csv` (o da un DataFrame in input). Il check C1 non dipende più dalla diligenza del chiamante.
- [x] **P2.6 — Warning su `terminal_growth > 0` nel 3° stadio** (`dcf/three_stage.py`). `value_three_stage` emette `UserWarning` quando la premessa `ROIC=WACC` della formula semplificata è contraddetta da una crescita positiva.
- [x] **P2.7 — Rating implicito interpolato nel path principale** (`agentic_credit_risk/simulator.py`). `simulator.run()` usa `rating_of_pd_interpolated` invece della ricerca sequenziale. Il campo `implied_rating` è una stringa pura (es. `"BBB+"`) se la PD coincide con un anchor della master scale, oppure una label interpolata del tipo `"BBB+/BBB (0.42)"` altrimenti.
- [x] **P2.8 — `BMSBuilder` esclude automaticamente `is_target == 1`** (`bms/builder.py`). Se il DataFrame di input contiene righe con `is_target=1`, vengono rimosse con un `UserWarning`. `excluded_as_outliers` resta vuoto; il filtro target è sempre-on.
- [x] **P2.9 — `discount_factor` rifiuta `t` non intero** (`common/financial.py`). Raise `ValueError` su `t` non-int, negativo, o bool. Mid-year discounting non è mai stato voluto dal paper Scarano/Di Napoli.
- [x] **P2.10 — Integrazione three_stage ↔ coherence** (`dcf/three_stage.py`). `ThreeStageResult.coherence_report` è popolato automaticamente con tutti i 7 check. Il campo `gdp_nominal_5y_avg` su `ThreeStageInputs` è opzionale; se non popolato il check C1 è effettivamente skippato (cap = +∞).

#### P3 — Estensioni "Appendice A completa" del paper RAPD

Queste voci sono **opt-in** e retrocompatibili: con i default neutri il simulator riproduce esattamente il comportamento pre-audit (modello ridotto Sezione 2). Attivarle consente di avvicinarsi all'implementazione empirica usata nel back-testing Sezione 5 del paper.

- [x] **P3.11 — Interessi attivi sul cash** (`agentic_credit_risk/debt_solver.py`, `simulator.py`). `InitialState.cash_yield` (default 0) fornisce al solver il tasso di interesse dopo tasse applicato al cash precedente. OCF è coerentemente ridefinito come `NOPAT − ΔNIC + τ·INT + cash_income`.
- [x] **P3.12 — Normalizzazione stocastica tax rate** (`agentic_credit_risk/simulator.py`). `InitialState.tax_stochastic: bool` (default False) attiva una distribuzione uniforme `U(0.7·τ, 1.5·τ)` per trial (fissa cross-year, semplificazione vs Appendice A ma sufficientemente fedele). `simulate_period_vectorized` ora accetta `tax_rate` scalare o `np.ndarray`.
- [x] **P3.13 — Primitives per piano Capex esplicito** (nuovo modulo `agentic_credit_risk/capex_plan.py`). `CapexPlan` con cohort rolling buffer, equazioni [I]-[VI] del paper footnote 8 (straight-line depreciation, retirement, implied Capex per target NFA). Modulo stand-alone — l'integrazione in `simulator.py` è una follow-up.
- [x] **P3.14 — Primitives per split long-term / short-term debt** (nuovo modulo `agentic_credit_risk/debt_tranches.py`). `simulate_period_two_tranches` riusa `simulate_period_vectorized` su due tranche con costi diversi, allocando NOPAT per peso NIC. Modulo stand-alone — integrazione in `simulator.py` è follow-up.
- [x] **P3.15 — Dividendi / payout** (`agentic_credit_risk/debt_solver.py`, `simulator.py`). `payout_ratio: float = 0.0` in `InitialState` e in `simulate_period_vectorized`. Il dividendo è `d · max(0, NOPAT − INT_{t-1}·(1−τ))`, consistente con paper eq. [9]. Il closed-form del debito è stato esteso di conseguenza.
- [x] **P3.16 — Debt floor / covenant** (`agentic_credit_risk/debt_solver.py`, `simulator.py`). `debt_floor: float = 0.0` in `InitialState` e in `simulate_period_vectorized`. Implementa paper eq. [8]: `D_t = max(D_bar, ...)`.
- [x] **P3.17 — Collateral coverage nell'LGD** (`agentic_credit_risk/credit_metrics.py`). `compute_metrics(collateral_coverage: float = 0.0)`: la parte secured dell'EAD è sottratta prima del waterfall. Approssimazione semplice della seniority — estensioni più raffinate (più tranche) restano da fare.

#### P4 — Funzionalità opzionali BMS/DCF

- [x] **P4.18 — Calcolo endogeno del ROIC marginale mediano** (`dcf/three_stage.py`). Helper `median_roic_marginal_from_explicit(nopat, nic)`, usato automaticamente dal chiamante quando passa il nuovo `roic_marginal_decay_base`.
- [x] **P4.19 — Screening outlier dimensionali in `BMSBuilder`** (`bms/builder.py`). Parametro opzionale `outlier_sigma: float | None = None`: rimuove peer con revenues oltre k·σ dalla media. I peer rimossi sono tracciati in `BMSResult.excluded_as_outliers`.
- [x] **P4.20 — Statistiche robuste in `BMSResult`** (`bms/builder.py`). Nuovi campi `income_statement_shares_{median,p25,p75}` e `balance_sheet_shares_{median,p25,p75}`. Utili per banding e per flaggare peer che deviano dalla tendenza centrale.

---

## Backlog aperto

Nessuna voce dell'audit originale è rimasta aperta. Di seguito i follow-up che erano stati indicati come "primitive implementate, integrazione pending":

### Integrazione nel simulator principale delle primitives Appendice A

I seguenti moduli esistono ma non sono ancora cablati in `simulator.run()`:

- [ ] Integrazione di `capex_plan.py` nel loop del simulator (opt-in flag per sostituire `NFA = f·REV` con la logica dei vintage).
- [ ] Integrazione di `debt_tranches.py` in `simulator.run()` (richiede split degli input `delta_nic` in `delta_nfa` + `delta_nwc` e un secondo cost of debt).

Queste integrazioni sono follow-up e richiederanno test di regressione quantitativi sul dataset reale (non fake) perché cambiano la struttura del modello.

### Dashboard Streamlit

- [ ] Esporre i nuovi parametri opt-in (cash_yield, payout_ratio, debt_floor, tax_stochastic, collateral_coverage) nella pagina `4_Agentic_Credit_Risk.py` — oggi il simulator supporta tutto via API ma la UI non li espone.
- [ ] Esporre `roic_marginal_decay_base` e `gdp_nominal_5y_avg` nella pagina `2_DCF_Valuation.py`.
- [ ] Visualizzare il `coherence_report` integrato di `ThreeStageResult` direttamente sotto il risultato numerico.

### Credit metrics — robustezza numerica

- [x] **Clippare LGD e recovery rate in `credit_metrics.py`** (emerso il 2026-07-13 sul dataset reale, target `trafer_spa`; **fixato il 2026-07-13**). Sui trial in cui l'EV simulato andava negativo, la LGD superava l'EAD e il recovery rate esplodeva (−46.75% medio in dashboard, milioni di percento sui trial con debito ≈ 0). Fix applicato — responsabilità limitata nella cascata: `LGD = clip(EAD_unsecured − max(EV,0) − max(CASH,0), 0, EAD_unsecured)`, recovery calcolato solo sui default con EAD materiale (> 1 EUR). PD invariata per costruzione. 5 test di regressione aggiunti (inclusi EV negativo, debito nullo, target reale distressed end-to-end). Su TRAFER: LGD media da 1.70 → 0.88 M€ (≤ EAD 1.14), recovery da −46.8% → 27.1%, EL da 1.65 → 0.85 M€.

### Dati reali

- [x] Documentare in `data/mapping_iv_directive.md` il mapping IV Direttiva → schema `companies.csv` — **fatto 2026-07-13** con l'onboarding del dataset AIDA ATECO 4672 (277 società, 2020–2024, ETL `data/etl/aida_to_companies.py`; il dataset reale è ora il principale in `data/`, il sintetico è in `data/synthetic/`).
- [x] Estendere `sectors.csv` con parametri di settore italiani reali oltre Industrial Machinery — **fatto 2026-07-13**: riga `Metals Wholesale (ATECO 4672)` (beta unlevered 0.75 Damodaran, shape Weibull default paper). Le stime macro IT 2020–2024 in `macro.csv` sono da fonti pubbliche approssimate: raffinare per valutazioni puntuali.
- [ ] Filtro/gestione a monte delle società con EBITDA atteso negativo per il simulatore Agentic Credit Risk (~19 società nel FY2024 reale: oggi `from_company()` solleva errore).
- [ ] Eseguire il backtest Sezione 5 del paper RAPD sul sample storico, ora che le estensioni Appendice A sono disponibili.
