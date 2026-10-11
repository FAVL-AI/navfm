"""G9 — the goal image existed, and was sealed, before the robot moved.

The failure this exists to prevent is subtle and produces a dataset that trains
and evaluates beautifully. If the goal image is taken from the final observation
of the episode, then the goal is by construction reachable, perfectly framed and
photographed from exactly the pose the demonstrator happened to stop in. A
policy evaluated against such goals is being asked to reproduce an outcome that
was defined by the outcome. Nothing in the resulting trajectory files records
that this happened.

So the contract is chronological, and it is enforced on an event sequence rather
than inferred from the images:

    declare goal -> acquire goal image -> hash it -> write provenance
                 -> SEAL -> first motion command

**Pixel similarity is not provenance.** Two images being different does not show
the goal was captured first, and two being identical does not show it was
reused: a stationary robot photographs the same scene twice. Only the recorded
order of events answers the question, which is why the seal is a sequence check
and the hash exists to detect mutation after sealing rather than to compare
against the final frame.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
from itertools import pairwise
from typing import Any

from .gates import GateKind, GateResult, GateStatus

__all__ = [
    "GoalSeal",
    "GoalSealError",
    "SealEvent",
    "evaluate_goal_seal",
    "image_digest",
]


class SealEvent(enum.Enum):
    """Events whose ORDER is the contract."""

    GOAL_DECLARED = "GOAL_DECLARED"
    GOAL_IMAGE_ACQUIRED = "GOAL_IMAGE_ACQUIRED"
    GOAL_IMAGE_HASHED = "GOAL_IMAGE_HASHED"
    GOAL_PROVENANCE_WRITTEN = "GOAL_PROVENANCE_WRITTEN"
    GOAL_SEALED = "GOAL_SEALED"
    FIRST_MOTION_COMMAND = "FIRST_MOTION_COMMAND"


#: The order the contract requires, earliest first.
REQUIRED_ORDER = (
    SealEvent.GOAL_DECLARED,
    SealEvent.GOAL_IMAGE_ACQUIRED,
    SealEvent.GOAL_IMAGE_HASHED,
    SealEvent.GOAL_PROVENANCE_WRITTEN,
    SealEvent.GOAL_SEALED,
    SealEvent.FIRST_MOTION_COMMAND,
)


class GoalSealError(RuntimeError):
    """The goal contract was violated while the episode was being set up."""


def image_digest(image: Any) -> str:
    """SHA-256 of an image's bytes, however it is carried."""
    if hasattr(image, "tobytes"):
        raw = image.tobytes()
    elif isinstance(image, bytes | bytearray):
        raw = bytes(image)
    else:
        raise TypeError(f"cannot digest an image of type {type(image).__name__}")
    return hashlib.sha256(raw).hexdigest()


