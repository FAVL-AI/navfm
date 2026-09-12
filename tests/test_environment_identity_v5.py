"""Controls for V5, Manifest V2 and preflight currency.

The invariant chain is now four deep, and each amendment answers only for the
state it froze:

    V2 accepts its freeze state, rejects the later seam state
    V3 accepts its freeze state, rejects the later treatment state
    V4 accepts its freeze state, rejects the later wiring state
    V5 accepts the final executable state

The specific thing V5 exists to prove, which V4 could not, is that the
experiment is invokable: a runner resolves, both arms dispatch, the selector
reaches the collector, and every declared output has someone to write it. None
of that says the simulator will work.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from navfm.arm_environment_guard import (
    AUTHORITATIVE_CONTRACT_VERSION,
    CONTRACTS,
    V4_AMENDMENT_SHA256,
    V5_AMENDMENT_REL,
    V5_AMENDMENT_SHA256,
    check_contract,
)
from navfm.execution_environment import V5_ADDITIONAL_CRITICAL_FIELDS, contract_fields
from navfm.execution_manifest_v2 import (
    MANIFEST_V2_VERSION,
    PREFLIGHT_CURRENCY_FIELDS,
    build_manifest_v2,
    freeze_manifest_v2,
    generate_live_preflight,
    preflight_currency,
    validate_manifest_v2,
)

REPO = Path(__file__).resolve().parents[1]
V5 = REPO / V5_AMENDMENT_REL
WIRING_REL = "gates/BO10/collector_wiring_regression_20260912.json"
GAP_REL = "gates/BO10/execution_readiness_gap_v1_20260912.json"

_SPEC = importlib.util.spec_from_file_location(
    "amend_v5", REPO / "scripts" / "amend_environment_identity_v5.py")
assert _SPEC and _SPEC.loader
v5mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v5mod)


def _head() -> str:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _sha() -> str:
    return hashlib.sha256(V5.read_bytes()).hexdigest()


@pytest.fixture
def amendment() -> dict[str, Any]:
    return json.loads(V5.read_text())


@pytest.fixture
def manifest(tmp_path: Path) -> dict[str, Any]:
    return build_manifest_v2(
        REPO, head=_head(), frozen_at_utc="2026-09-12T00:00:00+00:00",
        manifest_path="runs/bo10/intervention/execution_manifest_v2.json")


# --------------------------------------------------------------------------
# the invariant chain
# --------------------------------------------------------------------------


def test_v5_is_authoritative() -> None:
    assert AUTHORITATIVE_CONTRACT_VERSION == "V5"
    assert set(CONTRACTS) == {"V2", "V3", "V4", "V5"}


def test_v5_accepts_the_executable_state() -> None:
    result = check_contract(REPO, "V5")
    assert result["CONTRACT_SATISFIED"] == "PASS"
    assert result["drift"] == []
    assert result["fields_compared"] == 48


@pytest.mark.parametrize("version", ["V2", "V3", "V4"])
def test_every_predecessor_still_refuses(version: str) -> None:
    """Permanent. If any of these passes, an old contract was rewritten."""
    assert check_contract(REPO, version)["CONTRACT_SATISFIED"] == "FAIL"


def test_v4_refuses_for_the_wiring_transition() -> None:
    drift = [d["field"] for d in check_contract(REPO, "V4")["drift"]]
    assert "scientific_code.collect_sha256" in drift


def test_v4_file_is_byte_unchanged() -> None:
    assert hashlib.sha256(
        (REPO / "gates/BO10/environment_identity_v4_20260912.json").read_bytes()
    ).hexdigest() == V4_AMENDMENT_SHA256


def test_v5_adds_the_execution_machinery_to_the_contract() -> None:
    assert len(contract_fields("V5")) == len(contract_fields("V4")) + 2
    added = set(contract_fields("V5")) - set(contract_fields("V4"))
    assert added == set(V5_ADDITIONAL_CRITICAL_FIELDS)
    assert added == {"scientific_code.intervention_runner_sha256",
                     "scientific_code.arm_runner_sha256"}


def test_pinned_v5_sha_matches_the_artefact() -> None:
    assert _sha() == V5_AMENDMENT_SHA256


# --------------------------------------------------------------------------
# what V5 records
# --------------------------------------------------------------------------


def test_the_gap_is_recorded_and_is_not_an_arm_failure(amendment: dict[str, Any]) -> None:
    gap = amendment["EXECUTION_READINESS_GAP"]
    assert gap["classification"] == "EXECUTION_READINESS_GAP_V1"
    assert "Arm A never started" in gap["not_an_arm_a_failure"]
    assert len(gap["blockers"]) == 3
    record = json.loads((REPO / GAP_REL).read_text())
    assert record["ARM_A_EXECUTION"] == "NOT_STARTED"
    assert record["explicitly_did_not_happen"]


def test_v5_does_not_claim_to_repair_v4(amendment: dict[str, Any]) -> None:
    assert "remains correct about the tree it froze" in amendment["amends"][
        "this_does_not_repair_v4"]


def test_transitions_are_measured_not_prescribed(amendment: dict[str, Any]) -> None:
    transitions = amendment["SOURCE_IDENTITY_TRANSITIONS_V4_TO_V5"]
    assert transitions["measured_not_prescribed"] is True
    assert "scientific_code.collect_sha256" in transitions["changed"]
    assert set(transitions["added"]) == set(V5_ADDITIONAL_CRITICAL_FIELDS)
    assert transitions["unchanged_field_count"] == 44
    for entry in transitions["changed"].values():
        assert entry["reason"] and entry["evidence"]["sha256"]


def test_the_controller_did_not_change_in_this_tranche(amendment: dict[str, Any]) -> None:
    pinned = amendment["SOURCE_IDENTITY_TRANSITIONS_V4_TO_V5"][
        "control_py_unchanged_since_v3"]
    assert pinned == hashlib.sha256(
        (REPO / "src/navfm/control.py").read_bytes()).hexdigest()
    assert "scientific_code.control_sha256" not in amendment[
        "SOURCE_IDENTITY_TRANSITIONS_V4_TO_V5"]["changed"]


def test_wiring_regression_is_bound_with_its_counts(amendment: dict[str, Any]) -> None:
    regression = amendment["ARM_A_COLLECTOR_WIRING_REGRESSION"]
    assert regression["verdict"] == "PASS"
    assert regression["artefact"]["sha256"] == hashlib.sha256(
        (REPO / WIRING_REL).read_bytes()).hexdigest()
    for trace in regression["traces"].values():
        assert trace["steps_evaluated"] == 1200
        assert sum(trace["mismatches_by_channel"].values()) == 0
    assert len(regression["implementations_compared"]) == 5
    assert "NOT a proof for every possible input" in regression["CLAIM_BOUNDARY"]


def test_executability_evidence_is_bound(amendment: dict[str, Any]) -> None:
    evidence = amendment["EXECUTABILITY_EVIDENCE"]
    assert evidence["EXECUTABILITY"] == "PASS"
    assert evidence["producer_coverage"]["verdict"] == "PASS"
    assert evidence["producer_coverage"]["outputs_without_a_producer"] == []
    assert set(evidence["supported_arms"]) == {"ARM_A_CONTROL", "ARM_B_TREATMENT"}
    assert "paper-ready and not runnable" in evidence["what_distinguishes_v5_from_v4"]
    assert "do NOT claim that Isaac will launch" in evidence["claim_boundary"]


def test_the_propagation_path_is_recorded(amendment: dict[str, Any]) -> None:
    path = amendment["ONE_FACTOR_EXECUTION_CONTRACT"]["propagation_path"]
    for stage in ("manifest arm identity", "runner", "CollectConfig.target_selector",
                  "resolve_target_selector", "PurePursuit"):
        assert stage in path
    assert amendment["ONE_FACTOR_EXECUTION_CONTRACT"]["behavioural_overrides"] == ["target"]


def test_version_chain_is_nine_linked_nodes(amendment: dict[str, Any]) -> None:
    nodes = amendment["VERSION_CHAIN"]
    assert [n["node"] for n in nodes] == [
        "INTERVENTION_V1", "ENVIRONMENT_V2", "TRACKER_INJECTION_EQUIVALENCE",
        "ENVIRONMENT_V3", "TREATMENT_VALIDATION", "ENVIRONMENT_V4",
        "COLLECTOR_WIRING_REGRESSION", "EXECUTABILITY_REPAIR", "ENVIRONMENT_V5"]
    assert nodes[0]["predecessor"] is None
    for earlier, later in itertools.pairwise(nodes):
        assert later["predecessor"] == earlier["node"]
        assert later["reason"] and later["evidence_basis"] and later["timestamp_utc"]


def test_no_arm_ran(amendment: dict[str, Any]) -> None:
    assert amendment["EXECUTION_STATUS"] == "NOT_RUN"
    assert amendment["arms_executed"] == 0
    assert amendment["ARM_A_EXECUTION"] == "NOT_STARTED"
    assert amendment["ARM_B_EXECUTION"] == "NOT_STARTED"


# --------------------------------------------------------------------------
# V5 immutability
# --------------------------------------------------------------------------


def test_unchanged_regeneration_reproduces_the_artefact() -> None:
    before = _sha()
    outcome = v5mod.freeze()
    assert outcome["V5_AMENDMENT"] == "FROZEN"
    assert outcome["refrozen"] is False
    assert _sha() == before


@pytest.mark.parametrize(
    "attribute", ["V4_SHA256", "TREATMENT_SHA256", "PREREG_SHA256", "CONTROL_SHA256"])
def test_a_mutated_pin_refuses_and_writes_nothing(
    attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _sha()
    monkeypatch.setattr(v5mod, attribute, "0" * 64)
    outcome = v5mod.freeze()
    assert outcome["V5_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_a_failed_wiring_regression_blocks_the_freeze(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = json.loads((REPO / WIRING_REL).read_text())
    broken["ARM_A_COLLECTOR_WIRING_REGRESSION"] = "FAIL"
    target = tmp_path / "broken.json"
    target.write_text(json.dumps(broken))
    monkeypatch.setattr(v5mod, "REPO", tmp_path)
    monkeypatch.setattr(v5mod, "WIRING_REL", target.name)
    assert v5mod.verify_wiring()["ok"] is False


def test_refusal_is_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v5mod, "V4_SHA256", "0" * 64)
    outcome = v5mod.freeze()
    assert outcome["V5_AMENDMENT"] == "REFUSED"
    assert isinstance(outcome["reasons"], list)
    assert "declines rather than raising" in outcome["note"]


def test_restoring_the_pins_reproduces_the_sha() -> None:
    before = _sha()
    assert v5mod.freeze()["V5_AMENDMENT"] == "FROZEN"
    assert _sha() == before == V5_AMENDMENT_SHA256


# --------------------------------------------------------------------------
# Manifest V2
# --------------------------------------------------------------------------


def test_manifest_v2_validates(manifest: dict[str, Any]) -> None:
    result = validate_manifest_v2(manifest, REPO, expected_head=_head())
    assert result["MANIFEST_VALID"] == "PASS", result["failures"]


def test_manifest_v2_declares_v5_and_executability(manifest: dict[str, Any]) -> None:
    assert manifest["manifest_version"] == MANIFEST_V2_VERSION
    assert manifest["authoritative_contract"]["version"] == "V5"
    readiness = manifest["executability"]
    for key in ("runner_resolved", "collector_resolved", "selector_wiring_present",
                "selectors_resolved", "arm_a_dispatch_valid", "arm_b_dispatch_valid",
                "required_output_producers_complete"):
        assert readiness[key] is True


def test_manifest_v2_does_not_overwrite_v1(manifest: dict[str, Any]) -> None:
    supersedes = manifest["supersedes"]
    assert supersedes["version"] == "EXECUTION_MANIFEST_V1"
    assert supersedes["not_overwritten"] is True
    assert "declared outputs without establishing" in supersedes["limitation"]


def test_manifest_v2_records_the_authorised_invocation(manifest: dict[str, Any]) -> None:
    invocation = manifest["authorised_invocation"]
    assert "--arm ARM_A_CONTROL" in invocation["arm_a"]
    assert "--arm ARM_B_TREATMENT" in invocation["arm_b"]
    assert "run_terminal_approach_intervention.py" in invocation["arm_a"]


def test_manifest_v2_carries_the_producer_map(manifest: dict[str, Any]) -> None:
    producers = manifest["producer_map"]
    declared = set(manifest["output_allowlist"]["tracked"]) | set(
        manifest["output_allowlist"]["untracked_runtime"])
    assert set(producers) == declared
    assert all(entry["producer"] for entry in producers.values())


@pytest.mark.parametrize(
    ("path", "value", "expected_field"),
    [("executability.runner_resolved", False, "executability.runner_resolved"),
     ("executability.arm_a_dispatch_valid", False, "executability.arm_a_dispatch_valid"),
     ("executability.arm_b_dispatch_valid", False, "executability.arm_b_dispatch_valid"),
     ("executability.selector_wiring_present", False,
      "executability.selector_wiring_present"),
     ("executability.required_output_producers_complete", False,
      "executability.required_output_producers_complete"),
     ("executability.runner_sha256", "0" * 64, "executability.runner_sha256"),
     ("authoritative_contract.version", "V4", "authoritative_contract.version"),
     ("manifest_version", "EXECUTION_MANIFEST_V1", "manifest_version"),
     ("repository.head", "0" * 40, "repository.head")],
)
def test_a_mutated_manifest_v2_field_is_named(
    manifest: dict[str, Any], path: str, value: Any, expected_field: str
) -> None:
    import copy

    broken = copy.deepcopy(manifest)
    node: Any = broken
    parts = path.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value
    result = validate_manifest_v2(broken, REPO, expected_head=_head())
    assert result["MANIFEST_VALID"] == "FAIL"
    assert expected_field in [f["field"] for f in result["failures"]]


def test_a_missing_producer_fails_manifest_v2(manifest: dict[str, Any]) -> None:
    import copy

    broken = copy.deepcopy(manifest)
    broken["output_allowlist"]["tracked"].append("gates/BO10/intervention/orphan.json")
    result = validate_manifest_v2(broken, REPO, expected_head=_head())
    assert result["MANIFEST_VALID"] == "FAIL"
    assert any(f["field"] == "producer_map" for f in result["failures"])


def test_manifest_v2_freeze_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "m2.json"
    first = freeze_manifest_v2(target, REPO, head=_head(),
                               frozen_at_utc="2026-09-12T00:00:00+00:00")
    assert first["EXECUTION_MANIFEST"] == "FROZEN"
    assert first["validate_only_selftest"] == {
        "ARM_A_CONTROL": "PASS", "ARM_B_TREATMENT": "PASS"}
    second = freeze_manifest_v2(target, REPO, head=_head(),
                                frozen_at_utc="2099-01-01T00:00:00+00:00")
    assert second["sha256"] == first["sha256"]
    assert second["first_freeze"] is False


def test_manifest_v2_refuses_a_wrong_head(tmp_path: Path) -> None:
    outcome = freeze_manifest_v2(tmp_path / "m2.json", REPO, head="0" * 40,
                                 frozen_at_utc="2026-09-12T00:00:00+00:00")
    assert outcome["EXECUTION_MANIFEST"] == "REFUSED"


# --------------------------------------------------------------------------
# preflight currency
# --------------------------------------------------------------------------


def test_a_fresh_preflight_is_current(tmp_path: Path) -> None:
    manifest_path = tmp_path / "m2.json"
    freeze_manifest_v2(manifest_path, REPO, head=_head(),
                       frozen_at_utc="2026-09-12T00:00:00+00:00")
    generated = generate_live_preflight(
        tmp_path / "pf.json", REPO, manifest_path=manifest_path)
    result = preflight_currency(generated["record"], REPO, manifest_path=manifest_path)
    assert result["PREFLIGHT_CURRENCY"] == "PASS"
    assert result["stale_fields"] == []


@pytest.mark.parametrize("field", PREFLIGHT_CURRENCY_FIELDS)
def test_an_old_bound_value_is_stale_not_passing(tmp_path: Path, field: str) -> None:
    manifest_path = tmp_path / "m2.json"
    freeze_manifest_v2(manifest_path, REPO, head=_head(),
                       frozen_at_utc="2026-09-12T00:00:00+00:00")
    generated = generate_live_preflight(
        tmp_path / "pf.json", REPO, manifest_path=manifest_path)
    record = generated["record"]
    record["bound"][field] = "0" * 40
    result = preflight_currency(record, REPO, manifest_path=manifest_path)
    assert result["PREFLIGHT_CURRENCY"] == "STALE_PREFLIGHT"
    assert [s["field"] for s in result["stale_fields"]] == [field]


def test_a_preflight_binding_nothing_is_stale() -> None:
    result = preflight_currency({}, REPO, manifest_path=REPO / "nope.json")
    assert result["PREFLIGHT_CURRENCY"] == "STALE_PREFLIGHT"


def test_currency_covers_every_execution_identity() -> None:
    for field in ("repository_head", "manifest_sha256", "runner_sha256",
                  "collect_sha256", "control_sha256", "target_selection_sha256",
                  "authoritative_contract_sha256"):
        assert field in PREFLIGHT_CURRENCY_FIELDS
