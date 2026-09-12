"""The frozen execution manifest for TERMINAL_APPROACH_INTERVENTION_V1.

Everything an arm needs in order to run, and everything a later reader needs in
order to check that it ran as declared, fixed in one place before anything runs.

Two structural decisions are worth stating, because both are easy to get wrong
in a way that looks fine.

**The manifest is a runtime artefact, not a tracked one.** It binds the exact
repository HEAD both arms execute from, and a tracked file cannot truthfully
contain the SHA of the commit that contains it. Writing a placeholder,
committing, rewriting the real HEAD and committing again would produce a file
that pins a commit which is no longer HEAD -- a provenance claim that reads as
precise and is false. So all tracked governance lands first, and the manifest is
frozen afterwards against the resulting HEAD, in the already-ignored runtime
evidence tree.

**The output allow-list is an enumeration, not a pattern.** ``runs/**`` or
``gates/**`` would make the worktree check incapable of distinguishing an
expected trajectory from an edited controller, which is the one distinction it
exists to make. Every path an arm may create is named here, and anything else
appearing in the tree fails the policy.

No outcome value appears in this module. A manifest is written before the
experiment; a manifest that could carry a result would be a manifest that could
be written after one.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from navfm.execution_environment import (
    EQUALITY_CRITICAL_FIELDS,
    canonical_json,
    digest,
    sha256_file,
)

__all__ = [
    "ARM_ORDER",
    "MANIFEST_VERSION",
    "REQUIRED_MANIFEST_KEYS",
    "SELECTOR_ASSIGNMENT",
    "TRACKED_OUTPUTS",
    "UNTRACKED_OUTPUTS",
    "build_manifest",
    "canonical_manifest",
    "canonical_worktree_state",
    "freeze_manifest",
    "manifest_digest",
    "validate_manifest",
]

MANIFEST_VERSION = "EXECUTION_MANIFEST_V1"
AUTHORITATIVE_CONTRACT = "V4"

#: Fixed by protocol before the treatment existed, not chosen after seeing a
#: result. Order picked after a suggestive trace is order picked by the
#: experimenter.
ARM_ORDER: tuple[str, ...] = ("ARM_A_CONTROL", "ARM_B_TREATMENT")

SELECTOR_ASSIGNMENT: dict[str, dict[str, str]] = {
    "ARM_A_CONTROL": {
        "selector_class": "navfm.target_selection.LegacyVertexTargetSelector",
        "target_type": "PATH_VERTEX",
    },
    "ARM_B_TREATMENT": {
        "selector_class": "navfm.target_selection.ArcLengthInterpolatedTargetSelector",
        "target_type": "ARC_LENGTH_INTERPOLATED",
    },
}

#: Artefacts that land in the tracked tree and therefore make it dirty. Named
#: individually: the worktree check has to tell an expected result from an edited
#: source file, and a glob cannot.
TRACKED_OUTPUTS: tuple[str, ...] = (
    "gates/BO10/intervention/arm_a_result.json",
    "gates/BO10/intervention/arm_a_terminal_trace.csv",
    "gates/BO10/intervention/arm_b_result.json",
    "gates/BO10/intervention/arm_b_terminal_trace.csv",
    "gates/BO10/intervention/environment_equivalence.json",
    "gates/BO10/intervention/comparison.json",
)

#: Runtime artefacts under the already-ignored evidence tree. Enumerated anyway,
#: so "it was ignored" never stands in for "it was expected".
UNTRACKED_OUTPUTS: tuple[str, ...] = (
    "runs/bo10/intervention/execution_manifest.json",
    "runs/bo10/intervention/env/pre_arm_a.json",
    "runs/bo10/intervention/env/post_arm_a.json",
    "runs/bo10/intervention/env/pre_arm_b.json",
    "runs/bo10/intervention/env/post_arm_b.json",
    "runs/bo10/intervention/status/arm_a_status.json",
    "runs/bo10/intervention/status/arm_b_status.json",
    "runs/bo10/intervention/arm_a/",
    "runs/bo10/intervention/arm_b/",
)

#: The one path whose content may legitimately differ at a pre-arm capture, under
#: the narrow exception the environment guard already defines. Referenced, never
#: redefined here.
PREFLIGHT_REL = "gates/BO10/intervention_execution_preflight_20260911.json"

REQUIRED_MANIFEST_KEYS: tuple[str, ...] = (
    "manifest_version",
    "intervention",
    "authoritative_contract",
    "repository",
    "environment_guard",
    "arms",
    "route",
    "episode",
    "runtime_configuration",
    "outcomes",
    "environment_policy",
    "output_allowlist",
    "retry_policy",
    "failure_policy",
    "claim_limit",
    "EXECUTION_STATUS",
)

#: Recomputed on every freeze; excluded from the canonical digest so a
#: regeneration that changed nothing scientific reproduces the same identity.
_VOLATILE_KEYS = frozenset({"frozen_at_utc"})


def canonical_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """The manifest minus the fields that legitimately move per freeze."""
    return {k: v for k, v in manifest.items() if k not in _VOLATILE_KEYS}


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    return digest(canonical_manifest(manifest))


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def canonical_worktree_state(
    repo_root: Path,
    *,
    allow_preflight: bool = False,
    allow_outputs: Sequence[str] = (),
) -> dict[str, Any]:
    """Worktree state after subtracting only what the manifest declares.

    Expected scientific output is not source drift, and unexpected source drift
    is not output. Keeping both statements true at once is the only reason this
    is not simply ``git status``.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {"WORKTREE_POLICY": "FAIL", "reason": "git status failed",
                "paths": [], "unexpected": []}
    paths = sorted(line[3:].strip() for line in proc.stdout.splitlines() if line.strip())

    permitted = list(allow_outputs)
    if allow_preflight:
        permitted.append(PREFLIGHT_REL)
    unexpected = [
        p for p in paths
        if not any(p == a or (a.endswith("/") and p.startswith(a)) for a in permitted)
    ]
    return {
        "WORKTREE_POLICY": "PASS" if not unexpected else "FAIL",
        "paths": paths,
        "permitted": sorted(permitted),
        "unexpected": unexpected,
        "canonical_state": "clean" if not unexpected else "dirty:" + ",".join(unexpected),
        "semantics": (
            "only the manifest-declared output paths and, at a pre-arm capture, the "
            "one preflight artefact are subtracted. Everything else is source drift"
        ),
    }


