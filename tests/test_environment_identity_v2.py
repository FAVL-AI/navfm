"""Controls for EXECUTION_ENVIRONMENT_IDENTITY_V2 and the provenance correction.

Two things are under test, and they fail in opposite directions.

The environment contract must DETECT a difference. A comparator that returns
PASS because it compares nothing would pass every happy-path test ever written,
so every equality-critical field is mutated in turn and the comparator must name
that field and no other.

The historical assertion must NOT MOVE. The defect being corrected was a
provenance field that changed when the machine changed, so the tests check the
assertion against a live machine whose state now contradicts it: ISAAC_SLOT
reads AVAILABLE while the frozen record says outcomes were not observable at the
design freeze. If those two ever agree merely because the GPU was repaired, the
regression is back.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.execution_environment import (  # noqa: E402
    CONTRACT_CRITICAL_FIELDS,
    EQUALITY_CRITICAL_FIELDS,
    OBSERVATIONAL_FIELDS,
    PAIRWISE_CRITICAL_FIELDS,
    arm_equivalence,
    contract_satisfied,
    digest,
    select,
    worktree_state,
)

_SPEC = importlib.util.spec_from_file_location(
    "amend_environment_identity_v2", REPO / "scripts" / "amend_environment_identity_v2.py"
)
assert _SPEC and _SPEC.loader
amend = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(amend)

AMENDMENT = REPO / "gates/BO10/environment_identity_v2_20260911.json"
PREFLIGHT = REPO / "gates/BO10/intervention_execution_preflight_20260911.json"


def _nest(flat: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for dotted, value in flat.items():
        node = out
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


def _set(snapshot: dict[str, Any], dotted: str, value: Any) -> dict[str, Any]:
    out = copy.deepcopy(snapshot)
    node = out
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    return out


@pytest.fixture
def env() -> dict[str, Any]:
    """A synthetic snapshot whose every field is distinct and identifiable."""
    flat = {f: f"value::{f}" for f in EQUALITY_CRITICAL_FIELDS}
    flat.update({f: f"observed::{f}" for f in OBSERVATIONAL_FIELDS})
    return _nest(flat)


# --------------------------------------------------------------------------
# The comparator must discriminate
# --------------------------------------------------------------------------


def test_identical_environments_are_equivalent(env: dict[str, Any]) -> None:
    verdict = arm_equivalence(env, copy.deepcopy(env))
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "PASS"
    assert verdict["INTERVENTION_COMPARISON"] == "VALID"
    assert verdict["mismatches"] == []
    assert verdict["fields_compared"] == len(EQUALITY_CRITICAL_FIELDS)


@pytest.mark.parametrize("field", EQUALITY_CRITICAL_FIELDS)
def test_every_equality_critical_field_is_detected(env: dict[str, Any], field: str) -> None:
    """A gate that cannot fail proves nothing, so each field is failed in turn."""
    other = _set(env, field, "MUTATED")
    verdict = arm_equivalence(env, other)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert verdict["INTERVENTION_COMPARISON"] == "INVALID"
    assert [m["field"] for m in verdict["mismatches"]] == [field]


@pytest.mark.parametrize("field", OBSERVATIONAL_FIELDS)
def test_observational_fields_are_tolerated(env: dict[str, Any], field: str) -> None:
    """Free memory and uptime differ between any two runs; requiring them to
    match would refuse every comparison ever made."""
    other = _set(env, field, "COMPLETELY DIFFERENT")
    verdict = arm_equivalence(env, other)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "PASS"
    assert verdict["mismatches"] == []


def test_a_missing_field_is_a_mismatch_not_a_pass(env: dict[str, Any]) -> None:
    """Absence must not be silently equal to absence-of-difference."""
    other = copy.deepcopy(env)
    del other["gpu"]["driver_version"]
    verdict = arm_equivalence(env, other)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert [m["field"] for m in verdict["mismatches"]] == ["gpu.driver_version"]
    assert verdict["mismatches"][0]["right"] == "<ABSENT>"


def test_kernel_release_mismatch(env: dict[str, Any]) -> None:
    other = _set(env, "host.kernel_release", "6.8.0-139-generic")
    verdict = arm_equivalence(env, other)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert verdict["INTERVENTION_COMPARISON"] == "INVALID"


def test_nvidia_module_mismatch(env: dict[str, Any]) -> None:
    other = _set(env, "gpu.kernel_module_version", "580.173.02")
    verdict = arm_equivalence(env, other)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert [m["field"] for m in verdict["mismatches"]] == ["gpu.kernel_module_version"]


def test_nvidia_driver_mismatch(env: dict[str, Any]) -> None:
    other = _set(env, "gpu.driver_version", "580.179.01")
    assert arm_equivalence(env, other)["ENVIRONMENT_EQUIVALENCE"] == "FAIL"


def test_isaac_version_mismatch(env: dict[str, Any]) -> None:
    other = _set(env, "isaac.isaacsim_version", "5.2.0.0")
    verdict = arm_equivalence(env, other)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert [m["field"] for m in verdict["mismatches"]] == ["isaac.isaacsim_version"]


def test_repository_head_mismatch(env: dict[str, Any]) -> None:
    other = _set(env, "repository.head", "0" * 40)
    verdict = arm_equivalence(env, other)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert [m["field"] for m in verdict["mismatches"]] == ["repository.head"]


def test_reboot_between_arms_is_detected_and_named(env: dict[str, Any]) -> None:
    """The no-reboot rule needs an instrument. Kernel release is not one: a
    reboot into the same kernel leaves it unchanged. boot_id is redrawn."""
    same_kernel_new_boot = _set(env, "session.boot_id", "a-different-boot-uuid")
    verdict = arm_equivalence(env, same_kernel_new_boot)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert verdict["reboot_detected_between_arms"] is True
    assert same_kernel_new_boot["host"]["kernel_release"] == env["host"]["kernel_release"]


def test_non_reboot_failure_is_not_reported_as_a_reboot(env: dict[str, Any]) -> None:
    other = _set(env, "runtime_contract.max_steps", 1800)
    assert arm_equivalence(env, other)["reboot_detected_between_arms"] is False


def test_torch_and_runtime_contract_drift_are_critical(env: dict[str, Any]) -> None:
    for field in ("python.torch_version", "python.torch_cuda_build",
                  "runtime_contract.control_dt", "runtime_contract.goal_tol_m",
                  "scientific_code.control_sha256"):
        assert arm_equivalence(env, _set(env, field, "X"))["ENVIRONMENT_EQUIVALENCE"] == "FAIL"


# --------------------------------------------------------------------------
# The frozen contract
# --------------------------------------------------------------------------


def test_contract_drift_is_detected(env: dict[str, Any]) -> None:
    frozen = select(env, CONTRACT_CRITICAL_FIELDS)
    assert contract_satisfied(env, frozen)["CONTRACT_SATISFIED"] == "PASS"
    drifted = _set(env, "gpu.driver_version", "580.179.01")
    verdict = contract_satisfied(drifted, frozen)
    assert verdict["CONTRACT_SATISFIED"] == "FAIL"
    assert [d["field"] for d in verdict["drift"]] == ["gpu.driver_version"]


def test_pairwise_fields_are_not_frozen_in_the_contract() -> None:
    """repository.head cannot be frozen by the amendment that the commit will
    carry, and boot_id cannot be frozen before the boot happens."""
    for field in PAIRWISE_CRITICAL_FIELDS:
        assert field not in CONTRACT_CRITICAL_FIELDS
        assert field in EQUALITY_CRITICAL_FIELDS


def test_observational_fields_are_in_no_critical_set() -> None:
    for field in OBSERVATIONAL_FIELDS:
        assert field not in EQUALITY_CRITICAL_FIELDS


def test_contract_digest_ignores_observational_change(env: dict[str, Any]) -> None:
    before = digest(select(env, CONTRACT_CRITICAL_FIELDS))
    noisy = _set(env, "observational.gpu_memory_used_mib", 9999)
    assert digest(select(noisy, CONTRACT_CRITICAL_FIELDS)) == before
    moved = _set(env, "host.kernel_release", "other")
    assert digest(select(moved, CONTRACT_CRITICAL_FIELDS)) != before


# --------------------------------------------------------------------------
# Deterministic regeneration
# --------------------------------------------------------------------------


def _history_and_contract() -> tuple[dict[str, Any], dict[str, Any]]:
    history = amend.verify_history()
    contract = select(_nest({f: f"value::{f}" for f in CONTRACT_CRITICAL_FIELDS}),
                      CONTRACT_CRITICAL_FIELDS)
    return history, contract


def test_regeneration_with_unchanged_content_is_identical() -> None:
    history, contract = _history_and_contract()
    first = amend.build_payload("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00",
                                history, contract)
    second = amend.build_payload("2099-12-31T23:59:59+00:00", "2099-12-31T23:59:59+00:00",
                                 history, contract)
    assert amend.diff_paths(amend.strip_volatile(first), amend.strip_volatile(second)) == []
    assert digest(amend.strip_volatile(first)) == digest(amend.strip_volatile(second))


def test_changed_critical_field_refuses_the_same_identity() -> None:
    history, contract = _history_and_contract()
    first = amend.build_payload("t", "b", history, contract)
    moved = dict(contract, **{"gpu.driver_version": "580.179.01"})
    second = amend.build_payload("t", "b", history, moved)
    drift = amend.diff_paths(amend.strip_volatile(second), amend.strip_volatile(first))
    assert drift, "a changed driver must not regenerate under the same V2 identity"
    assert any("gpu.driver_version" in d for d in drift)


def test_restoring_the_field_reproduces_the_original_digest() -> None:
    history, contract = _history_and_contract()
    original = digest(amend.strip_volatile(amend.build_payload("t", "b", history, contract)))
    moved = dict(contract, **{"gpu.driver_version": "580.179.01"})
    assert digest(amend.strip_volatile(
        amend.build_payload("t", "b", history, moved))) != original
    restored = dict(moved, **{"gpu.driver_version": contract["gpu.driver_version"]})
    assert digest(amend.strip_volatile(
        amend.build_payload("t", "b", history, restored))) == original


# --------------------------------------------------------------------------
# Historical provenance: it must not move
# --------------------------------------------------------------------------


def test_provenance_verifies_against_the_pinned_commit() -> None:
    history = amend.verify_history()
    assert history["PROVENANCE"] == "VERIFIED"
    assert history["controls_passed"] == history["controls_total"]


def test_provenance_source_hash_is_load_bearing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: if the pinned hash stops matching, the claim must be
    refused rather than asserted from whatever the file happens to say."""
    monkeypatch.setattr(amend, "FREEZE_SOURCE_SHA256", "0" * 64)
    history = amend.verify_history()
    assert history["PROVENANCE"] == "INCONCLUSIVE"


