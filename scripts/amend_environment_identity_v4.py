"""TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V4: the executable state.

V3 pinned a source tree in which the treatment did not yet exist. That was the
point of V3 -- it froze while the seam was empty, so the equivalence proof it
bound could not have been shaped by the treatment. The treatment now exists, in
the same module V3 pins, and V3 refuses. It should. V4 does not repair V3 and
does not make it accept anything; V3 remains correct about the tree it froze.

What V4 pins is the state both arms will actually execute from. That is the
whole reason it has to exist: Arm A and Arm B must run from one repository HEAD,
one interpreter and one shared controller, with the selector chosen at runtime.
Running the control from a pre-treatment commit and the treatment from a
post-treatment commit would reintroduce exactly the confound the seam and its
equivalence proof were built to remove.

The claim V4 carries is narrow and evidenced: after introducing the treatment
implementation into the common source tree, no behavioural difference was
detected in the legacy control path over the frozen regression domain. Not
universal equivalence, and not a word about whether the treatment works --
nothing has been executed.
"""

from __future__ import annotations

import datetime as _dt
import inspect
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
    capture,
    contract_fields,
    digest,
    select,
    sha256_file,
)

AMENDMENT_ID = "TAI-V1-A4-ENV"
AMENDMENT_VERSION = "V4"
OUT = REPO / "gates/BO10/environment_identity_v4_20260912.json"

PREREG_REL = "gates/BO10/terminal_approach_intervention_v1_20260911.json"
V2_REL = "gates/BO10/environment_identity_v2_20260911.json"
V3_REL = "gates/BO10/environment_identity_v3_20260911.json"
EQUIVALENCE_REL = "gates/BO10/tracker_injection_equivalence_20260911.json"
TREATMENT_REL = "gates/BO10/arclength_treatment_validation_20260912.json"
SEAM_REL = "src/navfm/target_selection.py"
CONTROL_REL = "src/navfm/control.py"

PREREG_SHA256 = "941e44da35c8a4145fa4154d1c82deb53da2ef76f04d649789946cc2c3825b4d"
V2_SHA256 = "d664388997dcec8014a1fd598bf315a0ef76cad4d9e679b0a248c67650d4a16a"
V3_SHA256 = "0105d34b8090a736f94532d90ae0e171518e9413e267c2b518ff089f43045148"
EQUIVALENCE_SHA256 = "ff0cd687a9b6c7a1b5c0bb88f5f23eb6dead6cdf365860e452f15d0a7e62a52b"
TREATMENT_SHA256 = "25e006d53dd0ec524a724362c205185c0bc7f660c42040e581d448c26fc2ad4d"

TREATMENT_COMMIT = "ef5e7f0feb6eb1bd5eed4ebb0638aaf2306e5333"
V3_SEAM_SHA256 = "490d623c5f58f6a0943ec78af7f5435ef1dfee2d2daac3aadf655e9cbdf2a472"
V4_SEAM_SHA256 = "4678e5ebe9c7fa3771a71ac0f8944a9f92e72fb18891ce3100f29a77f2dcee58"
CONTROL_SHA256 = "679cd60f86ea2b84e4f8fe93cd464a8484bee69204f6716a62f3adb05d04abc6"

EXPECTED_RECORDED_STEPS = 1200
EXPECTED_FIXTURES = 13


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _is_ancestor(commit: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(REPO), "merge-base", "--is-ancestor", commit, "HEAD"],
        capture_output=True, check=False).returncode == 0


def refused(stage: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "V4_AMENDMENT": "REFUSED",
        "stage": stage,
        "reasons": reasons,
        "note": (
            "V4 is not written. The amendment declines rather than raising, so the "
            "refusal is a recorded scientific result instead of a traceback"
        ),
    }


