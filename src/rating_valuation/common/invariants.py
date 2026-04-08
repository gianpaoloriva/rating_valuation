"""Balance sheet / P&L invariant checks for the reclassified statements.

These are the same invariants enforced by the fake data generator and expected
by all downstream tools. Any violation in real data should be flagged before
running BMS, DCF or RAPD.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

DEFAULT_TOLERANCE = 0.01  # absolute tolerance in the CSV's monetary unit


@dataclass(frozen=True)
class InvariantViolation:
    company_id: str
    fiscal_year: int
    rule: str
    lhs: float
    rhs: float
    diff: float

    def as_dict(self) -> dict:
        return {
            "company_id": self.company_id,
            "fiscal_year": self.fiscal_year,
            "rule": self.rule,
            "lhs": self.lhs,
            "rhs": self.rhs,
            "diff": self.diff,
        }


def _row_checks(row: pd.Series, tolerance: float) -> list[InvariantViolation]:
    violations: list[InvariantViolation] = []

    def check(rule: str, lhs: float, rhs: float) -> None:
        diff = lhs - rhs
        if abs(diff) > tolerance:
            violations.append(
                InvariantViolation(
                    company_id=str(row["company_id"]),
                    fiscal_year=int(row["fiscal_year"]),
                    rule=rule,
                    lhs=float(lhs),
                    rhs=float(rhs),
                    diff=float(diff),
                )
            )

    check("ebitda == revenues - operating_costs",
          row["ebitda"], row["revenues"] - row["operating_costs"])
    check("ebit == ebitda - depreciation_amortization",
          row["ebit"], row["ebitda"] - row["depreciation_amortization"])
    check("nic == nfa + nwc",
          row["net_invested_capital"],
          row["net_fixed_assets"] + row["net_working_capital"])
    check("net_debt == gross_debt - cash",
          row["net_debt"], row["gross_debt"] - row["cash"])
    check("equity == nic - net_debt",
          row["equity"],
          row["net_invested_capital"] - row["net_debt"])

    return violations


def check_invariants(
    companies: pd.DataFrame,
    tolerance: float = DEFAULT_TOLERANCE,
) -> list[InvariantViolation]:
    """Run all invariant checks and return the list of violations (empty = OK)."""
    violations: list[InvariantViolation] = []
    for _, row in companies.iterrows():
        violations.extend(_row_checks(row, tolerance))
    return violations


def assert_invariants(
    companies: pd.DataFrame,
    tolerance: float = DEFAULT_TOLERANCE,
) -> None:
    """Raise AssertionError if any invariant is violated."""
    violations = check_invariants(companies, tolerance)
    if violations:
        lines = [
            f"- {v.company_id}/{v.fiscal_year}: {v.rule} "
            f"(lhs={v.lhs:.3f}, rhs={v.rhs:.3f}, diff={v.diff:.3f})"
            for v in violations[:10]
        ]
        extra = "" if len(violations) <= 10 else f"\n... and {len(violations) - 10} more"
        raise AssertionError(
            "Balance sheet invariants violated:\n" + "\n".join(lines) + extra
        )
