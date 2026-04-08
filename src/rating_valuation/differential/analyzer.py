"""Differential analyzer: target company vs Impresa Media Standard (IMS).

Given a BMS built from a peer sample and a target company row, this module
quantifies and attributes the difference on the main value drivers used by
the DCF:

    - Margine operativo (EBITDA, EBIT, NOPAT margin)
    - Intensità di capitale (NIC / Fatturato, NFA / Fatturato, NWC / Fatturato)
    - Struttura finanziaria (Debito / Attivo, Leverage, Cash / Fatturato)
    - Crescita (CAGR del fatturato se si dispone di più anni)
    - Efficienza del capitale (ROIC = NOPAT / NIC)

Reference: Scarano/Brughera, AIAF n. 65, 2008 — "Conclusioni finali" sulla
valutazione differenziale rispetto all'Impresa Media Standard.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from rating_valuation.bms.builder import BMSResult


# -----------------------------------------------------------------------------
# Indicators definition
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """Defines how a single KPI is computed from a company row and a BMS."""

    key: str
    label: str
    category: str                # 'margin', 'capital_intensity', 'leverage', 'efficiency', 'scale'
    unit: str                    # 'pct', 'ratio', 'money'
    numerator: str               # column in companies.csv
    denominator: str | None      # column; None means raw numerator
    bms_statement: str           # 'income_statement' | 'balance_sheet' | 'derived'
    higher_is_better: bool       # True means target > BMS is good

    def compute_from_row(self, row: pd.Series) -> float:
        num = float(row[self.numerator])
        if self.denominator is None:
            return num
        den = float(row[self.denominator])
        if den == 0:
            return float("nan")
        return num / den

    def compute_from_bms(self, bms: BMSResult) -> float:
        if self.bms_statement == "derived":
            return self._compute_derived_from_bms(bms)

        if self.bms_statement == "income_statement":
            num = float(bms.income_statement[self.numerator])
            if self.denominator is None:
                return num
            # Denominator is always "revenues" or "total_assets" at BMS level
            if self.denominator == "revenues":
                return num / bms.average_revenues
            if self.denominator == "total_assets":
                return num / bms.average_total_assets
            # Ratio within income statement
            den = float(bms.income_statement[self.denominator])
            return num / den if den != 0 else float("nan")

        # balance_sheet
        num = float(bms.balance_sheet[self.numerator])
        if self.denominator is None:
            return num
        if self.denominator == "revenues":
            return num / bms.average_revenues
        if self.denominator == "total_assets":
            return num / bms.average_total_assets
        den = float(bms.balance_sheet[self.denominator])
        return num / den if den != 0 else float("nan")

    def _compute_derived_from_bms(self, bms: BMSResult) -> float:
        if self.key == "roic":
            nopat = float(bms.income_statement["nopat"])
            nic = float(bms.balance_sheet["net_invested_capital"])
            return nopat / nic if nic else float("nan")
        if self.key == "nic_to_revenues":
            nic = float(bms.balance_sheet["net_invested_capital"])
            return nic / bms.average_revenues
        if self.key == "debt_to_equity":
            gd = float(bms.balance_sheet["gross_debt"])
            eq = float(bms.balance_sheet["equity"])
            return gd / eq if eq else float("nan")
        raise KeyError(f"Unknown derived indicator: {self.key}")


# -----------------------------------------------------------------------------
# Default catalog of indicators used by the analyzer
# -----------------------------------------------------------------------------


DEFAULT_INDICATORS: tuple[IndicatorSpec, ...] = (
    # Scale
    IndicatorSpec(
        "revenues", "Fatturato", "scale", "money",
        numerator="revenues", denominator=None,
        bms_statement="income_statement", higher_is_better=True,
    ),
    IndicatorSpec(
        "total_assets", "Totale attivo", "scale", "money",
        numerator="total_assets", denominator=None,
        bms_statement="balance_sheet", higher_is_better=True,
    ),
    # Margins
    IndicatorSpec(
        "ebitda_margin", "EBITDA margin", "margin", "pct",
        numerator="ebitda", denominator="revenues",
        bms_statement="income_statement", higher_is_better=True,
    ),
    IndicatorSpec(
        "ebit_margin", "EBIT margin", "margin", "pct",
        numerator="ebit", denominator="revenues",
        bms_statement="income_statement", higher_is_better=True,
    ),
    IndicatorSpec(
        "nopat_margin", "NOPAT margin", "margin", "pct",
        numerator="nopat", denominator="revenues",
        bms_statement="income_statement", higher_is_better=True,
    ),
    # Capital intensity
    IndicatorSpec(
        "nfa_to_revenues", "NFA / Fatturato", "capital_intensity", "pct",
        numerator="net_fixed_assets", denominator="revenues",
        bms_statement="balance_sheet", higher_is_better=False,
    ),
    IndicatorSpec(
        "nwc_to_revenues", "NWC / Fatturato", "capital_intensity", "pct",
        numerator="net_working_capital", denominator="revenues",
        bms_statement="balance_sheet", higher_is_better=False,
    ),
    IndicatorSpec(
        "nic_to_revenues", "NIC / Fatturato", "capital_intensity", "pct",
        numerator="",  # derived
        denominator=None,
        bms_statement="derived", higher_is_better=False,
    ),
    # Leverage
    IndicatorSpec(
        "debt_to_ta", "Debito lordo / Attivo", "leverage", "pct",
        numerator="gross_debt", denominator="total_assets",
        bms_statement="balance_sheet", higher_is_better=False,
    ),
    IndicatorSpec(
        "equity_to_ta", "Equity / Attivo", "leverage", "pct",
        numerator="equity", denominator="total_assets",
        bms_statement="balance_sheet", higher_is_better=True,
    ),
    IndicatorSpec(
        "debt_to_equity", "Debito / Equity", "leverage", "ratio",
        numerator="",  # derived
        denominator=None,
        bms_statement="derived", higher_is_better=False,
    ),
    # Efficiency
    IndicatorSpec(
        "roic", "ROIC = NOPAT / NIC", "efficiency", "pct",
        numerator="",  # derived
        denominator=None,
        bms_statement="derived", higher_is_better=True,
    ),
)


# Map derived indicators to their row-level computation
def _row_derived(row: pd.Series, key: str) -> float:
    if key == "roic":
        nopat = float(row["nopat"])
        nic = float(row["net_invested_capital"])
        return nopat / nic if nic else float("nan")
    if key == "nic_to_revenues":
        nic = float(row["net_invested_capital"])
        rev = float(row["revenues"])
        return nic / rev if rev else float("nan")
    if key == "debt_to_equity":
        gd = float(row["gross_debt"])
        eq = float(row["equity"])
        return gd / eq if eq else float("nan")
    raise KeyError(f"Unknown derived indicator: {key}")


# -----------------------------------------------------------------------------
# Result container
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorComparison:
    key: str
    label: str
    category: str
    unit: str
    target: float
    bms: float
    delta: float                      # target - bms
    delta_pct: float                  # (target - bms) / bms  (when bms != 0)
    favorable: bool                   # True if delta sign aligns with higher_is_better

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "category": self.category,
            "unit": self.unit,
            "target": self.target,
            "bms": self.bms,
            "delta": self.delta,
            "delta_pct": self.delta_pct,
            "favorable": self.favorable,
        }


@dataclass(frozen=True)
class DifferentialReport:
    target_id: str
    target_name: str
    fiscal_year: int
    bms_fiscal_year: int
    n_peers: int
    comparisons: tuple[IndicatorComparison, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def as_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([c.as_dict() for c in self.comparisons])

    def by_category(self) -> dict[str, tuple[IndicatorComparison, ...]]:
        buckets: dict[str, list[IndicatorComparison]] = {}
        for c in self.comparisons:
            buckets.setdefault(c.category, []).append(c)
        return {k: tuple(v) for k, v in buckets.items()}

    def favorable_count(self) -> int:
        return sum(1 for c in self.comparisons if c.favorable)

    def unfavorable_count(self) -> int:
        return sum(1 for c in self.comparisons if not c.favorable)

    def summary_line(self) -> str:
        tot = len(self.comparisons)
        fav = self.favorable_count()
        return (
            f"{self.target_name} (FY{self.fiscal_year}) — "
            f"{fav}/{tot} indicatori favorevoli rispetto al BMS "
            f"{self.bms_fiscal_year} ({self.n_peers} peer)"
        )


# -----------------------------------------------------------------------------
# Analyzer
# -----------------------------------------------------------------------------


class DifferentialAnalyzer:
    """Compare a target company row against a BMS and produce a structured report."""

    def __init__(
        self,
        bms: BMSResult,
        indicators: tuple[IndicatorSpec, ...] = DEFAULT_INDICATORS,
    ) -> None:
        self.bms = bms
        self.indicators = indicators

    def analyze(self, target_row: pd.Series) -> DifferentialReport:
        comps: list[IndicatorComparison] = []
        for spec in self.indicators:
            if spec.bms_statement == "derived":
                target_val = _row_derived(target_row, spec.key)
            else:
                target_val = spec.compute_from_row(target_row)

            bms_val = spec.compute_from_bms(self.bms)

            delta = target_val - bms_val
            delta_pct = delta / bms_val if bms_val not in (0, float("nan")) else float("nan")
            favorable = (delta > 0) == spec.higher_is_better

            comps.append(
                IndicatorComparison(
                    key=spec.key,
                    label=spec.label,
                    category=spec.category,
                    unit=spec.unit,
                    target=target_val,
                    bms=bms_val,
                    delta=delta,
                    delta_pct=delta_pct,
                    favorable=favorable,
                )
            )

        return DifferentialReport(
            target_id=str(target_row["company_id"]),
            target_name=str(target_row["company_name"]),
            fiscal_year=int(target_row["fiscal_year"]),
            bms_fiscal_year=self.bms.fiscal_year,
            n_peers=self.bms.n_companies,
            comparisons=tuple(comps),
        )
