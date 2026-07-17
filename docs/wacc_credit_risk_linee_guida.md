# WACC e Credit Risk — Nota di validazione, architettura e linee guida

**Documento canonico unico.** Aggrega tre note di lavoro precedenti (architettura del Monte Carlo,
validazione delle cinque osservazioni di Maurizio, checklist di integrazione) e le eleva a
**contratto normativo del WACC** per tutti i progetti che ne integrano il calcolo.

- **Oggetto:** modalità *Rating & Valuation* — package `src/rating_valuation/`
  (moduli `common/`, `dcf/`, `agentic_credit_risk/`, `rating/`) e dataset annesso.
- **Destinatario primario:** Maurizio (autore del capitolo sul WACC); Alfonso (impostazione baseline del modello).
- **Vive in due repository** (vedi *Parte 0 → Divergenza tra i due repo*): mantenere le due copie allineate.
- **Metodo:** ogni affermazione è verificata sul codice sorgente; i riferimenti sono `file:linea`.
- **Riferimenti metodologici:** Scarano/Brughera (AIAF n. 65), Scarano/Di Napoli (AIAF n. 66),
  Montesi/Papiro (2014), Ruback (2002).

**Indice**
- Parte 0 — Come leggere questo documento
- Parte I — Architettura del modello Monte Carlo (Agentic Credit Risk)
- Parte II — Validazione delle cinque osservazioni
- Parte III — Contratto WACC (linee guida normative per altri progetti)
- Parte IV — Checklist di integrazione per fasi
- Appendice — Verifica dei riferimenti, divergenza repo, verifica numerica

---

## Parte 0 — Come leggere questo documento

### La chiave di lettura: il modello usa *due* WACC

Buona parte delle osservazioni sul WACC si chiarisce con un'unica precisazione: **il modello impiega
deliberatamente due tassi di sconto distinti, per due flussi di cassa distinti**, e la regola operativa
(CLAUDE.md) è *«pre-tax con CCF, after-tax con FCFF — MAI mescolare»*.

| Flusso scontato | WACC usato | Fattore (1−t) sul debito | Dove |
|---|---|---|---|
| **FCFF** (DCF, valutazione equity/EV) | **after-tax** | **incluso**: `w_e·k_e + w_d·r_d·(1−t)` | `common/financial.py:43-54` |
| **Capital Cash Flow** alla Ruback (Monte Carlo credit risk) | **pre-tax** | **escluso**: `w_e·k_e + w_d·r_d` | `common/financial.py:57-69`; `agentic_credit_risk/simulator.py:271` |

Il capitolo sul WACC descrive il ramo **after-tax** (con il fattore di correzione). La dichiarazione
«quando va escluso» si riferisce al ramo **pre-tax** del Monte Carlo. **Le due posizioni non sono in
contrasto: coesistono nel codice e descrivono due oggetti diversi.**

### Divergenza tra i due repo — leggere prima di usare i `file:linea`

Questo documento vive in **due** repository con implementazioni quasi identiche:

| Repo | Path del package | Ruolo |
|---|---|---|
| **A — `valuation_analyst/`** | `src/rating_valuation/` | Toolkit multi-modale (Damodaran + FSI + R&V) |
| **B — `rating_valuation/`** (standalone) | `src/rating_valuation/` | App Streamlit dedicata, dataset AIDA reale |

**I numeri di riga coincidono nei due repo per tutti i file citati, tranne `credit_metrics.py`.**
Il repo B è **avanti** su quel file: contiene una correzione di *limited liability* nella waterfall
della LGD (clip su `[0, EAD]` + soglia di EAD materiale) **assente nel repo A**, che sposta gli
ancoraggi di ~11 righe. Dove serve, il riferimento è dato per **entrambi** i repo.

