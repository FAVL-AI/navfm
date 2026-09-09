"""G8 — the controller that drives an episode is the one that was declared.

A collection run is only reproducible if the thing doing the driving is fixed
for its duration. The failure this catches is not sabotage; it is a parameter
changed between episodes, a config reloaded mid-run, or a limits object mutated
by a caller that assumed it owned it. Any of those makes the episodes in one
dataset the product of different demonstrators, and nothing in the recorded
trajectories says so.

So the identity is digested before the episode and recomputed after, and the
two must agree.

**A digest is not a motion claim.** This gate says the controller did not
change. It says nothing about whether the robot moved: a controller can issue
commands to an articulation that is wedged, unauthored or asleep, and the digest
is identical in every case. FL-013 is the same genus -- ``optimizer.step()``
returning is not evidence the model changed. Realised motion is a POSTCONDITION,
measured from recorded poses by :func:`verify_motion_occurred`, and the two must
never be reported as one fact.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import numpy as np

from .gates import GateKind, GateResult, GateStatus

__all__ = [
    "ControllerIdentity",
    "evaluate_controller_identity",
    "verify_motion_occurred",
]


@dataclasses.dataclass(frozen=True)
class ControllerIdentity:
    """Everything that determines how the demonstrator behaves."""

    implementation: str
    control_hz: float
    max_v: float
    max_w: float
    max_vy: float
    max_a: float
    max_alpha: float
    cruise_v: float
    lookahead_m: float
    goal_tol_m: float
    demonstrator_mode: str
    seed: int
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        # Infinities are legitimate limit values and are not JSON-representable,
        # so they are encoded rather than dropped: a digest that silently ignored
        # an unbounded acceleration limit would not notice it being bounded.
        def encode(v: Any) -> Any:
            if isinstance(v, float) and (v == float("inf") or v == float("-inf")):
                return f"{'-' if v < 0 else ''}Infinity"
            if isinstance(v, float) and v != v:
                return "NaN"
            return v
        return {k: (encode(v) if not isinstance(v, dict)
                    else {ik: encode(iv) for ik, iv in v.items()}) for k, v in d.items()}

    @property
    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def evaluate_controller_identity(
    before: ControllerIdentity,
    after: ControllerIdentity,
) -> GateResult:
    """G8 — the controller and its configuration did not change during collection."""
    same = before.digest == after.digest
    changed_fields = sorted(
        k for k, v in before.to_dict().items() if after.to_dict().get(k) != v
    )
    detail: dict[str, Any] = {
        "before_digest": before.digest,
        "after_digest": after.digest,
        "before": before.to_dict(),
        "after": after.to_dict(),
        "changed_fields": changed_fields,
        "claim_boundary": (
            "controller identity only. This gate does not establish that the robot "
            "moved: a command issued to a wedged articulation produces an identical "
            "digest. Realised motion is a postcondition measured from recorded poses."),
    }
    if same:
        return GateResult("G8_CONTROLLER_IDENTITY", GateStatus.PASS, GateKind.POSTCONDITION,
                          reason="controller identity unchanged across the episode",
                          detail=detail)
    return GateResult(
        "G8_CONTROLLER_IDENTITY", GateStatus.FAIL, GateKind.POSTCONDITION,
        reason=f"controller changed during collection: {', '.join(changed_fields) or 'digest differs'}",
        detail=detail,
    )


def verify_motion_occurred(
    positions: np.ndarray,
    yaws: np.ndarray,
    *,
    min_displacement_m: float = 0.5,
) -> GateResult:
    """POSTCONDITION — the robot actually moved, from recorded poses.

    Deliberately separate from G8. "A command was issued" and "the base moved"
    are different facts, and the whole point of recording both is that they can
    disagree.
    """
    pos = np.asarray(positions, dtype=float)
    yaw = np.asarray(yaws, dtype=float)
    if pos.ndim != 2 or pos.shape[1] != 2 or pos.shape[0] < 2:
        return GateResult("MOTION_REALISED", GateStatus.INCONCLUSIVE, GateKind.POSTCONDITION,
                          reason=f"cannot measure motion from positions of shape {pos.shape}",
                          detail={"positions_shape": list(pos.shape)})
    travelled = float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum())
    net = float(np.linalg.norm(pos[-1] - pos[0]))
    yaw_span = float(np.ptp(np.unwrap(yaw))) if yaw.size > 1 else 0.0
    detail = {
        "travelled_distance_m": travelled,
        "net_displacement_m": net,
        "yaw_span_rad": yaw_span,
        "min_displacement_m": min_displacement_m,
        "distinct_from_g8": "G8 proves the controller did not change; this proves the base moved",
    }
    if travelled >= min_displacement_m:
        return GateResult("MOTION_REALISED", GateStatus.PASS, GateKind.POSTCONDITION,
                          reason=f"travelled {travelled:.3f} m", detail=detail)
    return GateResult("MOTION_REALISED", GateStatus.FAIL, GateKind.POSTCONDITION,
                      reason=(f"travelled {travelled:.4f} m < {min_displacement_m} m; "
                              "commands were issued but the base did not move"),
                      detail=detail)
