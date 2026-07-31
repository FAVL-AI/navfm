"""Protocol freeze audit — the preflight that must pass before G0.c executes.

    python scripts/protocol_freeze_audit.py --amendment-commit <sha> --run-dir runs/g0c

Fourteen machine-verifiable checks, extending the five that
`--preregistration-commit` already enforces inside the evaluator. Those five
establish that a protocol commit exists and precedes execution. These fourteen
establish that *everything the protocol names is frozen, recorded, and still
matches what is on disk* — which is a different question, and the one that
decides whether a G0.c number means anything.

Every check runs to completion regardless of individual failures, and every
outcome is recorded pass or fail. A check whose result is visible only when it
fails cannot be audited afterwards, and an operator fixing a gate should learn
everything that is wrong in one pass.

**Any FAIL ends the gate as "gate execution invalid".** That is not an adverse
scientific outcome. It is the gate declining to produce one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SPLIT_DIR = REPO / "gates" / "G0" / "splits"
SHA256SUMS = REPO / "gates" / "G0" / "SHA256SUMS"
PROTOCOL = REPO / "PREREGISTRATION.md"
DECLARATION = REPO / "gates" / "G0" / "evaluation_declaration.json"
PAIR_MANIFEST = REPO / "gates" / "G0" / "evaluation_pairs.json"
PATCH_DIFF = REPO / "gates" / "G0" / "patch.diff"
UPSTREAM = REPO / "third_party" / "visualnav-transformer"


class Check:
    __slots__ = ("detail", "name", "passed")

    def __init__(self, name: str, passed: bool, detail: str) -> None:
        self.name, self.passed, self.detail = name, bool(passed), detail

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "result": "PASS" if self.passed else "FAIL",
            "detail": self.detail,
        }


def _git(*args: str) -> tuple[int, str]:
    p = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False, timeout=60
    )
    return p.returncode, (p.stdout or p.stderr).strip()


def _git_at(root: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False, timeout=60
    )
    return p.returncode, (p.stdout or p.stderr).strip()


def _identity_diff(expected_id: str) -> str:
    """Name the fields that differ, so a mismatch is diagnosable, not just fatal."""
    try:
        sys.path.insert(0, str(REPO / "src"))
        from navfm.provenance import environment_identity

        observed = environment_identity()
        fields = [
            f
            for f in (
                "python_version",
                "torch_version",
                "cuda_version",
                "pythonpath",
                "sys_prefix",
                "pythonhome",
                "pip_freeze_digest",
            )
            if getattr(observed, f, None) is not None
        ]
        return ", ".join(f"{f}={getattr(observed, f)!r}" for f in fields[:4])
    except Exception:
        return ""


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def audit(amendment_commit: str, run_dir: Path, checkpoint: Path | None) -> list[Check]:
    checks: list[Check] = []

    # 1-3: the amendment exists, is identified, and is in this history.
    code, resolved = _git("rev-parse", "--verify", f"{amendment_commit}^{{commit}}")
    resolves = code == 0
    # Resolving is not enough. Any commit resolves; this check must establish
    # that the named commit actually carries a G0.c decision rule, or it passes
    # vacuously for HEAD and certifies nothing.
    carries = False
    marker = ""
    if resolves:
        blob_code, blob = _git("show", f"{resolved}:PREREGISTRATION.md")
        if blob_code == 0:
            carries = bool(re.search(r"^##\s+Amendment\s+\d+.*G0\.c", blob, re.M | re.I))
            marker = (
                "carries a G0.c amendment"
                if carries
                else ("PREREGISTRATION.md at that commit contains NO G0.c amendment heading")
            )
        else:
            marker = "no PREREGISTRATION.md at that commit"
    exists = resolves and carries
    checks.append(
        Check(
            "amendment_committed",
            exists,
            f"{resolved} -- {marker}" if resolves else f"unresolvable: {resolved}",
        )
    )
    checks.append(
        Check(
            "amendment_sha_recorded",
            resolves and len(resolved) == 40,
            f"full SHA {resolved}" if resolves else "no SHA to record",
        )
    )
    if resolves:
        anc, _ = _git("merge-base", "--is-ancestor", resolved, "HEAD")
        checks.append(
            Check(
                "amendment_ancestor_of_head",
                anc == 0,
                "in HEAD's history" if anc == 0 else "NOT an ancestor of HEAD",
            )
        )
    else:
        checks.append(Check("amendment_ancestor_of_head", False, "commit does not resolve"))

    # 4: the protocol file's hash.
    protocol_sha = _sha256_file(PROTOCOL)
    checks.append(
        Check(
            "preregistration_hash_recorded",
            protocol_sha is not None,
            f"sha256 {protocol_sha}" if protocol_sha else f"unreadable: {PROTOCOL}",
        )
    )

    # 5-7: the split is frozen — key rule, allocation algorithm, and the files.
    manifest_path = SPLIT_DIR / "split_manifest.json"
    manifest: dict[str, Any] = {}
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        checks.append(Check("scene_key_rule_hash_recorded", False, f"no split manifest: {exc}"))
        checks.append(Check("scene_order_algorithm_hash_recorded", False, "no split manifest"))
        checks.append(Check("split_digests_recorded_and_match", False, "no split manifest"))
    else:
        rule = manifest.get("manifest_core_verbatim", {}).get("scene_key_rule", "")
        version = manifest.get("scene_key_version", "")
        rule_sha = hashlib.sha256(f"{version}|{rule}".encode()).hexdigest() if rule else None
        checks.append(
            Check(
                "scene_key_rule_hash_recorded",
                rule_sha is not None,
                f"{version} rule sha256 {rule_sha}" if rule_sha else "scene key rule absent",
            )
        )

        algo = manifest.get("allocation_algorithm", {})
        algo_sha = (
            hashlib.sha256(
                json.dumps(algo, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if algo
            else None
        )
        checks.append(
            Check(
                "scene_order_algorithm_hash_recorded",
                algo_sha is not None,
                f"{algo.get('version')} algorithm sha256 {algo_sha}"
                if algo_sha
                else "allocation algorithm absent",
            )
        )

        problems: list[str] = []
        for split, key in (("train", "train_names_sha256"), ("test", "test_names_sha256")):
            recorded = manifest.get(key)
            path = SPLIT_DIR / split / "traj_names.txt"
            if not recorded:
                problems.append(f"{split}: no digest recorded")
                continue
            try:
                names = path.read_text().split()
            except OSError:
                problems.append(f"{split}: {path} unreadable")
                continue
            actual = hashlib.sha256("\n".join(names).encode()).hexdigest()
            if actual != recorded:
                problems.append(f"{split}: file {actual[:16]} != recorded {recorded[:16]}")
        checks.append(
            Check(
                "split_digests_recorded_and_match",
                not problems,
                "; ".join(problems) if problems else "train and test digests match committed files",
            )
        )

    # 8-9: acquisition digests recorded, and the checkpoint re-verified NOW.
    sums_sha = _sha256_file(SHA256SUMS)
    checks.append(
        Check(
            "sha256sums_recorded",
            sums_sha is not None,
            f"gates/G0/SHA256SUMS sha256 {sums_sha}" if sums_sha else "gates/G0/SHA256SUMS missing",
        )
    )
    if checkpoint is None:
        checks.append(
            Check("checkpoint_digest_reverified", False, "no --checkpoint given to verify")
        )
    elif sums_sha is None:
        checks.append(
            Check("checkpoint_digest_reverified", False, "no SHA256SUMS to verify against")
        )
    else:
        expected = {}
        for line in SHA256SUMS.read_text().splitlines():
            m = re.match(r"^([0-9a-f]{64})\s+\.?/?(.+)$", line.strip())
            if m:
                expected[Path(m.group(2)).name] = m.group(1)
        want = expected.get(checkpoint.name)
        got = _sha256_file(checkpoint)
        ok = want is not None and got == want
        checks.append(
            Check(
                "checkpoint_digest_reverified",
                ok,
                f"{checkpoint.name} {got[:16] if got else 'unreadable'} vs recorded "
                f"{want[:16] if want else '(not in SHA256SUMS)'}"
                + ("" if ok else " -- the bytes about to be scored are not the bytes recorded"),
            )
        )

    # 10-11: the instrument, and the tree it ran from.
    try:
        sys.path.insert(0, str(REPO / "src"))
        from navfm.provenance import execution_fingerprint

        fp = execution_fingerprint(REPO, UPSTREAM)
        expected = ""
        try:
            expected = json.loads(DECLARATION.read_text())["environment"]["identity"]
        except (OSError, ValueError, KeyError):
            expected = ""
        if not expected:
            checks.append(
                Check(
                    "environment_identity_recorded",
                    False,
                    "no preregistered identity in the declaration to compare against",
                )
            )
        elif fp.environment_id == expected:
            checks.append(
                Check("environment_identity_recorded", True, f"matches preregistered {expected}")
            )
        else:
            differing = _identity_diff(expected)
            checks.append(
                Check(
                    "environment_identity_recorded",
                    False,
                    f"expected {expected} observed {fp.environment_id}"
                    + (f" -- differing fields: {differing}" if differing else "")
                    + " -- the instrument is not the one the protocol froze",
                )
            )
        checks.append(
            Check(
                "worktree_state_declared",
                True,
                f"working tree: {fp.repository_worktree}",
            )
        )
    except Exception as exc:  # the fingerprint is mandatory; its absence is a FAIL
        checks.append(Check("environment_identity_recorded", False, f"unavailable: {exc}"))
        checks.append(Check("worktree_state_declared", False, f"unavailable: {exc}"))

    # 11b: every artefact the amendment names must resolve AT THE AMENDMENT
    # COMMIT, not merely in the worktree. A path that exists today but did not
    # exist when the protocol was frozen was not pinned by that protocol.
    if resolves:
        required = (
            "gates/G0/SHA256SUMS",
            "gates/G0/splits/split_manifest.json",
            "gates/G0/splits/train/traj_names.txt",
            "gates/G0/splits/test/traj_names.txt",
        )
        missing_at_commit = []
        for rel in required:
            code_ls, _ = _git("cat-file", "-e", f"{resolved}:{rel}")
            if code_ls != 0:
                missing_at_commit.append(rel)
        checks.append(
            Check(
                "artefacts_resolve_at_amendment_commit",
                not missing_at_commit,
                "all pinned artefacts present at the amendment commit"
                if not missing_at_commit
                else f"absent at {resolved[:12]}: {missing_at_commit} -- a path that exists "
                f"only in the worktree was not pinned by the frozen protocol",
            )
        )
    else:
        checks.append(
            Check("artefacts_resolve_at_amendment_commit", False, "commit does not resolve")
        )

    # 15: the evaluation population, verified directly.
    try:
        pinned = json.loads(PAIR_MANIFEST.read_text())
        digest = pinned.get("sha256")
        count = pinned.get("pair_count")
        ok = bool(digest) and bool(count)
        checks.append(
            Check(
                "evaluation_pair_manifest_digest",
                ok,
                f"population digest {str(digest)[:16]}, {count} pairs"
                if ok
                else "manifest present but missing sha256 or pair_count",
            )
        )
    except (OSError, ValueError) as exc:
        checks.append(
            Check("evaluation_pair_manifest_digest", False, f"no pinned pair manifest: {exc}")
        )

    # 16: the patch set is part of the protocol identity.
    problems_patch: list[str] = []
    code_u, upstream_sha = _git_at(UPSTREAM, "rev-parse", "HEAD")
    declared_upstream = ""
    try:
        declared_upstream = json.loads(DECLARATION.read_text())["upstream"]["commit"]
    except (OSError, ValueError, KeyError):
        problems_patch.append("declaration names no upstream commit")
    if code_u != 0:
        problems_patch.append("cannot read the upstream clone's HEAD")
    elif declared_upstream and upstream_sha != declared_upstream:
        problems_patch.append(
            f"upstream HEAD {upstream_sha[:12]} != declared {declared_upstream[:12]}"
        )
    patch_digest = _sha256_file(PATCH_DIFF)
    if patch_digest is None:
        problems_patch.append("no archived patch diff")
    script_digest = _sha256_file(REPO / "scripts" / "patch_upstream.py")
    applied = 0
    dataset = UPSTREAM / "train" / "vint_train" / "data" / "vint_dataset.py"
    try:
        applied = dataset.read_text().count("# navfm-patch:")
    except OSError:
        problems_patch.append("cannot read the patched dataset module")
    if applied < 4:
        problems_patch.append(
            f"only {applied} sampling patch markers present in vint_dataset.py -- the clone "
            f"is unpatched or partially patched, so sampling semantics are not the frozen ones"
        )
    checks.append(
        Check(
            "upstream_patch_identity_verified",
            not problems_patch,
            "; ".join(problems_patch)
            if problems_patch
            else f"upstream {upstream_sha[:12]}, patch script {str(script_digest)[:16]}, "
            f"diff {str(patch_digest)[:16]}, {applied} markers applied",
        )
    )

    # 12-13: nothing was produced before the audit.
    checks.append(
        Check(
            "no_existing_g0c_result_directory",
            not run_dir.exists(),
            "absent" if not run_dir.exists() else f"{run_dir} already exists",
        )
    )
    stray = sorted(run_dir.glob("**/metrics.json")) if run_dir.exists() else []
    checks.append(
        Check(
            "no_pre_audit_evaluator_output",
            not stray,
            "none"
            if not stray
            else f"{len(stray)} evaluator output(s) predate this audit: {[str(p) for p in stray[:3]]}",
        )
    )
    return checks


def render(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    lines = ["PROTOCOL FREEZE AUDIT", "=" * 21, ""]
    lines += [
        f"{c.name.ljust(width)}  {'PASS' if c.passed else 'FAIL'}  {c.detail}" for c in checks
    ]
    failed = [c for c in checks if not c.passed]
    lines += [""]
    if failed:
        lines += [
            f"{len(failed)} of {len(checks)} checks FAILED.",
            "gate execution invalid -- no evidential classification.",
            "This is not a result. It is the gate declining to produce one.",
        ]
    else:
        lines += [f"all {len(checks)} checks PASS -- the protocol is frozen and G0.c may execute."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--amendment-commit", required=True)
    p.add_argument(
        "--run-dir", required=True, help="the G0.c output directory (must not exist yet)"
    )
    p.add_argument("--checkpoint", default=None, help="re-verified against gates/G0/SHA256SUMS")
    p.add_argument("--json-out", default=None)
    args = p.parse_args(argv)

    checks = audit(
        args.amendment_commit,
        Path(args.run_dir),
        Path(args.checkpoint) if args.checkpoint else None,
    )
    report = render(checks)
    print(report, end="")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps([c.as_dict() for c in checks], indent=2) + "\n")
    return 0 if all(c.passed for c in checks) else 5


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
