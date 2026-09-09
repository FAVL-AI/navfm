"""The occupancy window is opt-in, and it cannot exclude an admissible route.

`gates/failures/F-BOUNDS-1.md` records why this exists: the stage bound is not a
collection region in a scene containing distant scenery, and two geometric rules
for deriving a tighter one are refuted by measurement. So the region is declared,
and what a test can hold is that the declaration is sound and that the default
did not move.
"""

from __future__ import annotations

import math

import pytest

from navfm.isaac.collect import CollectConfig, Collector
from navfm.isaac.robot import M3PRO

MAX_PATH_M = 40.0
RADIUS = 0.24


class TestTheWindowCannotExcludeAnAdmissibleRoute:
    def test_the_half_width_is_the_frozen_route_length_plus_the_footprint(self) -> None:
        lo, hi = Collector.route_window((0.0, 0.0), MAX_PATH_M, RADIUS)
        assert hi[0] - lo[0] == pytest.approx(2 * (MAX_PATH_M + RADIUS))
        assert hi[1] - lo[1] == pytest.approx(2 * (MAX_PATH_M + RADIUS))

    def test_every_point_within_the_frozen_path_length_is_inside(self) -> None:
        """The load-bearing property. Displacement cannot exceed path length."""
        centre = (3.0, -7.0)
        lo, hi = Collector.route_window(centre, MAX_PATH_M, RADIUS)
        for k in range(64):
            a = 2 * math.pi * k / 64
            x = centre[0] + MAX_PATH_M * math.cos(a)
            y = centre[1] + MAX_PATH_M * math.sin(a)
            assert lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1]

    def test_the_swept_body_at_maximum_range_is_still_inside(self) -> None:
        centre = (0.0, 0.0)
        lo, hi = Collector.route_window(centre, MAX_PATH_M, RADIUS)
        assert hi[0] >= MAX_PATH_M + RADIUS
        assert lo[1] <= -(MAX_PATH_M + RADIUS)

    def test_a_point_beyond_the_frozen_path_length_may_fall_outside(self) -> None:
        """The window is a bound, not a formality: it must exclude something."""
        lo, hi = Collector.route_window((0.0, 0.0), MAX_PATH_M, RADIUS)
        far = MAX_PATH_M + RADIUS + 1.0
        assert not (lo[0] <= far <= hi[0])

    def test_the_window_follows_its_centre(self) -> None:
        a_lo, _ = Collector.route_window((0.0, 0.0), MAX_PATH_M, RADIUS)
        b_lo, _ = Collector.route_window((100.0, 0.0), MAX_PATH_M, RADIUS)
        assert b_lo[0] - a_lo[0] == pytest.approx(100.0)

    def test_the_window_is_derived_from_the_frozen_config_not_a_new_constant(self) -> None:
        cfg = CollectConfig()
        assert cfg.max_path_m == MAX_PATH_M
        assert M3PRO.footprint_radius == RADIUS
        lo, hi = Collector.route_window((0.0, 0.0), cfg.max_path_m, M3PRO.footprint_radius)
        assert hi[0] - lo[0] == pytest.approx(2 * (cfg.max_path_m + M3PRO.footprint_radius))


class TestTheDefaultDidNotMove:
    def test_build_occupancy_still_defaults_to_the_stage_bound(self) -> None:
        """Hospital's frozen result was produced under the stage bound.

        A changed default would change its grid, and a different grid means
        different sampling, so the frozen result would no longer be re-derivable.
        """
        import inspect

        sig = inspect.signature(Collector.build_occupancy)
        assert sig.parameters["bounds"].default is None

    def test_the_override_is_used_only_when_given(self) -> None:
        source = inspect_source()
        assert "bounds if bounds is not None else self._stage_bounds()" in source

    def test_the_reason_for_the_override_is_recorded_in_the_source(self) -> None:
        """So the next reader does not delete it as an unused parameter."""
        doc = Collector.build_occupancy.__doc__ or ""
        assert "OPT-IN" in doc
        assert "F-BOUNDS-1" in doc


def inspect_source() -> str:
    import inspect

    return inspect.getsource(Collector.build_occupancy)
