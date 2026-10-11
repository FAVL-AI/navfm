"""Planner inflation, and the reconciliation of three clearance quantities.

Two things are established here, both analytically and both independent of any
simulator.

*Inflation is validated on its own*, separately from rasterisation. The
temptation when a map under-reports obstacles is to enlarge the inflation until
routes stop colliding. That hides a rasterisation defect behind a safety margin
and makes the map's error invisible, so inflation is checked against geometry
whose forbidden region can be derived by hand.

*The three clearances are reconciled before they are compared.* The original
F-G5 report read "planner 0.4 m, PhysX 0.0003 m", which invites the conclusion
that an instrument is broken. They are different estimands. Compared without
conversion they differ by roughly an inflation radius plus a footprint radius
whether or not anything is wrong.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from navfm.collection.clearance_estimands import (
    ClearanceComparison,
    ClearanceEstimands,
    analytic_clearance_to_box,
    chamfer_distance_cells,
    expected_inflated_cells,
    physx_clearance_to_surface,
    planner_clearance_to_surface,
)
from navfm.planning import OccupancyGrid

RES = 0.10
FOOTPRINT = 0.24
#: OccupancyGrid.inflate uses ceil(radius / resolution) cells.
INFLATION_CELLS = math.ceil(FOOTPRINT / RES)          # 3
INFLATION_M = INFLATION_CELLS * RES                    # 0.30


class TestInflationMatchesAnIndependentDerivation:
    """The repository's inflate() against a separately written expectation."""

    def grid_with(self, occupied: set[tuple[int, int]], shape=(21, 21)) -> OccupancyGrid:
        g = np.zeros(shape, dtype=bool)
        for r, c in occupied:
            g[r, c] = True
        return OccupancyGrid(g, RES, (0.0, 0.0))

    def measured(self, occupied: set[tuple[int, int]], shape=(21, 21)) -> set[tuple[int, int]]:
        inflated = self.grid_with(occupied, shape).inflate(FOOTPRINT)
        rows, cols = np.nonzero(inflated.grid)
        return {(int(r), int(c)) for r, c in zip(rows, cols, strict=True)}

    def test_fixture_B_isolated_box_obstacle(self) -> None:
        occ = {(10, 10)}
        assert self.measured(occ) == expected_inflated_cells(occ, FOOTPRINT, RES, (21, 21))

    def test_fixture_A_planar_wall(self) -> None:
        occ = {(r, 10) for r in range(21)}
        assert self.measured(occ) == expected_inflated_cells(occ, FOOTPRINT, RES, (21, 21))

    def test_fixture_C_thin_wall(self) -> None:
        occ = {(r, 10) for r in range(5, 16)}
        assert self.measured(occ) == expected_inflated_cells(occ, FOOTPRINT, RES, (21, 21))

    def test_fixture_D_corner(self) -> None:
        occ = {(10, c) for c in range(10, 21)} | {(r, 10) for r in range(10, 21)}
        assert self.measured(occ) == expected_inflated_cells(occ, FOOTPRINT, RES, (21, 21))

    def test_inflation_uses_ceil_so_it_is_never_smaller_than_the_footprint(self) -> None:
        """3 cells = 0.30 m against a 0.24 m radius. Conservative, and required."""
        assert INFLATION_CELLS * RES >= FOOTPRINT
        assert INFLATION_CELLS == 3

    def test_a_free_centre_cell_is_at_least_the_footprint_from_any_obstacle(self) -> None:
        """The property inflation exists to provide."""
        occ = {(10, 10)}
        forbidden = self.measured(occ)
        for r in range(21):
            for c in range(21):
                if (r, c) in forbidden:
                    continue
                assert math.hypot(r - 10, c - 10) * RES >= FOOTPRINT

    def test_inflation_is_not_a_substitute_for_rasterisation(self) -> None:
        """An obstacle absent from the base map is absent after inflation too.

        Enlarging inflation cannot recover geometry the rasteriser never saw,
        which is why the map repair could not be replaced by a bigger margin.
        """
        missed = self.measured(set())
        assert missed == set()


