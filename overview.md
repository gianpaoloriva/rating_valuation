# Rating & Valuation — Overview

Questa cartella contiene tre documenti che, letti insieme, definiscono un quadro coerente di **valutazione d'impresa** (DCF, Terminal Value, approccio settoriale per PMI) e di **stima del rischio di credito forward-looking** (Agentic Credit Risk). I tre lavori condividono lo stesso impianto concettuale (capital budgeting + flussi di cassa attesi + WACC) e si prestano a essere implementati come una suite integrata di strumenti.

---

## 1. Bilancio Medio Standardizzato (BMS) — valutazione PMI con approccio settoriale

**Fonte:** *Valutazione di una PMI con approccio settoriale* — Alfonso Scarano, Giorgio L.G. Brughera, Rivista AIAF n. 65 (dic. 2007/gen. 2008), pp. 45–49.

### Idea centrale
Per valutare una PMI il dato puntuale del singolo bilancio è troppo volatile e poco rappresentativo. L'approccio proposto **rovescia la prospettiva**: si parte dal settore, si costruisce un'**Impresa Media Standard (IMS)** rappresentativa, la si valuta con DCF, e poi si valuta la PMI obiettivo per **differenziale** rispetto all'IMS.

### Costruzione del Bilancio Medio Standardizzato (BMS)
Il BMS **non è una semplice somma** dei bilanci del campione (la somma sarebbe dominata dalle aziende più grandi). È invece una **media normalizzata** in cui ciascuna impresa pesa allo stesso modo:

**Conto economico — voce i-esima:**
```
Ce_i = (1/n) Σ_j (ce_{i,j} / Fatturato_j)  ×  (1/n) Σ_j Fatturato_j
```

**Stato patrimoniale — voce i-esima:**
```
Sp_i = (1/n) Σ_j (sp_{i,j} / TotaleAttivo_j)  ×  (1/n) Σ_j TotaleAttivo_j
```

Procedimento operativo:
1. Per ogni impresa j, normalizzare ogni voce di CE sul fatturato e ogni voce di SP sul totale attivo.
2. Calcolare la media delle voci normalizzate (percentuali) sul campione.
3. Calcolare il fatturato medio e l'attivo medio del campione.
4. Moltiplicare le percentuali medie per il fatturato medio (CE) e per l'attivo medio (SP).

### Selezione del campione
- Almeno **una ventina di imprese** omogenee e coerenti (settore, dimensione, area geografica).
- La scelta è discrezionale: l'analista deve documentare i criteri e tendere alla "legge dei grandi numeri".

### Applicazione del BMS
1. **Storico**: costruire un BMS annuale per più esercizi → individuare punti di flesso, criticità e virtuosità del settore.
2. **Previsione**: stimare scenari prospettici sull'IMS più stabili di quelli sulla singola impresa.
3. **Valutazione DCF dell'IMS** → valore di riferimento del settore.
4. **Analisi differenziale** della singola PMI rispetto al BMS, isolando le peculiarità (positive o negative) e il loro peso sul valore.
5. Confronto BMS vs "bilancio somma" del settore (line-by-line) per evidenziare l'effetto dimensionale.

---

## 2. Calcolo del Terminal Value e condizioni di coerenza

**Fonte:** *Calcolo del Terminal Value (TV) e rispetto delle condizioni di coerenza* — Alfonso Scarano, Giuseppe Di Napoli, Rivista AIAF n. 66 (apr. 2008), pp. 27–32.

### Problema affrontato
Una ricerca dell'Università di Bergamo su circa 800 report di valutazione di società quotate europee rileva che **~10% dei report ha un TV incoerente** con la logica del DCF sottostante. Il TV pesa in media il **64%** della valutazione complessiva: gli errori nel TV inquinano in modo significativo il fair value.

### Modello DCF a 2 stadi (formulazione standard)
```
Valore Impresa = Σ_{t=1..T} FCFF_t / (1+wacc)^t  +  TV / (1+wacc)^T

TV = FCFF_T · (1+g) / (wacc_{T+1} - g)
```
con `g` = tasso di crescita di lungo periodo.

### Condizioni di coerenza
Tre scelte metodologiche dell'analista determinano la qualità del TV:
1. Scelta dell'orizzonte di previsione esplicita.
2. Scelta del tasso di crescita `g`.
3. **Verifica che la crescita `g` sia sostenibile dal reinvestimento**.

