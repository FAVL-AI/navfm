"""Pure freeze, launch and comparison contracts for development qualification."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORDER = (
    "compat-vint-release",
    "compat-vint-adapted",
    "compat-gnm-release",
    "compat-nomad-release",
    "dev-vint-release",
    "dev-vint-adapted",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def frozen(commit: str, cfg: dict) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != commit or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("exact clean freeze HEAD required")
    for item in cfg["inputs"]:
        if sha(Path(item["path"])) != item["sha256"]:
            raise ValueError("input drift: " + item["path"])
    for item in cfg["upstream_files"]:
        if sha(Path(cfg["upstream"]) / item["path"]) != item["sha256"]:
            raise ValueError("upstream drift: " + item["path"])


def next_launch(records: list[dict], launch: str) -> None:
    if any(r.get("event") not in ("start", "end") or r.get("id") not in ORDER for r in records):
        raise ValueError("unknown ledger record")
    if [r["event"] for r in records] != [
        e for _ in range(len(records) // 2) for e in ("start", "end")
    ]:
        raise ValueError("unclosed or nonalternating ledger")
    starts = [r["id"] for r in records if r["event"] == "start"]
    if (
        starts != list(ORDER[: len(starts)])
        or len(starts) >= len(ORDER)
        or ORDER[len(starts)] != launch
    ):
        raise ValueError("undeclared, duplicate or out-of-order launch")
    ends = [r for r in records if r["event"] == "end"]
    if len(ends) != len(starts) or any(r["status"] != "PASS" for r in ends):
        raise ValueError("previous attempt incomplete or failed; halt")
    if [r["id"] for r in ends] != starts:
        raise ValueError("end identities mismatch")


def compare_initial(a: dict, b: dict, image_mad: float) -> dict:
    import math

    failures = []
    if a["counters"] != {"stop_count": 0, "stopped": False} or b["counters"] != a["counters"]:
        failures.append("initial policy counters")
    if a["history_length"] != 6 or b["history_length"] != 6:
        failures.append("cold-start history length")
    if not math.isfinite(image_mad) or image_mad > 2.5:
        failures.append("initial RGB MAD")
    pa, pb = a["pose"], b["pose"]
    if len(pa) != 3 or len(pb) != 3 or not all(math.isfinite(float(x)) for x in [*pa, *pb]):
        return {"status": "FAIL", "failures": ["nonfinite/invalid pose"], "image_mad": image_mad}
    if a.get("camera") != b.get("camera") or not a.get("camera"):
        failures.append("camera/product provenance")
    if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) > 0.02:
        failures.append("initial XY")
    yaw = abs(math.atan2(math.sin(pa[2] - pb[2]), math.cos(pa[2] - pb[2])))
    if yaw > math.radians(2):
        failures.append("initial yaw")
    return {"status": "FAIL" if failures else "PASS", "failures": failures, "image_mad": image_mad}


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def validate_prior(records: list[dict], freeze: str, cfg: dict, out: Path) -> None:
    for record in records:
        if record.get("freeze") != freeze:
            raise ValueError("prior attempt belongs to another freeze")
    for record in records:
        if record.get("event") != "end":
            continue
        launch = record["id"]
        if launch.startswith("compat-"):
            role = launch.removeprefix("compat-")
            path = out / (launch + ".json")
            report = json.loads(path.read_text())
            if (
                sha(path) != record.get("report_sha256")
                or report.get("role") != role
                or report.get("checkpoint_sha256") != cfg["models"][role]["sha256"]
                or report.get("status") != "PASS"
                or report.get("device_type") != "cuda"
            ):
                raise ValueError("prior compatibility report is not bound to this role/checkpoint")
        else:
            path = out / launch / "boundary.json"
            if sha(path) != record.get("report_sha256"):
                raise ValueError("prior boundary report drift")


def validate_clocks(sensor: object, sim: object) -> None:
    import math

    for value in (sensor, sim):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("finite numeric sensor/simulation clocks required")
    if abs(sensor - sim) > 0.02:
        raise ValueError("initial RGB/simulation timestamp mismatch")


def cancel_signal(signum, frame):
    raise InterruptedError("qualification cancelled by signal")


def run_bounded(cmd, env, cwd, log, timeout):
    import contextlib
    import os
    import signal

    child = subprocess.Popen(
        cmd, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    )
    try:
        return child.wait(timeout=timeout)
    finally:
        if child.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
