"""Controls for V8, Manifest V5, and attempt provenance.

V7 pinned a tree whose real path was entered. Attempt 001 proved that was true:
it entered the lifecycle, created a valid PRE_ARM_A, launched Isaac, built the
collector, and stopped at scene loading because the adapter had handed the
collector a ``SimConfig`` where a live ``IsaacApp`` was required.

The distinction V8 holds:

    the real path is entered
        !=
    the objects that path needs are propagated across it

Every readiness gate before Attempt 001 compared configuration, and the
configuration was correct throughout. So these controls compare objects.

They also hold the provenance line. Attempt 001 is not a navigation outcome --
no episode ran -- and its capture must stay byte-identical forever, because it
is the evidence that a failed attempt entered the production lifecycle under a
valid environment.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from navfm.arm_environment_guard import (
    AUTHORITATIVE_CONTRACT_VERSION,
    CONTRACTS,
    V7_AMENDMENT_REL,
    V7_AMENDMENT_SHA256,
    check_contract,
    is_production_label,
    parse_attempt,
    parse_label,
)
from navfm.execution_environment import CONTRACT_FIELDS_BY_VERSION

REPO = Path(__file__).resolve().parents[1]
V8_REL = "gates/BO10/environment_identity_v8_20260917.json"
SEAM_REL = "gates/BO10/adapter_collector_app_seam_20260917.json"
ATTEMPT_REL = "gates/BO10/arm_a_attempt_001_20260917.json"
ATTEMPT_001_PRE = "runs/bo10/intervention/arm_a/pre_capture.json"
V7_FREEZE_COMMIT = "01916dfa3a2901177ae1bc07caffd0881139d798"

V8 = REPO / V8_REL

_SPEC = importlib.util.spec_from_file_location(
    "amend_v8", REPO / "scripts" / "amend_environment_identity_v8.py")
assert _SPEC and _SPEC.loader
v8mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v8mod)


def _sha() -> str:
    return hashlib.sha256(V8.read_bytes()).hexdigest()


@pytest.fixture
def amendment() -> dict[str, Any]:
    return json.loads(V8.read_text())


@pytest.fixture
def attempt() -> dict[str, Any]:
    return json.loads((REPO / ATTEMPT_REL).read_text())


# --- the chain ---------------------------------------------------------------

def test_v8_is_authoritative() -> None:
    assert AUTHORITATIVE_CONTRACT_VERSION == "V8"
    assert {"V2", "V3", "V4", "V5", "V6", "V7", "V8"} <= set(CONTRACTS)


@pytest.mark.archive
def test_v8_accepts_the_repaired_tree(amendment: dict[str, Any]) -> None:
    """Archived repaired source/host evidence, never current-tree attestation."""
    from navfm.execution_environment import _SCIENTIFIC_SOURCES
    seam = json.loads((REPO / SEAM_REL).read_text())
    frozen = amendment["EXECUTION_ENVIRONMENT_IDENTITY_V8"]["frozen_contract_values"]
    for key, relative in _SCIENTIFIC_SOURCES.items():
        field = f"scientific_code.{key}"
        if field not in frozen:
            continue
        blob = subprocess.run(["git", "-C", str(REPO), "show",
                               f"{seam['repository_head']}:{relative}"],
                              capture_output=True, check=True).stdout
        assert hashlib.sha256(blob).hexdigest() == frozen[field], field
    archived = Path(os.environ.get("NAVFM_ARCHIVE_ROOT", str(REPO))) / ATTEMPT_001_PRE
    raw = archived.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == amendment["ARM_A_ATTEMPT_001"]["pre_capture"]["sha256"]
    observed = json.loads(raw)["equality_critical_snapshot"]
    # V8 changed software; the original measured host/runtime fields are retained.
    for field, value in frozen.items():
        if field.startswith(("host.", "gpu.", "python.", "isaac.", "runtime_contract.")):
            assert observed[field] == value, field


@pytest.mark.isaac_host
@pytest.mark.parametrize("version", ["V2", "V3", "V4", "V5", "V6", "V7"])
def test_every_predecessor_still_refuses(version: str) -> None:
    """Permanent. If any of these passes, an old contract was rewritten."""
    assert check_contract(REPO, version)["CONTRACT_SATISFIED"] == "FAIL"


@pytest.mark.isaac_host
def test_v7_refuses_for_the_seam_repair_specifically() -> None:
    drift = [d["field"] for d in check_contract(REPO, "V7")["drift"]]
    assert "scientific_code.collect_sha256" in drift


def test_v8_pins_the_same_fields_as_v7() -> None:
    """Both files that moved were already pinned; a new field would add nothing."""
    assert CONTRACT_FIELDS_BY_VERSION["V8"] == CONTRACT_FIELDS_BY_VERSION["V7"]


def test_v7_is_byte_unchanged() -> None:
    assert hashlib.sha256(
        (REPO / V7_AMENDMENT_REL).read_bytes()).hexdigest() == V7_AMENDMENT_SHA256


def test_every_moved_value_carries_a_rationale(amendment: dict[str, Any]) -> None:
    transitions = amendment["SOURCE_IDENTITY_TRANSITIONS_V7_TO_V8"]
    assert set(transitions["expected_change"]) == set(transitions["changed"])
    assert all(len(t) > 40 for t in transitions["expected_change"].values())


def test_the_manipulated_factor_did_not_move(amendment: dict[str, Any]) -> None:
    changed = amendment["SOURCE_IDENTITY_TRANSITIONS_V7_TO_V8"]["changed"]
    for untouched in ("scientific_code.control_sha256",
                      "scientific_code.target_selection_sha256",
                      "scientific_code.preregistration_sha256"):
        assert untouched not in changed, untouched


# --- attempt 001 -------------------------------------------------------------

def test_attempt_001_is_not_a_navigation_outcome(attempt: dict[str, Any]) -> None:
    """No episode ran, so there is no success and no failure to report."""
    assert attempt["CLASSIFICATION"] == "INFRASTRUCTURE_FAILURE_BEFORE_EPISODE"
    assert attempt["EPISODE_STARTED"] is False
    assert attempt["ARM_A_SCIENTIFIC_RESULT"] == "NOT_OBSERVED"
    # Recording success=false would assert a completed trial that never began.
    assert "success" not in attempt
    for excluded in ("n", "SR", "OSR", "goal distance", "cross-track"):
        assert excluded in attempt["excluded_from"]


def test_attempt_001_observed_facts_match_what_ran(attempt: dict[str, Any]) -> None:
    observed = attempt["observed"]
    assert observed["isaac_process_launched"] is True
    assert observed["collector_constructed"] is True
    assert observed["hospital_scene_loaded"] is False
    assert observed["trajectory_produced"] is False
    assert observed["arm_b_touched"] is False
    assert observed["refusal"]["stage"] == "SCENE_READY"
    assert observed["refusal"]["escaped_exception"] is True


@pytest.mark.archive
def test_attempt_001_pre_capture_is_preserved_byte_for_byte(
    attempt: dict[str, Any],
) -> None:
    """The capture is evidence. If this fails, it was rewritten or recycled."""
    pre = attempt["ATTEMPT_001_PRE_CAPTURE"]
    assert pre["PRESERVED"] is True
    assert pre["path"] == ATTEMPT_001_PRE
    archive_root = Path(os.environ.get("NAVFM_ARCHIVE_ROOT", str(REPO)))
    on_disk = hashlib.sha256((archive_root / ATTEMPT_001_PRE).read_bytes()).hexdigest()
    assert on_disk == pre["sha256"]
    assert pre["label"] == "PRE_ARM_A"
    assert pre["capture_validation"] == "PASS"


def test_a_repaired_attempt_cannot_write_over_attempt_001(
    amendment: dict[str, Any],
) -> None:
    model = amendment["ATTEMPT_IDENTITY_MODEL"]
    assert model["attempt_001_preserved"] is True
    assert model["resolved_from"].startswith("the frozen manifest")
    assert "001" in model["attempt_ids"] and "002" in model["attempt_ids"]


# --- attempt labels ----------------------------------------------------------

def test_an_unnumbered_label_still_means_attempt_one() -> None:
    """PRE_ARM_A predates numbering and must not become malformed."""
    assert parse_label("PRE_ARM_A") == ("A", "PRE")
    assert parse_attempt("PRE_ARM_A") is None
    assert is_production_label("PRE_ARM_A") is True


def test_a_numbered_label_parses_and_stays_production() -> None:
    assert parse_label("PRE_ARM_A_ATTEMPT_002") == ("A", "PRE")
    assert parse_attempt("PRE_ARM_A_ATTEMPT_002") == "002"
    assert is_production_label("PRE_ARM_A_ATTEMPT_002") is True


def test_the_label_set_is_still_closed() -> None:
    """The attempt number is open. The base label is not."""
    for bogus in ("NONSENSE", "PRE_ARM_C", "PRE_ARM_A_ATTEMPT_X", "ARM_A"):
        with pytest.raises(ValueError):
            parse_label(bogus)


# --- the seam ----------------------------------------------------------------

def test_the_seam_evidence_is_bound_by_hash(amendment: dict[str, Any]) -> None:
    seam = amendment["ADAPTER_COLLECTOR_APP_SEAM"]
    assert seam["artefact"]["sha256"] == hashlib.sha256(
        (REPO / SEAM_REL).read_bytes()).hexdigest()
    assert seam["verdict"] == "REPAIRED_AND_VALIDATED"


def test_the_seam_facts_are_about_objects_not_configuration(
    amendment: dict[str, Any],
) -> None:
    seam = amendment["ADAPTER_COLLECTOR_APP_SEAM"]
    assert seam["same_object"] is True
    assert seam["applications_constructed"] == 1
    assert seam["open_stage_calls"] == 1
    assert seam["bare_assert_removed"] is True
    assert seam["collector_accepts_a_live_app"] is True
    assert seam["adapter_passes_the_app"] is True


def test_every_seam_control_fired(amendment: dict[str, Any]) -> None:
    controls = amendment["ADAPTER_COLLECTOR_APP_SEAM"]["negative_controls"]
    assert controls, "no controls were recorded"
    assert all(controls.values()), controls
    assert controls["config_only_is_refused"] is True


def test_arm_a_behaviour_is_unchanged(amendment: dict[str, Any]) -> None:
    regression = amendment["ARM_A_BEHAVIOURAL_REGRESSION"]
    assert regression["verdict"] == "PASS"
    for name, trace in regression["traces"].items():
        assert trace["steps_evaluated"] == 1200, name
        assert trace["mismatches"] == 0, name


# --- where V8 stops ----------------------------------------------------------

def test_v8_reports_level_five_as_partial(amendment: dict[str, Any]) -> None:
    """Isaac launches. That is now known, and it is not an episode."""
    levels = amendment["READINESS_MODEL"]
    assert levels["LEVEL_4_6_RUNTIME_OBJECT_PROPAGATION"] == "established by V8"
    assert levels["LEVEL_5_REAL_RUNTIME_ATTEMPT"].startswith("PARTIAL")
    assert "Hospital scene loads" in levels["LEVEL_5_REAL_RUNTIME_ATTEMPT"]


def test_v8_does_not_claim_the_scene_loads(amendment: dict[str, Any]) -> None:
    boundary = amendment["EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY"]
    for unclaimed in ("Hospital scene loads", "render loop", "completes an episode"):
        assert unclaimed in boundary, unclaimed
    assert amendment["authorisation"].startswith("NOT AUTHORISED")


def test_no_arm_has_executed(amendment: dict[str, Any]) -> None:
    assert amendment["EXECUTION_STATUS"] == "NOT_RUN"
    assert amendment["arms_executed"] == 0
    assert amendment["ARM_A_ATTEMPT_002"] == "NOT_STARTED"
    assert amendment["ARM_B_EXECUTION"] == "NOT_STARTED"


def test_v8_freezes_no_execution_manifest(amendment: dict[str, Any]) -> None:
    assert amendment["EXECUTION_MANIFEST"] == "NOT_FROZEN_BY_THIS_AMENDMENT"


# --- refusal controls --------------------------------------------------------

@pytest.mark.archive
def test_regeneration_on_an_unchanged_tree_is_idempotent(amendment: dict[str, Any]) -> None:
    """Rebuild archived canonical payload without writing or measuring today's host."""
    before = _sha()
    archived = Path(os.environ.get("NAVFM_ARCHIVE_ROOT", str(REPO))) / ATTEMPT_001_PRE
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == amendment["ARM_A_ATTEMPT_001"]["pre_capture"]["sha256"]
    seam = v8mod.verify_seam()
    assert seam["ok"], seam["reasons"]
    attempt = {"record": json.loads((REPO / ATTEMPT_REL).read_text())}
    rebuilt = v8mod.build_payload(amendment["amended_at_utc"], seam, attempt,
                                 amendment["EXECUTION_ENVIRONMENT_IDENTITY_V8"]["frozen_contract_values"])
    assert v8mod.diff_paths(v8mod.strip_volatile(rebuilt), v8mod.strip_volatile(amendment)) == []
    assert _sha() == before


