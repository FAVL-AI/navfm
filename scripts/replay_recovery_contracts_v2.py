"""Observer-window v2: exact call/product/native callback order before digest."""

from __future__ import annotations

import json
import math
from pathlib import Path

from initialization_diagnostic import REPO, git, sha
from replay_recovery_contracts import FILES as V1_FILES
from replay_recovery_contracts import boundary_history
from replay_recovery_contracts import compare_pair as compare_pair
from replay_recovery_contracts import forced_entry as forced_entry
from replay_recovery_contracts import snapshot as snapshot

OLD_FREEZE = "d74927f7f2e88dd75e20f13646dc22f8e05c5671"
CONFIG = REPO / "configs/eval/replay_recovery_validation_v2.json"
FILES = [
    *V1_FILES,
    "scripts/replay_recovery_contracts_v2.py",
    "scripts/collect_replay_recovery_validation_v2.py",
    "scripts/run_replay_recovery_validation_v2.py",
    "tests/test_replay_recovery_contracts_v2.py",
    "configs/eval/replay_recovery_validation_v2.json",
    "docs/OBSERVER_WINDOW_V2_PROTOCOL.md",
]


def frozen(commit: str, *, launch: bool = False) -> dict:
    commit = git("rev-parse", commit).decode().strip()
    if launch and (
        git("status", "--porcelain") or git("rev-parse", "HEAD").decode().strip() != commit
    ):
        raise ValueError("Clean exact v2 freeze HEAD required")
    for name in V1_FILES:
        if (REPO / name).read_bytes() != git("show", f"{OLD_FREEZE}:{name}"):
            raise ValueError("Protected failed-v1 source drift: " + name)
    for name in FILES:
        if (REPO / name).read_bytes() != git("show", f"{commit}:{name}"):
            raise ValueError("Frozen v2 source drift: " + name)
    cfg = json.loads(CONFIG.read_text())
    for name, digest in cfg["asset_sha256"].items():
        if sha(Path(name)) != digest:
            raise ValueError("Asset drift: " + name)
    return cfg


def arm_observation(report: dict, events: list[dict]) -> None:
    """Keep the live list in the failure record before any setter/render/capture."""
    report["kidnap_acquisition_events"] = events
    report["kidnap_acquisition_before"] = len(events)


def event_membership(trace: dict) -> list[dict]:
    rows = []
    for i, event in enumerate(trace.get("kidnap_acquisition_events", [])):
        kind = "unknown"
        if (
            event.get("supported")
            and isinstance(event.get("render_product"), str)
            and "render_call_index" in event
        ):
            if event["render_product"] != trace.get("boundary_render_product"):
                kind = "unrelated_product"
            elif event["render_call_index"] != trace.get("boundary_render_call_index"):
                kind = "outside_boundary_call"
            else:
                kind = "boundary_member_unqualified"
        rows.append(dict(sequence=i, classification=kind))
    return rows


def classify_acquisitions(trace: dict) -> dict:
    events = trace.get("kidnap_acquisition_events", [])
    if (
        trace.get("kidnap_acquisition_before") != 0
        or not trace.get("acquisition_subscription_present")
        or not events
    ):
        raise ValueError("Missing measured acquisitions")
    call = trace["boundary_render_call_index"]
    product = trace["boundary_render_product"]
    classifications = []
    candidates = []
    last_exit = -1
    last_relevant = None
    for i, event in enumerate(events):
        if (
            event.get("sequence") != i
            or not event.get("supported")
            or not event.get("actual_callback_completed")
        ):
            raise ValueError("Unknown or ambiguous event provenance")
        enter, complete = event.get("callback_enter_order"), event.get("camera_complete_order")
        if (
            not isinstance(enter, int)
            or not isinstance(complete, int)
            or not last_exit < enter < complete
            or event.get("registration_order") != 0
        ):
            raise ValueError("Invalid native acquisition ordering")
        last_exit = complete
        if not isinstance(event.get("render_product"), str) or "render_call_index" not in event:
            raise ValueError("Unknown product/call membership")
        member = event["render_call_index"]
        if member is not None and (not isinstance(member, int) or member < 0 or member > call):
            raise ValueError("Ambiguous call membership")
        if event["render_product"] != product:
            classifications.append(dict(sequence=i, classification="unrelated_product"))
            continue
        last_relevant = i
        read = event.get("rgb_read_order")
        if (
            not isinstance(read, int)
            or not complete < read
            or not math.isfinite(event.get("sim_time", float("nan")))
            or not math.isfinite(event.get("camera_sensor_time", float("nan")))
        ):
            raise ValueError("Incomplete RGB acquisition order/time")
        last_exit = read
        if member != call:
            classifications.append(dict(sequence=i, classification="outside_boundary_call"))
        else:
            candidates.append(i)
            classifications.append(dict(sequence=i, classification="boundary_acquisition"))
    if not candidates or last_relevant != candidates[-1]:
        raise ValueError("Missing or ambiguous final boundary acquisition")
    chosen = candidates[-1]  # Chronological last actual completion, never digest search.
    value = events[chosen]
    if (
        value["rgb_sha256"] != trace["boundary_raw_rgb_sha256"]
        or abs(value["sim_time"] - trace["boundary"]["sim_time"]) > 1e-8
        or abs(value["camera_sensor_time"] - value["sim_time"]) > 1e-8
    ):
        raise ValueError("Final ordered boundary acquisition does not match saved RGB/time")
    for row in classifications:
        if row["classification"] == "boundary_acquisition":
            row["classification"] = (
                "qualified_final_boundary"
                if row["sequence"] == chosen
                else "superseded_boundary_acquisition"
            )
    return dict(
        events=classifications,
        qualified_sequence=chosen,
        qualified_call=call,
        qualified_product=product,
    )


