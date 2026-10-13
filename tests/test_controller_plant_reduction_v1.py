import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
from controller_plant_diagnostic_v1 import command, info
from imu_controller_boundary_v1 import validate_evaluation
from reduce_controller_plant_diagnostic_v1 import validate_rows


def rows():
    return [
        dict(tick=i, command=list(command(i)), evaluation_v=0.0, diagnostic=info(i))
        for i in range(3120)
    ]


def test_metadata_separately_validated_numeric_payload_preserved():
    data = rows()
    with pytest.raises(ValueError, match="nonnumeric"):
        validate_evaluation(data)
    assert len(validate_rows(data)) == 3120
    assert "diagnostic" in data[0]


def test_nonfinite_numeric_not_rescued_by_metadata_separation():
    data = rows()
    data[100]["evaluation_v"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        validate_rows(data)


def test_metadata_and_command_tampering_rejected():
    data = rows()
    data[300]["diagnostic"] = {**info(300), "mode": "carry"}
    with pytest.raises(ValueError, match="metadata"):
        validate_rows(data)
    data = rows()
    data[300]["command"] = [0, 0]
    with pytest.raises(ValueError, match="command"):
        validate_rows(data)


def fixture_attempt(tmp_path):
    import json

    from reduce_controller_plant_diagnostic_v1 import EXPECTED_FREEZE, digest

    root = tmp_path / "input"
    (root / "attempt").mkdir(parents=True)
    data = rows()
    events = []
    sequence = 0
    for tick, row in enumerate(data):
        row.update(time=(tick + 1) / 120, control_output=0.0, xy=[0.0, 0.0], evaluation_w=0.0)
        for phase in [
            "TELEMETRY_PRE_CONTROL",
            "TELEMETRY_POST_CONTROL",
            "TELEMETRY_REQUESTED_TARGET",
            "TELEMETRY_ACCEPTED_TARGET",
            "TELEMETRY_POST_PHYSICS",
        ]:
            event = dict(
                sequence=sequence,
                phase=phase,
                tick=tick,
                simulation_time=(tick + (phase == "TELEMETRY_POST_PHYSICS")) / 120,
            )
            if phase == "TELEMETRY_POST_CONTROL":
                event["integral_after"] = 0.0
            if phase == "TELEMETRY_REQUESTED_TARGET":
                event.update(
                    requested=[[0.0] * 4],
                    dof_names=["fl", "fr", "rl", "rr"],
                    wheel_indices=[0, 1, 2, 3],
                )
            if phase == "TELEMETRY_ACCEPTED_TARGET":
                event["accepted"] = [[0.0] * 4]
            if phase == "TELEMETRY_POST_PHYSICS":
                event["realized"] = [[0.0] * 4]
            events.append(event)
            sequence += 1
        if tick in [300 + 240 * k for k in range(12)]:
            events.append(dict(phase="TARGET_ONSET", tick=tick))
    report = dict(
        status="FAIL",
        error="nonfinite or nonnumeric evaluation sample",
        rows=data,
        dof_names=["fl", "fr", "rl", "rr"],
        wheel_indices=[0, 1, 2, 3],
    )
    (root / "attempt/imu_qualification.json").write_text(json.dumps(report))
    (root / "attempt/lifecycle.jsonl").write_text("\n".join(json.dumps(x) for x in events))
    for name in ["attempt/imu_readings.jsonl", "worker-entry.jsonl", "process.log"]:
        (root / name).write_text("")
    ledger = dict(
        id="controller-plant-diagnostic-v1-0000",
        freeze=EXPECTED_FREEZE,
        artifacts_sha256={
            str(p.relative_to(root)): digest(p) for p in root.rglob("*") if p.is_file()
        },
    )
    (root / "ledger.json").write_text(json.dumps(ledger))
    return root


def test_complete_saved_nested_schema_reduces_without_reclassifying(tmp_path):
    from reduce_controller_plant_diagnostic_v1 import reduce

    result = reduce(fixture_attempt(tmp_path))
    assert result["original_report_status"] == "FAIL"
    assert len(result["cells"]) == 12 and result["telemetry_events"] == 15600
    assert result["cells"][0]["accepted_wheel_mean"] == [0.0] * 4


def test_typed_metadata_rejects_bool_integer_alias():
    data = rows()
    data[300]["diagnostic"]["trial"] = False
    with pytest.raises(ValueError, match="metadata"):
        validate_rows(data)


@pytest.mark.parametrize("fault", ["clock", "order", "freeze", "missing_artifact"])
def test_complete_fixture_integrity_rejects(tmp_path, fault):
    import json

    from reduce_controller_plant_diagnostic_v1 import digest, reduce

    root = fixture_attempt(tmp_path)
    ledger = json.loads((root / "ledger.json").read_text())
    if fault in ("clock", "order"):
        path = root / "attempt/lifecycle.jsonl"
        events = [json.loads(x) for x in path.read_text().splitlines()]
        if fault == "clock":
            events[0]["simulation_time"] = float("nan")
        else:
            events[0], events[5] = events[5], events[0]
        path.write_text("\n".join(json.dumps(x) for x in events))
        ledger["artifacts_sha256"]["attempt/lifecycle.jsonl"] = digest(path)
    elif fault == "freeze":
        ledger["freeze"] = "wrong"
    else:
        del ledger["artifacts_sha256"]["attempt/lifecycle.jsonl"]
    (root / "ledger.json").write_text(json.dumps(ledger))
    with pytest.raises(ValueError):
        reduce(root)