**Vincoli macro su g:**
- `g` non può superare la crescita del PIL nominale di lungo periodo (per Eurozona ~1,67–1,82%).

**Vincolo micro di coerenza (reinvestimento):**
```
g = ROIC_NI · h_T
```
dove:
- `ROIC_NI` = rendimento marginale dei nuovi investimenti
- `h_T` = quota di NOPAT reinvestita per finanziare la crescita = `ΔCI / NOPAT`

Sostituendo nella formula del TV:
```
TV = NOPAT_{T+1} · (1 - g/ROIC_NI) / (wacc_{T+1} - g)
```

**Caso particolare** in cui `ROIC_NI = wacc` (i nuovi investimenti rendono esattamente il costo del capitale → no extra-profitti, no creazione di valore dal Δg):
```
TV = NOPAT_{T+1} / wacc_{T+1}
```

### Modello DCF a 3 stadi (consigliato)
1. **Stadio 1** — previsione esplicita (5–8 anni): NOPAT, Capex, ΔCCN, ΔTFR, FCFF dettagliati.
2. **Stadio 2** — convergenza: il `ROIC_marginale` decresce gradualmente fino a uguagliare il WACC (le forze concorrenziali erodono gli extra-rendimenti).
3. **Stadio 3** — steady state con `ROIC_NI = wacc` → TV calcolato con la formula semplificata `NOPAT/wacc`.

**Tasso di convergenza geometrica del ROIC marginale verso il WACC:**
```
tasso = (WACC / ROIC_residuo)^(1/n) - 1
```
dove `n` è il numero di anni dello stadio di convergenza. A ogni anno del 2° stadio si applica questo tasso al ROIC marginale e si ricalcola il flusso di cassa coerente.

### Conclusioni operative
Il modello a 3 stadi elimina la problematica della normalizzazione del NOPAT nel TV, perché la convergenza ROIC=WACC permette di usare la formula semplificata. Una buona policy di controllo qualità impone procedure che verifichino la coerenza tra `g`, `h_T = g/ROIC` e `wacc` in ogni valutazione.

---

## 3. Agentic Credit Risk — Risk Analysis Probability of Default

**Fonte:** *Risk Analysis Probability of Default: A Stochastic Simulation Model* — Giuseppe Montesi (Univ. Siena), Giovanni Papiro (Capital Planning Director, Banca MPS), Draft April 2014.

### Idea centrale
Stimare la **PD forward-looking** di un'impresa partendo dai fondamentali (e non dai prezzi di mercato), usando **capital budgeting + Monte Carlo**. La PD è la frequenza con cui, nelle simulazioni, l'Enterprise Value scende sotto il Net Debt.

### Variabili e relazioni base
| Simbolo | Significato |
|---|---|
| REV | Ricavi |
| g | Crescita ricavi |
| m | Margine operativo (EBIT) |
| τ | Aliquota fiscale |
| NOPAT | Net Operating Profit After Tax |
| NIC | Net Invested Capital |
| NFA, f | Net Fixed Assets, f = NFA/REV |
| NWC, w | Net Working Capital, w = NWC/REV |
| D | Debito |
| r_d | Costo del debito |
| INT | Oneri finanziari |
| OCF | Operating Cash Flow (capital cash flow) |
| CASH | Excess cash |
| ΔCAP | Aumento di capitale |

**Equazioni fondamentali:**
```
[1]  NOPAT_t = REV_{t-1} · (1 + g_t) · m_t · (1 - τ)
[2]  NIC_t   = (f_t + w_t) · REV_{t-1} · (1 + g_t)
[3]  OCF_t   = NOPAT_t - ΔNIC_t + τ · INT_t          (capital cash flow, Ruback 2002)
[4]  INT_t   = r_d · (D_{t-1} + D_t) / 2
```

