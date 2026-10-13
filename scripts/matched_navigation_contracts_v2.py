"""Finite development order and outcome contracts; no simulator inputs to policy."""

import math

ORDER = (
    "coverage-v2-0000",
    "dev-v2-release-a",
    "dev-v2-adapted-b",
    "dev-v2-adapted-c",
    "dev-v2-release-d",
)


def admit(records, launch, freeze):
    if launch not in ORDER or len(records) >= len(ORDER):
        raise ValueError("unknown or extra launch")
    if [r.get("id") for r in records] != list(ORDER[: len(records)]):
        raise ValueError("duplicate or out-of-order evidence")
    if any(r.get("freeze") != freeze or r.get("integrity") != "PASS" for r in records):
        raise ValueError("prior integrity failed or freeze drift")
    if ORDER[len(records)] != launch:
        raise ValueError("undeclared order")


def score_command(rows, command):
    v, w = command
    if not rows or not all(
        math.isfinite(float(r[k])) for r in rows for k in ("evaluation_v", "evaluation_w", "dt")
    ):
        raise ValueError("nonfinite tracking evaluation")
    late = rows[len(rows) // 2 :]
    mv = sum(r["evaluation_v"] for r in late) / len(late)
    mw = sum(r["evaluation_w"] for r in late) / len(late)
    exposure = sum(r["dt"] for r in rows)
    actual_turn = sum(r["evaluation_w"] * r["dt"] for r in rows)
    actual_distance = sum(r["evaluation_v"] * r["dt"] for r in rows)
    expected_turn = w * exposure
    checks = dict(
        translation=abs(mv - v) <= max(0.01, 0.25 * abs(v)),
        rate=abs(mw - w) <= max(0.002, 0.25 * abs(w)),
        sign=w == 0 or mw * w > 0,
        integrated_turn=abs(actual_turn - expected_turn) <= max(0.001, 0.25 * abs(expected_turn)),
        integrated_sign=w == 0 or actual_turn * w > 0,
    )
    return dict(
        command=list(command),
        mean_v=mv,
        mean_w=mw,
        exposure_s=exposure,
        actual_turn_rad=actual_turn,
        expected_turn_rad=expected_turn,
        actual_signed_distance_m=actual_distance,
        commanded_distance_m=v * exposure,
        near_zero_uncovered=(0 < abs(w) < 0.005 or 0 < v < 0.025),
        checks=checks,
        passed=all(checks.values()),
    )


def terminal_boundary(manifest):
    captures = manifest["captures"]
    terminals = [
        (manifest.get(key), kind)
        for key, kind in [("policy_stop_frame", "stop"), ("policy_abstain_frame", "abstain")]
        if manifest.get(key) is not None
    ]
    if not terminals:
        return len(captures), captures[-1]["simulation_time"], None, None
    index, kind = min(terminals)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(captures):
        raise ValueError("invalid terminal frame")
    decision = next((r for r in manifest["inference"] if r["frame"] == index), None)
    if decision is None:
        raise ValueError("missing terminal decision")
    return index, decision["predecision_sim_time"], kind, decision


def classify(manifest):
    captures = manifest["captures"]
    if not captures or any(not math.isfinite(float(c["distance_to_goal_m"])) for c in captures):
        raise ValueError("invalid outcome evidence")
    boundary, time, kind, decision = terminal_boundary(manifest)
    distance = None
    if decision is not None:
        goal = manifest["route"]["waypoints"][-1]
        goal = [goal[0], goal[1] + manifest["route"]["scene_index"] * 20.0]
        pose = decision["predecision_pose"]
        if not all(math.isfinite(float(x)) for x in [*pose, *goal, time]):
            raise ValueError("nonfinite terminal evaluation")
        distance = math.dist(pose[:2], goal)
    outcome = (
        ("correct_stop" if distance <= 0.5 else "wrong_stop")
        if kind == "stop"
        else "abstain"
        if kind == "abstain"
        else "timeout"
    )
    return dict(
        outcome=outcome,
        goal_visited=any(c["distance_to_goal_m"] <= 0.5 for c in captures[:boundary])
        or (distance is not None and distance <= 0.5),
        tail_goal_visited=any(c["distance_to_goal_m"] <= 0.5 for c in captures[boundary:]),
        frames=len(captures),
        task_capture_count=boundary,
        terminal_index=boundary,
        terminal_sim_time=time,
        first_stop_distance_m=distance if kind == "stop" else None,
        first_stop_signed_margin_m=0.5 - distance if kind == "stop" else None,
        stop_frame=manifest.get("policy_stop_frame"),
    )


def tracking_summary(holds, terminal_index):
    task = [r for r in holds if r["frame"] < terminal_index]
    tail = [r for r in holds if r["frame"] >= terminal_index]
    return dict(
        task_holds=len(task),
        tail_holds=len(tail),
        task_pass_fraction=sum(r["passed"] for r in task) / len(task) if task else None,
        tail_pass_fraction=sum(r["passed"] for r in tail) / len(tail) if tail else None,
    )


def contact_counts(records):
    counts = dict(support=0, floor_nonwheel=0, fixture=0, self_contact=0)
    for record in records:
        paths = record["paths"]
        robot = [p for p in paths if p.startswith("/World/Robot/")]
        others = [p for p in paths if not p.startswith("/World/Robot/")]
        if not robot or len(paths) != 2:
            raise ValueError("unknown contact actors")
        if not others:
            counts["self_contact"] += 1
        elif others[0].endswith("/Floor") and others[0].startswith("/World/Fixture/"):
            wheel = all(
                p.rsplit("/", 1)[-1] in ("fl_wheel", "fr_wheel", "rl_wheel", "rr_wheel")
                for p in robot
            )
            counts["support" if wheel else "floor_nonwheel"] += 1
        elif others[0].startswith("/World/Fixture/"):
            counts["fixture"] += 1
        else:
            raise ValueError("unknown contact environment")
    return counts


def verify_recorded_artifacts(root, record):
    from pathlib import Path

    from development_qualification_contracts_v1 import sha

    root = Path(root)
    artifacts = record.get("artifacts", {})
    required = (
        ["result.json", "attempt/imu_qualification.json"]
        if record["id"] == ORDER[0]
        else [
            "result.json",
            "episode/first_policy_input.png",
            "episode/first_policy_input.json",
            "episode/first_policy_tensors.json",
        ]
    )
    if any(name not in artifacts for name in required):
        raise ValueError("gate-consumed artifact missing from ledger")
    for name, digest in artifacts.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("invalid artifact path")
        file = root / path
        if file.is_symlink() or not file.is_file() or sha(file) != digest:
            raise ValueError("recorded artifact drift")
