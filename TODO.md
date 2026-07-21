# TODO — Backlog e stato sviluppo

Tracker unificato: **in testa ciò che resta da fare**, in coda le funzionalità completate e le correzioni post-audit (l'audit del 2026-04-08 ha confrontato linea per linea le formule implementate con i paper di riferimento).

Ultimo aggiornamento: 2026-07-21 — **nuovo target del dataset reale: `metal_d_s_r_l`** (METAL D S.R.L., al posto del broker `trafer_spa`); fix NWC negativo nel simulatore; skip+log delle società non simulabili nel backtest; `default_buffer` (Punto 4a linee guida) in `compute_metrics`/`run()`; parametri opt-in Appendice A esposti in dashboard; backtest di dispersione eseguito su tutto il FY2024 reale (256/277 simulate). Tutte le modifiche a `src/` replicate byte-identiche sul gemello `valuation_analyst/` (196 test verdi anche lì). Test suite: **201 test passati in ~1s**.

Precedente: 2026-07-17 — questo repo è **fonte autoritativa** di `credit_metrics.py`; il fix limited-liability è stato portato al repo gemello `valuation_analyst/` rendendo i due file byte-identici (vedi sezione *Governance*). Documentazione WACC/credit risk consolidata in `docs/wacc_credit_risk_linee_guida.md` e `docs/nota_tecnica_credit_metrics_allineamento.md`.

Precedente: 2026-07-13 — onboarding del dataset reale AIDA (ATECO 4672) come dataset principale; sintetico spostato in `data/synthetic/`.

---

## Da fare

### Integrazione nel simulator delle primitives Appendice A

I moduli `capex_plan.py` (eq. [I]-[VI], footnote 8) e `debt_tranches.py` (Sezione 4) esistono, sono testati come primitives stand-alone (voci P3.13/P3.14 completate), ma non sono cablati in `simulator.run()`, che gira sempre il modello ridotto Sezione 2. Ordine concordato il 2026-07-21:

- [ ] **1) Integrazione `capex_plan.py`** — opt-in flag per sostituire `NFA = f·REV` / `D&A = ratio·REV` con la logica dei vintage (`CapexPlan.advance_period`). Richiede il nuovo input **vita utile L** (stimabile come NFA/ammortamenti; per il campione ATECO 4672 l'impatto atteso è contenuto — grossisti asset-light). Test di non-regressione: flag off → output bit-identico.
- [ ] **2) Integrazione `debt_tranches.py`** — opt-in per lo split lungo termine (finanzia NFA, costo r_long) / breve termine (finanzia NWC, costo r_short). Prerequisiti: (a) **decisione di calibrazione** sul secondo costo del debito — AIDA fornisce solo il costo blended; serve un'assunzione sullo spread breve/lungo oppure un'estrazione AIDA con dettaglio debiti entro/oltre esercizio; (b) estendere `simulate_period_two_tranches` alle opzioni già integrate (cash_yield, payout_ratio, debt_floor, tax stocastico), altrimenti attivare le tranche le perderebbe silenziosamente; (c) rivedere il TV con ITS sugli interessi somma delle due tranche. Economicamente rilevante per l'ingrosso (il breve che finanzia il magazzino è la struttura tipica del settore).
- [ ] Entrambe: test di regressione quantitativi sul dataset reale (non-regressione a flag spenti + sensitivity su METAL D a flag accesi) e replica sul repo gemello.

### Default anticipato — estensione opzionale

- [ ] **4b** *(opzionale)* — Soglia alternativa su coverage ratio `EBIT_t/INT_t < soglia`: richiede di accumulare `ebit_t` in matrice nel loop del simulator e passarlo a `compute_metrics`. Il 4a (`default_buffer`) è completato — vedi sezione Completato.

### Backtest Sezione 5 del paper RAPD

- [ ] Backtest vero e proprio con label di default storiche: richiede l'elenco delle società ATECO 4672 fallite/in procedura concorsuale, che l'export AIDA attuale non contiene — da procurare (es. estrazione AIDA "stato giuridico" o registro imprese). L'infrastruttura è pronta (skip automatico, Gini/AUROC/KS, pagina 6); il backtest di **dispersione** senza label è già stato eseguito il 2026-07-21 (vedi Completato).

### Governance — allineamento con il repo gemello `valuation_analyst/`

