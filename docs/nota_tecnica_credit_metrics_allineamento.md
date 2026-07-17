# Nota tecnica — Allineamento dei due `credit_metrics.py` (fix limited-liability LGD)

**Prerequisito del Punto 4** (buffer di default) della nota `wacc_credit_risk_linee_guida.md` → Fase 0 → D6.
Va eseguito **prima** di introdurre il `default_buffer`, perché entrambi gli interventi toccano lo stesso file.

- **Direzione dell'allineamento:** **repo A ← repo B** (il repo B è avanti: contiene il bug-fix).
- **Repo A** = `valuation_analyst/` → `src/rating_valuation/agentic_credit_risk/credit_metrics.py` (**da correggere**)
- **Repo B** = `rating_valuation/` → `src/rating_valuation/agentic_credit_risk/credit_metrics.py` (**sorgente del fix**)
- **Obiettivo:** rendere i due `credit_metrics.py` **byte-identici**. Il diff riguarda **solo** la waterfall
  della LGD e il recovery rate; nessun'altra parte del file diverge.

---

## 1. Il bug nel repo A

Nel repo A la LGD e il recovery rate **non impongono la responsabilità limitata**:

```python
# valuation_analyst/.../credit_metrics.py:165-167  (BUGGATO)
unsecured_ead = ead_at_default * (1.0 - collateral_coverage)
lgd = np.maximum(0.0, unsecured_ead - ev_at_default - cash_at_default)
recovery = 1.0 - lgd / np.maximum(ead_at_default, 1e-12)
```

Due difetti:

1. **EV e CASH non sono flooredati a zero.** Il Monte Carlo può generare `EV` negativo (scenario di
   stress). Con `EV = −30` e `EAD = 10`, la formula dà `LGD = 10 − (−30) = 40` → **LGD > EAD**: il
   creditore "perde" più dell'esposizione. Economicamente impossibile (responsabilità limitata: il
   creditore recupera al massimo ciò che esiste, e perde al massimo l'esposizione).
2. **Il recovery rate include i default con EAD ≈ 0.** Un trial che va in default per insolvenza sul
   *valore* dell'equity ma **senza debito** (`EAD ≈ 0`) produce recovery rate di milioni di punti
   percentuali e distorce la media.

Effetto pratico: su target *distressed* con debito quasi nullo, `recovery_rate_mean` e `lgd_mean`
diventano assurdi (documentato nella docstring del fix nel repo B).

## 2. Il fix (già nel repo B)

```python
# rating_valuation/.../credit_metrics.py:178-191  (CORRETTO)
# Limited liability: creditors recover at most what exists (EV and cash
# floored at zero) and lose at most the unsecured exposure.
unsecured_ead = ead_at_default * (1.0 - collateral_coverage)
recoverable = np.maximum(ev_at_default, 0.0) + np.maximum(cash_at_default, 0.0)
lgd = np.clip(unsecured_ead - recoverable, 0.0, unsecured_ead)

# Recovery rate only over defaults with material exposure: trials that
# default with EAD ~ 0 (equity-value insolvency without debt) have no
# creditor exposure to recover and would distort the mean.
material = ead_at_default > _MATERIAL_EAD
recovery = (
    1.0 - lgd[material] / ead_at_default[material]
    if material.any()
    else np.array([1.0])
)
```

Garanzie: `LGD ≤ EAD` e `recovery ∈ [0, 1]` **per costruzione** (clip + floor).

---

## 3. Diff puntuale da applicare al repo A

