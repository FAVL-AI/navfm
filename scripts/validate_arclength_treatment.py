"""ARC_LENGTH_INTERPOLATED_TARGET_SELECTOR_V1: analytic validation.

The treatment is the manipulated factor of a one-factor experiment, so three
things have to be true at once before it can ever run, and each is established
here separately.

**Arm A is unchanged now that the treatment exists.** Adding a second selector
to the source tree must not move the control arm. The same frozen equivalence
domain is re-run -- fifteen analytic fixtures and all 1200 recorded poses,
compared against the pre-seam tracker read from git as well as against the
post-seam default and injected legacy paths.

**Arm B's geometry is right, checked against arithmetic rather than against
itself.** Expected targets are hand-computed on routes with integer arc lengths
and written down as literals. Validating an interpolation helper with another
helper that shares its production code would prove only that the code agrees
with itself.

**Only target selection differs.** The treatment is reached through the seam,
which hands it the path, a position, an index and the look-ahead and nothing
else, so it has no route to the speed law, the gains, the stop branch or the
goal criteria.

The offline run_00001 comparison is a command-field counterfactual and nothing
more. Those poses were produced by the control behaviour; an interpolated
tracker would not have visited them. It answers how commands differ at recorded
states, never what trajectory Arm B would produce.

Nothing here runs Isaac, opens an episode, or executes an arm.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
import inspect
import json
import math
import pathlib
import pickle
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.arm_environment_guard import check_contract  # noqa: E402
from navfm.collection.interpolated_target import InterpolatedLookaheadPursuit  # noqa: E402
from navfm.control import M3PRO_LIMITS, DemonstratorMode, PurePursuit  # noqa: E402
from navfm.evidence import emit_evidence  # noqa: E402
from navfm.target_selection import (  # noqa: E402
    ArcLengthInterpolatedTargetSelector,
    LegacyVertexTargetSelector,
    TargetSelection,
    TargetSelectionRefused,
    TargetSelector,
    interpolated_selection,
)
from navfm.tracker_equivalence import (  # noqa: E402
    COMMAND_CHANNELS,
    TARGET_CHANNELS,
    compare_sequences,
    run_command_sequence,
    run_target_sequence,
)

OUT = REPO / "gates/BO10/arclength_treatment_validation_20260912.json"
PREREG = REPO / "gates/BO10/terminal_approach_intervention_v1_20260911.json"
RUN_TRAJ = REPO / "runs/bo10/hospital_bo10_run_00001/traj_data.pkl"
PRE_SEAM_COMMIT = "437ebfc63f828fb1200df1f01df56bc339209349"
CONTROL_REL = "src/navfm/control.py"
SEAM_REL = "src/navfm/target_selection.py"

LOOKAHEAD = 0.45
CONFIG: dict[str, Any] = {
    "lookahead": LOOKAHEAD,
    "goal_tol": 0.20,
    "limits": M3PRO_LIMITS,
    "mode": DemonstratorMode.NONHOLONOMIC,
    "cruise_v": 0.35,
}

#: Declared BEFORE any fixture was run, and not fitted to an observed
#: discrepancy. Expected values are decimal literals computed by hand; the
#: implementation accumulates the same decimals in IEEE-754, so the two differ
#: by a few ulps -- of order 1e-15 m at these magnitudes. 1e-12 m is three
#: orders of magnitude above that and ten orders below the 0.45 m look-ahead, so
#: it cannot absorb a geometric error while still tolerating representation.
ANALYTIC_TOLERANCE_M = 1e-12

# Routes with integer arc lengths, so every expectation below is exact
# arithmetic rather than a number read off the implementation.
L_ROUTE = np.array([[0.0, 0.0], [3.0, 0.0], [3.0, 4.0]])          # cum 0, 3, 7
SQUARE = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])  # cum 0, 1, 2, 3
DENSE = np.array([[0.0, 0.0], [0.1, 0.0], [0.2, 0.0], [0.3, 0.0], [5.0, 0.0]])
STRAIGHT = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
DEGENERATE = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 0.0], [4.0, 0.0]])


def _fixture(
    name: str, route: np.ndarray, pose: tuple[float, float], *,
    projection_s: float, target_s: float, target: tuple[float, float],
    target_segment: int, clamped: bool, why: str,
) -> dict[str, Any]:
    """One fixture with its expectation stated independently of the code."""
    return {
        "name": name, "route": route, "pose": pose,
        "expected": {
            "projection_s": projection_s, "target_s": target_s,
            "target_x": target[0], "target_y": target[1],
            "target_segment": target_segment, "clamped_at_route_end": clamped,
        },
        "why": why,
    }


def analytic_fixtures() -> list[dict[str, Any]]:
    """Hand-computed expectations. Arithmetic, not output capture."""
    return [
        _fixture(
            "A_STRAIGHT_SEGMENT", L_ROUTE, (1.0, 0.0),
            projection_s=1.0, target_s=1.45, target=(1.45, 0.0),
            target_segment=0, clamped=False,
            why="s=1 on the 3 m leg; 1 + 0.45 stays on the same leg"),
        _fixture(
            "B_EXACT_VERTEX", L_ROUTE, (3.0, 0.0),
            projection_s=3.0, target_s=3.45, target=(3.0, 0.45),
            target_segment=1, clamped=False,
            why="the pose is the shared corner; the tie resolves to the earlier "
                "segment so s=3, and 0.45 past the corner is 0.45 up the second leg"),
        _fixture(
            "C_BETWEEN_VERTICES", L_ROUTE, (1.5, 0.0),
            projection_s=1.5, target_s=1.95, target=(1.95, 0.0),
            target_segment=0, clamped=False,
            why="interpolation within one segment"),
        _fixture(
            "D_CROSS_ONE_VERTEX", L_ROUTE, (2.8, 0.0),
            projection_s=2.8, target_s=3.25, target=(3.0, 0.25),
            target_segment=1, clamped=False,
            why="2.8 + 0.45 = 3.25 crosses the corner at s=3 by 0.25"),
        _fixture(
            "E_CROSS_MULTIPLE_VERTICES", DENSE, (0.0, 0.0),
            projection_s=0.0, target_s=0.45, target=(0.45, 0.0),
            target_segment=3, clamped=False,
            why="0.45 spans three 0.1 m segments and lands 0.15 into the fourth"),
        _fixture(
            "F_RIGHT_ANGLE_CORNER", L_ROUTE, (2.7, 0.0),
            projection_s=2.7, target_s=3.15, target=(3.0, 0.15),
            target_segment=1, clamped=False,
            why="arc length turns the corner. A Euclidean chord of 0.45 m would "
                "reach (3.15, 0), which is not on the route at all"),
        _fixture(
            "G_MULTI_CORNER_ROUTE", SQUARE, (0.8, 0.0),
            projection_s=0.8, target_s=1.25, target=(1.0, 0.25),
            target_segment=1, clamped=False,
            why="cumulative length across the first corner of a three-leg route"),
        _fixture(
            "H_OFF_ROUTE_POSE", L_ROUTE, (1.0, 1.0),
            projection_s=1.0, target_s=1.45, target=(1.45, 0.0),
            target_segment=0, clamped=False,
            why="1 m off the first leg; the clamped foot is (1, 0) at s=1, and "
                "interpolation proceeds from the projection, not the pose"),
        _fixture(
            "I_FINAL_SEGMENT", L_ROUTE, (3.0, 3.0),
            projection_s=6.0, target_s=6.45, target=(3.0, 3.45),
            target_segment=1, clamped=False,
            why="1.0 m of route remains, which exceeds the look-ahead"),
        _fixture(
            "J_REMAINING_SHORTER_THAN_LOOKAHEAD", L_ROUTE, (3.0, 3.8),
            projection_s=6.8, target_s=7.0, target=(3.0, 4.0),
            target_segment=1, clamped=True,
            why="6.8 + 0.45 = 7.25 exceeds the 7 m route, so the target clamps to "
                "the final point rather than extrapolating past the goal"),
        _fixture(
            "K_EXACT_ROUTE_ENDPOINT", L_ROUTE, (3.0, 4.0),
            projection_s=7.0, target_s=7.0, target=(3.0, 4.0),
            target_segment=1, clamped=True,
            why="at the end of the route the target is the end of the route"),
        _fixture(
            "L_PROJECTION_TIE_CASE", L_ROUTE, (1.0, 2.0),
            projection_s=1.0, target_s=1.45, target=(1.45, 0.0),
            target_segment=0, clamped=False,
            why="exactly 2 m from both legs. The frozen rule resolves a tie to the "
                "earlier segment, giving s=1 rather than s=5"),
        _fixture(
            "M_DEGENERATE_REPEATED_VERTEX", DEGENERATE, (0.5, 0.0),
            projection_s=0.5, target_s=0.95, target=(0.95, 0.0),
            target_segment=0, clamped=False,
            why="a repeated vertex contributes a zero-length segment, which the "
                "projection skips; the arc-length coordinate is unaffected"),
    ]


REFUSAL_FIXTURES: list[tuple[str, Any, Any, float]] = [
    ("N_EMPTY_ROUTE", np.zeros((0, 2)), (0.0, 0.0), LOOKAHEAD),
    ("N_SINGLE_POINT_ROUTE", np.array([[0.0, 0.0]]), (0.0, 0.0), LOOKAHEAD),
    ("O_NONFINITE_POSE", L_ROUTE, (float("nan"), 0.0), LOOKAHEAD),
    ("O_NONFINITE_ROUTE", np.array([[0.0, 0.0], [float("inf"), 0.0]]), (0.0, 0.0), LOOKAHEAD),
    ("P_MALFORMED_POINT_SHAPE", np.array([0.0, 1.0, 2.0]), (0.0, 0.0), LOOKAHEAD),
    ("P_THREE_COLUMN_ROUTE", np.zeros((3, 3)), (0.0, 0.0), LOOKAHEAD),
    ("Q_NEGATIVE_LOOKAHEAD", L_ROUTE, (0.0, 0.0), -0.45),
    ("Q_NONFINITE_LOOKAHEAD", L_ROUTE, (0.0, 0.0), float("nan")),
    ("R_ZERO_LENGTH_ROUTE", np.array([[1.0, 1.0], [1.0, 1.0]]), (0.0, 0.0), LOOKAHEAD),
]


# --- test-only defective selectors -------------------------------------------


class _WrongOffsetSelector:
    """Interpolates the wrong distance along the route."""

    target_type = "NEGATIVE_CONTROL_WRONG_OFFSET"

    def select_target(self, path: np.ndarray, position: np.ndarray, index: int,
                      lookahead: float) -> TargetSelection:
        inherited = LegacyVertexTargetSelector().select_target(
            path, position, index, lookahead)
        selection = interpolated_selection(path, position, lookahead * 2.0)
        return TargetSelection(selection.point, inherited.next_index)


class _BackwardSelector:
    """Interpolates backwards along the route."""

    target_type = "NEGATIVE_CONTROL_BACKWARD"

    def select_target(self, path: np.ndarray, position: np.ndarray, index: int,
                      lookahead: float) -> TargetSelection:
        from navfm.collection.route_projection import (
            point_at_arclength,
            polyline_cumlength,
            project_to_polyline,
        )

        pts = np.asarray(path, dtype=np.float64).reshape(-1, 2)
        cum = polyline_cumlength(pts)
        proj = project_to_polyline(pts, cum, np.asarray(position)[:2])
        inherited = LegacyVertexTargetSelector().select_target(
            path, position, index, lookahead)
        return TargetSelection(
            point_at_arclength(pts, cum, proj.s - lookahead), inherited.next_index)


class _ExtrapolatingSelector:
    """Violates the frozen route-end rule by extrapolating past the final point."""

    target_type = "NEGATIVE_CONTROL_EXTRAPOLATES"

    def select_target(self, path: np.ndarray, position: np.ndarray, index: int,
                      lookahead: float) -> TargetSelection:
        from navfm.collection.route_projection import polyline_cumlength, project_to_polyline

        pts = np.asarray(path, dtype=np.float64).reshape(-1, 2)
        cum = polyline_cumlength(pts)
        proj = project_to_polyline(pts, cum, np.asarray(position)[:2])
        target_s = proj.s + lookahead
        last, prev = pts[-1], pts[-2]
        unit = (last - prev) / float(np.linalg.norm(last - prev))
        point = (
            last + (target_s - float(cum[-1])) * unit
            if target_s > float(cum[-1])
            else _ExtrapolatingSelector._on_route(pts, cum, target_s)
        )
        inherited = LegacyVertexTargetSelector().select_target(
            path, position, index, lookahead)
        return TargetSelection(point, inherited.next_index)

    @staticmethod
    def _on_route(pts: np.ndarray, cum: np.ndarray, s: float) -> np.ndarray:
        from navfm.collection.route_projection import point_at_arclength

        return point_at_arclength(pts, cum, s)


class _LaterSegmentTieSelector:
    """Violates the frozen tie rule by resolving ties to the later segment."""

    target_type = "NEGATIVE_CONTROL_LATER_SEGMENT_TIE"

    def select_target(self, path: np.ndarray, position: np.ndarray, index: int,
                      lookahead: float) -> TargetSelection:
        from navfm.collection.route_projection import point_at_arclength, polyline_cumlength

        pts = np.asarray(path, dtype=np.float64).reshape(-1, 2)
        cum = polyline_cumlength(pts)
        p = np.asarray(position, dtype=np.float64)[:2]
        best_s, best_d = 0.0, float("inf")
        for i in range(pts.shape[0] - 1):
            a, b = pts[i], pts[i + 1]
            ab = b - a
            length = float(np.linalg.norm(ab))
            if length <= 0.0:
                continue
            t = float(np.clip(np.dot(p - a, ab) / (length * length), 0.0, 1.0))
            d = float(np.linalg.norm(p - (a + t * ab)))
            if d <= best_d:            # <= rather than <: ties go to the LATER segment
                best_d, best_s = d, float(cum[i] + t * length)
        inherited = LegacyVertexTargetSelector().select_target(
            path, position, index, lookahead)
        return TargetSelection(
            point_at_arclength(pts, cum, best_s + lookahead), inherited.next_index)


def evaluate_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    """Compare the implementation against the hand-computed expectation."""
    route, pose = fixture["route"], np.array(fixture["pose"], dtype=np.float64)
    expected = fixture["expected"]
    try:
        got = interpolated_selection(route, pose, LOOKAHEAD)
    except TargetSelectionRefused as exc:
        return {"name": fixture["name"], "verdict": "FAIL",
                "reason": f"refused a valid fixture: {exc}"}

    total = float(np.linalg.norm(np.diff(route, axis=0), axis=1).sum())
    deltas = {
        "projection_s": abs(got.projection_s - expected["projection_s"]),
        "target_s": abs(got.target_s - expected["target_s"]),
        "target_x": abs(float(got.point[0]) - expected["target_x"]),
        "target_y": abs(float(got.point[1]) - expected["target_y"]),
    }
    worst = max(deltas.values())
    matches = worst <= ANALYTIC_TOLERANCE_M
    segment_ok = got.target_segment == expected["target_segment"]
    clamp_ok = got.clamped_at_route_end == expected["clamped_at_route_end"]

    # Arc-length invariants, checked on every valid fixture.
    invariants = {
        "target_s_not_behind_projection": got.target_s >= got.projection_s - 1e-15,
        "target_s_within_route": got.target_s <= total + 1e-12,
        "target_s_is_min_of_sum_and_total": (
            abs(got.target_s - min(got.projection_s + LOOKAHEAD, total))
            <= ANALYTIC_TOLERANCE_M),
        "target_lies_on_declared_segment": _point_on_segment(
            route, got.target_segment, got.point),
    }
    ok = matches and segment_ok and clamp_ok and all(invariants.values())
    return {
        "name": fixture["name"], "verdict": "PASS" if ok else "FAIL",
        "why": fixture["why"], "expected": expected,
        "observed": {
            "projection_s": got.projection_s, "target_s": got.target_s,
            "target_x": float(got.point[0]), "target_y": float(got.point[1]),
            "target_segment": got.target_segment,
            "clamped_at_route_end": got.clamped_at_route_end,
        },
        "max_abs_difference_m": worst, "deltas": deltas,
        "segment_matches": segment_ok, "clamp_matches": clamp_ok,
        "invariants": invariants,
    }


def _point_on_segment(route: np.ndarray, segment: int, point: np.ndarray) -> bool:
    a, b = route[segment], route[segment + 1]
    ab = b - a
    length = float(np.linalg.norm(ab))
    if length <= 0.0:
        return bool(np.allclose(point, a))
    t = float(np.dot(point - a, ab) / (length * length))
    perpendicular = float(np.linalg.norm(point - (a + np.clip(t, 0.0, 1.0) * ab)))
    return -1e-12 <= t <= 1.0 + 1e-12 and perpendicular <= 1e-12


def sha256_file(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


# --- Arm A regression, now that the treatment exists --------------------------


def load_pre_seam() -> tuple[Any, str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{PRE_SEAM_COMMIT}:{CONTROL_REL}"],
        capture_output=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"cannot read {CONTROL_REL} at {PRE_SEAM_COMMIT[:12]}")
    digest = hashlib.sha256(proc.stdout).hexdigest()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="preseam_")) / "control_pre_seam.py"
    tmp.write_bytes(proc.stdout)
    spec = importlib.util.spec_from_file_location("control_pre_seam_treatment", tmp)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, digest


def arm_a_regression(pre_seam: Any, path: np.ndarray, poses: np.ndarray) -> dict[str, Any]:
    """LEGACY_DIRECT == LEGACY_INJECTED == PRE_SEAM, after the treatment exists."""
    out: dict[str, Any] = {}
    for pass_name, runner, channels in (
        ("command", run_command_sequence, COMMAND_CHANNELS),
        ("target", run_target_sequence, TARGET_CHANNELS),
    ):
        trackers = {
            "PRE_SEAM": pre_seam.PurePursuit(
                path.copy(), lookahead=LOOKAHEAD, goal_tol=CONFIG["goal_tol"],
                limits=pre_seam.M3PRO_LIMITS,
                mode=pre_seam.DemonstratorMode.NONHOLONOMIC,
                cruise_v=CONFIG["cruise_v"]),
            "LEGACY_DIRECT": PurePursuit(path.copy(), **CONFIG),
            "LEGACY_INJECTED": PurePursuit(
                path.copy(), **CONFIG, target_selector=LegacyVertexTargetSelector()),
        }
        sequences = {name: runner(t, poses) for name, t in trackers.items()}
        for left, right in (("PRE_SEAM", "LEGACY_DIRECT"),
                            ("PRE_SEAM", "LEGACY_INJECTED"),
                            ("LEGACY_DIRECT", "LEGACY_INJECTED")):
            out[f"{pass_name}:{left}_vs_{right}"] = compare_sequences(
                sequences[left], sequences[right], left_label=left, right_label=right,
                channels=channels)
    return out


def channel_totals(comparisons: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for result in comparisons.values():
        for channel, count in result.get("mismatches_by_channel", {}).items():
            totals[channel] = totals.get(channel, 0) + int(count)
    return totals


# --- shared controller laws ---------------------------------------------------


def shared_law_invariance(pre_seam: Any) -> dict[str, Any]:
    """Treatment code must not have moved any law outside target selection."""
    import navfm.control as current

    members = {
        "speed_and_angular_law_step": (pre_seam.PurePursuit.step, PurePursuit.step),
        "route_completion_finished": (
            pre_seam.PurePursuit.__dict__["finished"].fget,
            PurePursuit.__dict__["finished"].fget),
        "velocity_clipping_clamp": (
            pre_seam.BaseLimits.clamp, M3PRO_LIMITS.__class__.clamp),
        "se2_integration_unicycle": (pre_seam.unicycle_step, current.unicycle_step),
        "se2_integration_holonomic": (pre_seam.holonomic_step, current.holonomic_step),
        "waypoint_to_twist": (pre_seam.waypoint_to_twist, current.waypoint_to_twist),
    }
    detail: dict[str, Any] = {}
    unchanged = True
    for name, (before, after) in members.items():
        a = hashlib.sha256(inspect.getsource(before).encode()).hexdigest()
        b = hashlib.sha256(inspect.getsource(after).encode()).hexdigest()
        detail[name] = {"pre_seam_sha256": a, "current_sha256": b, "identical": a == b}
        unchanged &= a == b
    control_now = sha256_file(REPO / CONTROL_REL)
    return {
        "SHARED_CONTROLLER_LAWS": "UNCHANGED" if unchanged else "CHANGED",
        "method": "byte comparison of each law's source against the pinned pre-seam module",
        "members": detail,
        "control_py_unchanged_by_this_tranche": control_now == (
            "679cd60f86ea2b84e4f8fe93cd464a8484bee69204f6716a62f3adb05d04abc6"),
        "control_py_sha256": control_now,
        "what_this_tranche_changed": [
            f"{SEAM_REL}: added ArcLengthInterpolatedTargetSelector, "
            "interpolated_selection, InterpolatedSelection and TargetSelectionRefused"
        ],
        "runtime_limits": {
            "lookahead_m": LOOKAHEAD, "goal_tol_m": CONFIG["goal_tol"],
            "cruise_v": CONFIG["cruise_v"], "max_v": M3PRO_LIMITS.max_v,
            "max_w": M3PRO_LIMITS.max_w,
        },
    }


def override_surface() -> dict[str, Any]:
    """The treatment's reachable surface, asked of the objects."""
    behavioural = [
        name for name in dir(ArcLengthInterpolatedTargetSelector)
        if not name.startswith("_")
        and callable(getattr(ArcLengthInterpolatedTargetSelector, name))
    ]
    parameters = [
        p for p in inspect.signature(
            ArcLengthInterpolatedTargetSelector.select_target).parameters if p != "self"
    ]
    base = {n for n in dir(PurePursuit) if not n.startswith("__")}
    overridden = sorted(n for n in base if n in InterpolatedLookaheadPursuit.__dict__)
    subclass_behavioural = [n for n in overridden if n not in {"target_type"}]
    forbidden = {"tracker", "limits", "cruise_v", "mode", "goal_tol", "dt", "max_steps",
                 "route", "goal"}
    return {
        "BEHAVIOURAL_OVERRIDE_SURFACE": ["target"],
        "selector_behavioural_members": behavioural,
        "selector_surface_is_one_method": behavioural == ["select_target"],
        "selector_parameters": parameters,
        "forbidden_parameters_present": sorted(set(parameters) & forbidden),
        "subclass_behavioural_overrides": subclass_behavioural,
        "subclass_override_is_target_only": subclass_behavioural == ["target"],
        "why_it_is_structural": (
            "the selector is handed a path, a position, an index and the look-ahead. "
            "It is never handed the tracker, so it has no route to the speed law, the "
            "gains, the stop branch, the goal predicate, dt or max_steps"
        ),
    }


