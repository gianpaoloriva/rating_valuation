# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Rating & Valuation Suite** — Python library + Streamlit dashboard implementing three integrated methodologies from the reference papers (see `overview.md` for full derivations and formulas):

1. **BMS — Bilancio Medio Standardizzato** (Scarano/Brughera, AIAF n. 65, 2008): sector-average synthetic company built by normalizing each peer's CE on its own revenues and SP on its own total assets, then equal-weighting.
2. **Terminal Value coerente** (Scarano/Di Napoli, AIAF n. 66, 2008): 2/3-stage DCF with the reinvestment constraint `g = ROIC_NI · h`, collapsing to `TV = NOPAT/wacc` when `ROIC_NI = wacc`.
3. **Agentic Credit Risk** (Montesi/Papiro, 2014): forward-looking stochastic PD via Monte Carlo simulation with endogenous recursive debt (eq. [7]), dynamic cash accumulation (eq. [6]), and EV from capital cash flow discounted at pre-tax WACC.

The three tools share the same cash-flow convention: **capital cash flow (Ruback 2002)** `OCF = NOPAT − ΔNIC + τ·INT`. This is why Agentic Credit Risk uses **pre-tax WACC** — the tax shield is already in the cash flow, so do not re-apply `(1-t)` to the debt weight.

## Commands

```bash
# Install (editable, dev + app extras)
pip install -e ".[dev,app]"

# Regenerate the PRIMARY dataset (real AIDA data → data/*.csv, deterministic)
python3 data/etl/aida_to_companies.py

# Regenerate the synthetic fixture (fixed seed → idempotent, data/synthetic/)
python3 data/generators/seed_companies.py

# Test suite (pytest is configured via pyproject.toml: testpaths=tests, pythonpath=src)
pytest                                    # full suite, ~152 tests, <1s
pytest tests/test_dcf_coherence.py        # single file
pytest tests/test_dcf_coherence.py::test_name  # single test
pytest -k "agentic_credit_risk"           # by name pattern
pytest --cov=rating_valuation             # with coverage

# Lint
ruff check src tests app

# Streamlit dashboard (multi-page, pages auto-discovered from app/pages/)
streamlit run app/Rating_Valuation_Suite.py                          # real data (default)
RV_DATA_DIR=data/synthetic streamlit run app/Rating_Valuation_Suite.py  # synthetic demo

# Docker
docker compose up --build                 # → http://localhost:8501 (mounts ./data read-only)

# Deploy to AWS (ECS Express, eu-west-1 — ECR repo & service already provisioned)
./deploy/deploy.sh                        # build linux/amd64, push to ECR, update service
./deploy/deploy.sh --no-wait              # same, without polling for RUNNING
```

Requires Python >= 3.11. Runtime deps: `pandas`, `numpy`, `scipy`. App extras: `streamlit`, `plotly`.

## Architecture

### Layered design

```
data/ (CSVs) ──► common/data_loader ──► domain modules ──► app/pages (Streamlit)
                                          │
                              ┌───────────┼───────────┐
                              ▼           ▼           ▼
                            bms/        dcf/    agentic_credit_risk/
                              │           │           │
                              └───►  differential/  ◄─┘
                                       rating/
                                       backtest/
```

