"""DCF valuation engine with Terminal Value coherence checks.

Reference: Scarano A., Di Napoli G., "Calcolo del Terminal Value (TV) e rispetto
delle condizioni di coerenza", Rivista AIAF n. 66, apr. 2008, pp. 27-32.
"""

from rating_valuation.dcf.coherence import (
    CoherenceCheck,
    CoherenceReport,
    Severity,
    check_coherence,
)
from rating_valuation.dcf.three_stage import (
    ThreeStageInputs,
    ThreeStageResult,
    compute_fade_rate,
    value_three_stage,
)
from rating_valuation.dcf.two_stage import (
    TwoStageInputs,
    TwoStageResult,
    terminal_value_coherent,
    value_two_stage,
    value_two_stage_coherent,
)

__all__ = [
    "CoherenceCheck",
    "CoherenceReport",
    "Severity",
    "ThreeStageInputs",
    "ThreeStageResult",
    "TwoStageInputs",
    "TwoStageResult",
    "check_coherence",
    "compute_fade_rate",
    "terminal_value_coherent",
    "value_three_stage",
    "value_two_stage",
    "value_two_stage_coherent",
]