def build_manifest(repo_root: Path | str, *, head: str, frozen_at_utc: str) -> dict[str, Any]:
    """Assemble the manifest from the frozen records, restating nothing."""
    root = Path(repo_root)
    prereg_rel = "gates/BO10/terminal_approach_intervention_v1_20260911.json"
    v4_rel = "gates/BO10/environment_identity_v4_20260912.json"
    prereg = json.loads((root / prereg_rel).read_text())
    v4 = json.loads((root / v4_rel).read_text())
    cross_track = prereg["secondary_outcome_cross_track_error"]
    contract = v4["EXECUTION_ENVIRONMENT_IDENTITY_V4"]["frozen_contract_values"]

    return {
        "manifest_version": MANIFEST_VERSION,
        "artifact_semantics": "PRE_EXECUTION_MANIFEST_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "frozen_at_utc": frozen_at_utc,
        "intervention": {
            "identifier": "TERMINAL_APPROACH_INTERVENTION_V1",
            "preregistration": {"path": prereg_rel, "sha256": sha256_file(root / prereg_rel)},
            "manipulated_factor": "target selection only",
        },
        "authoritative_contract": {
            "version": AUTHORITATIVE_CONTRACT,
            "path": v4_rel,
            "sha256": sha256_file(root / v4_rel),
            "no_automatic_fallback": (
                "execution requires V4. Older contracts remain checkable against the "
                "state they froze and are never substituted for V4"
            ),
        },
        "repository": {
            "head": head,
            "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD") or None,
            "path": str(root),
            "both_arms_execute_from_this_head": True,
            "rule": (
                "a tracked source or governance commit after this freeze invalidates "
                "the manifest; a new versioned manifest must be frozen before execution"
            ),
        },
        "environment_guard": {
            "version": "PER_ARM_ENVIRONMENT_EQUIVALENCE_GUARD_V1",
            "captures": ["PRE_ARM_A", "POST_ARM_A", "PRE_ARM_B", "POST_ARM_B"],
            "equality_critical_field_count": len(EQUALITY_CRITICAL_FIELDS),
            "contract_field_count": len(contract),
        },
        "arms": {
            "order": list(ARM_ORDER),
            "order_rule": (
                "control before treatment, preregistered before the treatment existed "
                "and before any arm ran. Not randomised now, and not reordered after "
                "seeing Arm A"
            ),
            "selectors": SELECTOR_ASSIGNMENT,
            "behavioural_overrides": ["target"],
            "selector_verified_at_pre_arm_barrier": (
                "the requested selector identity is checked before movement; a wrong "
                "assignment refuses execution rather than producing a mislabelled arm"
            ),
            "sample_count_per_arm": 1,
        },
        "route": {
            "identity": "BO10_FROZEN_TURNING_ROUTE",
            "polyline": cross_track["frozen_route_polyline"]["coordinates"],
            "source_artefact": {
                "path": "gates/BO10/hospital_turning_route_population_20260910.json",
                "sha256": sha256_file(
                    root / "gates/BO10/hospital_turning_route_population_20260910.json"),
            },
            "projection_instrument": cross_track["instrument_pinned"],
        },
        "episode": {
            "scene_id": "hospital_bo10",
            "scene_asset": (
                "https://omniverse-content-production.s3-us-west-2.amazonaws.com/"
                "Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd"),
            "scene_byte_identity": "NOT_VERIFIED_REMOTE_STREAMED_ASSET",
            "scene_claim_boundary": (
                "the same asset identifier is frozen and comparable across arms. Byte "
                "identity of what the remote server serves is not verified, and no "
                "scene SHA is invented"
            ),
            "seed": 0,
            "initial_pose_xy_yaw": [-21.82872391, 32.52503586, -2.9377558421693295],
            "goal_xy": [-5.1272511265954535, 27.725192148593067],
            "sealed_goal_identity": digest(
                [-5.1272511265954535, 27.725192148593067]),
            "camera": "the frozen collection camera transform, unchanged between arms",
        },
        "runtime_configuration": {
            "physics_dt": contract["runtime_contract.physics_dt"],
            "rendering_dt": contract["runtime_contract.rendering_dt"],
            "control_dt": contract["runtime_contract.control_dt"],
            "control_hz": contract["runtime_contract.control_hz"],
            "max_steps": contract["runtime_contract.max_steps"],
            "lookahead_m": contract["runtime_contract.lookahead_m"],
            "goal_tol_m": contract["runtime_contract.goal_tol_m"],
            "cruise_v": contract["runtime_contract.cruise_v"],
            "max_v": contract["runtime_contract.max_v"],
            "max_w": contract["runtime_contract.max_w"],
            "seed": contract["runtime_contract.seed"],
            "shared_by_both_arms": True,
        },
        "outcomes": {
            "primary": {
                "definition": prereg["design_carried_forward_unchanged"]["primary_outcome"],
                "source": f"{prereg_rel} -> design_carried_forward_unchanged.primary_outcome",
            },
            "secondary_cross_track": {
                "definition": cross_track["definition"],
                "windows": cross_track["windows"],
                "statistics_per_arm_per_window": cross_track[
                    "statistics_to_report_per_arm_per_window"],
                "threshold_status": cross_track["threshold_status"],
            },
            "secondary_lookahead_domain": {
                "name": prereg["secondary_outcome_lookahead_domain"]["name"],
                "lookahead_radius_m": prereg["secondary_outcome_lookahead_domain"][
                    "lookahead_radius_m"],
                "interpretation_caveat": prereg["secondary_outcome_lookahead_domain"][
                    "INTERPRETATION_CAVEAT"],
            },
            "terminal_window_rule": (
                "the arc-length window from the last interior route vertex to the sealed "
                "goal. It is a property of the frozen route, so both arms share it; the "
                "STEP at which each arm enters it differs and comparisons are made over "
                "the window, never over a fixed step range"
            ),
            "terminal_trace_fields": prereg["terminal_mechanism_trace"][
                "persist_per_step_over_the_terminal_planned_leg"],
            "no_significance_testing": prereg["power_and_claim_limit"][
                "NO_SIGNIFICANCE_TESTING"],
            "interpretation_rules_source": f"{prereg_rel} -> interpretation_rules",
            "no_outcome_values_in_this_manifest": True,
        },
        "environment_policy": {
            "no_reboot_between_pre_arm_a_and_post_arm_b": True,
            "reboot_instrument": "session.boot_id",
            "expected_nvidia_driver": "580.178.04",
            "expected_nvidia_module": "580.178.04",
            "expected_held_package_count": 22,
            "hold_list_path": "~/navfm-nvidia-580-held-20260911.txt",
            "holds_released_only_after": [
                "Arm A", "Arm B", "artefact write", "read-back", "validation", "hashing",
            ],
            "preflight_exception": {
                "path": PREFLIGHT_REL,
                "policy": "defined by navfm.arm_environment_guard; referenced, not redefined",
                "volatile_fields": ["timestamp_utc", "isaac_slot.nvidia_smi_stderr"],
                "not_broadened_here": True,
            },
            "execution_environment_claim_boundary": (
                "a successful CUDA probe does not establish that the Hospital scene "
                "loads, that the render loop runs, or that the collector completes"
            ),
        },
        "output_allowlist": {
            "tracked": list(TRACKED_OUTPUTS),
            "untracked_runtime": list(UNTRACKED_OUTPUTS),
            "policy": "deny by default; every permitted path is enumerated",
            "forbidden_patterns": ["runs/**", "gates/**", "*.json", "*.csv"],
            "why_not_patterns": (
                "a glob cannot tell an expected trajectory from an edited controller, "
                "which is the one distinction this check exists to make"
            ),
            "unexpected_path_consequence": "WORKTREE_POLICY = FAIL and execution refused",
        },
        "retry_policy": {
            "source": f"{prereg_rel} and the V1 execution preflight",
            "scientifically_valid_arm": "executes once",
            "infrastructure_failure_before_valid_artefact": (
                "STOP, record RUN_FAILED_NO_ARTEFACT, and require an explicit protocol "
                "decision or amendment before any re-run"
            ),
            "forbidden": [
                "re-running because a result looks strange",
                "re-running only the worse arm",
                "choosing the better duplicate",
                "averaging across repeated environments",
            ],
        },
        "failure_policy": {
            "arm_a_produces_no_valid_artefact": (
                "do NOT proceed to Arm B. The preregistered two-arm comparison cannot be "
                "completed, so record the failure and stop"
            ),
            "pre_arm_a_fails": "Arm A does not run",
            "post_arm_a_invalid": "Arm B does not run",
            "pre_arm_b_not_equivalent_to_pre_arm_a": "Arm B does not run",
            "post_arm_b_invalid": "the scientific comparison is invalid",
            "four_way_equivalence_fails": "INTERVENTION_COMPARISON = INVALID",
            "no_selective_repair": True,
            "comparison_invalidation": {
                "forbidden": [
                    "averaging across environments",
                    "repairing one arm and comparing anyway",
                    "re-running only the less favourable arm",
                    "silently choosing the better pair",
                ],
            },
        },
        "claim_limit": {
            "a_positive_result_permits": (
                "an instance-level causal claim: under this frozen Hospital route and "
                "configuration, changing target selection changed the measured outcome"
            ),
            "it_does_not_establish": [
                "an expected Hospital-wide effect",
                "a population success-rate improvement",
                "any improvement to GNM, ViNT or NoMaD",
                "physical robot behaviour",
                "sim-to-real success",
            ],
            "sample_count_per_arm": 1,
        },
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "authorisation": "NOT AUTHORISED. Explicit execution authorisation is required.",
    }