### Politica finanziaria endogena
Il debito è calcolato in modo **ricorsivo** per soddisfare l'equilibrio finanziario (cash inflow = cash outflow):
```
[5]  D_t = max[ 0,  D_{t-1} - OCF_t + INT_t - ΔCAP_t ]
```
Forma chiusa derivata sostituendo [4] in [5]:
```
[7]  D_t = max[ 0, (2·(NOPAT_t - ΔNIC_t + ΔCAP_t - 2·D_{t-1}) / (r_d·(1-τ) - 2)) - D_{t-1} ]
```
Estensioni: floor minimo di debito (target leverage), payout dei dividendi `d`, debito long/short term separati, interessi attivi sul cash, capex via piano di ammortamento.

### Enterprise Value e condizione di default
```
[12]  EV_t = Σ_{i=t..T-1} OCF_{i+1} / (1+k)^{i+1}     k = pre-tax WACC
[13]  Default ⇔ EV_t < D_t - CASH_t
```

### Stima della PD
La risoluzione è per **Monte Carlo** (~20.000 trial) con approccio a copula per le distribuzioni congiunte delle variabili stocastiche. Si calcolano tre tipi di PD:
1. **Yearly Default Frequency** — `P(EV_t < D_t)` (fragilità nel singolo anno)
2. **Yearly Marginal Default Frequency** — probabilità di default in t condizionata al non-default precedente
3. **Cumulated PD** — somma delle marginali sull'orizzonte

### LGD, EL, UL
Per ogni scenario di default:
```
[15]  LGD^k_t = EAD^k_t - EV^k_t - CASH^k_t        (EAD = D)
[16]  Average(LGD)_t = Σ_k (EAD - EV - CASH) / S
       EL = PD · LGD · EAD
       UL = LGD al percentile dell'intervallo di confidenza scelto
```
Estensione naturale a seniority/garanzie diverse aggiungendo waterfall sul pagamento.

### Differenza vs modelli option/contingent (Merton, Moody's KMV)
| Aspetto | Agentic Credit Risk | Merton/KMV |
|---|---|---|
| EV | da fondamentali (DCF stocastico) | da prezzi di mercato + volatilità storica |
| Debito | endogeno, ricorsivo | esogeno, statico |
| Applicabile a private | Sì | No |
| Orizzonte > 1 anno | Sì (multi-anno coerente) | Limitato |
| Dipendenza da bolle/inefficienze di mercato | No | Sì |

### Iperparametri di implementazione (back-testing)
- **Trial Monte Carlo**: 20.000
- **Forecast esplicito**: 3 anni
- **Distribuzioni**: Weibull
  - Ricavi: shape 2 (asimmetria positiva)
  - Costi operativi (% su ricavi): shape 3.5
  - NFA/Sales (Capex implicito): shape 3.5
  - NWC/Sales: shape 3
- **Centro distribuzione ricavi**: media 5 anni del PIL nominale del paese
- **Minimo distribuzione**: media impresa − differenza settoriale (settore GICS)
- **Matrice di correlazione standard**:
  - Autocorr Sales: 0,2 — OpCost/Sales: 0,3 — NFA/Sales: 0,5 — NWC/Sales: 0,4
  - Cross: Sales × OpCost/Sales = −0,4; NFA/Sales × OpCost/Sales = −0,2; Sales × NFA/Sales = +0,2; Sales × NWC/Sales = −0,3
- **Fiscalità**: range tra 70% e 150% dell'aliquota nominale del paese
- **Cost of capital**: pre-tax WACC con risk-free = bond decennale paese, MRP 5%, beta unlevered = mediana settore GICS
- **Terminal Value**: perpetuity di NOPAT + Interest Tax Shield dell'ultimo anno

### Master scale Rating ↔ PD a 1 anno
| Rating | PD | Rating | PD |
|---|---|---|---|
| AAA | 0,000% | BB+ | 0,550% |
| AA+ | 0,010% | BB | 0,800% |
| AA | 0,020% | BB- | 1,300% |
| AA- | 0,040% | B+ | 2,600% |
| A+ | 0,070% | B | 5,880% |
| A | 0,090% | B- | 9,120% |
| A- | 0,120% | CCC+ | 15,805% |
| BBB+ | 0,160% | CCC | 27,390% |
| BBB | 0,230% | CCC- | 37,861% |
| BBB- | 0,380% | CC | 52,335% |
|  |  | C | 72,343% |
|  |  | D | 100,000% |

Conversione **CDS spread → PD**: `PD = 1 - exp(-CDS / LGD)` con LGD = 60% (recovery 40%).

