"""One fixed ten-second sensor/controller probe; ground truth is evaluation only."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import sys
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from imu_controller_boundary_v1 import BodyGyro, validate_evaluation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def setup_prefix(source):
    tree = ast.parse(source)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    block = next(n for n in main.body if isinstance(n, ast.Try))
    index = [
        i
        for i, n in enumerate(block.body)
        if isinstance(n, ast.ImportFrom) and n.module == "navfm.collection.yaw_rate_tracker"
    ]
    if len(index) != 1:
        raise ValueError("preserved qualification setup boundary changed")
    prefix = ast.Module(body=block.body[: index[0]], type_ignores=[])
    contact = next(
        n for n in ast.walk(prefix) if isinstance(n, ast.FunctionDef) and n.name == "contact"
    )
    conditions = [n for n in ast.walk(contact) if isinstance(n, ast.If)]
    if len(conditions) != 1:
        raise ValueError("contact observer boundary changed")
    conditions[0].test = ast.parse('any("/Robot/" in v for v in paths)', mode="eval").body
    return ast.fix_missing_locations(prefix)


def command(tick):
    if tick < 120 or tick >= 960:
        return 0.0, 0.0
    # Seven one-second plateaux, including small/large turns and straight travel.
    return [(0.1, 0.0), (0.1, 0.1), (0.1, 0.2), (0.1, 0.4), (0.1, -0.1), (0.1, -0.2), (0.1, -0.4)][
        (tick - 120) // 120
    ]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--robot", required=True)
    a = p.parse_args()
    if a.out.exists() or a.out.resolve().is_relative_to(ROOT):
        raise ValueError("new external evidence required")
    a.out.mkdir(parents=True)
    result = {"status": "RUNNING", "rows": [], "imu_readings": [], "episodes": []}
    ns = {
        "np": np,
        "hashlib": hashlib,
        "Path": Path,
        "result": result,
        "a": SimpleNamespace(
            robot=a.robot,
            analytic_colliders=True,
            sphere_wheels=True,
            acceleration_drive=True,
            friction=-1,
        ),
    }
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True})
    ns["app"] = app
    try:
        setup = setup_prefix((ROOT / "scripts/qualify_articulated_control.py").read_text())
        exec(compile(setup, "preserved-qualification-setup", "exec"), ns)
        from navfm.collection.yaw_rate_tracker import YawRateTracker

        sim, robot = ns["sim"], ns["robot"]
        gyro = BodyGyro(robot, sim)
        result["imu_metadata"] = gyro.metadata
        gyro.evidence_path = a.out / "imu_readings.jsonl"
        tracker = YawRateTracker()
        result["imu_readings"] = gyro.guard.records
        names, idx = ns["names"], ns["idx"]
        robot.teleport((-3, 0), 0)
        for tick in range(1200):
            v, w = command(tick)
            if tick < 120:  # fixed startup settling: no sensor input or active command
                output = 0.0
                tracker.reset()
            else:
                measured = gyro.read()
                if v == 0 and w == 0:
                    tracker.reset()
                    output = 0.0  # Same zero-wheel stop as the deployment collector.
                else:
                    output = tracker.update(w, measured, 1 / 120)
            target = np.zeros((1, len(names)), dtype=np.float32)
            target[0, idx] = [
                (v - 0.1625 * output) / 0.04,
                (v + 0.1625 * output) / 0.04,
                (v - 0.1625 * output) / 0.04,
                (v + 0.1625 * output) / 0.04,
            ]
            robot._articulation.set_joint_velocity_targets(target)
            sim.step(render=False)
            xy, yaw = robot.pose()
            vel = np.asarray(robot._articulation.get_velocities()).reshape(-1, 6)[0]
            q = np.asarray(robot._articulation.get_world_poses()[1]).reshape(-1, 4)[0]
            row = {
                "tick": tick,
                "time": float(sim.current_time),
                "command": [v, w],
                "control_output": output,
                "xy": xy.tolist(),
                "yaw": float(yaw),
                "evaluation_orientation_wxyz": q.tolist(),
                "evaluation_world_velocity": vel.tolist(),
            }
            result["rows"].append(row)  # Preserve invalid samples before fail-closed validation.
            validate_evaluation(row)
            if abs(float(q @ q) - 1.0) > 1e-3:
                raise ValueError("evaluation orientation must be unit quaternion")
            qw, qx, qy, qz = q
            body_z_in_world = np.array(
                [2 * (qx * qz + qw * qy), 2 * (qy * qz - qw * qx), 1 - 2 * (qx * qx + qy * qy)]
            )
            body_x_in_world = np.array(
                [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy + qw * qz), 2 * (qx * qz - qw * qy)]
            )
            # Independent body-frame evaluations never return to the controller.
            row.update(
                evaluation_v=float(body_x_in_world @ vel[:3]),
                evaluation_w=float(body_z_in_world @ vel[3:6]),
                evaluation_world_wz=float(vel[5]),
            )
            validate_evaluation(row)
        rows = result["rows"]
        validate_evaluation(rows)
        plateaux = []
        for start in range(120, 960, 120):
            window = rows[start + 60 : start + 120]
            v, w = command(start)
            mv = float(np.mean([r["evaluation_v"] for r in window]))
            mw = float(np.mean([r["evaluation_w"] for r in window]))
            plateaux.append(
                {
                    "command": [v, w],
                    "mean_v": mv,
                    "mean_w": mw,
                    "pass": abs(mv - v) <= 0.05 and abs(mw - w) <= max(0.03, 0.25 * abs(w)),
                }
            )
        tail = rows[-60:]
        stopping_path = sum(math.dist(x["xy"], y["xy"]) for x, y in pairwise(rows[959:]))
        checks = {
            "tracking": all(r["pass"] for r in plateaux),
            "stop_distance": stopping_path <= 0.05,
            "residual_v": max(abs(r["evaluation_v"]) for r in tail) <= 0.01,
            "residual_w": max(abs(r["evaluation_w"]) for r in tail) <= 0.03,
            "sensor_count": len(gyro.guard.records) == 1080,
        }
        result.update(
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            plateaux=plateaux,
            stop_distance=stopping_path,
            contacts=ns["contacts"],
            simulation_ticks=1200,
            path_m=sum(math.dist(x["xy"], y["xy"]) for x, y in pairwise(rows)),
            commanded_motion_s=sum(any(command(i)) for i in range(1200)) / 120,
            scope="sampled engineering commands, not navigation or hardware qualification",
        )
    except BaseException as error:
        result.update(status="FAIL", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        try:
            payload = json.dumps(result, indent=2, allow_nan=result["status"] != "PASS")
        except ValueError:
            result.update(status="FAIL", error="nonfinite result cannot be PASS")
            payload = json.dumps(result, indent=2)
        (a.out / "imu_qualification.json").write_text(payload + "\n")
        app.close()


if __name__ == "__main__":
    main()
