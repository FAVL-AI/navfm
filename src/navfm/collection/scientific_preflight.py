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
    for i, capture in enumerate(captures):
        with Image.open(path / f"{i}.jpg") as image:
            image.load()
            if image.size != resolution:
                raise ValueError("saved image resolution mismatch")
        observed_pose = [*poses["position"][i], float(np.asarray(poses["yaw"][i]).item())]
        if not np.allclose(observed_pose, capture["pose"], rtol=0., atol=1e-8):
            raise ValueError("saved pose differs from captured pose")
        if transitions[i]["time_after"] != capture["simulation_time"]:
            raise ValueError("saved transition timestamp differs from capture")
