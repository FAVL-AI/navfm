"""Execution-environment identity for TERMINAL_APPROACH_INTERVENTION_V1.

Two arms that differ in one factor are evidence only if everything else capable
of changing the trajectory was the same. V1 pinned the scientific code and the
configuration. It did not pin the machine underneath them, and that gap was not
hypothetical: an unattended upgrade moved the NVIDIA userspace driver between
the design freeze and the first execution attempt. Had the arms run either side
of it, nothing in the frozen record would have shown it.

The contract splits the environment three ways, because "what must match" is not
one question.

**Contract-critical** fields are frozen in the V2 amendment and must still hold
when an arm runs: the kernel, the GPU and its driver, the interpreter and its
numerics, the Isaac version, the scientific sources, the scene, and the runtime
contract. These are the fields that can change what the simulator computes.

**Pairwise-critical** fields must match between Arm A and Arm B but cannot be
frozen in advance, because their correct value does not exist yet when the
amendment is written. ``repository.head`` is the clear case: the commit that
carries this amendment is not known to the amendment. ``session.boot_id`` is the
other, and it is what mechanically enforces the no-reboot rule -- it is redrawn
by the kernel on every boot, so two arms sharing a boot_id did not have a reboot
between them, and two arms that do not share one did, whatever the kernel
release says.

**Observational** fields locate a run without defining it: free memory, free
disk, uptime, pid, wall clock. Recording them helps diagnose a failure.
Requiring them to match would make every run unrepeatable by construction, so
they are recorded and never hashed.

Nothing in this module reads a historical fact off the live machine. A statement
about what was true at the design freeze is read from the artefact frozen at
that time and verified by hash; recomputing it from present state is the defect
this contract exists to correct.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import platform
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "CONTRACT_CRITICAL_FIELDS",
    "CONTRACT_FIELDS_BY_VERSION",
    "CONTRACT_VERSION",
    "EQUALITY_CRITICAL_FIELDS",
    "OBSERVATIONAL_FIELDS",
    "PAIRWISE_CRITICAL_FIELDS",
    "V3_ADDITIONAL_CRITICAL_FIELDS",
    "V5_ADDITIONAL_CRITICAL_FIELDS",
    "V6_ADDITIONAL_CRITICAL_FIELDS",
    "Mismatch",
    "arm_equivalence",
    "canonical_json",
    "capture",
    "compare",
    "contract_digest",
    "contract_fields",
    "contract_satisfied",
    "digest",
    "select",
    "worktree_state",
]

CONTRACT_VERSION = "EXECUTION_ENVIRONMENT_IDENTITY_V2"

#: Frozen in the amendment; an arm must still match every one of them.
CONTRACT_CRITICAL_FIELDS: tuple[str, ...] = (
    "host.kernel_release",
    "host.architecture",
    "gpu.model",
    "gpu.uuid",
    "gpu.pci_bus_id",
    "gpu.driver_version",
    "gpu.kernel_module_version",
    "python.executable",
    "python.version",
    "python.environment_path",
    "python.torch_version",
    "python.torch_cuda_build",
    "python.cuda_available",
    "python.visible_device_count",
    "isaac.isaacsim_version",
    "isaac.isaacsim_core_version",
    "isaac.interpreter",
    "repository.path",
    "repository.worktree_policy",
    "scientific_code.control_sha256",
    "scientific_code.interpolated_target_sha256",
    "scientific_code.route_projection_sha256",
    "scientific_code.kinematic_drive_sha256",
    "scientific_code.collect_sha256",
    "scientific_code.app_sha256",
    "scientific_code.planning_sha256",
    "scientific_code.kinematics_sha256",
    "scientific_code.measurement_instrument_sha256",
    "scientific_code.preregistration_sha256",
    "scientific_code.route_population_sha256",
    "scientific_code.route_polyline_sha256",
    "scene.scene_id",
    "scene.scene_asset",
    "runtime_contract.physics_dt",
    "runtime_contract.rendering_dt",
    "runtime_contract.control_dt",
    "runtime_contract.control_hz",
    "runtime_contract.max_steps",
    "runtime_contract.lookahead_m",
    "runtime_contract.goal_tol_m",
    "runtime_contract.cruise_v",
    "runtime_contract.max_v",
    "runtime_contract.max_vy",
    "runtime_contract.max_w",
    "runtime_contract.seed",
)

#: V3 adds the seam module, because after the tracker-injection seam the
#: default selector -- Arm A's actual behaviour -- lives in a file V2 could not
#: have known about. V2's own tuple is left exactly as it was frozen: a
#: superseding amendment does not get to edit its predecessor's contract.
V3_ADDITIONAL_CRITICAL_FIELDS: tuple[str, ...] = (
    "scientific_code.target_selection_sha256",
)

#: V5 adds the execution machinery itself. The runner and its library decide
#: which selector an arm gets and which artefacts an arm produces, so leaving
#: them unpinned would let the thing that performs the experiment change without
#: the contract noticing -- the same hole the seam opened in V3, one layer up.
V5_ADDITIONAL_CRITICAL_FIELDS: tuple[str, ...] = (
    "scientific_code.intervention_runner_sha256",
    "scientific_code.arm_runner_sha256",
)

#: V6 adds the orchestration itself. The plan table decides which producers an
#: arm invokes and in what order, so a change to it changes what an arm does
#: even when every other pinned file is identical. That is precisely the layer
#: whose absence made two authorisations fail.
V6_ADDITIONAL_CRITICAL_FIELDS: tuple[str, ...] = (
    "scientific_code.arm_lifecycle_sha256",
)

#: Must match across arms; cannot be frozen ahead of the commit that carries
#: this amendment, or ahead of the boot the arms will actually run under.
PAIRWISE_CRITICAL_FIELDS: tuple[str, ...] = (
    "repository.branch",
    "repository.head",
    "repository.worktree_state",
    "session.boot_id",
)

#: Recorded on every capture, never hashed and never compared.
OBSERVATIONAL_FIELDS: tuple[str, ...] = (
    "observational.captured_at_utc",
    "observational.hostname",
    "observational.pid",
    "observational.uptime_seconds",
    "observational.gpu_memory_used_mib",
    "observational.gpu_memory_total_mib",
    "observational.gpu_utilization_pct",
    "observational.disk_free_gib",
)

#: What ENV_A == ENV_B means.
EQUALITY_CRITICAL_FIELDS: tuple[str, ...] = (
    CONTRACT_CRITICAL_FIELDS + PAIRWISE_CRITICAL_FIELDS
)

#: Which fields each amendment version pins. Versioned rather than mutated so
#: that checking the current tree against V2 still means what V2 meant.
CONTRACT_FIELDS_BY_VERSION: dict[str, tuple[str, ...]] = {
    "V2": CONTRACT_CRITICAL_FIELDS,
    "V3": CONTRACT_CRITICAL_FIELDS + V3_ADDITIONAL_CRITICAL_FIELDS,
    # V4 adds nothing. The treatment was implemented inside the seam module V3
    # already pins, so the field that would have been added is the field that
    # already exists -- and adding a redundant one would make the contract look
    # stricter without checking anything more.
    "V4": CONTRACT_CRITICAL_FIELDS + V3_ADDITIONAL_CRITICAL_FIELDS,
    "V5": (CONTRACT_CRITICAL_FIELDS + V3_ADDITIONAL_CRITICAL_FIELDS
           + V5_ADDITIONAL_CRITICAL_FIELDS),
    "V6": (CONTRACT_CRITICAL_FIELDS + V3_ADDITIONAL_CRITICAL_FIELDS
           + V5_ADDITIONAL_CRITICAL_FIELDS + V6_ADDITIONAL_CRITICAL_FIELDS),
}


def contract_fields(version: str) -> tuple[str, ...]:
    """The contract-critical field set an amendment version pins."""
    try:
        return CONTRACT_FIELDS_BY_VERSION[version]
    except KeyError:
        raise ValueError(
            f"unknown contract version {version!r}; known: "
            f"{sorted(CONTRACT_FIELDS_BY_VERSION)}"
        ) from None


_MISSING = "<ABSENT>"

_SCIENTIFIC_SOURCES: dict[str, str] = {
    "control_sha256": "src/navfm/control.py",
    "interpolated_target_sha256": "src/navfm/collection/interpolated_target.py",
    "route_projection_sha256": "src/navfm/collection/route_projection.py",
    "kinematic_drive_sha256": "src/navfm/collection/kinematic_drive.py",
    "collect_sha256": "src/navfm/isaac/collect.py",
    "app_sha256": "src/navfm/isaac/app.py",
    "planning_sha256": "src/navfm/planning.py",
    "kinematics_sha256": "src/navfm/kinematics.py",
    "target_selection_sha256": "src/navfm/target_selection.py",
    "intervention_runner_sha256": "src/navfm/intervention_runner.py",
    "arm_runner_sha256": "scripts/run_terminal_approach_intervention.py",
    "arm_lifecycle_sha256": "src/navfm/arm_lifecycle.py",
    "measurement_instrument_sha256": "scripts/diagnose_q2_margin_consumption.py",
    "preregistration_sha256": "gates/BO10/terminal_approach_intervention_v1_20260911.json",
    "route_population_sha256": "gates/BO10/hospital_turning_route_population_20260910.json",
}

#: The scene is streamed from a remote Omniverse asset server, so its identity
#: here is the URL and the scene id, not a content hash. Saying so is the point:
#: a URL pins which asset was requested, not which bytes were served.
SCENE_ID = "hospital_bo10"
SCENE_ASSET = (
    "https://omniverse-content-production.s3-us-west-2.amazonaws.com/"
    "Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd"
)
SCENE_CLAIM_BOUNDARY = (
    "the scene is identified by asset URL and scene id. It is NOT content-hashed: "
    "the asset is streamed from a remote server and no local copy exists to hash. "
    "Two arms therefore share a scene REQUEST, and the Isaac version pinned in the "
    "URL path constrains but does not prove byte identity of what was served"
)


@dataclasses.dataclass(frozen=True)
class Mismatch:
    """One equality-critical field that differs."""

    field: str
    left: Any
    right: Any

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "left": self.left, "right": self.right}


def sha256_file(path: Path) -> str | None:
    """Content hash, or None when the file is absent."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def canonical_json(payload: Any) -> str:
    """One byte sequence per value, so a digest means what it appears to mean."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def select(snapshot: Mapping[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    """Pull dotted paths out of a snapshot, marking absence rather than hiding it."""
    out: dict[str, Any] = {}
    for field in fields:
        node: Any = snapshot
        for part in field.split("."):
            if isinstance(node, Mapping) and part in node:
                node = node[part]
            else:
                node = _MISSING
                break
        out[field] = node
    return out


def contract_digest(snapshot: Mapping[str, Any]) -> str:
    """Digest of the frozen half only. Observational drift cannot move it."""
    return digest(select(snapshot, CONTRACT_CRITICAL_FIELDS))


def compare(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    fields: Sequence[str] = EQUALITY_CRITICAL_FIELDS,
) -> list[Mismatch]:
    """Every equality-critical field that differs, absence included."""
    a = select(left, fields)
    b = select(right, fields)
    return [Mismatch(f, a[f], b[f]) for f in fields if a[f] != b[f]]


def arm_equivalence(
    env_a: Mapping[str, Any],
    env_b: Mapping[str, Any],
) -> dict[str, Any]:
    """ENV_A == ENV_B, and what follows for the comparison if it does not hold.

    A failure here is not a repairable condition. Averaging across environments,
    repairing one arm and comparing anyway, or re-running only the arm whose
    result is less convenient are all forbidden by the frozen policy, because
    each of them turns an invalid comparison into a publishable-looking one.
    """
    mismatches = compare(env_a, env_b)
    ok = not mismatches
    reboot = any(m.field == "session.boot_id" for m in mismatches)
    return {
        "ENVIRONMENT_EQUIVALENCE": "PASS" if ok else "FAIL",
        "INTERVENTION_COMPARISON": "VALID" if ok else "INVALID",
        "fields_compared": len(EQUALITY_CRITICAL_FIELDS),
        "mismatches": [m.as_dict() for m in mismatches],
        "reboot_detected_between_arms": reboot,
        "remedy": (
            None
            if ok
            else (
                "the comparison is refused. A valid retry requires the preregistered "
                "retry policy or a new amendment; it does not require a different "
                "analysis of these two runs"
            )
        ),
    }


def contract_satisfied(
    snapshot: Mapping[str, Any],
    frozen_contract: Mapping[str, Any],
    *,
    fields: Sequence[str] = CONTRACT_CRITICAL_FIELDS,
) -> dict[str, Any]:
    """Does a live environment still match what an amendment froze?

    ``fields`` is passed explicitly by callers that know which version they are
    checking against, so that a later amendment pinning more fields does not
    retroactively change what an earlier one asserted.
    """
    live = select(snapshot, fields)
    drift = [
        Mismatch(f, live[f], frozen_contract.get(f, _MISSING))
        for f in fields
        if live[f] != frozen_contract.get(f, _MISSING)
    ]
    return {
        "CONTRACT_SATISFIED": "PASS" if not drift else "FAIL",
        "fields_compared": len(fields),
        "drift": [m.as_dict() for m in drift],
    }


def worktree_state(repo_root: Path, allowed: Sequence[str] = ()) -> str:
    """``clean``, or ``dirty:`` and the paths that are not on the allow-list.

    The allow-list is a deny-by-default mechanism on purpose. An arm writes its
    own artefacts while it runs, so a post-arm tree cannot be required to be
    empty; but "dirty but expected" is not a state a gate can check, and a
    blanket tolerance would accept an unrelated edit to the controller with
    exactly the same verdict.
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return "unknown:git-status-failed"
    paths = sorted(
        line[3:].strip() for line in proc.stdout.splitlines() if line.strip()
    )
    offending = [p for p in paths if not any(p == a or p.startswith(a) for a in allowed)]
    return "clean" if not offending else "dirty:" + ",".join(offending)