| Ancoraggio | Repo A (`valuation_analyst`) | Repo B (`rating_valuation`) |
|---|---|---|
| Condizione di default `EV < D − CASH` | `credit_metrics.py:111` | `credit_metrics.py:122` |
| Calcolo LGD | `credit_metrics.py:165-166` | `credit_metrics.py:178-180` (con clip limited-liability) |
| `def compute_metrics` | `credit_metrics.py:84` | `credit_metrics.py:94` |

> ⚠️ **Debito tecnico da sanare:** i due `credit_metrics.py` sono divergenti. La correzione
> limited-liability del repo B (LGD ≤ EAD, recovery ∈ [0,1]) è un **bug-fix** che il repo A non ha
> ancora ricevuto: nel repo A una target *distressed* può produrre LGD > EAD e recovery rate assurdi.
> Prima di lavorare sul **Punto 4** (buffer di default, che tocca proprio questo file) allineare i due
> file. Vedi Parte IV → Fase 0 → D6.

Tutti gli altri riferimenti (`financial.py`, `simulator.py`, `coherence.py`, `mapper.py`,
`data_loader.py`, `debt_solver.py`) hanno numeri di riga **identici** nei due repo.

---

## Parte I — Architettura del modello Monte Carlo (Agentic Credit Risk)

Contesto necessario a interpretare i cinque punti. Riferimento: Montesi G., Papiro G. (2014),
*"Risk Analysis Probability of Default: A Stochastic Simulation Model"*.

### Architettura in 4 blocchi

| File | Ruolo |
|------|-------|
| `stochastic.py` | genera gli scenari casuali (Weibull + copula gaussiana) |
| `debt_solver.py` | **calcola il debito in modo endogeno** periodo per periodo |
| `credit_metrics.py` | da EV/Debito/Cassa → PD, LGD, EL, UL |
| `simulator.py` | orchestratore: 20.000 trial × 3 anni, vettorializzato in numpy |

Flusso di un singolo trial:

```
scenario stocastico → NOPAT → ΔNIC → debito endogeno → EV → confronto con il debito = default sì/no
```

### Le 4 variabili stocastiche (input, non il debito)

Quello che viene "tirato a sorte" **non è il debito**, ma 4 driver operativi (`stochastic.py:33`):
crescita ricavi `g`, margine EBITDA `m`, NFA/ricavi `f`, NWC/ricavi `w`. Ognuno è una **Weibull**
calibrata su media/minimo settoriale (`WeibullParams.from_mean_min`). Le correlazioni — incrociate
nello stesso anno e autocorrelazione AR(1) tra anni — sono imposte con una **copula gaussiana**:
matrice (4·n_anni)², Cholesky e inversione della CDF Weibull (`sample_scenarios`, `stochastic.py:196`).
Se la matrice non è definita positiva viene "riparata" clippando gli autovalori negativi.

### Il debito: endogeno, in forma chiusa

**Il debito non è proiettato esogenamente.** È **endogeno**: deriva da un vincolo di equilibrio
finanziario (*cassa in entrata = cassa in uscita*). È il "tappabuchi" che chiude il bilancio di cassa.

Dalle tre equazioni del paper (`debt_solver.py:7`):

```
OCF_t = NOPAT_t − ΔNIC_t + τ·INT_t                    [3]  capital cash flow (Ruback)
INT_t = r_d · (D_{t-1} + D_t) / 2                      [4]  interessi su debito medio
D_t   = max(0, D_{t-1} − OCF_t + INT_t − ΔCAP_t)      [5]  il debito assorbe il fabbisogno
```

La **circolarità** (`INT_t` dipende da `D_t` e viceversa) si risolve in **forma chiusa** [7]
(`debt_solver.py:65`):

```
β     = (1 − τ) · r_d / 2
D_raw = [ D_{t-1}·(1+β) − NOPAT_t + ΔNIC_t − ΔCAP_t ] / (1 − β)
D_t   = max(0, D_raw)
```

