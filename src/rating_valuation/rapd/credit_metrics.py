"""Credit metrics aggregation — PD, LGD, EL, UL from Monte Carlo output.

Given the simulation results (matrices of EV, Debt, and default flags),
this module computes:

    Yearly Default Frequency   — P(EV_t < D_t)                      (unconditional)
    Yearly Marginal Default    — P(default in t | no default in 1..t-1)
    Cumulative PD              — P(default in any year up to t)
    LGD (per scenario)         — max(0, EAD - EV - CASH)
    LGD summary                — mean, median, std, quantiles
    Expected Loss              — PD × mean(LGD)
    Unexpected Loss            — LGD at a chosen confidence level
    Recovery rate              — 1 − LGD_mean / EAD_mean

Reference: Montesi/Papiro (2014), Section 2.3 and eq. [14]-[16].
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# -----------------------------------------------------------------------------
# Result container
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class CreditMetrics:
    n_trials: int
    n_years: int

    # Probabilities of default
    yearly_default_frequency: np.ndarray   # shape (n_years,)
    yearly_marginal_default: np.ndarray    # shape (n_years,)
    cumulative_pd: np.ndarray              # shape (n_years,)

    # LGD / EL / UL
    lgd_mean: float
    lgd_median: float
    lgd_std: float
    lgd_quantiles: dict[float, float]      # {0.25: x, 0.75: y, 0.95: z, 0.99: w}
    ead_mean: float                        # expected EAD across default scenarios
    recovery_rate_mean: float
    expected_loss: float
    unexpected_loss_95: float
    unexpected_loss_99: float

    # Diagnostic
    n_default_scenarios: int
    default_rates_all_horizons: np.ndarray = field(default_factory=lambda: np.array([]))

    def summary(self) -> dict:
        return {
            "trials": self.n_trials,
            "horizon_years": self.n_years,
            "pd_cumulative_final": float(self.cumulative_pd[-1]) if len(self.cumulative_pd) else 0.0,
            "yearly_default_frequency": [float(x) for x in self.yearly_default_frequency],
            "marginal_pd": [float(x) for x in self.yearly_marginal_default],
            "cumulative_pd": [float(x) for x in self.cumulative_pd],
            "lgd_mean": self.lgd_mean,
            "lgd_median": self.lgd_median,
            "lgd_std": self.lgd_std,
            "lgd_q25": self.lgd_quantiles.get(0.25),
            "lgd_q75": self.lgd_quantiles.get(0.75),
            "lgd_q95": self.lgd_quantiles.get(0.95),
            "lgd_q99": self.lgd_quantiles.get(0.99),
            "ead_mean": self.ead_mean,
            "recovery_rate_mean": self.recovery_rate_mean,
            "expected_loss": self.expected_loss,
            "unexpected_loss_95": self.unexpected_loss_95,
            "unexpected_loss_99": self.unexpected_loss_99,
            "default_scenarios": self.n_default_scenarios,
        }


# -----------------------------------------------------------------------------
# Computation
# -----------------------------------------------------------------------------


def compute_metrics(
    *,
    ev: np.ndarray,         # shape (n_trials, n_years) — EV at each period
    debt: np.ndarray,       # shape (n_trials, n_years) — end-of-period debt
    cash: np.ndarray,       # shape (n_trials, n_years) — excess cash at period end
) -> CreditMetrics:
    """Aggregate EV / debt / cash matrices into credit metrics.

    Default condition (RAPD eq. [13]):  ``EV_t < D_t - CASH_t``
    """
    if ev.shape != debt.shape or ev.shape != cash.shape:
        raise ValueError("ev, debt, cash must share the same shape")
    n_trials, n_years = ev.shape

    default_matrix = ev < (debt - cash)  # shape (n_trials, n_years)

    # Yearly (unconditional) default frequency
    yearly_freq = default_matrix.mean(axis=0)

    # First-default index per trial (or -1 if no default)
    any_default = default_matrix.any(axis=1)
    first_default_year = np.where(
        any_default,
        default_matrix.argmax(axis=1),  # argmax returns first True
        -1,
    )

    # Cumulative PD: fraction of trials that have defaulted by end of year t
    cumulative_pd = np.zeros(n_years)
    for t in range(n_years):
        cumulative_pd[t] = ((first_default_year >= 0) & (first_default_year <= t)).mean()

    # Marginal PD: P(default at t | not defaulted before)
    marginal_pd = np.zeros(n_years)
    marginal_pd[0] = cumulative_pd[0]
    for t in range(1, n_years):
        survived = 1.0 - cumulative_pd[t - 1]
        marginal_pd[t] = (cumulative_pd[t] - cumulative_pd[t - 1]) / survived if survived > 0 else 0.0

    # --- LGD per default scenario ----------------------------------------
    # Use the first default period for each defaulted trial
    default_trials = np.where(any_default)[0]
    if len(default_trials) == 0:
        return CreditMetrics(
            n_trials=n_trials,
            n_years=n_years,
            yearly_default_frequency=yearly_freq,
            yearly_marginal_default=marginal_pd,
            cumulative_pd=cumulative_pd,
            lgd_mean=0.0,
            lgd_median=0.0,
            lgd_std=0.0,
            lgd_quantiles={0.25: 0.0, 0.5: 0.0, 0.75: 0.0, 0.95: 0.0, 0.99: 0.0},
            ead_mean=0.0,
            recovery_rate_mean=1.0,
            expected_loss=0.0,
            unexpected_loss_95=0.0,
            unexpected_loss_99=0.0,
            n_default_scenarios=0,
        )

    first_periods = first_default_year[default_trials]
    ead_at_default = debt[default_trials, first_periods]
    ev_at_default = ev[default_trials, first_periods]
    cash_at_default = cash[default_trials, first_periods]

    lgd = np.maximum(0.0, ead_at_default - ev_at_default - cash_at_default)
    recovery = 1.0 - lgd / np.maximum(ead_at_default, 1e-12)

    lgd_mean = float(lgd.mean())
    lgd_median = float(np.median(lgd))
    lgd_std = float(lgd.std(ddof=1)) if len(lgd) > 1 else 0.0
    lgd_quantiles = {
        0.25: float(np.quantile(lgd, 0.25)),
        0.5: float(np.quantile(lgd, 0.5)),
        0.75: float(np.quantile(lgd, 0.75)),
        0.95: float(np.quantile(lgd, 0.95)),
        0.99: float(np.quantile(lgd, 0.99)),
    }

    ead_mean = float(ead_at_default.mean())
    recovery_rate_mean = float(recovery.mean())

    # Expected loss on the total portfolio (per trial, not per default)
    # EL = cumulative_PD × mean_LGD (simplification)
    expected_loss = float(cumulative_pd[-1] * lgd_mean)

    # Unexpected loss — LGD at confidence interval, conditional on default
    unexpected_loss_95 = lgd_quantiles[0.95]
    unexpected_loss_99 = lgd_quantiles[0.99]

    return CreditMetrics(
        n_trials=n_trials,
        n_years=n_years,
        yearly_default_frequency=yearly_freq,
        yearly_marginal_default=marginal_pd,
        cumulative_pd=cumulative_pd,
        lgd_mean=lgd_mean,
        lgd_median=lgd_median,
        lgd_std=lgd_std,
        lgd_quantiles=lgd_quantiles,
        ead_mean=ead_mean,
        recovery_rate_mean=recovery_rate_mean,
        expected_loss=expected_loss,
        unexpected_loss_95=unexpected_loss_95,
        unexpected_loss_99=unexpected_loss_99,
        n_default_scenarios=int(len(default_trials)),
        default_rates_all_horizons=cumulative_pd,
    )
