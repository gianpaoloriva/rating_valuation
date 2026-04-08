"""Stochastic sampling for RAPD — Weibull marginals + Gaussian copula.

Implements the sampling approach described in the Montesi/Papiro paper
(Appendix A). For each of the four stochastic variables

    revenue growth g_t
    EBITDA margin  m_t     (called "operating costs (EBITDA margin)" in the paper)
    NFA / Revenues f_t
    NWC / Revenues w_t

we use a Weibull distribution with a sector-specific shape parameter and
a location/scale calibrated to the target mean and minimum for that
variable. Correlations are imposed via a Gaussian copula, using a
multivariate normal sample whose covariance matrix encodes both the
same-year cross correlations and the year-over-year autocorrelations.

Reference: Montesi G., Papiro G. (2014), "Risk Analysis Probability of
Default: A Stochastic Simulation Model", Appendix A.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import gamma as gamma_fn
from scipy.stats import norm, weibull_min

# -----------------------------------------------------------------------------
# Variable ordering constants
# -----------------------------------------------------------------------------

VAR_NAMES: tuple[str, ...] = ("growth", "ebitda_margin", "nfa_ratio", "nwc_ratio")
N_VARS: int = len(VAR_NAMES)


# -----------------------------------------------------------------------------
# Weibull distribution helpers
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class WeibullParams:
    """Weibull (shape, loc, scale) with a mean/min calibration constructor."""

    shape: float
    loc: float
    scale: float

    @classmethod
    def from_mean_min(cls, mean: float, minimum: float, shape: float) -> WeibullParams:
        """Calibrate (loc, scale) given target mean, minimum, and shape.

        ``loc = minimum`` and ``scale = (mean - minimum) / Γ(1 + 1/shape)``.
        """
        if shape <= 0:
            raise ValueError(f"Weibull shape must be positive, got {shape}")
        if mean <= minimum:
            raise ValueError(
                f"Mean ({mean}) must be strictly greater than minimum ({minimum})"
            )
        loc = minimum
        scale = (mean - loc) / gamma_fn(1.0 + 1.0 / shape)
        return cls(shape=float(shape), loc=float(loc), scale=float(scale))

    @property
    def mean(self) -> float:
        return self.loc + self.scale * gamma_fn(1.0 + 1.0 / self.shape)

    def ppf(self, q: np.ndarray) -> np.ndarray:
        """Inverse CDF (quantile function)."""
        return weibull_min.ppf(q, self.shape, loc=self.loc, scale=self.scale)


# -----------------------------------------------------------------------------
# Stochastic parameter container
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class StochasticParameters:
    """All inputs needed to generate multi-year correlated scenarios."""

    growth: WeibullParams
    ebitda_margin: WeibullParams
    nfa_ratio: WeibullParams
    nwc_ratio: WeibullParams

    # Autocorrelations (lag 1, AR(1) in latent space)
    autocorr_growth: float
    autocorr_margin: float
    autocorr_nfa: float
    autocorr_nwc: float

    # Cross correlations (same year)
    corr_growth_margin: float      # Sales × OpCost/Sales sign flipped → becomes Sales × EBITDA margin
    corr_nfa_margin: float         # NFA/Sales × OpCost/Sales → flipped sign for EBITDA margin
    corr_growth_nfa: float
    corr_growth_nwc: float

    def as_dict(self) -> dict:
        return {
            "growth": self.growth.__dict__,
            "ebitda_margin": self.ebitda_margin.__dict__,
            "nfa_ratio": self.nfa_ratio.__dict__,
            "nwc_ratio": self.nwc_ratio.__dict__,
            "autocorr_growth": self.autocorr_growth,
            "autocorr_margin": self.autocorr_margin,
            "autocorr_nfa": self.autocorr_nfa,
            "autocorr_nwc": self.autocorr_nwc,
            "corr_growth_margin": self.corr_growth_margin,
            "corr_nfa_margin": self.corr_nfa_margin,
            "corr_growth_nfa": self.corr_growth_nfa,
            "corr_growth_nwc": self.corr_growth_nwc,
        }


# -----------------------------------------------------------------------------
# Covariance matrix assembly
# -----------------------------------------------------------------------------


def _same_year_correlation_block(params: StochasticParameters) -> np.ndarray:
    """4×4 correlation matrix for (growth, margin, nfa_ratio, nwc_ratio) same year.

    Sign convention note: the paper reports correlations against "OpCost/Sales".
    EBITDA margin = 1 − OpCost/Sales, so the correlation flips sign. The
    paper's value `corr_sales_opcosts = -0.4` (negative) maps to
    `corr_growth_margin = +0.4` (positive). The factory `from_sector_defaults`
    handles this conversion.
    """
    m = np.eye(N_VARS)
    m[0, 1] = m[1, 0] = params.corr_growth_margin
    m[2, 1] = m[1, 2] = params.corr_nfa_margin
    m[0, 2] = m[2, 0] = params.corr_growth_nfa
    m[0, 3] = m[3, 0] = params.corr_growth_nwc
    return m


def build_covariance_matrix(
    params: StochasticParameters,
    n_years: int,
) -> np.ndarray:
    """Build the full (4·n_years) × (4·n_years) correlation matrix.

    Variable ordering: [g_1, m_1, f_1, w_1, g_2, m_2, f_2, w_2, ...].

    Block structure:
        - Diagonal blocks (same year):   ``_same_year_correlation_block``
        - Off-diagonal blocks (lag k):   diagonal matrix with AR(1)^k per variable,
                                          zeros on the off-diagonal entries
    """
    if n_years < 1:
        raise ValueError("n_years must be >= 1")

    size = N_VARS * n_years
    cov = np.zeros((size, size))
    same_year = _same_year_correlation_block(params)

    autocorrs = np.array(
        [params.autocorr_growth, params.autocorr_margin,
         params.autocorr_nfa, params.autocorr_nwc]
    )

    for y1 in range(n_years):
        for y2 in range(n_years):
            lag = abs(y1 - y2)
            if lag == 0:
                block = same_year
            else:
                block = np.diag(autocorrs ** lag)
            cov[
                y1 * N_VARS : (y1 + 1) * N_VARS,
                y2 * N_VARS : (y2 + 1) * N_VARS,
            ] = block

    return cov


def _ensure_positive_definite(cov: np.ndarray) -> np.ndarray:
    """If the matrix is not PD, clip negative eigenvalues to a small positive."""
    try:
        np.linalg.cholesky(cov)
        return cov
    except np.linalg.LinAlgError:
        eigvals, eigvecs = np.linalg.eigh(cov)
        eigvals = np.maximum(eigvals, 1e-8)
        return eigvecs @ np.diag(eigvals) @ eigvecs.T


# -----------------------------------------------------------------------------
# Scenario sampler
# -----------------------------------------------------------------------------


def sample_scenarios(
    params: StochasticParameters,
    n_trials: int,
    n_years: int,
    seed: int | None = None,
) -> np.ndarray:
    """Sample ``n_trials`` correlated multi-year scenarios.

    Returns
    -------
    np.ndarray
        Shape ``(n_trials, n_years, 4)``. Last axis order: growth, ebitda_margin,
        nfa_ratio, nwc_ratio.
    """
    rng = np.random.default_rng(seed)
    cov = _ensure_positive_definite(build_covariance_matrix(params, n_years))
    L = np.linalg.cholesky(cov)
    size = N_VARS * n_years

    # Latent standard normal → correlated normal via Cholesky
    z_indep = rng.standard_normal((n_trials, size))
    z_corr = z_indep @ L.T
    u = norm.cdf(z_corr)

    # Apply inverse Weibull CDF per variable
    distributions = [params.growth, params.ebitda_margin, params.nfa_ratio, params.nwc_ratio]
    out = np.zeros_like(u)
    for year in range(n_years):
        for var in range(N_VARS):
            col = year * N_VARS + var
            out[:, col] = distributions[var].ppf(u[:, col])

    return out.reshape(n_trials, n_years, N_VARS)
