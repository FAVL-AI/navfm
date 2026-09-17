"""Freeze EXECUTION_MANIFEST_V4 and generate the live preflight against it.

Run after every tracked change is committed. The manifest names the commit both
arms execute from, and a tracked file cannot truthfully contain the SHA of the
commit that contains it -- so this writes to the already-ignored runtime
evidence tree and moves no HEAD.

What V4 adds over V3 is the rung whose absence cost an authorisation. V3
measured levels 1-3 by rehearsing the candidate manifest, which was real work
and all of it went through the rehearsal adapter; it then declared the real
adapter as a dotted path that nothing in the repository constructed. The
canonical Arm-A invocation V3 pinned could only return a structured refusal.

V4 refuses unless the authorised entry point is observed constructing the real
adapter and entering mode=REAL. That probe stops at MANIFEST_VALIDATED, the
stage before the one that writes a capture labelled PRE_ARM_A, so establishing
it costs no production artefact and starts no simulator.

None of this establishes that Isaac launches. The freeze says so in its own
output, because a gate that overstates what it measured is how the last two
refusals were earned.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.arm_environment_guard import (  # noqa: E402
    AUTHORITATIVE_CONTRACT_VERSION,
    check_contract,
    nvidia_hold_state,
)
from navfm.execution_manifest import UNTRACKED_OUTPUTS, canonical_worktree_state  # noqa: E402
from navfm.execution_manifest_v2 import (  # noqa: E402
    V7_REL,
    freeze_manifest_v4,
    generate_live_preflight,
    preflight_currency,
    validate_manifest_v4,
)
from navfm.intervention_runner import validate_only  # noqa: E402

MANIFEST = REPO / "runs/bo10/intervention/execution_manifest_v4.json"
PREFLIGHT = REPO / "runs/bo10/intervention/live_preflight_v4.json"
ARMS = ("ARM_A_CONTROL", "ARM_B_TREATMENT")
SUPERSEDED = ("V2", "V3", "V4", "V5", "V6")


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def main() -> int:
    print("=" * 68)
    print("EXECUTION_MANIFEST_V4 FREEZE")
    print("=" * 68)

    worktree = canonical_worktree_state(REPO)
    print(f"worktree            {worktree['WORKTREE_POLICY']}  "
          f"unexpected={worktree['unexpected']}")
    if worktree["WORKTREE_POLICY"] != "PASS":
        print("REFUSED: the tracked tree is not clean, so the HEAD to pin is ambiguous")
        return 1

    head = _git("rev-parse", "HEAD")
    print(f"FINAL_PRE_EXECUTION_HEAD_V4  {head}")

    if AUTHORITATIVE_CONTRACT_VERSION != "V7":
        print(f"REFUSED: the authoritative contract is "
              f"{AUTHORITATIVE_CONTRACT_VERSION}, and V4 requires V7")
        return 1

    contract = check_contract(REPO, AUTHORITATIVE_CONTRACT_VERSION)
    print(f"contract {AUTHORITATIVE_CONTRACT_VERSION}         "
          f"{contract['CONTRACT_SATISFIED']}  "
          f"drift={[d['field'] for d in contract['drift']]}")
    if contract["CONTRACT_SATISFIED"] != "PASS":
        print("REFUSED: the authoritative contract does not accept this source state")
        return 1

    for superseded in SUPERSEDED:
        result = check_contract(REPO, superseded)
        print(f"  {superseded} refuses this tree   "
              f"{result['CONTRACT_SATISFIED'] == 'FAIL'}  "
              f"({[d['field'].split('.')[-1] for d in result['drift']]})")
        if result["CONTRACT_SATISFIED"] != "FAIL":
            print(f"REFUSED: {superseded} accepts a tree it never froze")
            return 1

    holds = nvidia_hold_state()
    print(f"NVIDIA holds        {holds['HOLD_GUARD']}  held={holds['held_count']}  "
          f"driver={holds['loaded_driver_version']}")

    outcome = freeze_manifest_v4(
        MANIFEST, REPO, head=head,
        frozen_at_utc=_dt.datetime.now(_dt.UTC).isoformat())
    if outcome["EXECUTION_MANIFEST"] != "FROZEN":
        print(f"REFUSED: {outcome.get('reason')}")
        for key in ("unmet_executability_facts",):
            if outcome.get(key):
                print(f"  {key}: {outcome[key]}")
        for failure in (outcome.get("validation") or {}).get("failures", []):
            print(f"  - {failure['field']}: {failure['detail']}")
        return 1

    manifest = json.loads(MANIFEST.read_text())
    print()
    print(f"manifest            {MANIFEST.relative_to(REPO)}")
    print(f"sha256              {outcome['sha256']}")
    print(f"canonical digest    {outcome['manifest_digest']}")
    print(f"bound head          {outcome['bound_head']}")
    print(f"contract            {manifest['authoritative_contract']['version']}  "
          f"{manifest['authoritative_contract']['sha256'][:16]}...")

    readiness = manifest["executability"]
    print()
    print("executability (measured at freeze, not asserted):")
    for key in sorted(k for k, v in readiness.items() if isinstance(v, bool)):
        print(f"  {key:42s} {readiness[key]}")
    print(f"  {'arm_a_selector':42s} {readiness['arm_a_selector']}")
    print(f"  {'arm_b_selector':42s} {readiness['arm_b_selector']}")
    print(f"  {'behavioural_overrides':42s} {readiness['behavioural_overrides']}")
    real = manifest["real_mode"]
    print(f"  {'real mode entered':42s} {real['mode_entered']}")
    print(f"  {'real probe refused at':42s} {real['refused_at_stage']}")
    print(f"  {'production labels consumed':42s} "
          f"{real['production_labels_present'] or 'none'}")
    print()

    generated = generate_live_preflight(
        PREFLIGHT, REPO, manifest_path=MANIFEST, contract_rel=V7_REL,
        check_name="LIVE_EXECUTION_PREFLIGHT_V4")
    currency = preflight_currency(
        generated["record"], REPO, manifest_path=MANIFEST, contract_rel=V7_REL)
    print(f"live preflight      {PREFLIGHT.relative_to(REPO)}")
    print(f"sha256              {generated['sha256']}")
    print(f"PREFLIGHT_CURRENCY  {currency['PREFLIGHT_CURRENCY']}")
    for stale in currency["stale_fields"]:
        print(f"  stale {stale['field']}: bound {str(stale['bound'])[:16]}... "
              f"current {str(stale['current'])[:16]}...")
    print()

    after = _git("rev-parse", "HEAD")
    drift = canonical_worktree_state(REPO, allow_outputs=UNTRACKED_OUTPUTS)
    revalidated = validate_manifest_v4(manifest, REPO, expected_head=head)
    selftest = {arm: validate_only(MANIFEST, arm, REPO)["VALIDATE_ONLY"]
                for arm in ARMS}

    print(f"HEAD after freeze   {after[:12]}  matches manifest: "
          f"{after == manifest['repository']['head']}")
    print(f"tracked drift       {drift['WORKTREE_POLICY']}  "
          f"unexpected={drift['unexpected']}")
    print(f"revalidation        {revalidated['MANIFEST_VALID']}")
    for failure in revalidated.get("failures", []):
        print(f"  - {failure['field']}: {failure['detail']}")
    print(f"validate-only       {selftest}")

    ok = (after == manifest["repository"]["head"]
          and drift["WORKTREE_POLICY"] == "PASS"
          and revalidated["MANIFEST_VALID"] == "PASS"
          and currency["PREFLIGHT_CURRENCY"] == "PASS"
          and set(selftest.values()) == {"PASS"})
    print()
    print(f"EXECUTION_MANIFEST  {'FROZEN' if ok else 'INVALID'}")
    print(f"EXECUTION_GATE      {'READY_FOR_ARM_A_ATTEMPT' if ok else 'CLOSED'}")
    print("  meaning           the producer invocation sequence is rehearsed without")
    print("                    Isaac, AND the authorised entry point is observed")
    print("                    constructing the real adapter and entering mode=REAL")
    print("  NOT established   that Isaac launches, that Hospital loads, that the")
    print("                    render loop runs, or that the collector completes.")
    print("                    Only an actual Arm-A attempt establishes those")
    print(f"  canonical Arm A   {manifest['authorised_invocation']['arm_a']}")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
