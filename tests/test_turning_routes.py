"""Independent generator controls A-H for TURNING_ROUTE_POPULATION_V1.

Control H is the load-bearing one. It proves the generator does not adapt to G10
outcomes: with any turn evaluator absent the output must be byte-identical. A
generator that retried until G10 passed would bake the evaluation criterion into
the population and make a subsequent pass uninterpretable.

The scenes here are synthetic occupancy grids, so no simulator is needed and the
controls run on every commit.
"""

from __future__ import annotations

import numpy as np
import pytest

from navfm.collection.turning_routes import (
    TURNING_ROUTE_GENERATOR_V1,
    TurningRouteGenerator,
    sample_turning_route,
)
from navfm.planning import OccupancyGrid, PlannerError

RES = 0.10


def open_grid(width_m: float = 30.0, height_m: float = 30.0) -> OccupancyGrid:
    g = np.zeros((int(height_m / RES), int(width_m / RES)), dtype=bool)
    g[0, :] = g[-1, :] = g[:, 0] = g[:, -1] = True
    return OccupancyGrid(g, RES, (0.0, 0.0))


def corridor_grid() -> OccupancyGrid:
    """A straight corridor 2 m wide."""
    g = np.ones((int(20 / RES), int(30 / RES)), dtype=bool)
    g[int(9 / RES):int(11 / RES), int(1 / RES):int(29 / RES)] = False
    return OccupancyGrid(g, RES, (0.0, 0.0))


def l_corridor_grid() -> OccupancyGrid:
    g = np.ones((int(30 / RES), int(30 / RES)), dtype=bool)
    g[int(4 / RES):int(6 / RES), int(2 / RES):int(20 / RES)] = False
    g[int(4 / RES):int(26 / RES), int(18 / RES):int(20 / RES)] = False
    return OccupancyGrid(g, RES, (0.0, 0.0))


class TestGeneratorProducesSeparatedNonCollinearAnchors:
    def test_anchors_respect_the_minimum_separation(self) -> None:
        rng = np.random.default_rng(0)
        cand = sample_turning_route(open_grid(), rng)
        gaps = np.linalg.norm(np.diff(cand.anchors, axis=0), axis=1)
        assert gaps.min() >= TURNING_ROUTE_GENERATOR_V1.min_anchor_separation_m - 1e-9

    def test_anchors_respect_the_maximum_separation(self) -> None:
        rng = np.random.default_rng(0)
        cand = sample_turning_route(open_grid(), rng)
        gaps = np.linalg.norm(np.diff(cand.anchors, axis=0), axis=1)
        assert gaps.max() <= TURNING_ROUTE_GENERATOR_V1.max_anchor_separation_m + 1e-9

    def test_every_interior_anchor_bends_at_least_the_qualifying_angle(self) -> None:
        """A bend below the qualifying magnitude could never be a turn event."""
        rng = np.random.default_rng(1)
        cand = sample_turning_route(open_grid(), rng)
        assert cand.anchor_turns_deg
        for t in cand.anchor_turns_deg:
            assert abs(t) >= TURNING_ROUTE_GENERATOR_V1.min_anchor_turn_deg - 1e-9

    def test_four_legs_give_three_interior_turns(self) -> None:
        rng = np.random.default_rng(2)
        cand = sample_turning_route(open_grid(), rng)
        assert len(cand.anchor_turns_deg) == 3

    def test_the_path_passes_through_its_anchors(self) -> None:
        """Per-leg smoothing must not string-pull the anchors away."""
        rng = np.random.default_rng(3)
        cand = sample_turning_route(open_grid(), rng)
        for a in cand.anchors:
            d = np.linalg.norm(cand.path - a, axis=1).min()
            assert d < 0.25, f"anchor {a} is {d:.3f} m from the path"