### Risultati empirici (back-testing)
- 46 imprese defaulted + 100 imprese performing (2003–2011, mercato US prevalentemente).
- Confronto con Altman Z-score, Moody's KMV EDF, Bloomberg DRSK, rating S&P, CDS implied PD.
- **Agentic Credit Risk fornisce le PD più alte e più tempestive** per le imprese poi defaulted (PD mediana >60% un anno prima del default; alta anche a 2–3 anni).
- Recovery rate medio del campione: 37,96% (mediana 33,65%, std 25,01%).
- Correlazione PD-Recovery: −0,704 (Pearson) → conferma la relazione teorica.
- Sui performing il modello non mostra bias upward.

---

## 4. Quadro comune e integrazione tra i tre lavori

I tre documenti condividono lo stesso impianto teorico ed è naturale comporli in una **suite integrata**:

```
                ┌──────────────────────────┐
                │  Database bilanci        │
                │  (settore + target)      │
                └────────────┬─────────────┘
                             │
                             ▼
                ┌──────────────────────────┐
                │  BMS Builder             │  ← Doc. 1
                │  Impresa Media Standard  │
                └────────────┬─────────────┘
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
   ┌────────────────────┐      ┌────────────────────┐
   │  DCF Valuation     │      │  Agentic Credit Risk              │  ← Doc. 3
   │  (TV coerente)     │◄────►│  Monte Carlo PD    │
   │  ← Doc. 2          │      │  endogeno EV/D     │
   └────────────────────┘      └────────────────────┘
                │                         │
                └────────────┬────────────┘
                             ▼
                ┌──────────────────────────┐
                │  Output:                 │
                │  - Equity / Enterprise   │
                │    Value                 │
                │  - PD / LGD / EL / UL    │
                │  - Rating implicito      │
                │  - Coerenza interna      │
                └──────────────────────────┘
```

Punti di contatto:
- **Stessa definizione di flusso di cassa**: capital cash flow `OCF = NOPAT − ΔNIC + τ·INT` (Ruback 2002). Coerente sia per il DCF della valutazione sia per il Agentic Credit Risk.
- **Stessa definizione di EV**: somma scontata dei flussi + Terminal Value. La coerenza del TV (Doc. 2) è prerequisito per la robustezza della stima di PD (Doc. 3).
- **Stessa logica settoriale**: il BMS (Doc. 1) può fornire i centroidi e le bande di variazione (medie e min sezionali) usate dal Agentic Credit Risk per parametrizzare le distribuzioni Weibull (Doc. 3, Appendice A).
- **Stesso WACC**: pre-tax, con beta unlevered settoriale. Il sample del BMS è anche il sample naturale per la stima del beta.

---

## 5. Strumenti che è possibile costruire

Di seguito una proposta modulare di tool, progettati per essere indipendenti ma componibili.

### A. BMS Builder
Input: dataset di n bilanci (CE + SP) di imprese del settore, schema di riclassificazione.
Output: Bilancio Medio Standardizzato (CE + SP) per uno o più anni.
Funzioni chiave:
- normalizzazione voci CE su fatturato e voci SP su totale attivo
- calcolo medie, mediane, percentili (per banding)
- confronto BMS vs "somma line-by-line" (effetto dimensionale)
- screening del campione (omogeneità, coerenza)
- serie storica BMS per analisi di trend

### B. DCF Engine con Terminal Value coerente
Input: piano economico-finanziario (storico + previsione esplicita), wacc, g target o ROIC target.
Output: Enterprise Value, Equity Value, decomposizione tra valore esplicito e TV, indicatori di coerenza.
Funzioni chiave:
- DCF a 2 stadi (formula standard)
- DCF a 3 stadi con stadio di convergenza ROIC_marginale → WACC
- check di coerenza: `g ≤ g_PIL`, `g = ROIC_NI · h_T`, `h_T = g/ROIC_NI`, sensitività
- formula semplificata `TV = NOPAT/wacc` quando ROIC=WACC
- validatore "stile University of Bergamo": flagga il report se il TV non è coerente con l'evoluzione di ROIC marginale

### C. Sector Valuation Differential
Input: BMS del settore + bilancio target + parametri DCF.
Output: valutazione del settore (IMS), valutazione della target, decomposizione differenziale (premio/sconto, drivers).
Logica: valuta prima l'IMS, poi la target, poi attribuisce le differenze a singoli driver (margine, capital intensity, crescita, leva).