- **`data/`** — single source of truth. Four CSVs with a strict schema documented in `data/schema.md`: `companies.csv` (reclassified balance sheets, one row per company×year), `sectors.csv` (GICS sub-industry → beta unlevered + Weibull shapes + correlation matrix), `macro.csv` (country×year risk-free, MRP, nominal GDP growth 5y avg), `rating_master_scale.csv` (S&P rating ↔ PD 1y from Montesi/Papiro Appendix A). All CSVs use `,` separator, UTF-8, `.` decimal; monetary values in **millions of the row's `currency`**; rates and percentages as **decimals** (0.28 = 28%). Since July 2026 the CSVs in `data/` are the **real AIDA dataset** (277 Italian metals wholesalers, ATECO 4672, FY2020–2024, target `trafer_spa`; raw xlsx in `data/real/`, produced by `data/etl/aida_to_companies.py`, mapping documented in `data/mapping_iv_directive.md`). The deterministic synthetic fixture lives in `data/synthetic/` (loaders expose it as `SYNTHETIC_DATA_DIR`) and is what the test suite runs on.
- **`src/rating_valuation/common/`** — cross-cutting utilities: `data_loader` (typed CSV loaders + `peer_sample()` / `target_row()` selectors + schema validation), `financial` (WACC, discount factors, Gordon perpetuity, ROIC), `invariants` (balance-sheet integrity checks: `ebitda==rev-opcost`, `nic==nfa+nwc`, `net_debt==gross_debt-cash`, `equity==nic-net_debt`).
- **`src/rating_valuation/bms/`** — `BMSBuilder` + `build_bms_timeseries`. Equal-weight mean of normalized shares; returns a `BMSResult` dataclass that also carries the naive line-by-line sum to expose the size-distortion effect. Default minimum sample threshold is 20 peers (paper Scarano/Brughera) — below this `below_min_sample=True` is set but no error is raised.
- **`src/rating_valuation/dcf/`** — `two_stage.py` (standard Gordon + coherent TV with `(1 - g/ROIC_NI)` reinvestment adjustment), `three_stage.py` (geometric ROIC→WACC convergence over stadio 2, then `TV = NOPAT/wacc`), `coherence.py` (flags TVs where `g > g_PIL`, `h_T = g/ROIC > 1`, or TV weight is implausible — the "University of Bergamo" quality check).
- **`src/rating_valuation/agentic_credit_risk/`** — four files:
  - `stochastic.py` — Weibull sampler with `StochasticParameters` carrying autocorr + cross-correlations; uses copula for joint draws.
  - `debt_solver.py` — closed-form recursive debt `D_t` (eq. [7]) and `simulate_period_vectorized()` which implements both the clamped-debt case and the **eq. [6] dynamic cash accumulation** when debt would go negative.
  - `credit_metrics.py` — aggregates the Monte Carlo output into yearly default frequency, marginal PD, cumulative PD, LGD, EL, UL. Known issue (TODO.md, P2): on deeply distressed targets (simulated EV ≈ 0) LGD can exceed EAD and the mean recovery rate goes negative — clip pending; PD is unaffected.
  - `simulator.py` — orchestrator: `AgenticCreditRiskSimulator.from_company(row, sectors, macro)` factory builds an `InitialState` (with `wacc` = **pre-tax** CAPM) + `StochasticParameters` from the reference CSVs, then `.run(seed=42)` vectorizes across `n_trials=20_000` × `n_years=3` (paper defaults). EV is computed per trial per period from discounted future OCFs + a perpetuity on the last NOPAT.
- **`src/rating_valuation/differential/analyzer.py`** — target vs IMS decomposition: separates margin, capital intensity, growth and leverage drivers.
- **`src/rating_valuation/rating/mapper.py`** — `RatingLookup` (master scale, interpolated on `log(PD)`), `PD → rating` and reverse, `CDS → PD = 1 - exp(-CDS/LGD)` with LGD=0.60, and Altman Z-score → rating via `ALTMAN_Z_BUCKETS`. Also `altman_z_double_prime_non_manufacturing()` for Italian PMI.
- **`src/rating_valuation/backtest/comparator.py`** — runs multiple credit risk models (Agentic Credit Risk, Altman Z'') on a defaulted+performing sample and scores them with Gini / AUROC / KS (Montesi/Papiro Section 5 reproduction).
- **`app/`** — Streamlit multi-page app. `Rating_Valuation_Suite.py` is the landing page (Streamlit discovers pages automatically from `app/pages/` — file names prefixed with `1_`, `2_`, … control sidebar order). `app/_common.py` has `load_bundle()` (cached `DataBundle`) and shared formatters. The app prepends the repo root to `sys.path` so it works both locally and inside the Docker image where `PYTHONPATH=/app`.
- **`.claude/agents/`** — six domain subagents (bms-analyst, dcf-validator, agentic-credit-risk-simulator, data-curator, backtest-analyst, valuation-reporter). Delegate to them proactively when the task matches their description (e.g. BMS construction, TV coherence audits, data integrity checks).