**È il debito a reagire allo scenario operativo, non viceversa.** Il denominatore `(1 − β)` cattura la
circolarità interessi↔debito; il codice valida che resti positivo (`debt_solver.py:67`).
Estensioni opt-in con default neutri: cassa con rendimento (`cash_yield`), floor di debito [8],
dividendi [9] (`simulate_period_vectorized`, `debt_solver.py:131`); split tranche lungo/breve
(`debt_tranches.py`, non attivo di default).

### Default e metriche

**Condizione di default** (eq. [13]): `EV_t < D_t − CASH_t` — il valore d'impresa non copre il debito
netto (`credit_metrics.py:111` repo A / `:122` repo B). Da `compute_metrics`: **PD** (frequenza di
default marginale e cumulata), **LGD per scenario** (waterfall del collaterale), **EL** = PD_cum ×
LGD_media, **UL** ai quantili 95/99. La PD cumulata è mappata su **rating implicito** via master scale.

Due dettagli legati al debito:
1. Il **Terminal Value include l'Interest Tax Shield** dell'ultimo anno (`TV = NOPAT_T/k + τ·INT_T`,
   `simulator.py:403`): per aziende molto indebitate ometterlo gonfierebbe la PD.
2. Il WACC è **pre-tax** (lo scudo è già nel CCF), coerente con la regola «mai mescolare».

---

## Parte II — Validazione delle cinque osservazioni

### Punto 1 — Coerenza del capitolo WACC e fattore (1−t)

> *«Ho redatto il capitolo sul WACC; è coerente con il modello? Io ho inserito il fattore di
> correzione, ma tu dichiari quando va escluso.»*

**Validazione.** Il codice contiene **entrambe** le formulazioni in `common/financial.py`:
`wacc_after_tax` (`:43-54`, con `(1−t)`) usata dalla pipeline **DCF/FCFF**; `wacc_pre_tax` (`:57-69`,
senza `(1−t)`) usata dal **Monte Carlo** (`simulator.py:271`).

**Perché nel pre-tax il (1−t) va escluso.** Il Monte Carlo sconta il *Capital Cash Flow* alla Ruback
`OCF = NOPAT − ΔNIC + τ·INT` (`debt_solver.py:115-123`): lo scudo fiscale `τ·INT` è **già nel
numeratore**. Applicare anche `(1−t)` al denominatore lo conterebbe **due volte**. Col FCFF, invece,
lo scudo non è nel flusso e va recuperato nel tasso con `r_d·(1−t)`. La regola «mai mescolare» è quindi
una necessità metodologica, non una convenzione.

**Numeri (Riva Meccanica, IT 2024):** WACC after-tax **≈ 7,93%** (DCF/FCFF), WACC pre-tax **≈ 8,32%**
(MC/CCF); Δ ≈ **39 bp** = `w_d·r_d·τ` (0,3106 · 0,045 · 0,28).

**Esito: coerente.** Le due affermazioni descrivono i due rami. Resta da **riconciliare il capitolo con
i parametri effettivi** (Parte III → *Parametri canonici*).

### Punto 2 — Variazione del WACC nella simulazione Monte Carlo

> *«Il WACC dovrebbe variare: (a) col diverso D/E di scenario; (b) col variare di r_d e k_e oltre certi
> livelli di D/E. Il modello li considera o tiene il WACC costante?»*

**Validazione: il WACC è costante.** Calcolato **una volta sola**, fuori dalla simulazione
(`simulator.py:254-284`), identico per tutti i 20.000 trial / anni / scenari (scalare immutabile,
`simulator.py:388, 400-404`).
- **(a) WACC che segue il D/E → NO.** Il *volume* del debito evolve stocasticamente (debt solver
  endogeno), ma il tasso di sconto non lo segue.
- **(b) r_d e k_e reattivi → NO.** `r_d` è scalare costante (`simulator.py:363`; `debt_solver.py:216`);
  `k_e` è relevered con Hamada **solo sul D/E iniziale** (`simulator.py:265-267`), mai per trial.

