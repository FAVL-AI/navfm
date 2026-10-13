"""Approval-gated parent for one static camera qualification v2 attempt."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

RUNNER_STARTED_MONOTONIC = time.monotonic()
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from static_arrival_camera_qualification_continuation_v2 import (  # noqa: E402
    build_config,
    run_once,
)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True, help="full reviewed commit SHA")
    parser.add_argument("--out", type=Path, required=True, help="new external evidence directory")
    parser.add_argument("--execute-approved", action="store_true")
    args = parser.parse_args()
    if not args.execute_approved:
        parser.error("PREPARATION ONLY: --execute-approved requires separate explicit approval")
    config_path = ROOT / "configs/eval/static_arrival_camera_qualification_v2.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config != build_config(ROOT):
            parser.error("qualification v2 freeze/config/source binding mismatch")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        parser.error(f"cannot verify qualification v2 freeze: {type(exc).__name__}")
    if args.freeze != head or dirty:
        parser.error("exact clean approved commit required")
    worker_python = config["runtime"]["worker_python"]
    if not Path(worker_python).is_file():
        parser.error("bound Isaac worker interpreter is unavailable")
    command = [
        worker_python,
        str(ROOT / "scripts/static_arrival_camera_child_bootstrap_v2.py"),
        "--worker",
        str(ROOT / "scripts/static_arrival_camera_qualification_worker_v2.py"),
    ]
    try:
        result = run_once(
            config=config,
            output=args.out,
            registry=Path(config["evidence"]["registry"]).expanduser(),
            freeze=args.freeze,
            worker_command=command,
            root=ROOT,
            process_started_monotonic=RUNNER_STARTED_MONOTONIC,
        )
    except BaseException as exc:
        print(f"QUALIFICATION_V2_FAIL: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(
        json.dumps(
            {
                "status": result["status"],
                "frames": result["frame_count"],
                "occupied_wall_seconds": result["occupied_wall_seconds"],
                "sdk_cleanup_completion": result["sdk_cleanup_completion"],
                "dataset_admission": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
