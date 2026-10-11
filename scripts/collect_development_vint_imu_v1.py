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

    def observed(self, history, goal):
        nonlocal seen
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
        return original(self, history, goal)

    rgb_baseline.RGBTopomapBaseline.step = observed
    from imu_controller_boundary_v1 import BodyGyro, bind_collector_source

    sensors = []

    def sensor_factory(robot, sim):
        sensor = BodyGyro(robot, sim)
        sensor.evidence_path = out / "imu_controller_readings.jsonl"
        (out / "imu_sensor_metadata.json").write_text(json.dumps(sensor.metadata) + "\n")
        sensors.append(sensor)
        return sensor

    source = ROOT / "scripts/collect_option1.py"
    try:
        exec(
            compile(bind_collector_source(source.read_text()), str(source), "exec"),
            {"__name__": "__main__", "__file__": str(source), "BodyGyro": sensor_factory},
        )
    finally:
        if sensors:
            (out / "imu_controller_readings.json").write_text(
                json.dumps({"source": sensors[0].path, "records": sensors[0].guard.records}) + "\n"
            )


if __name__ == "__main__":
    main()