# --- offline command-field counterfactual -------------------------------------


def command_field(path: np.ndarray, poses: np.ndarray) -> dict[str, Any]:
    """How commands differ at recorded states. Not a trajectory prediction."""
    legacy_t = run_target_sequence(PurePursuit(path.copy(), **CONFIG), poses)
    treat_t = run_target_sequence(
        PurePursuit(path.copy(), **CONFIG,
                    target_selector=ArcLengthInterpolatedTargetSelector()), poses)
    legacy_c = run_command_sequence(PurePursuit(path.copy(), **CONFIG), poses)
    treat_c = run_command_sequence(
        PurePursuit(path.copy(), **CONFIG,
                    target_selector=ArcLengthInterpolatedTargetSelector()), poses)

    def series(seq: dict[str, Any], key: str) -> np.ndarray:
        return np.array([r[key] for r in seq["records"]], dtype=np.float64)

    target_gap = np.hypot(
        series(treat_t, "target_x") - series(legacy_t, "target_x"),
        series(treat_t, "target_y") - series(legacy_t, "target_y"))
    distance_delta = series(treat_t, "target_distance") - series(legacy_t, "target_distance")
    heading_delta = np.abs(
        np.arctan2(
            np.sin(series(treat_t, "heading_error") - series(legacy_t, "heading_error")),
            np.cos(series(treat_t, "heading_error") - series(legacy_t, "heading_error"))))
    vx_delta = series(treat_c, "vx") - series(legacy_c, "vx")
    wz_delta = series(treat_c, "wz") - series(legacy_c, "wz")

    def stats(values: np.ndarray) -> dict[str, float]:
        return {
            "mean": float(np.mean(values)), "median": float(np.median(values)),
            "max": float(np.max(values)), "min": float(np.min(values)),
        }

    steps = int(poses.shape[0])
    return {
        "LABEL": "COMMAND_FIELD_COUNTERFACTUAL_ONLY",
        "steps_evaluated": steps,
        "differing_steps": {
            "target_coordinate": int(np.count_nonzero(target_gap > 0.0)),
            "target_distance": int(np.count_nonzero(distance_delta != 0.0)),
            "heading_error": int(np.count_nonzero(heading_delta > 0.0)),
            "vx": int(np.count_nonzero(vx_delta != 0.0)),
            "wz": int(np.count_nonzero(wz_delta != 0.0)),
        },
        "descriptive": {
            "target_separation_m": stats(target_gap),
            "target_distance_difference_m": stats(np.abs(distance_delta)),
            "abs_heading_error_difference_rad": stats(heading_delta),
            "abs_vx_difference_m_s": stats(np.abs(vx_delta)),
            "abs_wz_difference_rad_s": stats(np.abs(wz_delta)),
        },
        "index_advancement_identical": int(
            np.count_nonzero(
                series(treat_t, "index_after") != series(legacy_t, "index_after"))) == 0,
        "WHAT_THIS_ANSWERS": (
            "how the two target rules differ in the commands they would issue AT THESE "
            "RECORDED STATES, under identical frozen controller laws"
        ),
        "WHAT_THIS_DOES_NOT_ANSWER": [
            "what trajectory Arm B would produce",
            "whether Arm B reaches the goal",
            "whether cross-track error improves",
            "whether success rate or SPL changes",
        ],
        "why_the_domain_is_endogenous": (
            "these poses were produced by the control behaviour. An interpolated "
            "tracker steering differently from step one would not have visited them, "
            "so the comparison is a command field evaluated on the control arm's "
            "trajectory and never a miniature Arm B"
        ),
        "no_threshold_is_introduced": (
            "the 2.589 m cross-track observed in run_00001 against a 0.45 m look-ahead "
            "motivated this experiment. It is not a success threshold, not a target to "
            "beat, and not an arm result"
        ),
    }


