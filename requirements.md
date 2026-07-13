# Requirements — Prerequisiti per eseguire la Rating & Valuation Suite

Questo documento elenca tutto ciò che serve per **installare, configurare ed eseguire** la suite, in due scenari alternativi (locale Python oppure container Docker) e con i prerequisiti di **dati** e **parametri** che l'analista deve predisporre prima della prima valutazione.

L'obiettivo è che, leggendo solo questo documento, un analista nuovo al progetto possa:

1. preparare la macchina,
2. installare l'applicazione,
3. caricare i propri dati,
4. lanciare la prima analisi.

---

## 1. Prerequisiti hardware e sistema operativo

| Componente | Requisito minimo | Raccomandato |
|---|---|---|
| CPU | 2 core x86-64 / Apple Silicon | 4+ core (per Monte Carlo a 20.000 trial) |
| RAM | 4 GB | 8 GB+ (la simulazione tiene matrici `n_trials × n_years × variabili` in memoria) |
| Disco | 1 GB libero (codice + dipendenze) | 5 GB se si tengono dataset reali e cache Streamlit |
| Sistema operativo | macOS 12+ / Ubuntu 22.04+ / Windows 10+ con WSL2 | indifferente, purché supporti Python 3.11 o Docker Desktop |
| Connettività | Solo per il `pip install` iniziale | Nessuna connessione a internet richiesta a runtime |

Il calcolo è interamente in-memory: non c'è database, non c'è coda di job, non ci sono servizi esterni a runtime.

---

## 2. Prerequisiti software — scenario A: installazione locale Python

### 2.1 Runtime

- **Python ≥ 3.11** (vincolato in `pyproject.toml`).
  Verificare con `python3 --version`. Se la macchina ha una versione precedente, installare 3.11+ con `pyenv` (Mac/Linux) oppure dall'installer ufficiale [python.org](https://www.python.org/) (Windows). La suite usa pattern e annotazioni introdotti in 3.10/3.11 (es. `match`, generics moderni).

- **pip ≥ 23** e **virtualenv** (o equivalente). Si consiglia di creare un ambiente isolato:

  ```bash
  python3.11 -m venv .venv
  source .venv/bin/activate     # macOS / Linux
  # .venv\Scripts\activate      # Windows PowerShell
  ```

### 2.2 Dipendenze runtime (libreria + simulatore)

Installate automaticamente da `pip install -e .`. Versioni minime dichiarate in `pyproject.toml`:

| Pacchetto | Versione minima | Uso |
|---|---|---|
| `pandas` | ≥ 2.0 | Caricamento e manipolazione CSV, DataFrame strutturati |
| `numpy` | ≥ 1.24 | Vettorizzazione Monte Carlo, algebra matriciale |
| `scipy` | ≥ 1.10 | Distribuzioni Weibull, copula gaussiana, statistiche di test (KS, AUROC) |

Nessun'altra dipendenza è richiesta per usare la libreria via API Python.

### 2.3 Dipendenze opzionali — dashboard Streamlit (`[app]`)

Necessarie solo se si usa la dashboard web invece dell'API Python. Installate con `pip install -e ".[app]"`:

| Pacchetto | Versione minima | Uso |
|---|---|---|
| `streamlit` | ≥ 1.30 | Dashboard multi-pagina |
| `plotly` | ≥ 5.18 | Grafici interattivi (PD curves, distribuzioni, confronti) |

### 2.4 Dipendenze opzionali — sviluppo (`[dev]`)

Necessarie solo per chi modifica il codice o esegue la test suite. Installate con `pip install -e ".[dev]"`:

| Pacchetto | Versione minima | Uso |
|---|---|---|
| `pytest` | ≥ 7.4 | Test runner |
| `pytest-cov` | ≥ 4.1 | Coverage report |
| `ruff` | ≥ 0.3 | Linter + formatter |

### 2.5 Comando di installazione completo

Da repository root, in un virtualenv attivo:

```bash
# Solo libreria + simulatore (uso programmatico)
pip install -e .

# Libreria + dashboard Streamlit (uso interattivo)
pip install -e ".[app]"

# Tutto (sviluppo + test + dashboard)
pip install -e ".[dev,app]"
```

