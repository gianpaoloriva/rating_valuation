"""Backtest comparator for credit risk models.

Benchmarks RAPD against simpler reference models (Altman Z-score for now;
Merton-style models can be added later when market data is available).

Reference: Montesi/Papiro (2014), Section 5 — "RAPD comparative back-testing".
"""

from rating_valuation.backtest.comparator import (
    BacktestResult,
    BacktestRow,
    BacktestRunner,
    auroc,
    gini_coefficient,
    kolmogorov_smirnov,
)

__all__ = [
    "BacktestResult",
    "BacktestRow",
    "BacktestRunner",
    "auroc",
    "gini_coefficient",
    "kolmogorov_smirnov",
]
