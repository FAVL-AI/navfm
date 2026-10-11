"""Fail closed on stale sensor data before admitting a prospective collection."""
from __future__ import annotations

import json
import math
import pickle
from pathlib import Path
from typing import Any

import numpy as np


def validate_capture(rgb: Any, pose: Any, *, command_time: float,
                     capture_time: float, sensor_time: float,
                     previous_sensor_time: float | None,
                     resolution: tuple[int, int], dt: float) -> None:
    values = [command_time, capture_time, sensor_time, *pose]
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError("nonfinite capture time or pose")
    if not math.isclose(capture_time-command_time, dt, abs_tol=1e-8):
        raise ValueError(f"capture cadence differs from requested simulation dt: "
                         f"observed={capture_time-command_time}, requested={dt}")
    if not math.isclose(sensor_time, capture_time, abs_tol=1e-8):
        raise ValueError(f"stale sensor timestamp: sensor={sensor_time}, capture={capture_time}")
    if previous_sensor_time is not None and sensor_time <= previous_sensor_time:
        raise ValueError("sensor timestamp did not advance")
    a = np.asarray(rgb)
    if a.shape != (resolution[1], resolution[0], 3) or a.dtype != np.uint8:
        raise ValueError(f"invalid RGB shape/dtype: {a.shape}/{a.dtype}")
    if a.max() == a.min():
        raise ValueError("constant RGB image; scene visibility unresolved")


def require_scientific_preflight(decision: Any) -> None:
    if not decision.scientific_collection_permitted or decision.to_dict()["test_double_present"]:
        raise RuntimeError(f"scientific preflight blocked: {decision.unsatisfied}")


def verify_saved_recording(path: Path, captures: list[dict[str, Any]],
                           resolution: tuple[int, int]) -> None:
    """Read back a trusted recording produced by this process, never foreign pickle."""
    from PIL import Image

    from .recording import validate_records

    with (path / "traj_data.pkl").open("rb") as stream:
        poses = pickle.load(stream)
    transitions = json.loads((path / "transitions.json").read_text())["records"]
    validate_records(transitions, len(captures))
    if set(poses) != {"position", "yaw"}:
        raise ValueError("pickle contains fields beyond position/yaw")
    if len(list(path.glob("*.jpg"))) != len(captures):
        raise ValueError("saved image count differs from captures")
    # The writer stores yaw unwrapped (the GNM format requires continuous yaw), so
    # the expected yaw is the writer's own transform of the captured yaws, not the
    # raw wrapped value: a heading through +/-pi is not a corrupted pose.
    from navfm.kinematics import unwrap_yaw

    raw_yaw = np.asarray([c["pose"][2] for c in captures], dtype=float)
    expected_yaw = unwrap_yaw(raw_yaw)
    stored_yaw = np.asarray(poses["yaw"], dtype=float).reshape(-1)
    # The property itself, independent of unwrap_yaw: the stored yaw is the
    # captured yaw modulo 2*pi and is continuous (no step beyond pi).
    if stored_yaw.shape != raw_yaw.shape or not np.allclose(
            np.angle(np.exp(1j * (stored_yaw - raw_yaw))), 0., rtol=0., atol=1e-8):
        raise ValueError("saved pose differs from captured pose (yaw modulo 2*pi)")
    if stored_yaw.size > 1 and np.abs(np.diff(stored_yaw)).max() > np.pi:
        raise ValueError("saved pose yaw is not continuous")
    for i, capture in enumerate(captures):
        with Image.open(path / f"{i}.jpg") as image:
            image.load()
            if image.size != resolution:
                raise ValueError("saved image resolution mismatch")
        observed_pose = [*poses["position"][i], float(np.asarray(poses["yaw"][i]).item())]
        expected_pose = [*capture["pose"][:2], float(expected_yaw[i])]
        if len(capture["pose"]) != 3 or not np.allclose(
                observed_pose, expected_pose, rtol=0., atol=1e-8):
            raise ValueError("saved pose differs from captured pose")
        if transitions[i]["time_after"] != capture["simulation_time"]:
            raise ValueError("saved transition timestamp differs from capture")
