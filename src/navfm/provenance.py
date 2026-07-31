"""Environment identity and execution fingerprint.

A gate archive is worth what its provenance is worth. `gates/M1/` proved the
reproduction script runs inside a *declared* environment — one named on the
command line — which is a weaker claim than it looks: the declaration says
which interpreter was asked for, not what was actually installed behind it.

This module supplies the stronger claim. The **canonical environment** is not
a path. It is the environment whose identity is archived in the gate manifest:

    environment_id = sha256(python, torch, cuda, distribution digest, os, arch)

``~/.venv-train`` is one implementation of that identity, not its definition,
which is what makes the identity portable across machines and survivable across
a rebuild. Two environments with the same ``environment_id`` are
interchangeable for the purpose of a gate; two with different ones are not,
however similarly they were built.

The **execution fingerprint** is the identity plus the things that vary per
run — repository and upstream commits, interpreter path, hostname, UTC
timestamp, and whether the worktree was clean. It is emitted *before* any
experiment work and written as page one of the gate archive, so that provenance
is the first thing a reader sees rather than something reconstructed afterwards
from scattered logs.

The distribution digest is computed from ``importlib.metadata`` rather than by
shelling out to ``pip freeze``. The content is the same — sorted
``name==version`` lines — but a ``uv venv`` has no ``pip`` in it by default,
and a provenance helper that fails on the project's own canonical environment
would be a poor joke.

    python -m navfm.provenance                 # page-one text block
    python -m navfm.provenance --json          # same, machine-readable
    python -m navfm.provenance --identity-only # just the environment identity
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "EnvironmentIdentity",
    "ExecutionFingerprint",
    "environment_identity",
    "execution_fingerprint",
    "render_fingerprint",
]

# Fields that constitute the environment's identity. Deliberately excludes
# anything that varies between two runs in the same environment (timestamp,
# hostname, interpreter path, commit), because an identity that changes when
# nothing was reinstalled cannot be compared across runs.
_IDENTITY_FIELDS = (
    "python_version",
    "torch_version",
    "cuda_version",
    "pip_freeze_digest",
    "os",
    "architecture",
)


@dataclass(frozen=True)
class EnvironmentIdentity:
    """What must match for two environments to be the same instrument."""

    python_version: str
    torch_version: str | None
    cuda_version: str | None
    pip_freeze_digest: str
    distribution_count: int
    os: str
    architecture: str
    environment_id: str


@dataclass(frozen=True)
class ExecutionFingerprint:
    """The identity, plus what varies per run. Page one of every gate archive."""

    utc_timestamp: str
    hostname: str
    interpreter: str
    repository_commit: str | None
    repository_worktree: str
    upstream_commit: str | None
    python_version: str
    torch_version: str | None
    cuda_version: str | None
    os: str
    architecture: str
    environment_id: str


def _git(root: Path, *args: str) -> str | None:
    """Run git in ``root``; return stripped stdout, or None if it cannot answer."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _installed_distributions() -> list[str]:
    """Sorted ``name==version`` for every installed distribution."""
    from importlib.metadata import distributions

    seen: set[str] = set()
    for dist in distributions():
        # A broken or partially-removed distribution can carry no name; skip it
        # rather than let it poison the digest with a null.
        name = getattr(dist, "name", None)
        if not name:
            continue
        seen.add(f"{str(name).lower()}=={dist.version}")
    return sorted(seen)


def _torch_versions() -> tuple[str | None, str | None]:
    """(torch version, CUDA version torch was built against), or (None, None)."""
    try:
        import torch
    except ImportError:
        return None, None
    return str(torch.__version__), (str(torch.version.cuda) if torch.version.cuda else None)


def _worktree_status(root: Path) -> str:
    """``clean``, or a declaration of exactly what was modified.

    A gate that ran against a dirty tree is not invalid, but it is not
    reproducible from the recorded commit either, and the archive must say so
    rather than let the commit imply otherwise.
    """
    porcelain = _git(root, "status", "--porcelain")
    if porcelain is None:
        return "unknown (not a git worktree, or git unavailable)"
    if not porcelain:
        return "clean"
    # Do NOT slice at a fixed offset. Porcelain's XY status field is two
    # columns wide and an unstaged modification leaves column 1 blank (" M
    # f.txt"), but _git strips its output, so the first line arrives already
    # shifted by one. Splitting on the status token is offset-independent and
    # keeps paths containing spaces intact.
    entries: list[str] = []
    for line in porcelain.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            entries.append(parts[1])
        elif parts:
            entries.append(parts[0])
    listed = ", ".join(sorted(entries)[:10])
    suffix = ", ..." if len(entries) > 10 else ""
    return f"modified ({len(entries)}): {listed}{suffix}"