def acquisition_ok(trace: dict) -> None:
    classify_acquisitions(trace)


def trace_ok(trace: dict, cfg: dict, root: Path) -> None:
    from initialization_diagnostic import validate_render_interval
    from initialization_diagnostic_v2 import bootstrap_ok, eligibility_ok

    if (
        trace.get("status") != "PASS"
        or not trace.get("source_asset_preflight_and_postflight_match")
        or trace.get("recovery_invocations") != 0
    ):
        raise ValueError("Trace cannot qualify")
    acquisition_ok(trace)
    bootstrap_ok(trace["bootstrap"])
    eligibility_ok(trace["eligibility"], trace["startup_dlss_mode"])
    if trace["case"] != cfg["first_case"] or trace["boundary_policy"]["backend"] != "cuda":
        raise ValueError("Undeclared case/backend")
    if [x["physical_step"] for x in trace["learned_invocations"]] != cfg["invocation_steps"]:
        raise ValueError("Learned invocation schedule drift")
    capture_map = {
        x["physical_step"]: x for x in trace["captures"] if x["image"].startswith("script_")
    }
    for invocation in trace["learned_invocations"]:
        index = invocation["physical_step"]
        selected = [capture_map[j] for j in range(6, index + 1, 6)]
        expected_buffers = [trace["initial"]] * (6 - len(selected)) + selected
        expected_buffers = [
            {k: x[k] for k in ["image", "image_sha256", "sensor_time", "sim_time", "physical_step"]}
            for x in expected_buffers
        ]
        if (
            invocation["history"] != expected_buffers
            or invocation["requested_command_applied"] is not False
        ):
            raise ValueError("Learned input history/application drift")
    for record in trace["render_calls"][1:]:
        validate_render_interval(
            record["before_sim_time"],
            record["after_sim_time"],
            record["requested_delta_s"],
            record["feedback_updates"],
        )
    for value in trace["captures"]:
        if (
            value.get("unknown")
            or not value["mechanical_ok"]
            or sha(root / value["image"]) != value["image_sha256"]
            or abs(value["sim_time"] - value["sensor_time"]) > 1e-8
        ):
            raise ValueError("Capture integrity failure")
    frames = [x for x in trace["captures"] if x["image"].startswith("script_")]
    if boundary_history(frames, trace["boundary"]) != trace["boundary"]["history"]:
        raise ValueError("Boundary buffers changed")
    if trace["boundary_policy"] != trace["policy_after_kidnap"]:
        raise ValueError("Post-kidnap learned state changed without invocation")
    before, after = trace["policy_before_kidnap"], trace["policy_after_kidnap"]
    expected = json.loads(json.dumps(before))
    expected["state"].update(lost=True, reached_goal=False, _far=0, _pending=[])
    if "attempts" in expected["state"]:
        expected["state"].update(attempts=1, _scan=0, recovery_failed=False)
    expected["counters"].update(
        stop_count=0, stopped=False, abstained=None, verified_count=0, chain_reached_decisions=0
    )
    expected["search_window"] = [0, expected["state"]["goal_node"]]
    if after != expected:
        raise ValueError("Undeclared policy reset")
    import numpy as np

    actual, intent = trace["boundary"], trace["kidnap_intent"]
    from initialization_diagnostic import quat_error

    if (
        np.linalg.norm(np.asarray(actual["root"]["position"]) - intent["position"]) > 0.002
        or quat_error(actual["root"]["quaternion"], intent["quaternion"]) > 0.2
    ):
        raise ValueError("Kidnap pose readback failed")
    for key in ["root_velocity", "joint_positions", "joint_velocities", "held_command"]:
        if not np.allclose(actual[key], intent[key], atol=1e-6, rtol=0):
            raise ValueError("Kidnap state readback failed: " + key)
    if (
        actual["controller_integral"] != 0
        or any(actual["joint_position_targets"])
        or any(actual["joint_velocity_targets"])
    ):
        raise ValueError("Kidnap controller/targets not zero")
