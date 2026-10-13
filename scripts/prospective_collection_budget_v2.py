"""Prospective 190-second continuation budgets; no authority inferred from configuration."""

import math

from prospective_budget_proposal_v1 import validate_proposal


def execution_remaining(proposal, approved_opt_in, start, now):
    validate_proposal(proposal)
    if approved_opt_in is not True:
        raise ValueError("explicit approved-amendment invocation required")
    if (
        any(type(v) not in (float, int) or not math.isfinite(v) for v in (start, now))
        or now < start
    ):
        raise ValueError("monotonic clock integrity")
    return max(0.0, start + 185 - now)


def within_total_budget(start, now):
    if (
        any(type(v) not in (float, int) or not math.isfinite(v) for v in (start, now))
        or now < start
    ):
        raise ValueError("monotonic clock integrity")
    return now <= start + 190


def cleanup_remaining(start, now):
    within_total_budget(start, now)
    return max(0.0, start + 190 - now)


def finalize_transaction(out, slot, record, dataset_admission, start, writer=None, now=None):
    """No admission is usable without the completed final transaction marker."""
    import time

    from development_qualification_contracts_v1 import sha
    from offline_evaluation_contracts_v1 import atomic_snapshot

    writer = atomic_snapshot if writer is None else writer
    now = time.monotonic if now is None else now
    marker = out / "finalization_complete.json"
    admission_path = out / "admission.json"

    def check_deadline():
        current = now()
        record["occupied_wall_s"] = current - start
        record["whole_process_budget_exceeded"] = not within_total_budget(start, current)
        if record["whole_process_budget_exceeded"]:
            raise TimeoutError("whole process finalization deadline")

    try:
        check_deadline()
        record["finalization_complete"] = record["status"] == "PASS"
        writer(out / "ledger.json", record)
        writer(slot, record)
        check_deadline()
        if record["status"] == "PASS" and dataset_admission is not None:
            dataset_admission = dict(
                dataset_admission, finalization_required="finalization_complete.json"
            )
            writer(admission_path, dataset_admission)
            check_deadline()
            writer(
                marker,
                dict(
                    status="COMPLETE",
                    freeze=record["freeze"],
                    ledger_sha256=sha(out / "ledger.json"),
                    registry_sha256=sha(slot),
                    admission_sha256=sha(admission_path),
                ),
            )
            check_deadline()
    except BaseException as exc:
        record.update(
            status="FAIL", finalization_complete=False, finalization_error_type=type(exc).__name__
        )
        for path in (marker, admission_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                record["finalization_cleanup_storage_error"] = True
        for path in (out / "ledger.json", slot):
            try:
                writer(path, record)
            except BaseException:
                record["failure_record_storage_error"] = True
        raise


def verify_final_transaction(out, slot):
    import json

    from development_qualification_contracts_v1 import sha

    marker = json.loads((out / "finalization_complete.json").read_text())
    for path, key in [
        (out / "ledger.json", "ledger_sha256"),
        (slot, "registry_sha256"),
        (out / "admission.json", "admission_sha256"),
    ]:
        if sha(path) != marker[key]:
            raise ValueError("final transaction artifact drift")
    ledger = json.loads((out / "ledger.json").read_text())
    registry = json.loads(slot.read_text())
    admission = json.loads((out / "admission.json").read_text())
    if (
        marker["status"] != "COMPLETE"
        or ledger != registry
        or ledger["status"] != "PASS"
        or not ledger["finalization_complete"]
        or ledger["whole_process_budget_exceeded"]
        or admission["status"] != "PASS"
        or marker["freeze"] != ledger["freeze"]
    ):
        raise ValueError("completed final transaction required")
    for name, digest in ledger["artifacts"].items():
        if sha(out / name) != digest:
            raise ValueError("final transaction consumed artifact drift")
    return True