**Sintesi.** Varia il *volume* del debito (e gli interessi per volume), **non il *prezzo* del capitale**.
Manca il feedback merito-creditizio → spread → costo del capitale. **L'osservazione è corretta: è una
semplificazione consapevole.**

### Punto 3 — La «curva di credit spread»

> *«Mi pare che il modello utilizzi una curva di credit spread: come è costruita e come è utilizzata?»*

**Validazione: nel motore di simulazione non esiste alcuna curva di credit spread attiva.** Gli
elementi presenti sono **scollegati** dal simulatore:
1. `PD = 1 − exp(−(CDS/LGD)·T)`, LGD 60% (`rating/mapper.py:166-195`) → **utility di conversione**,
   mai chiamata dal simulatore. La PD del modello è **endogena** (frequenza di default Monte Carlo).
2. Master scale rating→PD → usata **solo a fine simulazione** per *etichettare* la PD cumulata con un
   rating implicito (direzione PD→rating, `simulator.py:412-417`); non entra nei flussi né nello sconto.
3. `credit_spread_bbb` in `macro.csv` → in whitelist (`data_loader.py:100`) ma **non letto da alcun
   modulo**: dato **inerte**.

**Conseguenze.** `r_d` non deriva da una curva (è la colonna `cost_of_debt` di `companies.csv`); lo
sconto non usa spread; la PD non usa CDS. **Equivoco da chiarire:** una curva di spread che faccia
*repricing* del debito oggi non c'è. È esattamente il componente del Punto 2 (stessa estensione).

### Punto 4 — Default prima di equity = 0

> *«Il default avviene ben prima dell'equity = 0. Sarebbe complicato simularlo?»*

**Validazione.** La condizione è **una riga**: `credit_metrics.py:111` (repo A) / `:122` (repo B):
```python
default_matrix = ev < (debt - cash)   # EV_t < D_t − CASH_t  ⇔  equity netto < 0
```
Eq. [13] Montesi/Papiro. **L'osservazione economica è fondata:** in pratica il default (covenant,
tensione di liquidità, rifinanziamento negato) si manifesta **prima** che `EV < D − CASH`.
**Esito: modificabile con basso impatto.** La soglia è isolata in un unico punto.

### Punto 5 — Crescita terminale `g` ancorata al PIL

> *«Non concordo con la regressione di g al PIL. Non regge teoricamente. Quanto è complesso simulare
> scenari diversi?»*

**Validazione: il modello NON ancora `g` al PIL.** `g` (`terminal_growth`) è **input libero**
(`dcf/two_stage.py:28`, `dcf/three_stage.py:60`; nell'esempio 0,025, scelto a mano e *sotto* il PIL
nominale del 3,6%, ma indipendentemente da esso). Non esiste alcun `g = gdp` né cap automatico.
L'ancoraggio teorico è il **reinvestimento**: `g = ROIC_NI · h_T`, `h_T ∈ [0,1]`
(`common/financial.py:144-168`). **Coincide con la posizione di Maurizio.**

Il PIL interviene in **un solo punto**: il check di coerenza **C1** (`dcf/coherence.py:131-158`), un
**tetto di sanity-check macro** (ERROR se `g` > PIL nominale) **disattivabile** (nel 3-stadi, se non si
passa il PIL il cap diventa `+inf`, `three_stage.py:345-349`). **Esito: equivoco a favore del modello.**

> I 7 check TV (`coherence.py`): C1 `g ≤ PIL` (ERROR, disattivabile) · C2 `g = ROIC·h` (ERROR) ·
> C3 formula TV con reinvestimento (WARN) · C4 peso TV ≤ 80% (WARN) · C5 convergenza ROIC→WACC (WARN) ·
> C6 bound `WACC>g`, `NOPAT_{T+1}>0` (ERROR) · C7 `h = g/ROIC ∈ [0,1]` (ERROR).
> **Solo C1 confronta `g` con il PIL.**

---

## Parte III — Contratto WACC (linee guida normative per altri progetti)

