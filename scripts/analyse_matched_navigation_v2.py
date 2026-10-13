"""Read saved development evidence; model outcomes never decide eligibility."""

import json
import math
from pathlib import Path

from development_qualification_contracts_v1 import validate_clocks
from matched_navigation_contracts_v2 import (
    classify,
    contact_counts,
    score_command,
    terminal_boundary,
    tracking_summary,
)


def analyse(dest, cfg, role):
    dest = Path(dest)
    collection = json.loads((dest / "collection.json").read_text())
    if collection["status"] != "COMPLETED" or len(collection["episodes"]) != 1:
        raise ValueError("single completed episode required")
    episode = dest / collection["episodes"][0]["id"]
    m = json.loads((episode / "runtime_manifest.json").read_text())
    if m["status"] != "PASS" or m["route"]["id"] != cfg["route"]:
        raise ValueError("episode integrity failed")
    if m["policy"]["sha256"] != cfg["models"][role]["sha256"] or m["policy"]["device"] != "cuda":
        raise ValueError("checkpoint/device mismatch")
    if m["topomap"]["chain_json_sha256"] != cfg["chain_sha256"]:
        raise ValueError("chain order/content mismatch")
    if m["base_controller"]["measurement"] != "native body-local IsaacImuSensor angular velocity z":
        raise ValueError("unqualified controller source")
    boundary = json.loads((dest / "first_policy_input.json").read_text())
    if boundary["history_sha256"][:-1] != m["initial_history_sha256"][1:]:
        raise ValueError("cold history mismatch")
    policy = m["policy"]
    if (
        policy["config"]["image_size"] != [85, 64]
        or policy["config"]["context_size"] != 5
        or policy["action_scale_m"] != 0.049994826316833496
        or policy["pd_dt_s"] != 0.5
        or policy["max_v"] != 0.1
        or policy["max_w"] != 0.4
    ):
        raise ValueError("shared preprocessing/action/cadence contract drift")
    tensors = json.loads((dest / "first_policy_tensors.json").read_text())
    if not tensors or tensors[0]["shape"] != [1, 18, 64, 85]:
        raise ValueError("actual six-frame tensor shape mismatch")
    first = m["inference"][0]
    validate_clocks(first["sensor_time"], first["predecision_sim_time"])
    boundary.update(
        pose=first["predecision_pose"],
        sensor_time=first["sensor_time"],
        predecision_sim_time=first["predecision_sim_time"],
        camera=dict(
            local_pose=m["camera_local_pose"],
            product={
                o["name"]: o["value"]
                for o in m["observations"]
                if o["name"]
                in (
                    "render_product_path",
                    "render_product_camera_target",
                    "render_product_resolution",
                    "active_renderer",
                )
            },
        ),
    )
    if len(boundary["camera"]["product"]) != 4 or any(
        v is None for v in boundary["camera"]["product"].values()
    ):
        raise ValueError("camera provenance incomplete")
    phases = [
        json.loads(line) for line in (episode / "imu_lifecycle.jsonl").read_text().splitlines()
    ]
    if len([r for r in phases if r["phase"] == "NATIVE_READY"]) != 1:
        raise ValueError("sensor readiness not established")
    evaluation = [
        json.loads(line)
        for line in (episode / "controller_evaluation.jsonl").read_text().splitlines()
    ]
    if len(evaluation) != len(m["captures"]):
        raise ValueError("post-step tracking population mismatch")
    primary = classify(m)
    terminal_index, terminal_time, _, _ = terminal_boundary(m)
    holds = []
    for prediction in m["inference"]:
        frame = prediction["frame"]
        command = prediction["command"]
        if (
            len(command) != 3
            or not all(math.isfinite(float(x)) for x in command)
            or not (0 <= command[0] <= 0.1 and command[1] == 0 and abs(command[2]) <= 0.4)
        ):
            raise ValueError("policy command outside frozen envelope")
        window = evaluation[frame : min(frame + 6, len(evaluation))]
        if any(r["command"] != command for r in window):
            raise ValueError("requested/held command mismatch")
        holds.append(
            dict(
                frame=frame,
                window="task" if frame < terminal_index else "tail",
                **score_command(window, (command[0], command[2])),
            )
        )
    start = first["predecision_sim_time"]
    task_holds = [r for r in holds if r["frame"] < terminal_index]
    task_contacts = [r for r in m["contacts"] if start <= r["time"] <= terminal_time]
    tail_contacts = [r for r in m["contacts"] if r["time"] > terminal_time]
    primary.update(
        task_exposure_s=terminal_time - start,
        total_capture_exposure_s=m["captures"][-1]["simulation_time"] - start,
        terminal_time_s=terminal_time - start,
        task_contacts=contact_counts(task_contacts),
        tail_contacts=contact_counts(tail_contacts),
        all_contacts=contact_counts(m["contacts"]),
        settling_contacts=contact_counts(m["start_settling"]["contacts"]),
        postcapture_stop_distance_m=None
        if primary["stop_frame"] is None
        else m["captures"][primary["stop_frame"]]["distance_to_goal_m"],
        final_distance_m=m["captures"][-1]["distance_to_goal_m"],
    )
    raw = [
        json.loads(line)
        for line in (episode / "imu_controller_readings.jsonl").read_text().splitlines()
    ]
    if not raw or any(not r.get("valid") for r in raw):
        raise ValueError("native controller readings absent/invalid")
    return dict(
        integrity="PASS",
        role=role,
        outcome=primary,
        boundary=boundary,
        first_tensors=tensors,
        tracking_holds=holds,
        tracking=tracking_summary(holds, terminal_index),
        native_readings=len(raw),
        near_zero_uncovered=dict(
            holds=sum(r["near_zero_uncovered"] for r in task_holds),
            exposure_s=sum(r["exposure_s"] for r in task_holds if r["near_zero_uncovered"]),
            commanded_abs_yaw_rad=sum(
                abs(r["expected_turn_rad"]) for r in task_holds if r["near_zero_uncovered"]
            ),
            commanded_distance_m=sum(
                r["commanded_distance_m"] for r in task_holds if r["near_zero_uncovered"]
            ),
        ),
        scope="two known-development pairs; not unseen-layout generalization",
    ), episode