# --- negative controls and refusals -------------------------------------------


def negative_controls() -> dict[str, Any]:
    """The fixture suite must reject a treatment that is subtly wrong."""
    defective: dict[str, TargetSelector] = {
        "wrong_offset": _WrongOffsetSelector(),
        "backward_interpolation": _BackwardSelector(),
        "extrapolates_past_route_end": _ExtrapolatingSelector(),
        "tie_resolves_to_later_segment": _LaterSegmentTieSelector(),
    }
    fixtures = analytic_fixtures()
    out: dict[str, Any] = {}
    for name, selector in defective.items():
        rejected: list[str] = []
        first: dict[str, Any] | None = None
        for fixture in fixtures:
            route = fixture["route"]
            pose = np.array(fixture["pose"], dtype=np.float64)
            tracker = PurePursuit(route.copy(), **CONFIG, target_selector=selector)
            point = np.asarray(tracker.target(pose), dtype=np.float64)
            expected = fixture["expected"]
            gap = math.hypot(point[0] - expected["target_x"], point[1] - expected["target_y"])
            if gap > ANALYTIC_TOLERANCE_M:
                rejected.append(fixture["name"])
                if first is None:
                    first = {
                        "fixture": fixture["name"],
                        "expected_target": [expected["target_x"], expected["target_y"]],
                        "observed_target": [float(point[0]), float(point[1])],
                        "separation_m": gap,
                        "quantity": "target coordinates (and therefore target_s)",
                    }
        out[name] = {
            "DETECTED": bool(rejected),
            "fixtures_rejected": rejected,
            "fixtures_total": len(fixtures),
            "first_rejection": first,
        }
    return out


