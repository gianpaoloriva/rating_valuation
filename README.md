# Rating & Valuation Suite

**Valutazione d'impresa e credit risk forward-looking per PMI italiane, su basi accademicamente solide e implementazione production-ready.**

---

## Executive summary

La Rating & Valuation Suite è un sistema integrato che risponde a tre domande che le banche, i fondi e i comitati crediti italiani si pongono ogni giorno davanti a una PMI non quotata:

1. **Quanto vale l'impresa oggi?** — fair value dell'equity e dell'enterprise con DCF multi-stadio, Terminal Value coerente e check automatico contro gli errori più frequenti dei report di valutazione (il 10% storicamente ha un TV non coerente).
2. **Qual è il suo rischio di credito nei prossimi 3 anni?** — probabilità di default, LGD, Expected Loss e Unexpected Loss calcolate in ottica forward-looking via simulazione Monte Carlo sui fondamentali, non sui prezzi di mercato (che per le PMI non esistono).
3. **Quanto si discosta dal benchmark del suo settore?** — analisi differenziale rispetto a un'"Impresa Media Standard" (IMS) costruita dai peer, con scomposizione del gap per margine, leva, capital intensity e crescita.

A differenza dei modelli option-based (Merton, Moody's KMV), che richiedono prezzi azionari e sono inapplicabili alle PMI, la suite lavora interamente da bilancio riclassificato + parametri settoriali pubblici. Questo la rende utilizzabile per **qualunque impresa di cui si abbiano i bilanci**, quotata o no.

Il sistema è costruito sulla sintesi di tre paper accademici di riferimento (due italiani, uno internazionale) e ne implementa fedelmente le formule, con test automatizzati di coerenza su ogni valutazione.

---

## Per chi è pensata

| Caso d'uso | Cosa serve tipicamente | Cosa offre la suite |
| --- | --- | --- |
| **Comitato crediti bancario** | PD/LGD/EL per delibera e Pillar 2 | Rating implicito sulla master scale S&P, PD a 1/2/3 anni, LGD scenario-based |
| **Fairness opinion M&A** | Enterprise e equity value difendibili in board | DCF 2/3 stadi con TV coerente, validatore automatico, decomposizione esplicito/TV |
| **Asset & credit review** | Confronto oggettivo vs benchmark di settore | BMS + analisi differenziale target vs IMS |
| **Stress testing** | Distribuzione di EV e PD sotto scenari | Monte Carlo 20.000 trial con correlazioni settoriali (paper Montesi/Papiro) |
| **Equity research PMI non quotate** | Valutazione rigorosa senza dati di mercato | Pipeline completa da bilancio riclassificato a rating implicito |

---

## Cosa produce il sistema

Per ogni impresa analizzata, la suite genera:

- **Enterprise Value e Equity Value** con decomposizione tra valore esplicito e Terminal Value, e con il `coherence_report` automatico (7 check) attaccato al risultato
- **Probabilità di default** per orizzonti 1, 2 e 3 anni in tre versioni (yearly default frequency, marginal PD condizionata, cumulative PD)
- **LGD, Expected Loss, Unexpected Loss** per ogni percentile dell'intervallo di confidenza, con collateral coverage opt-in
- **Rating implicito** sulla master scale S&P (AAA → D), interpolato log-linearmente (es. `"BBB+/BBB (0.42)"`) per non quantizzare la PD sulle 22 classi
- **Confronto target vs Impresa Media Standard** del settore, con attribuzione differenziale del premio/sconto per driver
- **Backtest comparativo** rispetto ad Altman Z'' e altri modelli classici, con AUROC / Gini / KS
- **Matrici diagnostiche per trial** (`nopat`, `ocf`, `debt`, `cash`, `ev`, `interest`) per audit, stress test e analisi di sensibilità

Tutti gli output sono esposti via libreria Python, dashboard Streamlit multi-pagina e container Docker pronto all'uso.

---

## Fondamenti metodologici

Il sistema implementa e integra tre metodologie accademicamente consolidate:

1. **Bilancio Medio Standardizzato (BMS)** — Scarano A., Brughera G.L.G., *Valutazione di una PMI con approccio settoriale*, Rivista AIAF n. 65, 2008. Approccio settoriale per PMI: invece di valutare direttamente l'impresa sul suo bilancio (volatile), si costruisce prima un'Impresa Media Standard del settore e si valuta la PMI per differenziale.
2. **Terminal Value coerente** — Scarano A., Di Napoli G., *Calcolo del Terminal Value e rispetto delle condizioni di coerenza*, Rivista AIAF n. 66, 2008. Lo studio Università di Bergamo mostra che il TV pesa in media il 64% del fair value e che il 10% dei report ha un TV incoerente: la suite implementa la formula con reinvestimento esplicito (`g = ROIC × h`) e i check automatici di coerenza.
3. **Agentic Credit Risk / RAPD** — Montesi G., Papiro G., *Risk Analysis Probability of Default: A Stochastic Simulation Model*, 2014. PD forward-looking via capital budgeting stocastico + Monte Carlo, con debito endogeno ricorsivo e condizione di default `EV < D − CASH`. Applicabile alle PMI e coerente multi-anno.

I tre paper condividono la stessa definizione di flusso di cassa (capital cash flow à la Ruback 2002) e lo stesso quadro WACC, il che permette di comporli in una pipeline unica che non introduce incoerenze tra valutazione e stima del rischio. Vedi `overview.md` per la sintesi completa di formule, integrazione e note implementative.

---

## Meccanismi decisionali di design

Le scelte non-banali fatte durante lo sviluppo sono motivate dai paper di riferimento e da un principio-guida: **evitare che lo stesso dato venga trattato in modo incoerente da moduli diversi**. Le 10 decisioni chiave qui sotto spiegano il "perché" dietro il codice — sono il riferimento quando si deve difendere un numero davanti al comitato crediti o al board.

### 1. Una sola definizione di cash flow in tutta la pipeline

DCF, Terminal Value coerente e simulatore Monte Carlo usano lo **stesso** flusso: `OCF = NOPAT − ΔNIC + τ·INT` (capital cash flow di Ruback 2002). Il tax shield del debito è esplicitamente dentro l'OCF.

**Perché**: usare FCFF post-tasse con WACC after-tax in un modulo e capital cash flow con WACC pre-tax in un altro porta a risultati incoerenti del 3–5% sullo stesso input. L'uniformità è un vincolo di architettura, non un dettaglio.

**Conseguenza operativa**: il simulator Agentic Credit Risk usa **pre-tax WACC** (`w_e·k_e + w_d·r_d` senza il fattore `(1−τ)` sul debito). Se si applicasse l'after-tax WACC al capital cash flow si farebbe doppio counting del tax shield.

### 2. Approccio settoriale per le PMI (BMS)

Il Bilancio Medio Standardizzato non è la somma line-by-line dei bilanci peer, ma la **media aritmetica delle quote normalizzate** su fatturato (CE) e totale attivo (SP).

**Perché**: la somma è dominata dal peer più grande. Nel paper Scarano/Brughera, con una Impresa A da 1.000 € di fatturato e una Impresa B da 3.000 €, la somma degli EBITDA è 1.200 € ma il BMS dà 533 € (la media delle quote 20% e 33%, moltiplicata per il fatturato medio di 2.000 €). La differenza — 22% di scostamento — è esattamente l'effetto dimensionale che il paper vuole eliminare.

**Conseguenza operativa**: ogni peer contribuisce **con peso 1/n** a prescindere dalla sua dimensione; il campione minimo raccomandato è ~20 imprese, ma il builder funziona anche sotto soglia (emette un flag `below_min_sample`).

### 3. Forward-looking Monte Carlo invece di scoring accounting-based

La PD non viene dedotta da rapporti di bilancio (Altman Z'') ma generata scenario per scenario variando stocasticamente i fondamentali (ricavi, margine, NFA, NWC) e verificando quante volte l'EV scende sotto il Net Debt.

**Perché**: gli scoring classici sono backward-looking (l'ultimo bilancio disponibile) e ottimizzati su imprese quotate. Il paper Montesi/Papiro mostra, su 46 imprese defaulted tra il 2003 e il 2011, che il modello stocastico anticipa il default di 1–3 anni rispetto all'Altman Z'' (mediana PD > 60% un anno prima del default vs < 20% per Altman).

**Conseguenza operativa**: la PD che il sistema restituisce è una **frequenza empirica** su 20.000 scenari coerenti, non una predizione puntuale. Va interpretata come "in questa percentuale di futuri plausibili l'impresa sarebbe insolvente".

### 4. Debito endogeno ricorsivo (eq. [7] del paper RAPD)

Il debito non è un input fisso ma **è risolto in forma chiusa** imponendo l'equilibrio finanziario `cash inflow = cash outflow` ogni periodo. La formula del codice è algebricamente equivalente all'eq. [7] del paper (dimostrazione nel test `test_solve_debt_paper_formula_equivalence`).

**Perché**: le PMI non seguono un piano di ammortamento predefinito. In pratica il debito è quello che serve per chiudere il gap tra NOPAT + cassa generata e ΔNIC + investimenti + dividendi. Fissare un piano esogeno introduce un errore di specificazione che si propaga al default check.

**Conseguenza operativa**: se il NOPAT cala sotto lo scenario base, il simulatore lo riflette automaticamente in un debito in crescita e, a un certo punto, in `EV < D − CASH` → default flaggato.

### 5. Distribuzioni Weibull + copula gaussiana

Le quattro variabili stocastiche (growth, margine, NFA/rev, NWC/rev) sono modellate come Weibull a 3 parametri (shape, loc, scale) con shape da paper (2 / 3.5 / 3.5 / 3). Le correlazioni cross-variabile e lag-1 sono imposte via copula gaussiana.

**Perché Weibull**: i ricavi hanno asimmetria positiva (eventi rari ma molto positivi, floor a valore minimo); le altre variabili sono più simmetriche ma comunque asimmetriche. Weibull cattura entrambe con un parametro di forma.

**Perché copula gaussiana**: scalare a distribuzioni multivariate Weibull è ingestibile. La copula permette di generare uniformi correlate e poi applicare l'inverso della CDF marginale variabile per variabile.

**Conseguenza operativa**: il flip di segno sulle correlazioni (`Corr(Sales, OpCost/Sales) = −0.4` diventa `Corr(Sales, EBITDA_margin) = +0.4`) è applicato una sola volta, nel factory `from_company()`, perché il simulatore usa `EBITDA_margin = 1 − OpCost/Sales`.

### 6. Terminal Value con formula coerente + shortcut steady-state

Il TV nel DCF 2 stadi usa la formula `TV = NOPAT·(1 − g/ROIC_NI)/(wacc − g)` (non la Gordon naive) che esplicita il vincolo di reinvestimento. Il DCF 3 stadi porta `ROIC` geometricamente a `WACC` durante lo stadio di convergenza e nel 3° stadio usa lo shortcut `TV = NOPAT/wacc`.

**Perché**: lo studio Università di Bergamo citato in Scarano/Di Napoli ha trovato che il **10% dei report di valutazione di aziende quotate europee ha un TV incoerente**. Il TV pesa in media il 64% del fair value, quindi l'errore si propaga sul valore totale. Imporre la formula coerente elimina il problema alla radice: non si può dichiarare `g = 3%` senza giustificarlo con un `ROIC_NI` e un `h` compatibili.

**Quando collassa**: se `ROIC_NI = WACC` (steady state, i nuovi investimenti rendono esattamente il costo del capitale), `(1 − g/ROIC) = (1 − g/wacc)` e il numeratore diventa `NOPAT·(wacc − g)/wacc`, che diviso per `(wacc − g)` dà `NOPAT/wacc` — la crescita non genera valore aggiuntivo.

### 7. Check di coerenza integrati dentro il risultato, non opzionali

Il risultato di `value_three_stage()` include automaticamente un `coherence_report` con 7 check (C1–C7) e un `verdict` aggregato (`PASS`, `WARNING`, `ERROR`).

**Perché**: il validatore opzionale è un validatore che nessuno chiama. L'integrazione forzata replica la raccomandazione operativa del paper Scarano/Di Napoli: "una buona policy di controllo qualità impone procedure che verifichino la coerenza tra `g`, `h_T = g/ROIC` e `wacc` in ogni valutazione".

**I 7 check**: C1 (`g ≤ g_PIL`), C2 (`g = ROIC × h`), C3 (formula coerente usata), C4 (`TV share ≤ 80%`), C5 (`ROIC_marginal → WACC`), C6 (bounds su segno e ordinamento), C7 (`h ∈ [0, 1]`).

### 8. Interest Tax Shield nel Terminal Value (post-audit)

Il TV del simulator include il tax shield dell'ultimo anno: `TV = NOPAT_T/k + τ·INT_T`, non solo `NOPAT_T/k`.

**Perché**: il paper RAPD (Appendice A) lo prescrive esplicitamente; l'omissione sovrastima sistematicamente la PD per società leveraged. L'impatto sul TV è ~5% per leva moderata, >10% per high yield. Questa correzione è stata fatta durante l'audit formule-vs-paper del 2026-04-08.

### 9. Rating implicito log-interpolato, non quantizzato

La master scale ha 22 classi con PD esponenzialmente crescenti (AAA 0.000% → D 100%). Una ricerca sequenziale restituirebbe sempre la classe "più vicina", quantizzando il rating su 22 slot discreti. Il sistema usa invece **interpolazione log-lineare** e restituisce una label continua.

**Perché**: una PD cumulata di 0.200% sta tra BBB+ (0.160%) e BBB (0.230%). La distanza log-lineare è `(log 0.200 − log 0.160)/(log 0.230 − log 0.160) ≈ 0.62`, quindi il rating è `"BBB+/BBB (0.62)"` — più vicino a BBB. Il comitato crediti ha un segnale più preciso di "appena sotto BBB+" rispetto a "BBB" secco.

### 10. Estensioni Appendice A opt-in con default retrocompatibili

Le estensioni del paper RAPD (cash yield, tax rate stocastico, payout, debt floor, collateral coverage, piano Capex esplicito, split long/short debt) sono tutte **opt-in** con default neutri che riproducono il "modello ridotto" della Sezione 2 del paper.

**Perché**: il modello ridotto è quello su cui Montesi/Papiro hanno fatto il back-testing empirico su 146 casi e su cui il paper è validato. Forzare le estensioni nel path di default comporterebbe rompere la riproducibilità dei risultati pubblicati. Il default retrocompatibile permette di attivare un pezzo alla volta e misurare l'effetto.

**Conseguenza operativa**: per riprodurre esattamente i numeri del paper, lasciare i default. Per stress test più realistici, attivare `cash_yield`, `tax_stochastic`, `collateral_coverage` uno alla volta osservando la derivata della PD cumulata.

---

## Come interpretare i risultati

Questa sezione risponde alla domanda "ok, ho il numero, ora come lo difendo?". Ogni sottosezione copre un output type con le invarianti che devono valere, i flag da controllare e gli edge case tipici.

### Enterprise Value e Equity Value

Il DCF restituisce `enterprise_value`, `equity_value` e una decomposizione `explicit_pv + convergence_pv + terminal_value_pv`.

**Cosa controllare sempre**:

1. `tv_weight` (peso del TV sull'EV): se > 80% il valore è dominato dalla perpetuity e la previsione esplicita conta poco. Il check C4 genera un WARNING in questo caso. Azione: allungare l'orizzonte esplicito o passare al DCF 3 stadi.
2. `coherence_report.verdict`: se è `ERROR`, il risultato non è utilizzabile. Se è `WARNING`, è utilizzabile con note esplicative. Se è `PASS`, è pronto per il board.
3. `fade_rate` (solo 3 stadi): deve essere negativo (ROIC scende verso WACC) e deve portare `current_roic` al WACC esattamente al termine dello stadio 2.

**Quando usare 2 stadi vs 3 stadi**: il 2 stadi è adatto quando il forecast esplicito arriva già al ROIC ≈ WACC (settori maturi, commodity). Il 3 stadi è obbligatorio se il forecast esplicito mostra un ROIC marginal ancora significativamente superiore al WACC alla fine del periodo — senza lo stadio di convergenza, il TV sarebbe troppo alto.

### Probabilità di default (PD 1/2/3y)

Il simulator restituisce tre versioni della PD con significati diversi:

| Versione | Formula | Interpretazione |
| --- | --- | --- |
| **Yearly default frequency** | `P(EV_t < D_t − CASH_t)` | Fragilità finanziaria nell'anno `t`, indipendentemente da quello che succede prima. Include trial che hanno già defaultato. |
| **Marginal PD** | `P(default in t \| no default prima)` | Probabilità che il default avvenga proprio nell'anno `t`, condizionata alla sopravvivenza fino a `t−1`. |
| **Cumulative PD** | `P(default entro l'anno t)` | Frazione di trial che hanno defaultato almeno una volta entro `t`. Equivale a `1 − ∏ (1 − marg_i)`. |

**Come usarle**:

- Per il comitato crediti: **cumulative PD a 3 anni** è il numero principale (allineato a Basel 2 IRB).
- Per lo stress test: **yearly default frequency** mostra la distribuzione temporale del rischio.
- Per pricing del debito: **marginal PD** anno per anno costruisce una curva spread che cresce nel tempo.

**Non è una previsione puntuale**. Il numero non dice "questa impresa fallirà nel 5% dei casi" in senso bayesiano; dice "dati i parametri stocastici del settore e il bilancio attuale, il 5% degli scenari plausibili porta l'EV sotto il Net Debt entro 3 anni". Il margine di errore a 20.000 trial è tipicamente < 50 bps sulla cumulativa.

### LGD, Expected Loss, Unexpected Loss

Calcolate solo sui trial che effettivamente defaultano:

- `lgd_mean`: perdita media nel paniere dei trial in default (in unità monetarie). Con `collateral_coverage > 0`, è al netto del recupero secured.
- `expected_loss = cum_PD × lgd_mean`: perdita attesa sul portafoglio, in unità monetarie. Usa direttamente la media dell'LGD assoluto (non `LGD% × EAD`), che è equivalente a meno di correlazione LGD-EAD.
- `unexpected_loss_95 / _99`: LGD al 95°/99° percentile condizionale al default. È l'equivalente del VaR per la perdita: "quanto potrei perdere nel peggior 5%/1% dei default".

**Recovery rate**: `1 − LGD_mean / EAD_mean`. Nel paper RAPD il recovery medio del campione empirico è ~38%, con correlazione PD–recovery `−0.70`. Il sistema riproduce questa correlazione negativa se la simulazione include un numero sufficiente di default.

### Analisi differenziale target vs Impresa Media Standard

Il Differential Analyzer scompone il premio/sconto del target rispetto al BMS in 4 driver:

- **margine operativo**: target vs BMS EBITDA/Revenues
- **crescita attesa**: target vs BMS CAGR
- **leva finanziaria**: target vs BMS Debt/Equity
- **capital intensity**: target vs BMS NIC/Revenues

La somma dei 4 contributi non coincide mai esattamente con il gap totale di equity value (gli effetti interagiscono), ma le direzioni dei driver dicono dove il target batte o perde contro il settore.

**Esempio dataset sintetico** (`data/synthetic/`): Riva Meccanica SpA ha margine 17% vs settore 14%, crescita 7% vs 4.5%, leva 34% vs 41%. L'analisi differenziale attribuisce il premio principalmente a margine (+8%) e crescita (+5%), con un contributo minore dalla minore leva. Questo dà al comitato un appiglio operativo: "paghiamo il premio perché il management ha dimostrato di difendere il margine sopra la media, non perché rischia di più".

### Quando fidarsi e quando no

| Segnale | Azione |
| --- | --- |
| `coherence_report.verdict == ERROR` | Non usare il risultato. Rivedere gli input. |
| `coherence_report.verdict == WARNING` | Usare con nota esplicativa. Mostrare i check warning al comitato. |
| `below_min_sample == True` (BMS con < 20 peer) | Il settore è troppo stretto o c'è un problema di filtro. Allargare il campione o motivare la scelta. |
| `tv_weight > 0.80` | Il DCF è dominato dal TV → poco affidabile. Passare a 3 stadi o allungare l'orizzonte. |
| `cumulative_pd[-1] == 0` su 20.000 trial | L'azienda è molto sana. OK, ma verificare i parametri Weibull del settore: se sono tarati male la distribuzione ha troppa poca varianza. |
| `cumulative_pd[-1] > 0.50` su 20.000 trial | L'azienda è in stress estremo. Verificare che non ci sia un errore di segno sul debito o sul NOPAT iniziale. |
| `implied_rating` cambia di più di 2 notch cambiando il seed | La varianza Monte Carlo è troppo alta per il numero di trial scelto. Aumentare `n_trials` o ridurre la varianza dei parametri Weibull. |

---

## Quickstart

Per i prerequisiti completi (hardware, versioni, dati, checklist pre-volo e troubleshooting) vedi [`requirements.md`](requirements.md).

### Locale

```bash
# Install in editable mode con dev + app extras
pip install -e ".[dev,app]"

# Rigenera il dataset principale (reale, da export AIDA in data/real/)
python3 data/etl/aida_to_companies.py

# Rigenera la fixture sintetica per test/demo (16 aziende × 3 anni, seed fisso)
python3 data/generators/seed_companies.py

# Test suite
pytest

# Dashboard Streamlit (dati reali; RV_DATA_DIR=data/synthetic per la demo sintetica)
streamlit run app/Rating_Valuation_Suite.py
```

### Docker

```bash
docker compose up --build
# poi apri http://localhost:8501
```

Il container è basato su `python:3.11-slim`, gira come non-root ed espone un healthcheck su `/_stcore/health`.

---

## Dataset

### Dataset principale: dati reali AIDA (`data/*.csv`)

Da luglio 2026 il dataset principale della suite è reale: **277 società italiane del commercio all'ingrosso di metalli (ATECO 4672)**, esercizi 2020–2024, estratte da AIDA (Bureau van Dijk) con filtro ricavi 2024 tra 5 e 20 M€ e sede in Nord/Centro Italia. Gli export grezzi sono in `data/real/20XX-ME.xlsx`; l'ETL `data/etl/aida_to_companies.py` li riclassifica e scrive i CSV conformi allo schema direttamente in `data/`.

**Decisioni di riclassificazione** (concordate con il gruppo di lavoro, dettaglio completo in `data/mapping_iv_directive.md`):

1. **Outlier per immobilizzazioni finanziarie**: le società con partecipazioni/crediti finanziari immobilizzati **> 10% del totale attivo in almeno un anno** sono escluse dal campione (43 su 320). Motivazione: quelle poste non generano EBITDA e distorcerebbero ROIC, intensità di capitale del BMS e distribuzione NFA/Ricavi del Monte Carlo. Per le società rimaste, le immobilizzazioni finanziarie (ormai marginali) restano nel capitale investito.
2. **Oneri finanziari**: AIDA espone solo il saldo netto della gestione finanziaria; `interest_expense` è il saldo negativo (proxy, oneri lordi non disponibili).
3. **NWC come residuo**: `NWC = NIC − NFA` con `NIC = PN + PFN`, così TFR e fondi (non esposti dall'export) restano impliciti e gli invarianti di bilancio chiudono per costruzione (0 violazioni su 1.329 bilanci).
4. **Target**: estratto casualmente con seed fisso (42) tra le società con panel 2020–2024 completo → **TRAFER SPA** (`company_id = trafer_spa`). Nota: il sorteggio ha selezionato un credito debole (ricavi da 20,7 a 7,5 M€ tra 2022 e 2024, PD simulata a 1 anno ≈ 93%, rating implicito C/D) — un caso realistico per il comitato crediti; per un target diverso basta cambiare `TARGET_SEED` nell'ETL.
5. **Chiave settoriale**: `gics_sub_industry = "Metals Wholesale (ATECO 4672)"` coerente tra `companies.csv` e `sectors.csv`; beta unlevered 0,75 (Damodaran, Trading Companies & Distributors Europa), shape Weibull di default dal paper RAPD; macro IT 2020–2024 da fonti pubbliche (stime da raffinare per valutazioni puntuali).

**Limite noto**: il simulatore di credito richiede un margine EBITDA atteso positivo; sulle ~19 società 2024 in perdita operativa `from_company()` solleva errore — vanno filtrate a monte.

### Dataset sintetico per test e demo (`data/synthetic/*.csv`)

La fixture deterministica storica resta disponibile: 16 aziende × 3 anni (2022–2024) del settore **Industrial Machinery**, 15 peer + 1 target (**Riva Meccanica SpA**, costruita sopra la media di settore per un'analisi differenziale dimostrativa). Si rigenera con `python3 data/generators/seed_companies.py` ed è il dataset su cui gira la test suite. Per usarla nella dashboard: `RV_DATA_DIR=data/synthetic streamlit run app/Rating_Valuation_Suite.py`.

Qualunque nuovo dataset reale deve rispettare lo schema documentato in `data/schema.md` (stessi nomi colonna, stesse unità: monetari in milioni di valuta, tassi come decimali). Il sistema valida lo schema automaticamente al caricamento.

---

## Mappa della documentazione

Ogni documento ha un ruolo preciso — partire da qui per capire cosa leggere:

| Documento | Ruolo | Per chi |
| --- | --- | --- |
| **README.md** (questo file) | Executive summary, decisioni di design, interpretazione dei risultati, quickstart | Primo contatto, board, comitato |
| [`requirements.md`](requirements.md) | Prerequisiti completi: hardware, installazione (locale/Docker), dati, checklist pre-volo, troubleshooting | Analista che deve installare ed eseguire |
| [`overview.md`](overview.md) | Sintesi teorica dei 3 paper: tutte le formule, il quadro integrato, le note implementative | Chi deve capire o difendere la metodologia |
| [`TODO.md`](TODO.md) | Stato di sviluppo e backlog con priorità | Chi pianifica gli interventi |
| [`data/schema.md`](data/schema.md) | Schema autoritativo dei CSV (colonne, unità, invarianti) | Chi prepara i dati |
| [`data/mapping_iv_directive.md`](data/mapping_iv_directive.md) | Mapping IV Direttiva (AIDA) → schema e decisioni di riclassificazione del dataset reale | Chi fa onboarding di bilanci reali |
| [`Capitolo_doc.md`](Capitolo_doc.md) | Capitolo editoriale: architettura, capability e fondamenti (per pubblicazione) | Lettori del Quaderno |
| [`CLAUDE.md`](CLAUDE.md) | Guida all'architettura per agenti Claude Code | Sviluppo assistito da AI |

## Struttura del repository

```text
rating_valuation/
├── README.md                      questo file — punto d'ingresso
├── requirements.md                prerequisiti di installazione ed esecuzione
├── overview.md                    sintesi completa dei 3 paper + quadro integrato
├── Capitolo_doc.md                capitolo editoriale sulla suite
├── CLAUDE.md                      guida all'architettura per agenti Claude Code
├── TODO.md                        stato sviluppo + backlog post-audit
├── data/                          dataset principale (reale AIDA) + schema + ETL
│   ├── real/                      export AIDA grezzi (xlsx) + benchmark GDO separato
│   ├── etl/                       ETL AIDA → CSV schema (aida_to_companies.py)
│   ├── synthetic/                 fixture sintetica deterministica (test/demo)
│   └── generators/                generatore della fixture sintetica
├── src/rating_valuation/          libreria Python (common, bms, dcf, agentic_credit_risk, rating, backtest)
├── app/                           dashboard Streamlit multi-page
├── tests/                         pytest test suite
├── examples/                      script end-to-end di esempio
├── deploy/                        deploy AWS ECS Express (deploy.sh)
├── docs/                          PDF originali dei 3 paper di riferimento
└── .claude/agents/                subagent specializzati per analisi approfondite
```

## Stato del progetto

Tutti i tool principali sono a produzione e coperti da una test suite di 188 test che gira in meno di un secondo. Il dataset principale è reale (AIDA, ATECO 4672) e la dashboard è deployata su AWS ECS. L'elenco dettagliato delle funzionalità completate e il backlog delle correzioni aperte (con priorità) sono in [`TODO.md`](TODO.md).

---

## Riferimenti accademici

- Scarano A., Brughera G.L.G., *Valutazione di una PMI con approccio settoriale*, Rivista AIAF n. 65, 2008.
- Scarano A., Di Napoli G., *Calcolo del Terminal Value (TV) e rispetto delle condizioni di coerenza*, Rivista AIAF n. 66, 2008.
- Montesi G., Papiro G., *Risk Analysis Probability of Default: A Stochastic Simulation Model*, Draft, 2014.
- Ruback R.S., *Capital Cash Flows: A Simple Approach to Valuing Risky Cash Flows*, Financial Management 31, 2002.
- Altman E.I., *Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy*, Journal of Finance, 1968.
- Merton R.C., *On the Pricing of Corporate Debt*, Journal of Finance, 1974.

I PDF originali dei tre paper metodologici principali sono in `docs/`.
