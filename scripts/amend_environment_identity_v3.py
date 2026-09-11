"""TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V3: re-pin after the seam.

V2 pinned ``control.py`` by content hash so that a change to the controller
would be impossible to miss. The tracker-injection seam then changed it, and V2
did exactly what it was built to do: it refuses, and it still refuses. This
amendment does not repair that refusal. It supersedes V2 for future execution
and records why the newer source state is admissible.

The claim being retired is "control.py is byte-identical to the V2 freeze". It
was true, it is now false, and concealing that by quietly rewriting V2's hash
would destroy the only evidence that the controller ever moved.

The claim replacing it is narrower and carries its own evidence: the controller
source changed solely to introduce the preregistered injection seam, and the
default and explicitly-injected legacy paths were shown behaviourally
equivalent to the pre-seam tracker before any treatment selector existed. That
ordering is the point. A re-pin written after the treatment had landed would
bundle the neutral refactor and the manipulated factor into one justification,
and no later reader could separate what the equivalence proof actually covered.

V3 is not permission to reopen V2 generally. The kernel, driver, holds,
interpreter, Isaac, scene, runtime contract and every policy carry forward
untouched; one field moves, one is added, and both are accounted for.
"""

from __future__ import annotations

import ast
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
    V3_ADDITIONAL_CRITICAL_FIELDS,
    capture,
    contract_fields,
    digest,
    select,
    sha256_file,
)

AMENDMENT_ID = "TAI-V1-A3-ENV"
AMENDMENT_VERSION = "V3"
OUT = REPO / "gates/BO10/environment_identity_v3_20260911.json"

PREREG_REL = "gates/BO10/terminal_approach_intervention_v1_20260911.json"
V2_REL = "gates/BO10/environment_identity_v2_20260911.json"
EQUIVALENCE_REL = "gates/BO10/tracker_injection_equivalence_20260911.json"
CONTROL_REL = "src/navfm/control.py"
SEAM_REL = "src/navfm/target_selection.py"

# Pinned predecessors. Each is verified by hash before V3 will freeze.
PREREG_SHA256 = "941e44da35c8a4145fa4154d1c82deb53da2ef76f04d649789946cc2c3825b4d"
V2_SHA256 = "d664388997dcec8014a1fd598bf315a0ef76cad4d9e679b0a248c67650d4a16a"
EQUIVALENCE_SHA256 = "ff0cd687a9b6c7a1b5c0bb88f5f23eb6dead6cdf365860e452f15d0a7e62a52b"

#: What V2 froze, and what the seam moved it to.
V2_CONTROL_SOURCE_IDENTITY = (
    "f5992b60564de9a8928fc1ade70655c882f0b19aae8c48a5d085a4c78fcae074")
V3_CONTROL_SOURCE_IDENTITY = (
    "679cd60f86ea2b84e4f8fe93cd464a8484bee69204f6716a62f3adb05d04abc6")

SEAM_COMMITS = (
    "a869729c0614991a114e9d241713eead31faa38d",
    "033e52a7c2350fc5b89508cf630f965088140a34",
)

EXPECTED_RECORDED_STEPS = 1200
EXPECTED_FIXTURES = 15


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def refused(stage: str, reasons: list[str]) -> dict[str, Any]:
    """A structured refusal. A refusal path that crashes has not refused."""
    return {
        "V3_AMENDMENT": "REFUSED",
        "stage": stage,
        "reasons": reasons,
        "note": (
            "V3 is not written. The amendment declines rather than raising, so the "
            "refusal is a recorded scientific result instead of a traceback"
        ),
    }


def _base_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
        elif isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name):
            names.add(base.value.id)
    return names


