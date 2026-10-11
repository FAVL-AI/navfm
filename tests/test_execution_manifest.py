"""Controls for the frozen execution manifest.

A manifest is only as good as what it refuses. These controls mutate one field
at a time and require the validator to name that field: an operator told only
that the manifest is "invalid" has been told to look everywhere.

Two properties get particular attention. The allow-list must stay an
enumeration -- a glob would make the worktree check unable to tell an expected
trajectory from an edited controller, which is the single distinction it exists
to draw. And the manifest must carry no outcome field, because a manifest that
could hold a result is a manifest that could have been written after one.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from navfm.execution_manifest import (
    ARM_ORDER,
    MANIFEST_VERSION,
    REQUIRED_MANIFEST_KEYS,
    TRACKED_OUTPUTS,
    UNTRACKED_OUTPUTS,
    build_manifest,
    canonical_manifest,
    canonical_worktree_state,
    freeze_manifest,
    manifest_digest,
    validate_manifest,
)

REPO = Path(__file__).resolve().parents[1]


def _head() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def manifest() -> dict[str, Any]:
    return build_manifest(REPO, head=_head(), frozen_at_utc="2026-09-12T00:00:00+00:00")


def _fields(result: dict[str, Any]) -> list[str]:
    return [f["field"] for f in result["failures"]]


# --------------------------------------------------------------------------
# a well-formed manifest
# --------------------------------------------------------------------------


def test_a_freshly_built_manifest_validates(manifest: dict[str, Any]) -> None:
    result = validate_manifest(manifest, REPO, expected_head=_head())
    assert result["MANIFEST_VALID"] == "PASS", result["failures"]


def test_every_required_key_is_present(manifest: dict[str, Any]) -> None:
    for key in REQUIRED_MANIFEST_KEYS:
        assert key in manifest


def test_arm_order_is_control_then_treatment(manifest: dict[str, Any]) -> None:
    assert manifest["arms"]["order"] == list(ARM_ORDER) == [
        "ARM_A_CONTROL", "ARM_B_TREATMENT"]
    assert "preregistered" in manifest["arms"]["order_rule"]
    assert "not reordered after" in manifest["arms"]["order_rule"]


def test_selectors_are_assigned_to_the_right_arms(manifest: dict[str, Any]) -> None:
    selectors = manifest["arms"]["selectors"]
    assert selectors["ARM_A_CONTROL"]["target_type"] == "PATH_VERTEX"
    assert selectors["ARM_B_TREATMENT"]["target_type"] == "ARC_LENGTH_INTERPOLATED"
    assert "Legacy" in selectors["ARM_A_CONTROL"]["selector_class"]
    assert "ArcLength" in selectors["ARM_B_TREATMENT"]["selector_class"]


def test_no_outcome_value_appears(manifest: dict[str, Any]) -> None:
    assert manifest["EXECUTION_STATUS"] == "NOT_RUN"
    assert manifest["arms_executed"] == 0
    assert manifest["outcomes"]["no_outcome_values_in_this_manifest"] is True
    blob = json.dumps(manifest).lower()
    for forbidden in ('"success_rate"', '"spl"', '"goal_reached"'):
        assert forbidden not in blob


def test_terminal_window_is_route_defined_not_step_defined(manifest: dict[str, Any]) -> None:
    rule = manifest["outcomes"]["terminal_window_rule"]
    assert "arc-length window" in rule
    assert "never over a fixed step range" in rule


def test_claim_limit_is_instance_level(manifest: dict[str, Any]) -> None:
    limit = manifest["claim_limit"]
    assert "instance-level causal claim" in limit["a_positive_result_permits"]
    joined = " ".join(limit["it_does_not_establish"])
    assert "population success-rate" in joined
    assert "sim-to-real" in joined
    assert limit["sample_count_per_arm"] == 1


def test_scene_boundary_and_holds_are_bound(manifest: dict[str, Any]) -> None:
    assert manifest["episode"]["scene_byte_identity"] == "NOT_VERIFIED_REMOTE_STREAMED_ASSET"
    environment = manifest["environment_policy"]
    assert environment["expected_nvidia_driver"] == "580.178.04"
    assert environment["expected_held_package_count"] == 22
    assert environment["no_reboot_between_pre_arm_a_and_post_arm_b"] is True
    assert environment["preflight_exception"]["not_broadened_here"] is True


def test_retry_policy_forbids_result_shopping(manifest: dict[str, Any]) -> None:
    forbidden = " ".join(manifest["retry_policy"]["forbidden"])
    assert "looks strange" in forbidden
    assert "only the worse arm" in forbidden
    assert "better duplicate" in forbidden


def test_arm_a_failure_stops_the_experiment(manifest: dict[str, Any]) -> None:
    assert "do NOT proceed to Arm B" in manifest["failure_policy"][
        "arm_a_produces_no_valid_artefact"]


# --------------------------------------------------------------------------
# negative controls: one mutation, one named field
# --------------------------------------------------------------------------


def _mutate(manifest: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    out = copy.deepcopy(manifest)
    node: Any = out
    parts = path.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value
    return out


@pytest.mark.parametrize(
    ("path", "value", "expected_field"),
    [
        ("repository.head", "0" * 40, "repository.head"),
        ("authoritative_contract.sha256", "0" * 64, "authoritative_contract.sha256"),
        ("authoritative_contract.version", "V3", "authoritative_contract.version"),
        ("arms.order", ["ARM_B_TREATMENT", "ARM_A_CONTROL"], "arms.order"),
        ("arms.behavioural_overrides", ["target", "step"], "arms.behavioural_overrides"),
        ("route.source_artefact.sha256", "0" * 64, "route.source_artefact.sha256"),
        ("episode.seed", 7, "episode.seed"),
        ("runtime_configuration.max_steps", 1800, "runtime_configuration.max_steps"),
        ("runtime_configuration.goal_tol_m", 0.5, "runtime_configuration.goal_tol_m"),
        ("runtime_configuration.lookahead_m", 0.9, "runtime_configuration.lookahead_m"),
        ("runtime_configuration.control_dt", 0.05, "runtime_configuration.control_dt"),
        ("environment_policy.expected_held_package_count", 21,
         "environment_policy.expected_held_package_count"),
        ("environment_policy.expected_nvidia_driver", "580.173.02",
         "environment_policy.expected_nvidia_driver"),
        ("episode.scene_byte_identity", "VERIFIED", "episode.scene_byte_identity"),
        ("manifest_version", "EXECUTION_MANIFEST_V9", "manifest_version"),
        ("EXECUTION_STATUS", "RUN", "EXECUTION_STATUS"),
    ],
)
def test_a_mutated_field_is_named(
    manifest: dict[str, Any], path: str, value: Any, expected_field: str
) -> None:
    result = validate_manifest(_mutate(manifest, path, value), REPO, expected_head=_head())
    assert result["MANIFEST_VALID"] == "FAIL"
    assert expected_field in _fields(result)


def test_swapped_selectors_are_detected(manifest: dict[str, Any]) -> None:
    swapped = copy.deepcopy(manifest)
    a = swapped["arms"]["selectors"]["ARM_A_CONTROL"]
    b = swapped["arms"]["selectors"]["ARM_B_TREATMENT"]
    swapped["arms"]["selectors"]["ARM_A_CONTROL"] = b
    swapped["arms"]["selectors"]["ARM_B_TREATMENT"] = a
    result = validate_manifest(swapped, REPO, expected_head=_head())
    assert result["MANIFEST_VALID"] == "FAIL"
    assert "arms.selectors.ARM_A_CONTROL.selector_class" in _fields(result)
    assert "arms.selectors.ARM_B_TREATMENT.selector_class" in _fields(result)


@pytest.mark.parametrize("pattern", ["runs/**", "gates/**", "*.json", "*.csv", "runs/*"])
def test_a_broad_output_pattern_is_refused(manifest: dict[str, Any], pattern: str) -> None:
    result = validate_manifest(
        _mutate(manifest, "output_allowlist.tracked", [*TRACKED_OUTPUTS, pattern]),
        REPO, expected_head=_head())
    assert result["MANIFEST_VALID"] == "FAIL"
    assert "output_allowlist.tracked" in _fields(result)


def test_a_missing_output_declaration_is_refused(manifest: dict[str, Any]) -> None:
    result = validate_manifest(
        _mutate(manifest, "output_allowlist.tracked", list(TRACKED_OUTPUTS)[:-1]),
        REPO, expected_head=_head())
    assert result["MANIFEST_VALID"] == "FAIL"
    assert "output_allowlist.tracked" in _fields(result)


def test_an_empty_allowlist_is_refused(manifest: dict[str, Any]) -> None:
    result = validate_manifest(
        _mutate(manifest, "output_allowlist.untracked_runtime", []),
        REPO, expected_head=_head())
    assert result["MANIFEST_VALID"] == "FAIL"


def test_a_malformed_manifest_is_refused() -> None:
    assert validate_manifest({}, REPO)["MANIFEST_VALID"] == "FAIL"
    assert validate_manifest(
        {"manifest_version": MANIFEST_VERSION}, REPO)["MANIFEST_VALID"] == "FAIL"


def test_a_missing_required_key_names_that_key(manifest: dict[str, Any]) -> None:
    without = {k: v for k, v in manifest.items() if k != "retry_policy"}
    result = validate_manifest(without, REPO)
    assert result["MANIFEST_VALID"] == "FAIL"
    assert "retry_policy" in _fields(result)


def test_a_weakened_retry_policy_is_refused(manifest: dict[str, Any]) -> None:
    result = validate_manifest(
        _mutate(manifest, "retry_policy.forbidden", []), REPO, expected_head=_head())
    assert "retry_policy.forbidden" in _fields(result)


def test_a_weakened_arm_a_failure_rule_is_refused(manifest: dict[str, Any]) -> None:
    result = validate_manifest(
        _mutate(manifest, "failure_policy.arm_a_produces_no_valid_artefact",
                "carry on to Arm B"),
        REPO, expected_head=_head())
    assert "failure_policy.arm_a_produces_no_valid_artefact" in _fields(result)


# --------------------------------------------------------------------------
# worktree canonicalisation
# --------------------------------------------------------------------------


def test_a_clean_tree_passes(tmp_path: Path) -> None:
    """On a controlled repository, not the live one: asserting that the working
    tree is clean would make this test fail during any development, which says
    nothing about whether the mechanism works."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    result = canonical_worktree_state(tmp_path)
    assert result["WORKTREE_POLICY"] == "PASS"
    assert result["canonical_state"] == "clean"


