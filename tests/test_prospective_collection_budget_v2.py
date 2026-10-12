import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from prospective_collection_budget_v2 import (
    cleanup_remaining,
    execution_remaining,
    within_total_budget,
)
from prospective_collection_contracts_v1 import admission


def proposal():
    return json.loads(
        (Path(__file__).parents[1] / "configs/eval/prospective_budget_proposal_v1.json").read_text()
    )


def test_actual_execution_and_cleanup_deadlines():
    cfg = proposal()
    assert execution_remaining(cfg, True, 1000, 1000) == 185
    assert execution_remaining(cfg, True, 1000, 1184.5) == 0.5
    assert execution_remaining(cfg, True, 1000, 1186) == 0
    assert cleanup_remaining(1000, 1188) == 2
    assert cleanup_remaining(1000, 1191) == 0
    assert within_total_budget(1000, 1190)
    assert not within_total_budget(1000, 1190.00001)


def test_pending_approval_has_no_execution_authority():
    with pytest.raises(ValueError, match="invocation"):
        execution_remaining(proposal(), False, 0, 0)


@pytest.mark.parametrize("now", [float("nan"), float("inf"), -1, True])
def test_bad_monotonic_clock_cannot_extend_budget(now):
    with pytest.raises(ValueError, match="clock"):
        execution_remaining(proposal(), True, 0, now)
    with pytest.raises(ValueError, match="clock"):
        within_total_budget(0, now)


def test_existing_capsule_admission_counts_and_process_guards_unchanged():
    capsule = dict(measurement_status="COMPLETE", report=dict(frames=[dict(status="PASS")] * 144))
    assert admission(capsule, 0, False, True, True)["status"] == "PASS"
    assert admission(capsule, 0, True, True, True)["status"] == "FAIL"
    capsule["report"]["frames"].pop()
    assert admission(capsule, 0, False, True, True)["status"] == "FAIL"


def test_continuation_reuses_exact_capture_and_has_no_scorer():
    source = (Path(__file__).parents[1] / "scripts/run_prospective_collection_v2.py").read_text()
    assert "scripts/prospective_capture_collection_v1.py" in source
    assert "seal generation identity drift" in source
    assert "verify_qualification(cfg)" in source
    calls = [
        x
        for x in ast.walk(ast.parse(source))
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
    ]
    remaining = next(x for x in calls if x.func.id == "execution_remaining")
    assert ast.unparse(remaining.args[1]) == "args.execute_approved_amendment"
    assert any(x.func.id == "cleanup_remaining" for x in calls)
    assert "finalize_transaction(out, slot, record, dataset_admission, start)" in source
    assert "run_prospective_timing" not in source and "score" not in source


def record_for_transaction():
    return dict(status="PASS", freeze="reviewed-test-freeze", artifacts={})


def test_registry_write_failure_invalidates_output_pass(tmp_path):
    from offline_evaluation_contracts_v1 import atomic_snapshot
    from prospective_collection_budget_v2 import finalize_transaction

    slot = tmp_path / "registry.json"
    seen_output_pass = []

    def writer(path, value):
        if path == slot:
            seen_output_pass.append(json.loads((tmp_path / "ledger.json").read_text())["status"])
            raise OSError("controlled registry write failure")
        atomic_snapshot(path, value)

    record = record_for_transaction()
    with pytest.raises(OSError):
        finalize_transaction(tmp_path, slot, record, dict(status="PASS"), 0, writer, lambda: 10)
    assert seen_output_pass[0] == "PASS"
    assert record["status"] == "FAIL"
    assert json.loads((tmp_path / "ledger.json").read_text())["status"] == "FAIL"
    assert not (tmp_path / "admission.json").exists()
    assert not (tmp_path / "finalization_complete.json").exists()


def test_deadline_crossed_during_persistence_cannot_leave_admission(tmp_path):
    from offline_evaluation_contracts_v1 import atomic_snapshot
    from prospective_collection_budget_v2 import finalize_transaction

    clock = [189.0]

    def writer(path, value):
        atomic_snapshot(path, value)
        if path.name == "admission.json":
            clock[0] = 190.01

    record = record_for_transaction()
    with pytest.raises(TimeoutError):
        finalize_transaction(
            tmp_path,
            tmp_path / "registry.json",
            record,
            dict(status="PASS"),
            0,
            writer,
            lambda: clock[0],
        )
    assert record["status"] == "FAIL" and record["whole_process_budget_exceeded"]
    assert not (tmp_path / "admission.json").exists()
    assert not (tmp_path / "finalization_complete.json").exists()


def test_cancellation_after_admission_is_fail_closed(tmp_path):
    from offline_evaluation_contracts_v1 import atomic_snapshot
    from prospective_collection_budget_v2 import finalize_transaction

    def writer(path, value):
        if path.name == "finalization_complete.json":
            raise KeyboardInterrupt
        atomic_snapshot(path, value)

    record = record_for_transaction()
    with pytest.raises(KeyboardInterrupt):
        finalize_transaction(
            tmp_path, tmp_path / "registry.json", record, dict(status="PASS"), 0, writer, lambda: 10
        )
    assert record["status"] == "FAIL"
    assert not (tmp_path / "admission.json").exists()


def test_completed_final_transaction_verifies_and_rejects_drift(tmp_path):
    from prospective_collection_budget_v2 import finalize_transaction, verify_final_transaction

    slot = tmp_path / "registry.json"
    finalize_transaction(
        tmp_path, slot, record_for_transaction(), dict(status="PASS"), 0, now=lambda: 10
    )
    assert verify_final_transaction(tmp_path, slot)
    slot.write_text("{}")
    with pytest.raises(ValueError, match="drift"):
        verify_final_transaction(tmp_path, slot)
