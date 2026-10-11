"""Freeze the runtime execution manifest against the final pre-execution HEAD.

Run this only after every tracked change has been committed, because the
manifest's whole job is to name the commit both arms execute from. A tracked
file cannot truthfully contain the SHA of the commit that contains it, so the
manifest lives in the runtime evidence tree instead of being committed: writing
a placeholder, committing, rewriting the real HEAD and committing again would
produce a file that pins a commit which is no longer HEAD, and that is a
provenance claim which reads as precise and is false.

Preconditions, all refused rather than warned about: the tree must be clean, the
authoritative V4 contract must accept it, and the manifest must validate against
the repository after being read back. Afterwards HEAD is re-read and compared
with what the manifest pinned, because a manifest that bound a HEAD which has
already moved is worse than no manifest.

Nothing here runs an arm.
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
from navfm.execution_manifest import (  # noqa: E402
    ARM_ORDER,
    SELECTOR_ASSIGNMENT,
    TRACKED_OUTPUTS,
    UNTRACKED_OUTPUTS,
    canonical_worktree_state,
    freeze_manifest,
    validate_manifest,
)

MANIFEST = REPO / "runs/bo10/intervention/execution_manifest.json"


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def main() -> int:
    print("=" * 68)
    print("FINAL EXECUTION MANIFEST FREEZE")
    print("=" * 68)

    # No arm has run, so nothing is permitted to be dirty yet: the output
    # allow-list describes what execution MAY create, not what may exist now.
    worktree = canonical_worktree_state(REPO)
    print(f"worktree            {worktree['WORKTREE_POLICY']}  "
          f"unexpected={worktree['unexpected']}")
    if worktree["WORKTREE_POLICY"] != "PASS":
        print("REFUSED: the tracked tree is not clean, so the HEAD to pin is ambiguous")
        return 1

    head = _git("rev-parse", "HEAD")
    if not head:
        print("REFUSED: cannot resolve HEAD")
        return 1
    print(f"FINAL_PRE_EXECUTION_HEAD  {head}")

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

    outcome = freeze_manifest(
        MANIFEST, REPO, head=head,
        frozen_at_utc=_dt.datetime.now(_dt.UTC).isoformat())
    if outcome["EXECUTION_MANIFEST"] != "FROZEN":
        print(f"REFUSED: {outcome.get('reason')}")
        if outcome.get("validation"):
            for failure in outcome["validation"]["failures"]:
                print(f"  - {failure['field']}: {failure['detail']}")
        return 1

    manifest = json.loads(MANIFEST.read_text())
    print()
    print(f"manifest            {MANIFEST.relative_to(REPO)}")
    print(f"sha256              {outcome['sha256']}")
    print(f"canonical digest    {outcome['manifest_digest']}")
    print(f"bound head          {outcome['bound_head']}")
    print(f"frozen at           {outcome['frozen_at_utc']}")
    print(f"{'FROZEN (first)' if outcome['first_freeze'] else 'RE-VERIFIED (unchanged)'}")
    print()
    print(f"arm order           {manifest['arms']['order']}")
    for arm in ARM_ORDER:
        print(f"  {arm:16s} {SELECTOR_ASSIGNMENT[arm]['target_type']}")
    print(f"overrides           {manifest['arms']['behavioural_overrides']}")
    print(f"tracked outputs     {len(TRACKED_OUTPUTS)} exact paths")
    print(f"runtime outputs     {len(UNTRACKED_OUTPUTS)} exact paths")
    print()

    # A manifest that pinned a HEAD which has already moved is worse than none.
    after = _git("rev-parse", "HEAD")
    drift = canonical_worktree_state(REPO, allow_outputs=UNTRACKED_OUTPUTS)
    consistent = after == manifest["repository"]["head"] and drift["WORKTREE_POLICY"] == "PASS"
    print(f"HEAD after freeze   {after[:12]}  matches manifest: "
          f"{after == manifest['repository']['head']}")
    print(f"tracked drift       {drift['WORKTREE_POLICY']}  unexpected={drift['unexpected']}")

    revalidated = validate_manifest(manifest, REPO, expected_head=head)
    print(f"revalidation        {revalidated['MANIFEST_VALID']}")
    for failure in revalidated["failures"]:
        print(f"  - {failure['field']}: {failure['detail']}")

    ok = consistent and revalidated["MANIFEST_VALID"] == "PASS"
    print()
    print(f"EXECUTION_MANIFEST  {'FROZEN' if ok else 'INVALID'}")
    print(f"EXECUTION_GATE      {'READY_FOR_EXPLICIT_AUTHORISATION' if ok else 'CLOSED'}")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