Il flag `-e` (editable) permette di modificare il codice in `src/` senza dover reinstallare il pacchetto.

### 2.6 Verifica installazione

```bash
# Test suite (deve restituire ~188 test passati, < 1 secondo)
pytest

# Smoke test rapido via API
python3 -c "from rating_valuation.bms import BMSBuilder; print('OK')"

# Lancio dashboard
streamlit run app/Rating_Valuation_Suite.py
# → apre il browser su http://localhost:8501
```

---

## 3. Prerequisiti software — scenario B: container Docker

Alternativa per chi non vuole gestire Python sulla macchina locale o vuole deployare la suite su un server interno.

### 3.1 Runtime

- **Docker Engine ≥ 24** oppure **Docker Desktop** (Mac/Windows).
- **docker compose ≥ 2.20** (incluso in Docker Desktop; su Linux server installare `docker-compose-plugin`).

### 3.2 Avvio

Da repository root:

```bash
# Build + run, primo lancio (la build scarica python:3.11-slim + dipendenze, ~3 minuti)
docker compose up --build

# Run successivi (immagine già in cache)
docker compose up

# Stop
docker compose down
```

La dashboard è esposta su `http://localhost:8501`.

### 3.3 Caratteristiche del container

- Base: `python:3.11-slim` (Debian-derived, ~120 MB prima dei pacchetti).
- Utente non-root (`appuser`, UID 1000) per ridurre la superficie di attacco.
- Healthcheck su `/_stcore/health` con intervallo 30 s.
- Cartella `data/` montata in **read-only** dal compose (`./data:/app/data:ro`): le modifiche ai CSV sulla macchina host sono visibili al container senza rebuild, ma il container non può scrivere sui dati.
- Variabili d'ambiente Streamlit pre-configurate per modalità headless (server-side, no analytics, no telemetria).

### 3.4 Modalità sviluppo (live reload)

```bash
DEV_MOUNT=1 docker compose up
```

Monta il repo intero in `/app`: le modifiche al codice in `src/` o `app/` sono picked up dal hot-reload di Streamlit.

---

## 4. Prerequisiti dati

Per eseguire una valutazione la suite legge quattro file CSV in `data/`. Lo schema è documentato in dettaglio in `data/schema.md`. Qui riportiamo solo l'essenziale.

### 4.1 Convenzioni comuni a tutti i CSV

- Separatore: `,`
- Encoding: `UTF-8`
- Decimal separator: `.`
- Valori mancanti: cella vuota (no `NaN`, `NA`, `NULL`)
- Valori monetari: **milioni** della valuta indicata nella colonna `currency` (es. EUR 1,5 mln → `1.5`)
- Tassi e percentuali: **decimali** (es. 28 % → `0.28`)
- Date: anno fiscale come intero `YYYY`

### 4.2 `companies.csv` — bilanci riclassificati

Una riga per coppia `(company, fiscal_year)`. Contiene il bilancio gestionale riclassificato del target e di tutti i peer di settore.

**Colonne minime obbligatorie** (subset; elenco completo in `data/schema.md` §1):

- Identificativo: `company_id`, `company_name`, `is_target` (0/1), `country`, `currency`, `gics_sector`, `gics_sub_industry`, `fiscal_year`
- Conto economico: `revenues`, `operating_costs`, `ebitda`, `depreciation_amortization`, `ebit`, `interest_expense`, `pre_tax_income`, `taxes`, `net_income`, `nopat`
- Stato patrimoniale riclassificato: `net_fixed_assets` (NFA), `net_working_capital` (NWC), `net_invested_capital` (NIC), `gross_debt`, `cash`, `net_debt`, `equity`, `total_assets`
- Flussi e parametri: `capex`, `cost_of_debt`, `corporate_tax_rate`