class TestClearanceEstimandsAreDeclaredBeforeComparison:
    def test_the_three_definitions_are_distinct(self) -> None:
        e = ClearanceEstimands()
        assert len({e.analytic, e.planner, e.physx}) == 3

    def test_physx_is_centre_to_surface_and_needs_the_footprint_removed(self) -> None:
        assert physx_clearance_to_surface(0.50, FOOTPRINT) == pytest.approx(0.26)

    def test_planner_needs_inflation_added_back_and_footprint_removed(self) -> None:
        # 1 cell from an inflated obstacle, inflation 0.30, footprint 0.24
        assert planner_clearance_to_surface(1.0, RES, INFLATION_M, FOOTPRINT) == pytest.approx(0.16)

    def test_comparing_raw_numbers_manufactures_a_discrepancy(self) -> None:
        """The reading error at the heart of the original F-G5 report.

        A robot 0.50 m (centre-to-surface) from a wall, correctly represented.
        Raw planner cells and raw PhysX metres look wildly different; converted,
        they agree.
        """
        raw_physx = 0.50
        raw_planner_cells = 1.0
        assert abs(raw_planner_cells - raw_physx) > 0.4, "raw values look incompatible"
        a = physx_clearance_to_surface(raw_physx, FOOTPRINT)
        b = planner_clearance_to_surface(raw_planner_cells, RES, INFLATION_M, FOOTPRINT)
        assert abs(a - b) <= RES, "converted values agree within one cell"


class TestFourThresholdDistances:
    """Well outside, exactly at, just inside, just outside the G5 threshold.

    The G5 criterion is analytic clearance >= 0, i.e. the footprint does not
    touch the obstacle. The threshold distance is therefore centre-to-surface
    equal to the footprint radius.
    """

    WALL = (1.0, -5.0, 5.0, 5.0)   # min_x, min_y, max_x, max_y

    def case(self, centre_to_surface: float, label: str) -> ClearanceComparison:
        cx = self.WALL[0] - centre_to_surface
        analytic = analytic_clearance_to_box((cx, 0.0), self.WALL, FOOTPRINT)
        # Base raster: wall cells are those whose area meets the wall.
        shape = (3, 80)
        blocked = np.zeros(shape, dtype=bool)
        for c in range(shape[1]):
            if 0.0 + c * RES + RES / 2 > self.WALL[0]:
                blocked[:, c] = True
        inflated = OccupancyGrid(blocked, RES, (0.0, 0.0)).inflate(FOOTPRINT)
        col = int(round(cx / RES))
        planner_cells = chamfer_distance_cells(inflated.grid, (1, col))
        return ClearanceComparison(
            label=label, analytic_m=analytic,
            planner_raw_cells=planner_cells,
            planner_converted_m=planner_clearance_to_surface(
                planner_cells, RES, INFLATION_M, FOOTPRINT),
            physx_raw_m=centre_to_surface,
            physx_converted_m=physx_clearance_to_surface(centre_to_surface, FOOTPRINT),
            resolution_m=RES)

    def test_well_outside_the_threshold_passes(self) -> None:
        c = self.case(1.00, "well_outside")
        assert c.analytic_m == pytest.approx(0.76)
        assert c.physx_agrees
        assert c.analytic_m > 0

    def test_exactly_at_the_threshold_is_zero_not_negative(self) -> None:
        c = self.case(FOOTPRINT, "exactly_at")
        assert c.analytic_m == pytest.approx(0.0, abs=1e-9)
        assert c.physx_agrees

    def test_just_inside_the_threshold_fails(self) -> None:
        c = self.case(FOOTPRINT - 0.001, "just_inside")
        assert c.analytic_m < 0, "the footprint overlaps the wall"
        assert c.physx_agrees

    def test_just_outside_the_threshold_passes_and_is_not_rounded_down(self) -> None:
        c = self.case(FOOTPRINT + 0.001, "just_outside")
        assert c.analytic_m == pytest.approx(0.001)
        assert c.analytic_m > 0
        assert c.physx_agrees

    def test_the_boundary_cases_are_separated_by_two_millimetres(self) -> None:
        """No rounding turns one into the other."""
        inside = self.case(FOOTPRINT - 0.001, "in").analytic_m
        outside = self.case(FOOTPRINT + 0.001, "out").analytic_m
        assert inside < 0 < outside
        assert outside - inside == pytest.approx(0.002)

    def test_physx_matches_analytic_at_every_distance(self) -> None:
        for d in (1.00, FOOTPRINT, FOOTPRINT - 0.001, FOOTPRINT + 0.001):
            assert self.case(d, "x").physx_agrees