@pytest.mark.parametrize("attribute", ["PREREG_SHA256", "CONTROL_SHA256"])
def test_a_mutated_pin_refuses_and_writes_nothing(
    attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _sha()
    monkeypatch.setattr(v8mod, attribute, "0" * 64)
    assert v8mod.freeze()["V8_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_a_failed_seam_blocks_the_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    """V8's central claim is the seam. It must not survive losing it."""
    before = _sha()
    monkeypatch.setattr(v8mod, "verify_seam", lambda: {
        "ok": False, "reasons": ["the seam did not validate"], "record": None})
    assert v8mod.freeze()["V8_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_a_rewritten_attempt_001_capture_blocks_the_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one provenance rule this tranche exists to hold."""
    before = _sha()
    real_sha = v8mod.sha256_file

    def as_if_rewritten(path: Path) -> str | None:
        # The capture on disk no longer hashes to what the record bound.
        if path.name == "pre_capture.json":
            return "0" * 64
        return real_sha(path)

    monkeypatch.setattr(v8mod, "sha256_file", as_if_rewritten)
    outcome = v8mod.freeze()
    assert outcome["V8_AMENDMENT"] == "REFUSED"
    assert any("never be rewritten" in r for r in outcome["reasons"]), outcome["reasons"]
    assert _sha() == before


def test_the_amender_declines_rather_than_raising() -> None:
    assert "recorded scientific result" in v8mod.refused("probe", ["reason"])["note"]


def test_v7_is_still_readable_from_history() -> None:
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{V7_FREEZE_COMMIT}:{V7_AMENDMENT_REL}"],
        capture_output=True, check=False)
    assert proc.returncode == 0
    assert hashlib.sha256(proc.stdout).hexdigest() == V7_AMENDMENT_SHA256


@pytest.mark.isaac_host
def test_current_candidate_is_refused_by_historical_v8() -> None:
    result = check_contract(REPO, "V8")
    assert result["CONTRACT_SATISFIED"] == "FAIL"
    assert "scientific_code.collect_sha256" in {d["field"] for d in result["drift"]}
