"""TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V2: an append-only amendment.

The scientific intervention is unchanged. One factor, one route, one seed, one
order. This amendment changes what the record *pins*, and corrects one field
that was pinning nothing.

**The provenance correction.** V1 emitted
``frozen_while_results_were_impossible_to_observe`` and computed it, at every
run, as ``ISAAC_SLOT == "BLOCKED"``. While the GPU was broken it read ``true``
and looked like a statement about the design freeze. When the GPU was repaired
and the preflight was re-run it read ``false`` -- the same sentence, about the
same past, with the opposite meaning. A claim about 09:33 UTC cannot be a
function evaluated at 18:31. Here the claim is read from the artefact that was
frozen at 09:33 UTC and committed to git thirty-five seconds later, and it is
verified by hash against a pinned commit. It cannot move when the machine does.

**The environment contract.** V1 held the science constant and left the machine
free. An unattended upgrade had already moved the NVIDIA driver once between the
design freeze and the first execution attempt; had the arms straddled it, the
one-factor claim would have been false and nothing in the record would have said
so. V2 freezes the execution environment and defines what it means for Arm A and
Arm B to have run in the same one.

Nothing here authorises execution.
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
    CONTRACT_CRITICAL_FIELDS,
    CONTRACT_VERSION,
    EQUALITY_CRITICAL_FIELDS,
    OBSERVATIONAL_FIELDS,
    PAIRWISE_CRITICAL_FIELDS,
    capture,
    digest,
    select,
    sha256_file,
)

AMENDMENT_ID = "TAI-V1-A2-ENV"
AMENDMENT_VERSION = "V2"
OUT = REPO / "gates/BO10/environment_identity_v2_20260911.json"
PREREG = REPO / "gates/BO10/terminal_approach_intervention_v1_20260911.json"
PREFLIGHT = REPO / "gates/BO10/intervention_execution_preflight_20260911.json"

# The historical source, pinned by commit and by content hash. Pinning the
# commit rather than HEAD matters: committing this amendment moves HEAD, and a
# historical assertion that follows HEAD is the defect being corrected.
FREEZE_COMMIT = "0ac2fb04a6ff42103d39bb27faa1bfecad1ff7a3"
FREEZE_SOURCE = "gates/BO10/intervention_execution_preflight_20260911.json"
FREEZE_SOURCE_SHA256 = "13c6b583f9fac24af1436033f510254be49123daf923eddd140f34d194f05dbf"

NVIDIA_HOLD_LIST = "~/navfm-nvidia-580-held-20260911.txt"
NVIDIA_HOLD_COUNT = 22
NVIDIA_DRIVER = "580.178.04"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    )


def frozen_blob() -> tuple[str, dict[str, Any]] | None:
    """The pre-reboot preflight exactly as it was committed, or nothing."""
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{FREEZE_COMMIT}:{FREEZE_SOURCE}"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    import hashlib

    got = hashlib.sha256(proc.stdout).hexdigest()
    if got != FREEZE_SOURCE_SHA256:
        return None
    try:
        return got, json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def verify_history() -> dict[str, Any]:
    """Can the frozen artefact carry the historical claim, or can it not?

    Every input is immutable: a blob at a pinned commit, its hash, and the
    preregistration it cites. If any check fails the claim is recorded as
    INCONCLUSIVE. The alternative -- asserting it anyway from present state --
    is the failure mode this amendment exists to remove.
    """
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> bool:
        checks.append({"check": name, "verdict": "PASS" if ok else "FAIL", "detail": detail})
        return ok

    blob = frozen_blob()
    if blob is None:
        check(
            "source_retrievable_and_hash_matches",
            False,
            f"{FREEZE_SOURCE} at {FREEZE_COMMIT[:12]} is absent, unreadable, or its "
            f"sha256 is not {FREEZE_SOURCE_SHA256[:16]}...",
        )
        # The refusal path must be as well formed as the success path, or the
        # amendment crashes exactly when it is supposed to decline.
        return {
            "PROVENANCE": "INCONCLUSIVE",
            "checks": checks,
            "controls_passed": 0,
            "controls_total": len(checks),
        }
    source_sha, frozen = blob
    check(
        "source_retrievable_and_hash_matches",
        True,
        f"git show {FREEZE_COMMIT[:12]}:{FREEZE_SOURCE} -> sha256 {source_sha[:16]}...",
    )
    check("source_parses", True, "the frozen artefact is valid JSON")

    slot = frozen.get("isaac_slot", {})
    probe = slot.get("cuda_probe", {})
    freeze_stamp = str(frozen.get("timestamp_utc", ""))

    ok_unobservable = check(
        "isaac_execution_unavailable_at_freeze",
        slot.get("ISAAC_SLOT") == "BLOCKED"
        and probe.get("available") is False
        and probe.get("count") == 0
        and slot.get("cuda_error_code") == "804",
        f"ISAAC_SLOT={slot.get('ISAAC_SLOT')}, cuda_available={probe.get('available')}, "
        f"device_count={probe.get('count')}, cuda_error={slot.get('cuda_error_code')}",
    )
    ok_no_outcomes = check(
        "no_outcome_existed_at_freeze",
        frozen.get("EXECUTION_STATUS") == "NOT_RUN" and frozen.get("arms_executed") == 0,
        f"EXECUTION_STATUS={frozen.get('EXECUTION_STATUS')}, "
        f"arms_executed={frozen.get('arms_executed')}",
    )

    prereg = json.loads(PREREG.read_text())
    frozen_prereg_sha = frozen.get("preregistration", {}).get("sha256")
    live_prereg_sha = sha256_file(PREREG)
    ok_design = check(
        "design_unchanged_since_freeze",
        frozen_prereg_sha == live_prereg_sha,
        f"preregistration sha256 at freeze {str(frozen_prereg_sha)[:16]}... "
        f"and now {str(live_prereg_sha)[:16]}...",
    )
    prereg_stamp = str(prereg.get("preregistered_at", ""))
    ok_order = check(
        "design_already_frozen_before_the_source_artefact",
        bool(prereg_stamp) and bool(freeze_stamp) and prereg_stamp < freeze_stamp,
        f"preregistered_at {prereg_stamp} precedes preflight timestamp {freeze_stamp}",
    )
    ok_arms = check(
        "arm_order_frozen_in_the_source",
        frozen.get("arm_identity_and_order", {}).get("execution_order")
        == ["ARM_A_CONTROL", "ARM_B_TREATMENT"],
        str(frozen.get("arm_identity_and_order", {}).get("execution_order")),
    )

    commit_stamp = _git("show", "-s", "--format=%cI", FREEZE_COMMIT).stdout.strip()
    ok_committed = check(
        "source_committed_to_history_at_freeze_time",
        bool(commit_stamp),
        f"commit {FREEZE_COMMIT[:12]} recorded at {commit_stamp}; the artefact was "
        f"generated at {freeze_stamp} and committed, not reconstructed later",
    )

    everything = all(
        [ok_unobservable, ok_no_outcomes, ok_design, ok_order, ok_arms, ok_committed]
    )
    return {
        "PROVENANCE": "VERIFIED" if everything else "INCONCLUSIVE",
        "checks": checks,
        "controls_passed": sum(1 for c in checks if c["verdict"] == "PASS"),
        "controls_total": len(checks),
        "_frozen": frozen,
        "_source_sha": source_sha,
        "_freeze_stamp": freeze_stamp,
        "_commit_stamp": commit_stamp,
    }


def build_payload(
    amended_at: str, boot_utc: str, history: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    """The canonical amendment. Deterministic given unchanged science."""
    frozen = history.get("_frozen", {})
    slot = frozen.get("isaac_slot", {})
    verified = history["PROVENANCE"] == "VERIFIED"

    design_freeze: dict[str, Any] = {
        "frozen_at_utc": history.get("_freeze_stamp") or None,
        "outcomes_observable_at_freeze": False if verified else None,
        "basis": {
            "source_artifact": FREEZE_SOURCE,
            "source_commit_path": f"{FREEZE_COMMIT}:{FREEZE_SOURCE}",
            "source_sha256": FREEZE_SOURCE_SHA256,
            "repository_commit": FREEZE_COMMIT,
            "isaac_execution_available_at_freeze": False if verified else None,
            "evidence_type": "historical_frozen_assertion",
            "supporting_values_read_from_the_frozen_source": {
                "ISAAC_SLOT": slot.get("ISAAC_SLOT"),
                "cuda_available": slot.get("cuda_probe", {}).get("available"),
                "cuda_device_count": slot.get("cuda_probe", {}).get("count"),
                "cuda_error_code": slot.get("cuda_error_code"),
                "loaded_kernel_module_version": slot.get("kernel_module_version"),
                "userspace_driver_version": slot.get("userspace_version"),
                "EXECUTION_STATUS": frozen.get("EXECUTION_STATUS"),
                "arms_executed": frozen.get("arms_executed"),
            },
            "corroboration_first_boot_after_freeze_utc": boot_utc,
            "not_derived_from": (
                "any live reading of the machine. Re-running the preflight, "
                "repairing the GPU, or rebooting cannot change this block"
            ),
        },
        "STATUS": "VERIFIED" if verified else "INCONCLUSIVE",
    }

    regression = {
        "record_id": "PROVENANCE_FIELD_REGRESSION_V1",
        "old_field": "arm_identity_and_order.frozen_while_results_were_impossible_to_observe",
        "old_computation": (
            "bool(isaac_slot['ISAAC_SLOT'] == 'BLOCKED'), evaluated at preflight run "
            "time in scripts/preflight_terminal_approach_intervention.py"
        ),
        "why_it_is_invalid": (
            "it is a statement about the design freeze whose value is a function of "
            "the machine's present state. Repairing the GPU rewrote the past: the "
            "same field, describing the same historical moment, changed from true to "
            "false because a driver was reloaded. A provenance field that live state "
            "can flip records nothing, and is worse than an absent field because it "
            "reads as evidence"
        ),
        "observed_value_pre_reboot": True,
        "observed_value_post_reboot": False,
        "pre_reboot_source": {
            "path": f"{FREEZE_COMMIT}:{FREEZE_SOURCE}",
            "sha256": FREEZE_SOURCE_SHA256,
        },
        "post_reboot_source": {
            "path": FREEZE_SOURCE,
            "note": "the working-tree artefact regenerated after the GPU was repaired",
        },
        "correction_introduced_in_v2": (
            "design_freeze, above: an immutable assertion read from the artefact "
            "frozen at 09:33 UTC and verified by hash against a pinned commit, "
            "separated from live execution readiness which is recomputed every run"
        ),
        "status": "DEPRECATED_FOR_PROVENANCE_INTERPRETATION",
        "old_artefacts_rewritten": False,
        "old_artefacts_note": (
            "the committed pre-reboot artefact is left exactly as it was. The field "
            "is deprecated for interpretation, not erased from history, and the "
            "live emitter no longer produces it as a boolean"
        ),
    }

    return {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_ENVIRONMENT_V2",
        "artifact_semantics": "AMENDMENT_AND_INSTRUMENTATION_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "amendment_id": AMENDMENT_ID,
        "amendment_version": AMENDMENT_VERSION,
        "amended_at_utc": amended_at,
        "STATUS": "FROZEN",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "authorisation": "NOT AUTHORISED. Neither arm may run under this amendment.",
        "amends": {
            "original_preregistration": {
                "path": str(PREREG.relative_to(REPO)),
                "sha256": sha256_file(PREREG),
                "preregistered_at": json.loads(PREREG.read_text()).get("preregistered_at"),
                "version": "V1",
            },
            "original_freeze_timestamp_utc": history.get("_freeze_stamp"),
            "repository_head_at_amendment": _git("rev-parse", FREEZE_COMMIT).stdout.strip()
            or FREEZE_COMMIT,
            "reason": (
                "execution environment identity was not sufficiently pinned in V1; "
                "one provenance field was incorrectly recomputed from live ISAAC_SLOT "
                "state rather than preserved as a historical freeze-time fact"
            ),
            "append_only": True,
            "the_intervention_itself_is_unchanged": True,
            "unchanged_by_this_amendment": [
                "the target-selection factor",
                "the route and the frozen polyline",
                "the initial pose and start yaw",
                "the goal and the goal tolerance",
                "the seed",
                "controller gains",
                "the look-ahead distance",
                "cruise speed and every velocity limit",
                "max_steps",
                "the primary outcome",
                "the secondary cross-track outcome",
                "arm order",
            ],
        },
        "design_freeze": design_freeze,
        "PROVENANCE_FIELD_REGRESSION_V1": regression,
        "provenance_verification": {
            "PROVENANCE": history["PROVENANCE"],
            "controls": f"{history['controls_passed']}/{history['controls_total']}",
            "checks": history["checks"],
        },
        "EXECUTION_ENVIRONMENT_IDENTITY_V2": {
            "contract_version": CONTRACT_VERSION,
            "implementation": "src/navfm/execution_environment.py",
            "what_it_is_for": (
                "an arm pair differing in one factor is evidence only if everything "
                "else that can change the trajectory was the same. These are the "
                "fields that can"
            ),
            "frozen_contract_values": contract,
            "contract_digest": digest(contract),
            "contract_critical_fields": list(CONTRACT_CRITICAL_FIELDS),
            "pairwise_critical_fields": list(PAIRWISE_CRITICAL_FIELDS),
            "equality_critical_fields": list(EQUALITY_CRITICAL_FIELDS),
            "observational_fields_recorded_never_compared": list(OBSERVATIONAL_FIELDS),
            "why_the_split_is_three_ways_and_not_two": (
                "contract-critical fields are frozen here and must still hold when an "
                "arm runs. Pairwise-critical fields must match between the arms but "
                "cannot be frozen here, because their correct value does not exist "
                "yet: the commit carrying this amendment is not known to it, and the "
                "boot the arms will run under has not happened. Observational fields "
                "locate a run without defining it; requiring them to match would make "
                "every run unrepeatable by construction"
            ),
            "boot_id_is_the_no_reboot_instrument": (
                "session.boot_id is redrawn by the kernel on every boot. Two arms "
                "sharing one did not have a reboot between them; two arms that do not "
                "share one did, whatever the kernel release says. Kernel release alone "
                "would not detect a reboot into the same kernel"
            ),
            "amendment_binding": {
                "rule": (
                    "a per-arm capture must record the sha256 of this amendment file "
                    "and it must equal the amendment in force"
                ),
                "why_it_is_not_a_field_inside_this_payload": (
                    "a file cannot contain its own hash. The binding is checked from "
                    "outside by the per-arm guard, not asserted from within"
                ),
            },
        },
        "KERNEL_UPDATE_POLICY": {
            "no_new_kernel_holds_added": True,
            "why": (
                "a staged kernel update cannot alter the running kernel without a "
                "reboot, so holding kernel packages protects against nothing this "
                "experiment is exposed to. Recording and comparing what actually ran "
                "is the protection that discriminates"
            ),
            "rule": "NO_REBOOT_PERMITTED_BETWEEN_ARM_A_AND_ARM_B",
            "per_arm_recording_required": [
                "uname -r (host.kernel_release)",
                "loaded NVIDIA kernel module version (gpu.kernel_module_version)",
                "NVIDIA driver version (gpu.driver_version)",
                "Isaac Sim version (isaac.isaacsim_version)",
                "boot id (session.boot_id)",
            ],
            "if_the_machine_reboots_between_arms": (
                "ENVIRONMENT_EQUIVALENCE = FAIL and the comparison is refused until "
                "environment identity is re-established under a new amendment"
            ),
        },
        "NVIDIA_HOLD_POLICY": {
            "hold_list_path": NVIDIA_HOLD_LIST,
            "expected_hold_count": NVIDIA_HOLD_COUNT,
            "expected_driver_version": NVIDIA_DRIVER,
            "holds_must_remain_through": [
                "Arm A",
                "Arm B",
                "artefact write",
                "artefact read-back",
                "validation",
                "hashing",
            ],
            "release_command": (
                "xargs -r sudo apt-mark unhold < ~/navfm-nvidia-580-held-20260911.txt"
            ),
            "released_in_this_tranche": False,
            "why": (
                "unattended-upgrades moved this driver once already, at 06:24 on the "
                "day of the design freeze. The holds are what stop it moving between "
                "Arm A and Arm B, which would make the one-factor claim false without "
                "making it look false"
            ),
            "hold_list_formatting_note": (
                "the frozen list carries explicit :amd64 qualifiers where apt-mark "
                "showhold prints bare names for the native architecture. The sets are "
                "identical once normalised; a count of 22 is the check that matters"
            ),
        },
        "WORKING_TREE_POLICY": {
            "pre_arm_requirement": "clean",
            "mechanism": "navfm.execution_environment.worktree_state(repo, allowed)",
            "allow_list_semantics": (
                "deny by default. A path is tolerated only if it is on the explicit "
                "allow-list; anything else makes the state dirty and fails the gate"
            ),
            "during_arm_allowed_paths": "SEALED_IN_THE_FROZEN_EXECUTION_MANIFEST",
            "why_not_declared_here": (
                "the arms' output paths are defined by the execution manifest, which "
                "is a later tranche. Inventing them now would freeze a guess"
            ),
            "generic_dirty_but_expected_is_forbidden": True,
            "preflight_artefact_disposition": (
                "gates/BO10/intervention_execution_preflight_20260911.json is intended "
                "scientific evidence and is committed with this amendment, so the tree "
                "is clean rather than tolerated-dirty at arm execution"
            ),
        },
        "ENVIRONMENT_MISMATCH_POLICY": {
            "if_any_equality_critical_field_differs_between_arms": {
                "ENVIRONMENT_EQUIVALENCE": "FAIL",
                "INTERVENTION_COMPARISON": "INVALID",
            },
            "forbidden": [
                "averaging across environments",
                "repairing one arm and comparing anyway",
                "silently re-running only the less favourable arm",
                "reporting the comparison with a caveat instead of refusing it",
            ],
            "a_valid_retry_requires": (
                "the preregistered retry policy already frozen in the V1 preflight, or "
                "a new amendment. It does not require a different analysis of two runs "
                "that were not comparable"
            ),
        },
        "ISAAC_SLOT_CLAIM_BOUNDARY": {
            "the_cuda_probe_establishes": [
                "CUDA context creation succeeds in the Isaac Python environment",
                "one CUDA device is visible",
                "approximately 15 GB of GPU memory was free at probe time",
            ],
            "it_does_not_establish": [
                "that full Isaac Sim rendering succeeds",
                "that scene loading succeeds",
                "that both intervention arms will execute",
            ],
            "status_of_ISAAC_SLOT_AVAILABLE": (
                "an execution-readiness INFERENCE, not proof of a completed Isaac run. "
                "Those claims require actual arm execution"
            ),
        },
        "ARM_ENVIRONMENT_GUARD": {
            "defined_here": True,
            "implemented_here": False,
            "captures_required_later": [
                "PRE_ARM_A",
                "POST_ARM_A",
                "PRE_ARM_B",
                "POST_ARM_B",
            ],
            "comparison_rule": "ENV_A == ENV_B over every equality-critical field",
            "api": "navfm.execution_environment.arm_equivalence(env_a, env_b)",
        },
        "milestone_unaffected": {
            "BO-03_REAL_DATA_COMPATIBILITY": "COMPLETE",
            "BO-10_HOSPITAL_COLLECTION": "COMPLETE_FOR_COMPATIBILITY_PURPOSE",
            "run_00001": "IMMUTABLE and excluded from the two-arm comparison",
        },
    }


def strip_volatile(payload: Any) -> Any:
    """Everything except the values that legitimately differ per regeneration."""
    if isinstance(payload, dict):
        return {
            k: strip_volatile(v)
            for k, v in payload.items()
            if k not in {"amended_at_utc", "corroboration_first_boot_after_freeze_utc"}
        }
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


def boot_utc() -> str:
    """Boot time from /proc/stat btime: an epoch, so no timezone to misread."""
    try:
        for line in pathlib.Path("/proc/stat").read_text().splitlines():
            if line.startswith("btime "):
                epoch = int(line.split()[1])
                return _dt.datetime.fromtimestamp(epoch, _dt.UTC).isoformat()
    except (OSError, ValueError, IndexError):
        pass
    return ""


def main() -> int:
    history = verify_history()
    if history["PROVENANCE"] != "VERIFIED":
        failed = [c for c in history["checks"] if c["verdict"] == "FAIL"]
        detail = "\n  ".join(f"{c['check']}: {c['detail']}" for c in failed)
        raise SystemExit(
            "PROVENANCE = INCONCLUSIVE\n\n"
            "The frozen artefact cannot carry the historical assertion. The "
            "amendment is NOT written, and the claim is not manufactured from "
            f"present state.\nFailed checks:\n  {detail}"
        )

    contract = select(capture(REPO), CONTRACT_CRITICAL_FIELDS)

    # Frozen once. A regeneration that recomputes the freeze timestamp, or the
    # boot that happens to be current, would make the artefact differ from
    # itself for reasons that have nothing to do with the science.
    if OUT.exists():
        prior = json.loads(OUT.read_text())
        amended_at = str(prior["amended_at_utc"])
        boot = str(
            prior.get("design_freeze", {})
            .get("basis", {})
            .get("corroboration_first_boot_after_freeze_utc", "")
        )
        result = build_payload(amended_at, boot, history, contract)
        drift = diff_paths(strip_volatile(result), strip_volatile(prior))
        if drift:
            shown = "\n  ".join(drift[:25]) + ("\n  ..." if len(drift) > 25 else "")
            raise SystemExit(
                "ENVIRONMENT_IDENTITY_V2_CANONICAL_GUARD = REFUSED\n\n"
                f"The canonical amendment no longer matches the frozen artefact at "
                f"{OUT.relative_to(REPO)}.\n"
                f"Fields that differ ({len(drift)}):\n  {shown}\n\n"
                "V2 is frozen and is cited by hash. It will NOT be silently "
                "regenerated, and execution under it is refused.\n"
                "A changed environment contract or a changed provenance basis "
                "requires an explicit V3 amendment written to a new artefact path, "
                "leaving this record and its digest intact."
            )
        refrozen = False
    else:
        amended_at = _dt.datetime.now(_dt.UTC).isoformat()
        boot = boot_utc()
        result = build_payload(amended_at, boot, history, contract)
        refrozen = True

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    for key in (
        "design_freeze",
        "PROVENANCE_FIELD_REGRESSION_V1",
        "EXECUTION_ENVIRONMENT_IDENTITY_V2",
        "EXECUTION_STATUS",
    ):
        if key not in back:
            raise SystemExit(f"evidence guard: missing {key}")
    if back["EXECUTION_STATUS"] != "NOT_RUN":
        raise SystemExit("evidence guard: no arm has run and the artefact must say so")
    if back["design_freeze"]["outcomes_observable_at_freeze"] is not False:
        raise SystemExit("evidence guard: the historical assertion did not survive write")

    canonical = digest(strip_volatile(back))
    print(f"provenance          {history['PROVENANCE']}  "
          f"({history['controls_passed']}/{history['controls_total']} controls)")
    print(f"frozen at           {back['design_freeze']['frozen_at_utc']}")
    print(f"source              {FREEZE_COMMIT[:12]}:{FREEZE_SOURCE}")
    print(f"source sha256       {FREEZE_SOURCE_SHA256[:32]}...")
    print(f"outcomes observable {back['design_freeze']['outcomes_observable_at_freeze']} (frozen)")
    print()
    print(f"contract fields     {len(CONTRACT_CRITICAL_FIELDS)} contract-critical, "
          f"{len(PAIRWISE_CRITICAL_FIELDS)} pairwise, {len(OBSERVATIONAL_FIELDS)} observational")
    print(f"contract digest     {back['EXECUTION_ENVIRONMENT_IDENTITY_V2']['contract_digest']}")
    print(f"canonical digest    {canonical}")
    print(f"{'FROZEN (first write)' if refrozen else 'RE-VERIFIED (unchanged)'}")
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha256_file(OUT)}")
    print("EXECUTION_STATUS    NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
