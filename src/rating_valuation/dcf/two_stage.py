"""Two-stage DCF valuation.

Implements the standard two-stage model:

    EV = sum_{t=1..T} FCFF_t / (1+wacc)^t  +  TV / (1+wacc)^T
    TV = FCFF_T * (1+g) / (wacc - g)

This is the starting point of the Scarano/Di Napoli article; the coherence
checks live in `coherence.py` and the 3-stage refinement in `three_stage.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rating_valuation.common.financial import (
    discount_factor,
    perpetuity,
    terminal_value_gordon,
)


@dataclass(frozen=True)
class TwoStageInputs:
    fcff_explicit: tuple[float, ...]   # explicit forecast, length T (t=1..T)
    wacc: float                         # discount rate (after-tax WACC for FCFF)
    terminal_growth: float              # long-run g for TV
    wacc_terminal: float | None = None  # optional different WACC in perpetuity
    net_debt_today: float = 0.0         # to derive equity value
    excess_cash_today: float = 0.0      # rarely used, kept for completeness


@dataclass(frozen=True)
class TwoStageResult:
    explicit_pv: float                  # sum of discounted FCFFs
    terminal_value: float               # raw TV at time T
    terminal_value_pv: float            # discounted TV at time 0
    enterprise_value: float             # explicit_pv + terminal_value_pv
    equity_value: float                 # EV - net debt + excess cash
    tv_weight: float                    # terminal_value_pv / enterprise_value
    inputs: TwoStageInputs

    def as_dict(self) -> dict:
        return {
            "explicit_pv": self.explicit_pv,
            "terminal_value": self.terminal_value,
            "terminal_value_pv": self.terminal_value_pv,
            "enterprise_value": self.enterprise_value,
            "equity_value": self.equity_value,
            "tv_weight": self.tv_weight,
        }


def _validate(inputs: TwoStageInputs) -> None:
    if not inputs.fcff_explicit:
        raise ValueError("fcff_explicit must contain at least one year of cash flows")
    if inputs.wacc <= inputs.terminal_growth:
        raise ValueError(
            f"WACC ({inputs.wacc:.4f}) must exceed terminal growth ({inputs.terminal_growth:.4f})"
        )
    if inputs.wacc_terminal is not None and inputs.wacc_terminal <= inputs.terminal_growth:
        raise ValueError(
            f"Terminal WACC ({inputs.wacc_terminal:.4f}) must exceed "
            f"terminal growth ({inputs.terminal_growth:.4f})"
        )


def value_two_stage(inputs: TwoStageInputs) -> TwoStageResult:
    """Compute enterprise and equity value using a 2-stage DCF."""
    _validate(inputs)

    # Explicit stage: discount each FCFF at the WACC
    explicit_pv = sum(
        fcff * discount_factor(inputs.wacc, t)
        for t, fcff in enumerate(inputs.fcff_explicit, start=1)
    )

    # Terminal value at time T, using the Gordon formula
    wacc_tv = inputs.wacc_terminal if inputs.wacc_terminal is not None else inputs.wacc
    fcff_last = inputs.fcff_explicit[-1]
    tv = terminal_value_gordon(fcff_last=fcff_last, wacc=wacc_tv, growth=inputs.terminal_growth)
    tv_pv = tv * discount_factor(inputs.wacc, len(inputs.fcff_explicit))

    ev = explicit_pv + tv_pv
    equity = ev - inputs.net_debt_today + inputs.excess_cash_today

    return TwoStageResult(
        explicit_pv=explicit_pv,
        terminal_value=tv,
        terminal_value_pv=tv_pv,
        enterprise_value=ev,
        equity_value=equity,
        tv_weight=tv_pv / ev if ev > 0 else float("nan"),
        inputs=inputs,
    )


# -----------------------------------------------------------------------------
# Convenience: value using the TV formula with reinvestment adjustment
# (Scarano/Di Napoli coherent version)
# -----------------------------------------------------------------------------


def terminal_value_coherent(
    nopat_t_plus_1: float,
    wacc: float,
    growth: float,
    roic_new_investments: float,
) -> float:
    """Reinvestment-adjusted TV: ``NOPAT_{T+1} * (1 - g/ROIC_NI) / (wacc - g)``.

    When ``roic_new_investments == wacc`` this simplifies to ``NOPAT_{T+1} / wacc``
    (steady state, no value from extra growth).
    """
    if wacc <= growth:
        raise ValueError(f"WACC ({wacc}) must exceed growth ({growth})")
    if roic_new_investments <= 0:
        raise ValueError("ROIC on new investments must be positive")
    reinvestment = growth / roic_new_investments
    fcff_normalized = nopat_t_plus_1 * (1.0 - reinvestment)
    return perpetuity(fcff_normalized, wacc, growth)


def value_two_stage_coherent(
    fcff_explicit: Sequence[float],
    nopat_t_plus_1: float,
    wacc: float,
    terminal_growth: float,
    roic_new_investments: float,
    net_debt_today: float = 0.0,
    excess_cash_today: float = 0.0,
    wacc_terminal: float | None = None,
) -> TwoStageResult:
    """DCF a due stadi con TV "coerente" alla Scarano/Di Napoli.

    Il TV viene calcolato con la formula che esplicita il vincolo di
    reinvestimento ``g = ROIC_NI · h``, quindi ``TV = NOPAT_{T+1}·(1-g/ROIC)/(wacc-g)``.
    Se ``ROIC_NI == wacc`` la formula collassa su ``NOPAT_{T+1}/wacc``.
    """
    fcff_tuple = tuple(fcff_explicit)
    if not fcff_tuple:
        raise ValueError("fcff_explicit must not be empty")
    if wacc <= terminal_growth:
        raise ValueError(f"WACC ({wacc}) must exceed growth ({terminal_growth})")

    explicit_pv = sum(
        fcff * discount_factor(wacc, t)
        for t, fcff in enumerate(fcff_tuple, start=1)
    )

    wacc_tv = wacc_terminal if wacc_terminal is not None else wacc
    tv = terminal_value_coherent(
        nopat_t_plus_1=nopat_t_plus_1,
        wacc=wacc_tv,
        growth=terminal_growth,
        roic_new_investments=roic_new_investments,
    )
    tv_pv = tv * discount_factor(wacc, len(fcff_tuple))
    ev = explicit_pv + tv_pv

    return TwoStageResult(
        explicit_pv=explicit_pv,
        terminal_value=tv,
        terminal_value_pv=tv_pv,
        enterprise_value=ev,
        equity_value=ev - net_debt_today + excess_cash_today,
        tv_weight=tv_pv / ev if ev > 0 else float("nan"),
        inputs=TwoStageInputs(
            fcff_explicit=fcff_tuple,
            wacc=wacc,
            terminal_growth=terminal_growth,
            wacc_terminal=wacc_terminal,
            net_debt_today=net_debt_today,
            excess_cash_today=excess_cash_today,
        ),
    )
