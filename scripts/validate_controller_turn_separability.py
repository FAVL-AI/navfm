"""Non-production controller-interface fixtures: does turn structure survive execution?

`run_00000` realised three planned corners as one 172 degree sweep. That is either
the route (corners too close for the controller to settle between them) or the
controller (never settles regardless). These fixtures answer it on analytic
geometry, before a single Hospital candidate is spent.

**Excluded from everything.** Not the BO-10 production population, not the E2
population, not production route selection. They exercise the UNCHANGED pure
pursuit and the UNCHANGED kinematic drive; nothing here may feed back into the
frozen generator.

**Free space, deliberately.** The collision guard admits every pose, because the
question is whether turn-event structure survives the controller, not whether
the guard works -- that has its own nine controls. Obstacles would confound the
measurement with rejections.

The defining positive control is THREE_WELL_SEPARATED. The tight fixture is
DIAGNOSTIC: it is not required to fail, and a suite whose success depended on the
controller behaving badly in one case would be a suite designed backwards.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import numpy as np  # noqa: E402

from navfm.collection.kinematic_drive import (  # noqa: E402
    DriveOutcome,
    KinematicDriveConfig,
    KinematicDriver,
)
from navfm.collection.turn_events import realised_turn_events  # noqa: E402
from navfm.control import DemonstratorMode, PurePursuit  # noqa: E402
from navfm.evidence import emit_evidence  # noqa: E402
from navfm.isaac.robot import M3PRO  # noqa: E402

CONTROL_HZ = 12.0
MAX_STEPS = 8000


class OpenSpace:
    """Admits every pose. The guard has its own controls; this is not that test."""

    def pose_is_free(self, x: float, y: float, yaw: float) -> bool:
        return True


def corner_route(legs: list[tuple[float, float]], step: float = 0.10) -> np.ndarray:
    """A piecewise-linear planned route through the given corner points."""
    pts: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in pairwise(legs):
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / step))
        for i in range(n):
            t = i / n
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    pts.append(legs[-1])
    return np.array(pts)


def cross_track(realised: np.ndarray, planned: np.ndarray) -> np.ndarray:
    """Distance from each realised point to the nearest point of the planned path."""
    d = np.linalg.norm(realised[:, None, :] - planned[None, :, :], axis=-1)
    return d.min(axis=1)


def drive(planned: np.ndarray, start_yaw: float) -> dict[str, Any]:
    """Drive a planned route with the UNCHANGED controller and kinematic drive."""
    cfg = KinematicDriveConfig(dt=1.0 / CONTROL_HZ)
    driver = KinematicDriver(guard=OpenSpace(), config=cfg)
    tracker = PurePursuit(planned, lookahead=0.45, goal_tol=0.20,
                          limits=M3PRO.limits, mode=DemonstratorMode.NONHOLONOMIC,
                          cruise_v=0.35)
    pose = (float(planned[0][0]), float(planned[0][1]), float(start_yaw))
    poses = [pose]
    commands: list[tuple[float, float, float]] = []
    rejected = 0
    reached = False
    for _ in range(MAX_STEPS):
        vx, vy, wz, done = tracker.step(np.array([pose[0], pose[1]]), pose[2])
        if done:
            reached = True
            break
        res = driver.step(pose, (vx, vy, wz))
        commands.append(res.commanded)
        if res.outcome is DriveOutcome.REJECTED_COLLISION:
            rejected += 1
            break
        pose = res.pose
        poses.append(pose)
    arr = np.array([[p[0], p[1]] for p in poses])
    yaws = np.array([p[2] for p in poses])
    return {"positions": arr, "yaws": yaws, "reached_goal": reached,
            "steps": len(poses), "rejected": rejected,
            "commands": commands}


def measure(name: str, legs: list[tuple[float, float]], start_yaw: float,
            expected_realised: int | None, declared_before_running: str) -> dict[str, Any]:
    planned = corner_route(legs)
    run = drive(planned, start_yaw)
    realised = run["positions"]

    plan_events, plan_detail = realised_turn_events(planned)
    real_events, real_detail = realised_turn_events(realised)

    planned_len = float(np.linalg.norm(np.diff(planned, axis=0), axis=1).sum())
    realised_len = float(np.linalg.norm(np.diff(realised, axis=0), axis=1).sum())
    xt = cross_track(realised, planned)

    # Heading error: realised path tangent against the nearest planned tangent.
    pd = np.diff(planned, axis=0)
    ptan = np.arctan2(pd[:, 1], pd[:, 0])
    rd = np.diff(realised, axis=0)
    rtan = np.arctan2(rd[:, 1], rd[:, 0])
    idx = np.linalg.norm(realised[:-1, None, :] - planned[None, :-1, :], axis=-1).argmin(axis=1)
    herr = np.abs(np.arctan2(np.sin(rtan - ptan[idx]), np.cos(rtan - ptan[idx])))

    return {
        "fixture": name,
        "declared_before_running": declared_before_running,
        "expected_realised_events": expected_realised,
        "corners": [[round(c[0], 3), round(c[1], 3)] for c in legs],
        "planned": {
            "turn_events": len(plan_events),
            "event_magnitudes_deg": [round(e.net_deg, 2) for e in plan_events],
            "path_length_m": round(planned_len, 4),
            "separator_runs_m": plan_detail.get("separator_runs_m"),
        },
        "realised": {
            "turn_events": len(real_events),
            "event_magnitudes_deg": [round(e.net_deg, 2) for e in real_events],
            "all_event_magnitudes_deg": [round(e["net_deg"], 2)
                                         for e in real_detail["all_events"]],
            "path_length_m": round(realised_len, 4),
            "separator_runs_m": real_detail.get("separator_runs_m"),
            "longest_separator_run_m": real_detail.get("longest_separator_run_m"),
            "turning_segments": real_detail.get("turning_segments"),
            "low_curvature_segments": real_detail.get("low_curvature_segments"),
        },
        "tracking": {
            "path_length_ratio_realised_over_planned": round(realised_len / planned_len, 5),
            "cross_track_error_m": {"max": round(float(xt.max()), 4),
                                    "mean": round(float(xt.mean()), 4),
                                    "p95": round(float(np.percentile(xt, 95)), 4)},
            "heading_error_deg": {"max": round(float(np.degrees(herr.max())), 3),
                                  "mean": round(float(np.degrees(herr.mean())), 3),
                                  "p95": round(float(np.degrees(np.percentile(herr, 95))), 3)},
            "thresholds": ("DESCRIPTIVE ONLY. No pass/fail threshold is invented for these here; "
                           "the defining question is whether distinct turn-event structure "
                           "survives execution."),
        },
        "execution": {"reached_goal": run["reached_goal"], "steps": run["steps"],
                      "guard_rejections": run["rejected"]},
        "trace": {
            "note": "enough to reconstruct the event decision independently",
            "realised_positions_first_20": realised[:20].round(4).tolist(),
            "realised_yaws_first_20": [round(float(y), 4) for y in run["yaws"][:20]],
            "realised_all_events": real_detail["all_events"],
            "semantics": real_detail["semantics"],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rec: dict[str, Any] = {
        "check": "CONTROLLER_TURN_SEPARABILITY",
        "artifact_semantics": "NON_PRODUCTION_CONTROLLER_INTERFACE_VALIDATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "excluded_from": ["BO-10 production population", "E2 population",
                          "production route selection"],
        "controller": {"implementation": "navfm.control.PurePursuit", "lookahead_m": 0.45,
                       "goal_tol_m": 0.20, "cruise_v_m_s": 0.35, "control_hz": CONTROL_HZ,
                       "mode": "nonholonomic", "UNCHANGED": True},
        "drive": {"model": "KINEMATIC_SE2", "dt_s": 1.0 / CONTROL_HZ,
                  "collision_guard": "OpenSpace -- admits every pose",
                  "why_free_space": ("the question is whether turn structure survives the "
                                     "controller; obstacles would confound it with rejections, "
                                     "and the guard has its own nine controls")},
        "generator_frozen_before_this": "gates/BO10/turning_route_population_v1_final_20260910.json",
        "cannot_feed_back": "no generator parameter may change from these results",
    }

    try:
        fixtures = [
            measure("ONE_SMOOTH_TURN",
                    [(0.0, 0.0), (6.0, 0.0), (6.0, 6.0)], 0.0, 1,
                    "one genuine 90 degree turn; expected realised events = 1"),
            measure("THREE_WELL_SEPARATED",
                    [(0.0, 0.0), (6.0, 0.0), (6.0, 6.0), (12.0, 6.0), (12.0, 12.0)], 0.0, 3,
                    "three 90 degree turns with 6 m legs; expected realised events = 3. "
                    "THIS IS THE DEFINING POSITIVE CONTROL."),
            measure("THREE_TIGHTLY_SPACED",
                    [(0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (5.0, 1.0), (5.0, 5.0)], 0.0, None,
                    "three 90 degree corners with 1 m legs between them. DIAGNOSTIC ONLY -- it is "
                    "NOT required to fail, and no verdict depends on it."),
        ]
        rec["fixtures"] = fixtures
        by = {f["fixture"]: f for f in fixtures}
        one_ok = by["ONE_SMOOTH_TURN"]["realised"]["turn_events"] == 1
        three_ok = by["THREE_WELL_SEPARATED"]["realised"]["turn_events"] >= 3
        rec["defining_controls"] = {
            "ONE_SMOOTH_TURN_realised_is_1": one_ok,
            "THREE_WELL_SEPARATED_realised_is_at_least_3": three_ok,
        }
        rec["CONTROLLER_TURN_SEPARABILITY"] = "PASS" if (one_ok and three_ok) else "FAIL"
        rec["tight_fixture_is_diagnostic_only"] = True
        rec["hospital_authorised"] = bool(one_ok and three_ok)
        if not rec["hospital_authorised"]:
            rec["classification_required"] = ["CONTROLLER_LOOKAHEAD", "ROUTE_CONTROLLER_INTERFACE",
                                              "TURN_SPACING", "KINEMATIC_TRACKING", "MIXED",
                                              "INCONCLUSIVE"]
    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-2500:]
        rec["CONTROLLER_TURN_SEPARABILITY"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=(
            "check", "artifact_semantics", "CONTROLLER_TURN_SEPARABILITY"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
