"""Exact completed dataset transaction binding for scoring-only continuation."""

import json
from pathlib import Path

from development_qualification_contracts_v1 import sha
from offline_evaluation_contracts_v1 import validate
from prospective_collection_budget_v2 import verify_final_transaction

COLLECTION_FREEZE = "a5f22c2571790ac5c53e66ea0b9796d373ef266c"


def verify_bound_dataset(cfg):
    binding = cfg["collected_dataset_binding"]
    root, registry = Path(binding["out"]), Path(binding["registry"])
    if binding["source_freeze"] != COLLECTION_FREEZE:
        raise ValueError("wrong dataset collection identity")
    if Path(cfg["dataset"]) != root / "data" or Path(cfg["admission"]) != root / "admission.json":
        raise ValueError("wrong dataset/admission path")
    required = {"ledger.json", "finalization_complete.json", "admission.json", "registry"}
    if set(binding["identity"]) != required:
        raise ValueError("complete dataset transaction identity required")
    for name, digest in binding["identity"].items():
        if sha(registry if name == "registry" else root / name) != digest:
            raise ValueError("dataset transaction identity drift")
    verify_final_transaction(root, registry)
    ledger = json.loads((root / "ledger.json").read_text())
    admission = json.loads((root / "admission.json").read_text())
    if ledger["freeze"] != COLLECTION_FREEZE or admission["source_freeze"] != COLLECTION_FREEZE:
        raise ValueError("wrong dataset collection identity")
    if (
        len(ledger["artifacts"]) != 152
        or len(admission["trajectories"]) != 4
        or any(x["processed_frames"] != 36 for x in admission["trajectories"])
    ):
        raise ValueError("admitted dataset population drift")
    if (
        admission["splits"]["train"]
        or admission["splits"]["test"]
        or len(admission["splits"]["dev"]) != 4
    ):
        raise ValueError("accessed pilot split drift")
    validate(cfg, admission)
    return dict(
        status="PASS",
        source_freeze=COLLECTION_FREEZE,
        ledger_artifact_count=152,
        prior_layout_exposure="ACCESSED_NOT_UNINSPECTED",
        sdk_cleanup_completion="NOT_INDEPENDENTLY_OBSERVED",
    )


def verify_prior_scores(prior, freeze):
    for entry in prior:
        if entry["freeze"] != freeze or entry["status"] != "PASS":
            raise ValueError("prior scoring incomplete")
        root = Path(entry["out"])
        if (
            sha(root / "ledger.json") != entry["ledger_sha256"]
            or sha(root / "scoring_complete.json") != entry["marker_sha256"]
        ):
            raise ValueError("prior completed scoring identity drift")
        marker = json.loads((root / "scoring_complete.json").read_text())
        ledger = json.loads((root / "ledger.json").read_text())
        if (
            marker
            != dict(
                status="COMPLETE",
                freeze=freeze,
                model=entry["model"],
                ledger_sha256=entry["ledger_sha256"],
            )
            or ledger["status"] != "PASS"
            or ledger["freeze"] != freeze
            or ledger["model"] != entry["model"]
        ):
            raise ValueError("prior completed scoring transaction required")
        for name, digest in ledger["artifacts"].items():
            if sha(root / name) != digest:
                raise ValueError("prior scoring artifact drift")


def finalize_score(out, reservations, prior, ledger, started, writer=None, now=None):
    import time

    from offline_evaluation_contracts_v1 import atomic_snapshot

    writer = atomic_snapshot if writer is None else writer
    now = time.monotonic if now is None else now
    marker = out / "scoring_complete.json"

    def deadline():
        elapsed = now() - started
        ledger["occupied_wall_s"] = elapsed
        if elapsed < 0 or elapsed > 1800:
            raise TimeoutError("scoring whole process deadline")

    try:
        deadline()
        ledger["artifacts"] = {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p.name not in ("ledger.json", "scoring_complete.json")
        }
        deadline()
        writer(out / "ledger.json", ledger)
        deadline()
        if ledger["status"] == "PASS":
            digest = sha(out / "ledger.json")
            writer(
                marker,
                dict(
                    status="COMPLETE",
                    freeze=ledger["freeze"],
                    model=ledger["model"],
                    ledger_sha256=digest,
                ),
            )
            deadline()
            prior[-1].update(
                status="PASS",
                out=str(out),
                ledger_sha256=digest,
                marker_sha256=sha(marker),
                occupied_wall_s=ledger["occupied_wall_s"],
            )
        else:
            prior[-1].update(status="FAIL", occupied_wall_s=ledger["occupied_wall_s"])
        writer(reservations, prior)
        deadline()
    except BaseException as exc:
        ledger.update(status="FAIL", finalization_error_type=type(exc).__name__)
        prior[-1].update(status="FAIL")
        for key in ("ledger_sha256", "marker_sha256"):
            prior[-1].pop(key, None)
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            ledger["failure_cleanup_storage_error"] = True
        for path, value in [(out / "ledger.json", ledger), (reservations, prior)]:
            try:
                writer(path, value)
            except BaseException:
                ledger["failure_record_storage_error"] = True
        raise
