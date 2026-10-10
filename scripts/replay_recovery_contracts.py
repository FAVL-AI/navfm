"""Frozen first-pair actual-policy and timestamped history boundary contracts."""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

from initialization_diagnostic import REPO, git, sha
from initialization_diagnostic_v2 import FILES as OLD_FILES

CONFIG = REPO / "configs/eval/replay_recovery_validation_v1.json"
OLD_FREEZE = "0393d46e814c80f2cc53ff9570af2c4015da2e7a"
FILES = [
    *OLD_FILES,
    "src/navfm/collection/perturbation.py",
    "scripts/replay_recovery_contracts.py",
    "scripts/collect_replay_recovery_validation.py",
    "scripts/run_replay_recovery_validation.py",
    "tests/test_replay_recovery_contracts.py",
    "configs/eval/replay_recovery_validation_v1.json",
    "docs/PROSPECTIVE_R2_REPLAY_PROTOCOL_V1.md",
]


def frozen(commit: str, *, launch: bool = False) -> dict:
    commit = git("rev-parse", commit).decode().strip()
    if launch and (
        git("status", "--porcelain") or git("rev-parse", "HEAD").decode().strip() != commit
    ):
        raise ValueError("Clean exact freeze HEAD required")
    for name in OLD_FILES:
        if (REPO / name).read_bytes() != git("show", f"{OLD_FREEZE}:{name}"):
            raise ValueError("Protected freeze drift: " + name)
    for name in FILES:
        if (REPO / name).read_bytes() != git("show", f"{commit}:{name}"):
            raise ValueError("Frozen source drift: " + name)
    cfg = json.loads(CONFIG.read_text())
    for name, digest in cfg["asset_sha256"].items():
        if sha(Path(name)) != digest:
            raise ValueError("Asset drift: " + name)
    return cfg


COUNTERS = ["stop_count", "stopped", "abstained", "verified_count", "chain_reached_decisions"]
STATE_FIELDS = {
    "goal_node",
    "closest_node",
    "reached_goal",
    "history",
    "bounded",
    "lost",
    "_far",
    "_pending",
}
R2_FIELDS = {"recovery", "recovery_failed", "attempts", "_scan"}


def snapshot(policy) -> dict:
    expected = STATE_FIELDS | (R2_FIELDS if policy.recovery is not None else set())
    if set(vars(policy.state)) != expected or policy.confirm is not None:
        raise ValueError("Unsupported actual policy state/confirmation schema")
    value = dict(
        state_class=type(policy.state).__name__,
        state=dataclasses.asdict(policy.state),
        counters={key: getattr(policy, key) for key in COUNTERS},
        confirmation=None,
        search_window=list(policy.state.window(policy.topomap_cfg)),
        backend=policy.device,
        checkpoint=policy.digest,
        config=policy.manifest,
        chain_length=len(policy.chain),
    )
    json.dumps(value, allow_nan=False)
    return value


def forced_entry(policy) -> tuple[dict, dict]:
    before = snapshot(policy)
    state = policy.state
    state.lost, state.reached_goal, state._far, state._pending = True, False, 0, []
    if policy.recovery is not None:
        state.attempts, state._scan, state.recovery_failed = 1, 0, False
    policy.stop_count, policy.stopped, policy.abstained = 0, False, None
    policy.verified_count, policy.chain_reached_decisions = 0, 0
    after = snapshot(policy)
    if (
        before["state"]["closest_node"] != after["state"]["closest_node"]
        or before["state"]["history"] != after["state"]["history"]
    ):
        raise ValueError("Inferred node/history changed at kidnap")
    return before, after


def boundary_history(frames: list[dict], current: dict) -> list[dict]:
    if len(frames) != 36 or [x["physical_step"] for x in frames] != list(range(1, 37)):
        raise ValueError("Ordered 36 physical frames required")
    current = dict(current)
    current.pop("history", None)
    result = [frames[i] for i in [5, 11, 17, 23, 29]] + [current]
    if current["physical_step"] != 36 or current["image"].startswith("script_"):
        raise ValueError("Current history must be post-kidnap live image")
    for frame, age in zip(result, [2.5, 2, 1.5, 1, 0.5, 0], strict=True):
        if (
            abs(current["sim_time"] - frame["sensor_time"] - age) > 1e-6
            or abs(frame["sensor_time"] - frame["sim_time"]) > 1e-8
        ):
            raise ValueError("Invalid kidnap boundary age/clock")
    return result


