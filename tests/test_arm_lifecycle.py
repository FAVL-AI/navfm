"""Controls for the arm execution body and its lifecycle.

EXECUTION_MANIFEST_V2 established that every declared output had an importable
callable behind it, and that was true. It was also not enough: each producer's
only reference in the tree was its own ``def`` line, so an authorised runner
resolved every component and still invoked none of them. Resolution is not
reachability, and reachability is not invocation.

These controls therefore never assert that a producer exists. They assert that
walking the one orchestration table invokes it, at the declared stage, the
declared number of times -- and, more importantly, that the lifecycle refuses
when it does not. Every positive gate here has a negative control, because a
readiness instrument that cannot fail has not been shown to measure anything.

The failures are matched on ``kind``, never on message text. ``kind`` is the
contract an operator acts on; the wording is free to improve without a test
pinning it in place.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from navfm import arm_lifecycle
from navfm.arm_lifecycle import (
    ARM_PLAN,
    LIFECYCLE_STAGES,
    PRODUCER_BINDINGS,
    ProducerBinding,
    RehearsalRuntimeAdapter,
    Stage,
    entrypoint_reachability,
    execute_arm,
)
from navfm.execution_manifest_v2 import build_manifest_v2

REPO = Path(__file__).resolve().parents[1]
ARMS = ("ARM_A_CONTROL", "ARM_B_TREATMENT")


def _head() -> str:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    """A manifest for the tree as it stands, so controls are about today.

    The head is read rather than pinned: a fixture pinning a literal would stop
    being about this tree the moment the tree moved, which is the failure these
    controls exist to catch elsewhere.
    """
    target = tmp_path / "manifest.json"
    target.write_text(json.dumps(build_manifest_v2(
        REPO, head=_head(), frozen_at_utc="1970-01-01T00:00:00+00:00",
        manifest_path=str(target)), indent=2))
    return target


def rehearse(manifest: Path, arm: str, tmp: Path, **kw: Any) -> Any:
    runtime = RehearsalRuntimeAdapter(fail_at=kw.pop("fail_at", None))
    return execute_arm(manifest, arm, REPO, runtime=runtime, mode="REHEARSAL",
                       output_root=tmp / f"rh_{arm}_{kw.pop('tag', 'base')}", **kw)


def kinds(outcome: Any) -> set[str]:
    return {p["kind"] for p in outcome.lifecycle.get("problems", [])}


# --- structural reachability -------------------------------------------------

def test_every_required_producer_is_bound_into_the_plan() -> None:
    """Necessary, and explicitly not sufficient -- rehearsal decides that."""
    report = entrypoint_reachability()
    assert report["ENTRYPOINT_REACHABILITY"] == "PASS"
    assert report["required_outputs_not_bound"] == []
    assert report["stage_binding_mismatches"] == []
    assert report["plan_is_stage_monotone"] is True


def test_plan_never_moves_backwards_through_the_stages() -> None:
    order = [LIFECYCLE_STAGES.index(step.stage) for step in ARM_PLAN]
    assert order == sorted(order)


def test_a_binding_absent_from_the_plan_fails_reachability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defined, importable, correctly named -- and never called. Must fail."""
    probe = ProducerBinding(
        "never_called_probe", True, Stage.SCIENTIFIC_EVIDENCE_WRITTEN,
        "navfm.intervention_runner:write_status", True, 1, "test-only probe")
    monkeypatch.setattr(arm_lifecycle, "PRODUCER_BINDINGS", (*PRODUCER_BINDINGS, probe))
    report = entrypoint_reachability()
    assert report["ENTRYPOINT_REACHABILITY"] == "FAIL"
    assert "never_called_probe" in report["required_outputs_not_bound"]


# --- rehearsal walks the real orchestration ----------------------------------

@pytest.mark.parametrize("arm", ARMS)
def test_rehearsal_completes_the_whole_lifecycle(manifest: Path, tmp_path: Path,
                                                 arm: str) -> None:
    outcome = rehearse(manifest, arm, tmp_path)
    assert outcome.status == "VALID", outcome.lifecycle
    assert outcome.lifecycle["LIFECYCLE"] == "PASS"

    entered = outcome.lifecycle["stages_entered"]
    # Every stage is reached, and the walk never goes backwards. A stage may
    # repeat -- three producers share SCIENTIFIC_EVIDENCE_WRITTEN -- so the
    # property is coverage plus monotonicity, not a literal sequence.
    assert set(entered) == {s.value for s in LIFECYCLE_STAGES}
    index = {s.value: i for i, s in enumerate(LIFECYCLE_STAGES)}
    positions = [index[stage] for stage in entered]
    assert positions == sorted(positions)


@pytest.mark.parametrize("arm", ARMS)
def test_rehearsal_never_touches_a_production_label_or_path(
    manifest: Path, tmp_path: Path, arm: str,
) -> None:
    """The one thing a rehearsal must not be able to do is look like an arm."""
    outcome = rehearse(manifest, arm, tmp_path)
    blob = json.dumps(outcome.as_dict())
    for production in ("PRE_ARM_A", "POST_ARM_A", "PRE_ARM_B", "POST_ARM_B"):
        assert production not in blob
    assert "SELFTEST" in blob


def test_the_arms_differ_only_in_the_treatment_factor(manifest: Path,
                                                      tmp_path: Path) -> None:
    """One factor, or the comparison is not about the intervention."""
    a = rehearse(manifest, "ARM_A_CONTROL", tmp_path).outputs["collect_config"]
    b = rehearse(manifest, "ARM_B_TREATMENT", tmp_path).outputs["collect_config"]
    differing = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    assert differing == {"target_selector"}, differing
    assert a["target_selector"] != b["target_selector"]