- [ ] **Regola di allineamento (in vigore finché non c'è il package unico):** ogni modifica a `src/rating_valuation/` va replicata nell'altro repo nella stessa PR (i due package sono copie; `credit_metrics.py` e `data_loader.py` sono già divergiti in passato — `data_loader.py` diverge tuttora per scelta di dataset: qui AIDA reale, nel gemello sintetico).
- [ ] **Unificazione dei due package: DECISO (2026-07-21) — package installabile.** `src/rating_valuation/` sarà estratto in un repo/package dedicato con proprio `pyproject.toml`; questo repo e `valuation_analyst/` lo installeranno via pip (editable in sviluppo, tag git in release). La divergenza voluta di `data_loader.py` (dataset di default) andrà parametrizzata via config/`RV_DATA_DIR`. **Da fare in una sessione dedicata, non ora**; fino ad allora resta in vigore la regola di replica manuale. Vedi `docs/nota_tecnica_credit_metrics_allineamento.md` §7.

### Dati

- [ ] Raffinare le stime macro IT 2020–2024 in `macro.csv` (oggi da fonti pubbliche approssimate) per valutazioni puntuali.

---

## Completato

### Batch 2026-07-21 — target rappresentativo, robustezza su dati reali, UI completa

- [x] **Nuovo target del dataset: `metal_d_s_r_l`**. Il target estratto casualmente (`trafer_spa`, seed 42) era di fatto un broker — struttura patrimoniale non rappresentativa, analisi fuorvianti. Criterio di selezione applicato (script riproducibile): tra le 251 società con panel 2020–2024 completo, hard filter su EBITDA > 0 e NWC > 0 tutti gli anni, equity > 0, NFA/ricavi ≥ 1%, debito > 0; score = distanza (robust z, mediana/IQR) dalle mediane di settore FY2024 su margine EBITDA, NFA/ricavi, NWC/ricavi e log(ricavi). Vincitore: METAL D S.R.L. (2° per score assoluto ma 1° tra quelli con debito materiale: ricavi 12,0 M€, margine 5,6%, D/E ≈ 0,62, PD 3y simulata 0,78% ≈ BB+). Dataset rigenerato con il nuovo flag ETL `--target <company_id|P.IVA>`; docs aggiornati (README, requirements, CLAUDE.md, mapping, Capitolo_doc).
- [x] **Selezione target da UI coerente**: scelta dell'azienda condivisa tra le pagine via `st.session_state` (`app/_common.py::target_selector`); la pagina Differential esclude l'azienda selezionata dal peer sample del BMS (`peer_sample_for_target`) — prima restava dentro la media con cui veniva confrontata.
- [x] **NWC negativo → crash `from_company()`** (emerso 2026-07-17): per la sola variabile NWC — l'unica fisiologicamente negativa (forte credito di fornitura nell'ingrosso) — il minimo della Weibull non è più forzato a 0: `loc` può essere negativo (`simulator.py::from_company`). Test dedicati; replicato sul gemello.
- [x] **Skip+log delle società non simulabili nel backtest**: `BacktestRunner.run()` salta le società non calibrabili (EBITDA atteso ≤ 0) e le logga in `BacktestResult.skipped` con motivo; la pagina 6 le mostra in un expander. `from_company()` continua a sollevare `ValueError` nelle analisi puntuali (voluto).
- [x] **4a — `default_buffer` in `compute_metrics`** (default `0.0` = baseline): `ev < (debt − cash)·(1 + buffer)`, esposto anche in `simulator.run()` e nella pagina 4. Test: buffer = 0 → PD/LGD/n_default identici alla baseline; anticipo su net debt positivo; validazione `buffer ≥ 0`. Nota nel docstring: la forma moltiplicativa allarga il trigger solo sui trial con net debt positivo (il buffer modella la pressione dei creditori, che richiede creditori). Applicato in entrambi i repo.
- [x] **Dashboard — parametri opt-in Appendice A** nella pagina 4: expander "Parametri avanzati" con cash_yield, payout_ratio, debt_floor, tax_stochastic, collateral_coverage e default_buffer; `from_company()` accetta i quattro parametri di `InitialState` come kwargs.
- [x] **Dashboard — pagina 2 DCF**: checkbox "Base decay ROIC esplicita" (`roic_marginal_decay_base`), PIL nominale passato automaticamente da `macro.csv` a `ThreeStageInputs` (attiva C1), e visualizzazione del `coherence_report` integrato di `ThreeStageResult` al posto del ricalcolo manuale.
- [x] **Backtest di dispersione sull'intero campione reale FY2024**: 256/277 società simulate (21 skip per EBITDA ≤ 0), 2 000 trial × 3y, ~1s. Distribuzione PD bimodale: 151 società < 0,25%, 55 > 50%; Spearman ACR vs Altman Z'' = 0,13 (modelli complementari; Altman usa proxy sui retained earnings).
- [x] Replica sul gemello: `simulator.py`, `credit_metrics.py`, `comparator.py` byte-identici nei due repo; nuovi test portati (361 test verdi nel gemello).

