"""Credit risk models back-test comparator.

Given a set of companies split into "defaulted" and "performing" groups,
this module runs multiple credit risk models on each subject and compares
their discriminatory power using standard metrics:

    - Gini coefficient (= 2·AUROC - 1)
    - AUROC (Area Under the ROC Curve)
    - Kolmogorov-Smirnov statistic

Supported models (V1):
    * Agentic Credit Risk — forward-looking stochastic simulation
    * Altman Z''          — accounting ratios (non-manufacturing formulation,
                              applicable to Italian private PMI)

The comparator works even with the fake dataset (where we do not have
real defaults); in that case the caller can pass an empty defaulted
sample and use it only as a "performing stress test" to see PD dispersion
across the sample.

Reference: Montesi/Papiro (2014), Section 5.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from rating_valuation.agentic_credit_risk.simulator import AgenticCreditRiskSimulator
from rating_valuation.rating.mapper import (
    RatingLookup,
    altman_z_double_prime_non_manufacturing,
)


# -----------------------------------------------------------------------------
# Metrics
# -----------------------------------------------------------------------------


def auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Area Under the ROC Curve.

    ``scores`` should be higher for riskier subjects. ``labels`` is 1 for
    defaulters and 0 for performers. AUROC = 1 means perfect discrimination,
    0.5 is random.
    """
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if scores.shape != labels.shape:
        raise ValueError("scores and labels must share the same shape")

    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")

    # Mann-Whitney U / (n_pos * n_neg)
    all_scores = np.concatenate([pos, neg])
    all_labels = np.concatenate([np.ones_like(pos), np.zeros_like(neg)])
    order = np.argsort(all_scores, kind="mergesort")
    ranked_labels = all_labels[order]
    ranks = np.arange(1, len(ranked_labels) + 1, dtype=float)
    # Handle ties (average rank)
    unique_scores, inverse = np.unique(all_scores[order], return_inverse=True)
    if len(unique_scores) < len(all_scores):
        sums = np.zeros(len(unique_scores))
        counts = np.zeros(len(unique_scores))
        np.add.at(sums, inverse, ranks)
        np.add.at(counts, inverse, 1)
        mean_ranks = sums / counts
        adjusted = mean_ranks[inverse]
    else:
        adjusted = ranks

    pos_rank_sum = adjusted[ranked_labels == 1].sum()
    n_pos = len(pos)
    n_neg = len(neg)
    u = pos_rank_sum - n_pos * (n_pos + 1) / 2.0
    return float(u / (n_pos * n_neg))


def gini_coefficient(scores: np.ndarray, labels: np.ndarray) -> float:
    """Gini = 2 · AUROC - 1."""
    a = auroc(scores, labels)
    if np.isnan(a):
        return float("nan")
    return 2.0 * a - 1.0


def kolmogorov_smirnov(scores: np.ndarray, labels: np.ndarray) -> float:
    """KS statistic: max distance between the two cumulative distributions."""
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    pos = np.sort(scores[labels == 1])
    neg = np.sort(scores[labels == 0])
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")

    grid = np.concatenate([pos, neg])
    grid.sort()
    cdf_pos = np.searchsorted(pos, grid, side="right") / len(pos)
    cdf_neg = np.searchsorted(neg, grid, side="right") / len(neg)
    return float(np.max(np.abs(cdf_pos - cdf_neg)))


# -----------------------------------------------------------------------------
# Result containers
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestRow:
    company_id: str
    company_name: str
    fiscal_year: int
    is_defaulted: int
    acr_pd: float
    acr_rating: str
    altman_z: float
    altman_rating: str
    altman_pd: float

    def as_dict(self) -> dict:
        return {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "fiscal_year": self.fiscal_year,
            "is_defaulted": self.is_defaulted,
            "acr_pd": self.acr_pd,
            "acr_rating": self.acr_rating,
            "altman_z": self.altman_z,
            "altman_rating": self.altman_rating,
            "altman_pd": self.altman_pd,
        }


@dataclass
class BacktestResult:
    rows: list[BacktestRow] = field(default_factory=list)
    n_trials: int = 0
    n_years: int = 0
    seed: int | None = None
    # Companies that could not be simulated (e.g. negative expected EBITDA
    # margin): list of {company_id, company_name, fiscal_year, reason}.
    skipped: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------------

    def as_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([r.as_dict() for r in self.rows])

    def metrics_table(self) -> pd.DataFrame:
        """Compute discriminatory metrics for each model.

        Requires at least one defaulted and one performing subject; otherwise
        returns NaNs (still useful to inspect PD dispersion).
        """
        df = self.as_dataframe()
        labels = df["is_defaulted"].to_numpy()

        models = {
            "Agentic Credit Risk": df["acr_pd"].to_numpy(),
            "Altman Z''": df["altman_pd"].to_numpy(),
        }

        rows = []
        for name, scores in models.items():
            rows.append(
                {
                    "model": name,
                    "auroc": auroc(scores, labels),
                    "gini": gini_coefficient(scores, labels),
                    "ks": kolmogorov_smirnov(scores, labels),
                    "mean_pd_defaulted": float(
                        scores[labels == 1].mean() if (labels == 1).any() else float("nan")
                    ),
                    "mean_pd_performing": float(
                        scores[labels == 0].mean() if (labels == 0).any() else float("nan")
                    ),
                    "median_pd_defaulted": float(
                        np.median(scores[labels == 1]) if (labels == 1).any() else float("nan")
                    ),
                    "median_pd_performing": float(
                        np.median(scores[labels == 0]) if (labels == 0).any() else float("nan")
                    ),
                }
            )
        return pd.DataFrame(rows)

    def skipped_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.skipped)

    def summary(self) -> str:
        df = self.as_dataframe()
        n_def = int(df["is_defaulted"].sum())
        n_perf = int((df["is_defaulted"] == 0).sum())
        base = (
            f"Backtest: {len(df)} companies ({n_def} defaulted, {n_perf} performing), "
            f"{self.n_trials} trials × {self.n_years}y horizon"
        )
        if self.skipped:
            base += f" — {len(self.skipped)} skipped (not simulatable)"
        return base


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------


