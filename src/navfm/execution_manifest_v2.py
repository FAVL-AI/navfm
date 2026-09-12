"""EXECUTION_MANIFEST_V2: a manifest that must be runnable, not merely correct.

V1 froze an exact output allow-list, a narrow worktree policy, arm order,
selector assignment and every scientific constant, and it validated. It was also
unrunnable: nothing wired the selector into the collector, and no runner existed
to produce the paths it declared. The manifest established declaration
integrity and said nothing about execution-path existence, so it was correct on
paper and impossible to execute at the same time.

V2 requires both. Every REQUIRED declared output must resolve to a real
producer, the runner must exist and import, both arm dispatches must resolve,
and a structural validate-only self-test must pass before the manifest will
freeze. None of that claims the simulator will work -- it claims the experiment
is invokable, which is exactly the thing V1 never checked.

The live preflight is separated from its implementation for the same reason the
manifest is not committed. A tracked artefact that records the current HEAD goes
stale the moment it is committed, because committing moves HEAD. So the
implementation is tracked and pinned, and the result is runtime evidence
generated after the final commit, binding the HEAD it actually describes.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from navfm.execution_environment import digest, sha256_file
from navfm.execution_manifest import (
    ARM_ORDER,
    build_manifest,
    manifest_digest,
    validate_manifest,
)
from navfm.intervention_runner import (
    PRODUCER_MAP,
    RUNNER_ENTRY_POINT,
    executability,
    validate_only,
)

__all__ = [
    "MANIFEST_V2_VERSION",
    "PREFLIGHT_CURRENCY_FIELDS",
    "build_manifest_v2",
    "freeze_manifest_v2",
    "generate_live_preflight",
    "preflight_currency",
    "validate_manifest_v2",
]

MANIFEST_V2_VERSION = "EXECUTION_MANIFEST_V2"
AUTHORITATIVE_CONTRACT_V2 = "V5"
V5_REL = "gates/BO10/environment_identity_v5_20260912.json"

#: What a live preflight must bind for it to describe THIS tree. A preflight
#: that binds an older value is stale, not passing: it is a true statement about
#: a repository that no longer exists.
PREFLIGHT_CURRENCY_FIELDS: tuple[str, ...] = (
    "repository_head",
    "authoritative_contract_sha256",
    "manifest_sha256",
    "runner_sha256",
    "collect_sha256",
    "control_sha256",
    "target_selection_sha256",
)

_SOURCES: dict[str, str] = {
    "runner_sha256": RUNNER_ENTRY_POINT,
    "collect_sha256": "src/navfm/isaac/collect.py",
    "control_sha256": "src/navfm/control.py",
    "target_selection_sha256": "src/navfm/target_selection.py",
}


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def build_manifest_v2(
    repo_root: Path | str, *, head: str, frozen_at_utc: str,
    manifest_path: str,
) -> dict[str, Any]:
    """V1's declarations, plus the executability contract V1 lacked."""
    root = Path(repo_root)
    base = build_manifest(root, head=head, frozen_at_utc=frozen_at_utc)
    base["manifest_version"] = MANIFEST_V2_VERSION
    base["supersedes"] = {
        "version": "EXECUTION_MANIFEST_V1",
        "path": "runs/bo10/intervention/execution_manifest.json",
        "not_overwritten": True,
        "limitation": (
            "V1's source HEAD was correctly frozen, but it declared outputs without "
            "establishing that any code could produce them. It is kept as history"
        ),
    }
    base["authoritative_contract"] = {
        "version": AUTHORITATIVE_CONTRACT_V2,
        "path": V5_REL,
        "sha256": sha256_file(root / V5_REL),
        "no_automatic_fallback": (
            "execution requires V5. Older contracts remain checkable against the state "
            "they froze and are never substituted for V5"
        ),
    }
    readiness = executability(base, root)
    base["executability"] = {
        "runner_resolved": readiness["runner_resolved"],
        "runner_sha_matches": readiness["runner_sha_present"],
        "collector_resolved": readiness["collector_resolved"],
        "selector_wiring_present": readiness["selector_wiring_present"],
        "selectors_resolved": readiness["selectors_resolved"],
        "arm_a_dispatch_valid": readiness["arm_a_dispatch_valid"],
        "arm_b_dispatch_valid": readiness["arm_b_dispatch_valid"],
        "required_output_producers_complete": readiness[
            "required_output_producers_complete"],
        "runner_entry_point": readiness["runner_entry_point"],
        "runner_sha256": readiness["runner_sha256"],
        "runner_module": readiness["runner_module"],
        "collector_entry_point": readiness["collector_entry_point"],
        "supported_arms": readiness["supported_arms"],
        "selector_registry": readiness["selector_registry"],
        "claim_boundary": readiness["claim_boundary"],
    }
    base["producer_map"] = {
        path: {"stage": stage, "producer": producer, "required": required}
        for path, (stage, producer, required) in sorted(PRODUCER_MAP.items())
    }
    base["authorised_invocation"] = {
        "arm_a": f"python {RUNNER_ENTRY_POINT} --manifest {manifest_path} "
                 "--arm ARM_A_CONTROL",
        "arm_b": f"python {RUNNER_ENTRY_POINT} --manifest {manifest_path} "
                 "--arm ARM_B_TREATMENT",
        "validate_only_suffix": "--validate-only",
        "no_other_invocation_is_authorised": (
            "scientific values come from this manifest and are refused on the command "
            "line, so there is no ad-hoc invocation to construct later"
        ),
    }
    base["preflight_currency_requirement"] = {
        "required_fields": list(PREFLIGHT_CURRENCY_FIELDS),
        "rule": (
            "a live preflight binding any older value is STALE_PREFLIGHT, not PASS. "
            "It is a true statement about a repository that no longer exists"
        ),
        "generated_after_the_final_tracked_commit": True,
        "location": "runs/bo10/intervention/live_preflight_v2.json",
    }
    base["manifest_self_path"] = manifest_path
    return base


