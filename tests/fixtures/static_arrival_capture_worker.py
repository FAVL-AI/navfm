"""Harmless subprocess used only to test capture supervision and finalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--family-input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("success", "failure", "hang"), default="success")
    parser.add_argument("--parent-nonce", required=True)
    args = parser.parse_args()
    if os.environ.get("NAVFM_STATIC_ARRIVAL_PARENT_NONCE") != args.parent_nonce:
        raise SystemExit(17)
    if args.mode == "hang":
        time.sleep(3)
        raise SystemExit(18)
    family = json.loads(args.family_input.read_text())
    if args.mode == "failure":
        (args.out / "partial.capture").write_text("preserved partial fixture\n")
        raise SystemExit(7)

    rows = []
    for frame in family["frames"]:
        relative = Path("policy_inputs") / "images" / f"{frame['image_id']}.fixture"
        path = args.out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"harmless synthetic image fixture {frame['image_id']}".encode()
        path.write_bytes(payload)
        rows.append(
            {
                "image_id": frame["image_id"],
                "episode_id": frame["episode_id"],
                "role": frame["role"],
                "status": "PASS",
                "image_path": str(relative),
                "image_sha256": hashlib.sha256(payload).hexdigest(),
                "fixture_only": True,
            }
        )
    report = {
        "schema": "static_arrival_camera_capture_v2",
        "status": "PASS",
        "family": family["family"],
        "fixture_only": True,
        "camera_config": family["camera"],
        "schedule_sha256": family["schedule_sha256"],
        "source_bindings_sha256": family["source_bindings_sha256"],
        "family_input_sha256": hashlib.sha256(
            json.dumps(family, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
        "frames": rows,
    }
    (args.out / "capture_report.json").write_text(json.dumps(report))
    expected_queries = [frame for frame in family["frames"] if frame["role"] == "query"]
    label_dir = args.out / "evaluator_only"
    label_dir.mkdir(parents=True, exist_ok=True)
    (label_dir / "geometric_labels.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "image_id": row["image_id"],
                    "access": "EVALUATOR_ONLY_NOT_DECISION_INPUT",
                }
            )
            + "\n"
            for row in expected_queries
        )
    )


if __name__ == "__main__":
    main()