def test_declared_outputs_are_not_source_drift(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "gates" / "BO10" / "intervention").mkdir(parents=True)
    (tmp_path / "gates/BO10/intervention/arm_a_result.json").write_text("{}")
    assert canonical_worktree_state(tmp_path)["WORKTREE_POLICY"] == "FAIL"
    permitted = canonical_worktree_state(tmp_path, allow_outputs=TRACKED_OUTPUTS)
    assert permitted["WORKTREE_POLICY"] == "PASS"


def test_unexpected_drift_is_not_hidden_as_output(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "gates" / "BO10" / "intervention").mkdir(parents=True)
    (tmp_path / "gates/BO10/intervention/arm_a_result.json").write_text("{}")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "control.py").write_text("x = 1\n")
    result = canonical_worktree_state(tmp_path, allow_outputs=TRACKED_OUTPUTS)
    assert result["WORKTREE_POLICY"] == "FAIL"
    assert result["unexpected"] == ["src/control.py"]


def test_the_preflight_exception_is_opt_in(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "gates" / "BO10").mkdir(parents=True)
    (tmp_path / "gates/BO10/intervention_execution_preflight_20260911.json").write_text("{}")
    assert canonical_worktree_state(tmp_path)["WORKTREE_POLICY"] == "FAIL"
    assert canonical_worktree_state(
        tmp_path, allow_preflight=True)["WORKTREE_POLICY"] == "PASS"