class TestIndependentControls:
    def test_A_open_corridor_introduces_no_artificial_turns(self) -> None:
        """A straight corridor cannot supply separated, non-collinear, non-reversing
        anchors, so it is refused rather than filled with a sawtooth.

        This control is what exposed the missing anti-reversal bound: without it
        the generator emitted 3 m out and 3 m back, a 180 degree "turn" that is a
        reversal along the same corridor.
        """
        rng = np.random.default_rng(0)
        with pytest.raises(PlannerError):
            sample_turning_route(corridor_grid(), rng)

    def test_B_an_L_corridor_supplies_one_natural_turn(self) -> None:
        rng = np.random.default_rng(0)
        gen = TurningRouteGenerator(legs=2, min_anchor_separation_m=3.0,
                                    max_anchor_separation_m=14.0)
        cand = sample_turning_route(l_corridor_grid(), rng, generator=gen)
        assert len(cand.anchor_turns_deg) == 1

    def test_C_a_scene_with_room_supplies_three_plan_events(self) -> None:
        rng = np.random.default_rng(4)
        cand = sample_turning_route(open_grid(), rng)
        from navfm.collection.turn_events import realised_turn_events
        events, _ = realised_turn_events(cand.path)
        assert len(events) >= 3

    def test_D_a_sawtooth_is_impossible_under_the_frozen_generator(self) -> None:
        """Tight spacing is not merely discouraged, it cannot occur.

        A first draft tried to build a deliberately tight generator and assert
        its gaps were small. It does not produce small gaps -- it fails to place
        anchors at all, because uniform free-pose sampling across an open scene
        almost never lands within 0.6 m of the previous anchor. So the property
        is asserted where it actually lives: the frozen minimum separation
        exceeds any sawtooth spacing, and every realised gap respects it.
        """
        rng = np.random.default_rng(9)
        cand = sample_turning_route(open_grid(), rng)
        gaps = np.linalg.norm(np.diff(cand.anchors, axis=0), axis=1)
        assert gaps.min() >= TURNING_ROUTE_GENERATOR_V1.min_anchor_separation_m - 1e-9
        assert TURNING_ROUTE_GENERATOR_V1.min_anchor_separation_m >= 3.0

        tight = TurningRouteGenerator(min_anchor_separation_m=0.2,
                                      max_anchor_separation_m=0.6)
        with pytest.raises(PlannerError):
            sample_turning_route(open_grid(), np.random.default_rng(9), generator=tight)

    def test_D2_a_near_reversal_is_refused(self) -> None:
        """A 180 degree bend is a reversal along the same corridor, not a turn."""
        rng = np.random.default_rng(12)
        cand = sample_turning_route(open_grid(), rng)
        for t in cand.anchor_turns_deg:
            assert abs(t) <= TURNING_ROUTE_GENERATOR_V1.max_anchor_turn_deg + 1e-9

    def test_E_a_disconnected_waypoint_is_rejected(self) -> None:
        g = np.ones((300, 300), dtype=bool)
        g[10:200, 10:200] = False          # one room
        g[220:280, 220:280] = False        # a sealed room, unreachable
        rng = np.random.default_rng(0)
        with pytest.raises(PlannerError):
            for _ in range(6):
                sample_turning_route(OccupancyGrid(g, RES, (0.0, 0.0)), rng,
                                     generator=TurningRouteGenerator(
                                         legs=4, min_anchor_separation_m=12.0,
                                         max_anchor_separation_m=25.0))

    def test_F_a_waypoint_inside_an_obstacle_is_never_sampled(self) -> None:
        rng = np.random.default_rng(5)
        grid = open_grid()
        cand = sample_turning_route(grid, rng)
        for a in cand.anchors:
            assert grid.is_free((float(a[0]), float(a[1])))

    def test_G_the_same_seed_gives_an_identical_population(self) -> None:
        a = sample_turning_route(open_grid(), np.random.default_rng(7))
        b = sample_turning_route(open_grid(), np.random.default_rng(7))
        assert np.allclose(a.anchors, b.anchors)
        assert np.allclose(a.path, b.path)

    def test_H_output_is_identical_with_no_turn_evaluator_present(self) -> None:
        """The load-bearing control: generation does not adapt to G10 outcomes.

        Checked structurally rather than by promise -- the module must not
        reference the turn metric at all, so there is nothing it could adapt to.
        """
        import ast
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1]
               / "src/navfm/collection/turning_routes.py").read_text()
        imported: set[str] = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any("turn_events" in m or "long_horizon" in m for m in imported), (
            "the generator must not import the turn metric"
        )
        for forbidden in ("realised_turn_events", "heading_changes", "TURN_SEMANTICS",
                          "predict_from_route", "measure_from_trajectory"):
            assert forbidden not in src, f"the generator references {forbidden}"

        baseline = sample_turning_route(open_grid(), np.random.default_rng(11))
        again = sample_turning_route(open_grid(), np.random.default_rng(11))
        assert np.allclose(baseline.path, again.path)


class TestGeneratorRefusesRatherThanRelaxes:
    def test_an_impossible_scene_raises_rather_than_loosening_its_rules(self) -> None:
        # 2 x 2 m. A first draft used 6 x 6 m, which comfortably admits 3 m legs
        # and was therefore not impossible at all.
        tiny = np.zeros((20, 20), dtype=bool)
        tiny[0, :] = tiny[-1, :] = tiny[:, 0] = tiny[:, -1] = True
        rng = np.random.default_rng(0)
        with pytest.raises(PlannerError):
            sample_turning_route(OccupancyGrid(tiny, RES, (0.0, 0.0)), rng)

    def test_parameter_provenance_excludes_the_failed_trajectory(self) -> None:
        prov = TURNING_ROUTE_GENERATOR_V1.to_dict()["parameter_provenance"]
        assert prov["derived_from_run_00000"] is False
        assert "1.0 m G10 separator" in prov["min_anchor_separation_m"]