def refusal_controls() -> dict[str, Any]:
    """Invalid input must produce a stated refusal, never a traceback."""
    out: dict[str, Any] = {}
    for name, route, pose, lookahead in REFUSAL_FIXTURES:
        try:
            interpolated_selection(route, np.asarray(pose, dtype=np.float64), lookahead)
        except TargetSelectionRefused as exc:
            out[name] = {"REFUSED": True, "reason": str(exc)[:160]}
        except Exception as exc:
            out[name] = {
                "REFUSED": False,
                "reason": f"raised {type(exc).__name__} instead of a stated refusal",
            }
        else:
            out[name] = {"REFUSED": False, "reason": "accepted an invalid input"}
    return out


def sensitivity() -> dict[str, Any]:
    """The treatment must differ where the geometry says it should, and must not
    differ merely because the code paths are separate."""
    differ_route, differ_pose = L_ROUTE, np.array([1.0, 0.0])
    legacy = PurePursuit(differ_route.copy(), **CONFIG)
    treat = PurePursuit(differ_route.copy(), **CONFIG,
                        target_selector=ArcLengthInterpolatedTargetSelector())
    differ = {
        "route": differ_route.tolist(), "pose": differ_pose.tolist(),
        "legacy_target": np.asarray(legacy.target(differ_pose)).tolist(),
        "treatment_target": np.asarray(treat.target(differ_pose)).tolist(),
        "reason": (
            "the legacy rule has not advanced past vertex 0, so it steers at the route "
            "start 1 m behind the pose. The treatment steers 0.45 m ahead along the "
            "route. This is the geometric difference the intervention exists to test"
        ),
    }
    differ["targets_differ"] = differ["legacy_target"] != differ["treatment_target"]

    # Where the two rules legitimately coincide: at the end of the route. The
    # legacy index has saturated at the final vertex and the arc-length target
    # has clamped to the final point, so both name it.
    #
    # An interior coincidence was tried first and does not exist. Whenever the
    # interpolated target lands ON a vertex, the Euclidean distance from the
    # pose to that vertex is at most the 0.45 m of route between them, so the
    # legacy strict-less-than test advances PAST it. That is geometry, not
    # floating point -- though the boundary case is also fragile in float:
    # 1.0 - 0.55 evaluates to 0.44999999999999996, which is strictly less than
    # 0.45. Recording the failed construction rather than deleting it, since it
    # says something true about the two rules.
    agree_poses = [[3.0, 4.0], [3.0, 3.9], [5.0, 5.0]]
    agreements = []
    for pose in agree_poses:
        legacy2 = PurePursuit(L_ROUTE.copy(), **CONFIG)
        treat2 = PurePursuit(L_ROUTE.copy(), **CONFIG,
                             target_selector=ArcLengthInterpolatedTargetSelector())
        legacy2._idx = L_ROUTE.shape[0] - 1
        treat2._idx = L_ROUTE.shape[0] - 1
        lt = np.asarray(legacy2.target(np.array(pose)), dtype=np.float64)
        tt = np.asarray(treat2.target(np.array(pose)), dtype=np.float64)
        agreements.append({
            "pose": pose,
            "legacy_target": lt.tolist(), "treatment_target": tt.tolist(),
            "agree": bool(math.hypot(*(tt - lt)) <= ANALYTIC_TOLERANCE_M),
        })
    agree = {
        "route": L_ROUTE.tolist(),
        "index": int(L_ROUTE.shape[0] - 1),
        "cases": agreements,
        "targets_agree": all(case["agree"] for case in agreements),
        "reason": (
            "at the route end the legacy index has saturated at the final vertex and "
            "the arc-length target has clamped to the final point, so both rules name "
            "it. Agreement here shows the difference elsewhere is geometric rather than "
            "an artefact of running two code paths"
        ),
        "why_interior_agreement_does_not_exist": (
            "whenever the interpolated target lands on a vertex, the Euclidean distance "
            "from the pose to that vertex is at most the 0.45 m of route between them, "
            "so the legacy strict-less-than advance test passes and the control arm "
            "steps past that vertex. The two rules can therefore only coincide where "
            "the legacy index can no longer advance"
        ),
    }
    return {
        "TREATMENT_IS_NOT_A_NO_OP": differ["targets_differ"],
        "TREATMENT_AGREES_WHERE_GEOMETRY_COINCIDES": agree["targets_agree"],
        "differs": differ,
        "agrees": agree,
    }


