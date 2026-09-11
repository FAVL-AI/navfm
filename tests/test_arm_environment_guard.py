"""Controls for PER_ARM_ENVIRONMENT_EQUIVALENCE_GUARD_V1.

The guard's whole value is that it refuses. So every control here drives it to
a refusal for a stated reason and checks that the reason is the intended one --
a gate that refuses for the wrong reason is as untrustworthy as one that never
refuses, because the next person fixes the wrong thing.

The preflight exception gets its own git repository per test. Reasoning about
what ``git status`` would say is not evidence about what it does say, and the
exception's entire job is to be narrower than it looks.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import navfm.arm_environment_guard as guard  # noqa: E402
from navfm.arm_environment_guard import (  # noqa: E402
    EXPECTED_DRIVER_VERSION,
    PREFLIGHT_REL,
    PREFLIGHT_SCIENTIFIC_FIELDS,
    PREFLIGHT_VOLATILE_FIELDS,
    PRODUCTION_LABELS,
    SCENE_BYTE_IDENTITY,
    SELFTEST_LABELS,
    arm_environment_equivalence,
    canonical_preflight,
    nvidia_hold_state,
    parse_label,
    preflight_exception,
    preflight_identity,
    reboot_detection,
    scene_identity,
    validate_post_arm_environment,
    validate_pre_arm_environment,
)
from navfm.execution_environment import (  # noqa: E402
    EQUALITY_CRITICAL_FIELDS,
    OBSERVATIONAL_FIELDS,
    digest,
)

_ABSENT = "<ABSENT>"

#: Two tests assert the state of THIS host's driver stack. Elsewhere -- CI, a
#: laptop -- there is no nvidia-smi and no apt hold list, so they are skipped
#: with a reason rather than failed: a missing instrument is the absence of a
#: measurement, not a negative result. The guard's refusal paths carry no such
#: guard, because they must hold everywhere.
_ON_THE_FROZEN_HOST = bool(shutil.which("nvidia-smi") and shutil.which("apt-mark"))
requires_frozen_host = pytest.mark.skipif(
    not _ON_THE_FROZEN_HOST,
    reason="no nvidia-smi / apt-mark on this host; the loaded driver stack cannot be read",
)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def _capture(label: str, **overrides: Any) -> dict[str, Any]:
    snapshot = {f: f"value::{f}" for f in EQUALITY_CRITICAL_FIELDS}
    snapshot.update(overrides)
    return {
        "label": label,
        "arm": parse_label(label)[0],
        "phase": parse_label(label)[1],
        "CAPTURE_VALIDATION": "PASS",
        "equality_critical_snapshot": snapshot,
        "observational": {f: f"observed::{label}::{f}" for f in OBSERVATIONAL_FIELDS},
    }


def _four(**overrides_by_label: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _capture(label, **overrides_by_label.get(label, {})) for label in PRODUCTION_LABELS
    ]


def _minimal_preflight() -> dict[str, Any]:
    return {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_EXECUTION_PREFLIGHT",
        "timestamp_utc": "2026-09-11T10:00:00+00:00",
        "SOFTWARE_PREFLIGHT": "PASS",
        "EXECUTION_GATE": "OPEN",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "preregistration": {"path": "p", "sha256": "a" * 64},
        "gates": {"PREREG_CANONICAL_PAYLOAD_GUARD": {"verdict": "PASS"}},
        "implementation_difference_audit": {"ONLY_TARGET_SELECTION_DIFFERS": True},
        "arm_identity_and_order": {"execution_order": ["ARM_A_CONTROL", "ARM_B_TREATMENT"]},
        "design_freeze": {"outcomes_observable_at_freeze": False},
        "amendment": {"sha256": "b" * 64},
        "isaac_slot": {
            "ISAAC_SLOT": "AVAILABLE",
            "userspace_version": EXPECTED_DRIVER_VERSION,
            "kernel_module_version": EXPECTED_DRIVER_VERSION,
            "cuda_probe": {"available": True, "count": 1},
            "nvidia_smi_stderr": ["Fri Sep 11 10:00:00 2026", "+---+"],
        },
    }


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A real git repository carrying a committed preflight artefact."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    target = tmp_path / PREFLIGHT_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_minimal_preflight(), indent=2) + "\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.email=f@e", "-c", "user.name=F",
         "commit", "-q", "-m", "seed"],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return tmp_path, head


def _rewrite(root: Path, payload: dict[str, Any]) -> None:
    (root / PREFLIGHT_REL).write_text(json.dumps(payload, indent=2) + "\n")


# --------------------------------------------------------------------------
# labels and schema
# --------------------------------------------------------------------------


def test_four_production_labels_are_declared() -> None:
    assert PRODUCTION_LABELS == ("PRE_ARM_A", "POST_ARM_A", "PRE_ARM_B", "POST_ARM_B")


@pytest.mark.parametrize(
    ("label", "arm", "phase"),
    [
        ("PRE_ARM_A", "A", "PRE"),
        ("POST_ARM_A", "A", "POST"),
        ("PRE_ARM_B", "B", "PRE"),
        ("POST_ARM_B", "B", "POST"),
        ("SELFTEST_A", "A", "SELFTEST"),
        ("SELFTEST_B", "B", "SELFTEST"),
    ],
)
def test_label_parsing(label: str, arm: str, phase: str) -> None:
    assert parse_label(label) == (arm, phase)


def test_unknown_label_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown capture label"):
        parse_label("PRE_ARM_C")


def test_selftest_labels_are_not_production_labels() -> None:
    assert not set(SELFTEST_LABELS) & set(PRODUCTION_LABELS)


# --------------------------------------------------------------------------
# four-way comparator
# --------------------------------------------------------------------------


def test_four_identical_captures_are_equivalent() -> None:
    verdict = arm_environment_equivalence(*_four())
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "PASS"
    assert verdict["INTERVENTION_COMPARISON"] == "VALID"
    assert verdict["mismatch_count"] == 0
    assert verdict["fields_compared"] == len(EQUALITY_CRITICAL_FIELDS)
    assert verdict["REBOOT_DETECTED"] is False


@pytest.mark.parametrize("field", EQUALITY_CRITICAL_FIELDS)
def test_every_critical_field_is_detected_in_every_position(field: str) -> None:
    for label in PRODUCTION_LABELS:
        verdict = arm_environment_equivalence(*_four(**{label: {field: "MUTATED"}}))
        assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
        assert verdict["INTERVENTION_COMPARISON"] == "INVALID"
        assert [m["field"] for m in verdict["mismatches"]] == [field]


def test_mismatch_reports_all_four_values_and_a_class() -> None:
    verdict = arm_environment_equivalence(
        *_four(POST_ARM_B={"gpu.driver_version": "580.179.01"})
    )
    (mismatch,) = verdict["mismatches"]
    assert mismatch["field"] == "gpu.driver_version"
    assert mismatch["PRE_ARM_A"] == "value::gpu.driver_version"
    assert mismatch["POST_ARM_A"] == "value::gpu.driver_version"
    assert mismatch["PRE_ARM_B"] == "value::gpu.driver_version"
    assert mismatch["POST_ARM_B"] == "580.179.01"
    assert mismatch["mismatch_class"] == "DRIVER_STACK_DRIFT"
    assert mismatch["changed_within_arm_b"] is True
    assert mismatch["changed_within_arm_a"] is False


def test_within_arm_change_is_localised() -> None:
    verdict = arm_environment_equivalence(*_four(POST_ARM_A={"host.kernel_release": "X"}))
    (mismatch,) = verdict["mismatches"]
    assert mismatch["changed_within_arm_a"] is True
    assert mismatch["changed_between_arms"] is True


def test_comparator_does_not_return_a_vague_verdict() -> None:
    verdict = arm_environment_equivalence(*_four(PRE_ARM_B={"isaac.isaacsim_version": "5.2"}))
    assert "ENVIRONMENT_CHANGED" not in json.dumps(verdict)
    assert verdict["mismatches"][0]["field"] == "isaac.isaacsim_version"


def test_failed_comparison_preserves_evidence_and_forbids_rescue() -> None:
    verdict = arm_environment_equivalence(*_four(POST_ARM_B={"host.kernel_release": "X"}))
    policy = verdict["if_failed"]
    assert policy["the_comparison_is_refused"] is True
    joined = " ".join(policy["forbidden"])
    assert "averaging across environments" in joined
    assert "less favourable arm" in joined
    assert "silently choosing the better pair" in joined
    assert verdict["mismatches"], "the differing fields must survive in the artefact"


def test_an_invalid_capture_fails_the_comparison() -> None:
    captures = _four()
    captures[1]["CAPTURE_VALIDATION"] = "FAIL"
    verdict = arm_environment_equivalence(*captures)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert verdict["invalid_captures"] == ["POST_ARM_A"]


# --------------------------------------------------------------------------
# named negative controls
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "expected_class"),
    [
        ("host.kernel_release", "6.8.0-139-generic", "KERNEL_DRIFT"),
        ("gpu.kernel_module_version", "580.173.02", "DRIVER_STACK_DRIFT"),
        ("gpu.driver_version", "580.179.01", "DRIVER_STACK_DRIFT"),
        ("isaac.isaacsim_version", "5.2.0.0", "SIMULATOR_DRIFT"),
        ("repository.head", "0" * 40, "REPOSITORY_DRIFT"),
        ("python.torch_version", "2.8.0+cu128", "INTERPRETER_DRIFT"),
        ("runtime_contract.max_steps", 1800, "RUNTIME_CONTRACT_DRIFT"),
        ("scientific_code.control_sha256", "f" * 64, "SCIENTIFIC_SOURCE_DRIFT"),
        ("scene.scene_asset", "file:///local/hospital.usd", "SCENE_IDENTIFIER_DRIFT"),
        ("session.boot_id", "another-boot", "REBOOT"),
    ],
)
def test_named_mismatch_identifies_the_intended_field_only(
    field: str, value: Any, expected_class: str
) -> None:
    verdict = arm_environment_equivalence(*_four(PRE_ARM_B={field: value}))
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert [m["field"] for m in verdict["mismatches"]] == [field]
    assert verdict["mismatches"][0]["mismatch_class"] == expected_class


@pytest.mark.parametrize("field", OBSERVATIONAL_FIELDS)
def test_observational_only_mutation_never_fails(field: str) -> None:
    captures = _four()
    captures[3]["observational"][field] = "WILDLY DIFFERENT"
    verdict = arm_environment_equivalence(*captures)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "PASS"
    assert verdict["mismatch_count"] == 0


# --------------------------------------------------------------------------
# missing fields
# --------------------------------------------------------------------------


def test_a_missing_critical_field_fails() -> None:
    captures = _four()
    del captures[2]["equality_critical_snapshot"]["gpu.uuid"]
    verdict = arm_environment_equivalence(*captures)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    (mismatch,) = verdict["mismatches"]
    assert mismatch["field"] == "gpu.uuid"
    assert mismatch["PRE_ARM_B"] == _ABSENT
    assert mismatch["mismatch_class"] == "MISSING_FIELD"


def test_missing_in_all_four_is_not_a_pass() -> None:
    """The FL-019 shape at field level: absent everywhere must not read as
    agreement. Four snapshots that all fail to record the driver have not
    demonstrated that the driver was the same."""
    captures = _four()
    for capture_payload in captures:
        del capture_payload["equality_critical_snapshot"]["gpu.driver_version"]
    verdict = arm_environment_equivalence(*captures)
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert [m["field"] for m in verdict["mismatches"]] == ["gpu.driver_version"]
    assert verdict["mismatches"][0]["mismatch_class"] == "MISSING_FIELD"


# --------------------------------------------------------------------------
# reboot detection
# --------------------------------------------------------------------------


def test_reboot_detected_by_boot_id_even_with_identical_kernel() -> None:
    captures = _four(PRE_ARM_B={"session.boot_id": "boot-2"})
    verdict = arm_environment_equivalence(*captures)
    assert verdict["REBOOT_DETECTED"] is True
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"
    assert verdict["INTERVENTION_COMPARISON"] == "INVALID"
    kernels = set(verdict["reboot_detection"]["kernel_releases"].values())
    assert len(kernels) == 1, "the kernel release did not move; boot_id did the work"


def test_kernel_drift_without_a_new_boot_id_is_not_called_a_reboot() -> None:
    verdict = arm_environment_equivalence(*_four(POST_ARM_B={"host.kernel_release": "6.9.0"}))
    assert verdict["REBOOT_DETECTED"] is False
    assert verdict["mismatches"][0]["mismatch_class"] == "KERNEL_DRIFT"
    assert verdict["ENVIRONMENT_EQUIVALENCE"] == "FAIL"


def test_reboot_detection_reports_every_boot_id() -> None:
    detection = reboot_detection(dict(zip(PRODUCTION_LABELS, _four(), strict=True)))
    assert set(detection["boot_ids"]) == set(PRODUCTION_LABELS)
    assert detection["distinct_boot_ids"] == 1
    assert detection["REBOOT_DETECTED"] is False


# --------------------------------------------------------------------------
# preflight exception: controls A-G
# --------------------------------------------------------------------------


def test_control_a_only_volatile_fields_change_accepts(repo: tuple[Path, str]) -> None:
    root, head = repo
    payload = _minimal_preflight()
    payload["timestamp_utc"] = "2026-09-11T18:30:00+00:00"
    payload["isaac_slot"]["nvidia_smi_stderr"] = ["Fri Sep 11 18:30:00 2026", "+---+"]
    _rewrite(root, payload)
    verdict = preflight_exception(root, head)
    assert verdict["PREFLIGHT_EXCEPTION"] == "ACCEPT", verdict["reasons"]
    assert verdict["dirty_paths"] == [PREFLIGHT_REL]
    assert verdict["live_canonical_sha"] == verdict["committed_canonical_sha"]


def test_control_b_scientific_field_change_refuses(repo: tuple[Path, str]) -> None:
    root, head = repo
    payload = _minimal_preflight()
    payload["SOFTWARE_PREFLIGHT"] = "FAIL"
    _rewrite(root, payload)
    verdict = preflight_exception(root, head)
    assert verdict["PREFLIGHT_EXCEPTION"] == "REFUSE"
    assert any("canonical payload changed" in r for r in verdict["reasons"])


def test_control_c_source_file_dirty_refuses(repo: tuple[Path, str]) -> None:
    root, head = repo
    payload = _minimal_preflight()
    payload["timestamp_utc"] = "2026-09-11T18:30:00+00:00"
    _rewrite(root, payload)
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "control.py").write_text("x = 1\n")
    verdict = preflight_exception(root, head)
    assert verdict["PREFLIGHT_EXCEPTION"] == "REFUSE"
    assert verdict["unexpected_paths"] == ["src/control.py"]
    assert any("paths other than the preflight artefact" in r for r in verdict["reasons"])


def test_control_d_unknown_untracked_file_refuses(repo: tuple[Path, str]) -> None:
    root, head = repo
    (root / "surprise.txt").write_text("hello\n")
    verdict = preflight_exception(root, head)
    assert verdict["PREFLIGHT_EXCEPTION"] == "REFUSE"
    assert verdict["unexpected_paths"] == ["surprise.txt"]


def test_control_e_head_change_refuses(repo: tuple[Path, str]) -> None:
    root, head = repo
    (root / "note.md").write_text("x\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=f@e", "-c", "user.name=F",
         "commit", "-q", "-m", "second"],
        check=True,
    )
    verdict = preflight_exception(root, head)
    assert verdict["PREFLIGHT_EXCEPTION"] == "REFUSE"
    assert any("HEAD is" in r for r in verdict["reasons"])


def test_control_f_missing_preflight_field_refuses(repo: tuple[Path, str]) -> None:
    root, head = repo
    payload = _minimal_preflight()
    del payload["EXECUTION_GATE"]
    _rewrite(root, payload)
    verdict = preflight_exception(root, head)
    assert verdict["PREFLIGHT_EXCEPTION"] == "REFUSE"
    assert any("missing required key" in r for r in verdict["reasons"])


def test_control_g_canonical_payload_change_refuses(repo: tuple[Path, str]) -> None:
    root, head = repo
    payload = _minimal_preflight()
    payload["arm_identity_and_order"]["execution_order"] = ["ARM_B_TREATMENT", "ARM_A_CONTROL"]
    _rewrite(root, payload)
    verdict = preflight_exception(root, head)
    assert verdict["PREFLIGHT_EXCEPTION"] == "REFUSE"
    assert any("canonical payload changed" in r for r in verdict["reasons"])


def test_clean_tree_also_accepts(repo: tuple[Path, str]) -> None:
    root, head = repo
    verdict = preflight_exception(root, head)
    assert verdict["PREFLIGHT_EXCEPTION"] == "ACCEPT"
    assert verdict["dirty_paths"] == []


def test_the_exception_is_not_a_dirty_tree_tolerance(repo: tuple[Path, str]) -> None:
    root, head = repo
    (root / "gates" / "BO10" / "other_evidence.json").write_text("{}\n")
    verdict = preflight_exception(root, head)
    assert verdict["PREFLIGHT_EXCEPTION"] == "REFUSE"
    assert "gates/BO10/other_evidence.json" in verdict["unexpected_paths"]


# --------------------------------------------------------------------------
# canonical preflight: the exclusion list must hide nothing scientific
# --------------------------------------------------------------------------


def test_volatile_exclusions_are_exactly_two_presentation_fields() -> None:
    assert PREFLIGHT_VOLATILE_FIELDS == ("timestamp_utc", "isaac_slot.nvidia_smi_stderr")


@pytest.mark.parametrize("field", PREFLIGHT_SCIENTIFIC_FIELDS)
def test_every_scientific_field_survives_canonicalisation(field: str) -> None:
    """If a scientific field could be dropped without moving the canonical
    digest, the exclusion list would be hiding it."""
    base = canonical_preflight(_minimal_preflight())
    mutated = copy.deepcopy(_minimal_preflight())
    node: Any = mutated
    parts = field.split(".")
    for part in parts[:-1]:
        node = node[part]
    node.pop(parts[-1])
    assert digest(canonical_preflight(mutated)) != digest(base)


def test_parsed_driver_versions_are_not_excluded() -> None:
    canonical = canonical_preflight(_minimal_preflight())
    assert canonical["isaac_slot"]["userspace_version"] == EXPECTED_DRIVER_VERSION
    assert canonical["isaac_slot"]["kernel_module_version"] == EXPECTED_DRIVER_VERSION
    assert "nvidia_smi_stderr" not in canonical["isaac_slot"]


def test_missing_preflight_file_reports_absence_not_success(tmp_path: Path) -> None:
    identity = preflight_identity(tmp_path / "nope.json")
    assert identity["present"] is False
    assert identity["CANONICAL_PREFLIGHT_SHA"] is None
    assert identity["missing_required_keys"]


# --------------------------------------------------------------------------
# NVIDIA holds
# --------------------------------------------------------------------------


@requires_frozen_host
def test_nvidia_hold_guard_passes_on_this_machine() -> None:
    state = nvidia_hold_state()
    assert state["HOLD_GUARD"] == "PASS", state["reasons"]
    assert state["held_count"] == 22
    assert state["loaded_driver_version"] == EXPECTED_DRIVER_VERSION
    assert state["loaded_module_version"] == EXPECTED_DRIVER_VERSION
    assert state["holds_released"] is False


def test_nvidia_hold_guard_can_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control. A guard that cannot fail is not a guard."""
    monkeypatch.setattr(guard, "EXPECTED_DRIVER_VERSION", "999.99.99")
    state = guard.nvidia_hold_state()
    assert state["HOLD_GUARD"] == "FAIL"
    assert any("loaded driver" in r for r in state["reasons"])
    assert any("loaded kernel module" in r for r in state["reasons"])


