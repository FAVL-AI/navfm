"""Frozen observable-state and history comparisons for the bounded diagnostic."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "configs/eval/initialization_diagnostic_v1.json"
FILES = [
    "tests/test_initialization_diagnostic.py",
    "scripts/initialization_diagnostic.py",
    "scripts/collect_initialization_diagnostic.py",
    "scripts/run_initialization_diagnostic.py",
    "scripts/reconstruct_initial_policy.py",
    "configs/eval/initialization_diagnostic_v1.json",
    "docs/INITIALIZATION_DIAGNOSTIC_V1_PLAN.md",
    "src/navfm/isaac/robot.py",
    "src/navfm/collection/yaw_rate_tracker.py",
    "src/navfm/collection/rgb_baseline.py",
    "src/navfm/collection/topomap.py",
    "src/navfm/collection/arrival_confirmation.py",
    "src/navfm/kinematics.py",
    "src/navfm/target_selection.py",
    "src/navfm/control.py",
    "src/navfm/upstream.py",
    "src/navfm/models/loader.py",
    "configs/eval/prospective_r2_recovery_v1.json",
]
HISTORY_INDICES = [5, 11, 17, 23, 29, 35]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(REPO), *args])


def frozen(commit: str, *, launch: bool = False) -> dict:
    commit = git("rev-parse", commit).decode().strip()
    if launch and (
        git("status", "--porcelain") or git("rev-parse", "HEAD").decode().strip() != commit
    ):
        raise ValueError("Launch requires clean exact freeze HEAD")
    for name in FILES:
        if (REPO / name).read_bytes() != git("show", f"{commit}:{name}"):
            raise ValueError(f"Frozen source drift: {name}")
    cfg = json.loads(CONFIG.read_text())
    for path, digest in cfg["asset_sha256"].items():
        if sha(Path(path)) != digest:
            raise ValueError(f"Asset drift: {path}")
    return cfg


def quat_error(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    return math.degrees(2 * math.acos(float(np.clip(abs(np.dot(a, b)), 0, 1))))


def yaw(q) -> float:
    w, x, y, z = q
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def gray_mad(a: Path, b: Path) -> float:
    av = np.asarray(Image.open(a).convert("L"), float)
    bv = np.asarray(Image.open(b).convert("L"), float)
    if av.shape != bv.shape:
        raise ValueError("Image shape mismatch")
    return float(np.abs(av - bv).mean())


def history(frames: list[dict]) -> list[dict]:
    if len(frames) != 36 or [f["physical_step"] for f in frames] != list(range(1, 37)):
        raise ValueError("History requires exactly ordered 36 live captures")
    return [frames[i] for i in HISTORY_INDICES]


def compare(a: dict, b: dict, out: Path, bounds: dict) -> dict:
    """No exemption for replaced history ages; missing state cannot match."""
    failures, metrics = [], {}

    def check(name, value, bound):
        metrics[name] = float(value)
        if not math.isfinite(value) or value > bound:
            failures.append(name)

    for key in ["root", "camera_world", "camera_local"]:
        ap, bp = np.asarray(a[key]["position"]), np.asarray(b[key]["position"])
        check(key + "_xy_m", float(np.linalg.norm(ap[:2] - bp[:2])), bounds["xy_m"])
        check(key + "_z_m", abs(float(ap[2] - bp[2])), bounds["z_m"])
        check(
            key + "_quaternion_deg",
            quat_error(a[key]["quaternion"], b[key]["quaternion"]),
            bounds["quaternion_deg"],
        )
    check(
        "yaw_deg",
        math.degrees(
            abs(
                math.atan2(
                    math.sin(yaw(a["root"]["quaternion"]) - yaw(b["root"]["quaternion"])),
                    math.cos(yaw(a["root"]["quaternion"]) - yaw(b["root"]["quaternion"])),
                )
            )
        ),
        bounds["yaw_deg"],
    )
    for key, bound in [
        ("joint_positions", "joint_position"),
        ("joint_velocities", "joint_velocity"),
        ("joint_position_targets", "controller"),
        ("joint_velocity_targets", "controller"),
        ("root_velocity", "root_velocity"),
        ("held_command", "controller"),
    ]:
        av, bv = np.asarray(a[key], float), np.asarray(b[key], float)
        if av.shape != bv.shape or av.size == 0:
            failures.append(key + "_shape")
            continue
        check(key, float(np.max(np.abs(av - bv))), bounds[bound])
    check(
        "controller_integral",
        abs(a["controller_integral"] - b["controller_integral"]),
        bounds["controller"],
    )
    for key in ["settings", "dof_names", "proxy_policy", "asset_sha256"]:
        if a[key] != b[key]:
            failures.append(key)
    if len(a["history"]) != 6 or len(b["history"]) != 6:
        raise ValueError("Exactly six history buffers required")
    for i, (ah, bh) in enumerate(zip(a["history"], b["history"], strict=True)):
        check(
            f"history_{i}_gray_mad",
            gray_mad(out / ah["image"], out / bh["image"]),
            bounds["gray_mad"],
        )
        check(
            f"history_{i}_relative_age_s",
            abs((a["sim_time"] - ah["sensor_time"]) - (b["sim_time"] - bh["sensor_time"])),
            bounds["history_age_s"],
        )
        if ah["physical_step"] != bh["physical_step"]:
            failures.append(f"history_{i}_index")
    for label, s in [("a", a), ("b", b)]:
        check(
            label + "_capture_clock_s",
            abs(s["sensor_time"] - s["sim_time"]),
            bounds["capture_clock_s"],
        )
        if s.get("unknown") or s.get("mechanical_ok") is not True:
            failures.append(label + "_unverified_state")
        if s["history"][-1]["image"] != s["image"]:
            failures.append(label + "_stale_live_history")
    return dict(
        passed=not failures,
        failures=failures,
        metrics=metrics,
        first_bound_violation=failures[0] if failures else None,
        first_numeric_difference=next((k for k, v in metrics.items() if v > 0), None),
    )


def raw_rgb_sha(path: Path) -> str:
    return hashlib.sha256(
        np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8).tobytes()
    ).hexdigest()


def normalized_prediction(pred: dict) -> dict:
    fields = [
        "window_distances",
        "requested_goal_distance",
        "waypoint_normalized",
        "command",
        "predicted_distance",
        "chain",
        "policy_stop",
    ]
    result = {key: pred[key] for key in fields}
    result["policy_abstain"] = pred.get("policy_abstain")
    return result


def validate_render_interval(
    before: float, after: float, delta: float, feedback_updates: int
) -> None:
    if abs(after - before - delta) > 1e-6:
        raise ValueError("Unexpected physics clock advance during render")
    expected = 10 if delta > 0 else 0
    if feedback_updates != expected:
        raise ValueError(
            f"Unqualified physics feedback count: {feedback_updates}, expected {expected}"
        )


def recorded_state_fields(state: object, keys: list[str]) -> dict:
    """Match preserved collector semantics for fields absent from B1x."""
    return {key: getattr(state, key, None) for key in keys}
