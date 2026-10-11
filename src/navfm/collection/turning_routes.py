"""TURNING_ROUTE_POPULATION_V1 — multi-leg routes with spatially separated turns.

The question this population exists to answer: does a route whose turns are
*spatially separated* produce >= 3 distinct realised turn episodes under the
UNCHANGED kinematic pure-pursuit controller?

`run_00000` showed three planned corners realised as one 172 degree sweep. That
could be the route (corners too close for the controller to settle between them)
or the controller (never settles regardless). This changes route structure only,
so the two can be told apart.

**The generator never sees G10.** It samples waypoints, plans per-leg, and emits
a route. Nothing in this module imports the turn metric, reads a gate result, or
retries on failure -- "keep adding waypoints until G10 passes" would bake the
evaluation criterion into the population and make any subsequent pass
uninterpretable. Control H holds this structurally: the output is byte-identical
whether or not a G10 evaluator exists.

**Natural structure, not manufactured zig-zags.** Waypoints must be separated by
at least a declared travelled distance, so a turn has room to be entered,
executed and left. A generator free to place waypoints arbitrarily close could
satisfy a turn count with a sawtooth no robot would drive and no dataset would
want.
"""

from __future__ import annotations

import dataclasses
import math
from itertools import pairwise
from typing import Any

import numpy as np

from ..planning import OccupancyGrid, PlannerError, astar, sample_free_pose, smooth_path

__all__ = [
    "TURNING_ROUTE_GENERATOR_V1",
    "TurningRouteCandidate",
    "TurningRouteGenerator",
    "sample_turning_route",
]


@dataclasses.dataclass(frozen=True)
class TurningRouteGenerator:
    """Frozen generator parameters. None derived from any collected trajectory."""

    #: Legs between anchors. Three legs give two interior turns; four give three,
    #: which is the minimum the frozen G10 contract requires.
    legs: int = 4

    #: Minimum straight-line separation between consecutive anchors. Derived from
    #: the frozen G10 separator: a realised turn episode is separated by a
    #: low-curvature run of 1.0 m, and an anchor must additionally allow the
    #: controller to enter and leave the turn. Three separator lengths, 3.0 m,
    #: is the smallest spacing that leaves a separator with room either side.
    min_anchor_separation_m: float = 3.0

    #: Ceiling so a route stays within the frozen max_path_m once legs are summed.
    max_anchor_separation_m: float = 9.0

    #: Anchors must not be collinear, or the "turn" is not a turn. The bound is
    #: the frozen qualifying turn magnitude itself: an anchor that bends the
    #: route by less than 30 degrees cannot produce a qualifying event, so
    #: emitting it would be emitting a turn the contract already rejects.
    min_anchor_turn_deg: float = 30.0

    #: Upper bound on an anchor bend. A bend approaching 180 degrees is the route
    #: REVERSING along the way it came, not transitioning between regions, and
    #: nothing else in the spacing rules forbids it: a corridor control exposed a
    #: generator happily emitting 3 m out, 3 m back. A doubling-back route would
    #: satisfy a turn count while being exactly the manufactured zig-zag this
    #: population exists to avoid. 135 degrees admits an acute corner between
    #: corridors and excludes a reversal.
    max_anchor_turn_deg: float = 135.0

    min_clearance_m: float = 0.35
    max_tries_per_anchor: int = 60

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["parameter_provenance"] = {
            "legs": "4 legs give 3 interior turns, the frozen G10 minimum",
            "min_anchor_separation_m": ("3 x the frozen 1.0 m G10 separator, so a separator run "
                                        "has room either side of it"),
            "max_anchor_separation_m": "keeps summed legs within the frozen max_path_m",
            "min_anchor_turn_deg": ("the frozen turn magnitude from the collection contract; a "
                                    "smaller bend cannot produce an admissible event"),
            "max_anchor_turn_deg": ("135 degrees. A bend approaching 180 is a reversal along the "
                                    "same corridor rather than a region transition, and the "
                                    "spacing rules alone do not forbid it."),
            "min_clearance_m": "unchanged from the collection contract",
            "derived_from_run_00000": False,
        }
        return d


TURNING_ROUTE_GENERATOR_V1 = TurningRouteGenerator()