def _run(cmd: Sequence[str], timeout: float = 60.0) -> str:
    try:
        proc = subprocess.run(
            list(cmd), capture_output=True, text=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _gpu() -> dict[str, Any]:
    query = "name,uuid,pci.bus_id,driver_version,memory.used,memory.total,utilization.gpu"
    raw = _run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"])
    first = raw.splitlines()[0] if raw else ""
    parts = [p.strip() for p in first.split(",")] if first else []
    module = ""
    proc_version = Path("/proc/driver/nvidia/version")
    if proc_version.exists():
        match = re.search(r"(\d+\.\d+\.\d+)", proc_version.read_text())
        module = match.group(1) if match else ""
    sys_version = Path("/sys/module/nvidia/version")
    sys_module = sys_version.read_text().strip() if sys_version.exists() else ""
    return {
        "model": parts[0] if len(parts) > 6 else None,
        "uuid": parts[1] if len(parts) > 6 else None,
        "pci_bus_id": parts[2] if len(parts) > 6 else None,
        "driver_version": parts[3] if len(parts) > 6 else None,
        "kernel_module_version": module or sys_module or None,
        "kernel_module_version_sys": sys_module or None,
        "_memory_used_mib": int(parts[4]) if len(parts) > 6 and parts[4].isdigit() else None,
        "_memory_total_mib": int(parts[5]) if len(parts) > 6 and parts[5].isdigit() else None,
        "_utilization_pct": int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else None,
    }


_ISAAC_PROBE = (
    "import json,platform,sys\n"
    "out={'python_executable':sys.executable,'python_version':platform.python_version(),"
    "'environment_path':sys.prefix}\n"
    "try:\n"
    "    import importlib.metadata as im\n"
    "    for name,key in (('isaacsim','isaacsim_version'),('isaacsim-core','isaacsim_core_version')):\n"
    "        try: out[key]=im.version(name)\n"
    "        except Exception: out[key]=None\n"
    "except Exception: pass\n"
    "try:\n"
    "    import torch\n"
    "    out['torch_version']=torch.__version__\n"
    "    out['torch_cuda_build']=torch.version.cuda\n"
    "    out['cuda_available']=bool(torch.cuda.is_available())\n"
    "    out['visible_device_count']=int(torch.cuda.device_count())\n"
    "except Exception as exc:\n"
    "    out['torch_error']=repr(exc)[:200]\n"
    "print('PROBE'+json.dumps(out))\n"
)


def probe_isaac_python(interpreter: Path) -> dict[str, Any]:
    """Ask the Isaac interpreter about itself. It is not the one running this."""
    if not interpreter.exists():
        return {"probe_error": f"interpreter absent: {interpreter}"}
    try:
        proc = subprocess.run(
            [str(interpreter), "-c", _ISAAC_PROBE],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"probe_error": repr(exc)[:200]}
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("PROBE")), "")
    if not line:
        return {"probe_error": "probe produced no result"}
    parsed: dict[str, Any] = json.loads(line[5:])
    return parsed


