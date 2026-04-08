"""Terminal Value coherence validator.

Encodes the coherence checks described in the Scarano/Di Napoli paper
(Rivista AIAF n. 66, 2008, pp. 27-32) and in the `dcf-validator` subagent:

    C1 — g <= GDP nominal growth (long run)
    C2 — g = ROIC_NI * h_T
    C3 — TV formula uses the reinvestment adjustment (or steady-state shortcut)
    C4 — TV share of enterprise value is not pathologically high
    C5 — ROIC_marginal converges to WACC at the end of the explicit period
    C6 — sign and bound checks (wacc > g, NOPAT > 0, g >= -inflation)
    C7 — reinvestment rate h_T = g/ROIC_NI is inside [0, 1]

Any ERROR should block the DCF from being accepted as a valid valuation.
WARNING should be surfaced to the analyst but does not block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class Severity(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class CoherenceCheck:
    code: str
    name: str
    severity: Severity
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def is_ok(self) -> bool:
        return self.severity == Severity.PASS


@dataclass(frozen=True)
class CoherenceReport:
    checks: tuple[CoherenceCheck, ...]

    @property
    def verdict(self) -> Severity:
        if any(c.severity == Severity.ERROR for c in self.checks):
            return Severity.ERROR
        if any(c.severity == Severity.WARNING for c in self.checks):
            return Severity.WARNING
        return Severity.PASS

    def errors(self) -> tuple[CoherenceCheck, ...]:
        return tuple(c for c in self.checks if c.severity == Severity.ERROR)

    def warnings(self) -> tuple[CoherenceCheck, ...]:
        return tuple(c for c in self.checks if c.severity == Severity.WARNING)

    def as_table(self) -> list[dict]:
        return [
            {
                "code": c.code,
                "name": c.name,
                "severity": c.severity.value,
                "message": c.message,
            }
            for c in self.checks
        ]


# -----------------------------------------------------------------------------
# Individual checks
# -----------------------------------------------------------------------------


def check_g_below_gdp_from_macro(
    growth: float,
    country: str,
    year: int,
    macro_df: pd.DataFrame | None = None,
    tolerance: float = 0.0005,
) -> CoherenceCheck:
    """Convenience wrapper around :func:`check_g_below_gdp`.

    Reads ``gdp_nominal_growth_5y_avg`` for ``(country, year)`` directly from
    ``data/macro.csv`` instead of requiring the caller to pass it explicitly.
    This is the form the Scarano/Di Napoli paper implicitly assumes: the
    GDP cap is a macro constant that should be automatically enforced, not
    a parameter the analyst can quietly dodge.

    Parameters
    ----------
    growth : float
        Terminal growth rate to validate.
    country : str
        ISO-3166 alpha-2 country code (e.g. ``"IT"``).
    year : int
        Fiscal year base used to pick the macro row.
    macro_df : pd.DataFrame, optional
        If provided, skip the CSV load and use this DataFrame. Useful for
        tests and for callers that already have a preloaded bundle.
    tolerance : float
        Same meaning as in :func:`check_g_below_gdp`.
    """
    if macro_df is None:
        # Local import to avoid a circular dependency with data_loader
        from rating_valuation.common.data_loader import load_macro

        macro_df = load_macro()

    row = macro_df[(macro_df["country"] == country) & (macro_df["year"] == year)]
    if row.empty:
        return CoherenceCheck(
            code="C1",
            name="g <= GDP nominal growth (long run)",
            severity=Severity.ERROR,
            message=(
                f"Nessun record macro per country={country!r}, year={year}. "
                f"Impossibile validare il cap su g."
            ),
            detail={"country": country, "year": year, "g": growth},
        )
    gdp_5y = float(row.iloc[0]["gdp_nominal_growth_5y_avg"])
    return check_g_below_gdp(growth, gdp_5y, tolerance=tolerance)


def check_g_below_gdp(
    growth: float,
    gdp_nominal_5y_avg: float,
    tolerance: float = 0.0005,  # 5 bps
) -> CoherenceCheck:
    """Check 1 — long-run growth cannot exceed nominal GDP growth.

    If violated the long-run cash flows would eventually exceed national GDP.
    """
    diff = growth - gdp_nominal_5y_avg
    if diff > tolerance:
        return CoherenceCheck(
            code="C1",
            name="g <= GDP nominal growth (long run)",
            severity=Severity.ERROR,
            message=(
                f"g = {growth:.4f} excede la crescita del PIL nominale di lungo periodo "
                f"({gdp_nominal_5y_avg:.4f}) di {diff*100:+.2f} p.p."
            ),
            detail={"g": growth, "gdp_nominal_5y_avg": gdp_nominal_5y_avg, "diff": diff},
        )
    return CoherenceCheck(
        code="C1",
        name="g <= GDP nominal growth (long run)",
        severity=Severity.PASS,
        message=f"g = {growth:.4f} entro il cap PIL nominale {gdp_nominal_5y_avg:.4f}",
        detail={"g": growth, "gdp_nominal_5y_avg": gdp_nominal_5y_avg},
    )


def check_reinvestment_identity(
    growth: float,
    roic_new_investments: float,
    implied_reinvestment: float,
    tolerance: float = 0.005,  # 0.5 p.p.
) -> CoherenceCheck:
    """Check 2 — Scarano/Di Napoli reinvestment identity.

    ``g == ROIC_NI * h_T``, equivalently ``h_T == g / ROIC_NI``.
    """
    if roic_new_investments <= 0:
        return CoherenceCheck(
            code="C2",
            name="g = ROIC_NI * h_T",
            severity=Severity.ERROR,
            message=f"ROIC_NI non positivo ({roic_new_investments:.4f}): identità non valutabile",
            detail={"roic_ni": roic_new_investments},
        )
    expected_h = growth / roic_new_investments
    diff = implied_reinvestment - expected_h
    if abs(diff) > tolerance:
        return CoherenceCheck(
            code="C2",
            name="g = ROIC_NI * h_T",
            severity=Severity.ERROR,
            message=(
                f"Tasso di reinvestimento h = {implied_reinvestment:.4f} "
                f"incoerente con g/ROIC = {expected_h:.4f} "
                f"(delta {diff*100:+.2f} p.p., tolleranza {tolerance*100:.1f} p.p.)"
            ),
            detail={
                "g": growth,
                "roic_ni": roic_new_investments,
                "h_expected": expected_h,
                "h_actual": implied_reinvestment,
                "diff": diff,
            },
        )
    return CoherenceCheck(
        code="C2",
        name="g = ROIC_NI * h_T",
        severity=Severity.PASS,
        message=(
            f"h = {implied_reinvestment:.4f} ≈ g/ROIC_NI = {expected_h:.4f} "
            f"(delta {diff*100:+.2f} p.p.)"
        ),
        detail={
            "g": growth,
            "roic_ni": roic_new_investments,
            "h_expected": expected_h,
            "h_actual": implied_reinvestment,
        },
    )


def check_tv_formula_used(
    used_coherent_formula: bool,
    roic_new_investments: float,
    wacc: float,
) -> CoherenceCheck:
    """Check 3 — the analyst must use the reinvestment-adjusted TV formula,
    unless they have verified that ``ROIC_NI == wacc`` (steady state shortcut)."""
    steady_state = abs(roic_new_investments - wacc) < 0.001
    if used_coherent_formula or steady_state:
        msg = (
            "Formula TV coerente applicata"
            if used_coherent_formula
            else "ROIC_NI ≈ WACC → shortcut steady-state NOPAT/WACC lecito"
        )
        return CoherenceCheck(
            code="C3",
            name="TV formula with reinvestment adjustment",
            severity=Severity.PASS,
            message=msg,
            detail={
                "steady_state": steady_state,
                "roic_ni": roic_new_investments,
                "wacc": wacc,
            },
        )
    return CoherenceCheck(
        code="C3",
        name="TV formula with reinvestment adjustment",
        severity=Severity.WARNING,
        message=(
            "Formula TV naive FCFF(1+g)/(wacc-g) senza verifica del reinvestimento. "
            "Usare TV = NOPAT(1 - g/ROIC)/(wacc - g)."
        ),
        detail={
            "steady_state": steady_state,
            "roic_ni": roic_new_investments,
            "wacc": wacc,
        },
    )


def check_tv_weight(
    tv_weight: float,
    warning_threshold: float = 0.80,
) -> CoherenceCheck:
    """Check 4 — the discounted TV should not dominate the EV excessively."""
    if tv_weight > warning_threshold:
        return CoherenceCheck(
            code="C4",
            name="TV share of enterprise value",
            severity=Severity.WARNING,
            message=(
                f"Peso del TV sul valore = {tv_weight:.1%} "
                f"(> {warning_threshold:.0%}). "
                "Considerare orizzonte esplicito più lungo o modello a 3 stadi."
            ),
            detail={"tv_weight": tv_weight, "threshold": warning_threshold},
        )
    return CoherenceCheck(
        code="C4",
        name="TV share of enterprise value",
        severity=Severity.PASS,
        message=f"Peso del TV = {tv_weight:.1%} (entro {warning_threshold:.0%})",
        detail={"tv_weight": tv_weight},
    )


def check_roic_convergence(
    roic_marginal_final: float,
    wacc: float,
    tolerance: float = 0.01,  # 1 p.p.
) -> CoherenceCheck:
    """Check 5 — the marginal ROIC at the end of the explicit period should be
    close to WACC (or a convergence period must follow)."""
    diff = roic_marginal_final - wacc
    if diff > tolerance:
        return CoherenceCheck(
            code="C5",
            name="ROIC_marginal convergence to WACC",
            severity=Severity.WARNING,
            message=(
                f"ROIC_marginale finale = {roic_marginal_final:.4f} > WACC = {wacc:.4f} "
                f"(+{diff*100:.2f} p.p.). Aggiungere stadio di convergenza."
            ),
            detail={"roic_marginal_final": roic_marginal_final, "wacc": wacc, "diff": diff},
        )
    return CoherenceCheck(
        code="C5",
        name="ROIC_marginal convergence to WACC",
        severity=Severity.PASS,
        message=(
            f"ROIC_marginale finale = {roic_marginal_final:.4f} ≈ WACC = {wacc:.4f} "
            f"(delta {diff*100:+.2f} p.p.)"
        ),
        detail={"roic_marginal_final": roic_marginal_final, "wacc": wacc},
    )


def check_reinvestment_bounds(
    growth: float,
    roic_new_investments: float,
) -> CoherenceCheck:
    """Check 7 — reinvestment rate ``h_T = g / ROIC_NI`` must lie in ``[0, 1]``.

    Equivalent to requiring that the normalized FCFF at steady state be
    non-negative (``FCFF = NOPAT·(1 - h_T)`` with ``h_T <= 1``) and the
    growth rate be non-negative (``h_T >= 0``). A violation means the
    business would need to reinvest more than 100% of its NOPAT to sustain
    the declared growth — equivalent to saying that ``g > ROIC_NI`` (the
    marginal investments are not profitable enough) and the TV is
    economically meaningless.
    """
    if roic_new_investments <= 0:
        return CoherenceCheck(
            code="C7",
            name="Reinvestment rate h_T in [0, 1]",
            severity=Severity.ERROR,
            message=f"ROIC_NI non positivo ({roic_new_investments:.4f}): h_T non definito",
            detail={"roic_ni": roic_new_investments, "g": growth},
        )
    h = growth / roic_new_investments
    if not 0.0 <= h <= 1.0:
        return CoherenceCheck(
            code="C7",
            name="Reinvestment rate h_T in [0, 1]",
            severity=Severity.ERROR,
            message=(
                f"h_T = g/ROIC_NI = {h:.4f} fuori da [0, 1] "
                f"(g={growth:.4f}, ROIC_NI={roic_new_investments:.4f}). "
                f"Se h_T > 1 il reinvestimento eccede il 100% del NOPAT; "
                f"il FCFF normalizzato è negativo e il TV perde senso economico."
            ),
            detail={"h": h, "g": growth, "roic_ni": roic_new_investments},
        )
    return CoherenceCheck(
        code="C7",
        name="Reinvestment rate h_T in [0, 1]",
        severity=Severity.PASS,
        message=f"h_T = g/ROIC_NI = {h:.4f} entro [0, 1]",
        detail={"h": h, "g": growth, "roic_ni": roic_new_investments},
    )


def check_bounds(
    wacc: float,
    growth: float,
    nopat_t_plus_1: float,
    inflation: float = 0.0,
) -> CoherenceCheck:
    """Check 6 — sign and bound sanity checks."""
    problems: list[str] = []
    if wacc <= growth:
        problems.append(f"WACC ({wacc:.4f}) <= g ({growth:.4f})")
    if growth < -inflation:
        problems.append(f"g ({growth:.4f}) < -inflation ({-inflation:.4f})")
    if nopat_t_plus_1 <= 0:
        problems.append(f"NOPAT_{{T+1}} ({nopat_t_plus_1:.2f}) <= 0: perpetuity senza senso")

    if problems:
        return CoherenceCheck(
            code="C6",
            name="Sign and bound checks",
            severity=Severity.ERROR,
            message="; ".join(problems),
            detail={
                "wacc": wacc,
                "growth": growth,
                "nopat_t_plus_1": nopat_t_plus_1,
                "inflation": inflation,
            },
        )
    return CoherenceCheck(
        code="C6",
        name="Sign and bound checks",
        severity=Severity.PASS,
        message="Tutti i vincoli di segno e bounds rispettati",
        detail={"wacc": wacc, "growth": growth, "nopat_t_plus_1": nopat_t_plus_1},
    )


# -----------------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------------


def check_coherence(
    *,
    wacc: float,
    growth: float,
    roic_new_investments: float,
    implied_reinvestment: float,
    tv_weight: float,
    roic_marginal_final: float,
    nopat_t_plus_1: float,
    gdp_nominal_5y_avg: float,
    used_coherent_formula: bool = False,
    inflation: float = 0.0,
) -> CoherenceReport:
    """Run all 6 coherence checks and return a consolidated report.

    Raise nothing — the caller inspects ``report.verdict``, ``errors()`` and
    ``warnings()`` to decide how to proceed.
    """
    checks = (
        check_g_below_gdp(growth, gdp_nominal_5y_avg),
        check_reinvestment_identity(growth, roic_new_investments, implied_reinvestment),
        check_tv_formula_used(used_coherent_formula, roic_new_investments, wacc),
        check_tv_weight(tv_weight),
        check_roic_convergence(roic_marginal_final, wacc),
        check_bounds(wacc, growth, nopat_t_plus_1, inflation),
        check_reinvestment_bounds(growth, roic_new_investments),
    )
    return CoherenceReport(checks=checks)
