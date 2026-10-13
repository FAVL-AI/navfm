"""Approval-gated parent for one technical camera qualification attempt."""

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

from navfm.collection.static_arrival_camera_qualification import (  # noqa: E402
    build_qualification,
    run_one_shot,
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
    config_path = ROOT / "configs/eval/static_arrival_camera_qualification_v1.json"
    config = json.loads(config_path.read_text())
    if config != build_qualification(ROOT):
        parser.error("qualification freeze/config/source binding mismatch")
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    except subprocess.CalledProcessError:
        parser.error("cannot verify repository freeze")
    if args.freeze != head or dirty:
        parser.error("exact clean approved commit required")
    worker_python = config["runtime"]["worker_python"]
    if not Path(worker_python).is_file():
        parser.error("bound Isaac worker interpreter is unavailable")
    allowed_root = Path(config["evidence"]["root"]).expanduser().resolve()
    if not args.out.expanduser().resolve().is_relative_to(allowed_root):
        parser.error("output must remain inside the bound external evidence root")
    command = [
        worker_python,
        str(ROOT / "scripts/static_arrival_camera_qualification_worker_v1.py"),
    ]
    try:
        result = run_one_shot(
            config=config,
            output=args.out,
            registry=Path(config["evidence"]["registry"]).expanduser(),
            freeze=args.freeze,
            worker_command=command,
            root=ROOT,
            process_started_monotonic=RUNNER_STARTED_MONOTONIC,
        )
    except BaseException as exc:
        print(f"QUALIFICATION_FAIL: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(
        json.dumps(
            {
                "status": result["status"],
                "frames": result["frame_count"],
                "occupied_wall_seconds": result["occupied_wall_seconds"],
                "dataset_admission": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