def validate_manifest_v2(
    manifest: Mapping[str, Any], repo_root: Path | str, *,
    expected_head: str | None = None,
) -> dict[str, Any]:
    """V1's field validation, plus every executability fact."""
    root = Path(repo_root)
    base = validate_manifest(manifest, root, expected_head=expected_head)
    failures = list(base["failures"])

    def fail(field: str, detail: str) -> None:
        failures.append({"field": field, "detail": detail})

    if manifest.get("manifest_version") != MANIFEST_V2_VERSION:
        # validate_manifest already flagged the version against V1's constant;
        # replace that with the V2 expectation rather than reporting both.
        failures = [f for f in failures if f["field"] != "manifest_version"]
        if manifest.get("manifest_version") != MANIFEST_V2_VERSION:
            fail("manifest_version",
                 f"{manifest.get('manifest_version')!r} != {MANIFEST_V2_VERSION!r}")
    else:
        failures = [f for f in failures if f["field"] != "manifest_version"]

    if manifest.get("authoritative_contract", {}).get("version") != AUTHORITATIVE_CONTRACT_V2:
        failures = [f for f in failures if f["field"] != "authoritative_contract.version"]
        fail("authoritative_contract.version",
             f"{manifest.get('authoritative_contract', {}).get('version')!r} != "
             f"{AUTHORITATIVE_CONTRACT_V2!r}")
    else:
        failures = [f for f in failures if f["field"] != "authoritative_contract.version"]

    readiness = manifest.get("executability")
    if not isinstance(readiness, Mapping):
        fail("executability", "the manifest declares no executability section")
    else:
        for key in ("runner_resolved", "collector_resolved", "selector_wiring_present",
                    "selectors_resolved", "arm_a_dispatch_valid", "arm_b_dispatch_valid",
                    "required_output_producers_complete"):
            if readiness.get(key) is not True:
                fail(f"executability.{key}", f"{readiness.get(key)!r} is not True")
        declared_runner = readiness.get("runner_sha256")
        actual_runner = sha256_file(root / RUNNER_ENTRY_POINT)
        if declared_runner != actual_runner:
            fail("executability.runner_sha256",
                 f"manifest says {str(declared_runner)[:16]}..., file is "
                 f"{str(actual_runner)[:16]}...")

    producers = manifest.get("producer_map")
    if not isinstance(producers, Mapping) or not producers:
        fail("producer_map", "no producer map is declared")
    else:
        allowlist = manifest.get("output_allowlist", {})
        declared = set(allowlist.get("tracked", ())) | set(
            allowlist.get("untracked_runtime", ()))
        for path in declared:
            entry = producers.get(path)
            if entry is None:
                fail("producer_map", f"no producer declared for required output {path!r}")
            elif entry.get("required") and not entry.get("producer"):
                fail("producer_map", f"required output {path!r} names no producer")
        for path in producers:
            if path not in declared:
                fail("producer_map",
                     f"producer declared for undeclared output {path!r}")

    if not manifest.get("preflight_currency_requirement", {}).get("required_fields"):
        fail("preflight_currency_requirement", "no currency fields are required")
    if not manifest.get("authorised_invocation", {}).get("arm_a"):
        fail("authorised_invocation", "no authorised invocation is recorded")

    return {
        "MANIFEST_VALID": "PASS" if not failures else "FAIL",
        "failures": failures,
        "checked_head": base.get("checked_head"),
        "manifest_digest": manifest_digest(manifest),
    }


