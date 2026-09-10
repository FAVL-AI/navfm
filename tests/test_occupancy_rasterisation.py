"""The analytic reference, tested where the answer can be worked out by hand.

This module is the yardstick the physical probe is measured against, so it has
to be right independently of the probe. Every case below has an expected cell
set that can be derived on paper from the frozen estimand: a cell is occupied
iff its full horizontal area, extruded through the slab, intersects the geometry.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from navfm.collection.occupancy import (
    AABB,
    cell_bounds,
    compare_cells,
    expected_cells_for_box,
    expected_cells_for_boxes,
)

RES = 0.10
ORIGIN = (0.0, 0.0)
SHAPE = (20, 20)
SLAB = (0.10, 0.60)


def cells(box: AABB, **kw: object) -> set[tuple[int, int]]:
    return expected_cells_for_box(box, ORIGIN, RES, SHAPE, slab=SLAB, **kw)  # type: ignore[arg-type]


class TestCellGeometry:
    def test_origin_is_the_centre_of_cell_zero_zero(self) -> None:
        """Reading origin as a corner would shift the entire map by half a cell."""
        x0, y0, x1, y1 = cell_bounds(ORIGIN, RES, 0, 0)
        assert (x0, y0, x1, y1) == pytest.approx((-0.05, -0.05, 0.05, 0.05))

    def test_cells_tile_without_gap_or_overlap(self) -> None:
        a = cell_bounds(ORIGIN, RES, 0, 0)
        b = cell_bounds(ORIGIN, RES, 0, 1)
        assert a[2] == pytest.approx(b[0])


class TestFixtureA_BoxInsideOneCell:
    def test_a_small_box_well_inside_one_cell_marks_exactly_that_cell(self) -> None:
        box = AABB(0.01, 0.01, 0.2, 0.03, 0.03, 0.4)
        assert cells(box) == {(0, 0)}


class TestFixtureB_BoxCrossingTwoCells:
    def test_a_box_straddling_a_boundary_marks_both(self) -> None:
        box = AABB(0.03, 0.0, 0.2, 0.07, 0.01, 0.4)
        assert cells(box) == {(0, 0), (0, 1)}

    def test_a_box_spanning_a_two_by_two_block_marks_four(self) -> None:
        box = AABB(0.03, 0.03, 0.2, 0.07, 0.07, 0.4)
        assert cells(box) == {(0, 0), (0, 1), (1, 0), (1, 1)}


class TestFixtureC_ThinWallExactlyOnACellBoundary:
    """The boundary-tangency case the estimand says must be settled by measurement."""

    WALL = AABB(0.05, -0.5, 0.0, 0.05, 0.5, 3.0)  # zero-thickness plane at x = 0.05

    def test_strict_convention_counts_neither_neighbour(self) -> None:
        assert cells(self.WALL) == set()

    def test_touch_convention_counts_both_neighbours(self) -> None:
        touched = cells(self.WALL, boundary_touch_counts=True)
        assert (0, 0) in touched and (0, 1) in touched

    def test_the_two_conventions_genuinely_differ_here(self) -> None:
        """Otherwise the parameter would be decorative."""
        assert cells(self.WALL) != cells(self.WALL, boundary_touch_counts=True)


class TestFixtureD_ThinWallOffsetInsideABoundary:
    def test_an_epsilon_offset_resolves_the_ambiguity(self) -> None:
        """Offset just inside cell (0,0), so only that cell may be occupied."""
        wall = AABB(0.049, -0.5, 0.0, 0.0499, 0.5, 3.0)
        got = cells(wall)
        assert (0, 0) in got
        assert (0, 1) not in got


class TestFixtureE_HollowDoubleFaceWall:
    """Two thin faces with a genuine cavity between them.

    The cavity is empty. Marking it occupied because the object is called a wall
    would be defining occupancy from a name, which the estimand forbids. The
    enclosure that stops a robot crossing comes from planner inflation, tested
    separately.
    """

    FACES: ClassVar[list[AABB]] = [
        AABB(0.10, -0.5, 0.0, 0.11, 0.5, 3.0),
        AABB(0.39, -0.5, 0.0, 0.40, 0.5, 3.0),
    ]

    def test_both_faces_are_marked(self) -> None:
        got = expected_cells_for_boxes(self.FACES, ORIGIN, RES, SHAPE, slab=SLAB)
        assert (0, 1) in got
        assert (0, 4) in got

    def test_the_cavity_between_the_faces_is_free_at_base_rasterisation(self) -> None:
        got = expected_cells_for_boxes(self.FACES, ORIGIN, RES, SHAPE, slab=SLAB)
        assert (0, 2) not in got and (0, 3) not in got

    def test_a_cell_outside_both_faces_is_free(self) -> None:
        got = expected_cells_for_boxes(self.FACES, ORIGIN, RES, SHAPE, slab=SLAB)
        assert (0, 8) not in got


class TestFixtureF_FurnitureSpanningManyCells:
    def test_a_desk_sized_box_marks_its_whole_footprint(self) -> None:
        box = AABB(0.02, 0.02, 0.0, 0.58, 0.28, 1.3)
        got = cells(box)
        assert len(got) == 7 * 4
        assert (0, 0) in got and (3, 6) in got


class TestFixtureH_VerticalExtentVsSlab:
    def test_geometry_entirely_above_the_slab_is_free(self) -> None:
        assert cells(AABB(0.0, 0.0, 0.8, 0.4, 0.4, 1.2)) == set()

    def test_geometry_entirely_below_the_slab_is_free(self) -> None:
        assert cells(AABB(0.0, 0.0, 0.0, 0.4, 0.4, 0.05)) == set()

    def test_geometry_intersecting_only_part_of_the_slab_is_occupied(self) -> None:
        """A 5 cm kerb reaching into the bottom of the slab still blocks."""
        assert cells(AABB(0.01, 0.01, 0.0, 0.03, 0.03, 0.15)) == {(0, 0)}

    def test_geometry_merely_touching_the_slab_face_is_not_occupied(self) -> None:
        """Measure-zero contact would block cells the robot passes cleanly under."""
        assert cells(AABB(0.01, 0.01, 0.0, 0.03, 0.03, 0.10)) == set()

    def test_a_tall_object_spanning_the_whole_slab_is_occupied(self) -> None:
        assert cells(AABB(0.01, 0.01, 0.0, 0.03, 0.03, 3.0)) == {(0, 0)}


class TestComparisonMetrics:
    def test_a_missed_cell_is_a_false_negative_not_an_average(self) -> None:
        cmp = compare_cells({(0, 0), (0, 1)}, {(0, 0)})
        assert cmp.false_negatives == frozenset({(0, 1)})
        assert cmp.recall == pytest.approx(0.5)
        assert not cmp.exact_agreement

    def test_a_spurious_cell_is_a_false_positive(self) -> None:
        cmp = compare_cells({(0, 0)}, {(0, 0), (5, 5)})
        assert cmp.false_positives == frozenset({(5, 5)})
        assert cmp.precision == pytest.approx(0.5)

    def test_perfect_agreement_is_reported_as_such(self) -> None:
        cmp = compare_cells({(0, 0), (1, 1)}, {(0, 0), (1, 1)})
        assert cmp.exact_agreement
        assert cmp.recall == 1.0 and cmp.precision == 1.0

    def test_recall_is_none_when_nothing_was_expected(self) -> None:
        """1.0 would claim a success that was never at risk."""
        assert compare_cells(set(), set()).recall is None

    def test_the_aggregate_cannot_hide_a_false_negative(self) -> None:
        """The defect that let the raycast builder through, as a property.

        A probe that gains many cells while losing a wall has a high measured
        count and still fails, because the comparison is set-based.
        """
        expected = {(0, c) for c in range(10)} | {(9, 9)}
        measured = {(0, c) for c in range(10)} | {(r, 5) for r in range(1, 9)}
        cmp = compare_cells(expected, measured)
        assert len(cmp.measured) > len(cmp.expected), "aggregate looks better"
        assert cmp.false_negatives == frozenset({(9, 9)}), "yet a real obstacle was lost"
        assert not cmp.exact_agreement


class TestCellSpanningIsByIndexNotByStepping:
    """H-SAMPLING-1: stepping world points under-covers an object's far edge."""

    class _Grid:
        origin = (0.0, 0.0)
        resolution = 0.10
        shape = (20, 20)

        def world_to_cell(self, xy):
            return (int(round(xy[1] / 0.10)), int(round(xy[0] / 0.10)))

        def in_bounds(self, rc):
            return 0 <= rc[0] < 20 and 0 <= rc[1] < 20

    def test_a_non_multiple_span_includes_its_far_edge(self) -> None:
        from navfm.collection.occupancy import cells_spanning_aabb

        box = AABB(0.0, 0.0, 0.0, 0.3424, 0.3424, 1.0)
        cells = cells_spanning_aabb(self._Grid(), box)
        far = self._Grid().world_to_cell((box.max_x, box.max_y))
        assert far in cells, "the cell containing the object's far edge must be covered"

    def test_stepping_by_resolution_would_have_missed_it(self) -> None:
        """The defect reproduced with the measured values that exposed it.

        SM_InformationDesk_A_232 spans y from -11.7972 to -11.4548 on a grid with
        origin y = -27.14. Its geometry is in row 157; the stepped sampler's last
        sample landed in row 156, so the object read as planner-invisible while
        the map had marked it correctly.
        """
        origin_y, res = -27.14, 0.10
        min_y, max_y = -11.7972, -11.4548

        def row(y: float) -> int:
            return int(round((y - origin_y) / res))

        n = int((max_y - min_y) / res)
        last_stepped_row = row(min_y + n * res)
        true_far_row = row(max_y)
        assert last_stepped_row == 156
        assert true_far_row == 157
        assert last_stepped_row < true_far_row, "the far edge row was never sampled"
