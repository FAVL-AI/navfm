"""Thin fixed ViNT continuation bindings; no metric/selection changes."""

import json
from pathlib import Path

from development_qualification_contracts_v1 import sha
from offline_evaluation_contracts_v1 import invalid_output, output_metrics
from prospective_scoring_contracts_v2 import verify_bound_dataset, verify_prior_scores
from vint_interface_v1 import validate_outputs

QUALIFICATION_FREEZE = "d0b724085afcdc3e2247acd79dfda9695269fb79"
PILOT_FREEZE = "bebf498395c6097b2825679a4c1847bf87f32795"


def verify_continuation(cfg):
    if cfg["evaluation"]["draws"] != {"gnm": 1, "nomad": 4, "vint": 1}:
        raise ValueError("fixed ViNT one-draw population required")
    roles = cfg["checkpoints"]["vint"]
    if [r["seed"] for r in roles] != [None, 0, 11, 22]:
        raise ValueError("fixed checkpoint order required")
    binding = cfg["vint_qualification"]
    root = Path(binding["out"])
    registry = Path(binding["registry"])
    for n, h in binding["identity"].items():
        if sha(registry if n == "registry" else root / n) != h:
            raise ValueError("qualification artifact identity drift")
    ledger = json.loads((root / "ledger.json").read_text())
    marker = json.loads((root / "qualification_complete.json").read_text())
    for n, h in ledger["artifacts"].items():
        if sha(root / n) != h:
            raise ValueError("qualification consumed artifact drift")
    report = json.loads((root / "report.json").read_text())
    reservation = json.loads(registry.read_text())[-1]
    if (
        ledger["freeze"] != QUALIFICATION_FREEZE
        or ledger["status"] != "PASS"
        or report["status"] != "PASS"
    ):
        raise ValueError("completed qualified interface required")
    if (
        ledger["child_exit_code"] != 0
        or ledger["timeout"] is not False
        or ledger["child_reaped"] is not True
    ):
        raise ValueError("qualified child lifecycle required")
    if (
        marker["ledger_sha256"] != sha(root / "ledger.json")
        or reservation["marker_sha256"] != sha(root / "qualification_complete.json")
        or reservation["ledger_sha256"] != marker["ledger_sha256"]
        or reservation["status"] != "PASS"
    ):
        raise ValueError("qualification transaction mismatch")
    for n, h in ledger["artifacts"].items():
        if sha(root / n) != h:
            raise ValueError("qualification consumed artifact drift")
    if [r["role"] for r in report["roles"]] != roles or any(
        r["status"] != "PASS" for r in report["roles"]
    ):
        raise ValueError("qualified checkpoint population mismatch")
    prior = json.loads(Path(cfg["completed_pilot_registry"]).read_text())
    if [r["model"] for r in prior] != ["gnm", "nomad"]:
        raise ValueError("closed pilot population mismatch")
    verify_prior_scores(prior, PILOT_FREEZE)
    legacy = json.loads(json.dumps(cfg))
    del legacy["evaluation"]["draws"]["vint"]
    return verify_bound_dataset(legacy)


def vint_output_metrics(
    predictions, distances, labels, distance_label, action_valid, spacing, horizon
):
    try:
        validate_outputs(distances, predictions, 1)
    except (ValueError, TypeError, IndexError):
        return invalid_output(action_valid, "native ViNT output integrity")
    return output_metrics(
        predictions, distances, labels, distance_label, action_valid, spacing, horizon
    )