### D. Agentic Credit Risk Stochastic Engine
Input: ultimo bilancio + parametri settoriali + matrice di correlazione + ipotesi macro.
Output: distribuzione PD (1y, 2y, 3y, cumulata), distribuzione LGD, EL, UL, rating implicito.
Componenti:
- generatore di scenari Monte Carlo con copula (default: Weibull con shape configurabili)
- risolutore ricorsivo del debito (formula chiusa [7])
- calcolo EV per ogni scenario (capital cash flow + TV perpetuity)
- check default `EV < D − CASH` per ogni periodo dell'orizzonte
- aggregazione PD/LGD/EL/UL con percentili

### E. Rating Mapper
Input: PD a 1 anno (o CDS spread).
Output: rating equivalente sulla master scale + classe di rischio.
Funzioni:
- master scale Rating ↔ PD (interpolazione esponenziale dove necessario)
- conversione CDS → PD (`PD = 1 - exp(-CDS/LGD)`)
- conversione Z-score → rating (master scale Altman) → PD
- normalizzazione delle frequenze storiche per evitare inconsistenze tra classi

### F. Back-testing & Comparator
Input: dataset di imprese (defaulted + performing) con bilanci storici.
Output: tabella comparativa PD per modello, statistiche di performance (Gini, KS, AUROC), grafici time-series.
Modelli supportabili: Agentic Credit Risk, Altman Z-score, Merton-style (richiede prezzi).

### G. Reporting & dashboard
Aggregatore finale che combina valutazione DCF, PD/LGD da Agentic Credit Risk, BMS settoriale e analisi differenziale in un unico report (per audit interno, comitato crediti o fairness opinion).

---

## 6. Note implementative

Considerazioni generali per chi implementerà la suite:

1. **Riclassificazione bilancio**: serve uno schema unico (riclassificato gestionale) condiviso da BMS, DCF e Agentic Credit Risk. Le voci minime: Ricavi, Costi operativi, EBITDA, EBIT, NOPAT, Capex, NFA, NWC, NIC, Debito, Cash, Equity.
2. **Capital cash flow**: l'OCF di Ruback è la formulazione su cui sono allineati sia il DCF a TV coerente sia il Agentic Credit Risk. Evitare di mischiarlo con FCFF tradizionale (che usa wacc dopo tasse).
3. **WACC**: per Agentic Credit Risk si usa il **pre-tax WACC** perché il tax shield è già nel cash flow (capital cash flow). Per il DCF "classico" del BMS si può usare l'after-tax WACC se si usa FCFF puro — ma è preferibile uniformare.
4. **Distribuzioni Weibull e correlazioni**: i parametri standard di Agentic Credit Risk sono un buon default ma vanno tarati sul settore reale; conviene tenerli come configurabili (non hard-coded).
5. **Coerenza temporale**: il BMS deve essere costruito sulle stesse annualità su cui si tarano media/varianza delle distribuzioni Weibull del Agentic Credit Risk per la stessa azienda.
6. **Validazione**: per ogni valutazione DCF il sistema dovrebbe stampare automaticamente i check di coerenza del TV (è la lezione dell'articolo n. 66 — il 10% dei report era incoerente).

---

## Riferimenti

- Scarano A., Brughera G.L.G., *Valutazione di una PMI con approccio settoriale*, Rivista AIAF n. 65, dic. 2007/gen. 2008.
- Scarano A., Di Napoli G., *Calcolo del Terminal Value (TV) e rispetto delle condizioni di coerenza*, Rivista AIAF n. 66, apr. 2008.
- Montesi G., Papiro G., *Risk Analysis Probability of Default: A Stochastic Simulation Model*, Draft, apr. 2014.
- Ruback R.S. (2002), *Capital Cash Flows: A Simple Approach to Valuing Risky Cash Flows*, Financial Management 31.
- Cassia L., Vismara S. (2005), *Valuation accuracy and infinity horizon forecasts*, Univ. Bergamo (referenziato in Doc. 2).
- Altman E.I. (1968); Merton R.C. (1974); Damodaran A. (2008) — riferimenti classici citati in Doc. 3.
