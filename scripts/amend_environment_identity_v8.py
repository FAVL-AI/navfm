"""TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V8 -- append-only.

V7 pinned the first tree whose authorised entry point constructed the real Isaac
adapter and entered mode=REAL. That was true, and it was enough to start an arm:
Attempt 1 entered the production lifecycle, created a valid PRE_ARM_A, launched
Isaac and built the collector.

It then stopped at scene loading with ``unhandled AssertionError:`` and an empty
reason. The adapter owned a live application; the collector had been handed
``self._app.config`` -- correct for the ``sim: SimConfig`` parameter, and not an
application. ``Collector.run`` is the only place that ever assigned ``_app``, and
the adapter does not call it, because an arm is one episode under a frozen route
rather than a collection loop.

So the rung V7 established was real and the next one was missing:

    the real path is entered
        is not
    the objects that path needs are propagated across it

V8 pins the first tree where the adapter hands the collector the application it
owns, where that boundary refuses with a named category instead of a bare
assertion, and where an attempt has an identity so Attempt 1 stays visible.

V7 is not repaired and not rewritten. It remains correct about the tree it froze,
and must continue to refuse this one. No scientific treatment definition changes:
the controller, the selectors and the preregistration are untouched, and the
frozen Arm-A regression returns the same verdict over the same 1200 poses.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import subprocess
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.execution_environment import (  # noqa: E402
    capture,
    contract_fields,
    digest,
    select,
    sha256_file,
)

AMENDMENT_ID = "TAI-V1-A8-ENV"
AMENDMENT_VERSION = "V8"
OUT = REPO / "gates/BO10/environment_identity_v8_20260917.json"

PREREG_REL = "gates/BO10/terminal_approach_intervention_v1_20260911.json"
V7_REL = "gates/BO10/environment_identity_v7_20260917.json"
SEAM_REL = "gates/BO10/adapter_collector_app_seam_20260917.json"
ATTEMPT_REL = "gates/BO10/arm_a_attempt_001_20260917.json"
WIRING_REL = "gates/BO10/collector_wiring_regression_20260912.json"

PREREG_SHA256 = "941e44da35c8a4145fa4154d1c82deb53da2ef76f04d649789946cc2c3825b4d"
CONTROL_SHA256 = "679cd60f86ea2b84e4f8fe93cd464a8484bee69204f6716a62f3adb05d04abc6"
V7_FREEZE_COMMIT = "01916dfa3a2901177ae1bc07caffd0881139d798"
EXPECTED_RECORDED_STEPS = 1200


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def refused(stage: str, reasons: list[str]) -> dict[str, Any]:
    return {"V8_AMENDMENT": "REFUSED", "stage": stage, "reasons": reasons,
            "note": ("V8 is not written. The amendment declines rather than raising, "
                     "so the refusal is a recorded scientific result")}


def verify_seam() -> dict[str, Any]:
    """The seam evidence is a precondition of V8, not a citation in it."""
    path = REPO / SEAM_REL
    if not path.is_file():
        return {"ok": False, "reasons": [f"{SEAM_REL} is absent"], "record": None}
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return {"ok": False, "reasons": [f"{SEAM_REL} does not parse: {exc}"],
                "record": None}

    reasons: list[str] = []
    proof = record.get("proof", {})
    if proof.get("ADAPTER_COLLECTOR_APP_SEAM") != "REPAIRED_AND_VALIDATED":
        reasons.append(f"the seam is {proof.get('ADAPTER_COLLECTOR_APP_SEAM')}")
    if proof.get("same_object", {}).get("PASS") is not True:
        reasons.append("the collector does not hold the adapter's application")
    if proof.get("single_owner", {}).get("applications_constructed") != 1:
        reasons.append(
            f"{proof.get('single_owner', {}).get('applications_constructed')} "
            "applications were constructed; exactly one is permitted")
    if proof.get("configuration_preserved", {}).get("PASS") is not True:
        reasons.append("the frozen sim configuration did not survive the repair")
    reach = proof.get("scene_load_reachability", {})
    if reach.get("PASS") is not True or reach.get("open_stage_calls") != 1:
        reasons.append(
            f"scene-load reachability is {reach.get('PASS')} with "
            f"{reach.get('open_stage_calls')} open_stage calls")
    controls = proof.get("negative_controls", {})
    if controls.get("verdict") != "PASS":
        reasons.append("the seam controls did not all fire")
    for name, result in controls.get("results", {}).items():
        if not result.get("DETECTED"):
            reasons.append(f"negative control {name} did not fire")

    if record.get("HEAD_CONTENT_COHERENCE", {}).get("HEAD_CONTENT_COHERENCE") != "PASS":
        reasons.append("the seam evidence does not cohere with the head it names")
    if record.get("isaac_launched") is not False:
        reasons.append("the seam artefact does not declare that Isaac stayed down")
    if record.get("EXECUTION_STATUS") != "NOT_RUN" or record.get("arms_executed") != 0:
        reasons.append("the seam artefact does not declare that no arm ran")

    regression = record.get("ARM_A_BEHAVIOURAL_REGRESSION", {})
    if regression.get("verdict") != "PASS":
        reasons.append(f"the Arm-A regression is {regression.get('verdict')}")
    for name, trace in regression.get("traces", {}).items():
        if trace.get("steps_evaluated") != EXPECTED_RECORDED_STEPS:
            reasons.append(f"{name} evaluated {trace.get('steps_evaluated')} steps")
        if trace.get("mismatches"):
            reasons.append(f"{name} has {trace['mismatches']} behavioural mismatches")

    return {"ok": not reasons, "reasons": reasons, "record": record}


def verify_attempt_record() -> dict[str, Any]:
    """Attempt 1 must be recorded, and recorded as not a navigation outcome."""
    path = REPO / ATTEMPT_REL
    if not path.is_file():
        return {"ok": False, "reasons": [f"{ATTEMPT_REL} is absent"], "record": None}
    record = json.loads(path.read_text())
    reasons: list[str] = []
    if record.get("CLASSIFICATION") != "INFRASTRUCTURE_FAILURE_BEFORE_EPISODE":
        reasons.append(f"attempt 001 is classified {record.get('CLASSIFICATION')}")
    if record.get("EPISODE_STARTED") is not False:
        reasons.append("the attempt record does not declare that no episode started")
    if record.get("ARM_A_SCIENTIFIC_RESULT") != "NOT_OBSERVED":
        reasons.append("the attempt record claims a scientific result")
    pre = record.get("ATTEMPT_001_PRE_CAPTURE", {})
    if pre.get("PRESERVED") is not True:
        reasons.append("the attempt-1 PRE capture is not marked preserved")
    observed = sha256_file(REPO / pre.get("path", ""))
    if observed is None or observed != pre.get("sha256"):
        reasons.append(
            "the attempt-1 PRE capture no longer matches the hash bound to it; it "
            "must never be rewritten")
    return {"ok": not reasons, "reasons": reasons, "record": record}


def measure_transitions(contract: dict[str, Any]) -> dict[str, Any]:
    prior = json.loads((REPO / V7_REL).read_text())
    before = prior["EXECUTION_ENVIRONMENT_IDENTITY_V7"]["frozen_contract_values"]
    changed: dict[str, Any] = {}
    added: dict[str, Any] = {}
    for field, value in contract.items():
        if field not in before:
            added[field] = {"V8": value}
        elif before[field] != value:
            changed[field] = {"V7": before[field], "V8": value}
    unchanged = [f for f in contract if f in before and before[f] == contract[f]]
    rationale = {
        "scientific_code.collect_sha256": (
            "Collector accepts a live isaac_app, refuses a missing one with a named "
            "category instead of a bare assertion, and refuses to build a second "
            "application when one was handed in"),
        "scientific_code.arm_lifecycle_sha256": (
            "the adapter hands the collector the application it owns, and the "
            "attempt identity is read from the frozen manifest so a repaired "
            "attempt cannot overwrite attempt 001"),
    }
    return {
        "measured_not_prescribed": True,
        "changed": changed,
        "added": added,
        "unchanged_field_count": len(unchanged),
        "expected_change": {f: rationale.get(f, "unreviewed change") for f in changed},
        "what_did_not_change": (
            "the controller, the selectors, the route, the seed and the "
            "preregistration. This tranche moved a runtime object, not the "
            "experiment"),
    }


def build_payload(amended_at: str, seam: dict[str, Any], attempt: dict[str, Any],
                  contract: dict[str, Any]) -> dict[str, Any]:
    seam_record = seam["record"]
    proof = seam_record["proof"]
    return {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V8",
        "artifact_semantics": "AMENDMENT_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "amendment_id": AMENDMENT_ID,
        "amendment_version": AMENDMENT_VERSION,
        "amended_at_utc": amended_at,
        "STATUS": "FROZEN",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "authorisation": "NOT AUTHORISED. Neither arm may run under this amendment.",
        "authoritative_intervention_contract": "V8",
        "amends": {
            "predecessor": {"path": V7_REL, "sha256": sha256_file(REPO / V7_REL),
                            "version": "V7"},
            "original_preregistration": {
                "path": PREREG_REL, "sha256": sha256_file(REPO / PREREG_REL),
                "version": "V1"},
            "append_only": True,
            "v1_to_v7_rewritten": False,
            "reason": (
                "V7 pinned a tree whose real path was entered and whose adapter "
                "handed the collector a configuration where a live application was "
                "required. V8 pins the first tree where that object crosses the "
                "boundary"),
            "this_does_not_repair_v7": (
                "V7 remains correct about the tree it froze and must continue to "
                "refuse this one"),
            "the_intervention_design_is_unchanged": True,
            "manipulated_factor": "target selection only",
        },
        "ARM_A_ATTEMPT_001": {
            "record": {"path": ATTEMPT_REL, "sha256": sha256_file(REPO / ATTEMPT_REL)},
            "classification": attempt["record"]["CLASSIFICATION"],
            "executed_at_head": attempt["record"]["executed_at_head"],
            "episode_started": attempt["record"]["EPISODE_STARTED"],
            "scientific_result": attempt["record"]["ARM_A_SCIENTIFIC_RESULT"],
            "pre_capture": attempt["record"]["ATTEMPT_001_PRE_CAPTURE"],
            "excluded_from": attempt["record"]["excluded_from"],
            "NOT_AN_ARM_A_OUTCOME": attempt["record"]["NOT_A_NAVIGATION_OUTCOME"],
        },
        "ADAPTER_COLLECTOR_APP_SEAM": {
            "artefact": {"path": SEAM_REL, "sha256": sha256_file(REPO / SEAM_REL)},
            "verdict": proof["ADAPTER_COLLECTOR_APP_SEAM"],
            "old_dataflow": seam_record["dataflow"]["old_dataflow"],
            "corrected_dataflow": seam_record["dataflow"]["corrected_dataflow"],
            "collector_accepts_a_live_app":
                seam_record["dataflow"]["collector_accepts_a_live_app"],
            "adapter_passes_the_app": seam_record["dataflow"]["adapter_passes_the_app"],
            "bare_assert_removed":
                not seam_record["dataflow"]["open_scene_uses_a_bare_assert"],
            "structured_refusal_category": "ISAAC_APP_NOT_BOUND_TO_COLLECTOR",
            "single_owner_category": "ISAAC_APP_SINGLE_OWNER_VIOLATION",
            "same_object": proof["same_object"]["PASS"],
            "applications_constructed":
                proof["single_owner"]["applications_constructed"],
            "open_stage_calls": proof["scene_load_reachability"]["open_stage_calls"],
            "scene_identifier":
                proof["scene_load_reachability"]["scene_identifier_passed"],
            "negative_controls": {
                name: result["DETECTED"]
                for name, result in proof["negative_controls"]["results"].items()},
            "INVARIANT": seam_record["INVARIANT"],
            "CLAIM_BOUNDARY": seam_record["CLAIM_BOUNDARY"],
        },
        "ATTEMPT_IDENTITY_MODEL": {
            "intervention_id": "TERMINAL_APPROACH_INTERVENTION_V1",
            "arm_ids": ["ARM_A_CONTROL", "ARM_B_TREATMENT"],
            "attempt_ids": ["001", "002"],
            "resolved_from": "the frozen manifest, never the command line",
            "why_not_a_flag": (
                "an attempt number that can be typed at run time can be retyped "
                "after a result is seen, and the point of numbering attempts is "
                "that an earlier one stays visible"),
            "label_shape": "<PHASE>_ARM_<ARM>[_ATTEMPT_<nnn>]",
            "unnumbered_label_means": (
                "attempt 001. PRE_ARM_A was written before attempts were numbered "
                "and is evidence, so it stays valid rather than becoming malformed"),
            "attempt_001_preserved": True,
        },
        "ARM_A_BEHAVIOURAL_REGRESSION": seam_record["ARM_A_BEHAVIOURAL_REGRESSION"],
        "VERSION_CHAIN": [
            {"node": "ENVIRONMENT_V7", "path": V7_REL,
             "sha256": sha256_file(REPO / V7_REL), "predecessor": "ENVIRONMENT_V6",
             "reason": "pinned the tree whose real path is entered"},
            {"node": "ARM_A_ATTEMPT_001", "path": ATTEMPT_REL,
             "sha256": sha256_file(REPO / ATTEMPT_REL), "predecessor": "ENVIRONMENT_V7",
             "reason": ("the first real execution: lifecycle entered, Isaac launched, "
                        "scene-load boundary failed, no episode")},
            {"node": "ADAPTER_COLLECTOR_APP_SEAM", "path": SEAM_REL,
             "sha256": sha256_file(REPO / SEAM_REL), "predecessor": "ARM_A_ATTEMPT_001",
             "reason": "the application now crosses the adapter/collector boundary"},
            {"node": "ENVIRONMENT_V8", "predecessor": "ADAPTER_COLLECTOR_APP_SEAM",
             "reason": "pins the first tree where that propagation holds"},
        ],
        "SOURCE_IDENTITY_TRANSITIONS_V7_TO_V8": measure_transitions(contract),
        "EXECUTION_ENVIRONMENT_IDENTITY_V8": {
            "contract_version": "EXECUTION_ENVIRONMENT_IDENTITY_V2",
            "supersedes": "V7",
            "implementation": "src/navfm/execution_environment.py",
            "frozen_contract_values": contract,
            "field_count": len(contract),
            "contract_digest": digest(contract),
        },
        "HISTORICAL_CONTRACTS_REMAIN_FROZEN": {
            "v1_to_v7_rewritten": False,
            "required_control": {
                "current_tree_against_V7": "REFUSE",
                "current_tree_against_V8": "PASS",
            },
        },
        "READINESS_MODEL": {
            "LEVEL_1_COMPONENT_RESOLUTION": "established",
            "LEVEL_2_ENTRYPOINT_REACHABILITY": "established",
            "LEVEL_3_NON_ISAAC_LIFECYCLE_REHEARSAL": "established",
            "LEVEL_4_CURRENT_PREFLIGHT_AND_ENVIRONMENT": "established at manifest freeze",
            "LEVEL_4_5_REAL_MODE_ENTRYPOINT_REACHABILITY": "established by V7",
            "LEVEL_4_6_RUNTIME_OBJECT_PROPAGATION": "established by V8",
            "LEVEL_5_REAL_RUNTIME_ATTEMPT": (
                "PARTIAL. Attempt 001 established that Isaac launches, that the "
                "runtime becomes available and that the collector constructs. It did "
                "NOT establish that the Hospital scene loads or that an episode "
                "runs"),
            "why_level_4_6_exists": (
                "the real path being entered is not the objects that path needs "
                "being propagated across it. Every gate before Attempt 1 compared "
                "configuration, and configuration was correct throughout"),
        },
        "EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY": (
            "the adapter's application reaches the collector and scene loading is "
            "reachable. It does not establish that the Hospital scene loads, that "
            "the render loop runs, or that the collector completes an episode. Only "
            "attempt 002 would establish those"),
        "EXECUTION_MANIFEST": "NOT_FROZEN_BY_THIS_AMENDMENT",
        "ARM_A_ATTEMPT_002": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }


def strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: strip_volatile(v) for k, v in payload.items()
                if k not in {"amended_at_utc", "timestamp_utc"}}
    if isinstance(payload, list):
        return [strip_volatile(v) for v in payload]
    return payload


def diff_paths(a: Any, b: Any, prefix: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            out.extend(diff_paths(a.get(key), b.get(key), f"{prefix}{key}."))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{prefix.rstrip('.')} (length {len(a)} vs {len(b)})")
        else:
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                out.extend(diff_paths(x, y, f"{prefix}{i}."))
    elif a != b:
        out.append(prefix.rstrip("."))
    return out


def freeze() -> dict[str, Any]:
    observed_prereg = sha256_file(REPO / PREREG_REL)
    if observed_prereg != PREREG_SHA256:
        return refused("predecessor verification", [
            f"{PREREG_REL} sha256 is {str(observed_prereg)[:16]}..., expected "
            f"{PREREG_SHA256[:16]}..."])

    observed_control = sha256_file(REPO / "src/navfm/control.py")
    if observed_control != CONTROL_SHA256:
        return refused("source identity", [
            f"control.py is {str(observed_control)[:16]}..., V8 pins "
            f"{CONTROL_SHA256[:16]}.... The controller must not change in this tranche"])

    attempt = verify_attempt_record()
    if not attempt["ok"]:
        return refused("attempt-001 verification", attempt["reasons"])

    seam = verify_seam()
    if not seam["ok"]:
        return refused("app-seam verification", seam["reasons"])

    contract = select(capture(REPO), contract_fields("V8"))

    if OUT.exists():
        prior = json.loads(OUT.read_text())
        amended_at = str(prior["amended_at_utc"])
        result = build_payload(amended_at, seam, attempt, contract)
        drift = diff_paths(strip_volatile(result), strip_volatile(prior))
        if drift:
            shown = "\n  ".join(drift[:25]) + ("\n  ..." if len(drift) > 25 else "")
            return refused("canonical regeneration", [
                f"the canonical amendment no longer matches {OUT.relative_to(REPO)}. "
                f"Fields that differ ({len(drift)}):\n  {shown}",
                "V8 is frozen and cited by hash; a change requires an explicit V9"])
        refrozen = False
    else:
        amended_at = _dt.datetime.now(_dt.UTC).isoformat()
        result = build_payload(amended_at, seam, attempt, contract)
        refrozen = True

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    for key in ("ARM_A_ATTEMPT_001", "ADAPTER_COLLECTOR_APP_SEAM",
                "ATTEMPT_IDENTITY_MODEL", "VERSION_CHAIN",
                "SOURCE_IDENTITY_TRANSITIONS_V7_TO_V8", "EXECUTION_STATUS"):
        if key not in back:
            return refused("evidence guard", [f"missing {key} after write"])
    if back["EXECUTION_STATUS"] != "NOT_RUN":
        return refused("evidence guard", ["no arm has run and the artefact must say so"])

    return {"V8_AMENDMENT": "FROZEN", "refrozen": refrozen, "payload": back,
            "sha256": sha256_file(OUT), "canonical_digest": digest(strip_volatile(back))}


def main() -> int:
    print("=" * 70)
    print("TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V8")
    print("=" * 70)
    print(f"HEAD                {_git('rev-parse', 'HEAD')[:12]}")

    outcome = freeze()
    if outcome["V8_AMENDMENT"] != "FROZEN":
        print(f"V8_AMENDMENT = REFUSED\nstage        : {outcome['stage']}")
        for reason in outcome["reasons"]:
            print(f"  - {reason}")
        return 1

    payload = outcome["payload"]
    transitions = payload["SOURCE_IDENTITY_TRANSITIONS_V7_TO_V8"]
    seam = payload["ADAPTER_COLLECTOR_APP_SEAM"]
    print()
    print("V7 -> V8 transitions (measured):")
    for field in transitions["changed"]:
        print(f"  changed {field}")
    for field in transitions["added"]:
        print(f"  added   {field}")
    print(f"  unchanged fields    {transitions['unchanged_field_count']}")
    print()
    print(f"attempt 001         {payload['ARM_A_ATTEMPT_001']['classification']}")
    print(f"  PRE preserved     {payload['ARM_A_ATTEMPT_001']['pre_capture']['PRESERVED']}")
    print(f"  scientific result {payload['ARM_A_ATTEMPT_001']['scientific_result']}")
    print(f"seam                {seam['verdict']}")
    print(f"  same object       {seam['same_object']}")
    print(f"  applications      {seam['applications_constructed']}")
    print(f"  open_stage calls  {seam['open_stage_calls']}")
    print(f"  bare assert gone  {seam['bare_assert_removed']}")
    print(f"contract fields     {payload['EXECUTION_ENVIRONMENT_IDENTITY_V8']['field_count']}")
    print(f"contract digest     {payload['EXECUTION_ENVIRONMENT_IDENTITY_V8']['contract_digest']}")
    print(f"canonical digest    {outcome['canonical_digest']}")
    print("FROZEN (first write)" if outcome["refrozen"] else "unchanged (idempotent)")
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {outcome['sha256']}")
    print("V8_AMENDMENT        FROZEN")
    print("LEVEL_5             PARTIAL -- Isaac launches; no episode has run")
    print("ARM_A_ATTEMPT_002   NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
