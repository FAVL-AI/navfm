"""KINEMATIC_COLLECTION_DRIVE_V1 — SE(2) drive with a collision invariant.

`F-DRIVE-1` established that commanding articulation root velocity does not move
this robot: PhysX overrides the imposed velocity against wheel contact and the
base vibrates in place, 0.0036 m over 40 steps. BO-10 needs a trajectory, not a
drivetrain model, so the base is driven kinematically.

**What this is not.** Integrating a twist and setting the pose would let the
robot pass through anything the planner's map failed to represent, which would
make the obstacle map the only thing between the dataset and a trajectory that
drives through furniture. Given that this programme has just spent a tranche
discovering that the map omitted a reception desk entirely, that is not an
acceptable single point of failure.

So every pose is a *candidate* until an independent geometric test admits it:

    current SE(2) -> desired twist -> candidate SE(2)
                  -> swept-footprint test against SCENE collision geometry
                  -> admitted: apply     rejected: refuse and stop

The guard queries the scene, not the map that planned the route. It is a runtime
invariant, not a diagnostic: a rejected pose is never applied.

**Claim boundary.** ``MOTION_MODEL = KINEMATIC_SE2``. Contact response, wheel
dynamics, mecanum roller behaviour, slip and traction are NOT_EVALUATED. This
mechanism supports trajectory geometry, camera observations, SE(2) pose history
and route-following execution, and supports no claim about drivetrain fidelity.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from typing import Any, Protocol

import numpy as np

__all__ = [
    "CollisionGuard",
    "DriveOutcome",
    "KinematicDriveConfig",
    "KinematicDriver",
    "StepResult",
    "integrate_se2",
    "swept_poses",
]


class DriveOutcome(enum.Enum):
    APPLIED = "APPLIED"
    #: The candidate pose or the sweep to it met blocking geometry.
    REJECTED_COLLISION = "REJECTED_COLLISION"
    #: The commanded twist was effectively zero, so no pose change was proposed.
    NO_COMMAND = "NO_COMMAND"

    @property
    def moved(self) -> bool:
        return self is DriveOutcome.APPLIED


@dataclasses.dataclass(frozen=True)
class KinematicDriveConfig:
    """Frozen before production use. Not tuned from a production outcome."""

    dt: float = 1.0 / 12.0
    max_v: float = 0.45
    max_vy: float = 0.35
    max_w: float = 1.2
    #: Sub-steps between the current and candidate pose for the sweep test. The
    #: guard must not be defeated by a single large dt stepping over a wall.
    sweep_substeps: int = 8
    #: Below this the command is treated as no command, so "did not move" and
    #: "was not asked to move" stay distinguishable.
    zero_command_eps: float = 1e-6
    #: A pose change larger than the limits could produce in one dt is refused
    #: as an integration fault rather than applied.
    max_step_translation_m: float = 0.45 / 12.0 * 1.5
    max_step_rotation_rad: float = 1.2 / 12.0 * 1.5

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class CollisionGuard(Protocol):
    """Is the robot footprint free of blocking geometry at this pose?"""

    def pose_is_free(self, x: float, y: float, yaw: float) -> bool: ...


def integrate_se2(
    pose: tuple[float, float, float],
    twist: tuple[float, float, float],
    dt: float,
) -> tuple[float, float, float]:
    """Advance an SE(2) pose by a body-frame twist for ``dt``.

    Body-frame velocities are rotated into the world by the CURRENT heading and
    applied over the interval, which is the standard explicit step. It is exact
    for straight motion and first-order for turning; ``sweep_substeps`` is what
    keeps the arc between poses from being stepped over.
    """
    x, y, yaw = pose
    vx, vy, wz = twist
    c, s = math.cos(yaw), math.sin(yaw)
    nx = x + (c * vx - s * vy) * dt
    ny = y + (s * vx + c * vy) * dt
    nyaw = math.atan2(math.sin(yaw + wz * dt), math.cos(yaw + wz * dt))
    return nx, ny, nyaw


def swept_poses(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    substeps: int,
) -> list[tuple[float, float, float]]:
    """Interpolated poses strictly between ``start`` and ``end``, inclusive of end.

    Heading is interpolated on the shortest arc, so a step across the +/-pi
    branch does not sweep the long way round and test poses the robot never
    occupies.
    """
    if substeps < 1:
        raise ValueError("substeps must be >= 1")
    x0, y0, a0 = start
    x1, y1, a1 = end
    da = math.atan2(math.sin(a1 - a0), math.cos(a1 - a0))
    out: list[tuple[float, float, float]] = []
    for k in range(1, substeps + 1):
        t = k / substeps
        out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t,
                    math.atan2(math.sin(a0 + da * t), math.cos(a0 + da * t))))
    return out


@dataclasses.dataclass
class StepResult:
    outcome: DriveOutcome
    pose: tuple[float, float, float]
    commanded: tuple[float, float, float]
    reason: str = ""
    rejected_at: tuple[float, float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "pose": list(self.pose),
            "commanded": list(self.commanded),
            "reason": self.reason,
            "rejected_at": list(self.rejected_at) if self.rejected_at else None,
        }


@dataclasses.dataclass
class KinematicDriver:
    """Applies twists as SE(2) poses, subject to the collision invariant."""

    guard: CollisionGuard
    config: KinematicDriveConfig = dataclasses.field(default_factory=KinematicDriveConfig)
    rejections: int = 0
    applied: int = 0

    def step(
        self,
        pose: tuple[float, float, float],
        twist: tuple[float, float, float],
    ) -> StepResult:
        cfg = self.config
        vx = float(np.clip(twist[0], -cfg.max_v, cfg.max_v))
        vy = float(np.clip(twist[1], -cfg.max_vy, cfg.max_vy))
        wz = float(np.clip(twist[2], -cfg.max_w, cfg.max_w))

        if (abs(vx) < cfg.zero_command_eps and abs(vy) < cfg.zero_command_eps
                and abs(wz) < cfg.zero_command_eps):
            # Distinguished from a rejection: nothing was asked for, so nothing
            # moving is the correct outcome rather than a safety event.
            return StepResult(DriveOutcome.NO_COMMAND, pose, (vx, vy, wz),
                              reason="commanded twist is zero")

        candidate = integrate_se2(pose, (vx, vy, wz), cfg.dt)

        travelled = math.hypot(candidate[0] - pose[0], candidate[1] - pose[1])
        turned = abs(math.atan2(math.sin(candidate[2] - pose[2]),
                                math.cos(candidate[2] - pose[2])))
        if travelled > cfg.max_step_translation_m or turned > cfg.max_step_rotation_rad:
            # An integration fault, not a manoeuvre. Refused rather than applied,
            # because a pose jump beyond what the limits permit in one dt is the
            # shape a teleport-through-a-wall would take.
            self.rejections += 1
            return StepResult(DriveOutcome.REJECTED_COLLISION, pose, (vx, vy, wz),
                              reason=(f"integration fault: {travelled:.4f} m / "
                                      f"{turned:.4f} rad exceeds the per-step limit"),
                              rejected_at=candidate)

        # The sweep, not just the endpoint. A candidate pose beyond a thin wall
        # is free at both ends and crosses geometry in between.
        for probe in swept_poses(pose, candidate, cfg.sweep_substeps):
            if not self.guard.pose_is_free(*probe):
                self.rejections += 1
                return StepResult(DriveOutcome.REJECTED_COLLISION, pose, (vx, vy, wz),
                                  reason="swept footprint meets blocking geometry",
                                  rejected_at=probe)

        self.applied += 1
        return StepResult(DriveOutcome.APPLIED, candidate, (vx, vy, wz),
                          reason="swept footprint clear")

    def to_dict(self) -> dict[str, Any]:
        return {
            "motion_model": "KINEMATIC_SE2",
            "contact_response": "NOT_EVALUATED",
            "wheel_dynamics": "NOT_EVALUATED",
            "mecanum_roller_fidelity": "NOT_EVALUATED",
            "slip_traction_fidelity": "NOT_EVALUATED",
            "config": self.config.to_dict(),
            "steps_applied": self.applied,
            "steps_rejected": self.rejections,
        }
