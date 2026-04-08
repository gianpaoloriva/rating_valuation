"""Rating master scale mapper.

Converts between:
    Rating class  <->  PD (1 year)
    CDS spread    -->  PD
    Altman Z-score --> Rating --> PD

Master scale source: Montesi & Papiro (2014), Appendix A, "Master Scale"
table, which itself is derived from S&P cumulative average default rates
(1981-2010) with exponential interpolation for sparse classes.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, log

import pandas as pd

from rating_valuation.common.data_loader import load_rating_master_scale

# -----------------------------------------------------------------------------
# Default LGD used by the CDS -> PD conversion (Agentic Credit Risk uses recovery 40%)
# -----------------------------------------------------------------------------

DEFAULT_RECOVERY_RATE = 0.40
DEFAULT_LGD = 1.0 - DEFAULT_RECOVERY_RATE  # 0.60


# -----------------------------------------------------------------------------
# Altman Z-score -> Rating table
# -----------------------------------------------------------------------------
# Source: Altman & Hotchkiss (2006), "Corporate Financial Distress and Bankruptcy",
# 3rd ed., Wiley, p. 247 (Z-score, manufacturing) and p. 248 (Z'-score, non-mfg),
# as referenced in Montesi/Papiro (2014) Appendix A.
#
# The mapping below uses the Z-score buckets proposed by Altman for the
# "original" manufacturing model. For dei non manufacturing ci sarà una tabella
# analoga (Z'' model) — a cura di una futura estensione.

ALTMAN_Z_BUCKETS: tuple[tuple[float, str], ...] = (
    (8.15, "AAA"),
    (7.60, "AA+"),
    (7.30, "AA"),
    (7.00, "AA-"),
    (6.85, "A+"),
    (6.65, "A"),
    (6.40, "A-"),
    (6.25, "BBB+"),
    (5.85, "BBB"),
    (5.65, "BBB-"),
    (5.25, "BB+"),
    (4.95, "BB"),
    (4.75, "BB-"),
    (4.50, "B+"),
    (4.15, "B"),
    (3.75, "B-"),
    (3.20, "CCC+"),
    (2.50, "CCC"),
    (1.75, "CCC-"),
    (0.00, "D"),
)


@dataclass
class RatingLookup:
    """Mapping snapshot loaded from the master scale CSV."""

    rating_to_pd: dict[str, float]
    rating_to_ordinal: dict[str, int]
    ordinal_to_rating: dict[int, str]
    # sorted arrays for interpolation
    _ordinals: list[int]
    _pds: list[float]

    @classmethod
    def from_csv(cls, path: str | None = None) -> RatingLookup:
        df: pd.DataFrame = load_rating_master_scale(path)
        rating_to_pd = dict(zip(df["rating"], df["pd_1y"]))
        rating_to_ordinal = dict(zip(df["rating"], df["rating_ordinal"]))
        ordinal_to_rating = dict(zip(df["rating_ordinal"], df["rating"]))
        return cls(
            rating_to_pd=rating_to_pd,
            rating_to_ordinal=rating_to_ordinal,
            ordinal_to_rating=ordinal_to_rating,
            _ordinals=df["rating_ordinal"].tolist(),
            _pds=df["pd_1y"].tolist(),
        )

    # ------------------------------------------------------------------
    # Primary lookups
    # ------------------------------------------------------------------

    def pd_of(self, rating: str) -> float:
        """Return the 1-year PD for a rating class (e.g. 'BBB+')."""
        if rating not in self.rating_to_pd:
            raise KeyError(f"Unknown rating class: {rating!r}")
        return self.rating_to_pd[rating]

    def rating_of_pd(self, pd_1y: float) -> str:
        """Return the rating class whose PD is closest to (but not below) `pd_1y`.

        The rule is "smallest rating class with PD >= input PD" — i.e. the
        rating that a rating agency would assign given the observed risk.
        Out-of-range values are clipped to AAA / D.
        """
        if pd_1y <= 0.0:
            return self.ordinal_to_rating[min(self._ordinals)]
        if pd_1y >= 1.0:
            return self.ordinal_to_rating[max(self._ordinals)]

        # walk the ordered table and return the first rating with pd >= input
        for ordinal, pd_class in zip(self._ordinals, self._pds):
            if pd_class >= pd_1y:
                return self.ordinal_to_rating[ordinal]
        return self.ordinal_to_rating[max(self._ordinals)]

    def rating_of_pd_interpolated(self, pd_1y: float) -> tuple[str, str, float]:
        """Return the two bracketing rating classes and the fraction between them.

        Useful to express a PD as "between BBB and BBB-, closer to BBB-".
        The fraction is expressed in log-PD space (exponential interpolation,
        same convention as the master scale).

        Returns
        -------
        (lower_rating, upper_rating, fraction)
            lower_rating is the class with lower PD (better credit)
            upper_rating is the class with higher PD (worse credit)
            fraction is 0 at lower_rating, 1 at upper_rating
        """
        if pd_1y <= self._pds[0]:
            return (
                self.ordinal_to_rating[self._ordinals[0]],
                self.ordinal_to_rating[self._ordinals[0]],
                0.0,
            )
        if pd_1y >= self._pds[-1]:
            return (
                self.ordinal_to_rating[self._ordinals[-1]],
                self.ordinal_to_rating[self._ordinals[-1]],
                1.0,
            )

        for i in range(len(self._pds) - 1):
            lo, hi = self._pds[i], self._pds[i + 1]
            if lo <= pd_1y <= hi:
                if lo == 0.0 or hi == 0.0:
                    frac = 0.0
                else:
                    # log-linear interpolation
                    frac = (log(pd_1y) - log(max(lo, 1e-12))) / (
                        log(max(hi, 1e-12)) - log(max(lo, 1e-12))
                    )
                return (
                    self.ordinal_to_rating[self._ordinals[i]],
                    self.ordinal_to_rating[self._ordinals[i + 1]],
                    float(frac),
                )
        raise RuntimeError("Unreachable: PD bracketing failed")

    # ------------------------------------------------------------------
    # CDS conversions
    # ------------------------------------------------------------------

    @staticmethod
    def pd_from_cds(
        cds_spread: float,
        lgd: float = DEFAULT_LGD,
        maturity_years: float = 1.0,
    ) -> float:
        """Approximate PD from a CDS spread.

        Formula (Montesi/Papiro 2014 Appendix A): ``PD = 1 − exp(−(CDS / LGD) · T)``
        with LGD=0.6 by default.

        Parameters
        ----------
        cds_spread : float
            Spread as a decimal (e.g. 0.012 for 120 bps).
        lgd : float
            Loss given default (default: 0.60 = 1 - 40% recovery).
        maturity_years : float
            Maturity of the CDS contract (default 1y).

        Returns
        -------
        float
            1-year probability of default.
        """
        if cds_spread < 0 or lgd <= 0 or lgd > 1 or maturity_years <= 0:
            raise ValueError(
                f"Invalid CDS/LGD/maturity: {cds_spread=}, {lgd=}, {maturity_years=}"
            )
        return 1.0 - exp(-(cds_spread / lgd) * maturity_years)

    def rating_from_cds(
        self,
        cds_spread: float,
        lgd: float = DEFAULT_LGD,
        maturity_years: float = 1.0,
    ) -> str:
        return self.rating_of_pd(self.pd_from_cds(cds_spread, lgd, maturity_years))

    # ------------------------------------------------------------------
    # Altman Z-score conversions
    # ------------------------------------------------------------------

    @staticmethod
    def rating_from_z_score(z_score: float) -> str:
        """Map an Altman Z-score to a rating class (manufacturing model).

        Buckets from Altman & Hotchkiss (2006), p. 247.
        """
        for threshold, rating in ALTMAN_Z_BUCKETS:
            if z_score >= threshold:
                return rating
        return "D"

    def pd_from_z_score(self, z_score: float) -> float:
        return self.pd_of(self.rating_from_z_score(z_score))


# -----------------------------------------------------------------------------
# Altman Z-score formulas (original 1968 manufacturing model)
# -----------------------------------------------------------------------------


def altman_z_score_manufacturing(
    working_capital: float,
    retained_earnings: float,
    ebit: float,
    market_value_equity: float,
    sales: float,
    total_assets: float,
    total_liabilities: float,
) -> float:
    """Altman (1968) Z-score for manufacturing listed companies.

    ``Z = 1.2·WC/TA + 1.4·RE/TA + 3.3·EBIT/TA + 0.6·MV(E)/BV(L) + 1.0·Sales/TA``

    Zones: Z > 2.99 safe, 1.81 < Z < 2.99 grey, Z < 1.81 distress.
    """
    if total_assets <= 0 or total_liabilities <= 0:
        raise ValueError("Total assets and total liabilities must be positive")
    return (
        1.2 * working_capital / total_assets
        + 1.4 * retained_earnings / total_assets
        + 3.3 * ebit / total_assets
        + 0.6 * market_value_equity / total_liabilities
        + 1.0 * sales / total_assets
    )


def altman_z_double_prime_non_manufacturing(
    working_capital: float,
    retained_earnings: float,
    ebit: float,
    book_value_equity: float,
    total_assets: float,
    total_liabilities: float,
) -> float:
    """Altman Z''-score (1995 revision) for non-manufacturing / private firms.

    ``Z'' = 3.25 + 6.56·WC/TA + 3.26·RE/TA + 6.72·EBIT/TA + 1.05·BV(E)/TL``

    Does not use the sales-to-assets term (which differs too much across
    industries) and replaces market value of equity with book value.
    """
    if total_assets <= 0 or total_liabilities <= 0:
        raise ValueError("Total assets and total liabilities must be positive")
    return (
        3.25
        + 6.56 * working_capital / total_assets
        + 3.26 * retained_earnings / total_assets
        + 6.72 * ebit / total_assets
        + 1.05 * book_value_equity / total_liabilities
    )
