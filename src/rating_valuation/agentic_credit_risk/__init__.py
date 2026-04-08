"""Agentic Credit Risk — forward-looking stochastic simulation of default risk.

Estimates corporate Probability of Default and Loss Given Default by simulating
the joint dynamics of revenues, margins, capital intensity and debt under a
Monte Carlo framework. Determines enterprise value and debt endogenously and
jointly, without relying on market prices, so it can be applied to private
companies and to multi-year horizons.

Reference (methodology origin): Montesi G., Papiro G., "Risk Analysis
Probability of Default: A Stochastic Simulation Model", Draft April 2014.
"""

from rating_valuation.agentic_credit_risk.credit_metrics import (
    CreditMetrics,
    compute_metrics,
)
from rating_valuation.agentic_credit_risk.debt_solver import (
    interest_expense,
    operating_cash_flow,
    simulate_period_scalar,
    simulate_period_vectorized,
    solve_debt_scalar,
    solve_debt_vectorized,
)
from rating_valuation.agentic_credit_risk.simulator import (
    AgenticCreditRiskResult,
    AgenticCreditRiskSimulator,
    InitialState,
)
from rating_valuation.agentic_credit_risk.stochastic import (
    StochasticParameters,
    WeibullParams,
    build_covariance_matrix,
    sample_scenarios,
)

__all__ = [
    "AgenticCreditRiskResult",
    "AgenticCreditRiskSimulator",
    "CreditMetrics",
    "InitialState",
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