**Invarianti che il loader verifica** (tolleranza `0,01` nell'unità monetaria):

- `ebitda = revenues − operating_costs`
- `ebit = ebitda − depreciation_amortization`
- `net_invested_capital = net_fixed_assets + net_working_capital`
- `net_debt = gross_debt − cash`
- `equity ≈ net_invested_capital − net_debt`

Una violazione fa fallire il caricamento. La riclassificazione corretta è prerequisito, non suggerimento.

**Numerosità minima del campione**: il paper Scarano/Brughera raccomanda almeno **20 peer** di settore (più il target). Sotto soglia il BMSBuilder funziona ma marca il risultato con `below_min_sample = True`.

### 4.3 `sectors.csv` — parametri di settore

Una riga per ogni `gics_sub_industry` rappresentato in `companies.csv`. Contiene:

- `beta_unlevered` — beta unlevered mediano del settore (per CAPM).
- Parametri Weibull: `weibull_revenues_shape` (default 2), `weibull_opcosts_shape` (3.5), `weibull_nfa_shape` (3.5), `weibull_nwc_shape` (3).
- Autocorrelazioni: `autocorr_revenues` (0.2), `autocorr_opcosts` (0.3), `autocorr_nfa` (0.5), `autocorr_nwc` (0.4).
- Cross-correlazioni: `corr_sales_opcosts` (−0.4), `corr_nfa_opcosts` (−0.2), `corr_sales_nfa` (+0.2), `corr_sales_nwc` (−0.3).

I valori in parentesi sono i default del paper RAPD Appendice A. Possono essere usati così come sono, oppure tarati su dati di settore reali se disponibili.

### 4.4 `macro.csv` — parametri macro country-year

Una riga per ogni coppia `(country, year)` rilevante per le valutazioni.

- `gdp_real_growth` — PIL reale.
- `inflation_rate` — inflazione CPI.
- `gdp_nominal_growth_5y_avg` — media a 5 anni del PIL nominale, **usata** dal check di coerenza C1 del TV (`g ≤ g_PIL`) e per la centratura della distribuzione dei ricavi nel simulatore.
- `risk_free_rate_10y` — rendimento del govvy decennale del paese.
- `market_risk_premium` — MRP. Per Eurozona il paper RAPD usa 5 %.
- `credit_spread_bbb` — spread medio investment grade BBB (riferimento).

### 4.5 `rating_master_scale.csv` — master scale Rating ↔ PD

Tabella di 22 righe (AAA → D). Già fornita con il repo, valori dal paper RAPD Appendice A. Non va modificata.

### 4.6 Dataset già pronti nel repo

Il repo include **due dataset completi**, entrambi conformi allo schema:

- **Dataset principale (reale)** — `data/*.csv`: 277 società italiane del commercio all'ingrosso di metalli (ATECO 4672), esercizi 2020–2024, da export AIDA; target `trafer_spa` (estrazione casuale, seed 42). È quello che libreria e dashboard caricano di default. Si rigenera dagli xlsx grezzi in `data/real/` con:

  ```bash
  python3 data/etl/aida_to_companies.py
  ```

  Le regole di riclassificazione sono documentate in `data/mapping_iv_directive.md`.

- **Dataset sintetico (demo/test)** — `data/synthetic/*.csv`: 16 imprese × 3 esercizi (2022–2024) del settore Industrial Machinery (15 peer + 1 target, *Riva Meccanica SpA*). È la fixture deterministica della test suite; per usarlo nella dashboard: `RV_DATA_DIR=data/synthetic streamlit run app/Rating_Valuation_Suite.py`. Si rigenera con seed fisso da:

  ```bash
  python3 data/generators/seed_companies.py
  ```

---

## 5. Prerequisiti analitici (lato analista)

Anche con codice e dati a posto, una valutazione corretta richiede che l'analista predisponga in anticipo alcuni elementi.

### 5.1 Riclassificazione del bilancio

I bilanci civilistici italiani (IV Direttiva) e quelli IFRS non sono direttamente nello schema della suite. È richiesta una riclassificazione gestionale — per gli export AIDA esiste già un ETL pronto (`data/etl/aida_to_companies.py`, regole in `data/mapping_iv_directive.md`) — che produca:

- **NIC = NFA + NWC** dove:
  - NFA = immobilizzazioni materiali + immateriali + finanziarie nette − fondo TFR/altri fondi operativi (se non separati)
  - NWC = crediti commerciali + magazzino − debiti commerciali − altre passività operative correnti
- **Net Debt = debito finanziario lordo − cassa e equivalenti**, separato dalla parte commerciale.
- **NOPAT = EBIT × (1 − τ)** con `τ` aliquota fiscale nominale del paese (per uniformità cross-impresa) oppure aliquota effettiva `taxes / pre_tax_income` per dati reali.

La suite non fa questa riclassificazione: si aspetta in input lo schema riclassificato. Il documento `data/mapping_iv_directive.md` (in roadmap) tracerà il mapping puntuale per i bilanci italiani.

### 5.2 Selezione del campione settoriale

La rappresentatività del BMS dipende dalla qualità del campione. Criteri suggeriti dal paper Scarano/Brughera:

- **Omogeneità di settore**: stesso `gics_sub_industry` (livello 4 GICS), non solo stesso settore di primo livello.
- **Omogeneità geografica**: stesso paese o area economica (Eurozona, EU, Nord America). Mescolare US e EU introduce confonditori da regime fiscale e da dinamica macro.
- **Omogeneità dimensionale**: evitare di mescolare grandi corporate quotate con micro-PMI. Lo screening via `outlier_sigma` rimuove i peer con fatturato oltre k σ dalla media.
- **Numerosità**: ≥ 20 peer per la "legge dei grandi numeri" del paper. Sotto soglia, documentare la motivazione.
- **Periodo storico**: stessi esercizi fiscali per tutti i peer (la BMS è un fotogramma annuale; il time-series si costruisce su più fotogrammi).

### 5.3 Parametri di valutazione (DCF)

Per il DCF servono input che non sono in `companies.csv` ma vanno prodotti dall'analista:

- **Forecast esplicito** del target (e/o dell'IMS) per 5–8 anni: NOPAT, ΔNIC, OCF anno per anno.
- **Tasso di crescita di lungo periodo `g`** del Terminal Value: vincolato sopra dal `gdp_nominal_growth_5y_avg` di `macro.csv`.
- **`ROIC_NI` di steady state**: tipicamente uguagliato al WACC nel 3° stadio, oppure stimato endogenamente come ROIC marginale mediano dello stadio 1 (helper `median_roic_marginal_from_explicit`).
- **Orizzonte dello stadio di convergenza** (solo 3 stadi): tipicamente 5–10 anni.

### 5.4 Parametri Monte Carlo (Agentic Credit Risk)

Il simulatore è già configurato con i default del paper RAPD ma l'analista può modificare:

- `n_trials` — default 20.000. Aumentare a 50.000+ se si analizzano imprese al limite (PD < 0,5 % o > 50 %).
- `n_years` — default 3. Allineato a Basel 2 IRB-A; può essere esteso a 5 per obiettivi di pricing del debito a medio termine.
- `seed` — default 42. Mantenere fisso per riproducibilità; cambiare seed per stimare la varianza Monte Carlo del rating implicito.

---

## 6. Prerequisiti di rete e sicurezza (deployment in azienda)

Se la suite è installata su un server interno per uso da parte del comitato crediti / del team di valuation:

- **Nessuna connessione internet richiesta a runtime.** Tutto il calcolo è locale.
- **Connessione internet richiesta solo per**:
  - `pip install` iniziale (PyPI),
  - `docker pull` di `python:3.11-slim` (Docker Hub) al primo build,
  - eventuali aggiornamenti di dipendenze.
- **Porte**: solo `8501/tcp` per la dashboard Streamlit. Nessun'altra porta esposta dal container.
- **Dati sensibili**: i CSV in `data/` contengono bilanci. Trattarli secondo le policy aziendali per i dati finanziari (cifratura at-rest, accesso ristretto). Nel container i dati sono montati in read-only.
- **Audit trail**: Streamlit non logga gli input dell'utente per default. Se serve un audit trail (decisioni del comitato crediti), implementarlo a livello di reverse proxy davanti a Streamlit, oppure aggiungere logging applicativo in `app/_common.py`.
- **Autenticazione**: la dashboard non implementa autenticazione nativa. In ambiente enterprise va deployata dietro un reverse proxy con SSO (OIDC, SAML) o restringere l'accesso a una VPN interna.

---

## 7. Checklist pre-volo

Prima di lanciare la prima valutazione:

**Macchina**

- [ ] Python ≥ 3.11 installato (oppure Docker Desktop attivo)
- [ ] virtualenv creato e attivato
- [ ] `pip install -e ".[app]"` completato senza errori
- [ ] `pytest` passa tutti i ~188 test in < 1 secondo
- [ ] `streamlit run app/Rating_Valuation_Suite.py` apre la dashboard sul browser

**Dati**

- [ ] `companies.csv` contiene il target con `is_target=1` e ≥ 20 peer dello stesso `gics_sub_industry`
- [ ] tutte le invarianti di bilancio passano (caricamento senza errori)
- [ ] `sectors.csv` ha una riga per il `gics_sub_industry` del target
- [ ] `macro.csv` ha una riga per il `country` del target nell'anno della valutazione
- [ ] `rating_master_scale.csv` non è stato modificato

**Parametri di valutazione**

- [ ] forecast esplicito del target (NOPAT, ΔNIC, OCF) disponibile per ≥ 5 anni
- [ ] `g` di lungo periodo scelto e ≤ `gdp_nominal_growth_5y_avg` del paese
- [ ] `ROIC_NI` di steady state definito (default: WACC)
- [ ] orizzonte stadio di convergenza definito (solo 3 stadi)

Quando tutte le caselle sono spuntate, la suite è pronta a produrre numeri difendibili.

---

## 8. Tabella riepilogativa rapida

| Cosa | Minimo | Dove trovarlo |
|---|---|---|
| Python | 3.11 | [python.org](https://www.python.org/) o `pyenv` |
| Pacchetti runtime | `pandas`, `numpy`, `scipy` | `pip install -e .` |
| Pacchetti dashboard | `streamlit`, `plotly` | `pip install -e ".[app]"` |
| Pacchetti test | `pytest`, `pytest-cov`, `ruff` | `pip install -e ".[dev]"` |
| Alternativa container | Docker ≥ 24 + compose ≥ 2.20 | `docker compose up --build` |
| Bilanci target + peer | ≥ 20 peer dello stesso GICS sub-industry | `data/companies.csv` |
| Parametri settore | beta unlevered, Weibull shapes, correlazioni | `data/sectors.csv` |
| Parametri macro | risk-free, MRP, PIL nominale 5y | `data/macro.csv` |
| Master scale rating | 22 classi AAA → D, PD 1y | `data/rating_master_scale.csv` (già nel repo) |
| Dataset reale (principale) | 277 imprese ATECO 4672, 2020–2024 | `data/*.csv` (rigenerabile: `python3 data/etl/aida_to_companies.py`) |
| Dataset sintetico (demo/test) | 16 imprese Industrial Machinery 2022–2024 | `data/synthetic/` (rigenerabile: `python3 data/generators/seed_companies.py`) |

---

## 9. Quando qualcosa non torna

Errori più comuni e dove guardare:

| Sintomo | Causa probabile | Fix |
|---|---|---|
| `SchemaError: missing column 'nopat'` al caricamento | CSV non aderente allo schema | Confrontare le colonne con `data/schema.md` §1 |
| `InvariantViolation: ebitda != revenues − operating_costs` | Errore di riclassificazione | Verificare che `operating_costs` non includa D&A |
| `BMSResult.below_min_sample == True` | < 20 peer nel campione | Allargare il filtro o documentare la scelta |
| `coherence_report.verdict == ERROR` | TV con `g > g_PIL` o `h ∉ [0,1]` | Rivedere il `g` o il `ROIC_NI` |
| PD = 0 o PD = 1 su 20.000 trial | Varianza Weibull troppo bassa o input degenerati | Controllare i parametri di `sectors.csv` e il NOPAT iniziale |
| Streamlit non parte | Porta 8501 occupata | `streamlit run --server.port 8502 app/Rating_Valuation_Suite.py` |
| Container non risponde | Healthcheck fallito | `docker logs rating-valuation-streamlit` |

Per problemi più sottili (rating implicito instabile, TV anomalo) consultare la sezione "Quando fidarsi e quando no" del `README.md`.
