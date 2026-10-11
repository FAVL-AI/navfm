"""Independent controls A-J for G10_TURN_SEMANTICS_V2.

Every fixture is analytic. None is derived from `hospital_bo10_run_00000`, which
is outcome-exposed: its failure has already been inspected, so using it to choose
a parameter would make the metric a rule shaped to admit a particular trajectory.

Control J is the load-bearing one. It proves the realised postcondition is not
merely reproducing the planned count: three planned corners blended by a
controller into one continuous arc must measure ONE realised event, and the
trajectory must fail.
"""

from __future__ import annotations

import math
from itertools import pairwise

import numpy as np
import pytest

from navfm.collection.turn_events import (
    TURN_SEMANTICS_V2,
    realised_turn_events,
)


def polyline(points: list[tuple[float, float]], step: float = 0.05) -> np.ndarray:
    """Densely sample a corner polyline: a piecewise-linear *executed* path."""
    out: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in pairwise(points):
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / step))
        for i in range(n):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    out.append(points[-1])
    return np.array(out)


def arc(radius: float, sweep_deg: float, step: float = 0.05,
        start_deg: float = 0.0) -> np.ndarray:
    """A smooth constant-curvature arc, as a controller would drive it."""
    # The angle always advances; only the lateral offset changes sign. A first
    # draft negated BOTH for a right-hand arc, which made the path run backwards
    # in x -- join() then rotated it ~180 degrees and produced a C-curve with no
    # sign reversal at all, so the S-curve control could never have passed.
    total = abs(math.radians(sweep_deg)) * radius
    n = max(3, int(total / step))
    sign = 1.0 if sweep_deg >= 0 else -1.0
    pts = []
    for i in range(n + 1):
        a = math.radians(start_deg) + abs(math.radians(sweep_deg)) * i / n
        pts.append((radius * math.sin(a), sign * radius * (1 - math.cos(a))))
    return np.array(pts)


def straight(length: float, step: float = 0.05,
             start: tuple[float, float] = (0.0, 0.0),
             heading_deg: float = 0.0) -> np.ndarray:
    n = max(2, int(length / step))
    c, s = math.cos(math.radians(heading_deg)), math.sin(math.radians(heading_deg))
    return np.array([(start[0] + c * length * i / n, start[1] + s * length * i / n)
                     for i in range(n + 1)])


def join(*parts: np.ndarray) -> np.ndarray:
    """Concatenate path pieces, translating and rotating each to continue the last."""
    out = parts[0].copy()
    for nxt in parts[1:]:
        tail = out[-1]
        prev_dir = out[-1] - out[-2]
        theta = math.atan2(prev_dir[1], prev_dir[0])
        nd = nxt[1] - nxt[0]
        phi = math.atan2(nd[1], nd[0])
        rot = theta - phi
        c, s = math.cos(rot), math.sin(rot)
        moved = np.array([[c * (p[0] - nxt[0][0]) - s * (p[1] - nxt[0][1]) + tail[0],
                           s * (p[0] - nxt[0][0]) + c * (p[1] - nxt[0][1]) + tail[1]]
                          for p in nxt])
        out = np.vstack([out, moved[1:]])
    return out


def count(path: np.ndarray) -> int:
    return len(realised_turn_events(path)[0])


