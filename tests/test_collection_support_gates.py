"""G3, G4, G5, G6 — every gate proved in both directions on synthetic geometry.

The probes are injected, so these controls need no simulator. That is the point:
a gate whose failure mode can only be demonstrated on the Isaac machine is a
gate whose failure mode is demonstrated rarely.

Each gate's defining negative control is the case where a centre-only test would
pass and the footprint test must not: the robot centred on support with its rim
over the edge.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from navfm.collection.clearance import ClearanceSample, evaluate_obstacle_clearance
from navfm.collection.footprint import (
    CircularFootprint,
    RectangularFootprint,
    SweepResolution,
)
from navfm.collection.gates import GateKind, GateStatus
from navfm.collection.support import (
    SupportSample,
    evaluate_continuous_support,
    evaluate_end_support,
    evaluate_start_support,
)

RADIUS = 0.24
FOOTPRINT = CircularFootprint(RADIUS)
RES = SweepResolution.derive(RADIUS)


# ---------------------------------------------------------------- probes ----
@dataclasses.dataclass
class HalfPlaneFloor:
    """Floor for x <= edge_x, void beyond. The slab-edge case."""

    edge_x: float = 0.0

    def sample(self, x: float, y: float) -> SupportSample:
        if x <= self.edge_x:
            return SupportSample(x, y, True, margin_m=0.0, prim="/World/Floor")
        return SupportSample(x, y, False, reason="NO_GROUND_HIT")


@dataclasses.dataclass
class FloorWithGap:
    """Continuous floor with one unsupported band across the route."""

    gap_start: float
    gap_end: float

    def sample(self, x: float, y: float) -> SupportSample:
        if self.gap_start <= x <= self.gap_end:
            return SupportSample(x, y, False, reason="NO_GROUND_HIT")
        return SupportSample(x, y, True, margin_m=0.0, prim="/World/Floor")


@dataclasses.dataclass
class FloorWithVoidCorner:
    """Floor everywhere except a quadrant the route rounds."""

    corner_x: float
    corner_y: float

    def sample(self, x: float, y: float) -> SupportSample:
        if x >= self.corner_x and y >= self.corner_y:
            return SupportSample(x, y, False, reason="NO_GROUND_HIT")
        return SupportSample(x, y, True, margin_m=0.0, prim="/World/Floor")


class DiagonalVoid:
    """A void reachable only at intermediate headings.

    An annular wedge between 30 and 60 degrees of bearing from the origin. A long
    thin body pointing along x or along y misses it entirely; the same body
    pivoting between those headings sweeps straight through it. This isolates the
    turn: the failure exists at no endpoint of the route, only in the arc
    ``swept_configurations`` expands.
    """

    def sample(self, x: float, y: float) -> SupportSample:
        r = math.hypot(x, y)
        bearing = math.degrees(math.atan2(y, x))
        if 0.15 <= r <= 0.30 and 30.0 <= bearing <= 60.0:
            return SupportSample(x, y, False, reason="NO_GROUND_HIT")
        return SupportSample(x, y, True, margin_m=0.0, prim="/World/Floor")


class NoCollider:
    def sample(self, x: float, y: float) -> SupportSample:
        return SupportSample(x, y, False, reason="NO_SUPPORT_COLLIDER")


class SolidFloor:
    def sample(self, x: float, y: float) -> SupportSample:
        return SupportSample(x, y, True, margin_m=0.0, prim="/World/Floor")


@dataclasses.dataclass
class PointObstacle:
    """A single blocking column; clearance is the planar distance to it."""

    ox: float
    oy: float
    free: float = 5.0

    def sample(self, x: float, y: float) -> ClearanceSample:
        d = math.hypot(x - self.ox, y - self.oy)
        return ClearanceSample(x, y, min(d, self.free), height_m=0.05,
                               prim="/World/Obstacle")


class OpenSpace:
    def sample(self, x: float, y: float) -> ClearanceSample:
        return ClearanceSample(x, y, 5.0)


STRAIGHT = np.array([[-3.0, 0.0], [3.0, 0.0]])


# ------------------------------------------------------------------- G3 ----
class TestG3StartSupport:
    def test_a_fully_supported_start_passes(self) -> None:
        r = evaluate_start_support(SolidFloor(), FOOTPRINT, (0.0, 0.0), 0.0, RES)
        assert r.status is GateStatus.PASS
        assert r.kind is GateKind.PRECONDITION
        assert r.admits

    def test_a_start_partly_over_an_edge_fails(self) -> None:
        r = evaluate_start_support(HalfPlaneFloor(edge_x=0.0), FOOTPRINT,
                                   (0.10, 0.0), 0.0, RES)
        assert r.status is GateStatus.FAIL
        assert r.detail["unsupported_probe_count"] > 0

    def test_a_centred_start_whose_footprint_overhangs_fails(self) -> None:
        """The defining control: a centre-only test would pass this."""
        probe = HalfPlaneFloor(edge_x=0.0)
        assert probe.sample(-0.01, 0.0).supported, "the centre itself is supported"
        r = evaluate_start_support(probe, FOOTPRINT, (-0.01, 0.0), 0.0, RES)
        assert r.status is GateStatus.FAIL, "footprint overhang must fail despite a supported centre"

    def test_no_support_collider_fails(self) -> None:
        r = evaluate_start_support(NoCollider(), FOOTPRINT, (0.0, 0.0), 0.0, RES)
        assert r.status is GateStatus.FAIL
        assert "NO_SUPPORT_COLLIDER" in r.reason

    def test_the_failure_records_where_and_why(self) -> None:
        r = evaluate_start_support(HalfPlaneFloor(0.0), FOOTPRINT, (0.10, 0.0), 0.0, RES)
        assert r.detail["unsupported_samples"], "an unsupported region must be recorded"
        assert r.detail["footprint_probe_count"] > 1
        assert r.detail["probe_spacing_m"] == RES.probe_spacing_m


# ------------------------------------------------------------------- G4 ----
class TestG4ContinuousSupport:
    def test_a_continuous_supported_corridor_passes(self) -> None:
        r = evaluate_continuous_support(SolidFloor(), FOOTPRINT, STRAIGHT, RES)
        assert r.status is GateStatus.PASS
        assert r.detail["configurations_evaluated"] > 1

    def test_a_small_unsupported_gap_fails(self) -> None:
        """One occupancy cell wide -- the smallest hazard the resolution claims."""
        gap = FloorWithGap(gap_start=0.50, gap_end=0.60)
        r = evaluate_continuous_support(gap, FOOTPRINT, STRAIGHT, RES)
        assert r.status is GateStatus.FAIL
        assert r.detail["first_unsupported_configuration"] is not None

    def test_an_unsupported_region_at_a_corner_fails(self) -> None:
        route = np.array([[-2.0, -1.0], [0.0, -1.0], [0.0, 2.0]])
        r = evaluate_continuous_support(FloorWithVoidCorner(0.10, 0.30), FOOTPRINT,
                                        route, RES)
        assert r.status is GateStatus.FAIL

    def test_a_void_swept_only_during_a_turn_fails(self) -> None:
        """The turn-specific control, and it needs a yaw-dependent footprint.

        A disc cannot express this case at all: its occupied set does not depend
        on heading, so for the production footprint a turn adds no coverage that
        translation had not already probed. Asserting a turn-only failure with a
        disc would be asserting something the geometry makes impossible, which is
        how a control ends up unable to fail. The long thin body makes the arc
        matter, and both endpoint headings are proved clear first so the failure
        can only have come from the expansion.
        """
        rect = RectangularFootprint(length_m=0.60, width_m=0.10)
        probe = DiagonalVoid()
        route = np.array([[-2.0, 0.0], [0.0, 0.0], [0.0, 2.0]])

        at_zero = evaluate_start_support(probe, rect, (0.0, 0.0), 0.0, RES)
        at_ninety = evaluate_start_support(probe, rect, (0.0, 0.0), math.pi / 2, RES)
        assert at_zero.status is GateStatus.PASS, "the incoming heading must be clear"
        assert at_ninety.status is GateStatus.PASS, "the outgoing heading must be clear"

        r = evaluate_continuous_support(probe, rect, route, RES, start_yaw=0.0)
        assert r.status is GateStatus.FAIL, (
            "the void is reachable only at intermediate headings, so a sweep that "
            "probed corner endpoints alone would miss it"
        )

    def test_a_distant_unsupported_floor_leaves_the_result_unchanged(self) -> None:
        near = evaluate_continuous_support(SolidFloor(), FOOTPRINT, STRAIGHT, RES)
        far = evaluate_continuous_support(HalfPlaneFloor(edge_x=500.0), FOOTPRINT,
                                          STRAIGHT, RES)
        assert near.status is far.status is GateStatus.PASS

    def test_the_first_failing_configuration_and_progress_are_recorded(self) -> None:
        r = evaluate_continuous_support(FloorWithGap(0.5, 0.6), FOOTPRINT, STRAIGHT, RES)
        first = r.detail["first_unsupported_configuration"]
        assert "route_progress_m" in first["configuration"]
        assert first["unsupported_probe_count"] >= 1

    def test_one_unsupported_configuration_is_enough_to_fail(self) -> None:
        """No averaging: the route is executed once."""
        r = evaluate_continuous_support(FloorWithGap(0.50, 0.51), FOOTPRINT, STRAIGHT, RES)
        assert r.status is GateStatus.FAIL
        assert r.detail["unsupported_configuration_count"] >= 1


# ------------------------------------------------------------------- G6 ----
class TestG6EndSupport:
    def test_a_supported_end_passes(self) -> None:
        r = evaluate_end_support(SolidFloor(), FOOTPRINT, (3.0, 0.0), 0.0, RES)
        assert r.status is GateStatus.PASS

    def test_a_partial_overhang_at_the_end_fails(self) -> None:
        r = evaluate_end_support(HalfPlaneFloor(edge_x=3.0), FOOTPRINT,
                                 (3.05, 0.0), 0.0, RES)
        assert r.status is GateStatus.FAIL

    def test_an_unsupported_end_fails(self) -> None:
        r = evaluate_end_support(NoCollider(), FOOTPRINT, (3.0, 0.0), 0.0, RES)
        assert r.status is GateStatus.FAIL

    def test_g4_passing_does_not_imply_g6(self) -> None:
        """The gap G6 exists to cover: a clean route ending over a void.

        The route stops short of the edge, so every swept configuration is
        supported, while the realised terminal pose is past it.
        """
        probe = HalfPlaneFloor(edge_x=2.0)
        route = np.array([[-1.0, 0.0], [1.70, 0.0]])
        g4 = evaluate_continuous_support(probe, FOOTPRINT, route, RES)
        g6 = evaluate_end_support(probe, FOOTPRINT, (2.20, 0.0), 0.0, RES)
        assert g4.status is GateStatus.PASS
        assert g6.status is GateStatus.FAIL, "G6 must be able to fail where G4 passed"


# ------------------------------------------------------------------- G5 ----
class TestG5ObstacleClearance:
    def test_a_clear_route_passes(self) -> None:
        r = evaluate_obstacle_clearance(OpenSpace(), FOOTPRINT, STRAIGHT, RES)
        assert r.status is GateStatus.PASS

    def test_an_obstacle_on_the_centreline_fails(self) -> None:
        r = evaluate_obstacle_clearance(PointObstacle(0.0, 0.0), FOOTPRINT, STRAIGHT, RES)
        assert r.status is GateStatus.FAIL
        assert r.detail["min_clearance_m"] < RADIUS

    def test_an_obstacle_the_centreline_misses_but_the_footprint_hits_fails(self) -> None:
        """The defining control: offset beyond the centreline, inside the body."""
        offset = RADIUS * 0.5
        obstacle = PointObstacle(0.0, offset)
        assert offset > 0.0, "the obstacle is not on the centreline"
        r = evaluate_obstacle_clearance(obstacle, FOOTPRINT, STRAIGHT, RES)
        assert r.status is GateStatus.FAIL, (
            "an obstacle inside the swept body must fail even though no route "
            "sample point coincides with it"
        )

    def test_an_obstacle_outside_the_swept_body_passes(self) -> None:
        r = evaluate_obstacle_clearance(PointObstacle(0.0, 3.0), FOOTPRINT, STRAIGHT, RES)
        assert r.status is GateStatus.PASS

    def test_the_criterion_is_the_circumscribed_radius_not_the_planner_parameter(self) -> None:
        """0.35 m is the planner's sampling bias, not the gate. Recorded, not applied."""
        obstacle = PointObstacle(0.0, 0.30)   # 0.30 m: > radius 0.24, < planner 0.35
        r = evaluate_obstacle_clearance(obstacle, FOOTPRINT, STRAIGHT, RES,
                                        planner_min_clearance_m=0.35)
        assert r.status is GateStatus.PASS, (
            "applying 0.35 m here would demand footprint_radius + 0.35 m of real space"
        )
        assert r.detail["planner_min_clearance_m"] == 0.35
        assert r.detail["required_clearance_m"] == pytest.approx(RADIUS)

    def test_the_closest_obstacle_and_progress_are_recorded(self) -> None:
        r = evaluate_obstacle_clearance(PointObstacle(1.0, 0.0), FOOTPRINT, STRAIGHT, RES)
        assert r.detail["closest_obstacle"]["prim"] == "/World/Obstacle"
        assert r.detail["min_clearance_at_route_progress_m"] is not None
        assert r.detail["first_violation"] is not None

    def test_the_map_derived_reading_is_recorded_but_labelled_as_not_the_gate(self) -> None:
        r = evaluate_obstacle_clearance(OpenSpace(), FOOTPRINT, STRAIGHT, RES,
                                        map_derived_clearance=np.array([0.1, 0.2]))
        assert r.detail["map_derived_min_clearance_m"] == pytest.approx(0.1)
        note = r.detail["map_derived_reading_is_not_the_gate"]
        assert "same grid that planned the route" in note
        assert "not a tie to resolve in the map's favour" in note


class TestGatesConsumeHeading:
    def test_support_uses_yaw_for_a_yaw_dependent_footprint(self) -> None:
        """Proves heading reaches the probe, which a disc-only suite cannot show."""
        rect = RectangularFootprint(length_m=0.60, width_m=0.10)
        probe = HalfPlaneFloor(edge_x=0.20)
        along = evaluate_start_support(probe, rect, (0.0, 0.0), math.pi / 2, RES)
        across = evaluate_start_support(probe, rect, (0.0, 0.0), 0.0, RES)
        assert along.status is GateStatus.PASS
        assert across.status is GateStatus.FAIL