def freeze_manifest_v2(
    path: Path | str, repo_root: Path | str, *, head: str, frozen_at_utc: str,
) -> dict[str, Any]:
    """Write V2 once. Refuses unless every executability fact holds."""
    target = Path(path)
    root = Path(repo_root)
    # A manifest written outside the repository (a test fixture, say) has no
    # repo-relative spelling. Record what it is rather than raising: the path is
    # descriptive here, and crashing on it would make the freeze untestable.
    try:
        relative = str(target.relative_to(root))
    except ValueError:
        relative = str(target)

    candidate = build_manifest_v2(
        root, head=head, frozen_at_utc=frozen_at_utc, manifest_path=relative)
    readiness = candidate["executability"]
    unmet = [k for k, v in readiness.items() if isinstance(v, bool) and not v]
    if unmet:
        return {"EXECUTION_MANIFEST": "REFUSED",
                "reason": "the manifest is not execution-ready",
                "unmet_executability_facts": unmet}

    if target.is_file():
        try:
            prior = json.loads(target.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return {"EXECUTION_MANIFEST": "REFUSED",
                    "reason": f"the existing manifest does not parse: {exc!r}"[:200]}
        candidate = build_manifest_v2(
            root, head=head, manifest_path=relative,
            frozen_at_utc=str(prior.get("frozen_at_utc", frozen_at_utc)))
        if manifest_digest(candidate) != manifest_digest(prior):
            return {"EXECUTION_MANIFEST": "REFUSED",
                    "reason": ("a frozen V2 manifest already exists and the canonical "
                               "payload differs. Freeze an explicitly versioned "
                               "replacement rather than overwriting it"),
                    "existing_digest": manifest_digest(prior),
                    "candidate_digest": manifest_digest(candidate)}
        first = False
    else:
        first = True

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(candidate, indent=2) + "\n")
    back = json.loads(target.read_text())
    validation = validate_manifest_v2(back, root, expected_head=head)
    if validation["MANIFEST_VALID"] != "PASS":
        return {"EXECUTION_MANIFEST": "REFUSED",
                "reason": "the written manifest did not validate",
                "validation": validation}

    selftest = {
        arm: validate_only(target, arm, root)["VALIDATE_ONLY"] for arm in ARM_ORDER}
    if set(selftest.values()) != {"PASS"}:
        return {"EXECUTION_MANIFEST": "REFUSED",
                "reason": "the validate-only self-test did not pass for both arms",
                "validate_only_selftest": selftest}

    return {
        "EXECUTION_MANIFEST": "FROZEN",
        "path": str(target), "sha256": sha256_file(target),
        "manifest_digest": manifest_digest(back),
        "bound_head": back["repository"]["head"],
        "frozen_at_utc": back["frozen_at_utc"],
        "first_freeze": first,
        "validation": validation,
        "validate_only_selftest": selftest,
    }


def generate_live_preflight(
    path: Path | str, repo_root: Path | str, *, manifest_path: Path | str,
) -> dict[str, Any]:
    """Runtime preflight, generated after the final commit, binding this tree."""
    root = Path(repo_root)
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text())
    bound = {
        "repository_head": _git(root, "rev-parse", "HEAD"),
        "authoritative_contract_sha256": sha256_file(root / V5_REL),
        "manifest_sha256": sha256_file(manifest_file),
    }
    for key, rel in _SOURCES.items():
        bound[key] = sha256_file(root / rel)

    record = {
        "check": "LIVE_EXECUTION_PREFLIGHT_V2",
        "artifact_semantics": "RUNTIME_PREFLIGHT_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "generated_at_utc": _dt.datetime.now(_dt.UTC).isoformat(),
        "bound": bound,
        "sources": dict(_SOURCES),
        "manifest_path": str(manifest_file),
        "manifest_version": manifest.get("manifest_version"),
        "why_this_is_runtime_evidence": (
            "a tracked artefact recording the current HEAD goes stale the moment it "
            "is committed, because committing moves HEAD. The implementation is "
            "tracked and pinned; the result is generated afterwards and binds the "
            "HEAD it actually describes"
        ),
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n")
    back = json.loads(target.read_text())
    return {"path": str(target), "sha256": sha256_file(target),
            "digest": digest(back["bound"]), "record": back}


def preflight_currency(
    preflight: Mapping[str, Any], repo_root: Path | str, *,
    manifest_path: Path | str,
) -> dict[str, Any]:
    """Does this preflight describe THIS tree, or an older one?"""
    root = Path(repo_root)
    manifest_file = Path(manifest_path)
    bound = preflight.get("bound")
    if not isinstance(bound, Mapping):
        return {"PREFLIGHT_CURRENCY": "STALE_PREFLIGHT",
                "reason": "the preflight binds nothing", "stale_fields": []}

    expected = {
        "repository_head": _git(root, "rev-parse", "HEAD"),
        "authoritative_contract_sha256": sha256_file(root / V5_REL),
        "manifest_sha256": sha256_file(manifest_file),
    }
    for key, rel in _SOURCES.items():
        expected[key] = sha256_file(root / rel)

    stale = [
        {"field": field, "bound": bound.get(field), "current": expected[field]}
        for field in PREFLIGHT_CURRENCY_FIELDS
        if bound.get(field) != expected[field]
    ]
    return {
        "PREFLIGHT_CURRENCY": "PASS" if not stale else "STALE_PREFLIGHT",
        "fields_checked": list(PREFLIGHT_CURRENCY_FIELDS),
        "stale_fields": stale,
        "semantics": (
            "a preflight binding an older value is stale, not passing. It is a true "
            "statement about a repository that no longer exists"
        ),
    }
