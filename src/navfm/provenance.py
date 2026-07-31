"""Environment identity and execution fingerprint.

A gate archive is worth what its provenance is worth. `gates/M1/` proved the
reproduction script runs inside a *declared* environment — one named on the
command line — which is a weaker claim than it looks: the declaration says
which interpreter was asked for, not what was actually installed behind it.

This module supplies the stronger claim. The **canonical environment** is not
a path. It is the environment whose identity is archived in the gate manifest:

    environment_id = sha256(python, torch, cuda, distribution digest,
                            os, arch, PYTHONPATH)

``PYTHONPATH`` is in there because a virtualenv does not isolate you from it.
Sourcing ROS 2 Humble exports a ``PYTHONPATH`` of Python 3.10 site-packages
that a 3.11 venv inherits *and prepends*, so imports resolve to another
interpreter's packages while every other field still matches. An identity blind
to that would certify two different instruments as the same one.

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
import os
import platform
import site
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
    # PYTHONPATH is part of the identity because it changes which code runs.
    # A virtualenv does NOT isolate you from it: sourcing ROS 2 Humble exports a
    # PYTHONPATH of Python 3.10 site-packages, which a 3.11 venv inherits and
    # prepends, so imports silently resolve to another interpreter's packages.
    # An identity blind to that would call two different instruments the same
    # one (F-M2-2).
    "pythonpath",
    # The rest of the effective-import surface. Two environments agreeing on
    # every version and disagreeing on where those versions are imported FROM
    # are not the same instrument.
    "sys_prefix",
    "sys_base_prefix",
    "pythonhome",
    "enable_user_site",
    "module_locations",
)


#: Modules whose *resolved location* defines this instrument. If any of these
#: is imported from somewhere other than where the canonical environment puts
#: it, the environment is not the one the archive claims -- which is precisely
#: how a sourced ROS 2 tree took over a 3.11 venv (F-M2-2).
_LOAD_BEARING_MODULES = (
    "torch",
    "torchvision",
    "navfm",
    "vint_train.training.train_utils",
    "cv2",
    "matplotlib",
    "diffusers",
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
    pythonpath: str
    sys_prefix: str
    sys_base_prefix: str
    pythonhome: str
    enable_user_site: bool
    module_locations: dict[str, str | None]
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
    pythonpath: str
    sys_prefix: str
    sys_base_prefix: str
    pythonhome: str
    enable_user_site: bool
    user_site: str | None
    module_locations: dict[str, str | None]
    # Recorded, never hashed: these locate the instrument without defining it.
    sys_executable: str
    sys_version: str
    sys_path: list[str]
    cwd: str
    module_locations_raw: dict[str, str | None]
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


def _normalize_path(raw: str | None, repo_root: Path) -> str | None:
    """Map a path to a machine-independent token.

    Machine-specific roots become tokens so the identity survives a move
    between machines; system roots (``/opt/ros/...``, ``/usr/lib/...``) are
    left literal, because they mean the same thing everywhere and their
    appearance here is exactly the signal worth catching.
    """
    if raw is None:
        return None
    path = Path(raw).resolve()
    for root, token in (
        (Path(sys.prefix).resolve(), "<prefix>"),
        (Path(sys.base_prefix).resolve(), "<base_prefix>"),
        (repo_root.resolve(), "<repo>"),
        (Path.home().resolve(), "~"),
    ):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        return token if str(rel) == "." else f"{token}/{rel}"
    return str(path)


def _module_locations(repo_root: Path) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Resolved ``__file__`` of every load-bearing module: (normalised, raw).

    Importing is the point. Asking where a module *would* resolve without
    importing it answers a different question from the one that matters, which
    is where it actually came from in this process.
    """
    import importlib

    normalised: dict[str, str | None] = {}
    raw_locations: dict[str, str | None] = {}
    for name in _LOAD_BEARING_MODULES:
        try:
            module = importlib.import_module(name)
        except Exception:  # absence and breakage are both "not here"
            normalised[name] = None
            raw_locations[name] = None
            continue
        raw = getattr(module, "__file__", None)
        raw_locations[name] = str(raw) if raw else None
        normalised[name] = _normalize_path(raw_locations[name], repo_root)
    return normalised, raw_locations


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


def environment_identity(repo_root: Path | str | None = None) -> EnvironmentIdentity:
    """Compute the identity of the environment this interpreter is running in."""
    repo = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    # Order matters. Importing the load-bearing modules mutates sys.path --
    # editable installs drop .pth hooks that append entries -- so a
    # distribution scan taken BEFORE those imports differs from one taken
    # after, and two consecutive calls would report two different identities.
    # Resolve the imports first, then scan, so the identity is stable from the
    # first call rather than from the second.
    module_locations, _raw = _module_locations(repo)
    torch_version, cuda_version = _torch_versions()
    dists = _installed_distributions()
    payload: dict[str, object] = {
        "python_version": platform.python_version(),
        "torch_version": torch_version,
        "cuda_version": cuda_version,
        "pip_freeze_digest": hashlib.sha256("\n".join(dists).encode()).hexdigest(),
        "os": platform.platform(),
        "architecture": platform.machine(),
        "pythonpath": os.environ.get("PYTHONPATH", ""),
        "sys_prefix": _normalize_path(sys.prefix, repo) or "",
        "sys_base_prefix": _normalize_path(sys.base_prefix, repo) or "",
        "pythonhome": os.environ.get("PYTHONHOME", ""),
        "enable_user_site": bool(site.ENABLE_USER_SITE),
        "module_locations": module_locations,
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
        pythonpath=str(payload["pythonpath"]),
        sys_prefix=str(payload["sys_prefix"]),
        sys_base_prefix=str(payload["sys_base_prefix"]),
        pythonhome=str(payload["pythonhome"]),
        enable_user_site=bool(payload["enable_user_site"]),
        module_locations=module_locations,
        environment_id=hashlib.sha256(canonical.encode()).hexdigest(),
    )


def execution_fingerprint(
    repo_root: Path | str | None = None,
    upstream_root: Path | str | None = None,
) -> ExecutionFingerprint:
    """Full fingerprint. Emit this *before* any experiment work begins."""
    repo = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    identity = environment_identity(repo)
    _normalised, raw_locations = _module_locations(repo)
    try:
        user_site: str | None = site.getusersitepackages()
    except Exception:  # some embedded builds have no user site
        user_site = None

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
        pythonpath=identity.pythonpath,
        sys_prefix=identity.sys_prefix,
        sys_base_prefix=identity.sys_base_prefix,
        pythonhome=identity.pythonhome,
        enable_user_site=identity.enable_user_site,
        user_site=user_site,
        module_locations=identity.module_locations,
        sys_executable=sys.executable,
        sys_version=sys.version.replace("\n", " "),
        sys_path=list(sys.path),
        cwd=os.getcwd(),
        module_locations_raw=raw_locations,
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
    ("pythonpath", "PYTHONPATH"),
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