> **Scopo.** Qualunque progetto che integri il calcolo del WACC nella modalità *Rating & Valuation*
> **DEVE** rispettare questo contratto, per mantenere uniformità tra repository e coerenza con i paper.
> Le regole marcate **[MUST]** sono vincolanti; **[SHOULD]** sono fortemente raccomandate.

### R1 — Due WACC, un accoppiamento fisso flusso↔tasso [MUST]

| Se sconti… | usa questo WACC | fattore (1−t) sul debito | funzione di riferimento |
|---|---|---|---|
| **FCFF** | **after-tax** | **incluso** | `wacc_after_tax` (`financial.py:43-54`) |
| **Capital Cash Flow (Ruback)** | **pre-tax** | **escluso** | `wacc_pre_tax` (`financial.py:57-69`) |

- **MAI mescolare** flusso e tasso appartenenti a rami diversi. È la causa di doppio conteggio (o
  omissione) dello scudo fiscale.
- Chi implementa un nuovo motore **[SHOULD]** aggiungere un `assert` a runtime che vincoli
  l'accoppiamento (oggi garantito solo da funzioni separate, docstring e test).

### R2 — Formule canoniche [MUST]

```
CAPM:            k_e = Rf + β_L · MRP            (NIENTE addendo CRP separato)
Hamada:          β_L = β_u · (1 + (1−τ)·D/E)
WACC after-tax:  w_e·k_e + w_d·r_d·(1−τ)          (per FCFF)
WACC pre-tax:    w_e·k_e + w_d·r_d                (per CCF)
Crescita TV:     g = ROIC_NI · h_T,   h_T ∈ [0,1]  (ancoraggio al reinvestimento, NON al PIL)
```

### R3 — Parametri canonici del modello R&V [MUST]

Questi sono i parametri **effettivamente implementati**. Un capitolo o un progetto che ne adotti altri
è **fuori contratto** finché non li si allinea (o non si estende esplicitamente il modello).

| Parametro | Valore/fonte nel modello R&V | **Divieto** |
|---|---|---|
| **Country Risk Premium (CRP)** | **Assente come addendo.** Il rischio-paese è incorporato in `Rf` e `MRP` (`financial.py:34-40`) | Non introdurre `Re = Rf + β·ERP + CRP` senza estendere il CAPM del modello |
| **Market/Equity Risk Premium** | **MRP = 5,0% fisso** (Eurozona) da `macro.csv` | Non usare l'**ERP 6-8%** delle skill FSI senza uniformare |
| **Costo del debito r_d** | **r_d = 4,5% fisso** per azienda, colonna `cost_of_debt` di `companies.csv` | Non derivarlo da `Rf(BTP) + spread da rating` senza uniformare la fonte |
| **Risk-free** | `risk_free_rate_10y` da `macro.csv` | — |
| **Tax rate τ** | `corporate_tax_rate` da `companies.csv` | — |

### R4 — Confine con Damodaran / FSI [MUST]

I termini **CRP**, **ERP 6-8%**, **BTP+spread da rating** appartengono alle convenzioni **Damodaran**
(`src/valuation_analyst/tools/wacc.py`) e **FSI Italy** (skill `fsi-*`), **NON** al modello R&V.
Sono modelli **diversi**: non importarne i parametri nel motore R&V. Se un capitolo li cita, va
riconciliato (togliere dal capitolo **oppure** decidere di estendere il modello — scelta esplicita,
mai implicita).

### R5 — Il WACC del Monte Carlo è costante (baseline) [MUST], dinamico solo opt-in [SHOULD]

- **Baseline:** WACC calcolato una volta fuori dal loop, costante per tutti i trial (impostazione di
  Alfonso). Qualunque estensione dinamica (leva→spread→costo del capitale) **DEVE** essere **opt-in**
  con default neutro: flag disattivato ⇒ output **bit-identico** alla baseline (test di non-regressione
  obbligatorio).