def _runtime_contract() -> dict[str, Any]:
    """Read the frozen numbers from the code that will run, not from prose.

    Restating a constant in an artefact records what someone believed. Importing
    it records what the simulator will actually use, so a change to the source
    moves the contract digest instead of leaving a stale number behind.
    """
    from navfm.control import M3PRO_LIMITS
    from navfm.isaac.app import SimConfig
    from navfm.isaac.collect import CollectConfig

    sim = SimConfig()
    collect = CollectConfig()
    return {
        # app.py pins physics, rendering and the run loop to one dt; recording
        # all three separately is what makes a future divergence visible.
        "physics_dt": sim.dt,
        "rendering_dt": sim.dt,
        "control_dt": sim.dt,
        "control_hz": sim.hz,
        "max_steps": collect.max_steps,
        "lookahead_m": collect.lookahead_m,
        "goal_tol_m": collect.goal_tol_m,
        "cruise_v": collect.cruise_v,
        "max_v": M3PRO_LIMITS.max_v,
        "max_vy": M3PRO_LIMITS.max_vy,
        "max_w": M3PRO_LIMITS.max_w,
        "seed": collect.seed,
        "sources": {
            "physics_dt": "src/navfm/isaac/app.py SimConfig.dt via set_simulation_dt",
            "rendering_dt": "src/navfm/isaac/app.py SimConfig.dt via set_simulation_dt",
            "control_dt": "src/navfm/isaac/app.py SimConfig.dt = 1/hz",
            "max_steps": "src/navfm/isaac/collect.py CollectConfig.max_steps",
            "lookahead_m": "src/navfm/isaac/collect.py CollectConfig.lookahead_m",
            "goal_tol_m": "src/navfm/isaac/collect.py CollectConfig.goal_tol_m",
            "cruise_v": "src/navfm/isaac/collect.py CollectConfig.cruise_v",
            "max_v": "src/navfm/control.py M3PRO_LIMITS.max_v",
            "max_w": "src/navfm/control.py M3PRO_LIMITS.max_w",
            "seed": "src/navfm/isaac/collect.py CollectConfig.seed",
        },
    }


