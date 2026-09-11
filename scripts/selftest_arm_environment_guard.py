"""Self-test for PER_ARM_ENVIRONMENT_EQUIVALENCE_GUARD_V1.

Exercises the guard against the real machine without opening an intervention
episode. Labels are SELFTEST_A and SELFTEST_B: the four production labels are
reserved for four production captures, and spending one on a rehearsal would
leave an artefact that looks like part of the experiment.

The one thing here that cannot be tested on a fixture is the volatile-field
exclusion list. Whether a fresh preflight really changes only ``timestamp_utc``
and the nvidia-smi banner is a claim about this repository's emitter, so it is
checked the only way that settles it: run the emitter twice and compare.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.arm_environment_guard import (  # noqa: E402
    AUTHORITATIVE_CONTRACT_VERSION,
    CONTRACTS,
    PREFLIGHT_REL,
    PREFLIGHT_VOLATILE_FIELDS,
    arm_environment_equivalence,
    capture_arm_environment,
    check_contract,
    nvidia_hold_state,
    preflight_exception,
    preflight_identity,
    validate_pre_arm_environment,
    write_capture,
)

OUT_DIR = REPO / "runs/env_guard"
PREFLIGHT = REPO / PREFLIGHT_REL


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    )


#: How many preflight runs the volatile check uses. One run takes under a
#: second, so two back-to-back runs often land inside the same wall-clock
#: second and the nvidia-smi banner does not move. A check that then reported
#: CONFIRMED would have observed nothing and said so in the language of
#: evidence, so the sample is large enough to cross a second boundary and an
#: unobserved exclusion is reported as INCONCLUSIVE rather than confirmed.
VOLATILE_PROBE_RUNS = 4


def volatile_list_is_empirically_correct() -> dict[str, object]:
    """Run the preflight repeatedly. Two claims, tested separately.

    Soundness: nothing OUTSIDE the frozen exclusion list may differ between
    runs. Necessity: every field INSIDE it must actually be seen to differ, or
    the list is broader than the evidence supports and says so.
    """
    before = PREFLIGHT.read_bytes()
    shas: list[str] = []
    canonicals: list[str] = []
    payloads: list[dict[str, object]] = []
    for _ in range(VOLATILE_PROBE_RUNS):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/preflight_terminal_approach_intervention.py")],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO,
        )
        if proc.returncode != 0:
            PREFLIGHT.write_bytes(before)
            return {"VOLATILE_LIST": "INCONCLUSIVE", "reason": proc.stderr[-400:]}
        identity = preflight_identity(PREFLIGHT)
        shas.append(str(identity["FULL_PREFLIGHT_SHA"]))
        canonicals.append(str(identity["CANONICAL_PREFLIGHT_SHA"]))
        payloads.append(json.loads(PREFLIGHT.read_text()))

    observed: set[str] = set()
    first = payloads[0]
    for other in payloads[1:]:
        for key in set(first) | set(other):
            if first.get(key) == other.get(key):
                continue
            if key == "isaac_slot":
                a_slot = first.get("isaac_slot", {})
                b_slot = other.get("isaac_slot", {})
                assert isinstance(a_slot, dict) and isinstance(b_slot, dict)
                for sub in set(a_slot) | set(b_slot):
                    if a_slot.get(sub) != b_slot.get(sub):
                        observed.add(f"isaac_slot.{sub}")
            else:
                observed.add(key)
    PREFLIGHT.write_bytes(before)

    unexpected = sorted(f for f in observed if f not in PREFLIGHT_VOLATILE_FIELDS)
    unobserved = sorted(f for f in PREFLIGHT_VOLATILE_FIELDS if f not in observed)
    if unexpected:
        verdict = "REFUTED"
    elif unobserved:
        verdict = "INCONCLUSIVE_BREADTH"
    else:
        verdict = "CONFIRMED"
    return {
        "VOLATILE_LIST": verdict,
        "runs": VOLATILE_PROBE_RUNS,
        "frozen_exclusions": list(PREFLIGHT_VOLATILE_FIELDS),
        "observed_differences": sorted(observed),
        "unexpected_differences": unexpected,
        "exclusions_never_observed_to_vary": unobserved,
        "soundness": "PASS" if not unexpected else "FAIL",
        "necessity": "PASS" if not unobserved else "NOT_DEMONSTRATED",
        "full_sha_differs": len(set(shas)) > 1,
        "canonical_sha_stable": len(set(canonicals)) == 1,
        "full_shas": shas,
        "canonical_sha": canonicals[0],
    }


def main() -> int:
    head = _git("rev-parse", "HEAD").stdout.strip()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 62)
    print("SELF-TEST: PER_ARM_ENVIRONMENT_EQUIVALENCE_GUARD_V1")
    print("=" * 62)
    print(f"HEAD                {head[:12]}")
    print("labels              SELFTEST_A, SELFTEST_B (no production label used)")
    print()

    holds = nvidia_hold_state()
    print(f"NVIDIA hold guard   {holds['HOLD_GUARD']}  "
          f"held={holds['held_count']}/{holds['expected_held_count']}  "
          f"driver={holds['loaded_driver_version']}  "
          f"module={holds['loaded_module_version']}")
    if holds["reasons"]:
        for reason in holds["reasons"]:
            print(f"                    - {reason}")
    print()

    volatile = volatile_list_is_empirically_correct()
    print(f"volatile exclusions {volatile['VOLATILE_LIST']}")
    print(f"  observed diffs    {volatile.get('observed_differences')}")
    print(f"  unexpected        {volatile.get('unexpected_differences')}")
    print(f"  full sha differs  {volatile.get('full_sha_differs')}")
    print(f"  canonical stable  {volatile.get('canonical_sha_stable')}")
    print(f"  soundness         {volatile.get('soundness')}  "
          f"necessity {volatile.get('necessity')}")
    print()

    exception = preflight_exception(REPO, head)
    print(f"preflight exception {exception['PREFLIGHT_EXCEPTION']}  "
          f"dirty={exception['dirty_paths']}")
    print()

    a = capture_arm_environment(
        "SELFTEST_A", repo_root=REPO, frozen_head=head, worktree_allowed=())
    b = capture_arm_environment(
        "SELFTEST_B", repo_root=REPO, frozen_head=head, worktree_allowed=())
    sha_a = write_capture(a, OUT_DIR / "selftest_a.json")
    sha_b = write_capture(b, OUT_DIR / "selftest_b.json")

    print(f"SELFTEST_A          {a['CAPTURE_VALIDATION']}  critical={a['critical_digest'][:16]}...")
    print(f"SELFTEST_B          {b['CAPTURE_VALIDATION']}  critical={b['critical_digest'][:16]}...")
    print(f"  same environment  {a['critical_digest'] == b['critical_digest']}")
    print(f"  observational differ {a['observational'] != b['observational']}")
    print(f"  artefacts         {sha_a[:16]}... / {sha_b[:16]}...")
    print()

    # Four-way comparator against one real environment sampled four times. This
    # is a plumbing check, not an experiment: no arm ran between the samples.
    four = arm_environment_equivalence(
        {**a, "label": "PRE_ARM_A"},
        {**a, "label": "POST_ARM_A"},
        {**b, "label": "PRE_ARM_B"},
        {**b, "label": "POST_ARM_B"},
    )
    print(f"four-way comparator {four['ENVIRONMENT_EQUIVALENCE']}  "
          f"fields={four['fields_compared']}  mismatches={four['mismatch_count']}  "
          f"reboot={four['REBOOT_DETECTED']}")
    print()

    # V3_VALIDATION: the authoritative contract must accept the post-seam tree
    # while its predecessor must still refuse it. A successor that made V2 pass
    # again would have rewritten history rather than superseded it.
    contracts = {version: check_contract(REPO, version) for version in sorted(CONTRACTS)}
    for version, result in contracts.items():
        drift = [d["field"] for d in result["drift"]]
        marker = "AUTHORITATIVE" if version == AUTHORITATIVE_CONTRACT_VERSION else "historical"
        print(f"contract {version} ({marker:13s}) {result['CONTRACT_SATISFIED']:7s} "
              f"fields={result.get('fields_compared')}  drift={drift}")
    v2_refuses = contracts["V2"]["CONTRACT_SATISFIED"] == "FAIL"
    v3_accepts = contracts["V3"]["CONTRACT_SATISFIED"] == "PASS"
    print(f"V3 superseded without weakening V2: {v2_refuses and v3_accepts}")
    print()

    barrier = validate_pre_arm_environment(
        "SELFTEST_A", repo_root=REPO, frozen_head=head, fresh_preflight=False)
    print(f"pre-arm barrier     {barrier['PRE_ARM_BARRIER']}  "
          f"(contract {barrier.get('contract_version')})")
    for reason in barrier["reasons"]:
        print(f"                    - {reason}")

    barrier_v2 = validate_pre_arm_environment(
        "SELFTEST_A", repo_root=REPO, frozen_head=head, fresh_preflight=False,
        contract_version="V2")
    print(f"pre-arm barrier V2  {barrier_v2['PRE_ARM_BARRIER']}  "
          f"(expected REFUSED: V2 pins the pre-seam controller)")
    print()

    summary = {
        "check": "ARM_ENVIRONMENT_GUARD_SELFTEST",
        "artifact_semantics": "SELFTEST_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "head": head,
        "nvidia_hold_state": holds,
        "volatile_exclusion_check": volatile,
        "preflight_exception": exception,
        "selftest_a_digest": a["critical_digest"],
        "selftest_b_digest": b["critical_digest"],
        "same_environment": a["critical_digest"] == b["critical_digest"],
        "four_way": {
            "ENVIRONMENT_EQUIVALENCE": four["ENVIRONMENT_EQUIVALENCE"],
            "fields_compared": four["fields_compared"],
            "mismatch_count": four["mismatch_count"],
        },
        "pre_arm_barrier": barrier["PRE_ARM_BARRIER"],
        "authoritative_contract": AUTHORITATIVE_CONTRACT_VERSION,
        "contract_checks": {
            version: {
                "CONTRACT_SATISFIED": result["CONTRACT_SATISFIED"],
                "drift": [d["field"] for d in result["drift"]],
            }
            for version, result in contracts.items()
        },
        "pre_arm_barrier_against_v2": barrier_v2["PRE_ARM_BARRIER"],
        "v3_superseded_without_weakening_v2": v2_refuses and v3_accepts,
        "scene_equality_semantics": a["scene_identity"]["equality_semantics"],
        "scene_byte_identity": a["scene_identity"]["scene_byte_identity"],
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }
    sha = write_capture(
        summary,
        OUT_DIR / "selftest_summary.json",
        required_keys=("check", "four_way", "EXECUTION_STATUS", "ARM_A_EXECUTION"),
    )

    passed = (
        holds["HOLD_GUARD"] == "PASS"
        and volatile["VOLATILE_LIST"] == "CONFIRMED"
        and a["CAPTURE_VALIDATION"] == "PASS"
        and b["CAPTURE_VALIDATION"] == "PASS"
        and a["critical_digest"] == b["critical_digest"]
        and four["ENVIRONMENT_EQUIVALENCE"] == "PASS"
        and barrier["PRE_ARM_BARRIER"] == "PASS"
        and v2_refuses
        and v3_accepts
        and barrier_v2["PRE_ARM_BARRIER"] == "REFUSED"
    )
    print(f"summary artefact    runs/env_guard/selftest_summary.json  {sha[:16]}...")
    print(f"SELFTEST            {'PASS' if passed else 'FAIL'}")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