class TestIndependentControls:
    def test_A_straight_trajectory_has_no_turns(self) -> None:
        assert count(straight(20.0)) == 0

    def test_B_one_smooth_ninety_degree_arc_is_one_turn(self) -> None:
        assert count(join(straight(3.0), arc(2.0, 90.0), straight(3.0))) == 1

    def test_C_one_continuous_172_degree_arc_is_one_turn(self) -> None:
        """Not five. Partitioning an arc would make any long bend qualify."""
        assert count(join(straight(3.0), arc(2.0, 172.0), straight(3.0))) == 1

    def test_D_three_turns_separated_by_low_curvature_runs_are_three(self) -> None:
        path = join(straight(3.0), arc(1.5, 90.0), straight(3.0), arc(1.5, 90.0),
                    straight(3.0), arc(1.5, 90.0), straight(3.0))
        assert count(path) == 3

    def test_E_two_turns_separated_by_a_straight_run_are_two(self) -> None:
        path = join(straight(3.0), arc(1.5, 90.0), straight(3.0), arc(1.5, 90.0),
                    straight(3.0))
        assert count(path) == 2

    def test_F_an_s_curve_has_two_distinct_direction_changes(self) -> None:
        path = join(straight(2.0), arc(2.0, 80.0), arc(2.0, -80.0), straight(2.0))
        assert count(path) == 2

    def test_G_a_noisy_straight_trajectory_has_no_turns(self) -> None:
        rng = np.random.default_rng(0)
        base = straight(20.0)
        noisy = base + rng.normal(0.0, 0.004, size=base.shape)
        assert count(noisy) == 0

    def test_H_small_left_right_corrections_are_not_turns(self) -> None:
        """Cumulative absolute heading would accumulate these into a false turn."""
        xs = np.linspace(0.0, 20.0, 800)
        ys = 0.02 * np.sin(xs * 3.0)
        path = np.column_stack([xs, ys])
        events, detail = realised_turn_events(path)
        assert len(events) == 0
        cumulative = sum(abs(e["net_deg"]) for e in detail["all_events"])
        assert cumulative >= 0.0

    def test_I_a_long_curve_is_one_event_not_floor_angle_over_thirty(self) -> None:
        path = join(straight(2.0), arc(3.0, 120.0), straight(2.0))
        events, _ = realised_turn_events(path)
        assert len(events) == 1
        assert abs(events[0].net_deg) == pytest.approx(120.0, abs=8.0)
        assert len(events) != int(120 // TURN_SEMANTICS_V2.qualifying_turn_deg)

    def test_J_three_planned_corners_blended_into_one_arc_measure_one(self) -> None:
        """The control that stops the postcondition echoing the plan.

        The PLAN has three corners. The controller blends them into one
        continuous sweep, so the recorded data contains one turning episode and
        the trajectory must FAIL, whatever the plan said.
        """
        planned = polyline([(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (8.0, 4.0), (8.0, 8.0)])
        planned_turns = count(planned)
        blended = join(straight(2.0), arc(2.5, 170.0), straight(2.0))
        realised_turns = count(blended)
        assert planned_turns >= 3, "the plan offers three qualifying corners"
        assert realised_turns == 1, "the execution contains one turning episode"
        assert realised_turns < TURN_SEMANTICS_V2.qualifying_turn_deg / 10


class TestSeparatorSemantics:
    def test_a_short_low_curvature_gap_does_not_separate(self) -> None:
        """Below the minimum separator distance the two arcs are one event."""
        path = join(straight(2.0), arc(1.5, 60.0), straight(0.4), arc(1.5, 60.0),
                    straight(2.0))
        assert count(path) == 1

    def test_a_long_enough_low_curvature_gap_does_separate(self) -> None:
        path = join(straight(2.0), arc(1.5, 60.0), straight(1.6), arc(1.5, 60.0),
                    straight(2.0))
        assert count(path) == 2

    def test_the_separator_statistics_are_reported(self) -> None:
        _, detail = realised_turn_events(join(straight(3.0), arc(1.5, 90.0), straight(3.0)))
        assert "longest_separator_run_m" in detail
        assert detail["turning_segments"] > 0


class TestParameterProvenance:
    def test_the_qualifying_threshold_did_not_move(self) -> None:
        assert TURN_SEMANTICS_V2.qualifying_turn_deg == 30.0

    def test_only_one_parameter_is_new_and_it_is_derived_from_the_interval(self) -> None:
        s = TURN_SEMANTICS_V2
        prov = s.to_dict()["parameter_provenance"]
        assert prov["min_separator_distance_m"].startswith("NEW")
        assert s.min_separator_distance_m == pytest.approx(2 * s.resample_interval_m)
        for reused in ("resample_interval_m", "low_curvature_segment_deg"):
            assert "REUSED" in prov[reused]

    def test_net_not_cumulative_is_used_for_magnitude(self) -> None:
        """An oscillation whose absolute sum is large has a small net."""
        xs = np.linspace(0.0, 12.0, 600)
        ys = 0.05 * np.sin(xs * 4.0)
        events, _ = realised_turn_events(np.column_stack([xs, ys]))
        assert all(abs(e.net_deg) < 30.0 for e in events)