### Key invariants & conventions that cross modules

- **Cash flow definition is uniform**: capital cash flow à la Ruback. Do not mix with traditional after-tax FCFF discounted at after-tax WACC inside the same pipeline.
- **WACC flavor matters**: DCF classico can use after-tax WACC with unlevered FCFF (`wacc_after_tax()`), but the Agentic Credit Risk simulator and the coherent TV both use **pre-tax WACC** (`wacc_pre_tax()`); `InitialState.wacc` is pre-tax by construction in `AgenticCreditRiskSimulator.from_company`.
- **BMS → Agentic Credit Risk integration**: the peer sample that builds the BMS is also the natural sample for the Weibull centroids and the beta unlevered. Keep `gics_sub_industry` keys consistent across `companies.csv` and `sectors.csv`.
- **TV coherence check must run on every valuation** (lesson from Scarano/Di Napoli: ~10% of analyst reports had incoherent TV). `dcf/coherence.py` is called by the dashboard page and should be invoked in any programmatic DCF workflow.
- **Sign flip for EBITDA margin correlations**: the Montesi/Papiro paper parametrizes on `OpCost/Sales`, our simulator uses `EBITDA margin = 1 - OpCost/Sales`, so `corr_sales_opcosts` and `corr_nfa_opcosts` are flipped in sign inside `AgenticCreditRiskSimulator.from_company`.
- **Fiscal year single-year constraint**: `BMSBuilder` requires a single `fiscal_year` in the input — filter upstream with `peer_sample(companies, sub_industry, fiscal_year=YYYY)` or pass `fiscal_year=` to the constructor. Multi-year analysis goes through `build_bms_timeseries()`.
- **`companies.csv` contains both peers and target**: `is_target=1` marks the subject of the valuation; `peer_sample()` drops it by default (`exclude_target=True`). The primary (real) dataset has 276 peers + 1 target (`trafer_spa`, randomly drawn with seed 42) in `Metals Wholesale (ATECO 4672)` for 2020–2024; the synthetic fixture in `data/synthetic/` has 15 peers + 1 target (`riva_meccanica`) in `Industrial Machinery` for 2022–2024. Real-data caveat: the credit simulator requires a positive expected EBITDA margin — companies with operating losses must be filtered before calling `from_company()`.
- **Data loaders validate schema**: any real dataset must preserve column names and units exactly; loaders raise `SchemaError` on missing columns. Invariant checks in `common/invariants.py` enforce balance-sheet consistency with a default tolerance of 0.01 (in the CSV's monetary unit).

### Reference documentation

- `overview.md` — full theoretical synthesis of the three papers, all formulas, integration diagram, implementation notes. Referenced by README, Dockerfile, Streamlit UI, `data/schema.md`, `src/rating_valuation/__init__.py`, and by four of the six subagents — do not delete or rename.
- `TODO.md` — single source of truth for **both** completed functionality (replaces the old README "Stato di sviluppo" section) and the post-audit backlog of formula discrepancies vs the reference papers. P1 items have quantitative impact on results and should be prioritized; P3 items only matter if reproducing the RAPD paper's Section 5 backtesting.
- `data/schema.md` — authoritative CSV schema (column names, units, invariants, real-data conventions).
- `docs/` — original PDFs of the three reference papers (`2008 n.-65 Bilancio Madio Standard.pdf`, `2008 n.-66 Calcolo del Terminal Value.pdf`, `RAPD.pdf`).
- `README.md` — C-level executive summary (use cases, deliverables, methodology) — not an implementation reference.