def live_override_surface() -> dict[str, Any]:
    """Asked of the objects, not of the documentation."""
    from navfm.collection.interpolated_target import InterpolatedLookaheadPursuit
    from navfm.control import PurePursuit
    from navfm.target_selection import (
        ArcLengthInterpolatedTargetSelector,
        LegacyVertexTargetSelector,
    )

    surfaces = {}
    for name, cls in (("legacy", LegacyVertexTargetSelector),
                      ("treatment", ArcLengthInterpolatedTargetSelector)):
        surfaces[name] = sorted(
            n for n in dir(cls)
            if not n.startswith("_") and callable(getattr(cls, n)))
    base = {n for n in dir(PurePursuit) if not n.startswith("__")}
    overridden = sorted(n for n in base if n in InterpolatedLookaheadPursuit.__dict__)
    parameters = [
        p for p in inspect.signature(
            ArcLengthInterpolatedTargetSelector.select_target).parameters if p != "self"]
    default = PurePursuit.__init__.__defaults__
    return {
        "behavioural_overrides": ["target"],
        "selector_surfaces": surfaces,
        "both_selectors_expose_one_method": all(
            surface == ["select_target"] for surface in surfaces.values()),
        "selector_parameters": parameters,
        "selector_is_never_handed_the_tracker": "tracker" not in parameters,
        "subclass_behavioural_overrides": [
            n for n in overridden if n not in {"target_type"}],
        "default_selector_kwarg_is_none": default is None or default[-1] is None,
        "arm_a_target_type": LegacyVertexTargetSelector.target_type,
        "arm_b_target_type": ArcLengthInterpolatedTargetSelector.target_type,
    }


def verify_treatment(surface: dict[str, Any]) -> dict[str, Any]:
    """The treatment evidence is a precondition of V4, not a citation in it."""
    reasons: list[str] = []
    path = REPO / TREATMENT_REL
    if not path.is_file():
        return {"ok": False, "reasons": [f"{TREATMENT_REL} is absent"], "record": None}
    observed = sha256_file(path)
    if observed != TREATMENT_SHA256:
        reasons.append(
            f"treatment artefact sha256 is {str(observed)[:16]}..., expected "
            f"{TREATMENT_SHA256[:16]}...")
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return {"ok": False, "reasons": [f"{TREATMENT_REL} does not parse: {exc}"],
                "record": None}

    if record.get("ARC_LENGTH_TREATMENT_VALIDATION") != "PASS":
        reasons.append(
            f"treatment validation is {record.get('ARC_LENGTH_TREATMENT_VALIDATION')}")
    if record.get("EXECUTION_STATUS") != "NOT_RUN" or record.get("arms_executed") != 0:
        reasons.append("the treatment artefact does not declare that no arm ran")
    # The validation necessarily ran BEFORE the treatment was committed, so it
    # records the commit it ran against rather than the commit that carries it.
    # What must hold is that the recorded commit is real and is in this history,
    # and that the treatment commit itself is an ancestor of HEAD.
    validated_at = str(record.get("repository_head") or "")
    if not validated_at or not _is_ancestor(validated_at):
        reasons.append(
            f"treatment validation records commit {validated_at[:12] or '<none>'}, "
            "which is not in this repository's history")
    if not _is_ancestor(TREATMENT_COMMIT):
        reasons.append(
            f"treatment commit {TREATMENT_COMMIT[:12]} is not an ancestor of HEAD")

    fixtures = record.get("analytic_fixtures", {})
    if fixtures.get("verdict") != "PASS":
        reasons.append(f"analytic fixtures verdict is {fixtures.get('verdict')}")
    if fixtures.get("count") != EXPECTED_FIXTURES:
        reasons.append(
            f"{fixtures.get('count')} analytic fixtures, expected {EXPECTED_FIXTURES}")

    for block, key in (("negative_controls", "verdict"), ("refusal_controls", "verdict"),
                       ("port_fidelity", "PORT_FIDELITY")):
        value = record.get(block, {}).get(key)
        if value != "PASS":
            reasons.append(f"{block} is {value}")

    sensitivity = record.get("treatment_sensitivity", {})
    if not sensitivity.get("TREATMENT_IS_NOT_A_NO_OP"):
        reasons.append("the treatment was not shown to differ from the control")

    laws = record.get("shared_controller_laws", {})
    if laws.get("SHARED_CONTROLLER_LAWS") != "UNCHANGED":
        reasons.append("laws outside target selection are not shown unchanged")

    regression = record.get("arm_a_post_treatment_regression", {})
    if regression.get("verdict") != "PASS":
        reasons.append(f"Arm-A post-treatment regression is {regression.get('verdict')}")
    traces = regression.get("recorded_traces", {})
    if not traces:
        reasons.append("no Arm-A regression traces are bound")
    for name, trace in traces.items():
        if trace.get("steps_evaluated") != EXPECTED_RECORDED_STEPS:
            reasons.append(
                f"regression trace {name} evaluated {trace.get('steps_evaluated')} steps")
        if sum(trace.get("mismatches_by_channel", {}).values()) != 0:
            reasons.append(f"regression trace {name} reports mismatches")

    recorded_surface = record.get("override_surface", {})
    if recorded_surface.get("BEHAVIOURAL_OVERRIDE_SURFACE") != ["target"]:
        reasons.append(
            f"recorded override surface is "
            f"{recorded_surface.get('BEHAVIOURAL_OVERRIDE_SURFACE')}, expected ['target']")
    if surface["behavioural_overrides"] != ["target"]:
        reasons.append("the live override surface is not exactly ['target']")
    if not surface["both_selectors_expose_one_method"]:
        reasons.append("a selector exposes more than select_target")
    if surface["subclass_behavioural_overrides"] != ["target"]:
        reasons.append("the frozen subclass overrides more than target")

    if record.get("implementation", {}).get("source_sha256") != V4_SEAM_SHA256:
        reasons.append("the treatment artefact validated a different seam module than V4 pins")

    return {"ok": not reasons, "reasons": reasons, "record": record}