### R6 — Provenienza dei valori [SHOULD]

I parametri vengono dai CSV normalizzati (`macro.csv`, `companies.csv`, `sectors.csv`), non hard-coded
nel codice di calcolo. Un nuovo progetto legge dagli stessi CSV (o da uno schema compatibile,
`data/.../schema.md`).

### Checklist di conformità (da eseguire quando un progetto integra il WACC)

- [ ] Usa `wacc_after_tax` **solo** con FCFF e `wacc_pre_tax` **solo** con CCF? (R1)
- [ ] CAPM senza CRP separato? (R2/R3)
- [ ] MRP = 5,0% e r_d dalla colonna `cost_of_debt`, non da spread di rating? (R3)
- [ ] Nessun parametro Damodaran/FSI importato nel motore R&V? (R4)
- [ ] Eventuale WACC dinamico è opt-in con default neutro e test di non-regressione? (R5)
- [ ] Parametri letti dai CSV, non hard-coded? (R6)

---

## Parte IV — Checklist di integrazione per fasi

Principio guida: **baseline invariata, estensioni opt-in con default neutri** — coerente con
l'impostazione di Alfonso e con lo stile delle estensioni «Appendix A» già presenti.

Legenda impegno: 🟢 basso (< 1h) · 🟡 medio (mezza giornata) · 🔴 alto (richiede calibrazione/decisione).

### Fase 0 — Decisioni da prendere prima di scrivere codice

- [ ] **D1.** Il capitolo WACC usa il **CRP** come addendo separato? → allineare al modello (no CRP) o
      estendere il CAPM. (R3/R4)
- [ ] **D2.** Il capitolo cita **ERP 6-8%**? Il modello usa **MRP 5,0%** → uniformare o documentare. (R3)
- [ ] **D3.** Il capitolo deriva **r_d da spread di rating**? Il modello usa **r_d 4,5% fisso** →
      uniformare la fonte. (R3)
- [ ] **D4.** Il vincolo **`g ≤ PIL`** (C1, ERROR) si tiene, si declassa a WARNING, o si disattiva?
- [ ] **D5.** Alfonso approva le estensioni come **scenari opt-in**?
- [ ] **D6.** ⚠️ **Allineare i due `credit_metrics.py`** (repo A ↔ repo B): portare nel repo A la
      correzione limited-liability del repo B **prima** di lavorare sul Punto 4. (vedi Parte 0)

### Fase 1 — Quick wins (chiudono i Punti 4 e 5)

