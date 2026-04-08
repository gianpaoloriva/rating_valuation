"""Agentic Credit Risk Monte Carlo orchestrator.

Ties together the stochastic sampler, the debt solver and the credit
metrics module into a single ``AgenticCreditRiskSimulator`` class. The
typical workflow:

    1. ``AgenticCreditRiskSimulator.from_company(...)`` reads the target row,
       the sector parameters and the macro data and builds a simulator instance.
    2. ``simulator.run(seed=42)`` executes ``n_trials`` Monte Carlo
       scenarios across ``n_years`` forecast periods.
    3. The returned ``AgenticCreditRiskResult`` bundles the credit metrics,
       the diagnostic matrices and the implied rating (via the master scale).

Vectorized across trials using numpy.

Appendix A extensions (all opt-in via ``InitialState`` and ``run()``
parameters, default values reproduce the original "reduced model"
behavior):

    * Interest Tax Shield in the TV — ``TV = NOPAT_T/k + τ·INT_T``
    * Interest on excess cash at ``cash_yield``
    * Stochastic tax rate normalization in ``[0.7, 1.5] × τ_nominal``
    * Dividend payout ratio
    * Debt floor (minimum target leverage)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from rating_valuation.agentic_credit_risk.credit_metrics import (
    CreditMetrics,
    compute_metrics,
)
from rating_valuation.agentic_credit_risk.debt_solver import (
    simulate_period_vectorized,
)
from rating_valuation.agentic_credit_risk.stochastic import (
    StochasticParameters,
    WeibullParams,
    sample_scenarios,
)
from rating_valuation.rating.mapper import RatingLookup


# -----------------------------------------------------------------------------
# Initial state snapshot
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class InitialState:
    revenues: float
    net_invested_capital: float
    net_fixed_assets: float
    net_working_capital: float
    gross_debt: float
    cash: float
    da_ratio: float                  # D&A / revenues (held constant in this V1)
    tax_rate: float
    cost_of_debt: float
    wacc: float                      # pre-tax WACC used to discount OCFs

    # --- Appendix A extensions (all default to neutral values) --------------
    cash_yield: float = 0.0          # yield on CASH_{t-1} (paper: risk-free)
    payout_ratio: float = 0.0        # dividend fraction of after-tax profit
    debt_floor: float = 0.0          # minimum debt stock per period (eq. [8])
    tax_stochastic: bool = False     # sample τ ∈ [0.7, 1.5]·τ_nominal per trial


# -----------------------------------------------------------------------------
# Result container
# -----------------------------------------------------------------------------


@dataclass
class AgenticCreditRiskResult:
    initial_state: InitialState
    params: StochasticParameters
    metrics: CreditMetrics
    n_trials: int
    n_years: int
    seed: int | None
    implied_rating: str | None = None

    # Diagnostic matrices — kept optionally for inspection
    nopat: np.ndarray | None = None
    ocf: np.ndarray | None = None
    debt: np.ndarray | None = None
    cash_matrix: np.ndarray | None = None
    ev: np.ndarray | None = None
    interest: np.ndarray | None = None      # INT per trial/year, used for TV ITS

    def summary(self) -> dict:
        out = self.metrics.summary()
        out["implied_rating"] = self.implied_rating
        out["initial_revenues"] = self.initial_state.revenues
        out["initial_debt"] = self.initial_state.gross_debt
        out["initial_nic"] = self.initial_state.net_invested_capital
        return out

    def as_dataframe(self) -> pd.DataFrame:
        """Return a compact table with the main results per horizon."""
        rows = []
        for t in range(self.n_years):
            rows.append(
                {
                    "year_ahead": t + 1,
                    "yearly_default_frequency": float(self.metrics.yearly_default_frequency[t]),
                    "marginal_pd": float(self.metrics.yearly_marginal_default[t]),
                    "cumulative_pd": float(self.metrics.cumulative_pd[t]),
                }
            )
        return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Simulator
# -----------------------------------------------------------------------------


class AgenticCreditRiskSimulator:
    """Monte Carlo stochastic simulator for PD/LGD estimation.

    Parameters
    ----------
    initial_state : InitialState
        Snapshot of the company at ``t=0`` (last balance sheet).
    params : StochasticParameters
        Weibull marginals + correlation coefficients.
    n_trials : int
        Number of Monte Carlo scenarios (default 20 000 as in the paper).
    n_years : int
        Forecast horizon (default 3 years as in the paper back-testing).
    """

    DEFAULT_N_TRIALS: int = 20_000
    DEFAULT_N_YEARS: int = 3

    def __init__(
        self,
        initial_state: InitialState,
        params: StochasticParameters,
        n_trials: int = DEFAULT_N_TRIALS,
        n_years: int = DEFAULT_N_YEARS,
    ) -> None:
        self.initial_state = initial_state
        self.params = params
        self.n_trials = n_trials
        self.n_years = n_years

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_company(
        cls,
        company_row: pd.Series,
        sectors: pd.DataFrame,
        macro: pd.DataFrame,
        *,
        beta_unlevered_override: float | None = None,
        revenue_growth_min_delta: float = 0.05,
        margin_min_delta: float = 0.03,
        nfa_min_delta: float = 0.08,
        nwc_min_delta: float = 0.05,
        n_trials: int = DEFAULT_N_TRIALS,
        n_years: int = DEFAULT_N_YEARS,
    ) -> AgenticCreditRiskSimulator:
        """Build a simulator directly from the reference datasets.

        ``*_min_delta`` are the implementation hypotheses that convert the
        central value (company-specific) into the minimum of the Weibull
        (sector-wide). They are intentionally exposed as knobs so the
        analyst can tighten them for stress testing.
        """
        sector_row = sectors[
            (sectors["gics_sub_industry"] == company_row["gics_sub_industry"])
        ]
        if sector_row.empty:
            raise KeyError(
                f"No sector parameters for {company_row['gics_sub_industry']!r}"
            )
        s = sector_row.iloc[0]

        macro_row = macro[
            (macro["country"] == company_row["country"])
            & (macro["year"] == int(company_row["fiscal_year"]))
        ]
        if macro_row.empty:
            raise KeyError(
                f"No macro data for country {company_row['country']!r} / "
                f"year {int(company_row['fiscal_year'])}"
            )
        m = macro_row.iloc[0]

        revenues = float(company_row["revenues"])
        ebit = float(company_row["ebit"])
        ebitda = float(company_row["ebitda"])
        nfa = float(company_row["net_fixed_assets"])
        nwc = float(company_row["net_working_capital"])
        da = float(company_row["depreciation_amortization"])

        # Central values for the distributions
        growth_center = float(m["gdp_nominal_growth_5y_avg"])
        margin_center = ebitda / revenues if revenues else 0.0
        nfa_center = nfa / revenues if revenues else 0.0
        nwc_center = nwc / revenues if revenues else 0.0

        # Weibull parameters (shape from sectors.csv, min = center - delta)
        growth_params = WeibullParams.from_mean_min(
            mean=growth_center,
            minimum=growth_center - revenue_growth_min_delta,
            shape=float(s["weibull_revenues_shape"]),
        )
        margin_params = WeibullParams.from_mean_min(
            mean=margin_center,
            minimum=max(0.0, margin_center - margin_min_delta),
            shape=float(s["weibull_opcosts_shape"]),
        )
        nfa_params = WeibullParams.from_mean_min(
            mean=nfa_center,
            minimum=max(0.0, nfa_center - nfa_min_delta),
            shape=float(s["weibull_nfa_shape"]),
        )
        nwc_params = WeibullParams.from_mean_min(
            mean=nwc_center,
            minimum=max(0.0, nwc_center - nwc_min_delta),
            shape=float(s["weibull_nwc_shape"]),
        )

        # Correlations: flip sign where needed for EBITDA margin framing.
        # Paper uses corr(Sales, OpCost/Sales) = -0.4 with OpCost/Sales increasing
        # when costs rise. EBITDA margin = 1 - OpCost/Sales → sign flipped.
        params = StochasticParameters(
            growth=growth_params,
            ebitda_margin=margin_params,
            nfa_ratio=nfa_params,
            nwc_ratio=nwc_params,
            autocorr_growth=float(s["autocorr_revenues"]),
            autocorr_margin=float(s["autocorr_opcosts"]),
            autocorr_nfa=float(s["autocorr_nfa"]),
            autocorr_nwc=float(s["autocorr_nwc"]),
            corr_growth_margin=-float(s["corr_sales_opcosts"]),
            corr_nfa_margin=-float(s["corr_nfa_opcosts"]),
            corr_growth_nfa=float(s["corr_sales_nfa"]),
            corr_growth_nwc=float(s["corr_sales_nwc"]),
        )

        # WACC: pre-tax, simple CAPM
        beta_u = (
            beta_unlevered_override
            if beta_unlevered_override is not None
            else float(s["beta_unlevered"])
        )
        risk_free = float(m["risk_free_rate_10y"])
        mrp = float(m["market_risk_premium"])
        tax_rate = float(company_row["corporate_tax_rate"])
        debt = float(company_row["gross_debt"])
        equity = float(company_row["equity"])
        de_ratio = debt / equity if equity > 0 else 0.0
        beta_l = beta_u * (1 + (1 - tax_rate) * de_ratio)
        ke = risk_free + beta_l * mrp
        w_d = debt / (debt + equity) if (debt + equity) > 0 else 0.0
        w_e = 1.0 - w_d
        # pre-tax WACC: no tax shield applied to the debt weight
        wacc_pretax = w_e * ke + w_d * float(company_row["cost_of_debt"])

        initial_state = InitialState(
            revenues=revenues,
            net_invested_capital=float(company_row["net_invested_capital"]),
            net_fixed_assets=nfa,
            net_working_capital=nwc,
            gross_debt=debt,
            cash=float(company_row["cash"]),
            da_ratio=da / revenues if revenues else 0.0,
            tax_rate=tax_rate,
            cost_of_debt=float(company_row["cost_of_debt"]),
            wacc=wacc_pretax,
        )

        return cls(
            initial_state=initial_state,
            params=params,
            n_trials=n_trials,
            n_years=n_years,
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        seed: int | None = None,
        map_rating: bool = True,
        keep_diagnostic: bool = True,
    ) -> AgenticCreditRiskResult:
        scenarios = sample_scenarios(
            self.params, n_trials=self.n_trials, n_years=self.n_years, seed=seed
        )
        # scenarios[:, year, var] where var order is (g, m, f, w)

        n_trials, n_years = self.n_trials, self.n_years

        # Storage matrices
        nopat_mat = np.zeros((n_trials, n_years))
        ocf_mat = np.zeros((n_trials, n_years))
        debt_mat = np.zeros((n_trials, n_years))
        cash_mat = np.zeros((n_trials, n_years))
        nic_mat = np.zeros((n_trials, n_years))
        interest_mat = np.zeros((n_trials, n_years))

        init = self.initial_state

        # Tax rate: constant or stochastic per trial (Appendix A: "effective
        # tax rate normalized within a range given by 70% and 150% of the
        # nominal rate"). Sampled once per trial (kept fixed across years
        # for simplicity — the paper does not require an autocorrelation).
        if init.tax_stochastic:
            rng = np.random.default_rng(seed if seed is None else seed + 1)
            tax_vector = rng.uniform(
                0.70 * init.tax_rate, 1.50 * init.tax_rate, size=n_trials
            )
            # Clip at the mathematical range permitted by the debt solver.
            tax_vector = np.clip(tax_vector, 0.0, 0.99)
        else:
            tax_vector = np.full(n_trials, init.tax_rate)

        rev_prev = np.full(n_trials, init.revenues)
        nic_prev = np.full(n_trials, init.net_invested_capital)
        debt_prev = np.full(n_trials, init.gross_debt)
        cash_prev = np.full(n_trials, init.cash)

        for t in range(n_years):
            g = scenarios[:, t, 0]
            margin = scenarios[:, t, 1]
            f = scenarios[:, t, 2]
            w = scenarios[:, t, 3]

            rev_t = rev_prev * (1.0 + g)
            ebitda_t = rev_t * margin
            da_t = rev_t * init.da_ratio
            ebit_t = ebitda_t - da_t
            nopat_t = ebit_t * (1.0 - tax_vector)

            nic_t = (f + w) * rev_t
            delta_nic = nic_t - nic_prev

            # Full-period update: debt, cash, interest, OCF (eq. [3-6])
            # with Appendix A extensions (cash yield, dividends, debt floor)
            debt_t, cash_t, int_t, ocf_t = simulate_period_vectorized(
                debt_prev=debt_prev,
                cash_prev=cash_prev,
                nopat=nopat_t,
                delta_nic=delta_nic,
                capital_increase=0.0,
                cost_of_debt=init.cost_of_debt,
                tax_rate=tax_vector,
                cash_yield=init.cash_yield,
                payout_ratio=init.payout_ratio,
                debt_floor=init.debt_floor,
            )

            nopat_mat[:, t] = nopat_t
            ocf_mat[:, t] = ocf_t
            debt_mat[:, t] = debt_t
            cash_mat[:, t] = cash_t
            nic_mat[:, t] = nic_t
            interest_mat[:, t] = int_t

            rev_prev = rev_t
            nic_prev = nic_t
            debt_prev = debt_t
            cash_prev = cash_t

        # --- EV at each period: discounted future OCFs + TV perpetuity --
        # Terminal value (Appendix A):
        #     TV = NOPAT_T / k + τ · INT_T
        # The Interest Tax Shield of the last explicit year is included,
        # which for leveraged companies can be a material component of the
        # TV (omitting it systematically inflates the PD).
        wacc = init.wacc
        if wacc <= 0:
            raise ValueError(f"WACC must be positive, got {wacc}")

        ev_mat = np.zeros((n_trials, n_years))
        its_last = tax_vector * interest_mat[:, -1]  # τ·INT_T, shape (n_trials,)
        for t in range(n_years):
            # Future OCFs from t+1 to T
            ev = np.zeros(n_trials)
            for future in range(t + 1, n_years + 1):
                if future - 1 < n_years:
                    periods = future - t
                    ev += ocf_mat[:, future - 1] / (1.0 + wacc) ** periods
            # Terminal value = perpetuity of last year NOPAT + ITS of last year
            periods_to_tv = n_years - t
            tv = nopat_mat[:, -1] / wacc + its_last
            ev += tv / (1.0 + wacc) ** periods_to_tv
            ev_mat[:, t] = ev

        # Cash matrix is now dynamically accumulated inside the year loop.
        metrics = compute_metrics(ev=ev_mat, debt=debt_mat, cash=cash_mat)

        implied_rating = None
        if map_rating:
            lookup = RatingLookup.from_csv()
            # Use log-linear interpolation (paper Appendix A: "exponential
            # interpolation") and format as a compact label
            # "lower/upper (frac)" so the rating is not quantized on slots.
            pd_cum = float(metrics.cumulative_pd[-1])
            lo, hi, frac = lookup.rating_of_pd_interpolated(pd_cum)
            implied_rating = lo if lo == hi else f"{lo}/{hi} ({frac:.2f})"

        result = AgenticCreditRiskResult(
            initial_state=init,
            params=self.params,
            metrics=metrics,
            n_trials=n_trials,
            n_years=n_years,
            seed=seed,
            implied_rating=implied_rating,
        )
        if keep_diagnostic:
            result.nopat = nopat_mat
            result.ocf = ocf_mat
            result.debt = debt_mat
            result.cash_matrix = cash_mat
            result.ev = ev_mat
            result.interest = interest_mat
        return result
