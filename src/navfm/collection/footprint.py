"""Footprint sampling and swept-route configurations, with a derived resolution.

The gates in this package all ask the same shape of question -- *is every part
of the robot, everywhere along the route, over the ground it needs and clear of
the geometry it must not hit* -- and they all answer it by probing a finite set
of points. The resolution of that set is the whole gate: probe too coarsely and
the gate reports PASS because it stepped over the hole.

**The resolution is derived, and frozen before any production route is seen.**

    smallest hazard the gate claims to detect = one occupancy cell = 0.10 m
                                                (CollectConfig.grid_resolution)
    Nyquist                                   => probe spacing <= 0.05 m
    route sample step                          = 0.05 m
    yaw step such that the footprint rim moves = 0.05 m
                                              => 0.05 / radius rad

Nothing here was chosen after looking at Hospital. If a later measurement shows
that a smaller feature must be detected, the derivation changes in a dated
amendment and the gate is re-run -- it is not retuned against an outcome.

**Yaw-invariance is stated, not hidden.** The frozen production footprint is a
disc (``footprint_radius = 0.24``), and a disc's occupied set does not depend on
heading. So for the production model ``points(x, y, yaw)`` is independent of
``yaw``, and G4's "unsupported corner during a turn" cannot be distinguished
from "unsupported corner" by geometry alone. Rather than let that make the
control vacuous, :class:`RectangularFootprint` exists as a control instrument:
it is genuinely yaw-dependent, so a test using it proves the swept machinery
consumes heading rather than merely carrying it.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

import numpy as np

__all__ = [
    "DERIVATION",
    "CircularFootprint",
    "Footprint",
    "RectangularFootprint",
    "SweepResolution",
    "SweptConfiguration",
    "heading_changes",
    "resample_route",
    "swept_configurations",
]

#: The occupancy resolution the planner's map is built at. Repeated here rather
#: than imported from CollectConfig because this is the *derivation input*, and a
#: default that drifts must break this module's pin test rather than silently
#: change the probe spacing.
GRID_RESOLUTION_M = 0.10


@dataclasses.dataclass(frozen=True)
class SweepResolution:
    """Frozen sampling resolution for support and clearance sweeps."""

    smallest_detectable_feature_m: float
    probe_spacing_m: float
    route_step_m: float
    max_yaw_step_rad: float

    @classmethod
    def derive(
        cls,
        footprint_radius_m: float,
        *,
        grid_resolution_m: float = GRID_RESOLUTION_M,
    ) -> SweepResolution:
        if footprint_radius_m <= 0:
            raise ValueError(f"footprint radius must be positive, got {footprint_radius_m}")
        if grid_resolution_m <= 0:
            raise ValueError(f"grid resolution must be positive, got {grid_resolution_m}")
        spacing = grid_resolution_m / 2.0
        return cls(
            smallest_detectable_feature_m=grid_resolution_m,
            probe_spacing_m=spacing,
            route_step_m=spacing,
            max_yaw_step_rad=spacing / footprint_radius_m,
        )

    def to_dict(self) -> dict[str, float | str]:
        return {
            "smallest_detectable_feature_m": self.smallest_detectable_feature_m,
            "probe_spacing_m": self.probe_spacing_m,
            "route_step_m": self.route_step_m,
            "max_yaw_step_rad": self.max_yaw_step_rad,
            "max_yaw_step_deg": math.degrees(self.max_yaw_step_rad),
            "derivation": DERIVATION,
        }


DERIVATION = (
    "smallest detectable unsupported/blocking feature = one occupancy cell "
    "(CollectConfig.grid_resolution); Nyquist gives probe spacing = cell/2; the route step "
    "equals the probe spacing; the yaw step is the rotation that moves the footprint rim by "
    "one probe spacing. Frozen before any production route was evaluated."
)


class Footprint(Protocol):
    """A robot footprint that can enumerate the ground it occupies."""

    @property
    def circumscribed_radius_m(self) -> float: ...

    def body_points(self, spacing_m: float) -> np.ndarray:
        """Body-frame (N, 2) points covering the footprint at ``spacing_m``."""

    def points(self, x: float, y: float, yaw: float, spacing_m: float) -> np.ndarray:
        """World-frame (N, 2) points for a pose."""


@dataclasses.dataclass(frozen=True)
class CircularFootprint:
    """The frozen production footprint: a disc of ``radius_m``.

    Sampled as a lattice over the disc plus its rim. The rim matters on its own
    account -- a lattice alone can miss a slab edge that passes between lattice
    rows, and the rim is exactly where a robot straddling an edge loses support.
    """

    radius_m: float

    @property
    def circumscribed_radius_m(self) -> float:
        return self.radius_m

    def body_points(self, spacing_m: float) -> np.ndarray:
        if spacing_m <= 0:
            raise ValueError(f"spacing must be positive, got {spacing_m}")
        r = self.radius_m
        n = max(1, int(math.ceil(r / spacing_m)))
        axis = np.linspace(-n, n, 2 * n + 1) * spacing_m
        gx, gy = np.meshgrid(axis, axis, indexing="ij")
        flat = np.column_stack([gx.ravel(), gy.ravel()])
        inside = flat[np.linalg.norm(flat, axis=1) <= r + 1e-12]
        n_rim = max(8, int(math.ceil(2 * math.pi * r / spacing_m)))
        a = np.linspace(0.0, 2 * math.pi, n_rim, endpoint=False)
        rim = np.column_stack([r * np.cos(a), r * np.sin(a)])
        return np.vstack([inside, rim])

    def points(self, x: float, y: float, yaw: float, spacing_m: float) -> np.ndarray:
        # A disc is rotation-invariant, so yaw does not enter. Stated here rather
        # than silently dropped: a caller reading this must not conclude that the
        # sweep is yaw-aware for the production footprint.
        return self.body_points(spacing_m) + np.asarray([x, y], dtype=float)


@dataclasses.dataclass(frozen=True)
class RectangularFootprint:
    """A yaw-dependent footprint. Control instrument, not the production model.

    Exists so that "the sweep consumes heading" is a property a test can fail,
    which it cannot be while every footprint in the suite is a disc.
    """

    length_m: float
    width_m: float

    @property
    def circumscribed_radius_m(self) -> float:
        return 0.5 * math.hypot(self.length_m, self.width_m)

    def body_points(self, spacing_m: float) -> np.ndarray:
        if spacing_m <= 0:
            raise ValueError(f"spacing must be positive, got {spacing_m}")
        hx, hy = self.length_m / 2.0, self.width_m / 2.0
        nx = max(1, int(math.ceil(hx / spacing_m)))
        ny = max(1, int(math.ceil(hy / spacing_m)))
        gx, gy = np.meshgrid(
            np.linspace(-hx, hx, 2 * nx + 1),
            np.linspace(-hy, hy, 2 * ny + 1),
            indexing="ij",
        )
        return np.column_stack([gx.ravel(), gy.ravel()])

    def points(self, x: float, y: float, yaw: float, spacing_m: float) -> np.ndarray:
        pts = self.body_points(spacing_m)
        c, s = math.cos(yaw), math.sin(yaw)
        rot = np.asarray([[c, -s], [s, c]], dtype=float)
        return pts @ rot.T + np.asarray([x, y], dtype=float)


@dataclasses.dataclass(frozen=True)
class SweptConfiguration:
    """One pose the robot passes through, with its progress along the route."""

    index: int
    x: float
    y: float
    yaw: float
    route_progress_m: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "index": self.index,
            "x": self.x,
            "y": self.y,
            "yaw_rad": self.yaw,
            "route_progress_m": self.route_progress_m,
        }


def resample_route(path: np.ndarray, step_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Uniform arc-length samples of a polyline, with each sample's progress."""
    pts = np.asarray(path, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"path must be (N, 2), got {pts.shape}")
    if pts.shape[0] < 2:
        return pts.copy(), np.zeros(pts.shape[0])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(s[-1])
    if total <= 0.0:
        return pts[:1].copy(), np.zeros(1)
    n = max(2, int(math.ceil(total / step_m)) + 1)
    targets = np.linspace(0.0, total, n)
    out = np.column_stack(
        [np.interp(targets, s, pts[:, 0]), np.interp(targets, s, pts[:, 1])]
    )
    return out, targets