# --------------------------------------------------------------------------
# freeze-once semantics
# --------------------------------------------------------------------------


def test_a_timestamp_does_not_move_the_identity(manifest: dict[str, Any]) -> None:
    later = build_manifest(REPO, head=_head(), frozen_at_utc="2099-01-01T00:00:00+00:00")
    assert manifest_digest(later) == manifest_digest(manifest)
    assert "frozen_at_utc" not in canonical_manifest(manifest)


def test_freeze_then_refreeze_is_identical(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    first = freeze_manifest(target, REPO, head=_head(), frozen_at_utc="2026-09-12T00:00:00+00:00")
    assert first["EXECUTION_MANIFEST"] == "FROZEN"
    assert first["first_freeze"] is True
    second = freeze_manifest(
        target, REPO, head=_head(), frozen_at_utc="2099-01-01T00:00:00+00:00")
    assert second["EXECUTION_MANIFEST"] == "FROZEN"
    assert second["first_freeze"] is False
    assert second["sha256"] == first["sha256"]
    assert json.loads(target.read_text())["frozen_at_utc"] == "2026-09-12T00:00:00+00:00"


def test_a_changed_payload_refuses_silent_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    freeze_manifest(target, REPO, head=_head(), frozen_at_utc="2026-09-12T00:00:00+00:00")
    before = target.read_bytes()
    outcome = freeze_manifest(
        target, REPO, head="0" * 40, frozen_at_utc="2026-09-12T00:00:00+00:00")
    assert outcome["EXECUTION_MANIFEST"] == "REFUSED"
    assert "will not be silently overwritten" in outcome["reason"]
    assert target.read_bytes() == before


def test_freeze_refuses_a_manifest_that_does_not_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "manifest.json"
    outcome = freeze_manifest(
        target, REPO, head="0" * 40, frozen_at_utc="2026-09-12T00:00:00+00:00")
    assert outcome["EXECUTION_MANIFEST"] == "REFUSED"
    assert outcome["validation"]["MANIFEST_VALID"] == "FAIL"
    assert "repository.head" in _fields(outcome["validation"])


def test_allowlist_entries_are_exact_paths() -> None:
    for entry in (*TRACKED_OUTPUTS, *UNTRACKED_OUTPUTS):
        assert "*" not in entry
        assert "?" not in entry
    assert len(set(TRACKED_OUTPUTS)) == len(TRACKED_OUTPUTS)
    assert len(set(UNTRACKED_OUTPUTS)) == len(UNTRACKED_OUTPUTS)


def test_every_arm_stage_has_a_declared_output() -> None:
    joined = " ".join((*TRACKED_OUTPUTS, *UNTRACKED_OUTPUTS))
    for stage in ("pre_arm_a", "post_arm_a", "pre_arm_b", "post_arm_b",
                  "arm_a_result", "arm_b_result", "arm_a_terminal_trace",
                  "arm_b_terminal_trace", "environment_equivalence", "comparison",
                  "arm_a_status", "arm_b_status"):
        assert stage in joined
    assert "execution_manifest.json" in joined
