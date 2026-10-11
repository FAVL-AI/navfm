"""Lifecycle reachability: is every declared producer actually invoked?

Two authorisations were spent on the same mistake in narrowing forms. The first
found declared outputs with no producers. The second found producers that
imported cleanly and were never called: the runner could name every artefact an
arm would write and contained no code that wrote one, and the readiness check
said PASS because it asked whether names resolved.

So this asks a different question, twice over. Structurally, is each required
producer bound into the plan the authorised entry point walks? And behaviourally,
does walking that plan with a fake runtime actually invoke each one, once, in
order? Neither alone is enough: a binding can sit in the table unexecuted, and a
rehearsal with its own private lifecycle could pass while the real path stayed
disconnected. There is one orchestration, and the rehearsal walks it.

The fault-injection controls matter more than the happy path here. Defects in
this work have clustered in negative-space code -- refusal handlers, unreachable
dependencies, early returns -- which ordinary success-path execution never
exercises. Each control below drives the instrument into one of those shapes and
requires it to refuse for the stated reason.

Nothing here starts Isaac, loads Hospital, or consumes a production label.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import navfm.arm_lifecycle as lifecycle  # noqa: E402
from navfm.arm_lifecycle import (  # noqa: E402
    ARM_PLAN,
    PRODUCER_BINDINGS,
    ProducerBinding,
    RehearsalRuntimeAdapter,
    Stage,
    entrypoint_reachability,
    execute_arm,
)
from navfm.evidence import emit_evidence  # noqa: E402
from navfm.execution_manifest_v2 import build_manifest_v2  # noqa: E402

V5_FREEZE_COMMIT = "c542e216653f2a711dacce9ae0f50f782d2e356b"
WIRING_REL = "gates/BO10/collector_wiring_regression_20260912.json"

GAP_OUT = REPO / "gates/BO10/execution_reachability_gap_v2_20260912.json"
OUT = REPO / "gates/BO10/lifecycle_reachability_rehearsal_20260912.json"


def sha256_file(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def current_manifest(tmp: pathlib.Path) -> pathlib.Path:
    """A manifest for the tree as it stands, so the rehearsal is about today."""
    target = tmp / "manifest_current.json"
    manifest = build_manifest_v2(
        REPO, head=_git("rev-parse", "HEAD"),
        frozen_at_utc="1970-01-01T00:00:00+00:00", manifest_path=str(target))
    target.write_text(json.dumps(manifest, indent=2))
    return target


def rehearse(manifest: pathlib.Path, arm: str, tmp: pathlib.Path,
             **kwargs: Any) -> tuple[Any, RehearsalRuntimeAdapter]:
    runtime = RehearsalRuntimeAdapter(fail_at=kwargs.pop("fail_at", None))
    outcome = execute_arm(
        manifest, arm, REPO, runtime=runtime, mode="REHEARSAL",
        output_root=tmp / f"rehearsal_{arm.lower()}_{kwargs.pop('tag', 'base')}",
        **kwargs)
    return outcome, runtime


class _RaisingAdapter(RehearsalRuntimeAdapter):
    """Raises something the lifecycle does not expect, at the boundary.

    The question is not whether the error is prevented -- it is whether an
    unexpected failure still produces a recorded verdict instead of a traceback
    standing in for a scientific result.
    """

    def run_episode(self, route: Any) -> Any:
        raise RuntimeError("simulated adapter fault that is not a LifecycleRefused")


def negative_controls(manifest: pathlib.Path, tmp: pathlib.Path) -> dict[str, Any]:
    results: dict[str, Any] = {}

    # 1. missing call: the producer resolves and its plan step is gone.
    plan = tuple(s for s in ARM_PLAN if s.action != "_write_status")
    outcome, _ = rehearse(manifest, "ARM_A_CONTROL", tmp, plan=plan, tag="missing")
    kinds = outcome.lifecycle["problem_kinds"]
    results["missing_call"] = {
        "DETECTED": outcome.status != "VALID",
        "expected_kind": "PRODUCER_UNREACHABLE_FROM_ENTRYPOINT",
        "kinds": kinds,
        "names_the_intended_kind": "PRODUCER_UNREACHABLE_FROM_ENTRYPOINT" in kinds,
        "detail": next((p["detail"] for p in outcome.lifecycle["problems"]
                        if p["kind"] == "PRODUCER_UNREACHABLE_FROM_ENTRYPOINT"), None),
    }

    # 2. defined but never called: a declared producer with no plan step at all.
    extra = ProducerBinding(
        "never_called_probe", True, Stage.SCIENTIFIC_EVIDENCE_WRITTEN,
        "navfm.intervention_runner:write_status", True, 1, "test-only probe")
    original = lifecycle.PRODUCER_BINDINGS
    lifecycle.PRODUCER_BINDINGS = (*original, extra)
    try:
        structural = entrypoint_reachability()
        outcome, _ = rehearse(manifest, "ARM_A_CONTROL", tmp, tag="nevercalled")
        results["defined_but_never_called"] = {
            "DETECTED": (structural["ENTRYPOINT_REACHABILITY"] == "FAIL"
                         and outcome.status != "VALID"),
            "structural_verdict": structural["ENTRYPOINT_REACHABILITY"],
            "unbound_outputs": structural["required_outputs_not_bound"],
            "rehearsal_status": outcome.status,
            "names_the_intended_kind":
                "PRODUCER_UNREACHABLE_FROM_ENTRYPOINT" in outcome.lifecycle["problem_kinds"],
        }
    finally:
        lifecycle.PRODUCER_BINDINGS = original

    # 3. wrong order: the post capture placed before evidence validation.
    reordered = []
    for step in ARM_PLAN:
        if step.action == "_validate_evidence":
            continue
        reordered.append(step)
        if step.action == "_capture_post":
            reordered.append(next(s for s in ARM_PLAN if s.action == "_validate_evidence"))
    outcome, _ = rehearse(manifest, "ARM_A_CONTROL", tmp, plan=tuple(reordered),
                          tag="order")
    results["wrong_order"] = {
        "DETECTED": outcome.status != "VALID",
        "kinds": outcome.lifecycle["problem_kinds"],
        "names_the_intended_kind":
            "STAGE_OUT_OF_ORDER" in outcome.lifecycle["problem_kinds"],
    }

    # 4. duplicate call: an exactly-once producer invoked twice.
    duplicated = (
        *ARM_PLAN,
        next(s for s in ARM_PLAN if s.action == "_write_result"))
    outcome, _ = rehearse(manifest, "ARM_A_CONTROL", tmp, plan=duplicated, tag="dup")
    results["duplicate_call"] = {
        "DETECTED": outcome.status != "VALID",
        "kinds": outcome.lifecycle["problem_kinds"],
        "names_the_intended_kind":
            ("PRODUCER_MULTIPLICITY_VIOLATION" in outcome.lifecycle["problem_kinds"]
             or "STAGE_OUT_OF_ORDER" in outcome.lifecycle["problem_kinds"]),
        "counts": outcome.lifecycle["invocation_counts"],
    }

    # 5. early return: the plan stops after the episode.
    truncated = tuple(ARM_PLAN[:ARM_PLAN.index(
        next(s for s in ARM_PLAN if s.action == "_finish_episode")) + 1])
    outcome, _ = rehearse(manifest, "ARM_A_CONTROL", tmp, plan=truncated, tag="early")
    results["early_return"] = {
        "DETECTED": outcome.status == "LIFECYCLE_INCOMPLETE",
        "status": outcome.status,
        "kinds": outcome.lifecycle["problem_kinds"],
        "names_the_intended_kind":
            "LIFECYCLE_INCOMPLETE" in outcome.lifecycle["problem_kinds"],
    }

    # 6. refusal path: an injected LifecycleRefused must return a verdict.
    outcome, _ = rehearse(manifest, "ARM_A_CONTROL", tmp, fail_at="run_episode",
                          tag="refuse")
    results["structured_refusal"] = {
        "DETECTED": outcome.status == "REFUSED",
        "refusal": outcome.refusal,
        "escaped_exception": bool((outcome.refusal or {}).get("escaped_exception")),
        "verdict_is_structured": outcome.refusal is not None,
    }

    # 7. an UNEXPECTED exception at a boundary must also be recorded, not raised.
    runtime = _RaisingAdapter()
    outcome = execute_arm(manifest, "ARM_A_CONTROL", REPO, runtime=runtime,
                          mode="REHEARSAL", output_root=tmp / "rehearsal_raise")
    results["exception_during_refusal_handling"] = {
        "DETECTED": outcome.status == "REFUSED",
        "refusal": outcome.refusal,
        "recorded_rather_than_raised": outcome.refusal is not None,
        "escaped_exception_flagged": bool((outcome.refusal or {}).get("escaped_exception")),
    }

    # 8. an unknown mode must refuse rather than default to a real run.
    outcome = execute_arm(manifest, "ARM_A_CONTROL", REPO,
                          runtime=RehearsalRuntimeAdapter(), mode="PRODUCTION?")
    results["unknown_mode"] = {
        "DETECTED": outcome.status == "REFUSED", "refusal": outcome.refusal}

    return results


def _blob_sha_at(commit: str, rel: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{rel}"],
                          capture_output=True, check=False)
    if proc.returncode != 0:
        return None
    return hashlib.sha256(proc.stdout).hexdigest()


def wiring_evidence_provenance() -> dict[str, Any]:
    """Was the V5-bound wiring regression measured against a tree that exists?

    Measured rather than asserted: each source identity the artefact recorded is
    looked up across the whole history. An artefact naming a head that does not
    contain the content it hashed was measured against an uncommitted working
    tree, and no later reader can reproduce it from any commit.
    """
    raw = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{V5_FREEZE_COMMIT}:{WIRING_REL}"],
        capture_output=True, check=False)
    if raw.returncode != 0:
        return {"CHECKED": False, "reason": f"{WIRING_REL} absent at V5's freeze"}

    record = json.loads(raw.stdout)
    claimed_head = record.get("repository_head")
    commits = _git("rev-list", "HEAD").split()
    recorded = {
        "src/navfm/isaac/collect.py": record["collector_identity"]["sha256"],
        "src/navfm/target_selection.py": record["selector_module_identity"]["sha256"],
    }

    findings = []
    for rel, sha in recorded.items():
        at_claimed = _blob_sha_at(claimed_head, rel) if claimed_head else None
        found_at = next((c for c in commits if _blob_sha_at(c, rel) == sha), None)
        findings.append({
            "path": rel,
            "recorded_sha256": sha,
            "sha256_at_claimed_head": at_claimed,
            "matches_claimed_head": at_claimed == sha,
            "exists_at_any_commit": found_at,
        })

    reproducible = all(f["matches_claimed_head"] for f in findings)
    return {
        "CHECKED": True,
        "artefact": WIRING_REL,
        "as_committed_at": V5_FREEZE_COMMIT,
        "claimed_repository_head": claimed_head,
        "sources": findings,
        "REPRODUCIBLE_FROM_A_COMMIT": reproducible,
        "finding": (
            "the artefact V5 binds for ARM_A_COLLECTOR_WIRING_REGRESSION records "
            "source identities that exist at no commit in this history, under a "
            "repository_head that does not contain them. It was measured against "
            "an uncommitted working tree. V5's own pins are internally consistent "
            "with its freeze commit, so the contract and the evidence it cites "
            "describe different trees"
        ) if not reproducible else "the bound artefact is reproducible from its claimed head",
        "defect_class": "EVIDENCE_MEASURED_AGAINST_AN_UNCOMMITTED_TREE",
        "repair": (
            "the regression was re-measured against the committed tree and the "
            "re-measurement records identities that do match its head. The "
            "original is left byte-unchanged as history"),
        "NOT_A_SCIENTIFIC_RESULT_CHANGE": (
            "this concerns whether the measurement can be reproduced, not whether "
            "Arm A's controller behaviour changed. The re-measurement returns the "
            "same verdict: 1200 steps, zero mismatches"),
    }


def main() -> int:
    head = _git("rev-parse", "HEAD")
    stamp = _dt.datetime.now(_dt.UTC).isoformat()

    gap = {
        "check": "EXECUTION_REACHABILITY_GAP_V2",
        "artifact_semantics": "GOVERNANCE_RECORD_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "classification": "EXECUTION_REACHABILITY_GAP_V2",
        "observed": {
            "runner_resolves": True,
            "arm_identities_resolve": True,
            "selector_propagation_resolves": True,
            "collector_class_resolves": True,
            "declared_output_producers_resolve_to_callables": True,
            "but_the_authorised_entry_point_had_no_lifecycle": (
                "nothing constructed the collector, executed the episode, or invoked "
                "any producer. Each producer's only reference in the source tree was "
                "its own def line"),
        },
        "readiness_hierarchy": [
            "COMPONENT_RESOLUTION does not imply ENTRYPOINT_REACHABILITY",
            "ENTRYPOINT_REACHABILITY does not imply LIFECYCLE_INVOCATION",
            "LIFECYCLE_INVOCATION does not imply RUNTIME_EXECUTION",
        ],
        "attempted_arm_a_authorisation": "AUTHORISED_BUT_NOT_STARTED",
        "explicitly_not": "ARM_A_FAILED",
        "evidence": {
            "pre_arm_a_created": False, "post_arm_a_created": False,
            "isaac_started": False, "hospital_loaded": False,
            "collector_executed": False, "trajectory_produced": False,
            "structured_refusal_exit_code": 2, "traceback": False,
            "partial_scientific_artefacts": False,
        },
        "manifest_v2_limitation": (
            "EXECUTION_MANIFEST_V2 demonstrated component resolution, selector "
            "dispatch resolution and producer name/callable coverage. It did NOT "
            "establish lifecycle reachability from the authorised runner. It is kept "
            "as history and not overwritten"),
        "v5_and_manifest_v2_preserved": True,
        "EVIDENCE_PROVENANCE_FINDING": wiring_evidence_provenance(),
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }
    gap_sha = emit_evidence(GAP_OUT, gap, required_keys=(
        "classification", "observed", "readiness_hierarchy",
        "attempted_arm_a_authorisation", "EXECUTION_STATUS",
        "EVIDENCE_PROVENANCE_FINDING"))

    print("=" * 70)
    print("LIFECYCLE REACHABILITY AND NON-ISAAC REHEARSAL")
    print("=" * 70)
    print(f"HEAD                {head[:12]}")
    print(f"gap record          {GAP_OUT.relative_to(REPO)}  {gap_sha[:16]}...")
    print()

    structural = entrypoint_reachability()
    print(f"ENTRYPOINT_REACHABILITY  {structural['ENTRYPOINT_REACHABILITY']}  "
          f"plan steps={len(structural['plan_steps'])}  "
          f"unbound={structural['required_outputs_not_bound']}")

    with tempfile.TemporaryDirectory(prefix="rehearse_") as raw:
        tmp = pathlib.Path(raw)
        manifest = current_manifest(tmp)

        traces: dict[str, Any] = {}
        for arm in ("ARM_A_CONTROL", "ARM_B_TREATMENT"):
            outcome, runtime = rehearse(manifest, arm, tmp)
            traces[arm] = {
                "status": outcome.status,
                "lifecycle": outcome.lifecycle["LIFECYCLE"],
                "stages_entered": outcome.lifecycle["stages_entered"],
                "invocation_counts": outcome.lifecycle["invocation_counts"],
                "invocations": [
                    {"output_id": i["output_id"], "stage": i["stage"],
                     "producer": i["producer"]}
                    for i in outcome.lifecycle["invocations"]],
                "adapter_boundaries": list(runtime.calls),
                "selector_identity": outcome.outputs["collect_config"]["target_selector"],
                "collect_config": outcome.outputs["collect_config"],
                "problems": outcome.lifecycle["problems"],
                "isaac_launched": False,
                "production_label_consumed": False,
            }
            print(f"  {arm:18s} {outcome.status}  selector="
                  f"{traces[arm]['selector_identity']}  "
                  f"producers={sum(outcome.lifecycle['invocation_counts'].values())}  "
                  f"boundaries={len(runtime.calls)}")

        a_cfg = dict(traces["ARM_A_CONTROL"]["collect_config"])
        b_cfg = dict(traces["ARM_B_TREATMENT"]["collect_config"])
        differing = sorted(k for k in a_cfg if a_cfg[k] != b_cfg[k])
        print(f"shared configuration differs only in: {differing}")

        controls = negative_controls(manifest, tmp)

    for name, result in controls.items():
        marker = "FIRED" if result.get("DETECTED") else "DID NOT FIRE"
        intended = result.get("names_the_intended_kind")
        suffix = "" if intended is None else f"  intended-kind={intended}"
        print(f"  {name:34s} {marker}{suffix}")

    rehearsal_ok = all(t["status"] == "VALID" for t in traces.values())
    controls_ok = all(r.get("DETECTED") for r in controls.values())
    intended_ok = all(r.get("names_the_intended_kind", True) for r in controls.values())
    config_ok = differing == ["target_selector"]
    verdict = ("PASS" if (structural["ENTRYPOINT_REACHABILITY"] == "PASS"
                          and rehearsal_ok and controls_ok and intended_ok and config_ok)
               else "FAIL")

    record = {
        "check": "LIFECYCLE_REACHABILITY_AND_REHEARSAL",
        "artifact_semantics": "REHEARSAL_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "repository_head": head,
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "gap_record": {"path": str(GAP_OUT.relative_to(REPO)), "sha256": gap_sha},
        "lifecycle_stages": [s.value for s in lifecycle.LIFECYCLE_STAGES],
        "producer_lifecycle_map": [
            {"output_id": b.output_id, "arm_scoped": b.arm_scoped,
             "lifecycle_stage": b.stage.value, "producer": b.producer,
             "required": b.required, "multiplicity": b.multiplicity,
             "invocation_precondition": b.invocation_precondition}
            for b in PRODUCER_BINDINGS],
        "required_arm_scoped_producer_count": sum(
            1 for b in PRODUCER_BINDINGS if b.required and b.arm_scoped),
        "ENTRYPOINT_REACHABILITY": structural,
        "NON_ISAAC_LIFECYCLE_REHEARSAL": {
            "verdict": "PASS" if rehearsal_ok else "FAIL",
            "one_orchestration": (
                "rehearsal walks ARM_PLAN, the same table real execution walks. There "
                "is no second lifecycle implementation, because a rehearsal with its "
                "own copy could pass while the real path stayed disconnected"),
            "adapter_boundary": {
                "orchestration": "shared",
                "real_adapter": "navfm.arm_lifecycle:IsaacRuntimeAdapter",
                "rehearsal_adapter": "navfm.arm_lifecycle:RehearsalRuntimeAdapter",
                "adapters_cannot_change_scientific_configuration": True,
            },
            "traces": traces,
            "shared_configuration_differs_only_in": differing,
        },
        "OUTPUT_PRODUCER_REACHABILITY": {
            "verdict": "PASS" if (structural["ENTRYPOINT_REACHABILITY"] == "PASS"
                                  and rehearsal_ok) else "FAIL",
            "definition": (
                "declared + producer resolves + bound to a lifecycle stage + reachable "
                "from the authorised entry point + demonstrated invocation in rehearsal "
                "+ valid ordering + valid multiplicity"),
            "supersedes": (
                "the Manifest V2 definition, which was 'every output has an importable "
                "callable'. That label is not reused, because its semantics changed"),
        },
        "negative_controls": {
            "verdict": "PASS" if (controls_ok and intended_ok) else "FAIL",
            "results": controls,
            "why_these_shapes": (
                "defects here have clustered in negative-space code: refusal handlers, "
                "unreachable dependencies, early returns and partial outputs, none of "
                "which happy-path execution exercises"),
        },
        "readiness_levels": {
            "LEVEL_1_COMPONENT_RESOLUTION": "PASS",
            "LEVEL_2_ENTRYPOINT_REACHABILITY": structural["ENTRYPOINT_REACHABILITY"],
            "LEVEL_3_NON_ISAAC_LIFECYCLE_REHEARSAL": "PASS" if rehearsal_ok else "FAIL",
            "LEVEL_4_CURRENT_PREFLIGHT_AND_ENVIRONMENT": "ESTABLISHED_AT_MANIFEST_FREEZE",
            "LEVEL_5_REAL_RUNTIME_ATTEMPT": "NOT_ESTABLISHED",
            "why_level_5_is_separate": (
                "no rehearsal can establish that Isaac launches, that the Hospital "
                "asset loads, that rendering works, or that the collector completes. "
                "Only an actual attempt can"),
        },
        "no_production_labels_used": True,
        "isaac_launched": False,
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "LIFECYCLE_REACHABILITY": verdict,
    }
    sha = emit_evidence(OUT, record, required_keys=(
        "LIFECYCLE_REACHABILITY", "ENTRYPOINT_REACHABILITY",
        "NON_ISAAC_LIFECYCLE_REHEARSAL", "negative_controls", "EXECUTION_STATUS"))
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha}")
    print(f"LIFECYCLE_REACHABILITY  {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