**Punto 5 — Scenari di `g`** 🟢 (l'osservazione coincide col modello: `g` è già libero)
- [ ] **5a.** Wrapper ~20-30 righe che cicla su una lista di `g` (basso/base/alto) richiamando
      `value_two_stage_coherent` / `value_three_stage`. Nessuna modifica al motore DCF.
- [ ] **5a-bis.** Esempio eseguibile in `examples/rating_valuation/` con tabella di sensitività su `g`.
- [ ] **5c.** *(dipende da D4)* Declassare C1: `coherence.py:142-145` da `ERROR` a `WARNING`; oppure
      zero-codice: non passare il PIL → cap `+inf` (`three_stage.py:345-349`).
- [ ] **5b.** *(opzionale)* Distribuzione stocastica di `g` (Weibull/triangolare); pattern già pronto
      in `simulator.py:209-219`.

**Punto 4 — Default anticipato** 🟢 (una riga; **dopo D6**)
- [ ] **4a.** Parametro `default_buffer` (default `0.0` = baseline) → `ev < (debt - cash) * (1 + buffer)`.
      Edit a `credit_metrics.py:111` (repo A) / `:122` (repo B).
- [ ] **4a-bis.** Allineare la coerenza sulla **LGD**: `credit_metrics.py:165-166` (repo A) /
      `:178-180` (repo B).
- [ ] **4a-test.** Test che con `buffer = 0` la PD sia **identica** alla baseline (non-regressione).
- [ ] **4b.** *(opzionale, più realistico)* Soglia su **coverage ratio** `EBIT_t / INT_t < soglia`.
      `interest_mat` esiste; `ebit_t` è calcolato (`simulator.py:349`) ma **non salvato in matrice** →
      accumularlo nel loop e passarlo a `compute_metrics`. Tocca `simulator.py` + `credit_metrics.py`.

**Punto 1 — Irrigidimento accoppiamento** 🟢
- [ ] **1b.** Assert a runtime CCF↔pre-tax e FCFF↔after-tax (~5 righe). (R1)

### Fase 2 — Documentazione e riconciliazione (Punti 1 e 3)

**Punto 1 — Capitolo WACC** 🟢 (esito: coerente)
- [ ] **1a.** Esplicitare nel capitolo la coesistenza dei due WACC e la regola flusso↔tasso.
- [ ] **1a-bis.** Riportare entrambi i valori (7,93% / 8,32%) con la derivazione del Δ = 39 bp.
- [ ] **1a-ter.** Motivare l'esclusione del (1−t) nel pre-tax (scudo già nel numeratore del CCF).
- [ ] **1c.** *(dipende da D1/D2/D3)* Riconciliare CRP / MRP / r_d col contratto (Parte III).

**Punto 3 — Chiarire l'equivoco «curva di credit spread»** 🟢 (esito: assente)
- [ ] **3a.** Documentare che la PD è **endogena** (frequenza Monte Carlo), non da CDS/spread.
- [ ] **3a-bis.** Chiarire lo stato dei tre elementi (utility CDS→PD; master scale solo per
      etichettatura PD→rating; `credit_spread_bbb` inerte).
- [ ] **3a-ter.** Decidere: rimuovere `credit_spread_bbb` da `macro.csv` o marcarlo riservato per 3b.

### Fase 3 — Estensione strutturata: leva → spread → costo del capitale (Punti 2 + 3b)

⚠️ **I Punti 2 e 3b sono la stessa estensione.** Da affrontare insieme, dopo la Fase 1. Oggi il WACC è
**scalare costante** (`simulator.py:254-284`).

- [ ] **2c.** *(precondizione)* Confermare architettura opt-in con default neutro (flag off → output
      bit-identico). (R5)
- [ ] **2a.** **WACC dinamico per leverage** 🟡 — spostare il calcolo *dentro* il loop: a ogni anno/trial
      ricalcolare D/E dal `debt_mat` e ri-applicare Hamada per `k_e`. Oggi Hamada gira solo sul D/E
      iniziale (`simulator.py:265-267`). Intervento a `simulator.py:340-405`.
- [ ] **2b / 3b.** **Repricing del debito** 🔴 — `r_d = f(leverage o coverage)`. Oggi `r_d` è scalare
      (`simulator.py:363`; `debt_solver.py:216`). **La parte non banale è la calibrazione, non il codice.**
- [ ] **2-attenzione.** ⚠️ Impatto sul **debt solver in forma chiusa**: la soluzione [7] assume `r_d`
      costante nel periodo (`β = (1−τ)·r_d/2`). Se `r_d` dipende dal debito **dello stesso periodo** si
      **reintroduce circolarità** → usare `r_d` laggato su `D_{t-1}`, oppure un solver iterativo.
      **Da decidere prima di implementare 2b.**
- [ ] **2-test.** Non-regressione: flag off → PD/EL/UL identici alla baseline.
- [ ] **2-doc.** Documentare calibrazione e sensibilità sull'output.

### Quadro di sintesi

| # | Tema | Esito validazione | Azione | Impegno | Baseline |
|---|------|-------------------|--------|---------|----------|
| 1 | (1−t) nel WACC | Coerente (due WACC) | 1a documentale + 1b assert | 🟢 | invariata |
| 2 | WACC costante nel MC | Limite riconosciuto | 2c opt-in → 2a, poi 2b | 🟡🔴 | invariata (opt-in) |
| 3 | Curva credit spread | Assente / equivoco | 3a chiarimento; 3b con 2b | 🟢/🔴 | invariata (opt-in) |
| 4 | Default a equity = 0 | Modificabile, 1 riga | D6 allineamento + 4a buffer | 🟢 | invariata (default 0) |
| 5 | `g` vs PIL | Equivoco a favore | 5a scenari di `g` | 🟢 | invariata |

**Ordine consigliato:** Fase 0 (decisioni, incl. D6) → Fase 1 (4a + 5a) → Fase 2 (documentale) →
Fase 3 (unico intervento strutturato, previa calibrazione).

---

## Appendice — Verifica dei riferimenti, divergenza repo, verifica numerica

### Verifica dei riferimenti (repo A — `valuation_analyst/src/rating_valuation/`)

| Riferimento | Posizione | Esito |
|---|---|---|
| `common/financial.py` — `relever_beta`/`cost_of_equity_capm`/`wacc_after_tax`/`wacc_pre_tax`/`reinvestment_rate`/`implied_growth` | `:29`/`:34`/`:43-54`/`:57-69`/`:144`/`:166` | ✓ |
| `agentic_credit_risk/simulator.py` — WACC pre-tax, Hamada su D/E iniziale, rating post-sim | `:271`/`:265-267`/`:412-418` | ✓ |
| `agentic_credit_risk/debt_solver.py` — OCF Ruback, forma chiusa [7] | `:65`/`:115-123` | ✓ |
| `agentic_credit_risk/credit_metrics.py` — default `EV < D − CASH`, LGD | `:111`/`:165-166` | ✓ (repo A) |
| `dcf/two_stage.py` / `dcf/three_stage.py` — `terminal_growth`, cap PIL `+inf` | `:28`/`:60`,`:345-349` | ✓ |
| `dcf/coherence.py` — `check_g_below_gdp` (C1, ERROR a `:145`) | `:131-158` | ✓ |
| `rating/mapper.py` — CDS→PD, LGD 60% | `:166-195` | ✓ |
| `common/data_loader.py` — `credit_spread_bbb` in whitelist (inerte) | `:100` | ✓ |

### Divergenza repo A ↔ repo B (verificata)

`financial.py`, `simulator.py`, `debt_solver.py`, `coherence.py`, `mapper.py` → **numeri di riga
identici**. Diverge **solo** `credit_metrics.py` (repo B avanti, correzione limited-liability):

| Ancoraggio | Repo A | Repo B |
|---|---|---|
| `def compute_metrics` | `:84` | `:94` |
| default `EV < D − CASH` | `:111` | `:122` |
| LGD | `:165-166` (`max(0, EAD−EV−CASH)`) | `:178-180` (`clip(EAD−recoverable, 0, EAD)` + recovery ∈ [0,1]) |

Diverge anche `data_loader.py` (repo B: dataset primario AIDA + `data/synthetic/`; repo A:
`data/rating_valuation/`), ma non contiene ancoraggi WACC/credit-risk citati qui.

### Verifica numerica (Riva Meccanica SpA, target IT 2024, dai CSV)

`gross_debt = 11,723` / `equity = 26,026` → **D/E = 0,4504**; Rf = 3,75%, MRP = 5,0% (`macro.csv`),
β_u = 0,95 (`sectors.csv`, Industrial Machinery), r_d = 4,5%, τ = 28% (`companies.csv`) →
β_L = 1,2581, k_e = 10,04%, **WACC after-tax = 7,93%**, **WACC pre-tax = 8,32%** (Δ = 39 bp = `w_d·r_d·τ`).

---

*Documento derivato dall'aggregazione di tre note di lavoro (architettura Monte Carlo, validazione dei
cinque punti, checklist). Per le implementazioni (Punti 2/3/4/5) si può predisporre una nota tecnica
separata con il diff puntuale, per repo.*