@requires_frozen_host
def test_hold_list_is_not_a_substitute_for_the_loaded_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(guard, "EXPECTED_DRIVER_VERSION", "999.99.99")
    state = guard.nvidia_hold_state()
    assert state["hold_list_present"] is True
    assert state["held_count"] == 22
    assert state["HOLD_GUARD"] == "FAIL", (
        "a correct hold list with a stale loaded driver must still fail")


def test_absent_tools_fail_the_guard_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a host with no nvidia-smi or apt-mark the guard must refuse, not
    crash and not pass. An unreadable driver stack is UNKNOWN, and UNKNOWN is
    never PASS."""
    real = subprocess.run

    def absent(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        if cmd and cmd[0] in {"apt-mark", "nvidia-smi"}:
            raise FileNotFoundError(cmd[0])
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr(guard.subprocess, "run", absent)
    state = guard.nvidia_hold_state()
    assert state["HOLD_GUARD"] == "FAIL"
    assert state["held_count"] == 0
    assert state["loaded_driver_version"] is None
    assert any("UNKNOWN" in r for r in state["reasons"])


def test_missing_hold_list_is_reported() -> None:
    state = nvidia_hold_state(hold_list="/nonexistent/holds.txt")
    assert state["HOLD_GUARD"] == "FAIL"
    assert state["hold_list_present"] is False


# --------------------------------------------------------------------------
# scene identity
# --------------------------------------------------------------------------


def test_scene_is_identifier_equivalent_not_byte_equivalent() -> None:
    identity = scene_identity({"isaac": {"isaacsim_version": "5.1.0.0"}})
    assert identity["scene_byte_identity"] == SCENE_BYTE_IDENTITY
    assert identity["equality_semantics"] == "IDENTIFIER_EQUIVALENCE_NOT_BYTE_EQUIVALENCE"
    assert identity["scene_asset_identifier"].startswith("https://")
    assert identity["isaac_version"] == "5.1.0.0"
    assert "identical bytes" in identity["what_it_does_not_demonstrate"]


def test_no_fabricated_scene_hash_anywhere() -> None:
    identity = scene_identity({"isaac": {}})
    assert not any(
        isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)
        for v in identity.values()
    ), "a 64-hex value here would be a fabricated scene SHA"


def test_comparison_artefact_carries_the_scene_boundary() -> None:
    verdict = arm_environment_equivalence(*_four())
    assert verdict["scene_equality_semantics"] == (
        "IDENTIFIER_EQUIVALENCE_NOT_BYTE_EQUIVALENCE")
    assert "NOT content-hashed" in verdict["scene_claim_boundary"]


# --------------------------------------------------------------------------
# barriers
# --------------------------------------------------------------------------


def test_post_arm_barrier_refuses_exit_zero_with_no_artefact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FL-019: a process that exits 0 having written nothing did not run."""
    monkeypatch.setattr(
        guard, "capture_arm_environment", lambda label, **kw: _capture(label))
    verdict = validate_post_arm_environment(
        "POST_ARM_A",
        repo_root=tmp_path,
        frozen_head="0" * 40,
        artefact_path=tmp_path / "absent.json",
        exit_code=0,
    )
    assert verdict["RUN_OUTCOME"] == "RUN_FAILED_NO_ARTEFACT"
    assert verdict["ARM_EXECUTION"] == "RUN_FAILED_NO_ARTEFACT"
    assert verdict["POST_ARM_BARRIER"] == "FAIL"