@dataclasses.dataclass
class GoalSeal:
    """Records the goal-image chronology as it happens.

    Used by the collector: each step is called at the moment it occurs, and
    :meth:`seal` refuses if the preceding steps did not happen. The collector
    then calls :meth:`note_first_motion` at the first velocity command, and the
    gate adjudicates the completed sequence.
    """

    goal_xy: tuple[float, float]
    source_camera: str
    events: list[tuple[str, int]] = dataclasses.field(default_factory=list)
    goal_image_sha256: str | None = None
    capture_sim_time: float | None = None
    _sealed_digest: str | None = None
    _counter: int = 0
    _has_first_motion: bool = False

    def _record(self, event: SealEvent) -> None:
        self._counter += 1
        self.events.append((event.value, self._counter))

    def declare(self) -> None:
        self._record(SealEvent.GOAL_DECLARED)

    def acquire(self, image: Any, *, sim_time: float | None = None) -> None:
        if not self._has(SealEvent.GOAL_DECLARED):
            raise GoalSealError("goal image acquired before the goal was declared")
        self.capture_sim_time = sim_time
        self._record(SealEvent.GOAL_IMAGE_ACQUIRED)
        self.goal_image_sha256 = image_digest(image)
        self._record(SealEvent.GOAL_IMAGE_HASHED)

    def write_provenance(self) -> dict[str, Any]:
        if self.goal_image_sha256 is None:
            raise GoalSealError("provenance written before the goal image was hashed")
        self._record(SealEvent.GOAL_PROVENANCE_WRITTEN)
        return {
            "goal_xy": list(self.goal_xy),
            "source_camera": self.source_camera,
            "goal_image_sha256": self.goal_image_sha256,
            "capture_sim_time": self.capture_sim_time,
            "events": list(self.events),
        }

    def seal(self) -> None:
        missing = [e.value for e in REQUIRED_ORDER[:4] if not self._has(e)]
        if missing:
            raise GoalSealError(f"cannot seal the goal: {missing} did not occur")
        self._record(SealEvent.GOAL_SEALED)
        self._sealed_digest = self.goal_image_sha256

    def note_first_motion(self) -> None:
        if not self._has(SealEvent.GOAL_SEALED):
            raise GoalSealError(
                "first motion command issued before the goal was sealed; a goal "
                "captured after motion cannot be distinguished from one derived "
                "from the episode's outcome")
        self._record(SealEvent.FIRST_MOTION_COMMAND)

    def _has(self, event: SealEvent) -> bool:
        return any(name == event.value for name, _ in self.events)

    def _index(self, event: SealEvent) -> int | None:
        for name, order in self.events:
            if name == event.value:
                return order
        return None


def evaluate_goal_seal(
    seal: GoalSeal,
    *,
    final_observation_digest: str | None = None,
    current_goal_digest: str | None = None,
) -> GateResult:
    """G9 — adjudicate the completed goal chronology.

    ``final_observation_digest`` is compared only to catch the *specific*
    degenerate case where the sealed goal is byte-identical to the episode's last
    frame. That comparison is a corroborating check, never the provenance
    decision: a stationary robot legitimately produces identical frames, and two
    different images prove nothing about capture order.
    """
    detail: dict[str, Any] = {
        "goal_xy": list(seal.goal_xy),
        "source_camera": seal.source_camera,
        "goal_image_sha256": seal.goal_image_sha256,
        "capture_sim_time": seal.capture_sim_time,
        "events": list(seal.events),
        "required_order": [e.value for e in REQUIRED_ORDER],
        "provenance_is_the_event_order": (
            "pixel similarity does not establish provenance in either direction: a "
            "stationary robot photographs the same scene twice, and two different "
            "images do not show which was captured first"),
    }

    missing = [e.value for e in REQUIRED_ORDER if seal._index(e) is None]
    if missing:
        return GateResult("G9_GOAL_IMAGE_SEAL", GateStatus.FAIL, GateKind.PRECONDITION,
                          reason=f"goal chronology incomplete: {missing}", detail=detail)

    order = [seal._index(e) for e in REQUIRED_ORDER]
    if any(a is None or b is None or a >= b for a, b in pairwise(order)):
        return GateResult("G9_GOAL_IMAGE_SEAL", GateStatus.FAIL, GateKind.PRECONDITION,
                          reason="goal events did not occur in the required order",
                          detail=detail)

    if current_goal_digest is not None and current_goal_digest != seal._sealed_digest:
        detail["sealed_digest"] = seal._sealed_digest
        detail["current_digest"] = current_goal_digest
        return GateResult("G9_GOAL_IMAGE_SEAL", GateStatus.FAIL, GateKind.PRECONDITION,
                          reason="the goal image changed after it was sealed",
                          detail=detail)

    if final_observation_digest is not None:
        detail["final_observation_digest"] = final_observation_digest
        if final_observation_digest == seal.goal_image_sha256:
            return GateResult(
                "G9_GOAL_IMAGE_SEAL", GateStatus.FAIL, GateKind.PRECONDITION,
                reason=("the sealed goal image is byte-identical to the episode's final "
                        "observation, so the goal cannot be shown to be independent of "
                        "the outcome"),
                detail=detail)

    return GateResult("G9_GOAL_IMAGE_SEAL", GateStatus.PASS, GateKind.PRECONDITION,
                      reason="goal declared, captured, hashed, sealed, then motion began",
                      detail=detail)
