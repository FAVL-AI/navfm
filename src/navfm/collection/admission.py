"""BO-10 collection admission: all gates, composed, with no partial credit.

The composition exists so that "may this episode be collected?" has exactly one
answer computed in exactly one place. A collector that consulted gates
individually would eventually consult most of them.

**Pre-motion and post-episode are separated, and the separation is enforced.**
Only pre-motion gates can authorise execution, because they are the only ones
whose subject exists before the episode runs. A postcondition asked before
collection has nothing to measure, and answering it anyway is how a
postcondition gets reported for an episode that never happened. Asking this
object for a post-episode verdict before the episode is a programming error and
raises.

**All required gates must PASS.** No averaging, no partial credit, and
INCONCLUSIVE is not a weak pass -- a gate that could not reach its subject
measured nothing, and treating that as authorisation is the FL-019 shape.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .gates import GateKind, GateResult, GateStatus
from .scope import CollectionScope

__all__ = [
    "POST_EPISODE_GATES",
    "PRE_MOTION_GATES",
    "AdmissionError",
    "BO10CollectionAdmission",
]

#: Gates that must PASS before the first motion command.
PRE_MOTION_GATES = (
    "G2_OBSTACLE_MAP_INTEGRITY",
    "G3_START_SUPPORT",
    "G4_CONTINUOUS_ROUTE_SUPPORT",
    "G5_OBSTACLE_CLEARANCE",
    "G6_END_SUPPORT",
    "G7_CAMERA",
    "G9_GOAL_IMAGE_SEAL",
    "G10_LONG_HORIZON",          # as PREDICTED_CAPABILITY before the episode
)

#: Gates decided only from what the episode produced.
POST_EPISODE_GATES = (
    "G8_CONTROLLER_IDENTITY",
    "G10_LONG_HORIZON",          # as POSTCONDITION, from recorded data
    "MOTION_REALISED",
)


class AdmissionError(RuntimeError):
    """A verdict was requested that the available evidence cannot support."""


@dataclasses.dataclass
class BO10CollectionAdmission:
    """Collects gate results and answers the two admission questions."""

    scope: CollectionScope
    route_id: str
    scene: str
    pre_motion: dict[str, GateResult] = dataclasses.field(default_factory=dict)
    post_episode: dict[str, GateResult] = dataclasses.field(default_factory=dict)

    def record(self, result: GateResult) -> None:
        """File a gate result under the phase its kind implies.

        The kind decides, not the caller: a PREDICTED_CAPABILITY filed as a
        postcondition would be a forecast presented as a measurement.
        """
        if result.kind is GateKind.POSTCONDITION:
            self.post_episode[result.gate] = result
        else:
            self.pre_motion[result.gate] = result

    # -- pre-motion ------------------------------------------------------

    @property
    def missing_pre_motion_gates(self) -> list[str]:
        return [g for g in PRE_MOTION_GATES if g not in self.pre_motion]

    @property
    def failed_pre_motion_gates(self) -> list[str]:
        return sorted(g for g, r in self.pre_motion.items() if not r.admits)

    def may_begin_motion(self) -> bool:
        """True only when every pre-motion gate is present and PASS."""
        return not self.missing_pre_motion_gates and not self.failed_pre_motion_gates

    def assert_may_begin_motion(self) -> None:
        """Refuse to start an episode unless every pre-motion gate passed.

        A missing gate is refused exactly as loudly as a failing one. "Not
        evaluated" reaching a caller that expected "evaluated and passed" is the
        failure mode the whole gate discipline exists to prevent.
        """
        missing = self.missing_pre_motion_gates
        failed = self.failed_pre_motion_gates
        if not missing and not failed:
            return
        parts = []
        if missing:
            parts.append(f"not evaluated: {missing}")
        if failed:
            parts.append(
                "did not pass: "
                + ", ".join(f"{g}={self.pre_motion[g].status.value}" for g in failed))
        raise AdmissionError(
            f"route {self.route_id} in {self.scene} may not begin motion -- " + "; ".join(parts)
        )

    # -- post-episode ----------------------------------------------------

    @property
    def missing_post_episode_gates(self) -> list[str]:
        return [g for g in POST_EPISODE_GATES if g not in self.post_episode]

    def episode_admitted(self) -> bool:
        """True only after the episode, when every gate in both phases passed."""
        if self.missing_post_episode_gates:
            raise AdmissionError(
                f"post-episode verdict requested for route {self.route_id} before "
                f"{self.missing_post_episode_gates} were measured. A postcondition "
                "asked before the episode has nothing to measure.")
        return self.may_begin_motion() and all(r.admits for r in self.post_episode.values())

    # -- reporting -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "route_id": self.route_id,
            "scene": self.scene,
            "scope": self.scope.to_manifest_fields(),
            "admission_rule": "ALL required gates must PASS; no averaging, no partial credit",
            "inconclusive_is_not_a_pass": (
                "a gate that could not reach its subject measured nothing; treating that "
                "as authorisation is the FL-019 shape"),
            "pre_motion_gates_required": list(PRE_MOTION_GATES),
            "post_episode_gates_required": list(POST_EPISODE_GATES),
            "pre_motion": {g: r.to_dict() for g, r in sorted(self.pre_motion.items())},
            "post_episode": {g: r.to_dict() for g, r in sorted(self.post_episode.items())},
            "pre_motion_missing": self.missing_pre_motion_gates,
            "pre_motion_failed": self.failed_pre_motion_gates,
            "MAY_BEGIN_MOTION": self.may_begin_motion(),
        }
        if self.missing_post_episode_gates:
            record["EPISODE_ADMITTED"] = "NOT_YET_MEASURED"
            record["post_episode_missing"] = self.missing_post_episode_gates
        else:
            record["EPISODE_ADMITTED"] = self.episode_admitted()
        return record

    @staticmethod
    def inconclusive(gate: str, reason: str, kind: GateKind = GateKind.PRECONDITION) -> GateResult:
        """Helper for a gate that could not reach its subject."""
        return GateResult(gate, GateStatus.INCONCLUSIVE, kind, reason=reason)
