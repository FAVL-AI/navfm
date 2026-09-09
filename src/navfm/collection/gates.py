"""Gate results: what a gate decided, and what kind of thing it decided.

Two distinctions this module exists to keep, both of which collapse silently if
a gate returns a bare boolean.

**PASS / FAIL / INCONCLUSIVE are three outcomes, not two.** A gate that could
not reach its subject -- a runtime that failed to start, a probe with no
geometry to query -- measured nothing, and recording that as FAIL is the same
error in the opposite direction as recording it as PASS. G7 has already been
INCONCLUSIVE once here, from an articulation defect in ``robot.spawn()``, and
reading it as a camera failure would have sent the repair to the wrong place.

**A precondition is not a postcondition.** Some gates authorise an episode
before it runs; others validate what the episode produced. A few, like the
long-horizon requirement, exist in both forms -- a prediction from the planned
route, and a measurement of the realised trajectory. Those are different claims
about different objects, and a composition that treated the prediction as the
measurement would report a postcondition before the episode occurred.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

__all__ = ["GateKind", "GateResult", "GateStatus"]


class GateStatus(enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"

    #: The gate did not reach its subject. Never a pass, never a failure of the
    #: subject -- a failure of the measurement.
    INCONCLUSIVE = "INCONCLUSIVE"

    @property
    def admits(self) -> bool:
        """Only PASS admits. INCONCLUSIVE is not a weak pass."""
        return self is GateStatus.PASS


class GateKind(enum.Enum):
    #: Decided before motion; may authorise execution.
    PRECONDITION = "PRECONDITION"

    #: A prediction about what the episode will produce, from the planned route.
    #: Never evidence about the realised trajectory.
    PREDICTED_CAPABILITY = "PREDICTED_CAPABILITY"

    #: Decided from recorded data after the episode.
    POSTCONDITION = "POSTCONDITION"


@dataclasses.dataclass(frozen=True)
class GateResult:
    gate: str
    status: GateStatus
    kind: GateKind
    reason: str = ""
    detail: dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def admits(self) -> bool:
        return self.status.admits

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status.value,
            "kind": self.kind.value,
            "reason": self.reason,
            "detail": self.detail,
        }
