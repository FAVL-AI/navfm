"""Independent matched episode verification and evaluation-only metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def main():
    from navfm.collection.dataset_admission import image_quality

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pretrained", type=Path, required=True)
    p.add_argument("--adapted", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--goal-root",
        type=Path,
        default=Path("/home/favl/navfm-runtime-evidence/option1-20261007-05"),
    )
    a = p.parse_args()
    if a.out.exists():
        p.error("new output required")
    rows = []
    manifests = {}
    starts = {}
    for arm, root in [("pretrained", a.pretrained), ("adapted", a.adapted)]:
        from navfm.collection.scene_layouts import refuse_sealed

        try:
            # Held-out routes never enter training, replay diagnostics or summaries.
            refuse_sealed(
                json.loads((root / "frozen_routes.json").read_text()),
                Path(__file__).resolve().parents[1],
            )
        except ValueError as exc:
            p.error(f"{root.name}: {exc}")
        collection = json.loads((root / "collection.json").read_text())
        if collection["status"] != "COMPLETED":
            raise ValueError("completed collections required")
        for e in collection["episodes"]:
            path = root / e["id"]
            m = json.loads((path / "runtime_manifest.json").read_text())
            subprocess.run(
                [
                    sys.executable,
                    str(REPO / "scripts/verify_rgb_feasibility.py"),
                    "--manifest",
                    str(path / "runtime_manifest.json"),
                ],
                check=True,
                capture_output=True,
            )
            goal_path = a.goal_root / e["id"] / "goal.png"
            goal_source_manifest = a.goal_root / e["id"] / "runtime_manifest.json"
            original = json.loads(goal_source_manifest.read_text())
            original_goal_time = next(
                o["value"] for o in original["observations"] if o["name"] == "goal_capture_sim_time"
            )
            if hashlib.sha256(goal_path.read_bytes()).hexdigest() != m["fixed_goal_sha256"]:
                raise ValueError("fixed goal does not match registered source image")
            records = json.loads((path / "trajectory/transitions.json").read_text())["records"]
            start = records[0]["pose_before"]
            captures = m["captures"]
            stop = m["policy_stop_frame"]
            dist = captures[-1]["distance_to_goal_m"]
            poses = [start, *[c["pose"] for c in captures]]
            travel = sum(math.dist(x[:2], y[:2]) for x, y in pairwise(poses))
            goal = np.asarray(m["route"]["waypoints"][-1], float)
            goal[1] += m["route"]["scene_index"] * 20.0
            shortest = max(0.0, float(np.linalg.norm(np.array(start[:2]) - goal)) - 0.5)
            # Bound includes entry into goal region; collision-free latched stop + settled position.
            correct = stop is not None and captures[stop]["distance_to_goal_m"] <= 0.5
            premature = stop is not None and not correct
            collision = bool(m["contacts"])
            success = correct and dist <= 0.5 and not collision
            timing_key = (
                "observed_frame_available_to_command_ms"
                if all("observed_frame_available_to_command_ms" in x for x in m["inference"])
                else "perception_to_command_ms"
            )
            latency = [x[timing_key] for x in m["inference"]]
            frames = list((path / "trajectory").glob("*.jpg"))
            bad = sum(not image_quality(np.asarray(Image.open(f)))["usable"] for f in frames)
            row = {
                "arm": arm,
                "route": e["id"],
                "seed": m["route"]["seed"],
                "frames": m["frames"],
                "inferences": len(latency),
                "success": int(success),
                "correct_stopping": int(correct),
                "premature_stopping": int(premature),
                "stop_events": int(stop is not None),
                "collision_episode": int(collision),
                "reported_contact_events": len(m["contacts"]),
                "arrival_any_frame": int(any(c["distance_to_goal_m"] <= 0.5 for c in captures)),
                "final_goal_distance_m": dist,
                "path_length_m": travel,
                "path_efficiency": shortest / max(shortest, travel) if success else 0.0,
                "perception_to_command_p50_ms": float(np.percentile(latency, 50)),
                "perception_to_command_p95_ms": float(np.percentile(latency, 95)),
                "perception_to_command_max_ms": max(latency),
                "first_inference_ms": latency[0],
                "missed_250ms_deadlines": sum(v > 250 for v in latency),
                "unusable_image_frames": bad,
                "termination": m["termination"],
                "checkpoint_sha256": m["policy"]["sha256"],
                "timing_field": timing_key,
                "fixed_goal_source": str(goal_path),
                "fixed_goal_source_manifest_sha256": hashlib.sha256(
                    goal_source_manifest.read_bytes()
                ).hexdigest(),
                "fixed_goal_source_capture_sim_time": original_goal_time,
                "fixed_goal_time_epoch": a.goal_root.name,
                "runtime_R3_limitation": "local unused capture time; fixed goal originates from separate source clock above",
                "manifest_sha256": hashlib.sha256(
                    (path / "runtime_manifest.json").read_bytes()
                ).hexdigest(),
                "latencies_ms": latency,
            }
            rows.append(row)
            manifests[arm, e["id"]] = m
            starts[arm, e["id"]] = start
    ids = {r["route"] for r in rows}
    matching = []
    for route in sorted(ids):
        b, f = manifests["pretrained", route], manifests["adapted", route]
        sb, sf = starts["pretrained", route], starts["adapted", route]
        xy = math.dist(sb[:2], sf[:2])
        yaw = abs(math.atan2(math.sin(sb[2] - sf[2]), math.cos(sb[2] - sf[2])))
        checks = {
            k: b[k] == f[k]
            for k in [
                "route",
                "fixture",
                "requested",
                "prospective_wheel_drives",
                "wheel_mapping",
                "observed_rates",
                "camera_local_pose",
                "fixed_goal_sha256",
                "qualification_sha256",
            ]
        }
        checks["start_xy"] = xy <= 0.001
        checks["start_yaw"] = yaw <= 0.005
        matching.append(
            {
                "route": route,
                "start_xy_delta_m": xy,
                "start_yaw_delta_rad": yaw,
                "checks": checks,
                "pass": all(checks.values()),
            }
        )
    aggregate = {}
    for arm in ["pretrained", "adapted"]:
        rr = [r for r in rows if r["arm"] == arm]
        ll = [v for r in rr for v in r["latencies_ms"]]
        aggregate[arm] = {
            "episodes": len(rr),
            **{
                k: sum(r[k] for r in rr)
                for k in [
                    "success",
                    "correct_stopping",
                    "premature_stopping",
                    "stop_events",
                    "collision_episode",
                    "arrival_any_frame",
                    "unusable_image_frames",
                    "missed_250ms_deadlines",
                ]
            },
            "mean_path_efficiency": float(np.mean([r["path_efficiency"] for r in rr])),
            "perception_to_command_p95_ms": float(np.percentile(ll, 95)),
            "latency_samples": len(ll),
        }
    for r in rows:
        r.pop("latencies_ms")
    result = {
        "status": "PASS_MATCHED_INTEGRATION"
        if all(m["pass"] for m in matching)
        else "MATCHING_FAILED",
        "scope": "SIMULATOR_ENGINEERING_NOT_NAVIGATION_SUPERIORITY_OR_REAL_TRANSFER",
        "rows": rows,
        "matching": matching,
        "aggregate": aggregate,
        "definition": {
            "success": "latched RGB stop within0.5m at decision and final settled position; no reported contact",
            "correct_stop": "stop decision <=0.5m, counted per episode; precision undefined if zero stops",
            "premature_stop": "stop decision >0.5m",
            "path_efficiency": "success weighted Euclidean distance to0.5m region /max(distance,path); geometry-only evaluator, not SPLbenchmark claim",
            "latency": "Per-row timing_field: observed-frame-ready through bookkeeping/residence, RGB access, preprocessing, synchronized inference, controller and first target submission when available; otherwise legacy RGB access start. Earlier acquisition/exposure and physical response excluded; cold starts retained; variable background load.",
            "missing": "actualhardwaremetrics and measured safety-clearance duration unavailable; RGB screen is heuristic not geometric visibility guarantee",
        },
        "improvement_claim": False,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["status"], json.dumps(aggregate))


if __name__ == "__main__":
    main()