def _boot_id() -> str | None:
    path = Path("/proc/sys/kernel/random/boot_id")
    return path.read_text().strip() if path.exists() else None


def _uptime_seconds() -> float | None:
    path = Path("/proc/uptime")
    if not path.exists():
        return None
    try:
        return float(path.read_text().split()[0])
    except (ValueError, IndexError):
        return None


def _route_polyline_digest(prereg: Path) -> str | None:
    """Hash the coordinates both arms project against, not the file holding them."""
    try:
        payload = json.loads(prereg.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    try:
        coords = payload["secondary_outcome_cross_track_error"]["frozen_route_polyline"][
            "coordinates"
        ]
    except (KeyError, TypeError):
        return None
    return digest(coords)


def capture(
    repo_root: Path | str | None = None,
    *,
    isaac_python: Path | None = None,
    worktree_allowed: Sequence[str] = (),
) -> dict[str, Any]:
    """A full environment snapshot: contract-critical, pairwise, observational."""
    import datetime as _dt

    # Resolved, because repository.path is contract-critical: a caller passing
    # "." would otherwise report drift against an absolute frozen value and be
    # refused for a path spelling rather than for anything about the machine.
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[2]
    )
    interpreter = isaac_python or (Path.home() / "miniforge3/envs/isaac/bin/python")
    gpu = _gpu()
    isaac = probe_isaac_python(interpreter)
    prereg = root / "gates/BO10/terminal_approach_intervention_v1_20260911.json"

    code = {key: sha256_file(root / rel) for key, rel in _SCIENTIFIC_SOURCES.items()}
    code["route_polyline_sha256"] = _route_polyline_digest(prereg)

    return {
        "contract_version": CONTRACT_VERSION,
        "host": {
            "kernel_release": platform.release(),
            "architecture": platform.machine(),
            "os": platform.system(),
        },
        "gpu": {
            "model": gpu["model"],
            "uuid": gpu["uuid"],
            "pci_bus_id": gpu["pci_bus_id"],
            "driver_version": gpu["driver_version"],
            "kernel_module_version": gpu["kernel_module_version"],
        },
        "python": {
            "executable": isaac.get("python_executable"),
            "version": isaac.get("python_version"),
            "environment_path": isaac.get("environment_path"),
            "torch_version": isaac.get("torch_version"),
            "torch_cuda_build": isaac.get("torch_cuda_build"),
            "cuda_available": isaac.get("cuda_available"),
            "visible_device_count": isaac.get("visible_device_count"),
        },
        "isaac": {
            "isaacsim_version": isaac.get("isaacsim_version"),
            "isaacsim_core_version": isaac.get("isaacsim_core_version"),
            "interpreter": str(interpreter),
            "probe_error": isaac.get("probe_error"),
        },
        "repository": {
            "path": str(root),
            "branch": _run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"]) or None,
            "head": _run(["git", "-C", str(root), "rev-parse", "HEAD"]) or None,
            "worktree_state": worktree_state(root, worktree_allowed),
            "worktree_policy": "CLEAN_REQUIRED_AT_PRE_ARM_CAPTURE",
        },
        "scientific_code": code,
        "scene": {
            "scene_id": SCENE_ID,
            "scene_asset": SCENE_ASSET,
            "claim_boundary": SCENE_CLAIM_BOUNDARY,
        },
        "runtime_contract": _runtime_contract(),
        "session": {"boot_id": _boot_id()},
        "observational": {
            "captured_at_utc": _dt.datetime.now(_dt.UTC).isoformat(),
            "hostname": platform.node(),
            "pid": os.getpid(),
            "uptime_seconds": _uptime_seconds(),
            "gpu_memory_used_mib": gpu["_memory_used_mib"],
            "gpu_memory_total_mib": gpu["_memory_total_mib"],
            "gpu_utilization_pct": gpu["_utilization_pct"],
            "disk_free_gib": round(os.statvfs(root).f_bavail * os.statvfs(root).f_frsize / 2**30, 2),
        },
    }
