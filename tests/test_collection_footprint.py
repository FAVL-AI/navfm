"""Swept-footprint sampling: the resolution is derived, and heading is consumed.

Two properties carry the G3-G6 gates that will use this module, and both are
the kind that pass by accident if untested.

*The resolution is derived, not chosen.* It comes from the occupancy cell size
by Nyquist, before any production route was evaluated. If ``grid_resolution``
drifts, the pin here fails rather than the probe spacing changing quietly.

*The sweep consumes yaw.* The production footprint is a disc, so yaw cannot
change what it covers -- which means a suite built only on discs would pass
whether or not heading were wired through at all. The rectangular control
exists to make that property falsifiable.
"""

from __future__ import annotations

import math
from itertools import pairwise

import numpy as np
import pytest

from navfm.collection.footprint import (
    GRID_RESOLUTION_M,
    CircularFootprint,
    RectangularFootprint,
    SweepResolution,
    heading_changes,
    resample_route,
    swept_configurations,
)

M3PRO_RADIUS = 0.24


class TestTheResolutionIsDerived:
    def test_probe_spacing_is_half_the_occupancy_cell(self) -> None:
        res = SweepResolution.derive(M3PRO_RADIUS)
        assert res.smallest_detectable_feature_m == GRID_RESOLUTION_M
        assert res.probe_spacing_m == pytest.approx(GRID_RESOLUTION_M / 2)
        assert res.route_step_m == pytest.approx(GRID_RESOLUTION_M / 2)

    def test_the_yaw_step_moves_the_rim_by_one_probe_spacing(self) -> None:
        res = SweepResolution.derive(M3PRO_RADIUS)
        rim_travel = res.max_yaw_step_rad * M3PRO_RADIUS
        assert rim_travel == pytest.approx(res.probe_spacing_m)

    def test_the_grid_resolution_pin_matches_the_collector(self) -> None:
        """A drifting CollectConfig default must break this, not the gate."""
        from navfm.isaac.collect import CollectConfig

        assert CollectConfig().grid_resolution == GRID_RESOLUTION_M

    @pytest.mark.parametrize("bad", [0.0, -0.24])
    def test_a_nonpositive_radius_is_refused(self, bad: float) -> None:
        with pytest.raises(ValueError):
            SweepResolution.derive(bad)


class TestFootprintCoverage:
    def test_every_disc_sample_lies_within_the_radius(self) -> None:
        pts = CircularFootprint(M3PRO_RADIUS).body_points(0.05)
        assert np.all(np.linalg.norm(pts, axis=1) <= M3PRO_RADIUS + 1e-9)

    def test_the_disc_is_sampled_out_to_its_rim(self) -> None:
        """A lattice alone can miss a slab edge; the rim is where support is lost."""
        pts = CircularFootprint(M3PRO_RADIUS).body_points(0.05)
        assert np.max(np.linalg.norm(pts, axis=1)) == pytest.approx(M3PRO_RADIUS)

    def test_no_gap_between_samples_exceeds_the_spacing(self) -> None:
        """The gate detects a one-cell hole only if no sample gap exceeds spacing."""
        spacing = 0.05
        pts = CircularFootprint(M3PRO_RADIUS).body_points(spacing)
        d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
        np.fill_diagonal(d, np.inf)
        assert float(np.max(np.min(d, axis=1))) <= spacing + 1e-9

    def test_the_centre_alone_is_not_the_footprint(self) -> None:
        """G3's defining property: a centre-only test is a different, weaker gate."""
        assert CircularFootprint(M3PRO_RADIUS).body_points(0.05).shape[0] > 1


class TestTheSweepConsumesHeading:
    def test_a_rectangular_footprint_moves_when_yaw_changes(self) -> None:
        rect = RectangularFootprint(length_m=0.40, width_m=0.20)
        a = rect.points(0.0, 0.0, 0.0, 0.05)
        b = rect.points(0.0, 0.0, math.pi / 2, 0.05)
        assert not np.allclose(np.sort(a, axis=0), np.sort(b, axis=0))

    def test_the_production_disc_is_yaw_invariant_by_construction(self) -> None:
        """Stated as a property, so nobody later reads the disc sweep as yaw-aware."""
        disc = CircularFootprint(M3PRO_RADIUS)
        a = disc.points(1.0, 2.0, 0.0, 0.05)
        b = disc.points(1.0, 2.0, 1.234, 0.05)
        assert np.allclose(a, b)