### Batch 2026-07-13/17 — dataset reale e limited liability

- [x] **Clippare LGD e recovery rate in `credit_metrics.py`** (emerso il 2026-07-13 sul dataset reale, allora target `trafer_spa`; fixato il 2026-07-13). Sui trial con EV simulato negativo la LGD superava l'EAD e il recovery esplodeva (−46.75% medio, milioni di percento sui trial con debito ≈ 0). Fix: responsabilità limitata nella cascata — `LGD = clip(EAD_unsecured − max(EV,0) − max(CASH,0), 0, EAD_unsecured)`, recovery solo sui default con EAD materiale (> 1 EUR), PD invariata per costruzione. 5 test di regressione. Su TRAFER: LGD media 1.70 → 0.88 M€ (≤ EAD 1.14), recovery −46.8% → 27.1%, EL 1.65 → 0.85 M€. Portato al gemello il 2026-07-17 (file byte-identici).
- [x] Mapping IV Direttiva → schema documentato in `data/mapping_iv_directive.md` (onboarding dataset AIDA ATECO 4672: 277 società, 2020–2024, ETL `data/etl/aida_to_companies.py`; reale in `data/`, sintetico in `data/synthetic/`).
- [x] `sectors.csv` esteso con `Metals Wholesale (ATECO 4672)` (beta unlevered 0.75 Damodaran, shape Weibull default paper).
- [x] Documentazione WACC/credit risk consolidata: `docs/wacc_credit_risk_linee_guida.md` (contratto WACC + validazione dei 5 punti di Maurizio) e `docs/nota_tecnica_credit_metrics_allineamento.md` (diff puntuale del fix). Identiche in entrambi i repo.

### Fondamenta (stato al 2026-04-08)

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
- [x] **P3.13 — Primitives per piano Capex esplicito** (nuovo modulo `agentic_credit_risk/capex_plan.py`). `CapexPlan` con cohort rolling buffer, equazioni [I]-[VI] del paper footnote 8 (straight-line depreciation, retirement, implied Capex per target NFA). Modulo stand-alone — l'integrazione in `simulator.py` è nel backlog in testa a questo file.
- [x] **P3.14 — Primitives per split long-term / short-term debt** (nuovo modulo `agentic_credit_risk/debt_tranches.py`). `simulate_period_two_tranches` riusa `simulate_period_vectorized` su due tranche con costi diversi, allocando NOPAT per peso NIC. Modulo stand-alone — l'integrazione in `simulator.py` è nel backlog in testa a questo file.
- [x] **P3.15 — Dividendi / payout** (`agentic_credit_risk/debt_solver.py`, `simulator.py`). `payout_ratio: float = 0.0` in `InitialState` e in `simulate_period_vectorized`. Il dividendo è `d · max(0, NOPAT − INT_{t-1}·(1−τ))`, consistente con paper eq. [9]. Il closed-form del debito è stato esteso di conseguenza.
- [x] **P3.16 — Debt floor / covenant** (`agentic_credit_risk/debt_solver.py`, `simulator.py`). `debt_floor: float = 0.0` in `InitialState` e in `simulate_period_vectorized`. Implementa paper eq. [8]: `D_t = max(D_bar, ...)`.
- [x] **P3.17 — Collateral coverage nell'LGD** (`agentic_credit_risk/credit_metrics.py`). `compute_metrics(collateral_coverage: float = 0.0)`: la parte secured dell'EAD è sottratta prima del waterfall. Approssimazione semplice della seniority — estensioni più raffinate (più tranche) restano da fare.

#### P4 — Funzionalità opzionali BMS/DCF

- [x] **P4.18 — Calcolo endogeno del ROIC marginale mediano** (`dcf/three_stage.py`). Helper `median_roic_marginal_from_explicit(nopat, nic)`, usato automaticamente dal chiamante quando passa il nuovo `roic_marginal_decay_base`.
- [x] **P4.19 — Screening outlier dimensionali in `BMSBuilder`** (`bms/builder.py`). Parametro opzionale `outlier_sigma: float | None = None`: rimuove peer con revenues oltre k·σ dalla media. I peer rimossi sono tracciati in `BMSResult.excluded_as_outliers`.
- [x] **P4.20 — Statistiche robuste in `BMSResult`** (`bms/builder.py`). Nuovi campi `income_statement_shares_{median,p25,p75}` e `balance_sheet_shares_{median,p25,p75}`. Utili per banding e per flaggare peer che deviano dalla tendenza centrale.