# --- negative controls -------------------------------------------------------

def test_removing_a_producer_from_the_plan_is_detected(manifest: Path,
                                                       tmp_path: Path) -> None:
    """The exact defect Manifest V2 could not see."""
    pruned = tuple(s for s in ARM_PLAN if s.action != "_write_result")
    outcome = rehearse(manifest, "ARM_A_CONTROL", tmp_path, plan=pruned, tag="missing")
    assert outcome.status != "VALID"
    assert "PRODUCER_UNREACHABLE_FROM_ENTRYPOINT" in kinds(outcome)


def test_calling_an_exactly_once_producer_twice_is_detected(manifest: Path,
                                                            tmp_path: Path) -> None:
    doubled = (*ARM_PLAN, next(s for s in ARM_PLAN if s.action == "_write_result"))
    outcome = rehearse(manifest, "ARM_A_CONTROL", tmp_path, plan=doubled, tag="dup")
    assert outcome.status != "VALID"
    assert "PRODUCER_MULTIPLICITY_VIOLATION" in kinds(outcome)


def test_invoking_a_producer_out_of_order_is_detected(manifest: Path,
                                                      tmp_path: Path) -> None:
    post = next(s for s in ARM_PLAN if s.action == "_capture_post")
    early = (post, *(s for s in ARM_PLAN if s.action != "_capture_post"))
    outcome = rehearse(manifest, "ARM_A_CONTROL", tmp_path, plan=early, tag="order")
    assert outcome.status != "VALID"
    assert "STAGE_OUT_OF_ORDER" in kinds(outcome)


def test_an_early_return_is_incomplete_not_pass(manifest: Path,
                                                tmp_path: Path) -> None:
    """Components resolved, episode never ran. Must not read as ready."""
    truncated = ARM_PLAN[:4]
    outcome = rehearse(manifest, "ARM_A_CONTROL", tmp_path, plan=truncated, tag="early")
    assert outcome.status != "VALID"
    assert "LIFECYCLE_INCOMPLETE" in kinds(outcome)


def test_an_unknown_mode_is_refused_structurally(manifest: Path,
                                                 tmp_path: Path) -> None:
    outcome = execute_arm(manifest, "ARM_A_CONTROL", REPO,
                          runtime=RehearsalRuntimeAdapter(), mode="PRODUCTION?",
                          output_root=tmp_path / "unknown")
    assert outcome.status == "REFUSED"
    assert outcome.refusal is not None


def test_an_adapter_failure_produces_a_verdict_not_a_traceback(
    manifest: Path, tmp_path: Path,
) -> None:
    """Defects cluster in negative-space code, so the refusal path is a test target."""
    outcome = rehearse(manifest, "ARM_A_CONTROL", tmp_path,
                       fail_at="run_episode", tag="fail")
    assert outcome.status == "REFUSED"
    assert outcome.refusal is not None and outcome.refusal.get("stage")


def test_an_unreadable_manifest_is_refused_at_the_first_stage(tmp_path: Path) -> None:
    bad = tmp_path / "not.json"
    bad.write_text("{ this is not json")
    outcome = execute_arm(bad, "ARM_A_CONTROL", REPO,
                          runtime=RehearsalRuntimeAdapter(), mode="REHEARSAL",
                          output_root=tmp_path / "bad")
    assert outcome.status == "REFUSED"
    assert outcome.refusal is not None
    assert outcome.refusal["stage"] == Stage.MANIFEST_VALIDATED.value


# --- the manifest's readiness must be about the manifest ---------------------
#
# The first version of the V3 freeze measured readiness by rehearsing an
# internally built V2 stand-in, then recorded the result onto a V3 document the
# lifecycle went on to refuse. A readiness fact measured against a different
# document is a fact about that document.


def test_v3_readiness_is_measured_against_the_manifest_it_describes(
    tmp_path: Path,
) -> None:
    """Rehearsing the frozen manifest must agree with what it claims."""
    from navfm.execution_manifest_v2 import build_manifest_v3

    built = build_manifest_v3(
        REPO, head=_head(), frozen_at_utc="1970-01-01T00:00:00+00:00",
        manifest_path="runs/bo10/intervention/execution_manifest_v3.json")
    target = tmp_path / "frozen.json"
    target.write_text(json.dumps(built, indent=2))

    claimed = built["executability"]
    for arm, key in (("ARM_A_CONTROL", "arm_a_rehearsal"),
                     ("ARM_B_TREATMENT", "arm_b_rehearsal")):
        observed = rehearse(target, arm, tmp_path, tag="claimcheck")
        assert claimed[key] is (observed.status == "VALID"), (
            f"{key}={claimed[key]} but rehearsing the manifest gives "
            f"{observed.status}")
        assert observed.status == "VALID", observed.refusal


def test_the_lifecycle_refuses_a_manifest_version_it_has_no_validator_for(
    manifest: Path, tmp_path: Path,
) -> None:
    """Negative control. Falling through to an older validator is the defect."""
    doc = json.loads(manifest.read_text())
    doc["manifest_version"] = "EXECUTION_MANIFEST_V9"
    future = tmp_path / "future.json"
    future.write_text(json.dumps(doc))
    outcome = rehearse(future, "ARM_A_CONTROL", tmp_path, tag="future")
    assert outcome.status == "REFUSED"
    assert outcome.refusal is not None
    assert "EXECUTION_MANIFEST_V9" in outcome.refusal["reason"]
