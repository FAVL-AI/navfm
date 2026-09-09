"""G5 — can the swept robot body traverse the route without meeting geometry?

Distinct from G4 in what it asks and in what it queries. G4 asks whether ground
exists beneath the footprint; G5 asks whether anything solid occupies the space
the body must pass through. A hole and a bollard are different failures and one
gate cannot see both.

**Not read from the occupancy grid.** The grid is what planned the route, so
asking it to certify the route is circular -- the same defect that made
``blocking_coverage_fraction = 1.0`` uninformative about the planner's blind
band. G5 queries the scene independently, so geometry the map missed can still
be found. The map-derived reading is recorded alongside for comparison and is
explicitly not the gate; the two disagreeing is a finding, not a tie to break in
the map's favour.

**Two clearances, and they are not the same number.** ``min_clearance_m = 0.35``
is the *planner's* configuration: it biases start/goal sampling away from walls
on the inflated grid. The inflated grid has already removed
``footprint_radius``, so requiring 0.35 m on top of it would demand
``footprint_radius + 0.35`` of real space and make ordinary doorways
impassable. The gate criterion is therefore clearance to real geometry of at
least the circumscribed footprint radius, and the planner's parameter is
preserved unchanged rather than repurposed. Both are recorded so a reader can
see which one each claim rests on.

**Probe heights must span the robot's collision body, not its chassis.** The
simulated wheel colliders reach down to ground contact, so geometry at 0.05 m --
wall skirting, thresholds, cable trays -- is inside the collision band even
though it passes under the chassis. Sampling only at chassis height would report
clearance for obstacles the wheels would strike.

F-TWIN-1 is open: box colliders in the twin are squared. This gate may support
route-clearance acceptance, because the planner inflates by a footprint radius
exceeding the true circumscribed chassis radius. It may not support detailed
contact-physics claims.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Protocol

import numpy as np

from .footprint import Footprint, SweepResolution, swept_configurations
from .gates import GateKind, GateResult, GateStatus

__all__ = [
    "ClearanceProbe",
    "ClearanceSample",
    "evaluate_obstacle_clearance",
]


@dataclasses.dataclass(frozen=True)
class ClearanceSample:
    """Nearest blocking geometry around one point."""

    x: float
    y: float

    #: Horizontal distance to the nearest blocking geometry, in metres.
    distance_m: float

    #: Probe height at which the nearest hit was found, if the probe reports it.
    height_m: float | None = None

    #: Bearing of the nearest hit, degrees, if reported.
    bearing_deg: float | None = None

    prim: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "xy": [self.x, self.y],
            "distance_m": self.distance_m,
            "height_m": self.height_m,
            "bearing_deg": self.bearing_deg,
            "prim": self.prim,
        }


class ClearanceProbe(Protocol):
    """Distance from a point to the nearest blocking collision geometry."""

    def sample(self, x: float, y: float) -> ClearanceSample: ...


def evaluate_obstacle_clearance(
    probe: ClearanceProbe,
    footprint: Footprint,
    path: np.ndarray,
    resolution: SweepResolution,
    *,
    start_yaw: float | None = None,
    planner_min_clearance_m: float = 0.35,
    map_derived_clearance: np.ndarray | None = None,
    max_recorded_failures: int = 8,
) -> GateResult:
    """G5 — the swept body does not intersect blocking geometry.

    The criterion is ``min_distance >= footprint.circumscribed_radius_m`` at
    every swept configuration. Because the probe measures from the configuration
    centre, comparing against the circumscribed radius is exactly the
    footprint-versus-centreline distinction: an obstacle that the centreline
    misses but the body would strike sits closer than the radius and fails.

    ``planner_min_clearance_m`` is recorded, not applied. See the module
    docstring for why the two numbers must not be conflated.
    """
    configs = swept_configurations(np.asarray(path, dtype=float), resolution,
                                   start_yaw=start_yaw)
    required = footprint.circumscribed_radius_m

    worst: ClearanceSample | None = None
    worst_progress: float | None = None
    failures: list[dict[str, Any]] = []
    first_failure: dict[str, Any] | None = None

    for config in configs:
        sample = probe.sample(config.x, config.y)
        if worst is None or sample.distance_m < worst.distance_m:
            worst = sample
            worst_progress = config.route_progress_m
        if sample.distance_m < required:
            record = {
                "configuration": config.to_dict(),
                "sample": sample.to_dict(),
                "shortfall_m": required - sample.distance_m,
            }
            if first_failure is None:
                first_failure = record
            if len(failures) < max_recorded_failures:
                failures.append(record)

    detail: dict[str, Any] = {
        "criterion": "min horizontal distance to blocking geometry >= circumscribed footprint radius",
        "required_clearance_m": required,
        "configurations_evaluated": len(configs),
        "min_clearance_m": (worst.distance_m if worst else None),
        "min_clearance_at_route_progress_m": worst_progress,
        "closest_obstacle": (worst.to_dict() if worst else None),
        "violating_configuration_count": len(failures),
        "first_violation": first_failure,
        "violations": failures,
        "planner_min_clearance_m": planner_min_clearance_m,
        "planner_parameter_is_recorded_not_applied": (
            "min_clearance_m biases the planner's start/goal sampling on the inflated "
            "grid; the inflated grid already removed footprint_radius, so applying it "
            "again here would demand footprint_radius + 0.35 m of real space and make "
            "ordinary doorways impassable"),
        "f_twin_1": ("OPEN -- route-clearance acceptance only; no contact-physics claim "
                     "rests on this gate"),
    }
    if map_derived_clearance is not None:
        arr = np.asarray(map_derived_clearance, dtype=float)
        detail["map_derived_min_clearance_m"] = (float(arr.min()) if arr.size else None)
        detail["map_derived_reading_is_not_the_gate"] = (
            "produced by the same grid that planned the route; recorded for comparison. "
            "A disagreement between this and the measured clearance is a finding "
            "(see gates/failures/F-G5-1.md), not a tie to resolve in the map's favour")

    if first_failure is None:
        return GateResult("G5_OBSTACLE_CLEARANCE", GateStatus.PASS, GateKind.PRECONDITION,
                          reason=(f"minimum clearance "
                                  f"{worst.distance_m:.4f} m >= {required:.4f} m required"
                                  if worst else "no configurations to evaluate"),
                          detail=detail)
    return GateResult(
        "G5_OBSTACLE_CLEARANCE", GateStatus.FAIL, GateKind.PRECONDITION,
        reason=(f"clearance {first_failure['sample']['distance_m']:.4f} m < "
                f"{required:.4f} m required, at route progress "
                f"{first_failure['configuration']['route_progress_m']:.3f} m"),
        detail=detail,
    )
