# Capitolo — La Rating & Valuation Suite: architettura, capability e fondamenti metodologici

## Premessa: un'applicazione costruita con l'AI, eseguibile senza AI

La Rating & Valuation Suite descritta in queste pagine è stata progettata, scritta e validata in collaborazione con un agente di intelligenza artificiale generativa (Claude Code, di Anthropic), usato come *copilota di sviluppo*: traduzione delle formule pubblicate sui paper di riferimento in codice eseguibile, generazione dei test di regressione, audit linea-per-linea della corrispondenza fra pagine accademiche e implementazione. È un metodo di lavoro — non un requisito di prodotto.

Una volta installata, l'applicazione **non richiede alcun modello di AI per essere eseguita**. È una libreria Python deterministica e una dashboard Streamlit che girano in locale, in un container Docker o in un piccolo server interno: nessuna chiamata a servizi cognitivi, nessun token consumato a runtime, nessuna dipendenza da API esterne. I numeri prodotti sono integralmente riconducibili a formule chiuse o a procedure Monte Carlo a seed fisso; ogni risultato è riproducibile bit-per-bit a parità di input.

Questa distinzione — *AI-assisted in build time, AI-free in run time* — è importante per chi deve usare la suite in contesto regolamentato (comitato crediti, fairness opinion, valutazione di un'esposizione non quotata): non si chiede al modello di "prevedere" nulla; si chiede al codice di applicare in modo trasparente e ispezionabile un metodo di valutazione la cui letteratura è pubblica e citata in calce.

Il capitolo successivo del Quaderno spiegherà come installarla e usarla. Questo capitolo descrive **cosa fa** e **perché lo fa così**.

---

## 1. Inquadramento metodologico: i tre pilastri della suite

La suite è la sintesi operativa di tre paper, di cui due pubblicati su questa stessa Rivista AIAF:

1. **Bilancio Medio Standardizzato (BMS)** — Scarano A., Brughera G.L.G., *Valutazione di una PMI con approccio settoriale*, Rivista AIAF n. 65, dicembre 2007/gennaio 2008. Il paper introduce un metodo di costruzione di un'**Impresa Media Standard** (IMS) che evita la distorsione dimensionale tipica dei "bilanci somma" di settore: ogni voce di conto economico è normalizzata sul fatturato del singolo peer e ogni voce di stato patrimoniale sul totale attivo, prima di farne la media aritmetica. La PMI obiettivo è poi valutata *per differenziale* rispetto all'IMS.

2. **Terminal Value coerente** — Scarano A., Di Napoli G., *Calcolo del Terminal Value e rispetto delle condizioni di coerenza*, Rivista AIAF n. 66, aprile 2008. Lo studio Università di Bergamo citato nel paper rileva che il Terminal Value pesa in media il 64 % del fair value calcolato da analisti professionali e che circa il 10 % dei report ha un TV *incoerente* con il piano economico-finanziario sottostante (tipicamente: tasso `g` superiore al PIL nominale di lungo periodo, oppure `g` non finanziato da reinvestimento). Il paper propone una formula esplicita di reinvestimento `g = ROIC_NI · h` e raccomanda un DCF a tre stadi in cui il `ROIC` marginale converge geometricamente al WACC.

3. **Risk Analysis Probability of Default — Stochastic Simulation Model** — Montesi G., Papiro G., draft aprile 2014 (qui chiamato *Agentic Credit Risk*, dal nome interno con cui il modello è stato implementato). Il paper costruisce una stima **forward-looking** della probabilità di default di un'impresa partendo dai fondamentali di bilancio e da parametri settoriali, senza usare prezzi di mercato. La PD è la frequenza con cui, in 20.000 simulazioni Monte Carlo, l'Enterprise Value scende sotto il debito netto. Il modello è applicabile alle PMI non quotate, dove i metodi option-based (Merton, Moody's KMV) non sono utilizzabili per assenza di prezzi azionari.

I tre paper condividono lo stesso scheletro concettuale — *capital budgeting + flussi di cassa attesi + WACC* — e questo è il motivo per cui, nella suite, possono essere composti in una singola pipeline senza introdurre incoerenze fra moduli (il dettaglio è nella sezione 4).

---

## 2. Architettura della suite

L'applicazione è organizzata come una **libreria Python** (`rating_valuation`) con sopra una **dashboard web Streamlit** multi-pagina. Il disegno è a strati, dal dato grezzo al risultato finale:

```
data/  (CSV)
   │
   ▼
common/data_loader  ──►  validazione schema, invarianti di bilancio
   │
   ▼
moduli di dominio   ──►  bms/  dcf/  agentic_credit_risk/
                          differential/  rating/  backtest/
   │
   ▼
app/pages/          ──►  dashboard Streamlit (7 pagine)
```

I sei moduli di dominio sono indipendenti — ognuno produce risultati per conto suo — ma sono progettati per essere compositi. Una valutazione "completa" tipicamente compone:

- **BMS** sul campione di settore → benchmark IMS;
- **DCF** sull'IMS e sul target → Enterprise Value e Equity Value;
- **Differential** target vs IMS → attribuzione del premio o sconto a margine, leva, capital intensity, crescita;
- **Agentic Credit Risk** sul target → PD, LGD, EL, UL, rating implicito;
- **Rating Mapper** → traduzione PD ↔ classe S&P sulla master scale.

I dati di input sono in `data/`, in formato CSV con schema documentato (`data/schema.md`). I file sono quattro:

| File | Contenuto | Granularità |
|---|---|---|
| `companies.csv` | Bilanci riclassificati (CE + SP gestionale) | una riga per impresa × esercizio |
| `sectors.csv` | Beta unlevered, parametri Weibull, matrice di correlazione | una riga per sotto-settore GICS |
| `macro.csv` | Risk-free, MRP, PIL nominale 5y, inflazione, spread BBB | una riga per paese × anno |
| `rating_master_scale.csv` | Mapping S&P rating ↔ PD a 1 anno (paper RAPD App. A) | una riga per classe (AAA → D) |

Lo schema dei CSV è validato dai loader (`common/data_loader.py`): valori monetari espressi sempre in **milioni** della valuta dichiarata, tassi e percentuali in **decimali** (0,28 = 28 %), date come anno fiscale `YYYY`. Le invarianti di bilancio (`common/invariants.py`) verificano `EBITDA = Ricavi − Costi operativi`, `NIC = NFA + NWC`, `Net Debt = Debito lordo − Cassa`, `Equity ≈ NIC − Net Debt`. Una violazione fa fallire il caricamento prima ancora che l'analisi inizi: un errore di riclassificazione non si propaga silenziosamente nei numeri finali.

L'intero codice di dominio è in `src/rating_valuation/`. La dashboard in `app/`. La test suite — 188 test che girano in meno di un secondo — è in `tests/` e copre tutti i moduli, inclusi test specifici di equivalenza algebrica fra formule del codice e formule pubblicate (es. `test_solve_debt_paper_formula_equivalence` per l'equazione [7] del paper RAPD) e test di guardia sull'integrità del dataset reale.

---

## 3. Le sei capability funzionali

### 3.1 Capability 1 — BMS Builder (Bilancio Medio Standardizzato)

**Cosa fa.** Costruisce, dato un campione di peer di settore, un'Impresa Media Standard rappresentativa del comparto. Per ogni voce di conto economico si calcola la quota sul fatturato del singolo peer, si fa la media aritmetica delle quote, e la si moltiplica per il fatturato medio del campione. Per lo stato patrimoniale si fa lo stesso usando il totale attivo come denominatore.

**Perché non basta la somma.** Il paper Scarano/Brughera mostra con un esempio elementare l'effetto-dimensione: un'Impresa A con fatturato 1.000 € (EBITDA 200 €, margine 20 %) e un'Impresa B con fatturato 3.000 € (EBITDA 1.000 €, margine 33 %) hanno, sommate, un EBITDA aggregato di 1.200 € ed un margine implicito del 30 %, dominato dal peer più grande. Il BMS, mediando le quote (20 % + 33 %)/2 = 26,5 % e applicandolo al fatturato medio 2.000 €, dà un EBITDA standard di 533 € e un margine del 26,5 %. La differenza (~22 %) è esattamente la distorsione che il metodo intende eliminare.

**Funzionalità implementate.**

- Costruzione del BMS per un singolo esercizio (`BMSBuilder`) o serie storica multi-anno (`build_bms_timeseries`), per analisi di trend del settore.
- Esclusione automatica dell'eventuale impresa target dal campione (filtro `is_target == 1`).
- Screening opzionale degli outlier dimensionali (`outlier_sigma`): rimozione dei peer con fatturato oltre k deviazioni standard dalla media.
- Statistiche robuste oltre alla media: mediana, 25° e 75° percentile per ogni voce normalizzata, utili per definire bande di confidenza settoriali e per capire se la media è influenzata da pochi peer estremi.
- Confronto BMS vs "bilancio somma line-by-line" sullo stesso campione, per documentare quantitativamente l'effetto dimensionale.
- Soglia minima campione raccomandata dal paper: 20 peer. Sotto soglia il builder non solleva errori, ma marca il risultato con `below_min_sample = True` lasciando la decisione operativa all'analista.

**Output.** Un `BMSResult` con: CE e SP standardizzati, quote medie, statistiche robuste (mediana, percentili), elenco peer inclusi ed esclusi, confronto con la somma diretta.

### 3.2 Capability 2 — DCF Engine con Terminal Value coerente

**Cosa fa.** Calcola Enterprise Value ed Equity Value di un'impresa con un modello DCF a due o tre stadi, applicando la formula di reinvestimento del paper Scarano/Di Napoli e producendo automaticamente un **rapporto di coerenza** del Terminal Value.

**DCF a due stadi.** Periodo esplicito di previsione (tipicamente 5–8 anni) + Terminal Value calcolato con la formula coerente:

```
TV = NOPAT_{T+1} · (1 − g/ROIC_NI) / (wacc − g)
```

dove `(1 − g/ROIC_NI) = 1 − h_T` è il tasso di payout implicito, ovvero la quota di NOPAT non reinvestita per finanziare la crescita. Quando `ROIC_NI = wacc` (i nuovi investimenti rendono esattamente il costo del capitale → nessun valore aggiuntivo dalla crescita), la formula collassa a `TV = NOPAT/wacc`.

**DCF a tre stadi.** Stadio 1 = previsione esplicita; Stadio 2 = convergenza, in cui il `ROIC` marginale è portato geometricamente verso il WACC con tasso `(WACC/ROIC_residuo)^(1/n) − 1`; Stadio 3 = steady state con `ROIC_NI = WACC` e `TV = NOPAT/wacc`. Il punto di partenza del decay del ROIC può essere il ROIC marginale dell'ultimo anno esplicito oppure — come prescrive il paper p. 31 — il ROIC mediano dello stadio 1, calcolabile endogenamente con la helper `median_roic_marginal_from_explicit(nopat, nic)`.

**Check di coerenza integrati (non opzionali).** Ogni risultato del DCF include un `coherence_report` con sette controlli, eseguiti automaticamente:

| ID | Check | Effetto se violato |
|---|---|---|
| C1 | `g ≤ g_PIL_nominale_5y` | ERROR — la perpetuity supera la crescita di lungo periodo dell'economia |
| C2 | `g ≈ ROIC_NI · h_T` con tolleranza | WARNING — disallineamento fra crescita dichiarata e reinvestimento implicito |
| C3 | Formula coerente effettivamente usata (no Gordon naive) | WARNING — segnala che è stato usato il TV semplice senza reinvestment factor |
| C4 | `peso TV / EV ≤ 80 %` | WARNING — DCF dominato dal TV, allungare l'orizzonte esplicito |
| C5 | `ROIC_marginale → WACC` al termine dello stadio 2 (solo 3 stadi) | ERROR — il decay non chiude al WACC, il TV semplificato non è applicabile |
| C6 | Coerenza di segno e ordinamento (NOPAT > 0, ΔNIC > 0 in caso di crescita, ecc.) | WARNING |
| C7 | `h_T ∈ [0, 1]` | ERROR — il vincolo è violato: o `g` è troppo alto rispetto al ROIC, o il ROIC è negativo |

Il `verdict` aggregato è `PASS`, `WARNING` o `ERROR`. Un `ERROR` non blocca il calcolo numerico — il valore esce comunque — ma è un segnale forte all'analista che il TV non è difendibile in comitato senza correzioni agli input. Questo è coerente con la raccomandazione operativa del paper Scarano/Di Napoli: *"una buona policy di controllo qualità impone procedure che verifichino la coerenza tra g, h_T = g/ROIC e wacc in ogni valutazione"*.

**Aggancio automatico al PIL.** Il check C1 può leggere il `gdp_nominal_growth_5y_avg` direttamente da `data/macro.csv` per il paese e l'anno della valutazione (`check_g_below_gdp_from_macro`), togliendo dal carico dell'analista la digitazione manuale del cap macro.

### 3.3 Capability 3 — Differential Analyzer (target vs IMS)

**Cosa fa.** Date la valutazione del target e quella dell'IMS, scompone il **differenziale di valore** in quattro driver:

- **Margine operativo** — gap di EBITDA/Ricavi.
- **Crescita attesa** — gap di CAGR previsto.
- **Capital intensity** — gap di NIC/Ricavi.
- **Leva finanziaria** — gap di Debt/Equity.

L'output è una decomposizione che attribuisce a ciascun driver un contributo positivo o negativo al premio (o sconto) del target rispetto al settore. La somma dei quattro contributi non coincide mai esattamente con il gap totale di equity value perché gli effetti interagiscono moltiplicativamente, ma le **direzioni** dei driver dicono al comitato dove l'impresa batte o perde contro il benchmark.

**Esempio dimostrativo (dataset sintetico, `data/synthetic/`).** La fixture sintetica inclusa contiene Riva Meccanica SpA (target) confrontata con 15 peer del settore Industrial Machinery. La target ha margine 17 % vs settore 14 %, crescita 7 % vs 4,5 %, leva 34 % vs 41 %. L'analizzatore attribuisce il premio principalmente a margine (+8 %) e crescita (+5 %), con un contributo minore dalla minore leva. Il messaggio operativo per il comitato è: *"il premio è giustificato dalla difesa del margine sopra la media e dalla crescita superiore, non da un'esposizione finanziaria più aggressiva"*.

### 3.4 Capability 4 — Agentic Credit Risk (Monte Carlo PD forward-looking)

È il modulo più articolato della suite. Implementa il modello del paper Montesi/Papiro con tutte le estensioni dell'Appendice A.

**Idea centrale.** La PD non è uno score derivato da rapporti di bilancio (come l'Altman Z), ma una **frequenza empirica** generata simulando 20.000 traiettorie multi-anno coerenti dei fondamentali dell'impresa e contando in quante di esse l'EV scende sotto il debito netto.

**Equazioni base** (numerazione del paper):

```
[1]  NOPAT_t = REV_{t-1} · (1 + g_t) · m_t · (1 − τ)
[2]  NIC_t   = (f_t + w_t) · REV_{t-1} · (1 + g_t)
[3]  OCF_t   = NOPAT_t − ΔNIC_t + τ·INT_t          (capital cash flow, Ruback 2002)
[4]  INT_t   = r_d · (D_{t-1} + D_t) / 2
[5]  D_t     = max[0, D_{t-1} − OCF_t + INT_t − ΔCAP_t]
[6]  CASH_t  = CASH_{t-1} + max(0, OCF_t − INT_t − repayment_t)   (eq. dinamica cassa)
[7]  D_t     = max[0, (2·(NOPAT_t − ΔNIC_t + ΔCAP_t − 2·D_{t-1}) /
                       (r_d·(1−τ) − 2)) − D_{t-1}]                 (forma chiusa)
[12] EV_t    = Σ_{i=t..T-1} OCF_{i+1} / (1+k)^{i+1} + TV / (1+k)^T
[13] Default ⇔ EV_t < D_t − CASH_t
```

Le quattro **variabili stocastiche** (crescita ricavi, OpCost/Ricavi, NFA/Ricavi, NWC/Ricavi) sono modellate come distribuzioni Weibull a tre parametri con shape derivati dal paper (rispettivamente 2 / 3,5 / 3,5 / 3) e correlate via copula gaussiana. La matrice di correlazione standard del paper è:

|  | Sales | OpCost/Sales | NFA/Sales | NWC/Sales |
|---|---|---|---|---|
| Autocorr (lag 1) | +0,2 | +0,3 | +0,5 | +0,4 |
| Sales × … | — | −0,4 | +0,2 | −0,3 |
| OpCost × … |  | — | −0,2 |  |

**Centratura della distribuzione dei ricavi**: la media è ancorata al PIL nominale a 5 anni del paese dell'impresa (letto da `macro.csv`). Il floor della distribuzione è la media impresa decurtata dal differenziale settoriale (parametri da `sectors.csv`).

**WACC pre-tax.** Il simulatore usa il **pre-tax WACC** (`w_e·k_e + w_d·r_d`, senza moltiplicare il debito per `(1−τ)`), perché il tax shield è già esplicitamente dentro l'OCF di Ruback (`+ τ·INT`). Applicare l'after-tax WACC al capital cash flow farebbe doppio counting del beneficio fiscale del debito — un errore frequente in implementazioni naïf.

**Debito endogeno ricorsivo.** Il debito non è un input fisso ma è risolto in forma chiusa imponendo `cash inflow = cash outflow` ogni periodo (eq. [7]). Quando il fabbisogno di debito è negativo, il modello passa al regime di accumulazione di cassa (eq. [6]). L'equivalenza algebrica fra il codice e la formula del paper è verificata da un test automatico (`test_solve_debt_paper_formula_equivalence`).

**Estensioni Appendice A** (tutte opt-in, retro-compatibili con il "modello ridotto" della Sezione 2 del paper):

- `cash_yield` — interessi attivi sul cash dopo tasse.
- `tax_stochastic` — aliquota fiscale uniforme `U(0,7·τ; 1,5·τ)`, fissa per trial.
- `payout_ratio` — dividendi pari a `d · max(0, NOPAT − INT_{t-1}·(1−τ))` (paper eq. [9]).
- `debt_floor` — vincolo di leva minima `D_t ≥ D̄` (paper eq. [8]).
- `collateral_coverage` — quota secured dell'EAD sottratta prima del waterfall LGD.
- `capex_plan` (modulo `capex_plan.py`) — piano Capex esplicito con ammortamento per vintage e Capex implicito da target NFA (paper footnote 8).
- `debt_tranches` (modulo `debt_tranches.py`) — split long-term / short-term con costi del debito separati.

I primitives dei due ultimi punti sono già disponibili come moduli stand-alone; la loro integrazione nel loop principale del simulator è una follow-up dichiarata in `TODO.md`.

**Output del simulatore.** L'oggetto `AgenticCreditRiskResult` contiene, per ogni traiettoria e ogni periodo: matrici diagnostiche `nopat`, `ocf`, `debt`, `cash`, `ev`, `interest`. Aggregati a portfolio level: tre versioni della PD (yearly default frequency, marginal PD, cumulative PD), LGD media, Expected Loss, Unexpected Loss al 95° e 99° percentile, rating implicito interpolato sulla master scale. Il rating non è quantizzato sulle 22 classi: una PD di 0,200 % cade fra BBB+ (0,160 %) e BBB (0,230 %) e viene restituita come `"BBB+/BBB (0.62)"`, con interpolazione log-lineare sulla distanza fra le due classi.

**Interpretazione delle PD.**

| Metrica | Formula | Quando usarla |
|---|---|---|
| Yearly Default Frequency | `P(EV_t < D_t − CASH_t)` | Stress test, distribuzione temporale del rischio |
| Marginal PD | `P(default in t \| no default prima)` | Pricing del debito, costruzione della curva spread |
| Cumulative PD | `P(default entro t)` | Comitato crediti, allineata a Basel 2 IRB |

**Differenze vs modelli option-based** (Merton, Moody's KMV).

| Aspetto | Agentic Credit Risk | Merton / KMV |
|---|---|---|
| Source dell'EV | Fondamentali (DCF stocastico) | Prezzi di mercato + volatilità storica |
| Debito | Endogeno, ricorsivo | Esogeno, statico |
| Applicabile a private | Sì | No (richiede prezzi azionari) |
| Orizzonte > 1 anno | Sì, multi-anno coerente | Limitato |
| Bias da bolle/inefficienze di mercato | No | Sì |

### 3.5 Capability 5 — Rating Mapper

**Cosa fa.** Traduce fra PD e classe di rating, fra CDS spread e PD, fra Z-score di Altman e rating.

- **Master scale S&P** (22 classi, AAA → D) caricata da `rating_master_scale.csv`. La mappa PD → rating è interpolata log-linearmente fra le ancore, in modo che a una PD di 0,42 % corrisponda una label `"BBB+/BBB"` con peso di interpolazione, anziché un secco "BBB+" derivato da una ricerca per soglia.
- **Conversione CDS → PD** con la formula `PD = 1 − exp(−CDS / LGD)`, con `LGD = 0,60` (recovery 40 %, valore standard del paper RAPD).
- **Conversione Altman Z-score → rating** via la mappa `ALTMAN_Z_BUCKETS` riportata nel paper RAPD. È disponibile sia il classico `Z` per imprese manifatturiere quotate, sia il `Z''` *non manufacturing* di Altman, che è quello usato per le PMI italiane non quotate.

### 3.6 Capability 6 — Backtest Comparator

**Cosa fa.** Esegue, su un campione di imprese miste (defaulted + performing), il calcolo della PD secondo più modelli e ne misura la performance discriminatoria con tre statistiche standard:

- **AUROC** (Area Under the ROC Curve)
- **Coefficiente di Gini** (= 2·AUROC − 1)
- **Statistica di Kolmogorov-Smirnov**

Modelli supportati: Agentic Credit Risk, Altman Z'' non-manufacturing, e — quando il dataset include i prezzi — modelli Merton-style. Il modulo riproduce la sezione 5 del paper RAPD, dove il modello Agentic Credit Risk dimostra di anticipare il default di 1–3 anni rispetto all'Altman Z'' (PD mediana > 60 % un anno prima del default vs < 20 % per Altman) e di non mostrare bias upward sulle imprese performing.

---

## 4. Convenzioni trasversali (perché i numeri sono coerenti tra moduli)

Il design della suite è guidato da un principio: **lo stesso dato non deve essere trattato in modo diverso da moduli diversi**. Tre convenzioni rendono la pipeline algebricamente uniforme.

### 4.1 Una sola definizione di flusso di cassa: capital cash flow di Ruback

DCF, Terminal Value e Agentic Credit Risk usano lo stesso flusso:

```
OCF = NOPAT − ΔNIC + τ · INT
```

Questa è la formulazione di Ruback (2002), nota come *capital cash flow*: il tax shield del debito è esplicitamente dentro il flusso, non dentro il tasso di sconto. Mischiare, all'interno della stessa pipeline, FCFF tradizionale (post-tasse) scontato con WACC after-tax in un modulo, e capital cash flow in un altro, produce risultati incoerenti del 3–5 % sullo stesso input. L'uniformità è un vincolo di architettura.

### 4.2 WACC pre-tax dove serve, after-tax solo nel DCF "classico"

- **Agentic Credit Risk** → pre-tax WACC, sempre. Il tax shield è già nel flusso.
- **DCF coerente del TV** → pre-tax WACC, per coerenza con la stessa definizione di flusso.
- **DCF "classico" su FCFF puro** (non capital cash flow) → after-tax WACC; ma il design della suite preferisce uniformare.

`AgenticCreditRiskSimulator.from_company` costruisce il `wacc` dell'`InitialState` in pre-tax per costruzione: non c'è modo di sbagliare segno o moltiplicatore.

### 4.3 Sign flip esplicito sulle correlazioni di settore

Il paper RAPD parametrizza la matrice di correlazione su `OpCost/Sales`. La nostra implementazione lavora invece su `EBITDA margin = 1 − OpCost/Sales`. Il flip di segno (`Corr(Sales, OpCost/Sales) = −0,4` → `Corr(Sales, EBITDA_margin) = +0,4`) è applicato **una sola volta**, nel factory `from_company()`. È documentato esplicitamente nel CLAUDE.md di progetto perché una sua duplicazione (o omissione) altererebbe la varianza simulata dell'EV e quindi la PD.

### 4.4 Invarianti di bilancio enforced ai loader

`common/invariants.py` controlla, con tolleranza `0,01` nell'unità monetaria del CSV:

- `EBITDA = Ricavi − Costi operativi`
- `EBIT = EBITDA − D&A`
- `NIC = NFA + NWC`
- `Net Debt = Debito lordo − Cassa`
- `Equity ≈ NIC − Net Debt` (equilibrio del bilancio riclassificato)

Una violazione fa fallire il caricamento. Questo significa che un dataset reale, prima di poter alimentare la pipeline, deve essere riclassificato correttamente: la suite non maschera errori di riclassificazione propagandoli silenziosamente.

---

## 5. Stack tecnico e riproducibilità

**Linguaggio**: Python ≥ 3.11.
**Dipendenze runtime minime**: `pandas ≥ 2.0`, `numpy ≥ 1.24`, `scipy ≥ 1.10`. Nessuna libreria di AI/ML, nessuna dipendenza da servizi esterni a runtime.
**Dipendenze opzionali**: `streamlit ≥ 1.30` e `plotly ≥ 5.18` per la dashboard; `pytest`, `pytest-cov`, `ruff` per lo sviluppo.

**Riproducibilità.** Tutti i risultati Monte Carlo sono prodotti con seed fisso (default `seed=42`); a parità di seed e di input il sistema restituisce gli stessi numeri bit-per-bit. Sia l'ETL del dataset reale (`data/etl/aida_to_companies.py`) sia il generatore del dataset sintetico (`data/generators/seed_companies.py`) sono idempotenti.

**Test suite.** 188 test che girano in meno di un secondo. Coprono:

- equivalenza algebrica fra formule del codice e formule pubblicate (`test_solve_debt_paper_formula_equivalence`, `test_dcf_coherence_paper_examples`);
- proprietà delle distribuzioni stocastiche (medie, varianze, correlazioni a target);
- comportamento ai bordi (PD = 0 e PD = 1, ROIC = WACC, `h = 0` e `h = 1`, campione BMS sotto-soglia);
- check di coerenza del TV su esempi *progettati per fallire*;
- backward compatibility delle estensioni Appendice A con i default neutri.

**Dashboard.** Streamlit multi-pagina, scoperta automatica delle pagine per ordine numerico (`1_BMS_Builder`, `2_DCF_Valuation`, `3_Differential_Analysis`, `4_Agentic_Credit_Risk`, `5_Rating_Mapper`, `6_Backtest_Comparator`, `7_Data_Manager`). Il container Docker incluso espone la dashboard sulla porta 8501, gira come utente non-root e dichiara un healthcheck su `/_stcore/health`: pronto per essere deployato in un ambiente IT enterprise standard.

**Dataset.** Il dataset principale (`data/*.csv`) è **reale**: 277 società italiane del commercio all'ingrosso di metalli (ATECO 4672), esercizi 2020–2024, riclassificate da export AIDA tramite l'ETL `data/etl/aida_to_companies.py` (regole documentate in `data/mapping_iv_directive.md`); il target della valutazione, TRAFER SPA, è estratto casualmente con seed fisso. L'onboarding dei dati reali ha richiesto **zero modifiche al codice di dominio**: è bastato rispettare lo schema CSV documentato — la conferma empirica della tesi architetturale della suite. Resta disponibile in `data/synthetic/` la fixture sintetica (16 aziende Industrial Machinery, target **Riva Meccanica SpA**), usata dalla test suite e come demo didattica.

---

## 6. Cosa la suite non fa (limiti dichiarati)

Per onestà metodologica e per uso responsabile, è importante dichiarare cosa *non* è la suite:

- **Non è un sistema di previsione puntuale**. La PD restituita non dice "questa impresa fallirà nel 5 % dei casi" in senso bayesiano: dice "dati i parametri stocastici del settore e il bilancio attuale, il 5 % degli scenari plausibili porta l'EV sotto il Net Debt entro l'orizzonte". È un *ordering statistico*, non una previsione individuale.
- **Non sostituisce il giudizio dell'analista**. I check di coerenza (TV, BMS sotto-soglia, varianza Monte Carlo eccessiva) producono *segnali*, non blocchi. La decisione finale resta umana.
- **Non implementa modelli option-based** (Merton, KMV, DRSK Bloomberg). Il backtest può confrontarli con Agentic Credit Risk se l'utente fornisce i dati di prezzo, ma non li implementa.
- **Non importa automaticamente bilanci IV Direttiva arbitrari**. La riclassificazione gestionale è un atto interpretativo che resta a cura dell'analista: per gli export AIDA il repo include un ETL di riferimento (`data/etl/aida_to_companies.py`, regole in `data/mapping_iv_directive.md`), ma ogni nuova fonte richiede le proprie scelte di mapping documentate.
- **Non è certificata Basel-compliant**. La PD è metodologicamente compatibile con la prospettiva IRB-A (cumulative a 1 anno per il regulatory; multi-anno per il pricing), ma la suite non è auditata da un'autorità di vigilanza. Va integrata in un framework di model risk management interno della banca / del fondo prima dell'uso production.

---

## 7. Stato del progetto e roadmap

L'audit linea-per-linea fra codice e paper di riferimento, eseguito ad aprile 2026, ha chiuso tutte le voci di priorità P1–P4 con impatto quantitativo o qualitativo (cfr. `TODO.md`). A luglio 2026 è stato completato l'onboarding del dataset reale AIDA (ATECO 4672) come dataset principale, con la pubblicazione del mapping IV Direttiva → schema (`data/mapping_iv_directive.md`) e il deploy su AWS ECS. I follow-up aperti sono:

- integrazione delle primitives Capex (`capex_plan.py`) e debt tranches (`debt_tranches.py`) nel loop principale del simulator (richiede test di regressione su dataset reale);
- esposizione nei pannelli Streamlit dei parametri opt-in dell'Appendice A (`cash_yield`, `payout_ratio`, `debt_floor`, `tax_stochastic`, `collateral_coverage`);
- robustezza numerica delle metriche LGD/recovery sui target in stress estremo (clip LGD ≤ EAD);
- esecuzione del backtest Sezione 5 del paper RAPD su un sample storico reale, una volta disponibili le estensioni Appendice A integrate.

---

## 8. Verso il Capitolo 2: come si usa

Il prossimo capitolo del Quaderno descrive l'**uso operativo** della suite, dai prerequisiti all'esecuzione di una valutazione end-to-end. Anticipiamo qui un sommario dei prerequisiti minimi che un utilizzatore deve avere o predisporre:

1. **Ambiente**: una macchina con Python 3.11 (Mac, Linux, Windows) oppure Docker Desktop per il deploy containerizzato.
2. **Dati**: il bilancio riclassificato del target e di un campione di almeno 20 peer di settore, con i campi minimi documentati in `data/schema.md`.
3. **Parametri di settore**: beta unlevered settoriale e — se non si usano i default del paper RAPD — i parametri Weibull e la matrice di correlazione del comparto.
4. **Parametri macro**: risk-free decennale, MRP, PIL nominale 5y del paese al momento della valutazione.
5. **Riclassificazione**: capacità di passare da bilancio civilistico (IV Direttiva o IFRS) allo schema gestionale richiesto. Per le PMI italiane si usa tipicamente lo schema NIC = NFA + NWC, con il debito finanziario separato dalla parte commerciale.

Il capitolo successivo entra nel dettaglio passo-passo: installazione, prima valutazione, lettura del coherence report, interpretazione del rating implicito, e checklist di "buon uso" per il comitato crediti e per la fairness opinion.

---

## Riferimenti

- Scarano A., Brughera G.L.G., *Valutazione di una PMI con approccio settoriale*, Rivista AIAF n. 65, dicembre 2007/gennaio 2008.
- Scarano A., Di Napoli G., *Calcolo del Terminal Value (TV) e rispetto delle condizioni di coerenza*, Rivista AIAF n. 66, aprile 2008.
- Montesi G., Papiro G., *Risk Analysis Probability of Default: A Stochastic Simulation Model*, Draft, aprile 2014.
- Ruback R.S., *Capital Cash Flows: A Simple Approach to Valuing Risky Cash Flows*, Financial Management 31 (2), 2002.
- Cassia L., Vismara S., *Valuation accuracy and infinity horizon forecasts*, Università di Bergamo, 2005 (citato in Scarano/Di Napoli 2008).
- Altman E.I., *Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy*, Journal of Finance 23 (4), 1968.
- Merton R.C., *On the Pricing of Corporate Debt: The Risk Structure of Interest Rates*, Journal of Finance 29 (2), 1974.
- Damodaran A., *Equity Risk Premiums (ERP): Determinants, Estimation and Implications*, Stern School of Business, 2008.

I PDF originali dei tre paper metodologici principali sono allegati al repository del codice (cartella `docs/`).
