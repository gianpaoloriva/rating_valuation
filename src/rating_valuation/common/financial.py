"""Core financial math helpers used by BMS, DCF and Agentic Credit Risk modules.

All formulas follow the conventions of the three reference papers:
- Discount rate is the WACC (pre-tax when used with capital cash flow à la
  Ruback 2002, after-tax when used with unlevered FCFF).
- Growth rate ``g`` is capped at long-run nominal GDP growth.
- Perpetuity formula is the Gordon growth model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class WACCInputs:
    """Components of the Weighted Average Cost of Capital."""

    risk_free_rate: float
    market_risk_premium: float
    beta_unlevered: float
    target_debt_to_equity: float  # D/E in market values
    cost_of_debt_pretax: float
    tax_rate: float


def relever_beta(beta_unlevered: float, debt_to_equity: float, tax_rate: float) -> float:
    """Hamada formula: beta_L = beta_U * (1 + (1-t) * D/E)."""
    return beta_unlevered * (1.0 + (1.0 - tax_rate) * debt_to_equity)


def cost_of_equity_capm(
    risk_free_rate: float,
    market_risk_premium: float,
    beta_levered: float,
) -> float:
    """CAPM: k_e = r_f + beta_L * MRP."""
    return risk_free_rate + beta_levered * market_risk_premium


def wacc_after_tax(inputs: WACCInputs) -> float:
    """After-tax WACC using CAPM for equity and target D/E.

    Used with unlevered FCFF. Returns a decimal (e.g. 0.085 for 8.5%).
    """
    beta_l = relever_beta(
        inputs.beta_unlevered, inputs.target_debt_to_equity, inputs.tax_rate
    )
    ke = cost_of_equity_capm(inputs.risk_free_rate, inputs.market_risk_premium, beta_l)
    w_d = inputs.target_debt_to_equity / (1.0 + inputs.target_debt_to_equity)
    w_e = 1.0 - w_d
    return w_e * ke + w_d * inputs.cost_of_debt_pretax * (1.0 - inputs.tax_rate)


def wacc_pre_tax(inputs: WACCInputs) -> float:
    """Pre-tax WACC (Agentic Credit Risk convention, capital cash flow).

    The tax shield is embedded in the cash flows, so the discount rate
    must NOT be reduced by (1-t). See Ruback (2002).
    """
    beta_l = relever_beta(
        inputs.beta_unlevered, inputs.target_debt_to_equity, inputs.tax_rate
    )
    ke = cost_of_equity_capm(inputs.risk_free_rate, inputs.market_risk_premium, beta_l)
    w_d = inputs.target_debt_to_equity / (1.0 + inputs.target_debt_to_equity)
    w_e = 1.0 - w_d
    return w_e * ke + w_d * inputs.cost_of_debt_pretax


# -----------------------------------------------------------------------------
# Time value of money primitives
# -----------------------------------------------------------------------------


def discount_factor(rate: float, t: int) -> float:
    """Single-period discount factor ``1 / (1+r)^t``."""
    if not isfinite(rate) or rate <= -1.0:
        raise ValueError(f"Invalid discount rate: {rate}")
    return 1.0 / (1.0 + rate) ** t


def present_value(cash_flows: Sequence[float], rate: float, start_period: int = 1) -> float:
    """Discount a sequence of cash flows at a constant rate.

    ``cash_flows[0]`` is the cash flow at ``start_period`` (default: t=1,
    end-of-period convention).
    """
    return sum(
        cf * discount_factor(rate, start_period + i) for i, cf in enumerate(cash_flows)
    )


def perpetuity(cash_flow: float, rate: float, growth: float = 0.0) -> float:
    """Gordon growth perpetuity.

    ``PV = CF / (r - g)``. Assumes the first cash flow is paid one period from now.
    """
    if rate <= growth:
        raise ValueError(
            f"Discount rate ({rate:.4f}) must exceed growth rate ({growth:.4f})"
        )
    return cash_flow / (rate - growth)


def terminal_value_gordon(
    fcff_last: float, wacc: float, growth: float
) -> float:
    """Standard 2-stage TV formula: ``FCFF_T * (1+g) / (wacc - g)``.

    This is the formulation used by most analysts (and by the Scarano/Di Napoli
    article as the starting point) before the coherence check.
    """
    return perpetuity(fcff_last * (1.0 + growth), wacc, growth)


# -----------------------------------------------------------------------------
# Key operating ratios used by BMS, DCF and Agentic Credit Risk
# -----------------------------------------------------------------------------


def nopat_from_ebit(ebit: float, tax_rate: float) -> float:
    """NOPAT = EBIT * (1 - t)."""
    return ebit * (1.0 - tax_rate)


def roic(nopat: float, net_invested_capital: float) -> float:
    """Return on Invested Capital = NOPAT / NIC."""
    if net_invested_capital == 0:
        raise ZeroDivisionError("ROIC undefined: NIC is zero")
    return nopat / net_invested_capital


def reinvestment_rate(growth: float, roic_new_investments: float) -> float:
    """Coherent reinvestment ratio from the TV paper: ``h = g / ROIC``.

    Represents the share of NOPAT that must be reinvested to sustain growth g
    given the return ROIC on new investments.
    """
    if roic_new_investments == 0:
        raise ZeroDivisionError("Reinvestment rate undefined: ROIC is zero")
    return growth / roic_new_investments


def implied_growth(roic_new_investments: float, reinvestment: float) -> float:
    """Reverse of ``reinvestment_rate``: ``g = ROIC * h``."""
    return roic_new_investments * reinvestment
