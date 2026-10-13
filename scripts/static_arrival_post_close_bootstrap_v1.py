"""Bind the child environment and hand off to the lifecycle worker."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _event(output: Path, name: str) -> None:
    path = output / "lifecycle_events.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {"event": name, "clock": "time.monotonic_ns", "monotonic_ns": time.monotonic_ns()},
                sort_keys=True,
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    args, worker_args = parser.parse_known_args()
    root = Path(__file__).resolve().parents[1]
    output = Path(os.environ["NAVFM_POST_CLOSE_DIAGNOSTIC_OUT"]).resolve()
    nonce = os.environ.get("NAVFM_POST_CLOSE_PARENT_NONCE")
    if not nonce or len(nonce) != 64:
        raise RuntimeError("parent nonce missing or malformed")
    os.chdir(root)
    os.environ["OMNICLIENT_HUB_MODE"] = "disabled"
    os.environ["NAVFM_POST_CLOSE_CHILD_NONCE"] = nonce
    _event(output, "bootstrap_exec_handoff_requested")
    worker = args.worker or root / "scripts/static_arrival_post_close_worker_v1.py"
    worker = worker.resolve()
    if not worker.is_relative_to(root) or not worker.is_file():
        raise RuntimeError("worker must be an existing file inside the repository")
    os.execv(sys.executable, [sys.executable, str(worker), *worker_args])


if __name__ == "__main__":
    main()