def swept_configurations(
    path: np.ndarray,
    resolution: SweepResolution,
    *,
    start_yaw: float | None = None,
) -> list[SweptConfiguration]:
    """Every pose the swept footprint occupies, at the frozen resolution.

    Translation is sampled at ``route_step_m``. Heading is the route tangent,
    and where consecutive tangents differ by more than ``max_yaw_step_rad`` the
    turn is expanded into intermediate in-place configurations -- otherwise a
    corner would be swept as two poses with the arc between them unprobed, which
    is the "unsupported corner during a turn" case.
    """
    pts, progress = resample_route(path, resolution.route_step_m)
    if pts.shape[0] == 1:
        return [SweptConfiguration(0, float(pts[0, 0]), float(pts[0, 1]),
                                   float(start_yaw or 0.0), 0.0)]

    d = np.diff(pts, axis=0)
    tangents = np.arctan2(d[:, 1], d[:, 0])
    yaws = np.concatenate([tangents, tangents[-1:]])
    if start_yaw is not None:
        yaws[0] = start_yaw

    configs: list[SweptConfiguration] = []
    idx = 0
    for k in range(pts.shape[0]):
        x, y, s = float(pts[k, 0]), float(pts[k, 1]), float(progress[k])
        if k > 0:
            delta = _wrap(float(yaws[k]) - float(yaws[k - 1]))
            n_steps = int(math.ceil(abs(delta) / resolution.max_yaw_step_rad))
            for j in range(1, n_steps):
                configs.append(
                    SweptConfiguration(idx, x, y, _wrap(float(yaws[k - 1]) + delta * j / n_steps), s)
                )
                idx += 1
        configs.append(SweptConfiguration(idx, x, y, float(yaws[k]), s))
        idx += 1
    return configs


def _wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def heading_changes(path: np.ndarray, threshold_deg: float) -> tuple[int, list[float]]:
    """Count direction changes exceeding a threshold, on a decimated path.

    Decimation matters: consecutive samples of a smoothed path are nearly
    collinear, so per-sample angles measure planner noise rather than route
    structure. Turns accumulate until they exceed the threshold, so one sweeping
    corner counts once rather than as many small deltas.
    """
    pts, _ = resample_route(np.asarray(path, dtype=float), 0.5)
    if pts.shape[0] < 3:
        return 0, []
    d = np.diff(pts, axis=0)
    ang = np.arctan2(d[:, 1], d[:, 0])
    turns: list[float] = []
    acc = 0.0
    for k in range(1, len(ang)):
        delta = math.degrees(_wrap(float(ang[k]) - float(ang[k - 1])))
        if acc != 0.0 and (delta > 0) != (acc > 0):
            acc = delta  # direction reversed: start a fresh turn
        else:
            acc += delta
        if abs(acc) >= threshold_deg:
            turns.append(round(acc, 4))
            acc = 0.0
    return len(turns), turns
