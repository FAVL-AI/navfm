"""TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V6: the reachable state.

V5 pinned a tree where every component resolved and nothing invoked them. The
runner could name each artefact an arm would write and contained no code that
wrote one, so the second Arm-A authorisation was refused at the invocation gate
having started no simulator. That is recorded as EXECUTION_REACHABILITY_GAP_V2,
and as AUTHORISED_BUT_NOT_STARTED rather than as an arm failure, because Arm A
never began.

V6 pins the first tree where the lifecycle exists and is demonstrably walked.
The orchestration is a declared plan table, so which producers an arm invokes,
and in what order, is a data structure that can be read rather than control flow
that must be guessed at. The plan is pinned in the contract for the same reason
every other scientific source is: change it and an arm does something different,
even if no other file moves.

The readiness question is layered now, and the layers do not substitute for one
another. Components resolve. The entry point reaches them. A rehearsal with a
fake runtime traverses the same orchestration a real run would and records each
producer being invoked, once, in order. And none of that establishes that Isaac
launches, that the Hospital asset loads, or that the collector completes -- which
is why that remains a separate level that only an attempt can settle.
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

from navfm.arm_lifecycle import (  # noqa: E402
    ARM_PLAN,
    LIFECYCLE_STAGES,
    PRODUCER_BINDINGS,
    entrypoint_reachability,
)
from navfm.execution_environment import (  # noqa: E402
    CONTRACT_VERSION,
    EQUALITY_CRITICAL_FIELDS,
    OBSERVATIONAL_FIELDS,
    PAIRWISE_CRITICAL_FIELDS,
    V6_ADDITIONAL_CRITICAL_FIELDS,
    capture,
    contract_fields,
    digest,
    select,
    sha256_file,
)

AMENDMENT_ID = "TAI-V1-A6-ENV"
AMENDMENT_VERSION = "V6"
OUT = REPO / "gates/BO10/environment_identity_v6_20260912.json"

PREREG_REL = "gates/BO10/terminal_approach_intervention_v1_20260911.json"
V5_REL = "gates/BO10/environment_identity_v5_20260912.json"
GAP_REL = "gates/BO10/execution_reachability_gap_v2_20260912.json"
LIFECYCLE_REL = "gates/BO10/lifecycle_reachability_rehearsal_20260912.json"
WIRING_REL = "gates/BO10/collector_wiring_regression_20260912.json"

PREREG_SHA256 = "941e44da35c8a4145fa4154d1c82deb53da2ef76f04d649789946cc2c3825b4d"
V5_SHA256 = "b4d53a7f5734c87bac5279173aba085513ecece822a058438aafa8ff659108bc"
CONTROL_SHA256 = "679cd60f86ea2b84e4f8fe93cd464a8484bee69204f6716a62f3adb05d04abc6"
EXPECTED_RECORDED_STEPS = 1200


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def refused(stage: str, reasons: list[str]) -> dict[str, Any]:
    return {"V6_AMENDMENT": "REFUSED", "stage": stage, "reasons": reasons,
            "note": ("V6 is not written. The amendment declines rather than raising, "
                     "so the refusal is a recorded scientific result")}


def verify_lifecycle() -> dict[str, Any]:
    """The rehearsal evidence is a precondition of V6, not a citation in it."""
    reasons: list[str] = []
    path = REPO / LIFECYCLE_REL
    if not path.is_file():
        return {"ok": False, "reasons": [f"{LIFECYCLE_REL} is absent"], "record": None}
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return {"ok": False, "reasons": [f"{LIFECYCLE_REL} does not parse: {exc}"],
                "record": None}

    if record.get("LIFECYCLE_REACHABILITY") != "PASS":
        reasons.append(f"lifecycle reachability is {record.get('LIFECYCLE_REACHABILITY')}")
    if record.get("EXECUTION_STATUS") != "NOT_RUN" or record.get("arms_executed") != 0:
        reasons.append("the lifecycle artefact does not declare that no arm ran")
    if record.get("isaac_launched") is not False:
        reasons.append("the lifecycle artefact does not declare that Isaac stayed down")
    if record.get("ENTRYPOINT_REACHABILITY", {}).get("ENTRYPOINT_REACHABILITY") != "PASS":
        reasons.append("entry-point reachability did not pass")
    rehearsal = record.get("NON_ISAAC_LIFECYCLE_REHEARSAL", {})
    if rehearsal.get("verdict") != "PASS":
        reasons.append(f"the rehearsal verdict is {rehearsal.get('verdict')}")
    if rehearsal.get("shared_configuration_differs_only_in") != ["target_selector"]:
        reasons.append(
            "the two arms differ in more than the selector: "
            f"{rehearsal.get('shared_configuration_differs_only_in')}")
    for arm, expected in (("ARM_A_CONTROL", "PATH_VERTEX"),
                          ("ARM_B_TREATMENT", "ARC_LENGTH_INTERPOLATED")):
        trace = rehearsal.get("traces", {}).get(arm, {})
        if trace.get("status") != "VALID":
            reasons.append(f"{arm} rehearsal is {trace.get('status')}")
        if trace.get("selector_identity") != expected:
            reasons.append(f"{arm} rehearsed with {trace.get('selector_identity')!r}")
        counts = trace.get("invocation_counts", {})
        required = [b.output_id for b in PRODUCER_BINDINGS if b.required and b.arm_scoped]
        missing = [o for o in required if counts.get(o) != 1]
        if missing:
            reasons.append(f"{arm} did not invoke exactly once: {missing}")
    controls = record.get("negative_controls", {})
    if controls.get("verdict") != "PASS":
        reasons.append("the fault-injection controls did not all fire")
    for name, result in controls.get("results", {}).items():
        if not result.get("DETECTED"):
            reasons.append(f"negative control {name} did not fire")
    return {"ok": not reasons, "reasons": reasons, "record": record}


def verify_wiring() -> dict[str, Any]:
    path = REPO / WIRING_REL
    if not path.is_file():
        return {"ok": False, "reasons": [f"{WIRING_REL} is absent"], "record": None}
    record = json.loads(path.read_text())
    reasons: list[str] = []
    if record.get("ARM_A_COLLECTOR_WIRING_REGRESSION") != "PASS":
        reasons.append("the Arm-A wiring regression did not pass")
    for name, trace in record.get("regression", {}).get("traces", {}).items():
        if trace.get("steps_evaluated") != EXPECTED_RECORDED_STEPS:
            reasons.append(f"trace {name} evaluated {trace.get('steps_evaluated')} steps")
        if sum(trace.get("mismatches_by_channel", {}).values()) != 0:
            reasons.append(f"trace {name} reports mismatches")
    return {"ok": not reasons, "reasons": reasons, "record": record}


def measure_transitions(contract: dict[str, Any]) -> dict[str, Any]:
    v5 = json.loads((REPO / V5_REL).read_text())[
        "EXECUTION_ENVIRONMENT_IDENTITY_V5"]["frozen_contract_values"]
    changed = {f: {"V5": v5[f], "V6": v} for f, v in contract.items()
               if f in v5 and v5[f] != v}
    added = {f: v for f, v in contract.items() if f not in v5}
    unchanged = [f for f in contract if f in v5 and v5[f] == contract[f]]
    return {"changed": changed, "added": added,
            "unchanged_field_count": len(unchanged)}


def build_payload(amended_at: str, lifecycle: dict[str, Any], wiring: dict[str, Any],
                  contract: dict[str, Any]) -> dict[str, Any]:
    record = lifecycle["record"]
    gap = json.loads((REPO / GAP_REL).read_text())
    v5 = json.loads((REPO / V5_REL).read_text())
    transitions = measure_transitions(contract)
    structural = entrypoint_reachability()

    return {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V6",
        "artifact_semantics": "AMENDMENT_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "amendment_id": AMENDMENT_ID,
        "amendment_version": AMENDMENT_VERSION,
        "amended_at_utc": amended_at,
        "STATUS": "FROZEN",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "authorisation": "NOT AUTHORISED. Neither arm may run under this amendment.",
        "authoritative_intervention_contract": "V6",
        "amends": {
            "predecessor": {"path": V5_REL, "sha256": V5_SHA256, "version": "V5"},
            "original_preregistration": {
                "path": PREREG_REL, "sha256": PREREG_SHA256, "version": "V1"},
            "append_only": True,
            "v1_to_v5_rewritten": False,
            "reason": (
                "V5 pinned a tree in which every component resolved and nothing "
                "invoked them. V6 pins the first tree where the arm lifecycle exists "
                "and is demonstrably walked"),
            "this_does_not_repair_v5": (
                "V5 remains correct about the tree it froze and must continue to "
                "refuse this one"),
            "the_intervention_design_is_unchanged": True,
            "manipulated_factor": "target selection only",
        },
        "EXECUTION_REACHABILITY_GAP_V2": {
            "record": {"path": GAP_REL, "sha256": sha256_file(REPO / GAP_REL)},
            "classification": gap["classification"],
            "attempted_arm_a_authorisation": gap["attempted_arm_a_authorisation"],
            "explicitly_not": gap["explicitly_not"],
            "readiness_hierarchy": gap["readiness_hierarchy"],
            "manifest_v2_limitation": gap["manifest_v2_limitation"],
            "status": "RESOLVED",
        },
        "ARM_LIFECYCLE": {
            "stages": [s.value for s in LIFECYCLE_STAGES],
            "orchestration": "navfm.arm_lifecycle:execute_arm",
            "plan_table": "navfm.arm_lifecycle:ARM_PLAN",
            "plan_steps": len(ARM_PLAN),
            "one_orchestration_for_both_arms_and_both_modes": True,
            "why_a_table_not_control_flow": structural["method"],
            "real_adapter": "navfm.arm_lifecycle:IsaacRuntimeAdapter",
            "rehearsal_adapter": "navfm.arm_lifecycle:RehearsalRuntimeAdapter",
            "adapters_cannot_change_scientific_configuration": True,
            "producer_lifecycle_map": [
                {"output_id": b.output_id, "arm_scoped": b.arm_scoped,
                 "lifecycle_stage": b.stage.value, "producer": b.producer,
                 "required": b.required, "multiplicity": b.multiplicity,
                 "invocation_precondition": b.invocation_precondition}
                for b in PRODUCER_BINDINGS],
            "required_arm_scoped_producers": sum(
                1 for b in PRODUCER_BINDINGS if b.required and b.arm_scoped),
        },
        "LIFECYCLE_REACHABILITY_EVIDENCE": {
            "artefact": {"path": LIFECYCLE_REL,
                         "sha256": sha256_file(REPO / LIFECYCLE_REL)},
            "verdict": record["LIFECYCLE_REACHABILITY"],
            "ENTRYPOINT_REACHABILITY": record["ENTRYPOINT_REACHABILITY"][
                "ENTRYPOINT_REACHABILITY"],
            "NON_ISAAC_LIFECYCLE_REHEARSAL": record["NON_ISAAC_LIFECYCLE_REHEARSAL"][
                "verdict"],
            "OUTPUT_PRODUCER_REACHABILITY": record["OUTPUT_PRODUCER_REACHABILITY"],
            "arm_traces": {
                arm: {"status": t["status"],
                      "selector_identity": t["selector_identity"],
                      "invocation_counts": t["invocation_counts"],
                      "stages_entered": len(t["stages_entered"]),
                      "adapter_boundaries": t["adapter_boundaries"],
                      "isaac_launched": t["isaac_launched"]}
                for arm, t in record["NON_ISAAC_LIFECYCLE_REHEARSAL"]["traces"].items()},
            "shared_configuration_differs_only_in": record[
                "NON_ISAAC_LIFECYCLE_REHEARSAL"]["shared_configuration_differs_only_in"],
            "negative_controls": {
                name: result["DETECTED"]
                for name, result in record["negative_controls"]["results"].items()},
            "readiness_levels": record["readiness_levels"],
            "CLAIM": (
                "Every required producer is bound into the plan the authorised entry "
                "point walks, and a non-Isaac rehearsal of that same orchestration "
                "invoked each of them exactly once, in lifecycle order, for both arms"),
            "CLAIM_BOUNDARY": (
                "this establishes reachability and invocation. It does NOT establish "
                "that Isaac launches, that the Hospital asset loads, that rendering "
                "works, or that the collector completes. No rehearsal can"),
        },
        "ARM_A_COLLECTOR_WIRING_REGRESSION": {
            "artefact": {"path": WIRING_REL, "sha256": sha256_file(REPO / WIRING_REL)},
            "verdict": wiring["record"]["ARM_A_COLLECTOR_WIRING_REGRESSION"],
            "traces": {
                name: {"steps_evaluated": t["steps_evaluated"],
                       "mismatches_by_channel": t["mismatches_by_channel"]}
                for name, t in wiring["record"]["regression"]["traces"].items()},
            "CLAIM": (
                "Arm A's controller behaviour is unchanged over the frozen regression "
                f"domain: {EXPECTED_RECORDED_STEPS} recorded poses on two route "
                "densities against the pre-seam tracker and both post-seam legacy "
                "constructions"),
        },
        "VERSION_CHAIN": [
            {"node": "ENVIRONMENT_V5", "path": V5_REL, "sha256": V5_SHA256,
             "timestamp_utc": v5["amended_at_utc"], "predecessor": "ENVIRONMENT_V4",
             "reason": v5["amends"]["reason"],
             "evidence_basis": "the bound wiring regression and executability evidence"},
            {"node": "EXECUTION_REACHABILITY_GAP_V2", "path": GAP_REL,
             "sha256": sha256_file(REPO / GAP_REL), "timestamp_utc": gap["timestamp_utc"],
             "predecessor": "ENVIRONMENT_V5",
             "reason": "record that components resolved and nothing invoked them",
             "evidence_basis": "a structured refusal with no Isaac and no artefacts"},
            {"node": "LIFECYCLE_REACHABILITY_AND_REHEARSAL", "path": LIFECYCLE_REL,
             "sha256": sha256_file(REPO / LIFECYCLE_REL),
             "timestamp_utc": record["timestamp_utc"],
             "predecessor": "EXECUTION_REACHABILITY_GAP_V2",
             "reason": "bind every producer into the lifecycle and rehearse it",
             "evidence_basis": (
                 "structural plan binding plus a non-Isaac rehearsal of both arms and "
                 "eight fault-injection controls")},
            {"node": "ENVIRONMENT_V6", "path": str(OUT.relative_to(REPO)),
             "sha256": "<this artefact>", "timestamp_utc": amended_at,
             "predecessor": "LIFECYCLE_REACHABILITY_AND_REHEARSAL",
             "reason": "pin the first reachable, rehearsed executable state",
             "evidence_basis": "the bound lifecycle and wiring artefacts"},
        ],
        "SOURCE_IDENTITY_TRANSITIONS_V5_TO_V6": {
            "measured_not_prescribed": True,
            "changed": {
                field: {**values,
                        "reason": "the arm lifecycle and runner rehearsal mode were added",
                        "evidence": {"path": LIFECYCLE_REL,
                                     "sha256": sha256_file(REPO / LIFECYCLE_REL)}}
                for field, values in transitions["changed"].items()},
            "added": {
                field: {"V6": value,
                        "reason": ("the plan table decides which producers an arm "
                                   "invokes and in what order, so a change to it "
                                   "changes what an arm does even when every other "
                                   "pinned file is identical"),
                        "evidence": {"path": LIFECYCLE_REL,
                                     "sha256": sha256_file(REPO / LIFECYCLE_REL)}}
                for field, value in transitions["added"].items()},
            "unchanged_field_count": transitions["unchanged_field_count"],
            "control_py_unchanged_since_v3": CONTROL_SHA256,
        },
        "ONE_FACTOR_EXECUTION_CONTRACT": {
            **v5["ONE_FACTOR_EXECUTION_CONTRACT"],
            "selector_reaches_the_collector_through_the_lifecycle": True,
            "propagation_path": (
                "manifest arm identity -> execute_arm plan -> build_collect_config -> "
                "CollectConfig.target_selector -> resolve_target_selector -> "
                "PurePursuit(target_selector=...)"),
            "rehearsal_confirmed_only_target_differs": record[
                "NON_ISAAC_LIFECYCLE_REHEARSAL"]["shared_configuration_differs_only_in"],
        },
        "EXECUTION_ENVIRONMENT_IDENTITY_V6": {
            "contract_version": CONTRACT_VERSION,
            "supersedes": "V5",
            "implementation": "src/navfm/execution_environment.py",
            "frozen_contract_values": contract,
            "contract_digest": digest(contract),
            "contract_critical_fields": list(contract_fields("V6")),
            "fields_added_since_v5": list(V6_ADDITIONAL_CRITICAL_FIELDS),
            "pairwise_critical_fields": list(PAIRWISE_CRITICAL_FIELDS),
            "equality_critical_fields": list(EQUALITY_CRITICAL_FIELDS),
            "observational_fields_recorded_never_compared": list(OBSERVATIONAL_FIELDS),
        },
        "HISTORICAL_CONTRACTS_REMAIN_FROZEN": {
            "v1_to_v5_rewritten": False,
            "invariants": [
                "V2 accepts its freeze state and rejects the later seam state",
                "V3 accepts its freeze state and rejects the later treatment state",
                "V4 accepts its freeze state and rejects the later wiring state",
                "V5 accepts its freeze state and rejects the later lifecycle state",
                "V6 accepts the final reachable executable state",
            ],
            "required_control": {"current_tree_against_V5": "REFUSE",
                                 "current_tree_against_V6": "PASS"},
        },
        "READINESS_MODEL": {
            "LEVEL_1_COMPONENT_RESOLUTION": "established",
            "LEVEL_2_ENTRYPOINT_REACHABILITY": "established",
            "LEVEL_3_NON_ISAAC_LIFECYCLE_REHEARSAL": "established",
            "LEVEL_4_CURRENT_PREFLIGHT_AND_ENVIRONMENT": "established at manifest freeze",
            "LEVEL_5_REAL_RUNTIME_ATTEMPT": "NOT established, and not establishable here",
            "why_this_model_exists": (
                "two authorisations were spent discovering that a component existing "
                "is not a component being reachable, and that a component being "
                "reachable is not a component being invoked. Naming the levels stops a "
                "lower one from being reported as a higher one"),
        },
        "EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY": v5["EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY"],
        "scene_limitation_carried_forward": v5["scene_limitation_carried_forward"],
        "EXECUTION_MANIFEST": "NOT_FROZEN_BY_THIS_AMENDMENT",
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "milestone_unaffected": v5["milestone_unaffected"],
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
            if key not in a:
                out.append(f"{prefix}{key} (added)")
            elif key not in b:
                out.append(f"{prefix}{key} (removed)")
            else:
                out.extend(diff_paths(a[key], b[key], f"{prefix}{key}."))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{prefix.rstrip('.')} (length {len(b)} -> {len(a)})")
        else:
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                out.extend(diff_paths(x, y, f"{prefix}{i}."))
    elif a != b:
        out.append(prefix.rstrip(".") or "<root>")
    return out


def freeze() -> dict[str, Any]:
    reasons: list[str] = []
    for rel, expected in ((PREREG_REL, PREREG_SHA256), (V5_REL, V5_SHA256)):
        observed = sha256_file(REPO / rel)
        if observed != expected:
            reasons.append(
                f"{rel} sha256 is {str(observed)[:16]}..., expected {expected[:16]}...")
    if reasons:
        return refused("predecessor verification", reasons)

    observed_control = sha256_file(REPO / "src/navfm/control.py")
    if observed_control != CONTROL_SHA256:
        return refused("source identity", [
            f"control.py is {str(observed_control)[:16]}..., V6 pins "
            f"{CONTROL_SHA256[:16]}.... The controller must not change in this tranche"])

    structural = entrypoint_reachability()
    if structural["ENTRYPOINT_REACHABILITY"] != "PASS":
        return refused("entry-point reachability", [
            f"unbound outputs: {structural['required_outputs_not_bound']}, "
            f"stage mismatches: {structural['stage_binding_mismatches']}"])

    lifecycle = verify_lifecycle()
    if not lifecycle["ok"]:
        return refused("lifecycle verification", lifecycle["reasons"])

    wiring = verify_wiring()
    if not wiring["ok"]:
        return refused("wiring regression verification", wiring["reasons"])

    contract = select(capture(REPO), contract_fields("V6"))

    if OUT.exists():
        prior = json.loads(OUT.read_text())
        amended_at = str(prior["amended_at_utc"])
        result = build_payload(amended_at, lifecycle, wiring, contract)
        drift = diff_paths(strip_volatile(result), strip_volatile(prior))
        if drift:
            shown = "\n  ".join(drift[:25]) + ("\n  ..." if len(drift) > 25 else "")
            return refused("canonical regeneration", [
                f"the canonical amendment no longer matches {OUT.relative_to(REPO)}. "
                f"Fields that differ ({len(drift)}):\n  {shown}",
                "V6 is frozen and cited by hash; a change requires an explicit V7"])
        refrozen = False
    else:
        amended_at = _dt.datetime.now(_dt.UTC).isoformat()
        result = build_payload(amended_at, lifecycle, wiring, contract)
        refrozen = True

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    for key in ("ARM_LIFECYCLE", "LIFECYCLE_REACHABILITY_EVIDENCE", "VERSION_CHAIN",
                "SOURCE_IDENTITY_TRANSITIONS_V5_TO_V6", "EXECUTION_STATUS"):
        if key not in back:
            return refused("evidence guard", [f"missing {key} after write"])
    if back["EXECUTION_STATUS"] != "NOT_RUN":
        return refused("evidence guard", ["no arm has run and the artefact must say so"])

    return {"V6_AMENDMENT": "FROZEN", "refrozen": refrozen, "payload": back,
            "sha256": sha256_file(OUT), "canonical_digest": digest(strip_volatile(back))}


def main() -> int:
    outcome = freeze()
    if outcome["V6_AMENDMENT"] != "FROZEN":
        print(f"V6_AMENDMENT = {outcome['V6_AMENDMENT']}")
        print(f"stage        : {outcome['stage']}")
        for reason in outcome["reasons"]:
            print(f"  - {reason}")
        return 1

    payload = outcome["payload"]
    evidence = payload["LIFECYCLE_REACHABILITY_EVIDENCE"]
    transitions = payload["SOURCE_IDENTITY_TRANSITIONS_V5_TO_V6"]
    print("=" * 70)
    print("TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V6")
    print("=" * 70)
    print(f"HEAD                {_git('rev-parse', 'HEAD')[:12]}")
    print(f"predecessor         V5 {V5_SHA256[:16]}...")
    print(f"gap V2              {payload['EXECUTION_REACHABILITY_GAP_V2']['status']}")
    print(f"entrypoint reach    {evidence['ENTRYPOINT_REACHABILITY']}")
    print(f"rehearsal           {evidence['NON_ISAAC_LIFECYCLE_REHEARSAL']}")
    print(f"producer reach      {evidence['OUTPUT_PRODUCER_REACHABILITY']['verdict']}")
    for arm, trace in evidence["arm_traces"].items():
        print(f"  {arm:18s} {trace['status']}  {trace['selector_identity']}  "
              f"producers={sum(trace['invocation_counts'].values())}")
    print(f"negative controls   {sum(evidence['negative_controls'].values())}/"
          f"{len(evidence['negative_controls'])} fired")
    print(f"arm-A regression    {payload['ARM_A_COLLECTOR_WIRING_REGRESSION']['verdict']}")
    print()
    print("V5 -> V6 transitions (measured):")
    for field in transitions["changed"]:
        print(f"  changed {field}")
    for field in transitions["added"]:
        print(f"  added   {field}")
    print(f"  unchanged fields    {transitions['unchanged_field_count']}")
    print()
    print(f"contract fields     {len(contract_fields('V6'))} "
          f"(V5 had {len(contract_fields('V5'))})")
    print(f"contract digest     {payload['EXECUTION_ENVIRONMENT_IDENTITY_V6']['contract_digest']}")
    print(f"canonical digest    {outcome['canonical_digest']}")
    print(f"{'FROZEN (first write)' if outcome['refrozen'] else 'RE-VERIFIED (unchanged)'}")
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {outcome['sha256']}")
    print("V6_AMENDMENT        FROZEN")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
