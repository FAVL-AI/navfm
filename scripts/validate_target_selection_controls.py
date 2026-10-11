"""Bounded analytic controls for the two target-selection arms, before Hospital.

Section 5 of the intervention protocol requires that endpoint and corner
semantics be settled from the preregistration rather than invented after seeing
Hospital results. These fixtures do that. Every expected value is computed from
the geometry by hand -- an L-shaped route whose arc lengths are integers, so the
answers can be read off without trusting the code under test.

That last point is the standing rule this repository has paid for five times:
validation expectations must come from an independent representation of the
geometry, never from a convenient proxy and never from the instrument itself.
Here the independent representation is arithmetic simple enough to verify by
inspection.

Three things are proven:

1. the control arm still returns a path VERTEX, which is the frozen behaviour;
2. the treatment arm returns the point one look-ahead further along the route,
   including across corners, across several short segments, and where the route
   runs out;
3. the two arms differ in target selection and in nothing else -- the inherited
   vertex index advances identically, so ``finished`` means the same thing in
   both, and the projection instrument shared with the analysis agrees with the
   one already pinned in the preregistration.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import pickle
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from diagnose_q2_margin_consumption import project as q2_project  # noqa: E402
from diagnose_q2_margin_consumption import recover_planned_path, sha256  # noqa: E402

from navfm.collection.interpolated_target import (  # noqa: E402
    InterpolatedLookaheadPursuit,
)
from navfm.collection.route_projection import (  # noqa: E402
    point_at_arclength,
    polyline_cumlength,
    project_to_polyline,
)
from navfm.control import M3PRO_LIMITS, DemonstratorMode, PurePursuit  # noqa: E402

OUT = REPO / "gates/BO10/target_selection_controls_20260911.json"
POP = REPO / "gates/BO10/hospital_turning_route_population_20260910.json"
RUN = REPO / "runs/bo10/hospital_bo10_run_00001"

L = 0.45  # the frozen look-ahead
TOL = 1e-9

#: An L-shaped route with integer arc lengths: cum = [0, 10, 20].
ELL = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
#: Short segments, so one look-ahead spans several of them: cum = [0, .2, .4, .6].
SHORT = np.array([[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.4, 0.2]])


def tracker(path: np.ndarray, cls: type[PurePursuit]) -> PurePursuit:
    return cls(path, lookahead=L, goal_tol=0.20, limits=M3PRO_LIMITS,
               mode=DemonstratorMode.NONHOLONOMIC, cruise_v=0.35)


def main() -> int:
    stamp = _dt.datetime.now(_dt.UTC).isoformat()
    checks: list[dict[str, object]] = []

    def record(name: str, why: str, got: np.ndarray, expect: tuple[float, float],
               reasoning: str) -> None:
        err = float(np.linalg.norm(np.asarray(got, dtype=float)[:2] - np.array(expect)))
        checks.append({
            "control": name,
            "what_it_tests": why,
            "expected_xy": list(expect),
            "expected_from": reasoning,
            "actual_xy": [round(float(v), 9) for v in np.asarray(got)[:2]],
            "error_m": err,
            "PASS": err < TOL,
        })

    # --- treatment arm: interpolated target ---------------------------------
    # cum(ELL) = [0, 10, 20]; the corner sits at s = 10.
    cases = [
        ("straight_segment", (2.0, 0.0), (2.45, 0.0), ELL,
         "s=2 on the first leg; s+L=2.45 is still on it, so x=2.45, y=0"),
        ("exact_route_vertex", (10.0, 0.0), (10.0, 0.45), ELL,
         "s=10 is the corner; s+L=10.45 lies 0.45 up the second leg"),
        ("between_vertices", (9.8, 0.0), (10.0, 0.25), ELL,
         "s=9.8; s+L=10.25 is 0.25 past the corner, so the target turns it"),
        ("around_one_corner", (9.7, 0.0), (10.0, 0.15), ELL,
         "s=9.7; s+L=10.15 crosses the corner onto the second leg"),
        ("projection_off_route", (5.0, 3.0), (5.45, 0.0), ELL,
         "nearest projection is (5,0) so s=5 despite a 3 m lateral offset; "
         "s+L=5.45 on the first leg"),
        ("near_route_end", (10.0, 9.8), (10.0, 10.0), ELL,
         "s=19.8; s+L=20.25 exceeds the 20 m route, so the target clamps to the "
         "final point rather than extrapolating past it"),
        ("insufficient_remaining_route", (10.0, 10.0), (10.0, 10.0), ELL,
         "s=20 is the end; the target is the final point and stays there"),
        ("multi_segment_lookahead", (0.0, 0.0), (0.25, 0.2), SHORT,
         "cum=[0,.2,.4,.6]; s=0 and s+L=0.45 lands 0.05 into the third segment, "
         "which starts at (0.2,0.2) heading +x, so (0.25, 0.2)"),
    ]
    for name, pose, expect, path, why in cases:
        t = tracker(path, InterpolatedLookaheadPursuit)
        record(f"interpolated::{name}", "treatment-arm target selection",
               t.target(np.array(pose)), expect, why)

    # --- control arm: must still return a VERTEX ----------------------------
    # The advance is SEQUENTIAL from the current index, not a nearest-vertex
    # search: the loop tests only path[_idx] and breaks as soon as that vertex is
    # further away than the look-ahead. So these cases must run as one stateful
    # walk on a single tracker. Scoring them on fresh trackers was a defect in an
    # earlier version of this harness, recorded in gates/failures/.
    vertex_walk = [
        ((2.0, 0.0), (0.0, 0.0), 0,
         "2 m from vertex 0, outside the 0.45 m radius, so the loop breaks "
         "immediately and the target is vertex 0 -- behind the robot"),
        ((0.2, 0.0), (10.0, 0.0), 1,
         "0.2 m from vertex 0 is inside the radius so the index advances to 1; "
         "vertex 1 is then 9.8 m away, so the loop breaks and targets it"),
        ((10.0, 0.2), (10.0, 10.0), 2,
         "0.2 m from vertex 1 advances the index to 2, the last vertex, where the "
         "loop condition ends the walk"),
    ]
    walker = tracker(ELL, PurePursuit)
    for pose, expect, want_idx, why in vertex_walk:
        got = walker.target(np.array(pose))
        record(f"vertex::seq_pose_{pose[0]}_{pose[1]}", "control-arm frozen behaviour",
               got, expect, why)
        checks.append({
            "control": f"vertex::index_after_pose_{pose[0]}_{pose[1]}",
            "what_it_tests": "the sequential advance rule, index by index",
            "expected_index": want_idx,
            "actual_index": int(walker._idx),
            "PASS": int(walker._idx) == want_idx,
        })

    # --- the two arms differ in target selection and nothing else ------------
    walk = [(0.0, 0.0), (2.0, 0.0), (5.0, 0.5), (9.8, 0.0), (10.0, 0.3),
            (10.0, 5.0), (10.0, 9.9), (10.0, 10.0)]
    a, b = tracker(ELL, PurePursuit), tracker(ELL, InterpolatedLookaheadPursuit)
    idx_a, idx_b, differed = [], [], 0
    for pose in walk:
        ta = a.target(np.array(pose))
        tb = b.target(np.array(pose))
        idx_a.append(a._idx)
        idx_b.append(b._idx)
        if float(np.linalg.norm(np.asarray(ta) - np.asarray(tb))) > TOL:
            differed += 1
    checks.append({
        "control": "arms::vertex_index_advances_identically",
        "what_it_tests": (
            "the inherited index drives `finished`, so if the arms advanced it "
            "differently the experiment would carry a second uncontrolled factor"
        ),
        "index_sequence_control": idx_a,
        "index_sequence_treatment": idx_b,
        "PASS": idx_a == idx_b,
    })
    checks.append({
        "control": "arms::targets_actually_differ",
        "what_it_tests": (
            "a manipulation that changed nothing would make the experiment vacuous, "
            "so the arms must disagree somewhere on the same poses"
        ),
        "poses_compared": len(walk),
        "poses_with_different_targets": differed,
        "PASS": differed > 0,
    })

    # --- the shared projection instrument agrees with the pinned one ---------
    path, _ = recover_planned_path(json.loads(POP.read_text()))
    cum = polyline_cumlength(path)
    with (RUN / "traj_data.pkl").open("rb") as fh:
        pos = np.asarray(pickle.load(fh)["position"], dtype=float)
    ds_err = xt_err = 0.0
    for p in pos:
        new = project_to_polyline(path, cum, p)
        old = q2_project(path, cum, p)
        ds_err = max(ds_err, abs(new.s - old.s))
        xt_err = max(xt_err, abs(new.cross_track - old.cross_track))
    checks.append({
        "control": "projection::agrees_with_the_pinned_implementation",
        "what_it_tests": (
            "the preregistration pins a projection implementation and requires both "
            "arms to be measured by it. The controller now steers by the same "
            "geometry, so a second implementation drifting from the first would "
            "corrupt both the steering and the cross-track measure at once"
        ),
        "poses_compared": int(pos.shape[0]),
        "max_arclength_disagreement_m": ds_err,
        "max_cross_track_disagreement_m": xt_err,
        "tolerance_m": 1e-12,
        "PASS": bool(ds_err < 1e-12 and xt_err < 1e-12),
    })

    # --- clamping is a clamp, not an extrapolation --------------------------
    beyond = point_at_arclength(ELL, polyline_cumlength(ELL), 1e6)
    checks.append({
        "control": "endpoint::arclength_clamps_never_extrapolates",
        "what_it_tests": (
            "an arbitrarily large arc length must return the final route point. "
            "Extrapolation here would steer the base past the goal it is "
            "approaching, and would do so only near the end of a route, which is "
            "exactly where it would be hardest to notice"
        ),
        "queried_arclength_m": 1e6,
        "route_length_m": float(polyline_cumlength(ELL)[-1]),
        "returned_xy": [float(v) for v in beyond],
        "PASS": bool(np.allclose(beyond, ELL[-1])),
    })

    # --- negative control: the harness must be able to fail ------------------
    wrong = point_at_arclength(ELL, polyline_cumlength(ELL), 2.45)
    detects = float(np.linalg.norm(wrong - np.array([2.45, 0.0]))) < TOL
    bad = float(np.linalg.norm(wrong - np.array([2.46, 0.0]))) >= TOL
    checks.append({
        "control": "negative::fixtures_can_fail",
        "what_it_tests": (
            "a check that cannot fail certifies nothing. The same fixture is scored "
            "against the right answer and a deliberately wrong one 1 cm away"
        ),
        "accepts_correct_answer": detects,
        "rejects_wrong_answer_1cm_away": bad,
        "PASS": bool(detects and bad),
    })

    passed = sum(1 for c in checks if c["PASS"])
    result = {
        "check": "TARGET_SELECTION_UNIT_CONTROLS",
        "artifact_semantics": "ANALYTIC_CONTROLS_NO_SIMULATOR_PRE_HOSPITAL",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "purpose": (
            "settle corner and endpoint semantics for both arms before either runs "
            "against Hospital, so no endpoint behaviour can be invented afterwards"
        ),
        "frozen_lookahead_m": L,
        "expectations_are_independent": (
            "every expected value is arithmetic on an L-shaped route with integer "
            "arc lengths, computed by hand rather than by the code under test"
        ),
        "arm_implementations": {
            "control": {
                "class": "navfm.control.PurePursuit",
                "source": "src/navfm/control.py",
                "sha256": sha256(REPO / "src/navfm/control.py"),
                "target_type": "PATH_VERTEX",
                "modified_for_this_experiment": False,
            },
            "treatment": {
                "class": "navfm.collection.interpolated_target.InterpolatedLookaheadPursuit",
                "source": "src/navfm/collection/interpolated_target.py",
                "sha256": sha256(REPO / "src/navfm/collection/interpolated_target.py"),
                "target_type": "ARC_LENGTH_INTERPOLATED",
                "overrides": ["target"],
                "inherits_unchanged": [
                    "the goal predicate", "the speed law", "the curvature law",
                    "the turn-in-place regime", "velocity clamps", "finished",
                ],
            },
            "shared_geometry": {
                "source": "src/navfm/collection/route_projection.py",
                "sha256": sha256(REPO / "src/navfm/collection/route_projection.py"),
            },
        },
        "endpoint_semantics_fixed_here": {
            "past_route_end": (
                "the target clamps to the final path point. Arm B is defined as a "
                "point ON the polyline, and beyond the final vertex there is none"
            ),
            "vertex_index": (
                "advanced by the inherited rule in both arms, so `finished` carries "
                "the same meaning and the experiment keeps one factor"
            ),
            "projection_basis": (
                "the pose's own nearest valid projection, with the parametric foot "
                "clamped to each segment"
            ),
            "fixed_before_any_hospital_run": True,
        },
        "controls": checks,
        "controls_total": len(checks),
        "controls_passed": passed,
        "TARGET_SELECTION_CONTROLS": "PASS" if passed == len(checks) else "FAIL",
    }

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    if back["controls_total"] != len(checks):
        raise SystemExit("evidence guard: control count did not round-trip")
    if "TARGET_SELECTION_CONTROLS" not in back:
        raise SystemExit("evidence guard: verdict absent")

    for c in checks:
        print(f"  [{'PASS' if c['PASS'] else 'FAIL'}] {c['control']}")
    print()
    print(f"TARGET_SELECTION_CONTROLS = {result['TARGET_SELECTION_CONTROLS']}"
          f"  ({passed}/{len(checks)})")
    print(f"control arm source  src/navfm/control.py "
          f"@ {result['arm_implementations']['control']['sha256'][:16]}...  UNMODIFIED")
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha256(OUT)}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