@dataclasses.dataclass
class TurningRouteCandidate:
    """One multi-leg route and the anchors that shaped it."""

    anchors: np.ndarray
    path: np.ndarray
    start_yaw: float
    anchor_turns_deg: list[float]

    @property
    def start(self) -> np.ndarray:
        return self.path[0]

    @property
    def goal(self) -> np.ndarray:
        return self.path[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchors": [[round(float(a[0]), 4), round(float(a[1]), 4)] for a in self.anchors],
            "anchor_turns_deg": [round(t, 3) for t in self.anchor_turns_deg],
            "start_pose": [float(self.start[0]), float(self.start[1]), float(self.start_yaw)],
            "goal_pose": [float(self.goal[0]), float(self.goal[1])],
            "path_points": int(self.path.shape[0]),
            "path_length_m": float(np.linalg.norm(np.diff(self.path, axis=0), axis=1).sum()),
        }


def _bend_deg(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Signed heading change at ``b`` on the polyline a -> b -> c."""
    v1 = math.atan2(b[1] - a[1], b[0] - a[0])
    v2 = math.atan2(c[1] - b[1], c[0] - b[0])
    return math.degrees(math.atan2(math.sin(v2 - v1), math.cos(v2 - v1)))


def sample_turning_route(
    grid: OccupancyGrid,
    rng: np.random.Generator,
    *,
    generator: TurningRouteGenerator = TURNING_ROUTE_GENERATOR_V1,
    clearance_map: np.ndarray | None = None,
) -> TurningRouteCandidate:
    """Sample a multi-leg route whose anchors are separated and non-collinear.

    Raises :class:`PlannerError` when the scene cannot supply such a route within
    the frozen try budget. It does NOT relax its constraints and retry: a
    generator that loosened its own rules until it succeeded would produce a
    population whose structure depended on the scene's difficulty rather than on
    the declaration.
    """
    if clearance_map is None:
        clearance_map = grid.clearance()

    anchors: list[np.ndarray] = []
    start_yaw = 0.0
    for index in range(generator.legs + 1):
        placed = False
        for _ in range(generator.max_tries_per_anchor):
            point, yaw = sample_free_pose(grid, rng,
                                          min_clearance_m=generator.min_clearance_m,
                                          clearance_map=clearance_map)
            if index == 0:
                anchors.append(point)
                start_yaw = float(yaw)
                placed = True
                break
            gap = float(np.linalg.norm(point - anchors[-1]))
            if not (generator.min_anchor_separation_m <= gap
                    <= generator.max_anchor_separation_m):
                continue
            if len(anchors) >= 2:
                bend = _bend_deg(anchors[-2], anchors[-1], point)
                if not (generator.min_anchor_turn_deg <= abs(bend)
                        <= generator.max_anchor_turn_deg):
                    continue
            anchors.append(point)
            placed = True
            break
        if not placed:
            raise PlannerError(
                f"could not place anchor {index} under the frozen spacing and bend rules")

    # Per-leg planning and per-leg smoothing. Global smoothing would string-pull
    # straight through the anchors and remove the very structure the population
    # exists to create, which is why the anchors are mandatory and smoothing is
    # confined within a leg.
    legs: list[np.ndarray] = []
    for a, b in pairwise(anchors):
        # astar takes WORLD coordinates and returns a world path. An earlier
        # draft passed cells, which it then converted again -- the same class of
        # mistake as H-REPLAN-1, where a world pose was rounded into a cell.
        leg = astar(grid, (float(a[0]), float(a[1])), (float(b[0]), float(b[1])))
        if leg is None or len(leg) == 0:
            raise PlannerError("no path between consecutive anchors")
        legs.append(smooth_path(grid, np.asarray(leg, dtype=float)))

    path = legs[0]
    for leg in legs[1:]:
        path = np.vstack([path, leg[1:]])

    turns = [_bend_deg(anchors[i - 1], anchors[i], anchors[i + 1])
             for i in range(1, len(anchors) - 1)]
    return TurningRouteCandidate(anchors=np.array(anchors), path=path,
                                 start_yaw=start_yaw, anchor_turns_deg=turns)