def port_fidelity() -> dict[str, Any]:
    """The selector must reproduce the frozen subclass that defined the treatment.

    Secondary to the hand-computed fixtures, not a substitute: both share
    ``route_projection``, so this shows the port is faithful, not that the
    geometry is right.
    """
    mismatches = 0
    checked = 0
    for route in (L_ROUTE, SQUARE, DENSE, STRAIGHT):
        seam = PurePursuit(route.copy(), **CONFIG,
                           target_selector=ArcLengthInterpolatedTargetSelector())
        frozen = InterpolatedLookaheadPursuit(route.copy(), **CONFIG)
        total = float(np.linalg.norm(np.diff(route, axis=0), axis=1).sum())
        for s in np.linspace(-0.5, total + 0.5, 60):
            pose = np.array([s * 0.7, s * 0.3])
            a = np.asarray(seam.target(pose), dtype=np.float64)
            b = np.asarray(frozen.target(pose), dtype=np.float64)
            checked += 1
            if not np.array_equal(a, b) or seam._idx != frozen._idx:
                mismatches += 1
    return {
        "PORT_FIDELITY": "PASS" if mismatches == 0 else "FAIL",
        "poses_checked": checked,
        "mismatches": mismatches,
        "frozen_reference": {
            "class": "navfm.collection.interpolated_target.InterpolatedLookaheadPursuit",
            "source": "src/navfm/collection/interpolated_target.py",
            "sha256": sha256_file(REPO / "src/navfm/collection/interpolated_target.py"),
        },
        "claim_boundary": (
            "both implementations share route_projection, so this establishes that the "
            "port is faithful to the frozen subclass. It does NOT independently "
            "establish that the geometry is correct -- the hand-computed fixtures do"
        ),
    }


