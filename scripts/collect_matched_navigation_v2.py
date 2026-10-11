"""Reuse the preserved collector with a first-input cold-start observer only."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    import torch

    if not torch.cuda.is_available():
        raise ValueError("CUDA required before policy or simulator creation")
    from navfm.collection import rgb_baseline

    out = Path(sys.argv[sys.argv.index("--out") + 1])
    original = rgb_baseline.RGBTopomapBaseline.step
    seen = False
    recording_tensor = False
    tensor_records = []
    original_tensor = rgb_baseline.RGBBaseline.tensor

    def observed_tensor(self, images):
        value = original_tensor(self, images)
        if recording_tensor:
            raw = value.detach().cpu().contiguous().numpy()
            tensor_records.append(
                dict(
                    shape=list(value.shape),
                    dtype=str(value.dtype),
                    sha256=hashlib.sha256(raw.tobytes()).hexdigest(),
                )
            )
        return value

    rgb_baseline.RGBBaseline.tensor = observed_tensor

    def observed(self, history, goal):
        nonlocal seen, recording_tensor
        if self.device != "cuda":
            raise ValueError("development policy device must be cuda")
        if not seen:
            from PIL import Image

            seen = True
            record = {
                "history_length": len(history),
                "counters": {"stop_count": self.stop_count, "stopped": self.stopped},
                "history_sha256": [hashlib.sha256(im.tobytes()).hexdigest() for im in history],
                "goal_rgb_sha256": hashlib.sha256(goal.tobytes()).hexdigest(),
                "state": __import__("dataclasses").asdict(self.state),
                "cold_start": "six reads/repeats of initial RGB; not six elapsed decision frames",
            }
            Image.fromarray(history[-1]).save(out / "first_policy_input.png")
            (out / "first_policy_input.json").write_text(json.dumps(record) + "\n")
        recording_tensor = not tensor_records
        try:
            return original(self, history, goal)
        finally:
            if recording_tensor:
                (out / "first_policy_tensors.json").write_text(json.dumps(tensor_records) + "\n")
            recording_tensor = False

    rgb_baseline.RGBTopomapBaseline.step = observed
    from navigation_imu_boundary_v2 import bind, initialize, record_tracking

    sensors = []

    def observed_initialize(robot, sim, xy, yaw, episode):
        sensor = initialize(robot, sim, xy, yaw, episode)
        sensors.append(sensor)
        return sensor

    source = ROOT / "scripts/collect_option1.py"
    try:
        exec(
            compile(bind(source.read_text()), str(source), "exec"),
            {
                "__name__": "__main__",
                "__file__": str(source),
                "initialize": observed_initialize,
                "record_tracking": record_tracking,
            },
        )
    finally:
        if sensors:
            (out / "imu_controller_readings.json").write_text(
                json.dumps({"source": sensors[0].path, "records": sensors[0].guard.records}) + "\n"
            )


if __name__ == "__main__":
    main()
