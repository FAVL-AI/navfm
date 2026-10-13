"""Six actual CLI parent lifecycles with constrained harmless children; no models."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "scripts/qualify_ravel_graph_continuation_v2.py"
CASES = (
    "success",
    "preflight_reject",
    "worker_fail",
    "timeout",
    "write_failure",
    "populated_directory",
)


def main():
    root = Path(sys.argv[1])
    root.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    results = []
    environment = dict(os.environ, CUDA_VISIBLE_DEVICES="", PYTHONPATH=str(REPO / "src"))
    for case in CASES:
        folder = root / case
        marker = None
        if case == "populated_directory":
            folder.mkdir()
            marker = folder / "attempt.json"
            marker.write_text('{"status":"EXISTING_IMMUTABLE_FIXTURE"}\n')
            original = hashlib.sha256(marker.read_bytes()).hexdigest()
        command = [
            sys.executable,
            str(LAUNCHER),
            "--freeze",
            head,
            "--out",
            str(folder / "result.json"),
            "--lifecycle-test-case",
            case,
        ]
        outcome = subprocess.run(
            command, cwd=REPO, env=environment, capture_output=True, text=True, timeout=5
        )
        (root / (case + ".stdout")).write_text(outcome.stdout)
        (root / (case + ".stderr")).write_text(outcome.stderr)
        status_path = (
            folder / "parent_status.json"
            if case != "populated_directory"
            else root / (case + ".refusal.json")
        )
        status = json.loads(status_path.read_text())
        assert outcome.returncode == (0 if case == "success" else 1)
        if case == "success":
            assert status["status"] == "PASS_LAUNCHER_LIFECYCLE_ONLY"
            assert status["reaped"] and status["worker_started"]
            assert (
                json.loads((folder / "attempt.json").read_text())["status"] == "PREFLIGHT_STARTED"
            )
            assert (
                json.loads((folder / "worker_start.json").read_text())["status"]
                == "LAUNCH_REQUESTED"
            )
        elif case == "worker_fail":
            assert status["exit_code"] == 7 and status["reaped"]
        elif case == "timeout":
            assert status["timeout"] and status["reaped"] and status["exit_code"] != 0
        elif case in ("preflight_reject", "write_failure"):
            assert (
                not status["worker_started"]
                and status["reaped"] is None
                and status["timeout"] is None
            )
            if case == "write_failure":
                assert (
                    json.loads((folder / "worker_start.json").read_text())["status"]
                    == "CONFLICT_TECHNICAL_FIXTURE"
                )
        else:
            assert hashlib.sha256(marker.read_bytes()).hexdigest() == original
            assert status["status"] == "FAIL_POPULATED_DIRECTORY_REFUSED"
        results.append(
            dict(case=case, CLI_exit=outcome.returncode, terminal=status, model_calls=0, forwards=0)
        )
        (root / "partial.json").write_text(json.dumps(results, indent=2) + "\n")
    elapsed = time.monotonic() - started
    assert elapsed <= 30
    (root / "result.json").write_text(
        json.dumps(
            dict(
                status="PASS_LAUNCHER_LIFECYCLE_ONLY",
                cases=6,
                model_calls=0,
                forwards=0,
                GPU_calls=0,
                wall_s=elapsed,
                launcher_sha256=hashlib.sha256(LAUNCHER.read_bytes()).hexdigest(),
            ),
            indent=2,
        )
        + "\n"
    )
    print("Six actual CLI lifecycle cases PASS; zero models/forwards/GPU")


if __name__ == "__main__":
    main()