def main() -> int:
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False).stdout.strip()
    pre_seam, pre_seam_sha = load_pre_seam()
    prereg = json.loads(PREREG.read_text())
    route = np.array(
        prereg["secondary_outcome_cross_track_error"]["frozen_route_polyline"]["coordinates"],
        dtype=np.float64)
    with RUN_TRAJ.open("rb") as handle:
        traj = pickle.load(handle)
    positions = np.asarray(traj["position"], dtype=np.float64)
    poses = np.column_stack(
        [positions[:, 0], positions[:, 1], np.asarray(traj["yaw"], dtype=np.float64)])

    print("=" * 68)
    print("ARC_LENGTH_INTERPOLATED_TARGET_SELECTOR_V1 -- analytic validation")
    print("=" * 68)
    print(f"HEAD                {head[:12]}")
    print(f"tolerance           {ANALYTIC_TOLERANCE_M} m (declared before any fixture ran)")
    print()

    fixtures = [evaluate_fixture(f) for f in analytic_fixtures()]
    fixtures_ok = all(f["verdict"] == "PASS" for f in fixtures)
    worst = max(f.get("max_abs_difference_m", 0.0) for f in fixtures)
    for result in fixtures:
        print(f"  {result['name']:38s} {result['verdict']}  "
              f"max|d|={result.get('max_abs_difference_m', 0.0):.3e}")
    print(f"analytic fixtures   {'PASS' if fixtures_ok else 'FAIL'} "
          f"({len(fixtures)} valid)  worst {worst:.3e} m")

    refusals = refusal_controls()
    refusals_ok = all(r["REFUSED"] for r in refusals.values())
    print(f"refusal controls    {'PASS' if refusals_ok else 'FAIL'} ({len(refusals)})")

    sens = sensitivity()
    sens_ok = sens["TREATMENT_IS_NOT_A_NO_OP"] and sens[
        "TREATMENT_AGREES_WHERE_GEOMETRY_COINCIDES"]
    print(f"sensitivity         {'PASS' if sens_ok else 'FAIL'}  "
          f"differs={sens['TREATMENT_IS_NOT_A_NO_OP']}  "
          f"agrees_where_expected={sens['TREATMENT_AGREES_WHERE_GEOMETRY_COINCIDES']}")

    controls = negative_controls()
    controls_ok = all(c["DETECTED"] for c in controls.values())
    for name, result in controls.items():
        print(f"  {name:38s} {'DETECTED' if result['DETECTED'] else 'MISSED'}  "
              f"({len(result['fixtures_rejected'])}/{result['fixtures_total']} fixtures)")
    print(f"negative controls   {'PASS' if controls_ok else 'FAIL'}")

    fidelity = port_fidelity()
    print(f"port fidelity       {fidelity['PORT_FIDELITY']}  "
          f"({fidelity['poses_checked']} poses, {fidelity['mismatches']} mismatches)")

    surface = override_surface()
    print(f"override surface    {surface['BEHAVIOURAL_OVERRIDE_SURFACE']}  "
          f"selector_one_method={surface['selector_surface_is_one_method']}")

    laws = shared_law_invariance(pre_seam)
    print(f"shared laws         {laws['SHARED_CONTROLLER_LAWS']}")
    print()

    regression: dict[str, Any] = {}
    regression_ok = True
    from navfm.control import resample_path

    for name, trace_path in (("frozen_route_polyline", route),
                             ("frozen_route_resampled_0m25", resample_path(route, 0.25))):
        comparisons = arm_a_regression(pre_seam, trace_path, poses)
        totals = channel_totals(comparisons)
        ok = all(v.get("EQUIVALENCE") == "PASS" for v in comparisons.values())
        regression_ok &= ok
        regression[name] = {
            "steps_evaluated": int(poses.shape[0]),
            "verdict": "PASS" if ok else "FAIL",
            "mismatches_by_channel": totals,
            "comparisons": {k: v["EQUIVALENCE"] for k, v in comparisons.items()},
            "max_numerical_difference": max(
                float(v.get("max_numerical_difference", 0.0)) for v in comparisons.values()),
        }
        print(f"  arm-A {name:34s} {regression[name]['verdict']}  "
              f"mismatches={sum(totals.values())}")

    fixture_regression = arm_a_regression(pre_seam, L_ROUTE, np.array(
        [[x, 0.05, 0.2] for x in np.linspace(0.0, 2.9, 40)]))
    fixture_ok = all(v.get("EQUIVALENCE") == "PASS" for v in fixture_regression.values())
    regression_ok &= fixture_ok
    print(f"  arm-A analytic-domain regression        {'PASS' if fixture_ok else 'FAIL'}")
    print(f"arm-A regression    {'PASS' if regression_ok else 'FAIL'}")
    print()

    field = command_field(route, poses)
    descriptive = field["descriptive"]
    print(f"command field       {field['steps_evaluated']} steps  "
          f"({field['LABEL']})")
    print(f"  target differs    {field['differing_steps']['target_coordinate']} steps  "
          f"mean sep {descriptive['target_separation_m']['mean']:.3f} m  "
          f"max {descriptive['target_separation_m']['max']:.3f} m")
    print(f"  wz differs        {field['differing_steps']['wz']} steps  "
          f"mean |dwz| {descriptive['abs_wz_difference_rad_s']['mean']:.4f} rad/s  "
          f"max {descriptive['abs_wz_difference_rad_s']['max']:.4f}")
    print()

    contracts = {version: check_contract(REPO, version) for version in ("V2", "V3")}
    for version, result in contracts.items():
        print(f"contract {version}          {result['CONTRACT_SATISFIED']}  "
              f"drift={[d['field'] for d in result['drift']]}")
    print()

    verdict = (
        "PASS" if (fixtures_ok and refusals_ok and sens_ok and controls_ok
                   and fidelity["PORT_FIDELITY"] == "PASS"
                   and surface["selector_surface_is_one_method"]
                   and surface["subclass_override_is_target_only"]
                   and laws["SHARED_CONTROLLER_LAWS"] == "UNCHANGED"
                   and regression_ok)
        else "FAIL"
    )

    record = {
        "check": "ARC_LENGTH_INTERPOLATED_TARGET_SELECTOR_V1_VALIDATION",
        "artifact_semantics": "TREATMENT_VALIDATION_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": _dt.datetime.now(_dt.UTC).isoformat(),
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "repository_head": head,
        "implementation": {
            "class": "navfm.target_selection.ArcLengthInterpolatedTargetSelector",
            "target_type": ArcLengthInterpolatedTargetSelector.target_type,
            "source": SEAM_REL,
            "source_sha256": sha256_file(REPO / SEAM_REL),
            "interface": "select_target(path, position, index, lookahead) -> TargetSelection",
            "geometry_function": "navfm.target_selection.interpolated_selection",
            "frozen_lookahead_m": LOOKAHEAD,
        },
        "frozen_semantics_used": {
            "source_of_truth": [
                "gates/BO10/terminal_approach_intervention_v1_20260911.json",
                "gates/BO10/target_selection_controls_20260911.json",
                "src/navfm/collection/route_projection.py",
                "src/navfm/collection/interpolated_target.py",
            ],
            "projection_basis": "the pose's nearest valid projection, parametric foot clamped",
            "tie_rule": "ties resolve to the earlier segment (strict less-than)",
            "arc_length_coordinate": "cumulative polyline length from the first vertex",
            "forward_distance": "the frozen look-ahead, 0.45 m, along the route",
            "route_end_rule": "clamps to the final path point; never extrapolates",
            "vertex_index": "advanced by the inherited legacy rule so finished matches",
            "not_circle_intersection": (
                "this is an arc-length interpolated point on the polyline. It is NOT "
                "look-ahead-circle pure pursuit, and a small cross-track error does not "
                "establish that a forward circle intersection exists"
            ),
        },
        "numerical_standard": {
            "tolerance_m": ANALYTIC_TOLERANCE_M,
            "declared_before_fixtures_ran": True,
            "justification": (
                "expected values are hand-computed decimal literals; the implementation "
                "accumulates the same decimals in IEEE-754, differing by a few ulps "
                "(order 1e-15 m here). The tolerance is three orders above that and ten "
                "below the look-ahead, so it cannot absorb a geometric error"
            ),
        },
        "independent_oracle": {
            "method": (
                "every expected projection_s, target_s, segment and target coordinate is "
                "arithmetic on routes with integer arc lengths, written as literals"
            ),
            "not_validated_against": (
                "the production interpolation helpers. A helper checked with a helper "
                "that shares its code proves only self-consistency"
            ),
        },
        "analytic_fixtures": {
            "count": len(fixtures),
            "verdict": "PASS" if fixtures_ok else "FAIL",
            "max_abs_difference_m": worst,
            "results": fixtures,
        },
        "refusal_controls": {
            "verdict": "PASS" if refusals_ok else "FAIL",
            "count": len(refusals),
            "results": refusals,
        },
        "treatment_sensitivity": sens,
        "negative_controls": {
            "verdict": "PASS" if controls_ok else "FAIL", "results": controls},
        "port_fidelity": fidelity,
        "override_surface": surface,
        "shared_controller_laws": laws,
        "arm_a_post_treatment_regression": {
            "verdict": "PASS" if regression_ok else "FAIL",
            "pre_seam_reference": {"commit": PRE_SEAM_COMMIT, "sha256": pre_seam_sha},
            "recorded_traces": regression,
            "analytic_domain": {
                "verdict": "PASS" if fixture_ok else "FAIL",
                "comparisons": {k: v["EQUIVALENCE"] for k, v in fixture_regression.items()},
            },
        },
        "offline_command_field": field,
        "run_00001_source": {
            "path": "runs/bo10/hospital_bo10_run_00001/traj_data.pkl",
            "sha256": sha256_file(RUN_TRAJ),
            "used_as": "OFFLINE_POSE_TRACE_ONLY",
            "dynamics_replayed": False, "modified": False,
        },
        "contract_status": {
            version: {
                "CONTRACT_SATISFIED": result["CONTRACT_SATISFIED"],
                "drift": [d["field"] for d in result["drift"]],
            }
            for version, result in contracts.items()
        },
        "claim_boundary": (
            "this establishes that the treatment implements the preregistered geometry "
            "over the declared analytic fixtures, that it differs from the control where "
            "the geometry says it should, that only target selection differs, and that "
            "Arm A is unchanged now that the treatment exists. It establishes nothing "
            "about what either arm would produce in the simulator; no arm has run"
        ),
        "V4_AMENDMENT": "NOT_CREATED",
        "EXECUTION_MANIFEST": "NOT_FROZEN",
        "EXECUTION_MANIFEST_OWES_ARM_OUTPUT_ALLOWLIST": True,
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "TREATMENT_SELECTOR": (
            "IMPLEMENTED_AND_VALIDATED" if verdict == "PASS" else "VALIDATION_FAILED"),
        "ARC_LENGTH_TREATMENT_VALIDATION": verdict,
    }

    sha = emit_evidence(
        OUT, record,
        required_keys=(
            "ARC_LENGTH_TREATMENT_VALIDATION", "analytic_fixtures",
            "arm_a_post_treatment_regression", "offline_command_field",
            "negative_controls", "EXECUTION_STATUS"),
    )
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha}")
    print(f"TREATMENT_SELECTOR  {record['TREATMENT_SELECTOR']}")
    print(f"VALIDATION          {verdict}")
    print("V4_AMENDMENT        NOT_CREATED")
    print("EXECUTION_MANIFEST  NOT_FROZEN")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