class BacktestRunner:
    """Run Agentic Credit Risk + Altman on a sample and produce comparisons.

    Parameters
    ----------
    sectors, macro, rating_master_scale :
        Reference tables from :func:`rating_valuation.common.data_loader.load_all`.
    n_trials, n_years :
        Agentic Credit Risk simulation parameters. Default: 5 000 × 3 years
        (lighter than the paper's 20 000 for faster backtests).
    acr_kwargs :
        Extra keyword arguments forwarded to ``AgenticCreditRiskSimulator.from_company``.
    """

    def __init__(
        self,
        sectors: pd.DataFrame,
        macro: pd.DataFrame,
        rating_master_scale: pd.DataFrame | None = None,
        *,
        n_trials: int = 5_000,
        n_years: int = 3,
        acr_kwargs: dict | None = None,
    ) -> None:
        self.sectors = sectors
        self.macro = macro
        self.n_trials = n_trials
        self.n_years = n_years
        self.acr_kwargs = acr_kwargs or {}
        self.lookup = (
            RatingLookup(
                rating_to_pd=dict(zip(rating_master_scale["rating"], rating_master_scale["pd_1y"])),
                rating_to_ordinal=dict(zip(rating_master_scale["rating"], rating_master_scale["rating_ordinal"])),
                ordinal_to_rating=dict(zip(rating_master_scale["rating_ordinal"], rating_master_scale["rating"])),
                _ordinals=rating_master_scale["rating_ordinal"].tolist(),
                _pds=rating_master_scale["pd_1y"].tolist(),
            )
            if rating_master_scale is not None
            else RatingLookup.from_csv()
        )

    # ------------------------------------------------------------------

    def run(
        self,
        companies: pd.DataFrame,
        *,
        defaulted_ids: set[str] | None = None,
        seed: int | None = 42,
    ) -> BacktestResult:
        """Run both models on every row in ``companies`` and collect results.

        Parameters
        ----------
        companies : pd.DataFrame
            Rows from a curated sample (one row per company-year you want
            to score). No invariant check is performed here — run the
            data-curator first.
        defaulted_ids : set[str] | None
            Set of ``company_id`` values to label as defaulted (label = 1).
            Others are treated as performing (label = 0). Pass ``None`` or
            an empty set if the backtest only inspects PD dispersion.
        seed : int | None
            Base seed for the Monte Carlo. Each company uses ``seed + i``
            to keep results reproducible yet decorrelated between companies.
        """
        defaulted_ids = defaulted_ids or set()
        rows: list[BacktestRow] = []
        skipped: list[dict] = []

        for i, (_, company) in enumerate(companies.iterrows()):
            # --- Agentic Credit Risk ------------------------------------
            # Companies whose distributions cannot be calibrated (typically
            # a negative expected EBITDA margin) are skipped and logged
            # instead of aborting the whole backtest.
            try:
                sim = AgenticCreditRiskSimulator.from_company(
                    company,
                    self.sectors,
                    self.macro,
                    n_trials=self.n_trials,
                    n_years=self.n_years,
                    **self.acr_kwargs,
                )
            except ValueError as exc:
                skipped.append(
                    {
                        "company_id": str(company["company_id"]),
                        "company_name": str(company["company_name"]),
                        "fiscal_year": int(company["fiscal_year"]),
                        "reason": str(exc),
                    }
                )
                continue
            acr_result = sim.run(seed=(seed + i) if seed is not None else None)
            acr_pd = float(acr_result.metrics.cumulative_pd[-1])
            acr_rating = acr_result.implied_rating or "N/A"

            # --- Altman Z'' (non-manufacturing) -------------------------
            working_capital = float(company["net_working_capital"])
            # Retained earnings proxy: equity - paid-in capital. For the
            # reclassified schema we don't separate them, so we use equity
            # as an upper bound. In real data the caller should pass the
            # correct value.
            retained_earnings = float(company["equity"])
            ebit = float(company["ebit"])
            book_value_equity = float(company["equity"])
            total_assets = float(company["total_assets"])
            total_liabilities = (
                float(company["gross_debt"])
                + max(0.0, total_assets - float(company["equity"]) - float(company["gross_debt"]))
            )

            try:
                z = altman_z_double_prime_non_manufacturing(
                    working_capital=working_capital,
                    retained_earnings=retained_earnings,
                    ebit=ebit,
                    book_value_equity=book_value_equity,
                    total_assets=total_assets,
                    total_liabilities=max(total_liabilities, 1.0),
                )
                altman_rating = RatingLookup.rating_from_z_score(z)
                altman_pd = self.lookup.pd_of(altman_rating)
            except ValueError:
                z = float("nan")
                altman_rating = "N/A"
                altman_pd = float("nan")

            rows.append(
                BacktestRow(
                    company_id=str(company["company_id"]),
                    company_name=str(company["company_name"]),
                    fiscal_year=int(company["fiscal_year"]),
                    is_defaulted=1 if str(company["company_id"]) in defaulted_ids else 0,
                    acr_pd=acr_pd,
                    acr_rating=acr_rating,
                    altman_z=float(z) if z == z else float("nan"),
                    altman_rating=altman_rating,
                    altman_pd=float(altman_pd),
                )
            )

        return BacktestResult(
            rows=rows,
            n_trials=self.n_trials,
            n_years=self.n_years,
            seed=seed,
            skipped=skipped,
        )