def environment_identity() -> EnvironmentIdentity:
    """Compute the identity of the environment this interpreter is running in."""
    torch_version, cuda_version = _torch_versions()
    dists = _installed_distributions()
    payload: dict[str, object] = {
        "python_version": platform.python_version(),
        "torch_version": torch_version,
        "cuda_version": cuda_version,
        "pip_freeze_digest": hashlib.sha256("\n".join(dists).encode()).hexdigest(),
        "os": platform.platform(),
        "architecture": platform.machine(),
    }
    canonical = json.dumps(
        {k: payload[k] for k in _IDENTITY_FIELDS}, sort_keys=True, separators=(",", ":")
    )
    return EnvironmentIdentity(
        python_version=str(payload["python_version"]),
        torch_version=torch_version,
        cuda_version=cuda_version,
        pip_freeze_digest=str(payload["pip_freeze_digest"]),
        distribution_count=len(dists),
        os=str(payload["os"]),
        architecture=str(payload["architecture"]),
        environment_id=hashlib.sha256(canonical.encode()).hexdigest(),
    )


def execution_fingerprint(
    repo_root: Path | str | None = None,
    upstream_root: Path | str | None = None,
) -> ExecutionFingerprint:
    """Full fingerprint. Emit this *before* any experiment work begins."""
    repo = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    identity = environment_identity()

    upstream_commit: str | None = None
    if upstream_root is not None:
        upstream_commit = _git(Path(upstream_root), "rev-parse", "HEAD")

    return ExecutionFingerprint(
        utc_timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        hostname=socket.gethostname(),
        interpreter=sys.executable,
        repository_commit=_git(repo, "rev-parse", "HEAD"),
        repository_worktree=_worktree_status(repo),
        upstream_commit=upstream_commit,
        python_version=identity.python_version,
        torch_version=identity.torch_version,
        cuda_version=identity.cuda_version,
        os=identity.os,
        architecture=identity.architecture,
        environment_id=identity.environment_id,
    )


_LABELS: tuple[tuple[str, str], ...] = (
    ("utc_timestamp", "UTC timestamp"),
    ("hostname", "Hostname"),
    ("interpreter", "Interpreter"),
    ("repository_commit", "Repository commit"),
    ("repository_worktree", "Working tree"),
    ("upstream_commit", "Upstream commit"),
    ("python_version", "Python version"),
    ("torch_version", "Torch version"),
    ("cuda_version", "CUDA version"),
    ("os", "OS"),
    ("architecture", "Architecture"),
    ("environment_id", "Environment identity"),
)


def render_fingerprint(fingerprint: ExecutionFingerprint) -> str:
    """Render the fingerprint as the text block that opens a gate archive."""
    data = asdict(fingerprint)
    width = max(len(label) for _, label in _LABELS)
    lines = ["EXECUTION FINGERPRINT", "=" * 21, ""]
    lines += [
        f"{label.ljust(width)}  {data[key] if data[key] is not None else '(absent)'}"
        for key, label in _LABELS
    ]
    lines += [
        "",
        "Emitted before any experiment work. The environment identity is a digest",
        "over python, torch, cuda, the installed-distribution set, OS and",
        "architecture -- not over the path this interpreter happens to live at.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--repo-root", default=None, help="repository to fingerprint (default: this one)"
    )
    p.add_argument("--upstream", default=None, help="path to the pinned reference clone")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--identity-only", action="store_true", help="emit only the environment identity block"
    )
    args = p.parse_args(argv)

    if args.identity_only:
        identity = environment_identity()
        print(json.dumps(asdict(identity), indent=2) if args.json else _render_identity(identity))
        return 0

    fingerprint = execution_fingerprint(args.repo_root, args.upstream)
    print(
        json.dumps(asdict(fingerprint), indent=2) if args.json else render_fingerprint(fingerprint),
        end="",
    )
    return 0


def _render_identity(identity: EnvironmentIdentity) -> str:
    data = asdict(identity)
    width = max(len(f) for f in data)
    body = "\n".join(
        f"{k.ljust(width)}  {v if v is not None else '(absent)'}" for k, v in data.items()
    )
    return f"ENVIRONMENT IDENTITY\n{'=' * 19}\n\n{body}\n"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