def equivalent(a, b, *, atol: float = 1e-3, rtol: float = 1e-5) -> bool:
    """Numerical heads/state distances bounded; discrete fields remain exact."""
    if isinstance(a, float) and isinstance(b, (float, int)) and not isinstance(b, bool):
        return (
            math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, abs_tol=atol, rel_tol=rtol)
        )
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k], atol=atol, rtol=rtol) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(
            equivalent(x, y, atol=atol, rtol=rtol) for x, y in zip(a, b, strict=True)
        )
    return a == b


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


def compare_pair(reference: dict, replay: dict, root: Path, cfg: dict) -> dict:
    from initialization_diagnostic import compare

    rows = []
    for ra, rb in zip(
        [
            reference["initial"],
            *[x for x in reference["captures"] if x["image"].startswith("script_")],
            reference["boundary"],
        ],
        [
            replay["initial"],
            *[x for x in replay["captures"] if x["image"].startswith("script_")],
            replay["boundary"],
        ],
        strict=True,
    ):
        states = []
        for trace, value in [(reference, ra), (replay, rb)]:
            value = json.loads(json.dumps(value))
            value.setdefault("history", [json.loads(json.dumps(value)) for _ in range(6)])
            directory = cfg["authorized_processes"][["reference", "replay"].index(trace["role"])]
            value["image"] = directory + "/" + value["image"]
            for item in value["history"]:
                item["image"] = directory + "/" + item["image"]
            states.append(value)
        rows.append(compare(states[0], states[1], root, cfg["bounds"]))
    runtime_match = reference["observed_learned_runtime"] == replay["observed_learned_runtime"]
    learned = []
    for a, b in zip(reference["learned_invocations"], replay["learned_invocations"], strict=True):
        learned.append(
            all(
                equivalent(a[k], b[k], atol=cfg["output_atol"], rtol=cfg["output_rtol"])
                for k in ["before", "prediction", "after"]
            )
        )
    boundary_state = equivalent(
        reference["policy_before_kidnap"], replay["policy_before_kidnap"]
    ) and equivalent(reference["boundary_policy"], replay["boundary_policy"])
    passed = all(x["passed"] for x in rows) and all(learned) and boundary_state and runtime_match
    return dict(
        passed=passed,
        physical_history_comparisons=rows,
        learned_invocations_match=learned,
        boundary_policy_match=boundary_state,
        learned_runtime_match=runtime_match,
        decision="MATCHED_FIRST_PAIR_ONLY" if passed else "INITIALIZATION_HANDOVER_FAIL",
        efficacy_claim=False,
        further_launches_authorized=False,
        cross_repeat_validated=False,
    )


def acquisition_ok(trace: dict) -> None:
    events = trace.get("kidnap_acquisition_events", [])
    before = trace.get("kidnap_acquisition_before")
    if before is None or not trace.get("acquisition_subscription_present") or len(events) <= before:
        raise ValueError("Unknown/stale post-kidnap acquisition")
    observed = events[before:]
    if any(not x.get("supported") for x in observed):
        raise ValueError("Unsupported acquisition provenance")
    if any(x["render_call_index"] != trace["boundary_render_call_index"] for x in observed):
        raise ValueError("Acquisition not from boundary rerender")
    last = observed[-1]
    if (
        last["rgb_sha256"] != trace["boundary_raw_rgb_sha256"]
        or abs(last["sim_time"] - trace["boundary"]["sim_time"]) > 1e-8
        or abs(last["camera_sensor_time"] - last["sim_time"]) > 1e-8
    ):
        raise ValueError("Boundary RGB does not match completed acquisition")