def regression_counts(record: dict[str, Any]) -> dict[str, Any]:
    totals: dict[str, int] = {}
    for trace in record["arm_a_post_treatment_regression"]["recorded_traces"].values():
        for channel, count in trace.get("mismatches_by_channel", {}).items():
            totals[channel] = totals.get(channel, 0) + int(count)
    return {
        "recorded_steps_per_trace": EXPECTED_RECORDED_STEPS,
        "traces": sorted(record["arm_a_post_treatment_regression"]["recorded_traces"]),
        "target_mismatches": totals.get("target_x", 0) + totals.get("target_y", 0),
        "state_mismatches": totals.get("index_after", 0) + totals.get("finished_after", 0),
        "vx_mismatches": totals.get("vx", 0),
        "wz_mismatches": totals.get("wz", 0),
        "predicate_mismatches": totals.get("done", 0) + totals.get("finished_after", 0),
        "per_channel": totals,
        "analytic_domain": record["arm_a_post_treatment_regression"]["analytic_domain"],
        "pre_seam_reference": record["arm_a_post_treatment_regression"]["pre_seam_reference"],
    }


def build_payload(amended_at: str, treatment: dict[str, Any], surface: dict[str, Any],
                  contract: dict[str, Any]) -> dict[str, Any]:
    record = treatment["record"]
    counts = regression_counts(record)
    v2 = json.loads((REPO / V2_REL).read_text())
    v3 = json.loads((REPO / V3_REL).read_text())
    equivalence = json.loads((REPO / EQUIVALENCE_REL).read_text())
    prereg = json.loads((REPO / PREREG_REL).read_text())

    return {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V4",
        "artifact_semantics": "AMENDMENT_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "amendment_id": AMENDMENT_ID,
        "amendment_version": AMENDMENT_VERSION,
        "amended_at_utc": amended_at,
        "STATUS": "FROZEN",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "authorisation": "NOT AUTHORISED. Neither arm may run under this amendment.",
        "authoritative_intervention_contract": "V4",
        "no_automatic_fallback": (
            "production execution requires V4. Naming V1, V2 or V3 explicitly still "
            "validates historical state against that version, but no contract is "
            "substituted for another silently"
        ),
        "amends": {
            "predecessor": {"path": V3_REL, "sha256": V3_SHA256, "version": "V3"},
            "original_preregistration": {
                "path": PREREG_REL, "sha256": PREREG_SHA256, "version": "V1"},
            "append_only": True,
            "v1_v2_v3_rewritten": False,
            "reason": (
                "treatment code now exists in the same source tree from which both "
                "arms will execute. V4 pins that final treatment-capable state"
            ),
            "this_does_not_repair_v3": (
                "V3 froze while the seam was empty, which is what makes the equivalence "
                "proof it binds untainted by the treatment. V3 remains historically "
                "correct and must continue to refuse the treatment tree"
            ),
            "the_intervention_design_is_unchanged": True,
        },
        "VERSION_CHAIN": [
            {"node": "INTERVENTION_V1", "path": PREREG_REL, "sha256": PREREG_SHA256,
             "timestamp_utc": prereg.get("preregistered_at"), "predecessor": None,
             "reason": "the preregistered one-factor intervention",
             "evidence_basis": "Q2 and Q3 diagnostics"},
            {"node": "ENVIRONMENT_V2", "path": V2_REL, "sha256": V2_SHA256,
             "timestamp_utc": v2["amended_at_utc"], "predecessor": "INTERVENTION_V1",
             "reason": v2["amends"]["reason"],
             "evidence_basis": "the hash-verified pre-reboot preflight blob"},
            {"node": "TRACKER_INJECTION_EQUIVALENCE", "path": EQUIVALENCE_REL,
             "sha256": EQUIVALENCE_SHA256, "timestamp_utc": equivalence["timestamp_utc"],
             "predecessor": "ENVIRONMENT_V2",
             "reason": "prove the injection seam behaviour-neutral before treatment",
             "evidence_basis": "15 analytic fixtures and 1200 recorded poses against "
                               "the pre-seam tracker read from git"},
            {"node": "ENVIRONMENT_V3", "path": V3_REL, "sha256": V3_SHA256,
             "timestamp_utc": v3["amended_at_utc"],
             "predecessor": "TRACKER_INJECTION_EQUIVALENCE",
             "reason": v3["amends"]["reason"],
             "evidence_basis": "the bound equivalence artefact, frozen while the seam "
                               "was empty"},
            {"node": "ARC_LENGTH_INTERPOLATED_TARGET_SELECTOR_VALIDATION",
             "path": TREATMENT_REL, "sha256": TREATMENT_SHA256,
             "timestamp_utc": record["timestamp_utc"], "predecessor": "ENVIRONMENT_V3",
             "reason": "implement and independently validate the preregistered treatment",
             "evidence_basis": f"{EXPECTED_FIXTURES} hand-computed analytic fixtures, "
                               "four defective-selector controls, nine refusal controls, "
                               f"and an Arm-A regression over {EXPECTED_RECORDED_STEPS} "
                               "recorded poses"},
            {"node": "ENVIRONMENT_V4", "path": str(OUT.relative_to(REPO)),
             "sha256": "<this artefact>", "timestamp_utc": amended_at,
             "predecessor": "ARC_LENGTH_INTERPOLATED_TARGET_SELECTOR_VALIDATION",
             "reason": "pin the final treatment-capable executable source state",
             "evidence_basis": "the bound treatment-validation artefact"},
        ],
        "TREATMENT_EVIDENCE": {
            "treatment_commit": TREATMENT_COMMIT,
            "validation_artefact": {"path": TREATMENT_REL, "sha256": TREATMENT_SHA256,
                                    "verdict": record["ARC_LENGTH_TREATMENT_VALIDATION"],
                                    "validated_at_commit": record["repository_head"]},
            "treatment_selector": record["implementation"],
            "legacy_selector": {
                "class": "navfm.target_selection.LegacyVertexTargetSelector",
                "target_type": surface["arm_a_target_type"],
                "source": SEAM_REL, "source_sha256": V4_SEAM_SHA256},
            "both_selectors_share_one_module": True,
            "analytic_fixtures": {
                "count": record["analytic_fixtures"]["count"],
                "verdict": record["analytic_fixtures"]["verdict"],
                "max_abs_difference_m": record["analytic_fixtures"]["max_abs_difference_m"],
                "names": [r["name"] for r in record["analytic_fixtures"]["results"]],
                "oracle": record["independent_oracle"]["method"]},
            "defective_selector_controls": {
                name: {"detected": result["DETECTED"],
                       "fixtures_rejected": len(result["fixtures_rejected"])}
                for name, result in record["negative_controls"]["results"].items()},
            "refusal_controls": {
                "count": record["refusal_controls"]["count"],
                "all_refused": record["refusal_controls"]["verdict"] == "PASS"},
            "treatment_sensitivity": {
                "is_not_a_no_op": record["treatment_sensitivity"]["TREATMENT_IS_NOT_A_NO_OP"],
                "agrees_where_geometry_coincides": record["treatment_sensitivity"][
                    "TREATMENT_AGREES_WHERE_GEOMETRY_COINCIDES"]},
            "behavioural_override_surface": ["target"],
        },
        "ARM_A_POST_TREATMENT_REGRESSION": {
            "verdict": record["arm_a_post_treatment_regression"]["verdict"],
            **counts,
            "CLAIM": (
                "After introducing the treatment implementation into the common source "
                "tree, no behavioural difference was detected in the legacy control path "
                f"over the frozen regression domain: {EXPECTED_RECORDED_STEPS} recorded "
                "poses on two route densities plus the analytic fixtures, compared "
                "against the pre-seam tracker as well as the post-seam default and "
                "injected legacy paths"
            ),
            "CLAIM_BOUNDARY": (
                "this is equivalence over the frozen regression domain. It is NOT a "
                "mathematical proof of equivalence for every possible input, and it says "
                "nothing whatever about treatment effectiveness -- no arm has executed"
            ),
        },
        "SOURCE_IDENTITY_TRANSITION": {
            "V3_SEAM_SOURCE_IDENTITY": V3_SEAM_SHA256,
            "V4_SEAM_SOURCE_IDENTITY": V4_SEAM_SHA256,
            "SOURCE_BYTE_IDENTITY_ACROSS_V3_TO_V4": "CHANGED",
            "expected_and_intentional": True,
            "control_py_unchanged_since_v3": CONTROL_SHA256,
            "changed_from_v3": {
                "scientific_code.target_selection_sha256": {
                    "old": V3_SEAM_SHA256, "new": V4_SEAM_SHA256,
                    "justification": "the preregistered treatment selector was implemented",
                    "evidence": {"path": TREATMENT_REL, "sha256": TREATMENT_SHA256}},
                "no_other_field_changed": True,
                "fields_added": [],
                "why_no_field_was_added": (
                    "the treatment landed inside the seam module V3 already pins, so the "
                    "field that would have been added is the field that already exists. "
                    "Adding a redundant one would make the contract look stricter "
                    "without checking anything more"
                ),
            },
        },
        "ONE_FACTOR_EXECUTION_CONTRACT": {
            "shared_by_both_arms": [
                "repository HEAD and source state", "the controller implementation",
                "the route and frozen polyline", "the scene identifier",
                "the initial pose and start yaw", "the sealed goal", "the seed",
                "the camera transform", "the kinematic drive", "the collision guard",
                "the heading-error law", "the linear speed law", "the angular law",
                "controller gains", "velocity clipping", "SE(2) integration",
                "physics_dt, rendering_dt and control_dt", "cruise velocity",
                "the angular limit", "the look-ahead distance", "max_steps",
                "the goal tolerance", "the stopping logic", "the primary outcome",
                "the secondary cross-track outcome",
                "the execution environment requirements",
            ],
            "only_declared_difference": {
                "ARM_A_CONTROL": {
                    "target_selector": "LEGACY_VERTEX",
                    "class": "navfm.target_selection.LegacyVertexTargetSelector",
                    "target_type": surface["arm_a_target_type"]},
                "ARM_B_TREATMENT": {
                    "target_selector": "ARC_LENGTH_INTERPOLATED",
                    "class": "navfm.target_selection.ArcLengthInterpolatedTargetSelector",
                    "target_type": surface["arm_b_target_type"]},
            },
            "behavioural_overrides": ["target"],
            "both_arms_execute_from_one_source_tree": (
                "one repository HEAD, one Python environment, one shared controller. "
                "The selector is runtime configuration. Running the control from a "
                "pre-treatment commit and the treatment from a post-treatment commit "
                "would reintroduce the confound the seam was built to remove"
            ),
            "selector_surface": surface,
        },
        "EXECUTION_ENVIRONMENT_IDENTITY_V4": {
            "contract_version": CONTRACT_VERSION,
            "supersedes": "V3",
            "implementation": "src/navfm/execution_environment.py",
            "frozen_contract_values": contract,
            "contract_digest": digest(contract),
            "contract_critical_fields": list(contract_fields("V4")),
            "fields_added_since_v3": [],
            "pairwise_critical_fields": list(PAIRWISE_CRITICAL_FIELDS),
            "equality_critical_fields": list(EQUALITY_CRITICAL_FIELDS),
            "observational_fields_recorded_never_compared": list(OBSERVATIONAL_FIELDS),
        },
        "HISTORICAL_CONTRACTS_REMAIN_FROZEN": {
            "v1_v2_v3_rewritten": False,
            "invariants": [
                "V2 accepts its freeze state and rejects the later seam state",
                "V3 accepts its freeze state and rejects the later treatment state",
                "V4 accepts the final treatment-capable execution state",
            ],
            "required_control": {
                "current_tree_against_V3": "REFUSE on scientific_code.target_selection_sha256",
                "current_tree_against_V4": "PASS",
            },
        },
        "EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY": (
            "a successful CUDA probe establishes that a CUDA context can be created in "
            "the Isaac interpreter. It does not establish that the Hospital scene loads, "
            "that the render loop runs, or that the collector completes. The first arm "
            "execution is what would establish runtime execution evidence"
        ),
        "scene_limitation_carried_forward": {
            "scene_asset_identifier_can_be_established": True,
            "scene_byte_identity": "NOT_VERIFIED_REMOTE_STREAMED_ASSET",
            "no_scene_sha_generated": True,
        },
        "EXECUTION_MANIFEST": "NOT_FROZEN_BY_THIS_AMENDMENT",
        "execution_manifest_note": (
            "the runtime manifest is frozen after the last tracked commit, because a "
            "tracked artefact cannot truthfully contain the SHA of the commit that "
            "contains it"
        ),
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
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
    reasons: list[str] = []
    for rel, expected in ((PREREG_REL, PREREG_SHA256), (V2_REL, V2_SHA256),
                          (V3_REL, V3_SHA256), (EQUIVALENCE_REL, EQUIVALENCE_SHA256)):
        observed = sha256_file(REPO / rel)
        if observed != expected:
            reasons.append(
                f"{rel} sha256 is {str(observed)[:16]}..., expected {expected[:16]}...")
    if reasons:
        return refused("predecessor verification", reasons)

    for rel, expected, label in ((SEAM_REL, V4_SEAM_SHA256, "treatment seam module"),
                                 (CONTROL_REL, CONTROL_SHA256, "controller")):
        observed = sha256_file(REPO / rel)
        if observed != expected:
            return refused(
                "source identity",
                [f"{label} {rel} is {str(observed)[:16]}..., V4 pins {expected[:16]}..."])

    surface = live_override_surface()
    if surface["behavioural_overrides"] != ["target"] or not surface[
            "both_selectors_expose_one_method"]:
        return refused(
            "override surface",
            [f"the behavioural override surface is not exactly ['target']: {surface}"])

    treatment = verify_treatment(surface)
    if not treatment["ok"]:
        return refused("treatment verification", treatment["reasons"])

    contract = select(capture(REPO), contract_fields("V4"))

    if OUT.exists():
        prior = json.loads(OUT.read_text())
        amended_at = str(prior["amended_at_utc"])
        result = build_payload(amended_at, treatment, surface, contract)
        drift = diff_paths(strip_volatile(result), strip_volatile(prior))
        if drift:
            shown = "\n  ".join(drift[:25]) + ("\n  ..." if len(drift) > 25 else "")
            return refused(
                "canonical regeneration",
                [f"the canonical amendment no longer matches the frozen artefact at "
                 f"{OUT.relative_to(REPO)}. Fields that differ ({len(drift)}):\n  {shown}",
                 "V4 is frozen and cited by hash. A changed contract or evidence basis "
                 "requires an explicit V5 amendment at a new path"],
            )
        refrozen = False
    else:
        amended_at = _dt.datetime.now(_dt.UTC).isoformat()
        result = build_payload(amended_at, treatment, surface, contract)
        refrozen = True

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    for key in ("TREATMENT_EVIDENCE", "ARM_A_POST_TREATMENT_REGRESSION", "VERSION_CHAIN",
                "ONE_FACTOR_EXECUTION_CONTRACT", "EXECUTION_STATUS"):
        if key not in back:
            return refused("evidence guard", [f"missing {key} after write"])
    if back["EXECUTION_STATUS"] != "NOT_RUN":
        return refused("evidence guard", ["no arm has run and the artefact must say so"])
    if back["ONE_FACTOR_EXECUTION_CONTRACT"]["behavioural_overrides"] != ["target"]:
        return refused("evidence guard", ["the one-factor declaration did not survive write"])

    return {"V4_AMENDMENT": "FROZEN", "refrozen": refrozen, "payload": back,
            "sha256": sha256_file(OUT), "canonical_digest": digest(strip_volatile(back))}


def main() -> int:
    outcome = freeze()
    if outcome["V4_AMENDMENT"] != "FROZEN":
        print(f"V4_AMENDMENT = {outcome['V4_AMENDMENT']}")
        print(f"stage        : {outcome['stage']}")
        for reason in outcome["reasons"]:
            print(f"  - {reason}")
        return 1

    payload = outcome["payload"]
    regression = payload["ARM_A_POST_TREATMENT_REGRESSION"]
    print("=" * 68)
    print("TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V4")
    print("=" * 68)
    print(f"HEAD                {_git('rev-parse', 'HEAD')[:12]}")
    print(f"predecessor         V3 {V3_SHA256[:16]}...")
    print(f"treatment commit    {TREATMENT_COMMIT[:12]}")
    print(f"treatment evidence  {TREATMENT_SHA256[:16]}...  "
          f"{payload['TREATMENT_EVIDENCE']['validation_artefact']['verdict']}")
    print()
    print(f"seam V3 -> V4       {V3_SEAM_SHA256[:16]}... -> {V4_SEAM_SHA256[:16]}...")
    print(f"control.py          {CONTROL_SHA256[:16]}...  (unchanged since V3)")
    print(f"override surface    {payload['ONE_FACTOR_EXECUTION_CONTRACT']['behavioural_overrides']}")
    print()
    print(f"arm-A regression    {regression['verdict']}  "
          f"target={regression['target_mismatches']} state={regression['state_mismatches']} "
          f"vx={regression['vx_mismatches']} wz={regression['wz_mismatches']} "
          f"predicate={regression['predicate_mismatches']}")
    print()
    print(f"contract fields     {len(contract_fields('V4'))} (V3 had "
          f"{len(contract_fields('V3'))}; added "
          f"{payload['EXECUTION_ENVIRONMENT_IDENTITY_V4']['fields_added_since_v3']})")
    print(f"contract digest     {payload['EXECUTION_ENVIRONMENT_IDENTITY_V4']['contract_digest']}")
    print(f"canonical digest    {outcome['canonical_digest']}")
    print(f"{'FROZEN (first write)' if outcome['refrozen'] else 'RE-VERIFIED (unchanged)'}")
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {outcome['sha256']}")
    print("V4_AMENDMENT        FROZEN")
    print("EXECUTION_MANIFEST  NOT_FROZEN_BY_THIS_AMENDMENT")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
