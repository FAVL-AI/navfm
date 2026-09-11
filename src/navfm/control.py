"""Simulator-independent control and planning. Pure NumPy, fully unit-testable.

Two jobs:

1. **Data collection** -- generate the *demonstrator* trajectories the model
   learns from. What the demonstrator does defines the action distribution, so
   this is a modelling decision, not plumbing.
2. **Closed-loop evaluation** -- convert a policy's predicted waypoints into
   base velocity commands, for both differential-drive and holonomic bases.

The holonomic case is the substantive one here. ViNT/GNM/NoMaD were trained
almost entirely on differential-drive and Ackermann platforms, where lateral
displacement in the body frame is a *consequence* of turning, never a
commanded degree of freedom. A mecanum base can strafe. That means:

* the pretrained action prior has near-zero mass on pure-lateral motion, so
  collecting holonomic demonstrations moves the target distribution off the
  prior's support and degrades transfer;
* but at *execution* time a mecanum base can track a ``(dx, dy)`` waypoint
  exactly, without the nonholonomic detour a differential base needs.

We therefore separate ``DemonstratorMode`` (what we record) from
``BaseKinematics`` (how we execute), and default the demonstrator to
nonholonomic so the collected data stays on the prior's support. The holonomic
demonstrator is retained as a first-class ablation.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from navfm.target_selection import LegacyVertexTargetSelector, TargetSelector

__all__ = [
    "M3PRO_LIMITS",
    "BaseKinematics",
    "BaseLimits",
    "DemonstratorMode",
    "PDConfig",
    "PurePursuit",
    "holonomic_step",
    "reference_pd_twist",
    "resample_path",
    "unicycle_step",
    "waypoint_to_twist",
]


class DemonstratorMode(str, enum.Enum):
    """Which motion primitives the data-collection demonstrator is allowed."""

    #: Forward + yaw only (``v_y == 0``). Matches the pretraining distribution.
    NONHOLONOMIC = "nonholonomic"
    #: Full mecanum: forward, lateral and yaw. Ablation arm.
    HOLONOMIC = "holonomic"


class BaseKinematics(str, enum.Enum):
    DIFFERENTIAL = "differential"
    HOLONOMIC = "holonomic"


@dataclasses.dataclass(frozen=True)
class BaseLimits:
    """Velocity and acceleration envelope of the physical base.

    ``max_v``/``max_w`` also set the deployment-time unnormalisation constant:
    the reference deployment stack scales predicted waypoints by
    ``max_v / frame_rate`` (``deployment/config/robot.yaml``: 0.2 m/s, 4 Hz).
    """

    max_v: float
    max_w: float
    max_vy: float = 0.0
    max_a: float = math.inf
    max_alpha: float = math.inf

    def clamp(self, vx: float, vy: float, w: float) -> tuple[float, float, float]:
        vx = float(np.clip(vx, -self.max_v, self.max_v))
        vy = float(np.clip(vy, -self.max_vy, self.max_vy)) if self.max_vy > 0 else 0.0
        w = float(np.clip(w, -self.max_w, self.max_w))
        return vx, vy, w


#: Yahboom ROSMASTER M3 PRO. See docs/HARDWARE.md -- ``max_v``/``max_w`` are
#: PROVISIONAL: Yahboom publishes no maximum-speed figure. Replace with the
#: output of the vendor's own ``calibrate_linear.launch.py`` /
#: ``calibrate_angular.launch.py`` before any sim2real claim.
M3PRO_LIMITS = BaseLimits(max_v=0.45, max_w=1.2, max_vy=0.35, max_a=0.8, max_alpha=3.0)


@dataclasses.dataclass(frozen=True)
class PDConfig:
    """Waypoint-tracking gains.

    ``dt`` must equal ``1 / frame_rate`` of the policy loop -- the reference
    controller derives velocity as ``dx / dt``, so a mismatch rescales every
    command.
    """

    dt: float = 0.25
    eps: float = 1e-8
    kp_lin: float = 1.0
    kp_ang: float = 1.0


def reference_pd_twist(
    waypoint: Sequence[float], limits: BaseLimits, cfg: PDConfig
) -> tuple[float, float]:
    """Bit-exact port of ``deployment/src/pd_controller.py::pd_controller``.

    Included verbatim (not improved) so that closed-loop numbers are comparable
    with the published deployment stack. Note that despite the file name there
    is no derivative term and no proportional gain -- it is a feed-forward
    inverse-kinematics map with saturation.
    """
    wp = np.asarray(waypoint, dtype=np.float64)
    assert wp.shape[0] in (2, 4), "waypoint must be (dx, dy) or (dx, dy, hx, hy)"
    dx, dy = float(wp[0]), float(wp[1])

    if wp.shape[0] == 4 and abs(dx) < cfg.eps and abs(dy) < cfg.eps:
        v = 0.0
        w = math.atan2(float(wp[3]), float(wp[2])) / cfg.dt
    elif abs(dx) < cfg.eps:
        v = 0.0
        w = math.copysign(math.pi / (2.0 * cfg.dt), dy)
    else:
        v = dx / cfg.dt
        w = math.atan(dy / dx) / cfg.dt

    v = float(np.clip(v, 0.0, limits.max_v))
    w = float(np.clip(w, -limits.max_w, limits.max_w))
    return v, w


def waypoint_to_twist(
    waypoint: Sequence[float],
    limits: BaseLimits,
    cfg: PDConfig,
    kinematics: BaseKinematics = BaseKinematics.DIFFERENTIAL,
) -> tuple[float, float, float]:
    """Convert one body-frame waypoint to ``(vx, vy, wz)``.

    ``DIFFERENTIAL`` delegates to :func:`reference_pd_twist` so results stay
    comparable with the published stack.

    ``HOLONOMIC`` tracks the waypoint directly: the base can realise ``dy``
    without rotating, so lateral error becomes ``v_y`` instead of yaw rate. The
    residual yaw term still aligns heading with the direction of travel, which
    keeps the forward camera pointed where the robot is going -- essential,
    because the policy is conditioned on that camera and a crab-walking robot
    would see a view its training distribution never contained.
    """
    wp = np.asarray(waypoint, dtype=np.float64)
    dx, dy = float(wp[0]), float(wp[1])

    if kinematics is BaseKinematics.DIFFERENTIAL:
        v, w = reference_pd_twist(waypoint, limits, cfg)
        return v, 0.0, w

    vx = cfg.kp_lin * dx / cfg.dt
    vy = cfg.kp_lin * dy / cfg.dt
    if wp.shape[0] == 4:
        heading_err = math.atan2(float(wp[3]), float(wp[2]))
    elif math.hypot(dx, dy) > cfg.eps:
        heading_err = math.atan2(dy, dx)
    else:
        heading_err = 0.0
    wz = cfg.kp_ang * heading_err / cfg.dt
    return limits.clamp(vx, vy, wz)


class PurePursuit:
    """Look-ahead path tracker used by the data-collection demonstrator.

    Deliberately *smooth*: bang-bang or teleop-jerky demonstrations produce
    action labels with high-frequency content that a 5-to-8-step waypoint
    regressor cannot represent, which shows up as an irreducible action-loss
    floor. Pure pursuit with a look-ahead of a few tenths of a metre yields the
    curvature-continuous motion the label format assumes.
    """

    def __init__(
        self,
        path: np.ndarray,
        *,
        lookahead: float = 0.45,
        goal_tol: float = 0.20,
        limits: BaseLimits = M3PRO_LIMITS,
        mode: DemonstratorMode = DemonstratorMode.NONHOLONOMIC,
        cruise_v: float | None = None,
        target_selector: TargetSelector | None = None,
    ) -> None:
        self.path = np.asarray(path, dtype=np.float64).reshape(-1, 2)
        if self.path.shape[0] < 2:
            raise ValueError("path needs at least two waypoints")
        self.lookahead = float(lookahead)
        self.goal_tol = float(goal_tol)
        self.limits = limits
        self.mode = mode
        self.cruise_v = float(cruise_v) if cruise_v is not None else limits.max_v
        self._idx = 0
        # Omitting the selector yields the frozen behaviour, so no existing
        # caller changes because the seam now exists.
        self._selector: TargetSelector = (
            target_selector if target_selector is not None else LegacyVertexTargetSelector()
        )

    @property
    def finished(self) -> bool:
        return self._idx >= self.path.shape[0] - 1

    def target(self, position: np.ndarray) -> np.ndarray:
        """Advance the path index and return the current look-ahead point.

        The selection itself lives behind the injection seam. The index
        advancement it reports is applied here, so ``finished`` means what it
        always meant.
        """
        pos = np.asarray(position, dtype=np.float64)[:2]
        selection = self._selector.select_target(self.path, pos, self._idx, self.lookahead)
        self._idx = selection.next_index
        return selection.point

    def step(self, position: np.ndarray, yaw: float) -> tuple[float, float, float, bool]:
        """Return ``(vx, vy, wz, done)`` for the current pose."""
        pos = np.asarray(position, dtype=np.float64)[:2]
        if np.linalg.norm(self.path[-1] - pos) < self.goal_tol:
            return 0.0, 0.0, 0.0, True

        tgt = self.target(pos)
        delta = tgt - pos
        c, s = math.cos(-yaw), math.sin(-yaw)
        bx = c * delta[0] - s * delta[1]
        by = s * delta[0] + c * delta[1]
        dist = math.hypot(bx, by)
        if dist < 1e-9:
            return 0.0, 0.0, 0.0, self.finished

        if self.mode is DemonstratorMode.HOLONOMIC:
            scale = min(self.cruise_v, self.limits.max_v) / dist
            vx, vy = bx * scale, by * scale
            wz = math.atan2(by, bx) / max(self.lookahead / max(self.cruise_v, 1e-6), 1e-3)
            vx, vy, wz = self.limits.clamp(vx, vy, wz)
            return vx, vy, wz, False

        # Nonholonomic pure pursuit: curvature = 2 * lateral_offset / dist^2.
        heading_err = math.atan2(by, bx)
        curvature = 2.0 * by / (dist * dist)
        # Slow down for sharp headings so the base does not scrub sideways.
        vx = self.cruise_v * max(0.15, math.cos(np.clip(heading_err, -math.pi, math.pi)))
        wz = curvature * vx
        if abs(heading_err) > math.radians(75.0):
            # Turn (nearly) in place rather than carving an unrealistic arc.
            vx = 0.05 * self.cruise_v
            wz = math.copysign(self.limits.max_w, heading_err)
        vx, _vy, wz = self.limits.clamp(vx, 0.0, wz)
        return vx, 0.0, wz, False


def unicycle_step(
    position: np.ndarray, yaw: float, v: float, w: float, dt: float
) -> tuple[np.ndarray, float]:
    """Exact (arc) integration of the unicycle model -- no Euler drift.

    Used by the offline closed-loop simulator so that controller tests do not
    depend on Isaac Sim being installed.
    """
    pos = np.asarray(position, dtype=np.float64)[:2].copy()
    if abs(w) < 1e-9:
        pos += v * dt * np.array([math.cos(yaw), math.sin(yaw)])
        return pos, yaw
    radius = v / w
    new_yaw = yaw + w * dt
    pos += radius * np.array(
        [math.sin(new_yaw) - math.sin(yaw), -(math.cos(new_yaw) - math.cos(yaw))]
    )
    return pos, new_yaw


def holonomic_step(
    position: np.ndarray, yaw: float, vx: float, vy: float, w: float, dt: float
) -> tuple[np.ndarray, float]:
    """Body-frame velocity integration for an omnidirectional base."""
    pos = np.asarray(position, dtype=np.float64)[:2].copy()
    mid_yaw = yaw + 0.5 * w * dt  # midpoint rule keeps second-order accuracy
    c, s = math.cos(mid_yaw), math.sin(mid_yaw)
    pos += dt * np.array([c * vx - s * vy, s * vx + c * vy])
    return pos, yaw + w * dt


def resample_path(path: np.ndarray, spacing: float) -> np.ndarray:
    """Arc-length resample a polyline to uniform ``spacing`` metres."""
    path = np.asarray(path, dtype=np.float64).reshape(-1, 2)
    if path.shape[0] < 2:
        return path
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    if total < spacing:
        return path[[0, -1]]
    n = int(total // spacing) + 1
    targets = np.linspace(0.0, total, n)
    x = np.interp(targets, cum, path[:, 0])
    y = np.interp(targets, cum, path[:, 1])
    return np.stack([x, y], axis=1)

def unnormalise_waypoint(
    waypoint: Any, *, metric_waypoint_spacing: float, waypoint_spacing: int = 1
) -> np.ndarray:
    """Normalised model waypoint -> metres in the robot frame.

    The exact inverse of the label-side normalisation in
    :func:`navfm.kinematics.to_local_waypoints`, which divides robot-frame
    displacements by ``metric_waypoint_spacing * waypoint_spacing``. A policy
    trained on those labels predicts in the same normalised units, so its output
    must be multiplied back before any controller sees it.

    This existed only as a sentence in a docstring describing the *upstream*
    deployment stack, while :func:`waypoint_to_twist` consumes metres directly.
    Feeding a raw prediction to it therefore rescaled every command by
    ``1 / metric_waypoint_spacing`` -- about 8x for GO Stanford -- without
    raising, and produced a trajectory that looks plausible and is wrong
    everywhere. The failure is silent because nothing downstream knows which
    units it received.

    Only the displacement components are scaled. ``(cos, sin)`` are a direction:
    scaling them would change the represented angle, not its magnitude.
    """
    scale = float(metric_waypoint_spacing) * float(waypoint_spacing)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError(
            f"metric_waypoint_spacing * waypoint_spacing must be positive and finite; "
            f"got {scale!r}. A zero or negative scale would silently null or mirror "
            f"every command."
        )
    wp = np.asarray(waypoint, dtype=np.float64).copy()
    if wp.shape[-1] not in (2, 4):
        raise ValueError(
            f"waypoint last dimension must be 2 (dx, dy) or 4 (dx, dy, cos, sin); "
            f"got shape {wp.shape}"
        )
    wp[..., 0] *= scale
    wp[..., 1] *= scale
    return wp