def test_post_arm_barrier_refuses_artefact_missing_required_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guard, "capture_arm_environment", lambda label, **kw: _capture(label))
    artefact = tmp_path / "arm.json"
    artefact.write_text(json.dumps({"something": 1}))
    verdict = validate_post_arm_environment(
        "POST_ARM_A",
        repo_root=tmp_path,
        frozen_head="0" * 40,
        artefact_path=artefact,
        exit_code=0,
        required_keys=("trajectory", "outcome"),
    )
    assert verdict["RUN_OUTCOME"] == "RUN_FAILED_NO_ARTEFACT"
    assert verdict["POST_ARM_BARRIER"] == "FAIL"


def test_post_arm_barrier_accepts_a_real_artefact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guard, "capture_arm_environment", lambda label, **kw: _capture(label))
    artefact = tmp_path / "arm.json"
    artefact.write_text(json.dumps({"trajectory": [], "outcome": "x"}))
    verdict = validate_post_arm_environment(
        "POST_ARM_A",
        repo_root=tmp_path,
        frozen_head="0" * 40,
        artefact_path=artefact,
        exit_code=0,
        required_keys=("trajectory", "outcome"),
    )
    assert verdict["RUN_OUTCOME"] == "RUN_OK"
    assert verdict["ARM_EXECUTION"] == "VALID_ARM_EXECUTION"
    assert verdict["artefact_sha256"]


