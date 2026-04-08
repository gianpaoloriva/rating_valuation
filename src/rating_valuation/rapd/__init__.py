"""RAPD — Risk Analysis Probability of Default stochastic simulation model.

Reference: Montesi G., Papiro G., "Risk Analysis Probability of Default:
A Stochastic Simulation Model", Draft April 2014.
"""

from rating_valuation.rapd.credit_metrics import CreditMetrics, compute_metrics
from rating_valuation.rapd.debt_solver import (
    interest_expense,
    operating_cash_flow,
    simulate_period_scalar,
    simulate_period_vectorized,
    solve_debt_scalar,
    solve_debt_vectorized,
)
from rating_valuation.rapd.simulator import InitialState, RAPDResult, RAPDSimulator
from rating_valuation.rapd.stochastic import (
    StochasticParameters,
    WeibullParams,
    build_covariance_matrix,
    sample_scenarios,
)

__all__ = [
    "CreditMetrics",
    "InitialState",
    "RAPDResult",
    "RAPDSimulator",
    "StochasticParameters",
    "WeibullParams",
    "build_covariance_matrix",
    "compute_metrics",
    "interest_expense",
    "operating_cash_flow",
    "sample_scenarios",
    "simulate_period_scalar",
    "simulate_period_vectorized",
    "solve_debt_scalar",
    "solve_debt_vectorized",
]
