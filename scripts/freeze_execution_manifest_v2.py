"""Freeze EXECUTION_MANIFEST_V2 and generate the live preflight against it.

Run after every tracked change is committed. The manifest names the commit both
arms execute from, and a tracked file cannot truthfully contain the SHA of the
commit that contains it -- so this writes to the already-ignored runtime
evidence tree and moves no HEAD.

Unlike V1, the freeze refuses unless the experiment is actually invokable: the
runner must resolve, both arms must dispatch, the selector must reach the
collector, every required output must have a producer, and a structural
validate-only self-test must pass for both arms. V1 checked none of that, which
is how it froze a manifest that could not be run.

The live preflight is generated last, after the manifest exists, so it can bind
the manifest's own hash alongside the HEAD and the source identities. A preflight
generated before its manifest could not name it.
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
    freeze_manifest_v2,
    generate_live_preflight,
    preflight_currency,
    validate_manifest_v2,
)
from navfm.intervention_runner import validate_only  # noqa: E402

MANIFEST = REPO / "runs/bo10/intervention/execution_manifest_v2.json"
PREFLIGHT = REPO / "runs/bo10/intervention/live_preflight_v2.json"


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def main() -> int:
    print("=" * 68)
    print("EXECUTION_MANIFEST_V2 FREEZE")
    print("=" * 68)

    worktree = canonical_worktree_state(REPO)
    print(f"worktree            {worktree['WORKTREE_POLICY']}  "
          f"unexpected={worktree['unexpected']}")
    if worktree["WORKTREE_POLICY"] != "PASS":
        print("REFUSED: the tracked tree is not clean, so the HEAD to pin is ambiguous")
        return 1

    head = _git("rev-parse", "HEAD")
    print(f"FINAL_PRE_EXECUTION_HEAD_V2  {head}")

    contract = check_contract(REPO, AUTHORITATIVE_CONTRACT_VERSION)
    print(f"contract {AUTHORITATIVE_CONTRACT_VERSION}         "
          f"{contract['CONTRACT_SATISFIED']}  "
          f"drift={[d['field'] for d in contract['drift']]}")
    if contract["CONTRACT_SATISFIED"] != "PASS":
        print("REFUSED: the authoritative contract does not accept this source state")
        return 1

    holds = nvidia_hold_state()
    print(f"NVIDIA holds        {holds['HOLD_GUARD']}  held={holds['held_count']}  "
          f"driver={holds['loaded_driver_version']}")

    outcome = freeze_manifest_v2(
        MANIFEST, REPO, head=head,
        frozen_at_utc=_dt.datetime.now(_dt.UTC).isoformat())
    if outcome["EXECUTION_MANIFEST"] != "FROZEN":
        print(f"REFUSED: {outcome.get('reason')}")
        for key in ("unmet_executability_facts", "validate_only_selftest"):
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
    print(f"selftest            {outcome['validate_only_selftest']}")
    readiness = manifest["executability"]
    for key in sorted(k for k, v in readiness.items() if isinstance(v, bool)):
        print(f"  {key:42s} {readiness[key]}")
    print()

    generated = generate_live_preflight(PREFLIGHT, REPO, manifest_path=MANIFEST)
    currency = preflight_currency(generated["record"], REPO, manifest_path=MANIFEST)
    print(f"live preflight      {PREFLIGHT.relative_to(REPO)}")
    print(f"sha256              {generated['sha256']}")
    print(f"PREFLIGHT_CURRENCY  {currency['PREFLIGHT_CURRENCY']}")
    for stale in currency["stale_fields"]:
        print(f"  stale {stale['field']}: bound {str(stale['bound'])[:16]}... "
              f"current {str(stale['current'])[:16]}...")
    print()

    after = _git("rev-parse", "HEAD")
    drift = canonical_worktree_state(REPO, allow_outputs=UNTRACKED_OUTPUTS)
    revalidated = validate_manifest_v2(manifest, REPO, expected_head=head)
    selftest = {arm: validate_only(MANIFEST, arm, REPO)["VALIDATE_ONLY"]
                for arm in ("ARM_A_CONTROL", "ARM_B_TREATMENT")}

    print(f"HEAD after freeze   {after[:12]}  matches manifest: "
          f"{after == manifest['repository']['head']}")
    print(f"tracked drift       {drift['WORKTREE_POLICY']}  unexpected={drift['unexpected']}")
    print(f"revalidation        {revalidated['MANIFEST_VALID']}")
    print(f"validate-only       {selftest}")

    ok = (after == manifest["repository"]["head"]
          and drift["WORKTREE_POLICY"] == "PASS"
          and revalidated["MANIFEST_VALID"] == "PASS"
          and currency["PREFLIGHT_CURRENCY"] == "PASS"
          and set(selftest.values()) == {"PASS"})
    print()
    print(f"EXECUTION_MANIFEST  {'FROZEN' if ok else 'INVALID'}")
    print(f"EXECUTION_GATE      {'READY_FOR_ARM_A_ATTEMPT' if ok else 'CLOSED'}")
    print("  meaning           every software and governance path required to ATTEMPT")
    print("                    Arm A is present and frozen. NOT a claim that Isaac will")
    print("                    launch, that Hospital will load, or that the collector")
    print("                    will complete")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