def test_post_arm_barrier_believes_a_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guard, "capture_arm_environment", lambda label, **kw: _capture(label))
    artefact = tmp_path / "arm.json"
    artefact.write_text(json.dumps({"trajectory": []}))
    verdict = validate_post_arm_environment(
        "POST_ARM_A",
        repo_root=tmp_path,
        frozen_head="0" * 40,
        artefact_path=artefact,
        exit_code=1,
    )
    assert verdict["RUN_OUTCOME"] == "RUN_FAILED"


def test_pre_arm_label_required_for_pre_barrier(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a pre-arm label"):
        validate_pre_arm_environment(
            "POST_ARM_A", repo_root=tmp_path, frozen_head="0" * 40)


def test_post_arm_label_required_for_post_barrier(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a post-arm label"):
        validate_post_arm_environment(
            "PRE_ARM_A", repo_root=tmp_path, frozen_head="0" * 40,
            artefact_path=tmp_path / "x.json", exit_code=0)


def test_arm_b_refused_without_post_arm_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guard, "capture_arm_environment", lambda label, **kw: _capture(label))
    verdict = validate_pre_arm_environment(
        "PRE_ARM_B",
        repo_root=tmp_path,
        frozen_head="0" * 40,
        fresh_preflight=False,
        post_arm_a=None,
        pre_arm_a=_capture("PRE_ARM_A"),
    )
    assert verdict["PRE_ARM_BARRIER"] == "REFUSED"
    assert verdict["ARM_B_EXECUTION"] == "REFUSED"
    assert any("POST_ARM_A is absent" in r for r in verdict["reasons"])


def test_arm_b_refused_when_comparability_is_already_lost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running B into a changed environment spends a run to produce a number
    that cannot be compared with anything."""
    monkeypatch.setattr(
        guard,
        "capture_arm_environment",
        lambda label, **kw: _capture(label, **{"gpu.driver_version": "580.179.01"}),
    )
    verdict = validate_pre_arm_environment(
        "PRE_ARM_B",
        repo_root=tmp_path,
        frozen_head="0" * 40,
        fresh_preflight=False,
        post_arm_a=_capture("POST_ARM_A"),
        pre_arm_a=_capture("PRE_ARM_A"),
    )
    assert verdict["PRE_ARM_BARRIER"] == "REFUSED"
    assert verdict["ARM_B_EXECUTION"] == "REFUSED"
    differing = verdict["arm_b_checks"]["pre_arm_a_vs_pre_arm_b"]
    assert [d["field"] for d in differing] == ["gpu.driver_version"]


def test_arm_b_refused_when_post_arm_a_did_not_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guard, "capture_arm_environment", lambda label, **kw: _capture(label))
    bad_post = _capture("POST_ARM_A")
    bad_post["CAPTURE_VALIDATION"] = "FAIL"
    verdict = validate_pre_arm_environment(
        "PRE_ARM_B",
        repo_root=tmp_path,
        frozen_head="0" * 40,
        fresh_preflight=False,
        post_arm_a=bad_post,
        pre_arm_a=_capture("PRE_ARM_A"),
    )
    assert verdict["PRE_ARM_BARRIER"] == "REFUSED"
    assert any("POST_ARM_A did not validate" in r for r in verdict["reasons"])


def test_pre_arm_barrier_refuses_a_wrong_amendment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guard, "capture_arm_environment", lambda label, **kw: _capture(label))
    verdict = validate_pre_arm_environment(
        "PRE_ARM_A", repo_root=tmp_path, frozen_head="0" * 40, fresh_preflight=False)
    assert verdict["PRE_ARM_BARRIER"] == "REFUSED"
    # Asserted against the authoritative version rather than a hardcoded name,
    # so a future amendment does not silently turn this into a test of nothing.
    assert verdict["contract_version"] == guard.AUTHORITATIVE_CONTRACT_VERSION
    assert any(
        f"{guard.AUTHORITATIVE_CONTRACT_VERSION} amendment sha256" in r
        for r in verdict["reasons"]
    )


def test_pre_arm_barrier_can_be_asked_about_a_superseded_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every amendment stays checkable. Naming a superseded one must answer for
    that one, not quietly answer for the authoritative one."""
    monkeypatch.setattr(
        guard, "capture_arm_environment", lambda label, **kw: _capture(label))
    verdict = validate_pre_arm_environment(
        "PRE_ARM_A", repo_root=tmp_path, frozen_head="0" * 40, fresh_preflight=False,
        contract_version="V2")
    assert verdict["contract_version"] == "V2"
    assert verdict["PRE_ARM_BARRIER"] == "REFUSED"


def test_pre_arm_barrier_refuses_an_unknown_contract_version(tmp_path: Path) -> None:
    verdict = validate_pre_arm_environment(
        "PRE_ARM_A", repo_root=tmp_path, frozen_head="0" * 40, contract_version="V9")
    assert verdict["PRE_ARM_BARRIER"] == "REFUSED"
    assert any("unknown contract version" in r for r in verdict["reasons"])


def test_passing_the_barrier_is_not_execution_authorisation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guard, "capture_arm_environment", lambda label, **kw: _capture(label))
    verdict = validate_pre_arm_environment(
        "PRE_ARM_A", repo_root=tmp_path, frozen_head="0" * 40, fresh_preflight=False)
    assert "not execution authorisation" in verdict["passing_is_necessary_not_sufficient"]
    assert verdict["EXECUTION_STATUS"] == "NOT_RUN"


# --------------------------------------------------------------------------
# evidence location policy
# --------------------------------------------------------------------------


def test_runs_directory_is_ignored_and_source_trees_are_not() -> None:
    def ignored(path: str) -> bool:
        return subprocess.run(
            ["git", "-C", str(REPO), "check-ignore", "-q", path], check=False
        ).returncode == 0

    assert ignored("runs/env_guard/selftest_a.json")
    assert not ignored("gates/BO10/anything.json")
    assert not ignored("src/navfm/anything.py")
    assert not ignored("tests/anything.py")
    assert not ignored("scripts/anything.py")


def test_no_new_broad_ignore_patterns() -> None:
    patterns = {
        line.strip()
        for line in (REPO / ".gitignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    for broad in ("*.json", "runs/**", "gates/**", "*"):
        assert broad not in patterns
