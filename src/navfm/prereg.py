"""Machine-enforced pre-registration binding: the commit-order control.

A pre-registration's entire evidential force comes from having existed *before*
the result. Everything else about it — the hypotheses, the analysis plan, the
decision rule — is worthless if the ordering cannot be established, and
`git log` read afterwards by the person who ran the experiment is not
establishing it. It is the same person, the same afternoon, reporting on
themselves.

So the evaluator consumes the pre-registration commit as an input and refuses
to run unless five things hold. The commit-order block in the gate report is
then emitted by the machine that enforced them, not typed by hand from a log.

Any failure aborts with **gate execution invalid**, which is not a scientific
finding. It is the gate declining to produce one.

    python -m navfm.eval.offline --preregistration-commit <sha> ...
"""

from __future__ import annotations

import dataclasses
import hashlib
import subprocess
from pathlib import Path
from typing import Any

__all__ = [
    "GateExecutionInvalid",
    "PreregCheck",
    "protocol_blob",
    "verify",
]

PROTOCOL_PATH = "PREREGISTRATION.md"


class GateExecutionInvalid(RuntimeError):
    """The gate may not run. Never a finding; the absence of one."""


@dataclasses.dataclass(frozen=True)
class PreregCheck:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"check": self.name, "passed": self.passed, "detail": self.detail}


def _git(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False, timeout=60
    )
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _git_bytes(repo: Path, *args: str) -> tuple[int, bytes]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False, timeout=60
    )
    return proc.returncode, proc.stdout


def protocol_blob(repo: Path, commit: str, path: str = PROTOCOL_PATH) -> bytes | None:
    """The protocol file's exact bytes at ``commit``, or None if absent there."""
    code, data = _git_bytes(repo, "show", f"{commit}:{path}")
    return data if code == 0 else None


def verify(
    commit: str,
    *,
    repo_root: Path,
    output_dir: Path,
    protocol_path: str = PROTOCOL_PATH,
) -> tuple[list[PreregCheck], str | None]:
    """Run all five checks. Returns (checks, protocol_sha256).

    Every check runs even after one fails, so the manifest records the full
    picture rather than stopping at the first problem — an operator fixing a
    gate should learn everything that is wrong in one pass.
    """
    checks: list[PreregCheck] = []
    protocol_sha: str | None = None

    # 1 -- the commit exists.
    code, resolved = _git(repo_root, "rev-parse", "--verify", f"{commit}^{{commit}}")
    exists = code == 0
    checks.append(
        PreregCheck(
            "commit_exists",
            exists,
            f"resolved to {resolved}" if exists else f"cannot resolve {commit!r}: {resolved}",
        )
    )

    # 2 -- it is an ancestor of HEAD. A commit on an abandoned branch, or one
    # rewritten away, is not part of this repository's history and cannot have
    # preceded anything in it.
    if exists:
        code, _ = _git(repo_root, "merge-base", "--is-ancestor", resolved, "HEAD")
        ancestor = code == 0
        checks.append(
            PreregCheck(
                "commit_is_ancestor_of_head",
                ancestor,
                "in HEAD's history" if ancestor else f"{resolved[:12]} is NOT an ancestor of HEAD",
            )
        )
    else:
        checks.append(PreregCheck("commit_is_ancestor_of_head", False, "commit does not exist"))

    # 3 -- the protocol at that commit matches what the run archives.
    blob = protocol_blob(repo_root, resolved, protocol_path) if exists else None
    if blob is None:
        checks.append(
            PreregCheck("protocol_hash_matches", False, f"no {protocol_path} at {commit!r}")
        )
    else:
        protocol_sha = hashlib.sha256(blob).hexdigest()
        archived = output_dir / protocol_path
        if archived.is_file():
            archived_sha = hashlib.sha256(archived.read_bytes()).hexdigest()
            match = archived_sha == protocol_sha
            checks.append(
                PreregCheck(
                    "protocol_hash_matches",
                    match,
                    f"archived {archived_sha[:16]} vs commit {protocol_sha[:16]}",
                )
            )
        else:
            checks.append(
                PreregCheck(
                    "protocol_hash_matches",
                    True,
                    f"protocol sha256 {protocol_sha[:16]}... will be archived from this commit",
                )
            )

    # 4 -- the output directory did not predate the commit. Output older than
    # the protocol means the run began before the protocol was fixed, whatever
    # the manifest later says.
    commit_time: int | None = None
    if exists:
        code, out = _git(repo_root, "show", "-s", "--format=%ct", resolved)
        commit_time = int(out) if code == 0 and out.isdigit() else None
    if not output_dir.exists():
        checks.append(
            PreregCheck("output_postdates_commit", True, "output directory does not yet exist")
        )
    elif commit_time is None:
        checks.append(
            PreregCheck("output_postdates_commit", False, "cannot determine the commit timestamp")
        )
    else:
        created = int(output_dir.stat().st_mtime)
        ok = created >= commit_time
        checks.append(
            PreregCheck(
                "output_postdates_commit",
                ok,
                f"output mtime {created} vs commit time {commit_time}"
                + ("" if ok else " -- output predates the protocol it claims to follow"),
            )
        )

    # 5 -- the gate was not previously initialised under a different protocol.
    marker = output_dir / "preregistration.json"
    if marker.is_file():
        import json

        try:
            prior = json.loads(marker.read_text()).get("protocol_sha256")
        except (ValueError, OSError) as exc:
            checks.append(
                PreregCheck("protocol_stable_across_runs", False, f"unreadable marker: {exc}")
            )
        else:
            ok = protocol_sha is not None and prior == protocol_sha
            checks.append(
                PreregCheck(
                    "protocol_stable_across_runs",
                    ok,
                    "same protocol as the prior run in this directory"
                    if ok
                    else f"this gate was already initialised under protocol {str(prior)[:16]}..., "
                    f"now {str(protocol_sha)[:16]}... -- a protocol change after "
                    f"initialisation is a protocol change after execution",
                )
            )
    else:
        checks.append(
            PreregCheck("protocol_stable_across_runs", True, "no prior initialisation here")
        )

    return checks, protocol_sha


def enforce(checks: list[PreregCheck]) -> None:
    """Raise if any check failed, naming every failure."""
    failed = [c for c in checks if not c.passed]
    if not failed:
        return
    detail = "\n".join(f"    {c.name}: {c.detail}" for c in failed)
    raise GateExecutionInvalid(
        "gate execution invalid -- no evidential classification\n"
        f"{len(failed)} of {len(checks)} pre-registration checks failed:\n{detail}\n"
        "This is not a result. A gate that cannot establish that its protocol "
        "predates its execution has produced nothing to classify."
    )