#: Substrings that must never appear in an allow-list entry. A pattern here
#: would quietly restore the tolerance the enumeration exists to remove.
_FORBIDDEN_ALLOWLIST_TOKENS = ("**", "*", "?")


def validate_manifest(
    manifest: Mapping[str, Any],
    repo_root: Path | str,
    *,
    expected_head: str | None = None,
) -> dict[str, Any]:
    """Check a manifest against the repository it claims to pin.

    Every failure names the field it failed on. A manifest that was merely
    "invalid" would tell an operator to look everywhere.
    """
    root = Path(repo_root)
    failures: list[dict[str, str]] = []

    def fail(field: str, detail: str) -> None:
        failures.append({"field": field, "detail": detail})

    if not isinstance(manifest, Mapping):
        return {"MANIFEST_VALID": "FAIL",
                "failures": [{"field": "<root>", "detail": "manifest is not a mapping"}]}

    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing:
        for key in missing:
            fail(key, "required key is absent")
        return {"MANIFEST_VALID": "FAIL", "failures": failures}

    if manifest["manifest_version"] != MANIFEST_VERSION:
        fail("manifest_version", f"{manifest['manifest_version']!r} != {MANIFEST_VERSION!r}")

    contract = manifest["authoritative_contract"]
    if contract.get("version") != AUTHORITATIVE_CONTRACT:
        fail("authoritative_contract.version",
             f"{contract.get('version')!r} != {AUTHORITATIVE_CONTRACT!r}")
    else:
        observed = sha256_file(root / contract["path"])
        if observed != contract.get("sha256"):
            fail("authoritative_contract.sha256",
                 f"file is {str(observed)[:16]}..., manifest says "
                 f"{str(contract.get('sha256'))[:16]}...")

    head = _git(root, "rev-parse", "HEAD")
    declared = manifest["repository"].get("head")
    if expected_head is not None and declared != expected_head:
        fail("repository.head",
             f"manifest pins {str(declared)[:12]}, expected {expected_head[:12]}")
    if head and declared != head:
        fail("repository.head",
             f"manifest pins {str(declared)[:12]}, repository HEAD is {head[:12]}")

    arms = manifest["arms"]
    if list(arms.get("order", [])) != list(ARM_ORDER):
        fail("arms.order", f"{arms.get('order')} != {list(ARM_ORDER)}")
    if arms.get("behavioural_overrides") != ["target"]:
        fail("arms.behavioural_overrides",
             f"{arms.get('behavioural_overrides')} != ['target']")
    for arm, expected in SELECTOR_ASSIGNMENT.items():
        got = arms.get("selectors", {}).get(arm, {})
        if got.get("selector_class") != expected["selector_class"]:
            fail(f"arms.selectors.{arm}.selector_class",
                 f"{got.get('selector_class')!r} != {expected['selector_class']!r}")
        if got.get("target_type") != expected["target_type"]:
            fail(f"arms.selectors.{arm}.target_type",
                 f"{got.get('target_type')!r} != {expected['target_type']!r}")

    route = manifest["route"]
    route_sha = sha256_file(root / route["source_artefact"]["path"])
    if route_sha != route["source_artefact"].get("sha256"):
        fail("route.source_artefact.sha256",
             f"file is {str(route_sha)[:16]}..., manifest says "
             f"{str(route['source_artefact'].get('sha256'))[:16]}...")
    if not route.get("polyline"):
        fail("route.polyline", "no polyline is pinned")

    v4_path = root / contract.get("path", "")
    if v4_path.is_file():
        frozen = json.loads(v4_path.read_text())[
            "EXECUTION_ENVIRONMENT_IDENTITY_V4"]["frozen_contract_values"]
        runtime = manifest["runtime_configuration"]
        for key in ("physics_dt", "rendering_dt", "control_dt", "max_steps",
                    "lookahead_m", "goal_tol_m", "cruise_v", "max_v", "max_w", "seed"):
            expected_value = frozen.get(f"runtime_contract.{key}")
            if runtime.get(key) != expected_value:
                fail(f"runtime_configuration.{key}",
                     f"{runtime.get(key)!r} != frozen contract {expected_value!r}")
        if manifest["episode"].get("seed") != frozen.get("runtime_contract.seed"):
            fail("episode.seed",
                 f"{manifest['episode'].get('seed')!r} != "
                 f"{frozen.get('runtime_contract.seed')!r}")

    allowlist = manifest["output_allowlist"]
    for bucket in ("tracked", "untracked_runtime"):
        entries = allowlist.get(bucket)
        if not entries:
            fail(f"output_allowlist.{bucket}", "no output paths are declared")
            continue
        for entry in entries:
            if any(token in entry for token in _FORBIDDEN_ALLOWLIST_TOKENS):
                fail(f"output_allowlist.{bucket}",
                     f"{entry!r} is a pattern; the allow-list must enumerate exact paths")
    if set(allowlist.get("tracked", ())) != set(TRACKED_OUTPUTS):
        fail("output_allowlist.tracked", "does not match the declared tracked outputs")
    if set(allowlist.get("untracked_runtime", ())) != set(UNTRACKED_OUTPUTS):
        fail("output_allowlist.untracked_runtime",
             "does not match the declared runtime outputs")

    if not manifest["retry_policy"].get("forbidden"):
        fail("retry_policy.forbidden", "the forbidden re-run behaviours are not declared")
    if "do NOT proceed to Arm B" not in manifest["failure_policy"].get(
            "arm_a_produces_no_valid_artefact", ""):
        fail("failure_policy.arm_a_produces_no_valid_artefact",
             "the Arm-A failure rule does not stop the experiment")
    environment = manifest["environment_policy"]
    if environment.get("expected_held_package_count") != 22:
        fail("environment_policy.expected_held_package_count",
             f"{environment.get('expected_held_package_count')!r} != 22")
    if environment.get("expected_nvidia_driver") != "580.178.04":
        fail("environment_policy.expected_nvidia_driver",
             f"{environment.get('expected_nvidia_driver')!r} != '580.178.04'")
    if not environment.get("no_reboot_between_pre_arm_a_and_post_arm_b"):
        fail("environment_policy.no_reboot_between_pre_arm_a_and_post_arm_b",
             "the no-reboot rule is not asserted")
    if manifest["episode"].get("scene_byte_identity") != "NOT_VERIFIED_REMOTE_STREAMED_ASSET":
        fail("episode.scene_byte_identity",
             "the remote-scene limitation is missing or weakened")

    if manifest.get("EXECUTION_STATUS") != "NOT_RUN" or manifest.get("arms_executed") != 0:
        fail("EXECUTION_STATUS", "a pre-execution manifest must declare that no arm ran")
    blob = canonical_json(manifest).lower()
    for forbidden in ("success_rate", "spl", "goal_reached", "outcome_value", "result_value"):
        if f'"{forbidden}"' in blob:
            fail("outcomes", f"the manifest carries an outcome field {forbidden!r}")

    return {
        "MANIFEST_VALID": "PASS" if not failures else "FAIL",
        "failures": failures,
        "checked_head": head or None,
        "manifest_digest": manifest_digest(manifest),
    }


