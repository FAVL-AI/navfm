"""Simulator identity: which simulator stack produced a result.

`navfm.provenance.EnvironmentIdentity` already pins the Python side -- interpreter,
torch, CUDA, the installed-distribution digest, module locations. It says nothing
about the simulator, and for this programme the simulator IS the instrument: a
trajectory from Isaac Sim 5.1.0 and one from 6.0 are not interchangeable
evidence, and neither are two Isaac Lab commits.

This adds that block, and it is written before Isaac Lab is installed rather than
after, because a provenance field added once results exist can only describe the
runs that came later.

Three rules, each the repository's own discipline applied here:

**Nothing is inferred.** No interpreter is auto-discovered and no version is
guessed from a path. `import isaacsim` is never attempted: it is heavy, it
succeeds only inside the one environment that has it, and a harness that
discovered its own runtime would make the executed environment unknowable from
the archive (F-M1-1). Versions come from installed-distribution metadata, which
is readable without importing the package.

**Absent is ABSENT, never zero.** A stack without Isaac Lab records
``isaac_lab_version = None``, not an empty string that a later reader could take
for a version. This is the FL-019 shape: a missing fact must not arrive looking
like a measured one.

**A dirty clone is recorded as dirty.** An Isaac Lab commit is only identifying
if the worktree matches it.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

__all__ = [
    "SimulatorIdentity",
    "gpu_identity",
    "isaac_lab_identity",
    "package_version",
    "simulator_identity",
]

#: Distributions whose presence and version define the simulator stack.
ISAAC_SIM_DISTRIBUTION = "isaacsim"
ISAAC_LAB_DISTRIBUTION = "isaaclab"

#: The pair this repository's evidence is produced under. Recorded so a mismatch
#: is visible in the artefact rather than discovered when a result disagrees.
EXPECTED_ISAAC_SIM_VERSION = "5.1.0"


def package_version(distribution: str) -> str | None:
    """Installed version of ``distribution``, or None if it is not installed.

    Reads distribution metadata rather than importing, so this is safe to call
    from any interpreter, including one without a simulator.
    """
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def _run(cmd: list[str], cwd: Path | None = None) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return out or None


def gpu_identity() -> dict[str, Any]:
    """GPU name, driver and memory, from the driver rather than from a config.

    Reports ``driver_reachable = False`` when ``nvidia-smi`` is absent or fails.
    That is a different fact from "no GPU", and conflating them would let a
    result claim a GPU it never touched.
    """
    raw = _run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader"])
    if raw is None:
        return {"driver_reachable": False, "gpus": [],
                "note": "nvidia-smi absent or non-zero; this is not evidence that no GPU exists"}
    gpus = []
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            gpus.append({"name": parts[0], "driver_version": parts[1],
                         "memory_total": parts[2]})
    return {"driver_reachable": True, "gpus": gpus}


def isaac_lab_identity(clone_path: str | Path | None = None) -> dict[str, Any]:
    """Isaac Lab version, and the commit of its clone when one is declared.

    ``clone_path`` is DECLARED by the caller, never searched for. A recorder that
    went looking for an Isaac Lab checkout could find a different one than the
    run used.
    """
    version = package_version(ISAAC_LAB_DISTRIBUTION)
    record: dict[str, Any] = {
        "isaac_lab_version": version,
        "installed": version is not None,
        "clone_path": (str(clone_path) if clone_path else None),
        "isaac_lab_commit": None,
        "isaac_lab_tag": None,
        "clone_worktree_dirty": None,
    }
    if clone_path is None:
        return record
    path = Path(clone_path)
    if not (path / ".git").exists():
        record["clone_error"] = f"no git repository at {path}"
        return record
    record["isaac_lab_commit"] = _run(["git", "rev-parse", "HEAD"], cwd=path)
    record["isaac_lab_tag"] = _run(["git", "describe", "--tags", "--exact-match"], cwd=path)
    status = _run(["git", "status", "--porcelain"], cwd=path)
    record["clone_worktree_dirty"] = status is not None
    return record


@dataclasses.dataclass(frozen=True)
class SimulatorIdentity:
    """Which simulator stack a result was produced by."""

    isaac_sim_version: str | None
    isaac_sim_matches_expected: bool
    expected_isaac_sim_version: str
    isaac_lab: dict[str, Any]
    python_version: str
    torch_version: str | None
    cuda_runtime: str | None
    gpu: dict[str, Any]
    interpreter: str
    conda_env: str | None

    @property
    def isaac_sim_present(self) -> bool:
        return self.isaac_sim_version is not None

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["isaac_sim_present"] = self.isaac_sim_present
        return d


def simulator_identity(isaac_lab_clone: str | Path | None = None) -> SimulatorIdentity:
    """Capture the simulator stack of the CURRENT interpreter.

    Deliberately reports the interpreter it runs in, and nothing else. Called
    from a build host it records "no Isaac Sim", which is the correct answer for
    that host rather than a failure.
    """
    import platform
    import sys

    sim_version = package_version(ISAAC_SIM_DISTRIBUTION)
    torch_version: str | None = None
    cuda_runtime: str | None = None
    try:
        import torch

        torch_version = torch.__version__
        cuda_runtime = torch.version.cuda
    except Exception:
        pass

    return SimulatorIdentity(
        isaac_sim_version=sim_version,
        isaac_sim_matches_expected=(sim_version is not None
                                    and sim_version.startswith(EXPECTED_ISAAC_SIM_VERSION)),
        expected_isaac_sim_version=EXPECTED_ISAAC_SIM_VERSION,
        isaac_lab=isaac_lab_identity(isaac_lab_clone),
        python_version=platform.python_version(),
        torch_version=torch_version,
        cuda_runtime=cuda_runtime,
        gpu=gpu_identity(),
        interpreter=sys.executable,
        conda_env=os.environ.get("CONDA_DEFAULT_ENV"),
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    import argparse

    p = argparse.ArgumentParser(prog="python -m navfm.simenv", description=__doc__)
    p.add_argument("--isaac-lab-clone", default=None,
                   help="declared path to the Isaac Lab clone; never searched for")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    identity = simulator_identity(args.isaac_lab_clone)
    payload = json.dumps(identity.to_dict(), indent=2)
    if args.out:
        from .evidence import emit_evidence

        digest = emit_evidence(args.out, identity.to_dict(),
                               required_keys=("isaac_sim_version", "isaac_lab"))
        print(f"wrote {args.out} sha256={digest}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