Sono **quattro** hunk (il modo più sicuro è copiare l'intero file dal repo B al repo A: i due file
diventano identici e null'altro cambia).

### Hunk 1 — docstring di modulo (righe 9-14 → nuove righe)
```diff
-    LGD (per scenario)         — max(0, EAD - EV - CASH)
+    LGD (per scenario)         — clip(EAD_unsecured - max(EV,0) - max(CASH,0), 0, EAD_unsecured)
     LGD summary                — mean, median, std, quantiles
     Expected Loss              — PD × mean(LGD)
     Unexpected Loss            — LGD at a chosen confidence level
-    Recovery rate              — 1 − LGD_mean / EAD_mean
+    Recovery rate              — mean(1 − LGD/EAD) over defaults with material EAD
+
+Limited liability is enforced in the waterfall: a simulated negative EV cannot
+push the loss beyond the unsecured exposure, so LGD ≤ EAD and recovery ∈ [0, 1]
+by construction (distressed targets used to produce LGD > EAD and recovery
+rates of millions of percent when defaulting with near-zero debt).
```

### Hunk 2 — nuova costante (dopo `import numpy as np`)
```diff
 import numpy as np

+# Defaults with EAD at or below this threshold (in the dataset's monetary
+# unit, millions → 1 EUR) carry no meaningful creditor exposure and are
+# excluded from the recovery-rate mean.
+_MATERIAL_EAD = 1e-6
```

### Hunk 3 — docstring di `compute_metrics` (parametro `collateral_coverage`)
```diff
-        waterfall): ``LGD = max(0, EAD·(1 − collateral_coverage) − EV − CASH)``.
-        Default 0 reproduces the previous unsecured behavior.
+        waterfall): ``LGD = clip(EAD·(1 − collateral_coverage) − max(EV, 0)
+        − max(CASH, 0), 0, EAD·(1 − collateral_coverage))``.
+        Default 0 reproduces the unsecured behavior.
```

### Hunk 4 — il calcolo (righe 165-167 del repo A)
```diff
     unsecured_ead = ead_at_default * (1.0 - collateral_coverage)
-    lgd = np.maximum(0.0, unsecured_ead - ev_at_default - cash_at_default)
-    recovery = 1.0 - lgd / np.maximum(ead_at_default, 1e-12)
+    # Limited liability: creditors recover at most what exists (EV and cash
+    # floored at zero) and lose at most the unsecured exposure.
+    recoverable = np.maximum(ev_at_default, 0.0) + np.maximum(cash_at_default, 0.0)
+    lgd = np.clip(unsecured_ead - recoverable, 0.0, unsecured_ead)
+
+    # Recovery rate only over defaults with material exposure: trials that
+    # default with EAD ~ 0 (equity-value insolvency without debt) have no
+    # creditor exposure to recover and would distort the mean.
+    material = ead_at_default > _MATERIAL_EAD
+    recovery = (
+        1.0 - lgd[material] / ead_at_default[material]
+        if material.any()
+        else np.array([1.0])
+    )
```

**Comando equivalente (consigliato — rende i file identici):**
```bash
cp rating_valuation/src/rating_valuation/agentic_credit_risk/credit_metrics.py \
   valuation_analyst/src/rating_valuation/agentic_credit_risk/credit_metrics.py
```
> ⚠️ Verificare **prima** che i due file differiscano *solo* per questi hunk:
> `diff` mostra esclusivamente le righe qui sopra (già verificato al 2026-07-17). Se in futuro
> divergessero altrove, applicare i 4 hunk a mano invece del `cp`.

---

## 4. Test da aggiungere al repo A

Il repo B ha **5 test di regressione** in `tests/.../test_agentic_credit_risk_credit_metrics.py` che il
repo A non ha (blocco «Limited-liability waterfall»). Vanno portati:

1. `test_negative_ev_does_not_inflate_lgd_beyond_ead` — `EV=−30, EAD=10` → `LGD=10` (non 40), recovery 0
2. `test_recovery_rate_bounded_in_unit_interval` — pool misto → recovery ∈ [0,1]
3. `test_zero_debt_defaults_excluded_from_recovery_mean` — default con `EAD=0` escluso dalla media
4. `test_negative_cash_does_not_add_to_loss` — cash negativo flooredato a 0
5. `test_distressed_real_target_metrics_are_plausible` — regression end-to-end sul dataset

> ⚠️ **Attenzione al 5° test (coupling col dataset).** Nel repo B usa `DEFAULT_DATA_DIR` = dataset AIDA
> reale e cita il target **TRAFER**. Nel repo A `DEFAULT_DATA_DIR = data/rating_valuation/` (sintetico) e
> `companies.csv` **esiste** → il test **non** fa skip: gira sul target del sintetico (max `fiscal_year`).
> Le asserzioni sono generiche (`lgd_mean ≤ ead_mean`, `recovery ∈ [0,1]`, `EL ≤ ead_mean`) e passano
> comunque. **Adattare:** rimuovere il riferimento «TRAFER» dal commento o generalizzarlo. I primi 4
> test sono portabili tali e quali (input costruiti a mano, nessuna dipendenza dai dati).

---

## 5. Verifica

```bash
# Repo A — dopo il fix + i test
cd valuation_analyst && pytest tests/rating_valuation/test_agentic_credit_risk_credit_metrics.py -v

# Non-regressione end-to-end (la PD non deve cambiare: il fix tocca solo LGD/recovery, non il default)
pytest tests/rating_valuation/ -q

# Conferma che i due file siano ora identici
diff valuation_analyst/src/rating_valuation/agentic_credit_risk/credit_metrics.py \
     rating_valuation/src/rating_valuation/agentic_credit_risk/credit_metrics.py && echo "IDENTICI ✓"
```

**Atteso:** i 5 nuovi test passano; la suite R&V del repo A resta verde; `default_matrix` (la PD) è
invariata perché il fix agisce a valle, solo su `lgd`/`recovery`.

---

## 6. TODO list

### Repo A — `valuation_analyst/` (riceve il fix)

- [ ] **A1.** Verificare col `diff` che i due `credit_metrics.py` differiscano solo nei 4 hunk (§3).
- [ ] **A2.** Applicare il fix: `cp` dal repo B **oppure** i 4 hunk a mano (§3).
- [ ] **A3.** Portare i 5 test limited-liability (§4), **adattando il 5°** (rimuovere «TRAFER»,
      target generico dal sintetico).
- [ ] **A4.** `pytest tests/rating_valuation/ -q` → suite verde; confermare PD invariata (non-regressione).
- [ ] **A5.** Confermare `diff` vuoto tra i due `credit_metrics.py` (file identici).
- [ ] **A6.** *(sblocca il Punto 4)* Solo ora introdurre `default_buffer` su `credit_metrics.py:111`.

### Repo B — `rating_valuation/` (sorgente, resta autorità)

- [ ] **B1.** Nessuna modifica al codice: il fix è già presente e coperto da test (188 test verdi al 2026-07-13).
- [ ] **B2.** Marcare il repo B come **fonte autoritativa** di `credit_metrics.py` in `TODO.md`
      (finché i due package non vengono unificati — vedi §7).
- [ ] **B3.** Quando si implementerà il Punto 4, applicare `default_buffer` **anche qui**
      (`credit_metrics.py:122`, LGD a `:178-180`), mantenendo i due file allineati.

### Entrambi i repo (governance)

- [ ] **G1.** Aggiungere in ciascun `TODO.md` un puntatore a questa nota e alla `wacc_credit_risk_linee_guida.md`.
- [ ] **G2.** Definire la **regola di allineamento**: ogni modifica a `src/rating_valuation/` va replicata
      nell'altro repo nella stessa PR (o unificare i package — §7).

---

## 7. Fuori scope di questa nota (ma da decidere)

- **`data_loader.py` diverge** tra i due repo (repo B: dataset primario AIDA + `data/synthetic/`;
  repo A: `data/rating_valuation/`). **Non** è un bug, è una scelta di dataset. Non toccato qui.
- **Duplicazione strutturale.** Mantenere due copie di `src/rating_valuation/` è debito tecnico: ogni
  fix va fatto due volte. Valutare l'unificazione in un package condiviso (submodule, package
  installabile, o monorepo con path unico). Decisione architetturale separata.
