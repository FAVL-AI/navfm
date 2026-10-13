"""Offline descriptive recovery of numeric samples; original attempt remains FAIL."""

import argparse
import hashlib
import json
import math
from itertools import pairwise
from pathlib import Path

from controller_plant_diagnostic_v1 import TRIALS, command, info
from controller_telemetry_v1 import checked_array
from imu_controller_boundary_v1 import validate_evaluation
from matched_navigation_contracts_v2 import score_command

EXPECTED_FREEZE = "81e0af0a5e09fcc7ac379ba3f93678563f519bde"


def exact(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(
        b, sort_keys=True, allow_nan=False
    )


def validate_rows(rows):
    if len(rows) != 3120:
        raise ValueError("incomplete diagnostic rows")
    numeric = []
    for tick, row in enumerate(rows):
        if (
            not exact(row.get("diagnostic"), info(tick))
            or type(row.get("tick")) is not int
            or row.get("tick") != tick
        ):
            raise ValueError("diagnostic metadata/order mismatch")
        payload = {k: v for k, v in row.items() if k != "diagnostic"}
        validate_evaluation(payload)
        if row["command"] != list(command(tick)):
            raise ValueError("command drift")
        numeric.append(payload)
    return numeric


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean(values):
    return sum(values) / len(values)


def reduce(root):
    ledger = json.loads((root / "ledger.json").read_text())
    if (
        ledger.get("freeze") != EXPECTED_FREEZE
        or ledger.get("id") != "controller-plant-diagnostic-v1-0000"
    ):
        raise ValueError("unexpected attempt/freeze")
    required = {
        "attempt/imu_qualification.json",
        "attempt/lifecycle.jsonl",
        "attempt/imu_readings.jsonl",
        "worker-entry.jsonl",
        "process.log",
    }
    if not required.issubset(ledger.get("artifacts_sha256", {})):
        raise ValueError("consumed artifact missing from ledger")
    for name, expected in ledger["artifacts_sha256"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or digest(root / path) != expected:
            raise ValueError("recorded artifact mismatch")
    report = json.loads((root / "attempt/imu_qualification.json").read_text())
    rows = validate_rows(report["rows"])
    events = [
        json.loads(line) for line in (root / "attempt/lifecycle.jsonl").read_text().splitlines()
    ]
    phases = [
        "TELEMETRY_PRE_CONTROL",
        "TELEMETRY_POST_CONTROL",
        "TELEMETRY_REQUESTED_TARGET",
        "TELEMETRY_ACCEPTED_TARGET",
        "TELEMETRY_POST_PHYSICS",
    ]
    ticks = {i: [] for i in range(3120)}
    telemetry = [event for event in events if event["phase"] in phases]
    if (
        len(telemetry) != 15600
        or [(e.get("tick"), e["phase"]) for e in telemetry]
        != [(tick, phase) for tick in range(3120) for phase in phases]
        or not all(a["sequence"] < b["sequence"] for a, b in pairwise(telemetry))
    ):
        raise ValueError("chronological telemetry order mismatch")
    for event in telemetry:
        if type(event["tick"]) is not int:
            raise ValueError("invalid telemetry tick")
        validate_evaluation(event["simulation_time"])
        ticks[event["tick"]].append(event)
    for tick, group in ticks.items():
        if [e["phase"] for e in group] != phases or not all(
            a["sequence"] < b["sequence"] for a, b in pairwise(group)
        ):
            raise ValueError("telemetry phase/order mismatch")
        clock = group[0]["simulation_time"]
        if (
            any(abs(e["simulation_time"] - clock) > 1e-6 for e in group[:4])
            or abs(group[4]["simulation_time"] - clock - 1 / 120) > 1e-6
        ):
            raise ValueError("telemetry clock mismatch")
        if abs(group[4]["simulation_time"] - rows[tick]["time"]) > 1e-6:
            raise ValueError("sample clock mismatch")
        for event, key in zip(group[2:], ["requested", "accepted", "realized"], strict=True):
            event[key] = checked_array(event[key], 4)
        if (
            group[2]["dof_names"] != report["dof_names"]
            or group[2]["wheel_indices"] != report["wheel_indices"]
        ):
            raise ValueError("DOF binding mismatch")
    onsets = [e for e in events if e["phase"] == "TARGET_ONSET"]
    if [e["tick"] for e in onsets] != [300 + 240 * k for k in range(12)]:
        raise ValueError("onset order mismatch")
    cells = []
    for k, (mode, v, w) in enumerate(TRIALS):
        start = 300 + 240 * k
        sample = rows[start : start + 60]
        groups = [ticks[i] for i in range(start, start + 60)]
        scored = score_command([{**row, "dt": 1 / 120} for row in sample], (v, w))
        accepted = [g[3]["accepted"] for g in groups]
        realized = [g[4]["realized"] for g in groups]
        cells.append(
            dict(
                trial=k,
                mode=mode,
                **scored,
                onset=onsets[k],
                integral_first_update=groups[0][1]["integral_after"],
                mean_control_output=mean([r["control_output"] for r in sample]),
                accepted_wheel_mean=[mean([x[i] for x in accepted]) for i in range(4)],
                realized_wheel_mean=[mean([x[i] for x in realized]) for i in range(4)],
                accepted_differential_mean=mean(
                    [(x[1] + x[3] - x[0] - x[2]) / 2 for x in accepted]
                ),
                realized_differential_mean=mean(
                    [(x[1] + x[3] - x[0] - x[2]) / 2 for x in realized]
                ),
                requested_accepted_max_abs=max(
                    abs(a - b)
                    for g in groups
                    for a, b in zip(g[2]["requested"], g[3]["accepted"], strict=True)
                ),
            )
        )
    return dict(
        scope="derived descriptive reduction, not reclassification or qualification",
        original_report_status=report["status"],
        original_error=report.get("error"),
        input_artifacts=ledger["artifacts_sha256"],
        ledger_sha256=digest(root / "ledger.json"),
        reducer_source_sha256=digest(Path(__file__)),
        scoring_source_sha256=digest(
            Path(__file__).with_name("matched_navigation_contracts_v2.py")
        ),
        samples=len(rows),
        telemetry_events=sum(map(len, ticks.values())),
        cells=cells,
        derived_pass_count=sum(c["passed"] for c in cells),
        stop_distance_m=sum(math.dist(a["xy"], b["xy"]) for a, b in pairwise(rows[-121:])),
        plant_readback=[e["readback"] for e in events if e["phase"] == "PLANT_USD_READBACK"],
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "derived.json").write_text(
        json.dumps(reduce(args.input), indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
