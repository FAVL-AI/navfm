"""Harmless eight-frame subprocess fixture for the qualification supervisor."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT / "src"))
from prospective_data_contracts_v1 import float32_position  # noqa: E402

from navfm.collection.static_arrival_capture import canonical_sha256 as content_sha  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("success", "failure", "hang"), default="success")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--parent-nonce", required=True)
    args = parser.parse_args()
    if args.mode == "hang":
        time.sleep(5)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "partial.capture").write_text("fixture")
    if args.mode == "failure":
        raise SystemExit(7)
    worker_input = json.loads(args.input.read_text())
    frame_rows = []
    image_root = args.out / "policy_inputs" / "images"
    metadata_root = args.out / "capture_metadata"
    image_root.mkdir(parents=True)
    metadata_root.mkdir(parents=True)
    rng = np.random.default_rng(23)
    for index, frame in enumerate(worker_input["frames"]):
        image_id = frame["image_id"]
        pixels = rng.integers(0, 256, size=(240, 320, 3), dtype=np.uint8)
        image_path = image_root / f"{image_id}.jpg"
        Image.fromarray(pixels).save(image_path, quality=95)
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        body_x, body_y, yaw = frame["body_pose_xy_yaw_rad"]
        camera = worker_input["camera"]
        requested = [
            body_x + camera["forward_offset_m"] * math.cos(yaw),
            body_y + camera["forward_offset_m"] * math.sin(yaw),
            camera["camera_height_m"],
        ]
        represented = float32_position(requested)
        rendering_time = 10.0 + index * 0.25
        reference = {
            "referenceTimeNumerator": index + 1,
            "referenceTimeDenominator": 4,
        }
        row = {
            "image_id": image_id,
            "episode_id": frame["episode_id"],
            "role": frame["role"],
            "status": "PASS",
            "image_path": str(image_path.relative_to(args.out)),
            "image_sha256": digest,
            "camera": {"rendering_time": rendering_time, "rendering_frame": reference},
            "requested_camera_position": requested,
            "represented_float32_position": represented,
            "actual_camera_position": represented,
            "actual_camera_quaternion": [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)],
            "pose_author_time": rendering_time - 0.25,
            "hold_end_time": rendering_time,
            "rgb_shape": [240, 320, 4],
            "rgb_std": float(pixels.std()),
        }
        frame_rows.append(row)
        (metadata_root / f"{image_id}.json").write_text(
            json.dumps(
                {
                    "image_id": image_id,
                    "episode_id": frame["episode_id"],
                    "role": frame["role"],
                    "rendering_time": rendering_time,
                    "rendering_frame": reference,
                    "actual_camera_position": represented,
                    "actual_camera_quaternion": row["actual_camera_quaternion"],
                    "image_sha256": digest,
                },
                sort_keys=True,
            )
        )
    report = {
        "schema": "static_arrival_camera_qualification_v1",
        "status": "PASS",
        "qualification_only": True,
        "shutdown_returned": True,
        "bootstrap_compatibility_branch": [5, 0],
        "isaacsim_distribution_version": worker_input["expected_isaacsim_version"],
        "family": "TECHNICAL",
        "camera_config": worker_input["camera"],
        "schedule_sha256": worker_input["schedule_sha256"],
        "source_bindings_sha256": worker_input["source_bindings_sha256"],
        "worker_input_sha256": content_sha(worker_input),
        "frames": frame_rows,
    }
    (args.out / "capture_report.json").write_text(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
