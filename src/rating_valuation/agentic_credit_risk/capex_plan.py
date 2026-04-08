"""Explicit Capex / Depreciation schedule — paper RAPD footnote 8, eq. [I]-[VI].

The reduced V1 model in `simulator.py` treats NFA as ``f_t · REV_t`` (a
pure ratio to revenues) and D&A as ``da_ratio · REV_t``. This captures
the first-order effect but misses the vintage structure of the fixed
asset base: new Capex lives its useful life and generates D&A for
``useful_life`` years before being fully amortized and retired.

The helpers below implement the paper's equations [I]-[VI] so that an
analyst who wants the fuller Appendix A treatment can plug them into
the simulation without rewriting the core loop. They are exposed as
pure functions that operate on numpy arrays at the single-period level
and on a :class:`CapexPlan` container for the multi-period stock.

Equations (paper footnote 8, restated with our symbols):

    [I]   GFA_t    = GFA_{t-1} + CAPEX_t − RETIRED_t
    [II]  NFA_t    = NFA_{t-1} + CAPEX_t − DA_t − RETIRED_t·residual
    [III] DA_t     = Σ_{v} CAPEX_{t-v} / L    for v in [1, L]
    [IV]  RETIRED_t= CAPEX_{t-L}
    [V]   TargetNFA_t = f_t · REV_t
    [VI]  CAPEX_t = (TargetNFA_t − NFA_{t-1}) + DA_t
                    (implied Capex to hit the NFA target, replacing depreciation)

The simulator does NOT yet use this module by default (``simulator.py`` is
still the "reduced model" of Section 2 of the paper); the module is
provided so that a dedicated Appendix-A runner can be built on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CapexPlan:
    """Per-trial rolling buffer of Capex vintages for D&A and retirements.

    Maintains the last ``useful_life`` Capex cohorts per trial, with each
    cohort providing 1/L depreciation per year and being retired at the
    end of its useful life.
    """

    useful_life: int
    # cohorts[trial, age] = Capex vintage still on the balance sheet.
    # Axis 1 length == useful_life.
    cohorts: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))

    @classmethod
    def initialize(
        cls,
        n_trials: int,
        useful_life: int,
        opening_nfa: np.ndarray,
    ) -> CapexPlan:
        """Seed the plan with a flat cohort distribution that matches NFA_0.

        Each of the ``useful_life`` cohorts is set to ``NFA_0 / useful_life``
        so that the first-period D&A equals ``NFA_0 / useful_life``. Fully
        deterministic initialization — no opening noise.
        """
        if useful_life < 1:
            raise ValueError(f"useful_life must be >= 1, got {useful_life}")
        flat = np.broadcast_to(
            opening_nfa[:, None] / useful_life,
            (n_trials, useful_life),
        ).astype(float).copy()
        return cls(useful_life=useful_life, cohorts=flat)

    def advance_period(
        self,
        target_nfa: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Advance one period and return ``(capex_t, da_t, retired_t, nfa_t)``.

        Uses eq. [VI] to back out the implied Capex that hits the
        ``target_nfa`` given the current D&A + the retirement of the
        oldest cohort.
        """
        # Retired: the oldest cohort leaves the books at the end of the period
        retired_t = self.cohorts[:, -1].copy()
        # D&A: sum of 1/L of each surviving cohort (equivalent to
        # straight-line depreciation over the useful life)
        da_t = self.cohorts.sum(axis=1) / self.useful_life

        # NFA before the new Capex lands
        nfa_pre = self.cohorts.sum(axis=1) - da_t - retired_t
        # Capex to hit the target
        capex_t = np.maximum(0.0, target_nfa - nfa_pre)

        # Roll the cohorts: oldest out, new capex in as cohort age=0
        self.cohorts = np.concatenate(
            [capex_t[:, None], self.cohorts[:, :-1]], axis=1
        )
        nfa_t = self.cohorts.sum(axis=1) - 0.0  # freshly updated stock
        return capex_t, da_t, retired_t, nfa_t


def depreciation_from_vintages(
    vintages: np.ndarray,
    useful_life: int,
) -> np.ndarray:
    """Eq. [III]: straight-line D&A from a vintage matrix.

    Parameters
    ----------
    vintages : np.ndarray
        Shape ``(n_trials, useful_life)``: Capex cohort still on the books.
    useful_life : int
        Depreciation horizon in years.
    """
    if vintages.shape[1] != useful_life:
        raise ValueError(
            f"vintages has {vintages.shape[1]} columns but useful_life={useful_life}"
        )
    return vintages.sum(axis=1) / useful_life
