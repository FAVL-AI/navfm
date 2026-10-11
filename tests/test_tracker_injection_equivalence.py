"""Controls for the ARM_A_LEGACY == ARM_A_INJECTED equivalence instrument.

An equivalence proof is only worth the sensitivity of the instrument that
produced it. A comparator that silently compares nothing returns PASS on every
input, and that PASS would be indistinguishable from the real one. So the
controls here are mostly attempts to make it fail: a selector off by one vertex,
a selector that agrees on the target but drifts in state, a command perturbed by
a picometre per second, and inputs malformed enough that the honest answer is a
refusal rather than a verdict.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from navfm.control import M3PRO_LIMITS, DemonstratorMode, PurePursuit
from navfm.target_selection import LegacyVertexTargetSelector, TargetSelection
from navfm.tracker_equivalence import (
    COMMAND_CHANNELS,
    TARGET_CHANNELS,
    compare_sequences,
    equivalence_refused,
    run_command_sequence,
    run_target_sequence,
)

REPO = Path(__file__).resolve().parents[1]
ARTEFACT = REPO / "gates/BO10/tracker_injection_equivalence_20260911.json"

PATH = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [2.0, 1.0], [2.0, 2.0]])
CONFIG: dict[str, Any] = {
    "lookahead": 0.45,
    "goal_tol": 0.20,
    "limits": M3PRO_LIMITS,
    "mode": DemonstratorMode.NONHOLONOMIC,
    "cruise_v": 0.35,
}
POSES = np.array([[x, 0.05, 0.2] for x in np.linspace(0.0, 1.8, 40)])


def _tracker(**kwargs: Any) -> PurePursuit:
    return PurePursuit(PATH.copy(), **CONFIG, **kwargs)


class _OffByOne:
    target_type = "TEST_OFF_BY_ONE"

    def select_target(
        self, path: np.ndarray, position: np.ndarray, index: int, lookahead: float
    ) -> TargetSelection:
        legacy = LegacyVertexTargetSelector().select_target(path, position, index, lookahead)
        idx = min(legacy.next_index + 1, path.shape[0] - 1)
        return TargetSelection(path[idx], idx)


class _StateDrift:
    """Correct point, stale index."""

    target_type = "TEST_STATE_DRIFT"

    def select_target(
        self, path: np.ndarray, position: np.ndarray, index: int, lookahead: float
    ) -> TargetSelection:
        legacy = LegacyVertexTargetSelector().select_target(path, position, index, lookahead)
        return TargetSelection(legacy.point, index)


class _CommandPerturbed(PurePursuit):
    def step(self, position: np.ndarray, yaw: float) -> tuple[float, float, float, bool]:
        vx, vy, wz, done = super().step(position, yaw)
        return vx, vy, wz + 1e-12, done


# --------------------------------------------------------------------------
# positive control
# --------------------------------------------------------------------------


def test_identical_trackers_compare_equal_exactly() -> None:
    left = run_command_sequence(_tracker(), POSES)
    right = run_command_sequence(_tracker(target_selector=LegacyVertexTargetSelector()), POSES)
    result = compare_sequences(
        left, right, left_label="A", right_label="B", channels=COMMAND_CHANNELS)
    assert result["EQUIVALENCE"] == "PASS"
    assert result["mismatch_total"] == 0
    assert result["max_numerical_difference"] == 0.0
    assert result["tolerance_used"] == 0.0
    assert result["steps_compared"] == POSES.shape[0]


def test_default_tolerance_is_exact_equality() -> None:
    assert (
        compare_sequences(
            run_command_sequence(_tracker(), POSES),
            run_command_sequence(_tracker(), POSES),
            left_label="A", right_label="B", channels=COMMAND_CHANNELS,
        )["numerical_standard"]
        == "exact equality"
    )


# --------------------------------------------------------------------------
# negative control: wrong selector
# --------------------------------------------------------------------------


def test_wrong_selector_is_detected_on_target_and_index() -> None:
    result = compare_sequences(
        run_target_sequence(_tracker(), POSES),
        run_target_sequence(_tracker(target_selector=_OffByOne()), POSES),
        left_label="LEGACY", right_label="OFF_BY_ONE", channels=TARGET_CHANNELS,
    )
    assert result["EQUIVALENCE"] == "FAIL"
    by_channel = result["mismatches_by_channel"]
    assert by_channel["target_x"] > 0
    assert by_channel["index_after"] > 0
    assert result["first_mismatches"][0]["kind"] == "VALUE_MISMATCH"


def test_wrong_selector_also_moves_the_command() -> None:
    result = compare_sequences(
        run_command_sequence(_tracker(), POSES),
        run_command_sequence(_tracker(target_selector=_OffByOne()), POSES),
        left_label="LEGACY", right_label="OFF_BY_ONE", channels=COMMAND_CHANNELS,
    )
    assert result["EQUIVALENCE"] == "FAIL"
    assert result["mismatches_by_channel"]["wz"] > 0


# --------------------------------------------------------------------------
# negative control: state drift with a correct target
# --------------------------------------------------------------------------


def test_state_drift_is_caught_even_where_the_target_agrees() -> None:
    """The case a per-step output comparison would miss: the selector returns
    the right point and leaves the index behind."""
    result = compare_sequences(
        run_target_sequence(_tracker(), POSES),
        run_target_sequence(_tracker(target_selector=_StateDrift()), POSES),
        left_label="LEGACY", right_label="STATE_DRIFT", channels=TARGET_CHANNELS,
    )
    assert result["EQUIVALENCE"] == "FAIL"
    by_channel = result["mismatches_by_channel"]
    assert by_channel["index_after"] > 0
    # Some steps agree on the target while the state has already diverged --
    # which is precisely why state is compared at all.
    assert by_channel["index_after"] > by_channel["target_x"]


def test_state_drift_first_mismatch_is_the_index() -> None:
    result = compare_sequences(
        run_target_sequence(_tracker(), POSES),
        run_target_sequence(_tracker(target_selector=_StateDrift()), POSES),
        left_label="LEGACY", right_label="STATE_DRIFT", channels=TARGET_CHANNELS,
    )
    assert result["first_mismatches"][0]["channel"] == "index_after"


# --------------------------------------------------------------------------
# negative control: command drift with an identical target
# --------------------------------------------------------------------------


def test_command_drift_is_detected_though_targets_match() -> None:
    """Proves the proof is not merely comparing selector coordinates."""
    targets = compare_sequences(
        run_target_sequence(_tracker(), POSES),
        run_target_sequence(_CommandPerturbed(PATH.copy(), **CONFIG), POSES),
        left_label="LEGACY", right_label="PERTURBED", channels=TARGET_CHANNELS,
    )
    assert targets["EQUIVALENCE"] == "PASS", "the targets are identical by construction"

    commands = compare_sequences(
        run_command_sequence(_tracker(), POSES),
        run_command_sequence(_CommandPerturbed(PATH.copy(), **CONFIG), POSES),
        left_label="LEGACY", right_label="PERTURBED", channels=COMMAND_CHANNELS,
    )
    assert commands["EQUIVALENCE"] == "FAIL"
    assert commands["mismatches_by_channel"]["wz"] > 0
    assert commands["max_numerical_difference"] > 0.0


def test_a_picometre_of_drift_still_fails_under_exact_equality() -> None:
    commands = compare_sequences(
        run_command_sequence(_tracker(), POSES),
        run_command_sequence(_CommandPerturbed(PATH.copy(), **CONFIG), POSES),
        left_label="LEGACY", right_label="PERTURBED", channels=COMMAND_CHANNELS,
    )
    assert commands["max_numerical_difference"] < 1e-10
    assert commands["EQUIVALENCE"] == "FAIL"


def test_a_stated_tolerance_would_absorb_it() -> None:
    """Shows what a tolerance costs, which is why the default is zero."""
    commands = compare_sequences(
        run_command_sequence(_tracker(), POSES),
        run_command_sequence(_CommandPerturbed(PATH.copy(), **CONFIG), POSES),
        left_label="LEGACY", right_label="PERTURBED", channels=COMMAND_CHANNELS,
        tolerance=1e-9,
    )
    assert commands["EQUIVALENCE"] == "PASS"
    assert commands["tolerance_used"] == 1e-9


# --------------------------------------------------------------------------
# refusal paths: a harness that crashes has not refused
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        [[1.0, 2.0], [3.0, 4.0]],
        [],
        [[1.0, 2.0, float("nan")]],
        [[1.0, 2.0, float("inf")]],
        "not a trace",
        [[1.0, 2.0, 3.0, 4.0]],
    ],
)
def test_malformed_pose_traces_are_refused_not_raised(bad: Any) -> None:
    result = run_command_sequence(_tracker(), bad)
    assert result["EQUIVALENCE"] == "EQUIVALENCE_REFUSED"
    assert result["reason"]


def test_target_pass_refuses_malformed_traces_too() -> None:
    assert run_target_sequence(_tracker(), [[1.0]])["EQUIVALENCE"] == "EQUIVALENCE_REFUSED"


def test_a_tracker_without_step_is_refused() -> None:
    assert run_command_sequence(object(), POSES)["EQUIVALENCE"] == "EQUIVALENCE_REFUSED"


def test_mismatched_lengths_are_refused_not_silently_truncated() -> None:
    result = compare_sequences(
        run_command_sequence(_tracker(), POSES),
        run_command_sequence(_tracker(), POSES[:5]),
        left_label="LONG", right_label="SHORT", channels=COMMAND_CHANNELS,
    )
    assert result["EQUIVALENCE"] == "EQUIVALENCE_REFUSED"
    assert "different lengths" in result["reason"]


def test_an_upstream_refusal_propagates_rather_than_passing() -> None:
    result = compare_sequences(
        equivalence_refused("upstream broke"),
        run_command_sequence(_tracker(), POSES),
        left_label="BROKEN", right_label="OK", channels=COMMAND_CHANNELS,
    )
    assert result["EQUIVALENCE"] == "EQUIVALENCE_REFUSED"


def test_empty_comparison_is_refused_not_passed() -> None:
    """Zero steps compared is not zero mismatches found."""
    empty = {"EQUIVALENCE": "SEQUENCE_RECORDED", "records": []}
    result = compare_sequences(
        empty, empty, left_label="A", right_label="B", channels=COMMAND_CHANNELS)
    assert result["EQUIVALENCE"] == "EQUIVALENCE_REFUSED"


def test_a_missing_channel_is_a_mismatch_not_a_pass() -> None:
    left = {"EQUIVALENCE": "SEQUENCE_RECORDED", "records": [{"vx": 1.0}]}
    right = {"EQUIVALENCE": "SEQUENCE_RECORDED", "records": [{}]}
    result = compare_sequences(
        left, right, left_label="A", right_label="B", channels=("vx",))
    assert result["EQUIVALENCE"] == "FAIL"
    assert result["first_mismatches"][0]["kind"] == "MISSING_CHANNEL"


# --------------------------------------------------------------------------
# the pre-seam reference really is pre-seam
# --------------------------------------------------------------------------


def test_pinned_reference_predates_the_seam() -> None:
    spec = importlib.util.spec_from_file_location(
        "prove_equiv", REPO / "scripts" / "prove_tracker_injection_equivalence.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{module.PRE_SEAM_COMMIT}:{module.CONTROL_REL}"],
        capture_output=True, text=True, check=False,
    )
    assert source.returncode == 0, "the pinned pre-seam commit must be reachable"
    assert "target_selector" not in source.stdout, (
        "the reference must be the tracker BEFORE the seam, or the proof compares "
        "the new implementation with itself")
    assert "_selector" not in source.stdout


# --------------------------------------------------------------------------
# the persisted evidence
# --------------------------------------------------------------------------


def test_evidence_artefact_records_a_pass_and_no_arm() -> None:
    record = json.loads(ARTEFACT.read_text())
    assert record["ARM_A_LEGACY_INJECTION_EQUIVALENCE"] == "PASS"
    assert record["EXECUTION_STATUS"] == "NOT_RUN"
    assert record["arms_executed"] == 0
    assert record["ARM_A_EXECUTION"] == "NOT_STARTED"
    assert record["ARM_B_EXECUTION"] == "NOT_STARTED"


def test_evidence_records_zero_mismatches_and_exact_equality() -> None:
    record = json.loads(ARTEFACT.read_text())
    assert record["numerical_standard"]["tolerance"] == 0.0
    assert record["analytic_fixtures"]["max_numerical_difference"] == 0.0
    assert record["recorded_pose_equivalence"]["max_numerical_difference"] == 0.0
    for trace in record["recorded_pose_equivalence"]["traces"].values():
        assert trace["mismatch_total"] == 0
        assert set(trace["comparisons"].values()) == {"PASS"}


def test_evidence_shows_every_negative_control_fired() -> None:
    record = json.loads(ARTEFACT.read_text())
    fired = record["negative_controls"]["fired"]
    assert all(fired.values()), fired
    assert record["negative_controls"]["state_drift_detected_on_index_after"] is True


def test_evidence_does_not_claim_control_py_is_unchanged_by_hash() -> None:
    """The seam is an edit to control.py. Claiming otherwise would be false."""
    invariance = json.loads(ARTEFACT.read_text())["control_law_invariance"]
    assert invariance["control_py_file_hash_changed"] is True
    assert invariance["CONTROL_LAW_INVARIANCE"] == "PASS"
    assert all(m["identical"] for m in invariance["members"].values())


def test_evidence_uses_run_00001_as_an_offline_trace_only() -> None:
    source = json.loads(ARTEFACT.read_text())["run_00001_source"]
    assert source["used_as"] == "OFFLINE_POSE_TRACE_ONLY"
    assert source["dynamics_replayed"] is False
    assert source["modified"] is False


def test_evidence_records_the_outstanding_manifest_dependency() -> None:
    record = json.loads(ARTEFACT.read_text())
    assert record["EXECUTION_MANIFEST_OWES_ARM_OUTPUT_ALLOWLIST"] is True


def test_evidence_states_its_claim_boundary() -> None:
    boundary = json.loads(ARTEFACT.read_text())["claim_boundary"]
    assert "does not establish anything about the treatment selector" in boundary
    assert "no arm has run" in boundary
