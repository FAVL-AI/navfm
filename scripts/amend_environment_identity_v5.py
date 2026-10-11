"""TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V5: the runnable state.

V4 pinned a source tree that was correct and could not be executed. The selector
seam existed and was proved neutral, the treatment existed and was validated,
the manifest declared exactly what an arm would write -- and nothing connected
the selector to the collector, and nothing existed to write those artefacts. The
first Arm-A authorisation was refused at the pre-Isaac gates for that reason.

V5 pins the tree that can actually be invoked: the collector now resolves a
declared selector, one manifest-driven runner dispatches either arm, and every
declared output resolves to a producer. It does not change the intervention. The
manipulated factor is still target selection and nothing else.

What V5 adds to the contract is the execution machinery itself. The runner and
its library decide which selector an arm receives and which artefacts an arm
produces, so leaving them unpinned would let the thing that performs the
experiment change without the contract noticing -- the same hole the seam opened
one layer down, which is what V3 existed to close.

V4 is not repaired and is not rewritten. It remains correct about the tree it
froze, and it must continue to refuse this one.
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
    CONTRACT_VERSION,
    EQUALITY_CRITICAL_FIELDS,
    OBSERVATIONAL_FIELDS,
    PAIRWISE_CRITICAL_FIELDS,
    V5_ADDITIONAL_CRITICAL_FIELDS,
    capture,
    contract_fields,
    digest,
    select,
    sha256_file,
)
from navfm.execution_manifest import build_manifest  # noqa: E402
from navfm.intervention_runner import executability  # noqa: E402

AMENDMENT_ID = "TAI-V1-A5-ENV"
AMENDMENT_VERSION = "V5"
OUT = REPO / "gates/BO10/environment_identity_v5_20260912.json"

PREREG_REL = "gates/BO10/terminal_approach_intervention_v1_20260911.json"
V4_REL = "gates/BO10/environment_identity_v4_20260912.json"
TREATMENT_REL = "gates/BO10/arclength_treatment_validation_20260912.json"
WIRING_REL = "gates/BO10/collector_wiring_regression_20260912.json"
GAP_REL = "gates/BO10/execution_readiness_gap_v1_20260912.json"

PREREG_SHA256 = "941e44da35c8a4145fa4154d1c82deb53da2ef76f04d649789946cc2c3825b4d"
V4_SHA256 = "226a3b20cab9b02ca5e71c01ddb24f0aa7b1ca1e03b72bc2e4d45a1adb46aa93"
TREATMENT_SHA256 = "25e006d53dd0ec524a724362c205185c0bc7f660c42040e581d448c26fc2ad4d"
CONTROL_SHA256 = "679cd60f86ea2b84e4f8fe93cd464a8484bee69204f6716a62f3adb05d04abc6"

EXPECTED_RECORDED_STEPS = 1200


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def refused(stage: str, reasons: list[str]) -> dict[str, Any]:
    return {"V5_AMENDMENT": "REFUSED", "stage": stage, "reasons": reasons,
            "note": ("V5 is not written. The amendment declines rather than raising, "
                     "so the refusal is a recorded scientific result")}


def verify_wiring() -> dict[str, Any]:
    """The collector-wiring regression is a precondition, not a citation."""
    reasons: list[str] = []
    path = REPO / WIRING_REL
    if not path.is_file():
        return {"ok": False, "reasons": [f"{WIRING_REL} is absent"], "record": None}
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return {"ok": False, "reasons": [f"{WIRING_REL} does not parse: {exc}"],
                "record": None}

    if record.get("ARM_A_COLLECTOR_WIRING_REGRESSION") != "PASS":
        reasons.append(
            f"wiring regression is {record.get('ARM_A_COLLECTOR_WIRING_REGRESSION')}")
    if record.get("EXECUTION_STATUS") != "NOT_RUN" or record.get("arms_executed") != 0:
        reasons.append("the wiring artefact does not declare that no arm ran")
    controls = record.get("selector_wiring_controls", {})
    if not controls.get("PASS"):
        reasons.append("the selector wiring controls did not pass")
    for key in ("A_arm_a_reaches_legacy", "B_arm_b_reaches_interpolated",
                "C_absent_declaration_is_never_treatment",
                "D_unknown_declaration_refused", "F_surface_is_one_method"):
        if controls.get(key) is not True:
            reasons.append(f"wiring control {key} is {controls.get(key)!r}")
    traces = record.get("regression", {}).get("traces", {})
    if not traces:
        reasons.append("no wiring regression traces are bound")
    for name, trace in traces.items():
        if trace.get("steps_evaluated") != EXPECTED_RECORDED_STEPS:
            reasons.append(f"trace {name} evaluated {trace.get('steps_evaluated')} steps")
        if sum(trace.get("mismatches_by_channel", {}).values()) != 0:
            reasons.append(f"trace {name} reports mismatches")
    if record.get("controller_identity", {}).get("sha256") != CONTROL_SHA256:
        reasons.append("the wiring regression ran against a different controller than V5 pins")
    return {"ok": not reasons, "reasons": reasons, "record": record}


def measure_transitions(contract: dict[str, Any]) -> dict[str, Any]:
    """What actually moved between V4 and V5, measured rather than prescribed."""
    v4 = json.loads((REPO / V4_REL).read_text())[
        "EXECUTION_ENVIRONMENT_IDENTITY_V4"]["frozen_contract_values"]
    changed: dict[str, Any] = {}
    added: dict[str, Any] = {}
    for field, value in contract.items():
        if field not in v4:
            added[field] = value
        elif v4[field] != value:
            changed[field] = {"V4": v4[field], "V5": value}
    unchanged = [f for f in contract if f in v4 and v4[f] == contract[f]]
    return {"changed": changed, "added": added, "unchanged_field_count": len(unchanged)}


def build_payload(amended_at: str, wiring: dict[str, Any], readiness: dict[str, Any],
                  contract: dict[str, Any]) -> dict[str, Any]:
    wiring_record = wiring["record"]
    transitions = measure_transitions(contract)
    v4 = json.loads((REPO / V4_REL).read_text())
    treatment = json.loads((REPO / TREATMENT_REL).read_text())
    gap = json.loads((REPO / GAP_REL).read_text())
    prereg = json.loads((REPO / PREREG_REL).read_text())

    reasons = {
        "scientific_code.collect_sha256": (
            "the collector now resolves a declared target selector and passes it to "
            "the tracker, which is what makes an arm requestable at all"),
        "scientific_code.target_selection_sha256": (
            "the selector registry and resolver were added so a declared identity "
            "maps to an implementation, with an unknown name refused"),
    }

    return {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V5",
        "artifact_semantics": "AMENDMENT_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "amendment_id": AMENDMENT_ID,
        "amendment_version": AMENDMENT_VERSION,
        "amended_at_utc": amended_at,
        "STATUS": "FROZEN",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "authorisation": "NOT AUTHORISED. Neither arm may run under this amendment.",
        "authoritative_intervention_contract": "V5",
        "amends": {
            "predecessor": {"path": V4_REL, "sha256": V4_SHA256, "version": "V4"},
            "original_preregistration": {
                "path": PREREG_REL, "sha256": PREREG_SHA256, "version": "V1"},
            "append_only": True,
            "v1_v2_v3_v4_rewritten": False,
            "reason": (
                "V4 pinned a tree that was correct and could not be executed: the "
                "selector was never wired into the collector and no runner existed to "
                "produce the declared outputs. V5 pins the tree that can be invoked"),
            "this_does_not_repair_v4": (
                "V4 remains correct about the tree it froze and must continue to "
                "refuse this one"),
            "the_intervention_design_is_unchanged": True,
            "manipulated_factor": "target selection only",
        },
        "EXECUTION_READINESS_GAP": {
            "record": {"path": GAP_REL, "sha256": sha256_file(REPO / GAP_REL)},
            "classification": gap["classification"],
            "blockers": sorted(gap["blockers"]),
            "not_an_arm_a_failure": gap["THIS_IS_NOT_AN_ARM_A_FAILURE"],
            "manifest_v1_status": gap["manifest_v1_status"],
        },
        "VERSION_CHAIN": [
            {"node": "INTERVENTION_V1", "path": PREREG_REL, "sha256": PREREG_SHA256,
             "timestamp_utc": prereg.get("preregistered_at"), "predecessor": None,
             "reason": "the preregistered one-factor intervention",
             "evidence_basis": "Q2 and Q3 diagnostics"},
            {"node": "ENVIRONMENT_V2",
             "path": "gates/BO10/environment_identity_v2_20260911.json",
             "sha256": sha256_file(REPO / "gates/BO10/environment_identity_v2_20260911.json"),
             "timestamp_utc": json.loads(
                 (REPO / "gates/BO10/environment_identity_v2_20260911.json").read_text()
             )["amended_at_utc"],
             "predecessor": "INTERVENTION_V1",
             "reason": "pin the execution environment and correct the freeze provenance",
             "evidence_basis": "the hash-verified pre-reboot preflight blob"},
            {"node": "TRACKER_INJECTION_EQUIVALENCE",
             "path": "gates/BO10/tracker_injection_equivalence_20260911.json",
             "sha256": sha256_file(
                 REPO / "gates/BO10/tracker_injection_equivalence_20260911.json"),
             "timestamp_utc": json.loads(
                 (REPO / "gates/BO10/tracker_injection_equivalence_20260911.json").read_text()
             )["timestamp_utc"],
             "predecessor": "ENVIRONMENT_V2",
             "reason": "prove the injection seam behaviour-neutral before treatment",
             "evidence_basis": "15 analytic fixtures and 1200 recorded poses"},
            {"node": "ENVIRONMENT_V3",
             "path": "gates/BO10/environment_identity_v3_20260911.json",
             "sha256": sha256_file(REPO / "gates/BO10/environment_identity_v3_20260911.json"),
             "timestamp_utc": json.loads(
                 (REPO / "gates/BO10/environment_identity_v3_20260911.json").read_text()
             )["amended_at_utc"],
             "predecessor": "TRACKER_INJECTION_EQUIVALENCE",
             "reason": "re-pin the controller after the validated seam",
             "evidence_basis": "the bound equivalence artefact"},
            {"node": "TREATMENT_VALIDATION", "path": TREATMENT_REL,
             "sha256": TREATMENT_SHA256, "timestamp_utc": treatment["timestamp_utc"],
             "predecessor": "ENVIRONMENT_V3",
             "reason": "implement and independently validate the preregistered treatment",
             "evidence_basis": "13 hand-computed fixtures and an Arm-A regression"},
            {"node": "ENVIRONMENT_V4", "path": V4_REL, "sha256": V4_SHA256,
             "timestamp_utc": v4["amended_at_utc"], "predecessor": "TREATMENT_VALIDATION",
             "reason": "pin the treatment-capable source state",
             "evidence_basis": "the bound treatment-validation artefact"},
            {"node": "COLLECTOR_WIRING_REGRESSION", "path": WIRING_REL,
             "sha256": sha256_file(REPO / WIRING_REL),
             "timestamp_utc": wiring_record["timestamp_utc"],
             "predecessor": "ENVIRONMENT_V4",
             "reason": "prove collector selector propagation left Arm A unchanged",
             "evidence_basis": f"{EXPECTED_RECORDED_STEPS} recorded poses on two route "
                               "densities against the pre-seam tracker"},
            {"node": "EXECUTABILITY_REPAIR", "path": GAP_REL,
             "sha256": sha256_file(REPO / GAP_REL),
             "timestamp_utc": gap["timestamp_utc"],
             "predecessor": "COLLECTOR_WIRING_REGRESSION",
             "reason": "record the execution-readiness gap and add the runner, "
                       "producer coverage and preflight currency that close it",
             "evidence_basis": "runner resolution, arm dispatch and producer coverage"},
            {"node": "ENVIRONMENT_V5", "path": str(OUT.relative_to(REPO)),
             "sha256": "<this artefact>", "timestamp_utc": amended_at,
             "predecessor": "EXECUTABILITY_REPAIR",
             "reason": "pin the executable scientific code state",
             "evidence_basis": "the bound wiring regression and executability evidence"},
        ],
        "ARM_A_COLLECTOR_WIRING_REGRESSION": {
            "artefact": {"path": WIRING_REL, "sha256": sha256_file(REPO / WIRING_REL)},
            "verdict": wiring_record["ARM_A_COLLECTOR_WIRING_REGRESSION"],
            "implementations_compared": wiring_record["implementations_compared"],
            "pre_seam_reference": wiring_record["pre_seam_reference"],
            "traces": {
                name: {"steps_evaluated": trace["steps_evaluated"],
                       "mismatches_by_channel": trace["mismatches_by_channel"],
                       "verdict": trace["verdict"]}
                for name, trace in wiring_record["regression"]["traces"].items()},
            "selector_wiring_controls": wiring_record["selector_wiring_controls"],
            "CLAIM": (
                "After wiring selector propagation through the collector, no "
                "behavioural difference was detected in the legacy control path over "
                f"the frozen regression domain: {EXPECTED_RECORDED_STEPS} recorded "
                "poses on two route densities, compared against the pre-seam tracker "
                "and against both post-seam legacy constructions"),
            "CLAIM_BOUNDARY": (
                "equivalence over the frozen regression domain. NOT a proof for every "
                "possible input, and nothing at all about runtime behaviour in Isaac"),
        },
        "EXECUTABILITY_EVIDENCE": {
            "EXECUTABILITY": readiness["EXECUTABILITY"],
            "runner_entry_point": readiness["runner_entry_point"],
            "runner_sha256": readiness["runner_sha256"],
            "runner_module": readiness["runner_module"],
            "collector_entry_point": readiness["collector_entry_point"],
            "supported_arms": readiness["supported_arms"],
            "selector_registry": readiness["selector_registry"],
            "arm_dispatch": readiness["arm_dispatch"],
            "producer_coverage": {
                "verdict": readiness["producer_coverage"]["OUTPUT_PRODUCER_COVERAGE"],
                "declared_outputs": readiness["producer_coverage"]["declared_outputs"],
                "mapped_outputs": readiness["producer_coverage"]["mapped_outputs"],
                "outputs_without_a_producer": readiness["producer_coverage"][
                    "outputs_without_a_producer"]},
            "what_distinguishes_v5_from_v4": (
                "V4 was paper-ready and not runnable. These are the structural facts "
                "V4 never established: a runner exists, both arms dispatch, the "
                "selector reaches the collector, and every required output has a "
                "producer"),
            "claim_boundary": readiness["claim_boundary"],
        },
        "SOURCE_IDENTITY_TRANSITIONS_V4_TO_V5": {
            "measured_not_prescribed": True,
            "changed": {
                field: {**values, "reason": reasons.get(field, "measured transition"),
                        "evidence": {"path": WIRING_REL,
                                     "sha256": sha256_file(REPO / WIRING_REL)}}
                for field, values in transitions["changed"].items()},
            "added": {
                field: {"V5": value,
                        "reason": ("the execution machinery decides which selector an "
                                   "arm receives and which artefacts it produces; "
                                   "leaving it unpinned would let the thing performing "
                                   "the experiment change unnoticed"),
                        "evidence": {"path": WIRING_REL,
                                     "sha256": sha256_file(REPO / WIRING_REL)}}
                for field, value in transitions["added"].items()},
            "unchanged_field_count": transitions["unchanged_field_count"],
            "control_py_unchanged_since_v3": CONTROL_SHA256,
        },
        "ONE_FACTOR_EXECUTION_CONTRACT": {
            **v4["ONE_FACTOR_EXECUTION_CONTRACT"],
            "selector_now_reaches_the_collector": True,
            "propagation_path": (
                "manifest arm identity -> runner -> CollectConfig.target_selector -> "
                "resolve_target_selector -> PurePursuit(target_selector=...)"),
        },
        "EXECUTION_ENVIRONMENT_IDENTITY_V5": {
            "contract_version": CONTRACT_VERSION,
            "supersedes": "V4",
            "implementation": "src/navfm/execution_environment.py",
            "frozen_contract_values": contract,
            "contract_digest": digest(contract),
            "contract_critical_fields": list(contract_fields("V5")),
            "fields_added_since_v4": list(V5_ADDITIONAL_CRITICAL_FIELDS),
            "pairwise_critical_fields": list(PAIRWISE_CRITICAL_FIELDS),
            "equality_critical_fields": list(EQUALITY_CRITICAL_FIELDS),
            "observational_fields_recorded_never_compared": list(OBSERVATIONAL_FIELDS),
        },
        "HISTORICAL_CONTRACTS_REMAIN_FROZEN": {
            "v1_v2_v3_v4_rewritten": False,
            "invariants": [
                "V2 accepts its freeze state and rejects the later seam state",
                "V3 accepts its freeze state and rejects the later treatment state",
                "V4 accepts its freeze state and rejects the later wiring state",
                "V5 accepts the final executable state",
            ],
            "required_control": {"current_tree_against_V4": "REFUSE",
                                 "current_tree_against_V5": "PASS"},
        },
        "EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY": v4["EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY"],
        "scene_limitation_carried_forward": v4["scene_limitation_carried_forward"],
        "EXECUTION_MANIFEST": "NOT_FROZEN_BY_THIS_AMENDMENT",
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "milestone_unaffected": v4["milestone_unaffected"],
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
    for rel, expected in ((PREREG_REL, PREREG_SHA256), (V4_REL, V4_SHA256),
                          (TREATMENT_REL, TREATMENT_SHA256)):
        observed = sha256_file(REPO / rel)
        if observed != expected:
            reasons.append(
                f"{rel} sha256 is {str(observed)[:16]}..., expected {expected[:16]}...")
    if reasons:
        return refused("predecessor verification", reasons)

    observed_control = sha256_file(REPO / "src/navfm/control.py")
    if observed_control != CONTROL_SHA256:
        return refused("source identity", [
            f"control.py is {str(observed_control)[:16]}..., V5 pins "
            f"{CONTROL_SHA256[:16]}.... The controller must not change in this tranche"])

    wiring = verify_wiring()
    if not wiring["ok"]:
        return refused("wiring regression verification", wiring["reasons"])

    head = _git("rev-parse", "HEAD")
    manifest = build_manifest(
        REPO, head=head, frozen_at_utc="1970-01-01T00:00:00+00:00")
    readiness = executability(manifest, REPO)
    if readiness["EXECUTABILITY"] != "PASS":
        unmet = [k for k, v in readiness.items() if isinstance(v, bool) and not v]
        return refused("executability", [f"unmet structural facts: {unmet}"])

    contract = select(capture(REPO), contract_fields("V5"))

    if OUT.exists():
        prior = json.loads(OUT.read_text())
        amended_at = str(prior["amended_at_utc"])
        result = build_payload(amended_at, wiring, readiness, contract)
        drift = diff_paths(strip_volatile(result), strip_volatile(prior))
        if drift:
            shown = "\n  ".join(drift[:25]) + ("\n  ..." if len(drift) > 25 else "")
            return refused("canonical regeneration", [
                f"the canonical amendment no longer matches {OUT.relative_to(REPO)}. "
                f"Fields that differ ({len(drift)}):\n  {shown}",
                "V5 is frozen and cited by hash. A changed contract or evidence basis "
                "requires an explicit V6 amendment at a new path"])
        refrozen = False
    else:
        amended_at = _dt.datetime.now(_dt.UTC).isoformat()
        result = build_payload(amended_at, wiring, readiness, contract)
        refrozen = True

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    for key in ("ARM_A_COLLECTOR_WIRING_REGRESSION", "EXECUTABILITY_EVIDENCE",
                "VERSION_CHAIN", "SOURCE_IDENTITY_TRANSITIONS_V4_TO_V5",
                "EXECUTION_STATUS"):
        if key not in back:
            return refused("evidence guard", [f"missing {key} after write"])
    if back["EXECUTION_STATUS"] != "NOT_RUN":
        return refused("evidence guard", ["no arm has run and the artefact must say so"])

    return {"V5_AMENDMENT": "FROZEN", "refrozen": refrozen, "payload": back,
            "sha256": sha256_file(OUT), "canonical_digest": digest(strip_volatile(back))}


def main() -> int:
    outcome = freeze()
    if outcome["V5_AMENDMENT"] != "FROZEN":
        print(f"V5_AMENDMENT = {outcome['V5_AMENDMENT']}")
        print(f"stage        : {outcome['stage']}")
        for reason in outcome["reasons"]:
            print(f"  - {reason}")
        return 1

    payload = outcome["payload"]
    transitions = payload["SOURCE_IDENTITY_TRANSITIONS_V4_TO_V5"]
    print("=" * 68)
    print("TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V5")
    print("=" * 68)
    print(f"HEAD                {_git('rev-parse', 'HEAD')[:12]}")
    print(f"predecessor         V4 {V4_SHA256[:16]}...")
    print(f"wiring regression   {payload['ARM_A_COLLECTOR_WIRING_REGRESSION']['verdict']}")
    print(f"executability       {payload['EXECUTABILITY_EVIDENCE']['EXECUTABILITY']}")
    print()
    print("V4 -> V5 transitions (measured):")
    for field, values in transitions["changed"].items():
        print(f"  changed {field}")
        print(f"          {values['V4'][:24]}... -> {values['V5'][:24]}...")
    for field in transitions["added"]:
        print(f"  added   {field}")
    print(f"  unchanged fields    {transitions['unchanged_field_count']}")
    print()
    print(f"contract fields     {len(contract_fields('V5'))} "
          f"(V4 had {len(contract_fields('V4'))})")
    print(f"contract digest     {payload['EXECUTION_ENVIRONMENT_IDENTITY_V5']['contract_digest']}")
    print(f"canonical digest    {outcome['canonical_digest']}")
    print(f"{'FROZEN (first write)' if outcome['refrozen'] else 'RE-VERIFIED (unchanged)'}")
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {outcome['sha256']}")
    print("V5_AMENDMENT        FROZEN")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