def freeze_manifest(
    path: Path | str,
    repo_root: Path | str,
    *,
    head: str,
    frozen_at_utc: str,
) -> dict[str, Any]:
    """Write the manifest once, or prove a regeneration changed nothing.

    A timestamp must not move the identity, and a changed scientific field must
    not be absorbed silently. Both are the same mechanism the amendments use.
    """
    target = Path(path)
    root = Path(repo_root)
    candidate = build_manifest(root, head=head, frozen_at_utc=frozen_at_utc)

    if target.is_file():
        try:
            prior = json.loads(target.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return {"EXECUTION_MANIFEST": "REFUSED",
                    "reason": f"the existing manifest does not parse: {exc!r}"[:200]}
        candidate = build_manifest(
            root, head=head, frozen_at_utc=str(prior.get("frozen_at_utc", frozen_at_utc)))
        if manifest_digest(candidate) != manifest_digest(prior):
            return {
                "EXECUTION_MANIFEST": "REFUSED",
                "reason": (
                    "a frozen manifest already exists and the canonical payload differs. "
                    "It will not be silently overwritten; freeze an explicitly versioned "
                    "replacement instead"
                ),
                "existing_digest": manifest_digest(prior),
                "candidate_digest": manifest_digest(candidate),
            }
        refrozen = False
    else:
        refrozen = True

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(candidate, indent=2) + "\n")
    try:
        back = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"EXECUTION_MANIFEST": "REFUSED",
                "reason": f"the manifest did not read back: {exc!r}"[:200]}

    validation = validate_manifest(back, root, expected_head=head)
    if validation["MANIFEST_VALID"] != "PASS":
        return {"EXECUTION_MANIFEST": "REFUSED",
                "reason": "the written manifest did not validate",
                "validation": validation}

    return {
        "EXECUTION_MANIFEST": "FROZEN",
        "path": str(target),
        "sha256": sha256_file(target),
        "manifest_digest": manifest_digest(back),
        "bound_head": back["repository"]["head"],
        "frozen_at_utc": back["frozen_at_utc"],
        "first_freeze": refrozen,
        "validation": validation,
    }
