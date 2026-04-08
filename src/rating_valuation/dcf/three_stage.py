"""Three-stage DCF valuation with a convergence (fade) period.

Implements the model proposed by Scarano/Di Napoli where the marginal ROIC
decays geometrically toward the WACC during an intermediate "convergence"
stage. When the steady state is reached (ROIC == WACC) the Terminal Value
collapses to the simplified formula ``TV = NOPAT / wacc`` (no value created
by growth at marginal rates equal to the cost of capital).

Stages:

    Stage 1 — explicit forecast (analyst provides explicit FCFFs and NOPATs)
    Stage 2 — convergence: ROIC_marginal decays from a starting value down to
              WACC over ``n_convergence_years`` using a geometric rate
              ``decay = (wacc / roic_start) ** (1/n) - 1``. Each year the
              operating cash flow is re-derived from NOPAT using the
              reinvestment identity (g = ROIC_marginal * h, h = g/ROIC_marginal).
    Stage 3 — steady state: TV computed with ``NOPAT/wacc``.

Reference: AIAF n. 66 (2008), Scarano/Di Napoli, pp. 30-32.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median

from rating_valuation.common.financial import discount_factor
from rating_valuation.dcf.coherence import (
    CoherenceReport,
    check_coherence,
)


@dataclass(frozen=True)
class ThreeStageInputs:
    # Stage 1 — explicit forecast ---------------------------------------------
    fcff_explicit: tuple[float, ...]            # t=1..T1
    nopat_at_t1: float                          # NOPAT at end of stage 1
    wacc: float                                 # WACC (after-tax for FCFF)

    # Stage 2 — convergence ---------------------------------------------------
    n_convergence_years: int                    # length of stage 2
    roic_marginal_start: float                  # ROIC_marginal entering stage 2
    growth_stage2: float                        # NOPAT growth during stage 2

    # Optional base for the ROIC decay formula. When None, the fade rate is
    # computed from ``roic_marginal_start`` (the value at the stage-1/stage-2
    # boundary). When set, the fade rate starts from this value — matching
    # the paper's convention (Scarano/Di Napoli p. 31) of using the MEDIAN
    # marginal ROIC of stage 1 as the starting point, which yields a less
    # aggressive decay than starting from the last-year ROIC.
    roic_marginal_decay_base: float | None = None

    # Stage 3 — steady state --------------------------------------------------
    # (optional) allow a terminal growth even in the simplified formula;
    # default is 0 meaning TV = NOPAT / wacc. Setting it > 0 contradicts the
    # premise "ROIC = WACC → growth creates no value" and triggers a warning.
    terminal_growth: float = 0.0

    # Balance sheet bridge ----------------------------------------------------
    net_debt_today: float = 0.0
    excess_cash_today: float = 0.0

    # Optional GDP cap for coherence check C1 (long-run g <= g_PIL). When
    # None the C1 check is skipped (effectively g cap = +inf). Pass a macro
    # value from `data/macro.csv` to enable automatic enforcement.
    gdp_nominal_5y_avg: float | None = None


@dataclass(frozen=True)
class StageFlow:
    year_index: int                             # 1-based (year after t0)
    stage: str                                  # 'explicit' | 'convergence' | 'terminal'
    nopat: float
    roic_marginal: float
    reinvestment_rate: float                    # h = g / ROIC_marginal
    capital_investment: float                   # ΔCI = h * NOPAT
    operating_cash_flow: float                  # FCFF = NOPAT - ΔCI
    discount_factor: float
    present_value: float


@dataclass(frozen=True)
class ThreeStageResult:
    explicit_pv: float
    convergence_pv: float
    terminal_value: float
    terminal_value_pv: float
    enterprise_value: float
    equity_value: float
    tv_weight: float
    fade_rate: float                            # geometric decay applied per year
    flows: tuple[StageFlow, ...] = field(default_factory=tuple)
    inputs: ThreeStageInputs | None = None
    # Automatically populated by value_three_stage — runs the 6+1 coherence
    # checks from `dcf/coherence.py` using the inputs actually used for the
    # valuation. The paper (Scarano/Di Napoli) insists that coherence
    # validation must not be a separate, skippable step: here it is always
    # there alongside the numbers.
    coherence_report: CoherenceReport | None = None

    def as_dict(self) -> dict:
        return {
            "explicit_pv": self.explicit_pv,
            "convergence_pv": self.convergence_pv,
            "terminal_value": self.terminal_value,
            "terminal_value_pv": self.terminal_value_pv,
            "enterprise_value": self.enterprise_value,
            "equity_value": self.equity_value,
            "tv_weight": self.tv_weight,
            "fade_rate": self.fade_rate,
        }


# -----------------------------------------------------------------------------
# Core calculation
# -----------------------------------------------------------------------------


def _validate(inputs: ThreeStageInputs) -> None:
    if not inputs.fcff_explicit:
        raise ValueError("fcff_explicit must contain at least one year")
    if inputs.n_convergence_years < 1:
        raise ValueError("n_convergence_years must be at least 1")
    if inputs.roic_marginal_start <= 0:
        raise ValueError("roic_marginal_start must be positive")
    if inputs.wacc <= 0:
        raise ValueError("wacc must be positive")
    if inputs.wacc <= inputs.terminal_growth:
        raise ValueError(
            f"WACC ({inputs.wacc:.4f}) must exceed terminal growth "
            f"({inputs.terminal_growth:.4f})"
        )
    if inputs.roic_marginal_start < inputs.wacc:
        raise ValueError(
            "ROIC_marginal_start should be >= WACC (otherwise convergence is trivial). "
            f"Got ROIC={inputs.roic_marginal_start}, WACC={inputs.wacc}."
        )


def compute_fade_rate(
    roic_start: float,
    wacc: float,
    n_years: int,
) -> float:
    """Annual geometric decay needed for ROIC to reach WACC in ``n_years``.

    ``roic_{t+1} = roic_t * (1 + decay)``, with ``decay < 0`` when
    ``roic_start > wacc``. Derived from the formula in Scarano/Di Napoli, p. 31.
    """
    if n_years < 1:
        raise ValueError("n_years must be >= 1")
    if roic_start <= 0 or wacc <= 0:
        raise ValueError("roic_start and wacc must be positive")
    return (wacc / roic_start) ** (1.0 / n_years) - 1.0


def median_roic_marginal_from_explicit(
    nopat: Sequence[float],
    nic: Sequence[float],
) -> float:
    """Median of the marginal ROIC over the explicit forecast period.

    Computes ``ROIC_marginal_t = ΔNOPAT_t / ΔCIN_avg_t`` year by year
    (Scarano/Di Napoli paper, Tabella 2 p. 30) and returns the median.

    The paper uses this median as the starting point of the geometric decay
    in the stage-2 convergence formula ``decay = (wacc / roic_median)^(1/n) − 1``.
    Starting from the median is less sensitive to a single high-ROIC year
    than starting from the last-year ROIC, and is what the paper's worked
    example implicitly uses.

    Parameters
    ----------
    nopat : sequence of float
        NOPAT series of the explicit forecast, ordered by year.
        At least 2 elements are required.
    nic : sequence of float
        Net Invested Capital series of the explicit forecast, ordered by year.
        Must have the same length as ``nopat``.

    Returns
    -------
    float
        Median of the marginal ROICs computed over the explicit period.
    """
    nopat_list = list(nopat)
    nic_list = list(nic)
    if len(nopat_list) != len(nic_list):
        raise ValueError("nopat and nic must have the same length")
    if len(nopat_list) < 2:
        raise ValueError("At least 2 years of NOPAT/NIC are required")

    marginals: list[float] = []
    for t in range(1, len(nopat_list)):
        delta_nopat = nopat_list[t] - nopat_list[t - 1]
        delta_nic = nic_list[t] - nic_list[t - 1]
        if delta_nic <= 0:
            # Skip years where NIC does not grow: the marginal ROIC is
            # undefined or pathological (and the paper's table also drops them).
            continue
        marginals.append(delta_nopat / delta_nic)

    if not marginals:
        raise ValueError(
            "Cannot compute marginal ROIC: NIC does not grow in any year"
        )
    return float(median(marginals))


def value_three_stage(inputs: ThreeStageInputs) -> ThreeStageResult:
    """Run the 3-stage DCF and return the full decomposition.

    Automatically attaches a :class:`CoherenceReport` to the result — the
    Scarano/Di Napoli paper treats TV validation as an integral part of the
    computation, not an optional step.
    """
    _validate(inputs)

    # Warn on the economic inconsistency of positive terminal growth in the
    # steady-state stage: if ROIC == WACC, growth creates no value, and the
    # formula NOPAT/(wacc - g_term) amplifies the TV through a growth that
    # by construction is non-value-accretive.
    if inputs.terminal_growth > 0.0:
        warnings.warn(
            f"value_three_stage: terminal_growth = {inputs.terminal_growth:.4f} > 0 "
            f"with ROIC = WACC contraddice la premessa dello stadio 3 "
            f"(la crescita non genera valore quando ROIC_NI = WACC). "
            f"Usare terminal_growth = 0 — la crescita residua va modellata "
            f"nello stadio 2 di convergenza.",
            stacklevel=2,
        )

    flows: list[StageFlow] = []
    # --- Stage 1: explicit forecast -----------------------------------------
    explicit_pv = 0.0
    for t, fcff in enumerate(inputs.fcff_explicit, start=1):
        df = discount_factor(inputs.wacc, t)
        pv = fcff * df
        explicit_pv += pv
        flows.append(
            StageFlow(
                year_index=t,
                stage="explicit",
                nopat=float("nan"),  # analyst-provided FCFF; NOPAT not required here
                roic_marginal=float("nan"),
                reinvestment_rate=float("nan"),
                capital_investment=float("nan"),
                operating_cash_flow=fcff,
                discount_factor=df,
                present_value=pv,
            )
        )

    t1 = len(inputs.fcff_explicit)

    # --- Stage 2: convergence -----------------------------------------------
    # If the caller provided an explicit decay base (e.g. the median
    # marginal ROIC of stage 1, as in the paper's worked example), use it.
    # Otherwise fall back on `roic_marginal_start` — the entry-point value,
    # which matches the previous behavior and is retained for backward
    # compatibility.
    decay_base = (
        inputs.roic_marginal_decay_base
        if inputs.roic_marginal_decay_base is not None
        else inputs.roic_marginal_start
    )
    fade = compute_fade_rate(
        roic_start=decay_base,
        wacc=inputs.wacc,
        n_years=inputs.n_convergence_years,
    )

    convergence_pv = 0.0
    current_nopat = inputs.nopat_at_t1
    current_roic = decay_base
    g2 = inputs.growth_stage2

    for step in range(1, inputs.n_convergence_years + 1):
        # NOPAT grows at stage-2 growth rate
        current_nopat = current_nopat * (1.0 + g2)
        # ROIC fades toward WACC
        current_roic = current_roic * (1.0 + fade)

        # Reinvestment identity: h = g / ROIC_marginal
        h = g2 / current_roic if current_roic > 0 else 0.0
        capital_investment = h * current_nopat
        fcff = current_nopat - capital_investment

        year = t1 + step
        df = discount_factor(inputs.wacc, year)
        pv = fcff * df
        convergence_pv += pv

        flows.append(
            StageFlow(
                year_index=year,
                stage="convergence",
                nopat=current_nopat,
                roic_marginal=current_roic,
                reinvestment_rate=h,
                capital_investment=capital_investment,
                operating_cash_flow=fcff,
                discount_factor=df,
                present_value=pv,
            )
        )

    # --- Stage 3: steady state (TV) -----------------------------------------
    # At the end of stage 2, ROIC should equal WACC: TV = NOPAT / (wacc - g_terminal)
    # If terminal_growth is 0 the formula is the simplified NOPAT/wacc.
    terminal_nopat = current_nopat * (1.0 + inputs.terminal_growth)
    tv = terminal_nopat / (inputs.wacc - inputs.terminal_growth)
    t_tv = t1 + inputs.n_convergence_years
    df_tv = discount_factor(inputs.wacc, t_tv)
    tv_pv = tv * df_tv

    flows.append(
        StageFlow(
            year_index=t_tv,
            stage="terminal",
            nopat=terminal_nopat,
            roic_marginal=inputs.wacc,
            reinvestment_rate=inputs.terminal_growth / inputs.wacc if inputs.wacc > 0 else 0.0,
            capital_investment=terminal_nopat * (inputs.terminal_growth / inputs.wacc)
            if inputs.wacc > 0 else 0.0,
            operating_cash_flow=tv,  # we store the raw TV here
            discount_factor=df_tv,
            present_value=tv_pv,
        )
    )

    ev = explicit_pv + convergence_pv + tv_pv
    tv_weight = tv_pv / ev if ev > 0 else float("nan")

    # --- Automatic coherence check ------------------------------------------
    # The 3-stage model satisfies the reinvestment identity by construction
    # (we compute h from ROIC/g) and uses the steady-state formula for the
    # TV (ROIC = WACC ⇒ shortcut NOPAT/wacc). We nevertheless run the
    # full validator so that pathological inputs (e.g. g > g_PIL, TV weight
    # too high, ROIC final not converged) are surfaced without the caller
    # having to remember to invoke check_coherence() separately.
    gdp_cap = (
        inputs.gdp_nominal_5y_avg
        if inputs.gdp_nominal_5y_avg is not None
        else float("inf")
    )
    coherence_report = check_coherence(
        wacc=inputs.wacc,
        growth=inputs.terminal_growth,
        roic_new_investments=inputs.wacc,  # stage 3 premise: ROIC_NI = WACC
        implied_reinvestment=(
            inputs.terminal_growth / inputs.wacc if inputs.wacc > 0 else 0.0
        ),
        tv_weight=tv_weight,
        roic_marginal_final=current_roic,
        nopat_t_plus_1=terminal_nopat,
        gdp_nominal_5y_avg=gdp_cap,
        used_coherent_formula=True,
    )

    return ThreeStageResult(
        explicit_pv=explicit_pv,
        convergence_pv=convergence_pv,
        terminal_value=tv,
        terminal_value_pv=tv_pv,
        enterprise_value=ev,
        equity_value=ev - inputs.net_debt_today + inputs.excess_cash_today,
        tv_weight=tv_weight,
        fade_rate=fade,
        flows=tuple(flows),
        inputs=inputs,
        coherence_report=coherence_report,
    )
