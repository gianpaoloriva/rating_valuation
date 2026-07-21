"""Backtest comparator for credit risk models.

Benchmarks the Agentic Credit Risk model against simpler reference models
(Altman Z-score for now; Merton-style models can be added later when market
data is available).

Reference: Montesi/Papiro (2014), Section 5 — comparative back-testing.
"""

from rating_valuation.backtest.comparator import (
    BacktestResult,
    BacktestRow,
    BacktestRunner,
    PDDistribution,
    auroc,
    gini_coefficient,
    kolmogorov_smirnov,
    pd_distribution,
)

__all__ = [
    "BacktestResult",
    "BacktestRow",
    "BacktestRunner",
    "PDDistribution",
    "auroc",
    "gini_coefficient",
    "kolmogorov_smirnov",
    "pd_distribution",
]