def selectors_defined_in_source() -> dict[str, list[str]]:
    """Every class under src/ that declares ``select_target``, split by kind.

    Parsed rather than imported: importing would run module-level code, and the
    question is what the source declares, not what happens to be importable.

    The interface declaration is separated from concrete implementations.
    ``TargetSelector`` is a Protocol -- it defines the seam rather than
    occupying it -- so counting it as a selector would make the treatment-absence
    check refuse forever and mean nothing.
    """
    concrete: list[str] = []
    protocols: list[str] = []
    for path in sorted((REPO / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(
                isinstance(item, ast.FunctionDef) and item.name == "select_target"
                for item in node.body
            ):
                continue
            qualified = f"{path.relative_to(REPO)}::{node.name}"
            if "Protocol" in _base_names(node):
                protocols.append(qualified)
            else:
                concrete.append(qualified)
    return {"concrete": concrete, "protocols": protocols}


def verify_treatment_absent() -> dict[str, Any]:
    """Is the seam still empty of the manipulated factor at freeze time?"""
    declared = selectors_defined_in_source()
    selectors = declared["concrete"]
    legacy_only = selectors == [f"{SEAM_REL}::LegacyVertexTargetSelector"]
    import numpy as np

    from navfm.control import PurePursuit
    from navfm.target_selection import LegacyVertexTargetSelector

    default = PurePursuit(np.array([[0.0, 0.0], [1.0, 0.0]]))._selector
    default_is_legacy = isinstance(default, LegacyVertexTargetSelector)
    return {
        "TREATMENT_SELECTOR_IMPLEMENTED": not legacy_only,
        "ARC_LENGTH_INTERPOLATED_TARGET_SELECTOR": (
            "NOT_PRESENT_BEHIND_INJECTION_SEAM" if legacy_only else "PRESENT"
        ),
        "concrete_selectors_declared_under_src": selectors,
        "selector_protocols_declared_under_src": declared["protocols"],
        "default_selector_is_legacy": default_is_legacy,
        "method": (
            "AST scan for classes declaring select_target, with Protocol bases "
            "classified separately because the interface defines the seam rather "
            "than occupying it, plus a check on the default instance"
        ),
        "pre_existing_subclass_note": (
            "navfm.collection.interpolated_target.InterpolatedLookaheadPursuit exists "
            "from an earlier tranche and overrides PurePursuit.target by subclassing. "
            "It is NOT a TargetSelector and does not occupy the injection seam. "
            "Stating this precisely matters: the claim is that the seam is empty, not "
            "that no interpolated code exists anywhere in the repository"
        ),
        "ok": legacy_only and default_is_legacy,
    }


def verify_equivalence() -> dict[str, Any]:
    """The proof is a precondition, not a citation.

    Every field checked here is read from the artefact and compared against what
    the amendment claims it says. Binding a PASS without binding the counts that
    earned it would let a later, weaker proof inherit this amendment's authority.
    """
    reasons: list[str] = []
    path = REPO / EQUIVALENCE_REL
    if not path.is_file():
        return {"ok": False, "reasons": [f"{EQUIVALENCE_REL} is absent"], "record": None}
    observed_sha = sha256_file(path)
    if observed_sha != EQUIVALENCE_SHA256:
        reasons.append(
            f"equivalence artefact sha256 is {str(observed_sha)[:16]}..., expected "
            f"{EQUIVALENCE_SHA256[:16]}..."
        )
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return {"ok": False, "reasons": [f"{EQUIVALENCE_REL} does not parse: {exc}"],
                "record": None}

    if record.get("ARM_A_LEGACY_INJECTION_EQUIVALENCE") != "PASS":
        reasons.append(
            f"equivalence verdict is {record.get('ARM_A_LEGACY_INJECTION_EQUIVALENCE')}")
    if record.get("EXECUTION_STATUS") != "NOT_RUN" or record.get("arms_executed") != 0:
        reasons.append("the equivalence artefact does not declare that no arm ran")
    if record.get("repository_head") not in SEAM_COMMITS:
        reasons.append(
            f"the proof ran at {str(record.get('repository_head'))[:12]}, which is not "
            f"one of the seam commits {[c[:12] for c in SEAM_COMMITS]}"
        )

    fixtures = record.get("analytic_fixtures", {})
    if fixtures.get("verdict") != "PASS":
        reasons.append(f"analytic fixtures verdict is {fixtures.get('verdict')}")
    if fixtures.get("count") != EXPECTED_FIXTURES:
        reasons.append(
            f"{fixtures.get('count')} analytic fixtures, expected {EXPECTED_FIXTURES}")
    if fixtures.get("max_numerical_difference") != 0.0:
        reasons.append("analytic fixtures did not achieve exact equality")

    recorded = record.get("recorded_pose_equivalence", {})
    if recorded.get("verdict") != "PASS":
        reasons.append(f"recorded-pose verdict is {recorded.get('verdict')}")
    traces = recorded.get("traces", {})
    if not traces:
        reasons.append("no recorded-pose traces are bound")
    for name, trace in traces.items():
        if trace.get("steps_evaluated") != EXPECTED_RECORDED_STEPS:
            reasons.append(
                f"trace {name} evaluated {trace.get('steps_evaluated')} steps, expected "
                f"{EXPECTED_RECORDED_STEPS}")
        if trace.get("mismatch_total") != 0:
            reasons.append(f"trace {name} reports {trace.get('mismatch_total')} mismatches")

    controls = record.get("negative_controls", {})
    if controls.get("verdict") != "PASS":
        reasons.append("negative controls did not all fire")
    if not controls.get("state_drift_detected_on_index_after"):
        reasons.append("the state-drift control did not fire on index_after")

    invariance = record.get("control_law_invariance", {})
    if invariance.get("CONTROL_LAW_INVARIANCE") != "PASS":
        reasons.append("laws outside the seam are not shown unchanged")

    if record.get("controller_identity", {}).get("current_sha256") != V3_CONTROL_SOURCE_IDENTITY:
        reasons.append(
            "the proof was run against a different control.py than V3 is pinning")
    if record.get("pre_seam_reference", {}).get("sha256") != V2_CONTROL_SOURCE_IDENTITY:
        reasons.append(
            "the proof's pre-seam reference is not the source V2 froze")

    return {"ok": not reasons, "reasons": reasons, "record": record}


def mismatch_summary(record: dict[str, Any]) -> dict[str, Any]:
    totals: dict[str, int] = {}
    for trace in record.get("recorded_pose_equivalence", {}).get("traces", {}).values():
        for channel, count in trace.get("mismatches_by_channel", {}).items():
            totals[channel] = totals.get(channel, 0) + int(count)
    return {
        "target_mismatch_count": totals.get("target_x", 0) + totals.get("target_y", 0),
        "state_mismatch_count": totals.get("index_after", 0) + totals.get("finished_after", 0),
        "command_mismatch_count": (
            totals.get("vx", 0) + totals.get("vy", 0) + totals.get("wz", 0)),
        "predicate_mismatch_count": totals.get("done", 0) + totals.get("finished_after", 0),
        "per_channel": totals,
    }


def build_payload(amended_at: str, equivalence: dict[str, Any],
                  contract: dict[str, Any]) -> dict[str, Any]:
    record = equivalence["record"]
    treatment = verify_treatment_absent()
    summary = mismatch_summary(record)
    v2 = json.loads((REPO / V2_REL).read_text())

    return {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V3",
        "artifact_semantics": "AMENDMENT_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "amendment_id": AMENDMENT_ID,
        "amendment_version": AMENDMENT_VERSION,
        "amended_at_utc": amended_at,
        "STATUS": "FROZEN",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "authorisation": "NOT AUTHORISED. Neither arm may run under this amendment.",
        "authoritative_contract_for_future_arms": "V3",
        "amends": {
            "predecessor": {"path": V2_REL, "sha256": V2_SHA256, "version": "V2"},
            "original_preregistration": {
                "path": PREREG_REL, "sha256": PREREG_SHA256, "version": "V1"},
            "append_only": True,
            "v1_and_v2_rewritten": False,
            "reason": (
                "a behaviour-neutral dependency-injection seam was intentionally "
                "introduced after V2. This changed the source-byte identity of "
                "control.py while the frozen equivalence experiment demonstrated that "
                "legacy controller behaviour was unchanged"
            ),
            "tracker_injection_commits": list(SEAM_COMMITS),
            "the_intervention_design_is_unchanged": True,
            "unchanged_by_this_amendment": [
                "the target-selection factor", "the route and frozen polyline",
                "the initial pose and start yaw", "the goal and goal tolerance",
                "the seed", "controller gains", "the look-ahead distance",
                "cruise speed and every velocity limit", "max_steps",
                "the primary outcome", "the secondary cross-track outcome",
                "arm order", "the kernel contract", "the NVIDIA driver and module contract",
                "the NVIDIA hold count", "the Python, torch and CUDA identity",
                "the Isaac identity", "the remote Hospital scene limitation",
                "the runtime dt, control rate and limits",
                "the repository identity rules", "the dirty-tree rules",
                "the arm environment-equivalence policy",
            ],
        },
        "SOURCE_IDENTITY_TRANSITION": {
            "V2_CONTROL_SOURCE_IDENTITY": V2_CONTROL_SOURCE_IDENTITY,
            "V3_CONTROL_SOURCE_IDENTITY": V3_CONTROL_SOURCE_IDENTITY,
            "SOURCE_BYTE_IDENTITY_ACROSS_V2_TO_V3": "CHANGED",
            "expected_and_intentional": True,
            "retired_claim": (
                "control.py is byte-identical to the V2 freeze. This was true under V2 "
                "and is now false. It is retired, not concealed: V2 keeps its hash and "
                "continues to refuse the post-seam tree when checked against V2"
            ),
            "replacement_claim": (
                "the controller source changed solely to introduce the preregistered "
                "injection seam, and the legacy default and explicitly injected legacy "
                "paths were demonstrated behaviourally equivalent to the pre-seam "
                "tracker before any treatment selector existed"
            ),
            "what_changed_in_control_py": record["control_law_invariance"][
                "what_changed_in_control_py"],
            "this_is_not_a_claim_of_semantic_equivalence_by_inspection": (
                "no one read the diff and pronounced it harmless. The claim rests on "
                "the frozen behavioural equivalence evidence bound below"
            ),
        },
        "changed_from_v2": {
            "scientific_code.control_sha256": {
                "old": V2_CONTROL_SOURCE_IDENTITY,
                "new": V3_CONTROL_SOURCE_IDENTITY,
                "justification": "tracker injection seam",
                "evidence": {"path": EQUIVALENCE_REL, "sha256": EQUIVALENCE_SHA256},
            },
            "scientific_code.target_selection_sha256": {
                "old": "<NOT_PINNED_BY_V2>",
                "new": contract.get("scientific_code.target_selection_sha256"),
                "justification": (
                    "the seam moved Arm A's default target selection into a module V2 "
                    "could not have pinned. Leaving it unpinned would be a hole opened "
                    "by this very change"
                ),
                "evidence": {"path": EQUIVALENCE_REL, "sha256": EQUIVALENCE_SHA256},
                "field_added_not_replaced": True,
            },
            "no_other_field_changed": True,
            "unexplained_hash_replacements": [],
        },
        "INJECTION_SEAM_BEHAVIOURAL_NEUTRALITY": {
            "status": "PROVEN_OVER_THE_PREREGISTERED_EQUIVALENCE_DOMAIN",
            "proven_by": "ARM_A_LEGACY_INJECTION_EQUIVALENCE",
            "artefact": {
                "path": EQUIVALENCE_REL,
                "sha256": EQUIVALENCE_SHA256,
                "repository_head_used": record["repository_head"],
                "verdict": record["ARM_A_LEGACY_INJECTION_EQUIVALENCE"],
            },
            "implementations_compared": record["implementations"],
            "pre_seam_reference": record["pre_seam_reference"],
            "selector_identity": record["selector_identity"],
            "recorded_step_count": EXPECTED_RECORDED_STEPS,
            "analytic_fixture_count": EXPECTED_FIXTURES,
            "numerical_standard": record["numerical_standard"],
            **summary,
            "negative_controls": record["negative_controls"]["fired"],
            "state_drift_detected_on_index_after": record["negative_controls"][
                "state_drift_detected_on_index_after"],
            "CLAIM": (
                "No behavioural difference was detected over the preregistered "
                "equivalence domain, including all 1200 recorded run_00001 poses and "
                "15 analytic fixtures, across selected targets, target index and "
                "tracker-state evolution, commands and predicates. Equality was exact; "
                "the maximum numerical difference was zero"
            ),
            "CLAIM_BOUNDARY": (
                "this establishes equivalence over the declared analytic fixtures, the "
                "complete available recorded run_00001 pose sequence, the tested "
                "tracker-state evolution and the tested command and predicate surface. "
                "It is not a mathematical proof of equivalence for every possible "
                "future input, and the implementations are NOT claimed to be "
                "universally equivalent"
            ),
        },
        "OUTSIDE_SEAM_LAW_IDENTITY": {
            "verdict": record["control_law_invariance"]["CONTROL_LAW_INVARIANCE"],
            "method": record["control_law_invariance"]["method"],
            "members": record["control_law_invariance"]["members"],
            "file_changed": True,
            "mathematics_outside_seam_changed": False,
            "why_region_hashes_not_a_file_hash": (
                "the laws share the file the seam edited, so the old file hash cannot "
                "be retained and claiming it would be false. What is bound instead is "
                "the source of each law, hashed separately and compared against the "
                "pinned pre-seam module"
            ),
        },
        "TREATMENT_ABSENCE_AT_FREEZE": treatment,
        "causal_chronology": [
            "V2 froze the pre-seam source identity",
            "the injection seam changed control.py",
            "legacy equivalence was demonstrated independently, with no treatment present",
            "V3 records and justifies the source transition",
            "only then may treatment code appear",
        ],
        "why_the_order_matters": (
            "a re-pin written after the treatment had landed would bundle the neutral "
            "refactor and the manipulated factor into a single justification, and no "
            "later reader could separate what the equivalence proof actually covered"
        ),
        "VERSION_CHAIN": [
            {
                "node": "INTERVENTION_V1",
                "path": PREREG_REL,
                "sha256": PREREG_SHA256,
                "timestamp_utc": json.loads(
                    (REPO / PREREG_REL).read_text()).get("preregistered_at"),
                "predecessor": None,
                "reason": "the preregistered one-factor intervention",
                "evidence_basis": "Q2 and Q3 diagnostics",
            },
            {
                "node": "ENVIRONMENT_V2",
                "path": V2_REL,
                "sha256": V2_SHA256,
                "timestamp_utc": v2["amended_at_utc"],
                "predecessor": "INTERVENTION_V1",
                "reason": v2["amends"]["reason"],
                "evidence_basis": "the hash-verified pre-reboot preflight blob",
            },
            {
                "node": "TRACKER_INJECTION_EQUIVALENCE",
                "path": EQUIVALENCE_REL,
                "sha256": EQUIVALENCE_SHA256,
                "timestamp_utc": record["timestamp_utc"],
                "predecessor": "ENVIRONMENT_V2",
                "reason": "prove the injection seam behaviour-neutral before treatment",
                "evidence_basis": (
                    f"{EXPECTED_FIXTURES} analytic fixtures and "
                    f"{EXPECTED_RECORDED_STEPS} recorded poses against the pre-seam "
                    "tracker read from git"
                ),
            },
            {
                "node": "ENVIRONMENT_V3",
                "path": str(OUT.relative_to(REPO)),
                "sha256": "<this artefact>",
                "timestamp_utc": amended_at,
                "predecessor": "TRACKER_INJECTION_EQUIVALENCE",
                "reason": "re-pin scientific-code identity after the validated seam",
                "evidence_basis": "the bound equivalence artefact",
            },
        ],
        "EXECUTION_ENVIRONMENT_IDENTITY_V3": {
            "contract_version": CONTRACT_VERSION,
            "supersedes": "V2",
            "implementation": "src/navfm/execution_environment.py",
            "frozen_contract_values": contract,
            "contract_digest": digest(contract),
            "contract_critical_fields": list(contract_fields("V3")),
            "fields_added_since_v2": list(V3_ADDITIONAL_CRITICAL_FIELDS),
            "pairwise_critical_fields": list(PAIRWISE_CRITICAL_FIELDS),
            "equality_critical_fields": list(EQUALITY_CRITICAL_FIELDS),
            "observational_fields_recorded_never_compared": list(OBSERVATIONAL_FIELDS),
            "arm_to_arm_comparison_unchanged": (
                "the four-way comparator's field set is untouched. Per-file hashes are "
                "not needed there because repository.head plus a clean worktree already "
                "subsumes every source file across the four captures"
            ),
        },
        "V2_REMAINS_VALID_HISTORY": {
            "v2_is_not_rewritten": True,
            "v2_still_refuses_the_post_seam_tree": True,
            "why": (
                "V2 asserted a source identity that was true when it was frozen. "
                "Checking today's tree against V2 must still fail on "
                "scientific_code.control_sha256, or V2 would have been retroactively "
                "weakened and its refusal would have meant nothing"
            ),
            "required_control": {
                "current_repo_against_V2": "REFUSE on control hash",
                "current_repo_against_V3": "PASS if all V3 fields match",
            },
        },
        "EXECUTION_MANIFEST_OWES_ARM_OUTPUT_ALLOWLIST": True,
        "EXECUTION_MANIFEST": "NOT_FROZEN",
        "TREATMENT_SELECTOR": "NOT_IMPLEMENTED",
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "scene_limitation_carried_forward": {
            "scene_asset_identifier_can_be_established": True,
            "scene_byte_identity": "NOT_VERIFIED_REMOTE_STREAMED_ASSET",
            "no_scene_sha_generated": True,
        },
        "milestone_unaffected": {
            "BO-03_REAL_DATA_COMPATIBILITY": "COMPLETE",
            "BO-10_HOSPITAL_COLLECTION": "COMPLETE_FOR_COMPATIBILITY_PURPOSE",
            "run_00001": "IMMUTABLE and excluded from the two-arm comparison",
        },
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
    """Verify every precondition, then write. Refuses rather than raises."""
    reasons: list[str] = []
    for rel, expected in (
        (PREREG_REL, PREREG_SHA256),
        (V2_REL, V2_SHA256),
    ):
        observed = sha256_file(REPO / rel)
        if observed != expected:
            reasons.append(
                f"{rel} sha256 is {str(observed)[:16]}..., expected {expected[:16]}...")
    if reasons:
        return refused("predecessor verification", reasons)

    equivalence = verify_equivalence()
    if not equivalence["ok"]:
        return refused("equivalence verification", equivalence["reasons"])

    treatment = verify_treatment_absent()
    if not treatment["ok"]:
        return refused(
            "treatment absence",
            [
                "a selector other than the legacy one is declared behind the seam: "
                f"{treatment['concrete_selectors_declared_under_src']}. V3 must freeze BEFORE "
                "treatment implementation, or the re-pin bundles the neutral refactor "
                "with the manipulated factor"
            ],
        )

    live_control = sha256_file(REPO / CONTROL_REL)
    if live_control != V3_CONTROL_SOURCE_IDENTITY:
        return refused(
            "control source identity",
            [f"control.py is {str(live_control)[:16]}..., V3 pins "
             f"{V3_CONTROL_SOURCE_IDENTITY[:16]}..."],
        )

    contract = select(capture(REPO), contract_fields("V3"))

    if OUT.exists():
        prior = json.loads(OUT.read_text())
        amended_at = str(prior["amended_at_utc"])
        result = build_payload(amended_at, equivalence, contract)
        drift = diff_paths(strip_volatile(result), strip_volatile(prior))
        if drift:
            shown = "\n  ".join(drift[:25]) + ("\n  ..." if len(drift) > 25 else "")
            return refused(
                "canonical regeneration",
                [f"the canonical amendment no longer matches the frozen artefact at "
                 f"{OUT.relative_to(REPO)}. Fields that differ ({len(drift)}):\n  {shown}",
                 "V3 is frozen and cited by hash. A changed contract or a changed "
                 "evidence basis requires an explicit V4 amendment at a new path, "
                 "leaving this record and its digest intact"],
            )
        refrozen = False
    else:
        amended_at = _dt.datetime.now(_dt.UTC).isoformat()
        result = build_payload(amended_at, equivalence, contract)
        refrozen = True

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    for key in ("SOURCE_IDENTITY_TRANSITION", "INJECTION_SEAM_BEHAVIOURAL_NEUTRALITY",
                "VERSION_CHAIN", "changed_from_v2", "EXECUTION_STATUS"):
        if key not in back:
            return refused("evidence guard", [f"missing {key} after write"])
    if back["EXECUTION_STATUS"] != "NOT_RUN":
        return refused("evidence guard", ["no arm has run and the artefact must say so"])
    if back["TREATMENT_SELECTOR"] != "NOT_IMPLEMENTED":
        return refused("evidence guard", ["treatment absence did not survive write"])

    return {
        "V3_AMENDMENT": "FROZEN",
        "refrozen": refrozen,
        "payload": back,
        "sha256": sha256_file(OUT),
        "canonical_digest": digest(strip_volatile(back)),
    }


def main() -> int:
    outcome = freeze()
    if outcome["V3_AMENDMENT"] != "FROZEN":
        print(f"V3_AMENDMENT = {outcome['V3_AMENDMENT']}")
        print(f"stage        : {outcome['stage']}")
        for reason in outcome["reasons"]:
            print(f"  - {reason}")
        return 1

    payload = outcome["payload"]
    neutrality = payload["INJECTION_SEAM_BEHAVIOURAL_NEUTRALITY"]
    print("=" * 66)
    print("TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V3")
    print("=" * 66)
    print(f"HEAD                {_git('rev-parse', 'HEAD')[:12]}")
    print(f"predecessor         V2 {V2_SHA256[:16]}...")
    print(f"equivalence bound   {EQUIVALENCE_SHA256[:16]}...  "
          f"{neutrality['artefact']['verdict']}")
    print()
    print(f"control.py V2       {V2_CONTROL_SOURCE_IDENTITY[:32]}...")
    print(f"control.py V3       {V3_CONTROL_SOURCE_IDENTITY[:32]}...")
    print(f"byte identity       {payload['SOURCE_IDENTITY_TRANSITION']['SOURCE_BYTE_IDENTITY_ACROSS_V2_TO_V3']}")
    print()
    print(f"recorded steps      {neutrality['recorded_step_count']}   "
          f"fixtures {neutrality['analytic_fixture_count']}")
    print(f"target mismatches   {neutrality['target_mismatch_count']}")
    print(f"state mismatches    {neutrality['state_mismatch_count']}")
    print(f"command mismatches  {neutrality['command_mismatch_count']}")
    print(f"predicate mismatch  {neutrality['predicate_mismatch_count']}")
    print()
    treatment = payload["TREATMENT_ABSENCE_AT_FREEZE"]
    print(f"treatment selector  {treatment['ARC_LENGTH_INTERPOLATED_TARGET_SELECTOR']}")
    print(f"concrete selectors  {treatment['concrete_selectors_declared_under_src']}")
    print()
    print(f"contract fields     {len(payload['EXECUTION_ENVIRONMENT_IDENTITY_V3']['contract_critical_fields'])} "
          f"(V2 had 45; added {payload['EXECUTION_ENVIRONMENT_IDENTITY_V3']['fields_added_since_v2']})")
    print(f"contract digest     {payload['EXECUTION_ENVIRONMENT_IDENTITY_V3']['contract_digest']}")
    print(f"canonical digest    {outcome['canonical_digest']}")
    print(f"{'FROZEN (first write)' if outcome['refrozen'] else 'RE-VERIFIED (unchanged)'}")
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {outcome['sha256']}")
    print("V3_AMENDMENT        FROZEN")
    print("EXECUTION_MANIFEST  NOT_FROZEN")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