def test_provenance_source_commit_is_load_bearing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(amend, "FREEZE_COMMIT", "0" * 40)
    assert amend.verify_history()["PROVENANCE"] == "INCONCLUSIVE"


def test_inconclusive_provenance_refuses_to_assert_the_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unverifiable history yields a null, never a convenient False."""
    monkeypatch.setattr(amend, "FREEZE_SOURCE_SHA256", "0" * 64)
    history = amend.verify_history()
    payload = amend.build_payload("t", "b", history, {})
    assert payload["design_freeze"]["STATUS"] == "INCONCLUSIVE"
    assert payload["design_freeze"]["outcomes_observable_at_freeze"] is None


def test_the_historical_assertion_contradicts_the_live_machine() -> None:
    """The whole point. The GPU works now; the record still says it did not
    when the design was frozen. If these ever agree because the machine was
    repaired, the field has gone back to being recomputed."""
    amendment = json.loads(AMENDMENT.read_text())
    preflight = json.loads(PREFLIGHT.read_text())
    assert preflight["live_execution_readiness"]["isaac_slot"] == "AVAILABLE"
    assert preflight["live_execution_readiness"]["cuda_available"] is True
    assert amendment["design_freeze"]["outcomes_observable_at_freeze"] is False
    assert preflight["design_freeze"]["outcomes_observable_at_freeze"] is False
    assert preflight["design_freeze"]["recomputed_by_this_preflight"] is False


def test_design_freeze_matches_the_frozen_blob_not_the_working_tree() -> None:
    blob = amend.frozen_blob()
    assert blob is not None
    _, frozen = blob
    amendment = json.loads(AMENDMENT.read_text())
    basis = amendment["design_freeze"]["basis"]
    assert amendment["design_freeze"]["frozen_at_utc"] == frozen["timestamp_utc"]
    assert basis["repository_commit"] == amend.FREEZE_COMMIT
    assert basis["source_sha256"] == amend.FREEZE_SOURCE_SHA256
    assert basis["supporting_values_read_from_the_frozen_source"]["ISAAC_SLOT"] == "BLOCKED"
    # the working-tree artefact now says the opposite, and is not the source
    assert json.loads(PREFLIGHT.read_text())["isaac_slot"]["ISAAC_SLOT"] == "AVAILABLE"


def test_the_regressed_field_is_no_longer_emitted_as_a_boolean() -> None:
    preflight = json.loads(PREFLIGHT.read_text())
    field = preflight["arm_identity_and_order"]["frozen_while_results_were_impossible_to_observe"]
    assert field == "DEPRECATED_FOR_PROVENANCE_INTERPRETATION"
    assert not isinstance(field, bool)


def test_the_regression_is_recorded_rather_than_erased() -> None:
    record = json.loads(AMENDMENT.read_text())["PROVENANCE_FIELD_REGRESSION_V1"]
    assert record["observed_value_pre_reboot"] is True
    assert record["observed_value_post_reboot"] is False
    assert record["status"] == "DEPRECATED_FOR_PROVENANCE_INTERPRETATION"
    assert record["old_artefacts_rewritten"] is False


def test_live_readiness_is_recomputed_and_matches_the_live_probe() -> None:
    preflight = json.loads(PREFLIGHT.read_text())
    live = preflight["live_execution_readiness"]
    assert live["recomputed_every_run"] is True
    assert live["isaac_slot"] == preflight["isaac_slot"]["ISAAC_SLOT"]
    assert live["driver_version"] == preflight["isaac_slot"]["userspace_version"]


# --------------------------------------------------------------------------
# Working-tree policy
# --------------------------------------------------------------------------


def test_worktree_policy_is_deny_by_default(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert worktree_state(tmp_path) == "clean"

    (tmp_path / "arm_a.json").write_text("{}")
    dirty = worktree_state(tmp_path)
    assert dirty.startswith("dirty:")
    assert "arm_a.json" in dirty

    assert worktree_state(tmp_path, allowed=["arm_a.json"]) == "clean"

    (tmp_path / "unrelated.py").write_text("x = 1\n")
    still_dirty = worktree_state(tmp_path, allowed=["arm_a.json"])
    assert still_dirty.startswith("dirty:")
    assert "unrelated.py" in still_dirty
    assert "arm_a.json" not in still_dirty


def test_worktree_allow_list_is_prefix_scoped(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "arm_a.json").write_text("{}")
    assert worktree_state(tmp_path, allowed=["runs/"]) == "clean"
    assert worktree_state(tmp_path, allowed=["run/"]).startswith("dirty:")


# --------------------------------------------------------------------------
# The amendment as an artefact
# --------------------------------------------------------------------------


def test_amendment_declares_no_arm_has_run() -> None:
    amendment = json.loads(AMENDMENT.read_text())
    assert amendment["EXECUTION_STATUS"] == "NOT_RUN"
    assert amendment["arms_executed"] == 0
    assert amendment["STATUS"] == "FROZEN"
    assert "NOT AUTHORISED" in amendment["authorisation"]


def test_amendment_is_append_only_and_changes_no_science() -> None:
    amends = json.loads(AMENDMENT.read_text())["amends"]
    assert amends["append_only"] is True
    assert amends["the_intervention_itself_is_unchanged"] is True
    assert amends["original_preregistration"]["version"] == "V1"
    for held in ("the seed", "arm order", "max_steps", "the target-selection factor"):
        assert held in amends["unchanged_by_this_amendment"]


def test_amendment_does_not_release_the_nvidia_holds() -> None:
    policy = json.loads(AMENDMENT.read_text())["NVIDIA_HOLD_POLICY"]
    assert policy["released_in_this_tranche"] is False
    assert policy["expected_hold_count"] == 22
    assert policy["expected_driver_version"] == "580.178.04"
    assert "Arm B" in policy["holds_must_remain_through"]


def test_kernel_policy_adds_no_holds_and_forbids_a_reboot() -> None:
    policy = json.loads(AMENDMENT.read_text())["KERNEL_UPDATE_POLICY"]
    assert policy["no_new_kernel_holds_added"] is True
    assert policy["rule"] == "NO_REBOOT_PERMITTED_BETWEEN_ARM_A_AND_ARM_B"


def test_mismatch_policy_forbids_rescuing_the_comparison() -> None:
    policy = json.loads(AMENDMENT.read_text())["ENVIRONMENT_MISMATCH_POLICY"]
    forbidden = " ".join(policy["forbidden"])
    assert "averaging across environments" in forbidden
    assert "less favourable arm" in forbidden


def test_isaac_slot_claim_boundary_is_preserved() -> None:
    boundary = json.loads(AMENDMENT.read_text())["ISAAC_SLOT_CLAIM_BOUNDARY"]
    assert "INFERENCE" in boundary["status_of_ISAAC_SLOT_AVAILABLE"]
    assert any("rendering" in c for c in boundary["it_does_not_establish"])
    assert any("scene loading" in c for c in boundary["it_does_not_establish"])


def test_arm_guard_is_defined_but_not_implemented() -> None:
    guard = json.loads(AMENDMENT.read_text())["ARM_ENVIRONMENT_GUARD"]
    assert guard["defined_here"] is True
    assert guard["implemented_here"] is False
    assert guard["captures_required_later"] == [
        "PRE_ARM_A", "POST_ARM_A", "PRE_ARM_B", "POST_ARM_B"]