class TestSweptConfigurations:
    def test_a_corner_is_expanded_into_intermediate_headings(self) -> None:
        """Two poses with an unprobed arc between them is the turn-corner failure."""
        res = SweepResolution.derive(M3PRO_RADIUS)
        corner = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0]])
        configs = swept_configurations(corner, res)
        yaws = [c.yaw for c in configs]
        steps = [abs(math.atan2(math.sin(b - a), math.cos(b - a)))
                 for a, b in pairwise(yaws)]
        assert max(steps) <= res.max_yaw_step_rad + 1e-9

    def test_translation_is_sampled_at_the_frozen_step(self) -> None:
        res = SweepResolution.derive(M3PRO_RADIUS)
        configs = swept_configurations(np.array([[0.0, 0.0], [1.0, 0.0]]), res)
        xs = [c.x for c in configs]
        assert max(b - a for a, b in pairwise(xs)) <= res.route_step_m + 1e-9

    def test_route_progress_is_monotonic_and_ends_at_the_arc_length(self) -> None:
        res = SweepResolution.derive(M3PRO_RADIUS)
        configs = swept_configurations(np.array([[0.0, 0.0], [3.0, 0.0], [3.0, 4.0]]), res)
        progress = [c.route_progress_m for c in configs]
        assert progress == sorted(progress)
        assert progress[-1] == pytest.approx(7.0)

    def test_a_degenerate_route_yields_one_configuration(self) -> None:
        res = SweepResolution.derive(M3PRO_RADIUS)
        configs = swept_configurations(np.array([[1.0, 1.0], [1.0, 1.0]]), res)
        assert len(configs) == 1


class TestResampleRoute:
    def test_samples_are_uniformly_spaced_along_arc_length(self) -> None:
        _pts, progress = resample_route(np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]), 0.05)
        gaps = np.diff(progress)
        assert np.allclose(gaps, gaps[0])
        assert progress[-1] == pytest.approx(2.0)

    def test_a_non_two_column_path_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"\(N, 2\)"):
            resample_route(np.zeros((4, 3)), 0.05)


class TestHeadingChanges:
    def test_a_straight_line_has_no_heading_changes(self) -> None:
        n, turns = heading_changes(np.array([[0.0, 0.0], [5.0, 0.0], [10.0, 0.0]]), 30.0)
        assert n == 0 and turns == []

    def test_a_right_angle_counts_once_not_many_times(self) -> None:
        n, _ = heading_changes(np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0]]), 30.0)
        assert n == 1

    def test_each_corner_counts_once(self) -> None:
        """Three legs, two corners. An earlier draft of this assertion was a
        tautology, which is the check-that-cannot-fail defect it was meant to
        guard against; the count is pinned exactly instead."""
        three_legs = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])
        n, turns = heading_changes(three_legs, 30.0)
        assert n == 2, f"expected two corners, got {n}: {turns}"

    def test_the_count_does_not_depend_on_decimation_alignment(self) -> None:
        """The defect this counter was rebuilt to remove.

        One physical right-angle corner, with the leg length swept across the
        0.5 m decimation grid. The earlier accumulate-and-emit rule returned
        1, 2, 2, 1, 2, 1 for these six -- the corner reads as two 45 degree
        turns whenever interpolation replaces it with a chord. A count that
        depends on where the grid falls is not measuring route structure.
        """
        counts = {
            heading_changes(np.array([[0.0, 0.0], [leg, 0.0], [leg, leg]]), 30.0)[0]
            for leg in (5.0, 5.1, 5.25, 5.4, 6.73, 7.0)
        }
        assert counts == {1}, f"one corner must count once at every alignment, got {counts}"

    def test_consecutive_corners_in_the_same_direction_stay_separate(self) -> None:
        """Grouping must not merge distinct corners separated by straight legs."""
        spiral = np.array([[0.0, 0.0], [6.0, 0.0], [6.0, 6.0], [0.0, 6.0], [0.0, 0.6]])
        n, _ = heading_changes(spiral, 30.0)
        assert n == 3

    def test_grouping_is_conservative(self) -> None:
        """It can only merge counts, so it cannot rescue a failing minimum-turn route."""
        straightish = np.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
        assert heading_changes(straightish, 30.0)[0] == 0

    def test_a_turn_below_the_threshold_does_not_count(self) -> None:
        """Negative control for the threshold: a 20 deg bend must not register at 30 deg."""
        far = 10.0
        bend = np.array([[0.0, 0.0], [far, 0.0],
                         [far + far * math.cos(math.radians(20)),
                          far * math.sin(math.radians(20))]])
        n, _ = heading_changes(bend, 30.0)
        assert n == 0
