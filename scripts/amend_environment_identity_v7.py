"""TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V7 -- append-only.

V6 pinned a tree in which the arm lifecycle was walked end to end, every
required producer was invoked in order, and eight fault-injection controls
fired. All of that was true, and all of it was measured through the rehearsal
adapter. The manifest declared

    "real_adapter": "navfm.arm_lifecycle:IsaacRuntimeAdapter"

while nothing in the repository constructed that class and ``mode="REAL"`` was
passed nowhere, so the canonical Arm-A invocation could only return a structured
refusal. The gate said READY_FOR_ARM_A_ATTEMPT about a path that did not exist.

That is the V2 producer-coverage defect one layer up. Producer coverage learned
that a name is not a call; the adapter had to learn it again. V7 pins the first
tree where the authorised entry point actually constructs the real adapter and
enters the real lifecycle.

V6 is not repaired and not rewritten. It remains correct about the tree it
froze -- a tree whose rehearsal genuinely passed -- and it must continue to
refuse this one.

V7 still does not establish that Isaac launches. It moves the boundary from
"the real path does not exist" to "the real path is entered", which is LEVEL
4.5. LEVEL 5 is reached only by an actual attempt.
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

AMENDMENT_ID = "TAI-V1-A7-ENV"
AMENDMENT_VERSION = "V7"
OUT = REPO / "gates/BO10/environment_identity_v7_20260917.json"

PREREG_REL = "gates/BO10/terminal_approach_intervention_v1_20260911.json"
V6_REL = "gates/BO10/environment_identity_v6_20260912.json"
REACHABILITY_REL = "gates/BO10/real_mode_reachability_20260917.json"
RUNNER_REL = "scripts/run_terminal_approach_intervention.py"

PREREG_SHA256 = "941e44da35c8a4145fa4154d1c82deb53da2ef76f04d649789946cc2c3825b4d"
CONTROL_SHA256 = "679cd60f86ea2b84e4f8fe93cd464a8484bee69204f6716a62f3adb05d04abc6"
V6_FREEZE_COMMIT = "356ef56cee20e2d82e5275e8316d9d3158fbd665"


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def refused(stage: str, reasons: list[str]) -> dict[str, Any]:
    return {"V7_AMENDMENT": "REFUSED", "stage": stage, "reasons": reasons,
            "note": ("V7 is not written. The amendment declines rather than raising, "
                     "so the refusal is a recorded scientific result")}


def verify_reachability() -> dict[str, Any]:
    """The reachability evidence is a precondition of V7, not a citation in it."""
    path = REPO / REACHABILITY_REL
    if not path.is_file():
        return {"ok": False, "reasons": [f"{REACHABILITY_REL} is absent"],
                "record": None}
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return {"ok": False, "reasons": [f"{REACHABILITY_REL} does not parse: {exc}"],
                "record": None}

    reasons: list[str] = []
    if record.get("REAL_MODE_REACHABILITY") != "PASS":
        reasons.append(f"reachability is {record.get('REAL_MODE_REACHABILITY')}")
    if record.get("EXECUTION_STATUS") != "NOT_RUN" or record.get("arms_executed") != 0:
        reasons.append("the reachability artefact does not declare that no arm ran")
    if record.get("isaac_launched") is not False:
        reasons.append("the reachability artefact does not declare Isaac stayed down")

    structural = record.get("structural", {})
    if structural.get("REAL_MODE_STRUCTURAL_REACHABILITY") != "PASS":
        reasons.append("structural reachability did not pass")
    if structural.get("defaults_to_real_adapter") is not True:
        reasons.append("the entry point does not default to the real adapter")
    if structural.get("runtime_factory_not_on_command_line") is not True:
        reasons.append("the runtime factory is reachable from the command line")

    probe = record.get("probe", {})
    if probe.get("REAL_MODE_ENTRYPOINT_REACHABILITY") != "PASS":
        reasons.append("the real-mode probe did not pass")
    if probe.get("mode_entered") != "REAL":
        reasons.append(f"the probe entered mode {probe.get('mode_entered')!r}")
    if probe.get("real_adapter_instantiated") is not True:
        reasons.append("the probe did not observe the adapter being constructed")
    if probe.get("refused_at_stage") != "MANIFEST_VALIDATED":
        reasons.append(
            f"the probe refused at {probe.get('refused_at_stage')!r}; it must stop "
            "before the stage that writes a capture")
    if probe.get("production_labels_present"):
        reasons.append(f"a production label appeared: {probe['production_labels_present']}")

    controls = record.get("negative_controls", {})
    if controls.get("verdict") != "PASS":
        reasons.append("the reachability controls did not all fire")
    for name, result in controls.get("results", {}).items():
        if not result.get("DETECTED"):
            reasons.append(f"negative control {name} did not fire")

    return {"ok": not reasons, "reasons": reasons, "record": record}


def measure_transitions(contract: dict[str, Any]) -> dict[str, Any]:
    """What moved between V6 and V7, measured rather than asserted."""
    prior = json.loads((REPO / V6_REL).read_text())
    before = prior["EXECUTION_ENVIRONMENT_IDENTITY_V6"]["frozen_contract_values"]
    changed: dict[str, Any] = {}
    added: dict[str, Any] = {}
    for field, value in contract.items():
        if field not in before:
            added[field] = {"V7": value}
        elif before[field] != value:
            changed[field] = {"V6": before[field], "V7": value}
    unchanged = [f for f in contract if f in before and before[f] == contract[f]]
    return {
        "measured_not_prescribed": True,
        "changed": changed,
        "added": added,
        "unchanged_field_count": len(unchanged),
        "expected_change": {
            "scientific_code.arm_runner_sha256": (
                "the runner gained run_real_arm, the entry point that constructs "
                "IsaacRuntimeAdapter and enters mode=REAL. This is the defect V7 "
                "exists to close"),
            "scientific_code.intervention_runner_sha256": (
                "the manifest-version dispatch table gained EXECUTION_MANIFEST_V4, "
                "and the set of versions whose validators assert readiness facts is "
                "now named once rather than compared against a literal in two places"),
            "scientific_code.arm_lifecycle_sha256": (
                "_validate_manifest reads that set instead of testing for V3 by name. "
                "The literal was already missed once when V3 arrived, which made the "
                "lifecycle refuse the very manifest whose readiness it had measured"),
        },
        "what_did_not_change": (
            "the controller, the selectors, the collector and the preregistration. "
            "The manipulated factor is untouched by this tranche"),
    }


def build_payload(amended_at: str, reachability: dict[str, Any],
                  contract: dict[str, Any]) -> dict[str, Any]:
    record = reachability["record"]
    return {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V7",
        "artifact_semantics": "AMENDMENT_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "amendment_id": AMENDMENT_ID,
        "amendment_version": AMENDMENT_VERSION,
        "amended_at_utc": amended_at,
        "STATUS": "FROZEN",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "authorisation": "NOT AUTHORISED. Neither arm may run under this amendment.",
        "authoritative_intervention_contract": "V7",
        "amends": {
            "predecessor": {"path": V6_REL, "sha256": sha256_file(REPO / V6_REL),
                            "version": "V6"},
            "original_preregistration": {
                "path": PREREG_REL, "sha256": sha256_file(REPO / PREREG_REL),
                "version": "V1"},
            "append_only": True,
            "v1_to_v6_rewritten": False,
            "reason": (
                "V6 pinned a tree whose rehearsal passed end to end and whose real "
                "path did not exist: the adapter was named in the manifest and "
                "constructed nowhere. V7 pins the first tree where the authorised "
                "entry point builds it and enters mode=REAL"),
            "this_does_not_repair_v6": (
                "V6 remains correct about the tree it froze and must continue to "
                "refuse this one"),
            "the_intervention_design_is_unchanged": True,
            "manipulated_factor": "target selection only",
        },
        "REAL_MODE_UNREACHABLE_FROM_ENTRYPOINT": {
            "classification": "REAL_MODE_UNREACHABLE_FROM_ENTRYPOINT",
            "observed_at": V6_FREEZE_COMMIT,
            "observed": {
                "manifest_declared_real_adapter": True,
                "adapter_class_implemented": True,
                "adapter_ever_constructed": False,
                "mode_real_passed_anywhere": False,
                "canonical_arm_a_invocation_exit_code": 2,
            },
            "why_the_gate_missed_it": (
                "every readiness level was measured through the rehearsal adapter, "
                "because the tranche that built the instrument was forbidden from "
                "starting Isaac. Nothing asked whether REAL had an entry point"),
            "readiness_hierarchy": [
                "COMPONENT_RESOLUTION does not imply ENTRYPOINT_REACHABILITY",
                "rehearsal reachability does not imply REAL-mode reachability",
                "REAL-mode reachability does not imply RUNTIME_EXECUTION",
            ],
            "attempted_arm_a_authorisation": "AUTHORISED_BUT_NOT_STARTED",
            "explicitly_not": "ARM_A_FAILED",
            "evidence": {
                "pre_arm_a_created": False, "post_arm_a_created": False,
                "isaac_started": False, "traceback": False,
                "partial_scientific_artefacts": False,
            },
        },
        "REAL_MODE_REACHABILITY_EVIDENCE": {
            "artefact": {"path": REACHABILITY_REL,
                         "sha256": sha256_file(REPO / REACHABILITY_REL)},
            "verdict": record["REAL_MODE_REACHABILITY"],
            "READINESS_LEVEL": record["READINESS_LEVEL"],
            "entry_point": record["structural"]["entry_point"],
            "real_adapter": record["structural"]["real_adapter"],
            "mode_entered": record["probe"]["mode_entered"],
            "real_adapter_instantiated": record["probe"]["real_adapter_instantiated"],
            "refused_at_stage": record["probe"]["refused_at_stage"],
            "production_labels_present": record["probe"]["production_labels_present"],
            "negative_controls": {
                name: result["DETECTED"]
                for name, result in record["negative_controls"]["results"].items()},
            "CLAIM": record["probe"]["CLAIM"],
            "CLAIM_BOUNDARY": record["probe"]["CLAIM_BOUNDARY"],
        },
        "VERSION_CHAIN": [
            {"node": "ENVIRONMENT_V6", "path": V6_REL,
             "sha256": sha256_file(REPO / V6_REL), "predecessor": "ENVIRONMENT_V5",
             "reason": "pinned the tree whose arm lifecycle is walked in rehearsal"},
            {"node": "REAL_MODE_UNREACHABLE_FROM_ENTRYPOINT",
             "predecessor": "ENVIRONMENT_V6",
             "reason": ("the real adapter was declared and never constructed, so the "
                        "canonical Arm-A invocation could only refuse")},
            {"node": "REAL_MODE_REACHABILITY_EVIDENCE", "path": REACHABILITY_REL,
             "sha256": sha256_file(REPO / REACHABILITY_REL),
             "predecessor": "REAL_MODE_UNREACHABLE_FROM_ENTRYPOINT",
             "reason": "the entry point now builds the adapter and enters mode=REAL"},
            {"node": "ENVIRONMENT_V7", "predecessor": "REAL_MODE_REACHABILITY_EVIDENCE",
             "reason": "pins the first tree where the real path is reachable"},
        ],
        "SOURCE_IDENTITY_TRANSITIONS_V6_TO_V7": measure_transitions(contract),
        "EXECUTION_ENVIRONMENT_IDENTITY_V7": {
            "contract_version": "EXECUTION_ENVIRONMENT_IDENTITY_V2",
            "supersedes": "V6",
            "implementation": "src/navfm/execution_environment.py",
            "frozen_contract_values": contract,
            "field_count": len(contract),
            "contract_digest": digest(contract),
            "runner": {"path": RUNNER_REL, "sha256": sha256_file(REPO / RUNNER_REL)},
        },
        "HISTORICAL_CONTRACTS_REMAIN_FROZEN": {
            "v1_to_v6_rewritten": False,
            "required_control": {
                "current_tree_against_V6": "REFUSE",
                "current_tree_against_V7": "PASS",
            },
        },
        "READINESS_MODEL": {
            "LEVEL_1_COMPONENT_RESOLUTION": "established",
            "LEVEL_2_ENTRYPOINT_REACHABILITY": "established",
            "LEVEL_3_NON_ISAAC_LIFECYCLE_REHEARSAL": "established",
            "LEVEL_4_CURRENT_PREFLIGHT_AND_ENVIRONMENT": "established at manifest freeze",
            "LEVEL_4_5_REAL_MODE_ENTRYPOINT_REACHABILITY": "established by V7",
            "LEVEL_5_REAL_RUNTIME_ATTEMPT": "NOT established, and not establishable here",
            "why_level_4_5_exists": (
                "three authorisations were spent discovering that rehearsal "
                "reachability is not real reachability. The rung is checkable "
                "without starting Isaac, and its absence is what let a gate report "
                "READY for a path that did not exist"),
        },
        "EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY": (
            "the authorised entry point constructs the real adapter and enters the "
            "real lifecycle. It does not establish that the PRE capture succeeds, "
            "that Isaac launches, that the Hospital scene loads, that the render loop "
            "runs, or that the collector completes. The first arm execution is what "
            "would establish runtime execution evidence"),
        "EXECUTION_MANIFEST": "NOT_FROZEN_BY_THIS_AMENDMENT",
        "ARM_A_EXECUTION": "NOT_STARTED",
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
    reasons: list[str] = []
    observed_prereg = sha256_file(REPO / PREREG_REL)
    if observed_prereg != PREREG_SHA256:
        reasons.append(
            f"{PREREG_REL} sha256 is {str(observed_prereg)[:16]}..., expected "
            f"{PREREG_SHA256[:16]}...")
    if reasons:
        return refused("predecessor verification", reasons)

    observed_control = sha256_file(REPO / "src/navfm/control.py")
    if observed_control != CONTROL_SHA256:
        return refused("source identity", [
            f"control.py is {str(observed_control)[:16]}..., V7 pins "
            f"{CONTROL_SHA256[:16]}.... The controller must not change in this tranche"])

    reachability = verify_reachability()
    if not reachability["ok"]:
        return refused("real-mode reachability verification", reachability["reasons"])

    contract = select(capture(REPO), contract_fields("V7"))

    if OUT.exists():
        prior = json.loads(OUT.read_text())
        amended_at = str(prior["amended_at_utc"])
        result = build_payload(amended_at, reachability, contract)
        drift = diff_paths(strip_volatile(result), strip_volatile(prior))
        if drift:
            shown = "\n  ".join(drift[:25]) + ("\n  ..." if len(drift) > 25 else "")
            return refused("canonical regeneration", [
                f"the canonical amendment no longer matches {OUT.relative_to(REPO)}. "
                f"Fields that differ ({len(drift)}):\n  {shown}",
                "V7 is frozen and cited by hash; a change requires an explicit V8"])
        refrozen = False
    else:
        amended_at = _dt.datetime.now(_dt.UTC).isoformat()
        result = build_payload(amended_at, reachability, contract)
        refrozen = True

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    for key in ("REAL_MODE_UNREACHABLE_FROM_ENTRYPOINT",
                "REAL_MODE_REACHABILITY_EVIDENCE", "VERSION_CHAIN",
                "SOURCE_IDENTITY_TRANSITIONS_V6_TO_V7", "EXECUTION_STATUS"):
        if key not in back:
            return refused("evidence guard", [f"missing {key} after write"])
    if back["EXECUTION_STATUS"] != "NOT_RUN":
        return refused("evidence guard", ["no arm has run and the artefact must say so"])

    return {"V7_AMENDMENT": "FROZEN", "refrozen": refrozen, "payload": back,
            "sha256": sha256_file(OUT), "canonical_digest": digest(strip_volatile(back))}


def main() -> int:
    print("=" * 70)
    print("TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V7")
    print("=" * 70)
    print(f"HEAD                {_git('rev-parse', 'HEAD')[:12]}")

    outcome = freeze()
    if outcome["V7_AMENDMENT"] != "FROZEN":
        print(f"V7_AMENDMENT = REFUSED\nstage        : {outcome['stage']}")
        for reason in outcome["reasons"]:
            print(f"  - {reason}")
        return 1

    payload = outcome["payload"]
    transitions = payload["SOURCE_IDENTITY_TRANSITIONS_V6_TO_V7"]
    print()
    print("V6 -> V7 transitions (measured):")
    for field in transitions["changed"]:
        print(f"  changed {field}")
    for field in transitions["added"]:
        print(f"  added   {field}")
    print(f"  unchanged fields    {transitions['unchanged_field_count']}")
    print()
    evidence = payload["REAL_MODE_REACHABILITY_EVIDENCE"]
    print(f"entry point         {evidence['entry_point']}")
    print(f"mode entered        {evidence['mode_entered']}")
    print(f"adapter built       {evidence['real_adapter_instantiated']}")
    print(f"refused at          {evidence['refused_at_stage']}")
    print(f"contract fields     {payload['EXECUTION_ENVIRONMENT_IDENTITY_V7']['field_count']}")
    print(f"contract digest     {payload['EXECUTION_ENVIRONMENT_IDENTITY_V7']['contract_digest']}")
    print(f"canonical digest    {outcome['canonical_digest']}")
    print("FROZEN (first write)" if outcome["refrozen"] else "unchanged (idempotent)")
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {outcome['sha256']}")
    print("V7_AMENDMENT        FROZEN")
    print("LEVEL_5             NOT_ESTABLISHED")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
