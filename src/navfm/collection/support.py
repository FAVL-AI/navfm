"""G3, G4 and G6 — is the robot's whole footprint on solid ground?

One question, asked at three places: the start pose (G3), every configuration
along the swept route (G4), and the terminal pose (G6). They share an
implementation because they share a failure mode, and they stay separate gates
because passing one does not imply passing another.

**The footprint, never the centre.** A robot straddling the edge of a floor slab
has a supported centreline and an unsupported wheel. Testing the centre point
answers a different and much weaker question, so every check here enumerates the
footprint at the frozen resolution.

**G4 does not imply G6.** G4 sweeps the planned route; G6 asks about the pose
the robot actually finishes in. Goal tolerance, overshoot and the difference
between a planned terminal waypoint and a realised stop all live in that gap.
Deriving one from the other would mean the terminal pose was never tested.

**Support is not the absence of an obstacle.** The probe measures whether floor
exists beneath a point, at a height sampled just above the floor. A ray dropped
from a metre up returns the nearest hit, which in a furnished scene is a supply
cart or a handrail -- overhead clutter that says nothing about the ground. Read
as "unsupported", that conflates an obstacle with a hole, and obstacles are G5's
question.

The geometry source is injected as a :class:`SupportProbe`. The gates are then
pure with respect to Isaac: the same code runs against a PhysX scene query on
the execution machine and against synthetic geometry in the test suite, so the
controls that prove these gates can fail do not need a simulator.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Protocol

import numpy as np

from .footprint import Footprint, SweepResolution, swept_configurations
from .gates import GateKind, GateResult, GateStatus

__all__ = [
    "SupportProbe",
    "SupportSample",
    "evaluate_continuous_support",
    "evaluate_end_support",
    "evaluate_start_support",
    "footprint_support",
]


@dataclasses.dataclass(frozen=True)
class SupportSample:
    """What the probe found beneath one point."""

    x: float
    y: float

    #: True when solid, collidable ground was found within tolerance.
    supported: bool

    #: Signed height of the hit relative to the floor reference, if any.
    margin_m: float | None = None

    #: The collision prim that provided support, when the probe can name it.
    prim: str | None = None

    #: Why support was refused: NO_GROUND_HIT, HIT_OFF_FLOOR, or a probe-specific
    #: reason. Empty when supported.
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "xy": [self.x, self.y],
            "supported": self.supported,
            "margin_m": self.margin_m,
            "prim": self.prim,
            "reason": self.reason,
        }


class SupportProbe(Protocol):
    """Ground truth about whether a point is over solid ground."""

    def sample(self, x: float, y: float) -> SupportSample: ...


def footprint_support(
    probe: SupportProbe,
    footprint: Footprint,
    x: float,
    y: float,
    yaw: float,
    resolution: SweepResolution,
) -> tuple[bool, list[SupportSample], float | None]:
    """Probe the whole footprint at one pose.

    Returns ``(supported, unsupported_samples, min_margin_m)``. Every
    unsupported sample is returned rather than the first, because "the footprint
    overhangs by one probe" and "the footprint is over a void" are different
    situations and the caller should be able to tell them apart.
    """
    points = footprint.points(x, y, yaw, resolution.probe_spacing_m)
    unsupported: list[SupportSample] = []
    margins: list[float] = []
    for px, py in points:
        sample = probe.sample(float(px), float(py))
        if sample.margin_m is not None:
            margins.append(sample.margin_m)
        if not sample.supported:
            unsupported.append(sample)
    return (not unsupported), unsupported, (min(margins) if margins else None)


def _support_gate(
    name: str,
    probe: SupportProbe,
    footprint: Footprint,
    x: float,
    y: float,
    yaw: float,
    resolution: SweepResolution,
) -> GateResult:
    supported, unsupported, min_margin = footprint_support(
        probe, footprint, x, y, yaw, resolution
    )
    n_probes = int(footprint.points(x, y, yaw, resolution.probe_spacing_m).shape[0])
    detail: dict[str, Any] = {
        "pose": {"x": x, "y": y, "yaw_rad": yaw},
        "footprint_probe_count": n_probes,
        "probe_spacing_m": resolution.probe_spacing_m,
        "circumscribed_radius_m": footprint.circumscribed_radius_m,
        "min_support_margin_m": min_margin,
        "unsupported_probe_count": len(unsupported),
        "unsupported_samples": [s.to_dict() for s in unsupported[:8]],
        "support_prims": sorted({s.prim for s in unsupported if s.prim} or set()),
    }
    if supported:
        return GateResult(name, GateStatus.PASS, GateKind.PRECONDITION,
                          reason="entire footprint supported", detail=detail)
    reasons = sorted({s.reason for s in unsupported if s.reason})
    return GateResult(
        name, GateStatus.FAIL, GateKind.PRECONDITION,
        reason=(f"{len(unsupported)} of {n_probes} footprint probes unsupported "
                f"({', '.join(reasons) or 'unspecified'})"),
        detail=detail,
    )


def evaluate_start_support(
    probe: SupportProbe,
    footprint: Footprint,
    start: tuple[float, float],
    yaw: float,
    resolution: SweepResolution,
) -> GateResult:
    """G3 — the entire footprint is supported at the start pose."""
    return _support_gate("G3_START_SUPPORT", probe, footprint,
                         float(start[0]), float(start[1]), float(yaw), resolution)


def evaluate_end_support(
    probe: SupportProbe,
    footprint: Footprint,
    end: tuple[float, float],
    yaw: float,
    resolution: SweepResolution,
) -> GateResult:
    """G6 — the entire footprint is supported at the terminal pose.

    Deliberately not derived from G4. See the module docstring.
    """
    return _support_gate("G6_END_SUPPORT", probe, footprint,
                         float(end[0]), float(end[1]), float(yaw), resolution)


def evaluate_continuous_support(
    probe: SupportProbe,
    footprint: Footprint,
    path: np.ndarray,
    resolution: SweepResolution,
    *,
    start_yaw: float | None = None,
    max_recorded_failures: int = 8,
) -> GateResult:
    """G4 — the swept footprint stays supported for the whole route.

    Evaluates translation and heading change together: turns are expanded into
    intermediate in-place configurations by ``swept_configurations``, so a
    corner is probed through its arc rather than only at its endpoints. A robot
    that pivots over a slab edge is unsupported for part of the turn while both
    endpoints are fine.

    A single unsupported configuration FAILS. There is no averaging: the route
    is executed once, and the fraction of it that was safe is not the question.
    """
    configs = swept_configurations(np.asarray(path, dtype=float), resolution,
                                   start_yaw=start_yaw)
    failures: list[dict[str, Any]] = []
    min_margin: float | None = None
    first_failure: dict[str, Any] | None = None

    for config in configs:
        supported, unsupported, margin = footprint_support(
            probe, footprint, config.x, config.y, config.yaw, resolution
        )
        if margin is not None:
            min_margin = margin if min_margin is None else min(min_margin, margin)
        if not supported:
            record = {
                "configuration": config.to_dict(),
                "unsupported_probe_count": len(unsupported),
                "unsupported_samples": [s.to_dict() for s in unsupported[:4]],
                "prims": sorted({s.prim for s in unsupported if s.prim} or set()),
            }
            if first_failure is None:
                first_failure = record
            if len(failures) < max_recorded_failures:
                failures.append(record)

    detail: dict[str, Any] = {
        "configurations_evaluated": len(configs),
        "route_step_m": resolution.route_step_m,
        "max_yaw_step_rad": resolution.max_yaw_step_rad,
        "probe_spacing_m": resolution.probe_spacing_m,
        "min_support_margin_m": min_margin,
        "unsupported_configuration_count": len(failures),
        "first_unsupported_configuration": first_failure,
        "unsupported_configurations": failures,
        "recorded_failure_cap": max_recorded_failures,
    }
    if first_failure is None:
        return GateResult("G4_CONTINUOUS_ROUTE_SUPPORT", GateStatus.PASS,
                          GateKind.PRECONDITION,
                          reason=f"{len(configs)} configurations all supported",
                          detail=detail)
    progress = first_failure["configuration"]["route_progress_m"]
    return GateResult(
        "G4_CONTINUOUS_ROUTE_SUPPORT", GateStatus.FAIL, GateKind.PRECONDITION,
        reason=(f"footprint unsupported at route progress {progress:.3f} m "
                f"(first of {len(failures)} recorded)"),
        detail=detail,
    )
