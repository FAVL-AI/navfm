"""PER_ARM_ENVIRONMENT_EQUIVALENCE_GUARD_V1.

V2 froze *what* must match for two arms to be the same instrument. This is the
machinery that captures it four times and refuses when it does not hold.

Four captures, one schema. PRE_ARM_A and PRE_ARM_B establish that each arm
started in the frozen environment; POST_ARM_A and POST_ARM_B establish that it
was still that environment when the evidence was written. A pair of PRE captures
alone would miss an environment that moved *during* an arm, which is the case a
one-factor claim is least able to survive and least likely to notice.

Three things here are narrower than they first look, deliberately.

**The preflight exception is one path, not a tolerance.** A fresh preflight
rewrites its own timestamp and the nvidia-smi banner it quotes, so the pre-arm
tree cannot be byte-clean and freshly verified at the same moment. The exception
admits exactly one path, only while HEAD matches the frozen commit, and only
when the artefact's canonical payload -- everything except the two fields proven
to be presentation -- is unchanged. The parsed driver and module versions stay
equality-critical, so excluding the banner that quotes them costs nothing.

**A reboot is detected by boot_id, not by the kernel release.** A reboot into
the same kernel leaves the release string identical. A kernel or module version
that moves without a new boot_id is drift, not a reboot, and is reported as
drift.

**The scene is identifier-equivalent, never byte-equivalent.** The Hospital
stage is streamed from a remote asset server and no local copy exists to hash.
Equality across arms means the same asset was *requested* under the same Isaac
version. It does not mean the same bytes were served, and every artefact this
module produces carries that boundary rather than implying the stronger claim.

Nothing here runs an arm. Passing the pre-arm barrier is necessary for
execution and is not authorisation for it.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from navfm.evidence import RunOutcome, adjudicate_run, emit_evidence
from navfm.execution_environment import (
    EQUALITY_CRITICAL_FIELDS,
    OBSERVATIONAL_FIELDS,
    SCENE_ASSET,
    SCENE_CLAIM_BOUNDARY,
    SCENE_ID,
    capture,
    contract_fields,
    contract_satisfied,
    digest,
    select,
    sha256_file,
)

__all__ = [
    "AUTHORITATIVE_CONTRACT_VERSION",
    "CAPTURE_REQUIRED_KEYS",
    "CONTRACTS",
    "EXPECTED_DRIVER_VERSION",
    "EXPECTED_HOLD_COUNT",
    "GUARD_VERSION",
    "NVIDIA_HOLD_LIST",
    "PREFLIGHT_REL",
    "PREFLIGHT_VOLATILE_FIELDS",
    "PRODUCTION_LABELS",
    "SCENE_BYTE_IDENTITY",
    "SELFTEST_LABELS",
    "V2_AMENDMENT_REL",
    "V2_AMENDMENT_SHA256",
    "V3_AMENDMENT_REL",
    "V3_AMENDMENT_SHA256",
    "V4_AMENDMENT_REL",
    "V4_AMENDMENT_SHA256",
    "V5_AMENDMENT_REL",
    "V5_AMENDMENT_SHA256",
    "V6_AMENDMENT_REL",
    "V6_AMENDMENT_SHA256",
    "V7_AMENDMENT_REL",
    "V7_AMENDMENT_SHA256",
    "arm_environment_equivalence",
    "canonical_preflight",
    "capture_arm_environment",
    "check_contract",
    "is_production_label",
    "nvidia_hold_state",
    "parse_attempt",
    "parse_label",
    "preflight_exception",
    "preflight_identity",
    "reboot_detection",
    "scene_identity",
    "validate_post_arm_environment",
    "validate_pre_arm_environment",
    "write_capture",
]

GUARD_VERSION = "PER_ARM_ENVIRONMENT_EQUIVALENCE_GUARD_V1"

PRODUCTION_LABELS: tuple[str, ...] = ("PRE_ARM_A", "POST_ARM_A", "PRE_ARM_B", "POST_ARM_B")
SELFTEST_LABELS: tuple[str, ...] = ("SELFTEST_A", "SELFTEST_B")

V2_AMENDMENT_REL = "gates/BO10/environment_identity_v2_20260911.json"
V2_AMENDMENT_SHA256 = "d664388997dcec8014a1fd598bf315a0ef76cad4d9e679b0a248c67650d4a16a"
V3_AMENDMENT_REL = "gates/BO10/environment_identity_v3_20260911.json"
V3_AMENDMENT_SHA256 = "0105d34b8090a736f94532d90ae0e171518e9413e267c2b518ff089f43045148"
V4_AMENDMENT_REL = "gates/BO10/environment_identity_v4_20260912.json"
V4_AMENDMENT_SHA256 = "226a3b20cab9b02ca5e71c01ddb24f0aa7b1ca1e03b72bc2e4d45a1adb46aa93"
V5_AMENDMENT_REL = "gates/BO10/environment_identity_v5_20260912.json"
V5_AMENDMENT_SHA256 = "b4d53a7f5734c87bac5279173aba085513ecece822a058438aafa8ff659108bc"
V6_AMENDMENT_REL = "gates/BO10/environment_identity_v6_20260912.json"
V6_AMENDMENT_SHA256 = "b17d3c9372034efc4fdda0953fc726ef93673b8bab0cc99ed4736ae0331358fb"
V7_AMENDMENT_REL = "gates/BO10/environment_identity_v7_20260917.json"
V7_AMENDMENT_SHA256 = "bd8abf5a5f0b3b97f13afc1e2d2f483e8507713f6a258733929f7117c1c1d79b"
PREFLIGHT_REL = "gates/BO10/intervention_execution_preflight_20260911.json"

#: Which amendment authorises a future arm. Named, never inferred: a barrier
#: that tried V3 and fell back to V2 would silently accept a tree that the
#: authoritative contract rejects, which is the opposite of what a contract is.
AUTHORITATIVE_CONTRACT_VERSION = "V7"

#: Every amendment stays checkable, and each answers for the state it froze.
#: The invariants that matter are historical: V2 accepts its freeze state and
#: rejects the later seam state; V3 accepts its freeze state and rejects the
#: later treatment state; V4 accepts its freeze state and rejects the later
#: wiring state; V5 accepts the final executable state. A superseding
#: amendment never makes its predecessor pass again.
CONTRACTS: dict[str, tuple[str, str, str]] = {
    "V2": (V2_AMENDMENT_REL, V2_AMENDMENT_SHA256, "EXECUTION_ENVIRONMENT_IDENTITY_V2"),
    "V3": (V3_AMENDMENT_REL, V3_AMENDMENT_SHA256, "EXECUTION_ENVIRONMENT_IDENTITY_V3"),
    "V4": (V4_AMENDMENT_REL, V4_AMENDMENT_SHA256, "EXECUTION_ENVIRONMENT_IDENTITY_V4"),
    "V5": (V5_AMENDMENT_REL, V5_AMENDMENT_SHA256, "EXECUTION_ENVIRONMENT_IDENTITY_V5"),
    "V6": (V6_AMENDMENT_REL, V6_AMENDMENT_SHA256, "EXECUTION_ENVIRONMENT_IDENTITY_V6"),
    "V7": (V7_AMENDMENT_REL, V7_AMENDMENT_SHA256, "EXECUTION_ENVIRONMENT_IDENTITY_V7"),
}

NVIDIA_HOLD_LIST = "~/navfm-nvidia-580-held-20260911.txt"
EXPECTED_HOLD_COUNT = 22
EXPECTED_DRIVER_VERSION = "580.178.04"

#: The ONLY fields a fresh preflight may change. Both are presentation: the
#: wall clock, and the banner text nvidia-smi printed. The parsed driver and
#: module versions live elsewhere in the artefact and stay equality-critical,
#: so nothing scientific is inside this list and nothing may be added to it
#: without a versioned amendment.
PREFLIGHT_VOLATILE_FIELDS: tuple[str, ...] = (
    "timestamp_utc",
    "isaac_slot.nvidia_smi_stderr",
)

#: Fields that must survive canonicalisation. Asserted, not assumed: a test
#: drops each one and requires the canonical digest to move.
PREFLIGHT_SCIENTIFIC_FIELDS: tuple[str, ...] = (
    "SOFTWARE_PREFLIGHT",
    "EXECUTION_GATE",
    "EXECUTION_STATUS",
    "arms_executed",
    "preregistration",
    "gates",
    "implementation_difference_audit",
    "arm_identity_and_order",
    "design_freeze",
    "amendment",
    "isaac_slot.userspace_version",
    "isaac_slot.kernel_module_version",
    "isaac_slot.ISAAC_SLOT",
    "isaac_slot.cuda_probe",
)

#: Keys a preflight artefact must carry at all. A missing one is a refusal,
#: never a tolerated absence.
PREFLIGHT_REQUIRED_KEYS: tuple[str, ...] = (
    "SOFTWARE_PREFLIGHT",
    "EXECUTION_GATE",
    "EXECUTION_STATUS",
    "arm_identity_and_order",
    "implementation_difference_audit",
    "isaac_slot",
    "preregistration",
    "design_freeze",
    "amendment",
)

SCENE_BYTE_IDENTITY = "NOT_VERIFIED_REMOTE_STREAMED_ASSET"

_MISSING = "<ABSENT>"

_MISMATCH_CLASSES: tuple[tuple[str, str], ...] = (
    ("session.boot_id", "REBOOT"),
    ("host.", "KERNEL_DRIFT"),
    ("gpu.", "DRIVER_STACK_DRIFT"),
    ("python.", "INTERPRETER_DRIFT"),
    ("isaac.", "SIMULATOR_DRIFT"),
    ("repository.", "REPOSITORY_DRIFT"),
    ("scientific_code.", "SCIENTIFIC_SOURCE_DRIFT"),
    ("scene.", "SCENE_IDENTIFIER_DRIFT"),
    ("runtime_contract.", "RUNTIME_CONTRACT_DRIFT"),
)


#: A capture may name which attempt produced it: ``PRE_ARM_A_ATTEMPT_002``. The
#: base label stays a closed enumeration -- only the attempt number is open, and
#: only in this exact shape -- because a label pattern loose enough to admit
#: anything would stop distinguishing an A capture from a B capture, which is the
#: single job the label has.
_ATTEMPT_LABEL = re.compile(r"^(?P<base>[A-Z_]+?)_ATTEMPT_(?P<attempt>\d{3})$")


def parse_attempt(label: str) -> str | None:
    """The attempt a capture belongs to, or None for a single-attempt label.

    Attempt 1 of the terminal-approach intervention wrote ``PRE_ARM_A`` before
    attempts were numbered. That capture is evidence and is never rewritten, so
    an unnumbered label keeps meaning attempt 001 rather than becoming invalid.
    """
    match = _ATTEMPT_LABEL.match(label)
    return match.group("attempt") if match else None


def is_production_label(label: str) -> bool:
    """Whether this names a real arm capture, attempt suffix or not.

    Compared against the base, because membership decides whether the capture is
    held to the frozen HEAD. A suffixed label falling out of the set would have
    skipped that check silently -- the capture would still say PRE_ARM_A and no
    longer be checked against the commit it claims.
    """
    match = _ATTEMPT_LABEL.match(label)
    return (match.group("base") if match else label) in PRODUCTION_LABELS


def parse_label(label: str) -> tuple[str, str]:
    """``PRE_ARM_A`` -> ``("A", "PRE")``. One schema, so the label is the only
    thing that distinguishes an A capture from a B capture."""
    match = _ATTEMPT_LABEL.match(label)
    base = match.group("base") if match else label
    if base in SELFTEST_LABELS:
        return base.rsplit("_", 1)[1], "SELFTEST"
    if base not in PRODUCTION_LABELS:
        raise ValueError(
            f"unknown capture label {label!r}; production labels are "
            f"{PRODUCTION_LABELS} and self-test labels are {SELFTEST_LABELS}, "
            "each optionally suffixed _ATTEMPT_<nnn>"
        )
    phase, _, arm = base.partition("_ARM_")
    return arm, phase


def _drop(payload: Any, dotted: str) -> Any:
    parts = dotted.split(".")
    out = copy.deepcopy(payload)
    node = out
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return out
        node = node[part]
    if isinstance(node, dict):
        node.pop(parts[-1], None)
    return out


def canonical_preflight(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The preflight with only the frozen volatile fields removed."""
    out: Any = copy.deepcopy(dict(payload))
    for field in PREFLIGHT_VOLATILE_FIELDS:
        out = _drop(out, field)
    return dict(out)


def preflight_identity(path: Path) -> dict[str, Any]:
    """Both identities: the literal file, and the file minus presentation."""
    if not path.is_file():
        return {
            "path": str(path),
            "present": False,
            "FULL_PREFLIGHT_SHA": None,
            "CANONICAL_PREFLIGHT_SHA": None,
            "missing_required_keys": list(PREFLIGHT_REQUIRED_KEYS),
        }
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "path": str(path),
            "present": True,
            "parses": False,
            "parse_error": str(exc)[:200],
            "FULL_PREFLIGHT_SHA": sha256_file(path),
            "CANONICAL_PREFLIGHT_SHA": None,
        }
    missing = [k for k in PREFLIGHT_REQUIRED_KEYS if k not in payload]
    return {
        "path": str(path),
        "present": True,
        "parses": True,
        "FULL_PREFLIGHT_SHA": sha256_file(path),
        "CANONICAL_PREFLIGHT_SHA": digest(canonical_preflight(payload)),
        "excluded_volatile_fields": list(PREFLIGHT_VOLATILE_FIELDS),
        "missing_required_keys": missing,
        "SOFTWARE_PREFLIGHT": payload.get("SOFTWARE_PREFLIGHT"),
        "EXECUTION_GATE": payload.get("EXECUTION_GATE"),
        "EXECUTION_STATUS": payload.get("EXECUTION_STATUS"),
    }


def _safe_run(cmd: Sequence[str]) -> tuple[bool, str]:
    """Run a tool that may not exist here. A missing instrument is reported as
    an unreadable measurement, never as a clean one."""
    try:
        proc = subprocess.run(
            list(cmd), capture_output=True, text=True, check=False, timeout=120
        )
    except (OSError, subprocess.SubprocessError):
        return False, ""
    return proc.returncode == 0, proc.stdout


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _dirty_paths(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ["<git-status-failed>"]
    return sorted(line[3:].strip() for line in proc.stdout.splitlines() if line.strip())


def preflight_exception(repo_root: Path, frozen_head: str) -> dict[str, Any]:
    """May the tree differ, right now, in exactly one evidence file?

    This is not "a dirty tree is allowed". It is one named path, under a
    matching HEAD, whose canonical payload is byte-identical to the committed
    one. Anything else -- a second dirty path, an unknown untracked file, a
    moved HEAD, a changed scientific field -- is a refusal.
    """
    reasons: list[str] = []
    head = _git(repo_root, "rev-parse", "HEAD")
    if head != frozen_head:
        reasons.append(
            f"HEAD is {head[:12] or '<unknown>'} and the frozen commit is "
            f"{frozen_head[:12]}; repository identity must not move between the "
            "manifest and the arm"
        )

    dirty = _dirty_paths(repo_root)
    unexpected = [p for p in dirty if p != PREFLIGHT_REL]
    if unexpected:
        reasons.append(
            "paths other than the preflight artefact differ: " + ", ".join(unexpected)
        )

    live_path = repo_root / PREFLIGHT_REL
    live = preflight_identity(live_path)
    if not live.get("present"):
        reasons.append(f"{PREFLIGHT_REL} is absent")
    elif not live.get("parses"):
        reasons.append(f"{PREFLIGHT_REL} does not parse")
    elif live.get("missing_required_keys"):
        reasons.append(
            f"{PREFLIGHT_REL} is missing required key(s) "
            f"{live['missing_required_keys']}; a missing fact must not read as a "
            "benign one"
        )

    committed_canonical: str | None = None
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{frozen_head}:{PREFLIGHT_REL}"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        reasons.append(f"{PREFLIGHT_REL} is not present at {frozen_head[:12]}")
    else:
        try:
            committed_canonical = digest(canonical_preflight(json.loads(proc.stdout)))
        except json.JSONDecodeError:
            reasons.append(f"the committed {PREFLIGHT_REL} does not parse")

    if (
        committed_canonical is not None
        and live.get("CANONICAL_PREFLIGHT_SHA") is not None
        and live["CANONICAL_PREFLIGHT_SHA"] != committed_canonical
    ):
        reasons.append(
            "the preflight canonical payload changed. Only "
            f"{list(PREFLIGHT_VOLATILE_FIELDS)} may differ between a committed "
            "preflight and a fresh one; something else moved"
        )

    accepted = not reasons
    return {
        "PREFLIGHT_EXCEPTION": "ACCEPT" if accepted else "REFUSE",
        "allowed_path": PREFLIGHT_REL,
        "scope": (
            "exactly one path, under a matching HEAD, with an unchanged canonical "
            "payload. This is not a dirty-tree tolerance"
        ),
        "frozen_head": frozen_head,
        "observed_head": head or None,
        "dirty_paths": dirty,
        "unexpected_paths": unexpected,
        "live_canonical_sha": live.get("CANONICAL_PREFLIGHT_SHA"),
        "committed_canonical_sha": committed_canonical,
        "full_preflight_sha": live.get("FULL_PREFLIGHT_SHA"),
        "excluded_volatile_fields": list(PREFLIGHT_VOLATILE_FIELDS),
        "reasons": reasons,
    }


def check_contract(
    repo_root: Path | str,
    version: str = AUTHORITATIVE_CONTRACT_VERSION,
    *,
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Does the current tree satisfy a named amendment's frozen contract?

    Explicit about which amendment it is answering for. Checking today's tree
    against V2 and against V3 must give different answers, and that difference
    is the evidence that V3 did not retroactively weaken V2.
    """
    if version not in CONTRACTS:
        return {
            "CONTRACT_SATISFIED": "UNKNOWN_VERSION",
            "version": version,
            "known_versions": sorted(CONTRACTS),
            "drift": [],
        }
    rel, expected_sha, block = CONTRACTS[version]
    root = Path(repo_root)
    path = root / rel
    observed_sha = sha256_file(path)
    if observed_sha != expected_sha:
        return {
            "CONTRACT_SATISFIED": "FAIL",
            "version": version,
            "amendment_path": rel,
            "amendment_sha256": observed_sha,
            "expected_amendment_sha256": expected_sha,
            "drift": [],
            "reason": "the amendment file is not the one this guard pins",
        }
    try:
        frozen = json.loads(path.read_text())[block]["frozen_contract_values"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        return {
            "CONTRACT_SATISFIED": "FAIL",
            "version": version,
            "amendment_path": rel,
            "drift": [],
            "reason": f"the amendment carries no readable frozen contract: {exc!r}"[:200],
        }
    env = snapshot if snapshot is not None else capture(root)
    result = contract_satisfied(env, frozen, fields=contract_fields(version))
    result["version"] = version
    result["amendment_path"] = rel
    result["amendment_sha256"] = observed_sha
    return result


def nvidia_hold_state(hold_list: str = NVIDIA_HOLD_LIST) -> dict[str, Any]:
    """Holds AND the loaded stack. The list is a statement of intent; the
    loaded driver and module are what the arm will actually run against, and
    one is never evidence for the other."""
    reasons: list[str] = []
    path = Path(hold_list).expanduser()
    exists = path.is_file() and path.stat().st_size > 0
    if not exists:
        reasons.append(f"{hold_list} is absent or empty")

    ok, stdout = _safe_run(["apt-mark", "showhold"])
    held = sorted(pkg for pkg in stdout.split() if "580" in pkg) if ok else []
    if not ok:
        reasons.append(
            "apt-mark showhold could not be read; the hold state is UNKNOWN, which is "
            "not the same as clear"
        )
    elif len(held) != EXPECTED_HOLD_COUNT:
        reasons.append(f"{len(held)} NVIDIA packages held, expected {EXPECTED_HOLD_COUNT}")

    ok_smi, smi_out = _safe_run(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]
    )
    lines = smi_out.strip().splitlines()
    driver = lines[0].strip() if ok_smi and lines else ""
    if driver != EXPECTED_DRIVER_VERSION:
        reasons.append(
            f"loaded driver is {driver or '<unknown>'}, expected {EXPECTED_DRIVER_VERSION}"
        )

    module = ""
    proc_version = Path("/proc/driver/nvidia/version")
    if proc_version.exists():
        match = re.search(r"(\d+\.\d+\.\d+)", proc_version.read_text())
        module = match.group(1) if match else ""
    if module != EXPECTED_DRIVER_VERSION:
        reasons.append(
            f"loaded kernel module is {module or '<unknown>'}, expected "
            f"{EXPECTED_DRIVER_VERSION}"
        )

    return {
        "HOLD_GUARD": "PASS" if not reasons else "FAIL",
        "hold_list_path": hold_list,
        "hold_list_present": exists,
        "held_count": len(held),
        "expected_held_count": EXPECTED_HOLD_COUNT,
        "held_packages": held,
        "loaded_driver_version": driver or None,
        "loaded_module_version": module or None,
        "expected_driver_version": EXPECTED_DRIVER_VERSION,
        "holds_released": False,
        "why_both_are_checked": (
            "the hold list records what apt was told. The loaded driver and module "
            "record what the GPU is running. A correct list with a stale module is "
            "exactly the state that produced CUDA error 804"
        ),
        "reasons": reasons,
    }


def scene_identity(env: Mapping[str, Any]) -> dict[str, Any]:
    """Identifier equivalence, stated as such."""
    isaac = env.get("isaac", {}) if isinstance(env.get("isaac"), Mapping) else {}
    return {
        "scene_asset_identifier": SCENE_ASSET,
        "scene_id": SCENE_ID,
        "scene_uri": SCENE_ASSET,
        "scene_byte_identity": SCENE_BYTE_IDENTITY,
        "isaac_version": isaac.get("isaacsim_version"),
        "isaac_core_version": isaac.get("isaacsim_core_version"),
        "equality_semantics": "IDENTIFIER_EQUIVALENCE_NOT_BYTE_EQUIVALENCE",
        "claim_boundary": SCENE_CLAIM_BOUNDARY,
        "what_equality_across_arms_demonstrates": (
            "both arms requested the same asset identifier under the same Isaac "
            "version"
        ),
        "what_it_does_not_demonstrate": (
            "that the remote server returned identical bytes to both arms. No local "
            "copy exists to hash, and a fabricated scene SHA would assert exactly "
            "the claim that cannot be supported"
        ),
    }


def capture_arm_environment(
    label: str,
    *,
    repo_root: Path | str,
    frozen_head: str,
    worktree_allowed: Sequence[str] = (),
) -> dict[str, Any]:
    """One schema for all four production stages, and for the self-tests."""
    arm, phase = parse_label(label)
    root = Path(repo_root)
    env = capture(root, worktree_allowed=worktree_allowed)
    preflight = preflight_identity(root / PREFLIGHT_REL)
    holds = nvidia_hold_state()

    critical = select(env, EQUALITY_CRITICAL_FIELDS)
    absent = sorted(f for f, v in critical.items() if v == _MISSING or v is None)

    reasons: list[str] = []
    if absent:
        reasons.append(f"critical field(s) absent or null: {absent}")
    if env.get("isaac", {}).get("probe_error"):
        reasons.append(f"isaac probe failed: {env['isaac']['probe_error']}")
    if is_production_label(label) and env["repository"]["head"] != frozen_head:
        reasons.append(
            f"HEAD {str(env['repository']['head'])[:12]} is not the frozen "
            f"{frozen_head[:12]}"
        )

    payload: dict[str, Any] = {
        "check": GUARD_VERSION,
        "artifact_semantics": "ENVIRONMENT_CAPTURE_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "label": label,
        "arm": arm,
        "phase": phase,
        "is_production_label": is_production_label(label),
        "attempt": parse_attempt(label),
        "timestamp_utc": env["observational"]["captured_at_utc"],
        "boot_identity": {
            "boot_id": env["session"]["boot_id"],
            "kernel_release": env["host"]["kernel_release"],
            "uptime_seconds": env["observational"]["uptime_seconds"],
        },
        "environment": {
            "host": env["host"],
            "gpu": env["gpu"],
            "python": env["python"],
            "isaac": env["isaac"],
            "session": env["session"],
        },
        "repository": env["repository"],
        "scientific_code": env["scientific_code"],
        "runtime_contract": env["runtime_contract"],
        "scene_identity": scene_identity(env),
        "preflight_identity": preflight,
        "nvidia_hold_state": holds,
        "observational": env["observational"],
        "observational_fields_never_compared": list(OBSERVATIONAL_FIELDS),
        "equality_critical_snapshot": critical,
        "CAPTURE_VALIDATION": "PASS" if not reasons else "FAIL",
        "validation_reasons": reasons,
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
    }
    payload["critical_digest"] = digest(critical)
    payload["capture_digest"] = digest(
        {k: v for k, v in payload.items() if k not in {"observational", "timestamp_utc"}}
    )
    return payload


CAPTURE_REQUIRED_KEYS: tuple[str, ...] = (
    "label",
    "CAPTURE_VALIDATION",
    "equality_critical_snapshot",
)


def write_capture(
    payload: Mapping[str, Any],
    path: Path | str,
    *,
    required_keys: tuple[str, ...] = CAPTURE_REQUIRED_KEYS,
) -> str:
    """Persist and read back. Returns the artefact sha256.

    A file cannot carry its own hash, so ``capture_digest`` is the content
    identity recorded inside and this is the identity of the bytes on disk.

    ``required_keys`` defaults to what a capture owes. A caller writing some
    other artefact through the same read-back path must say what that artefact
    owes instead -- an empty tuple would make the read-back prove only that the
    file parses.
    """
    return emit_evidence(path, dict(payload), required_keys=required_keys)


def _snapshot(capture_payload: Mapping[str, Any]) -> dict[str, Any]:
    """The equality-critical view, taken from a capture or a raw environment."""
    recorded = capture_payload.get("equality_critical_snapshot")
    if isinstance(recorded, Mapping):
        return {f: recorded.get(f, _MISSING) for f in EQUALITY_CRITICAL_FIELDS}
    return select(capture_payload, EQUALITY_CRITICAL_FIELDS)


def _mismatch_class(field: str, values: Sequence[Any]) -> str:
    if any(v == _MISSING or v is None for v in values):
        return "MISSING_FIELD"
    for prefix, name in _MISMATCH_CLASSES:
        if field == prefix or field.startswith(prefix):
            return name
    return "UNCLASSIFIED_CRITICAL_DRIFT"


def reboot_detection(captures: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """boot_id across the captures. Kernel release cannot do this job."""
    boot_ids = {
        label: _snapshot(payload).get("session.boot_id")
        for label, payload in captures.items()
    }
    kernels = {
        label: _snapshot(payload).get("host.kernel_release")
        for label, payload in captures.items()
    }
    distinct = {v for v in boot_ids.values()}
    rebooted = len(distinct) > 1
    return {
        "REBOOT_DETECTED": rebooted,
        "boot_ids": boot_ids,
        "kernel_releases": kernels,
        "distinct_boot_ids": len(distinct),
        "instrument": "/proc/sys/kernel/random/boot_id",
        "why_not_kernel_release": (
            "a reboot into the same kernel leaves the release string unchanged, so "
            "kernel release cannot detect a reboot. boot_id is redrawn every boot"
        ),
        "note_if_kernel_moved_without_reboot": (
            "a kernel, module or driver version that differs while boot_id is "
            "constant is drift and is reported as drift, never as a reboot"
        ),
    }


def arm_environment_equivalence(
    pre_arm_a: Mapping[str, Any],
    post_arm_a: Mapping[str, Any],
    pre_arm_b: Mapping[str, Any],
    post_arm_b: Mapping[str, Any],
) -> dict[str, Any]:
    """ENV_A == ENV_B across all four captures, field by field.

    Reporting that "the environment changed" when a field-level answer exists
    would hand the experimenter a verdict without the evidence for it, and the
    evidence is the part that says whether the comparison can be rescued -- it
    cannot -- and what actually moved.
    """
    labels = list(PRODUCTION_LABELS)
    captures = dict(
        zip(labels, (pre_arm_a, post_arm_a, pre_arm_b, post_arm_b), strict=True)
    )
    snapshots = {label: _snapshot(payload) for label, payload in captures.items()}

    mismatches: list[dict[str, Any]] = []
    for field in EQUALITY_CRITICAL_FIELDS:
        values = [snapshots[label].get(field, _MISSING) for label in labels]
        # Absent everywhere is not agreement. Four captures that all failed to
        # record the driver have not shown the driver was the same; they have
        # shown nothing, and reading that as PASS is the FL-019 shape at field
        # level -- a missing fact consumed as a benign value.
        unestablished = any(v == _MISSING or v is None for v in values)
        if not unestablished and all(v == values[0] for v in values):
            continue
        mismatches.append(
            {
                "field": field,
                "PRE_ARM_A": values[0],
                "POST_ARM_A": values[1],
                "PRE_ARM_B": values[2],
                "POST_ARM_B": values[3],
                "mismatch_class": _mismatch_class(field, values),
                "changed_within_arm_a": values[0] != values[1],
                "changed_between_arms": values[1] != values[2],
                "changed_within_arm_b": values[2] != values[3],
            }
        )

    reboot = reboot_detection(captures)
    invalid_captures = [
        label
        for label, payload in captures.items()
        if payload.get("CAPTURE_VALIDATION") not in (None, "PASS")
    ]
    ok = not mismatches and not reboot["REBOOT_DETECTED"] and not invalid_captures

    return {
        "check": GUARD_VERSION,
        "artifact_semantics": "ENVIRONMENT_COMPARISON_ONLY",
        "ENVIRONMENT_EQUIVALENCE": "PASS" if ok else "FAIL",
        "INTERVENTION_COMPARISON": "VALID" if ok else "INVALID",
        "REBOOT_DETECTED": reboot["REBOOT_DETECTED"],
        "labels_compared": labels,
        "fields_compared": len(EQUALITY_CRITICAL_FIELDS),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "mismatch_classes": sorted({m["mismatch_class"] for m in mismatches}),
        "reboot_detection": reboot,
        "invalid_captures": invalid_captures,
        "observational_fields_excluded_by_design": list(OBSERVATIONAL_FIELDS),
        "scene_equality_semantics": "IDENTIFIER_EQUIVALENCE_NOT_BYTE_EQUIVALENCE",
        "scene_claim_boundary": SCENE_CLAIM_BOUNDARY,
        "if_failed": (
            None
            if ok
            else {
                "the_comparison_is_refused": True,
                "forbidden": [
                    "averaging across environments",
                    "repairing one arm and comparing anyway",
                    "re-running only the less favourable arm",
                    "silently choosing the better pair",
                    "reporting the comparison with a caveat instead of refusing it",
                ],
                "a_valid_retry_requires": (
                    "the preregistered retry policy or a new amendment, not a "
                    "different analysis of two runs that were not comparable"
                ),
                "evidence_preserved": "every differing field is listed above verbatim",
            }
        ),
    }


def validate_pre_arm_environment(
    label: str,
    *,
    repo_root: Path | str,
    frozen_head: str,
    worktree_allowed: Sequence[str] = (),
    fresh_preflight: bool = True,
    post_arm_a: Mapping[str, Any] | None = None,
    pre_arm_a: Mapping[str, Any] | None = None,
    contract_version: str = AUTHORITATIVE_CONTRACT_VERSION,
) -> dict[str, Any]:
    """Refuse an arm unless the frozen environment is demonstrably still here.

    Passing is necessary for execution and is not authorisation for it.

    For Arm B the bar is higher on purpose: a POST_ARM_A that validates, and a
    PRE_ARM_B equivalent to PRE_ARM_A on every frozen critical field. Running B
    after comparability has already been lost spends a run to produce a number
    that may not be compared with anything.
    """
    root = Path(repo_root)
    arm, phase = parse_label(label)
    if phase not in {"PRE", "SELFTEST"}:
        raise ValueError(f"{label} is not a pre-arm label")

    reasons: list[str] = []
    allowed = list(worktree_allowed)
    if fresh_preflight and PREFLIGHT_REL not in allowed:
        allowed.append(PREFLIGHT_REL)

    if contract_version not in CONTRACTS:
        return {
            "check": GUARD_VERSION,
            "barrier": "PRE_ARM",
            "label": label,
            "PRE_ARM_BARRIER": "REFUSED",
            "reasons": [f"unknown contract version {contract_version!r}"],
            "EXECUTION_STATUS": "NOT_RUN",
        }
    amendment_rel, expected_amendment_sha, _block = CONTRACTS[contract_version]
    amendment_path = root / amendment_rel
    amendment_sha = sha256_file(amendment_path)
    if amendment_sha != expected_amendment_sha:
        reasons.append(
            f"{contract_version} amendment sha256 is {str(amendment_sha)[:16]}..., "
            f"expected {expected_amendment_sha[:16]}...; the frozen contract is not "
            "the one in force"
        )

    head = _git(root, "rev-parse", "HEAD")
    if head != frozen_head:
        reasons.append(f"HEAD is {head[:12] or '<unknown>'}, frozen is {frozen_head[:12]}")

    exception = (
        preflight_exception(root, frozen_head)
        if fresh_preflight
        else {"PREFLIGHT_EXCEPTION": "NOT_APPLICABLE", "reasons": []}
    )
    if exception["PREFLIGHT_EXCEPTION"] == "REFUSE":
        reasons.append("preflight dirty-path exception refused: " + "; ".join(
            exception["reasons"]))

    capture_payload = capture_arm_environment(
        label, repo_root=root, frozen_head=frozen_head, worktree_allowed=allowed
    )
    if capture_payload.get("CAPTURE_VALIDATION") != "PASS":
        reasons.append(
            "environment capture invalid: "
            + "; ".join(capture_payload.get("validation_reasons", ["no reason recorded"]))
        )

    # A capture missing the blocks the barrier depends on is a refusal, not an
    # exception. Crashing here would leave the operator with a traceback where
    # a verdict belongs, and a traceback is not a recorded refusal.
    holds = capture_payload.get("nvidia_hold_state")
    if not isinstance(holds, dict):
        reasons.append("capture carries no nvidia_hold_state block")
        holds = {"HOLD_GUARD": "ABSENT", "reasons": ["not recorded by this capture"]}
    elif holds.get("HOLD_GUARD") != "PASS":
        reasons.append("NVIDIA hold guard failed: " + "; ".join(holds.get("reasons", [])))

    preflight = capture_payload.get("preflight_identity")
    if not isinstance(preflight, dict):
        reasons.append("capture carries no preflight_identity block")
        preflight = {"SOFTWARE_PREFLIGHT": "ABSENT"}
    else:
        if preflight.get("SOFTWARE_PREFLIGHT") != "PASS":
            reasons.append(f"SOFTWARE_PREFLIGHT is {preflight.get('SOFTWARE_PREFLIGHT')}")
        if preflight.get("missing_required_keys"):
            reasons.append(f"preflight missing keys {preflight['missing_required_keys']}")

    environment = capture_payload.get("environment", {})
    env_view = {
        "host": environment.get("host", {}),
        "gpu": environment.get("gpu", {}),
        "python": environment.get("python", {}),
        "isaac": environment.get("isaac", {}),
        "repository": capture_payload.get("repository", {}),
        "scientific_code": capture_payload.get("scientific_code", {}),
        "scene": {"scene_id": SCENE_ID, "scene_asset": SCENE_ASSET},
        "runtime_contract": capture_payload.get("runtime_contract", {}),
    }
    contract_drift = check_contract(root, contract_version, snapshot=env_view)
    if contract_drift["CONTRACT_SATISFIED"] != "PASS":
        fields = [d["field"] for d in contract_drift["drift"]]
        reasons.append(
            f"frozen {contract_version} contract no longer satisfied: "
            f"{fields or contract_drift.get('reason')}"
        )

    arm_b_checks: dict[str, Any] = {}
    if arm == "B" and phase == "PRE":
        if post_arm_a is None:
            reasons.append("POST_ARM_A is absent; Arm B may not start without it")
        else:
            if post_arm_a.get("CAPTURE_VALIDATION") != "PASS":
                reasons.append("POST_ARM_A did not validate")
            if post_arm_a.get("label") != "POST_ARM_A":
                reasons.append(f"expected POST_ARM_A, got {post_arm_a.get('label')!r}")
        if pre_arm_a is None:
            reasons.append("PRE_ARM_A is absent; Arm B comparability cannot be established")
        else:
            a = _snapshot(pre_arm_a)
            b = _snapshot(capture_payload)
            differing = [
                {"field": f, "PRE_ARM_A": a.get(f, _MISSING), "PRE_ARM_B": b.get(f, _MISSING)}
                for f in EQUALITY_CRITICAL_FIELDS
                if a.get(f, _MISSING) != b.get(f, _MISSING)
            ]
            arm_b_checks["pre_arm_a_vs_pre_arm_b"] = differing
            if differing:
                reasons.append(
                    "PRE_ARM_B is not equivalent to PRE_ARM_A on "
                    f"{[d['field'] for d in differing]}"
                )

    authorised = not reasons
    verdict_key = "ARM_B_EXECUTION" if arm == "B" else "ARM_A_EXECUTION"
    return {
        "check": GUARD_VERSION,
        "barrier": "PRE_ARM",
        "label": label,
        "arm": arm,
        "PRE_ARM_BARRIER": "PASS" if authorised else "REFUSED",
        verdict_key: "NOT_STARTED" if authorised else "REFUSED",
        "passing_is_necessary_not_sufficient": (
            "the barrier establishes that the frozen environment is still present. "
            "It is not execution authorisation, which is separate and explicit"
        ),
        "frozen_head": frozen_head,
        "observed_head": head or None,
        "contract_version": contract_version,
        "amendment_path": amendment_rel,
        "amendment_sha256": amendment_sha,
        "contract_check": contract_drift,
        "preflight_exception": exception,
        "nvidia_hold_state": holds,
        "capture": capture_payload,
        "arm_b_checks": arm_b_checks,
        "reasons": reasons,
        "EXECUTION_STATUS": "NOT_RUN",
    }


def validate_post_arm_environment(
    label: str,
    *,
    repo_root: Path | str,
    frozen_head: str,
    artefact_path: Path | str,
    exit_code: int,
    required_keys: tuple[str, ...] = (),
    worktree_allowed: Sequence[str] = (),
) -> dict[str, Any]:
    """Did this arm actually produce evidence, and was the environment intact?

    The outcome is adjudicated from the exit code AND the artefact together via
    ``navfm.evidence.adjudicate_run``. An arm whose process exits 0 having
    written nothing is RUN_FAILED_NO_ARTEFACT, never a completed arm -- FL-019
    is exactly a clean status for a step that did not happen.
    """
    arm, phase = parse_label(label)
    if phase not in {"POST", "SELFTEST"}:
        raise ValueError(f"{label} is not a post-arm label")
    root = Path(repo_root)

    outcome: RunOutcome = adjudicate_run(
        exit_code, artefact_path, required_keys=required_keys
    )
    capture_payload = capture_arm_environment(
        label, repo_root=root, frozen_head=frozen_head, worktree_allowed=worktree_allowed
    )

    reasons: list[str] = []
    if outcome is not RunOutcome.RUN_OK:
        reasons.append(f"run outcome is {outcome.value}")
    if capture_payload.get("CAPTURE_VALIDATION") != "PASS":
        reasons.append(
            "post-arm environment capture invalid: "
            + "; ".join(capture_payload.get("validation_reasons", ["no reason recorded"]))
        )

    valid = not reasons
    return {
        "check": GUARD_VERSION,
        "barrier": "POST_ARM",
        "label": label,
        "arm": arm,
        "RUN_OUTCOME": outcome.value,
        "ARM_EXECUTION": "VALID_ARM_EXECUTION" if valid else outcome.value,
        "POST_ARM_BARRIER": "PASS" if valid else "FAIL",
        "artefact_path": str(artefact_path),
        "artefact_sha256": sha256_file(Path(artefact_path)),
        "artefact_required_keys": list(required_keys),
        "exit_code": exit_code,
        "why_exit_code_alone_is_not_enough": (
            "an evidence write placed after SimulationApp.close() never runs and the "
            "process still exits 0. FL-019 is that shape: a clean status for a step "
            "that did not happen"
        ),
        "capture": capture_payload,
        "reasons": reasons,
        "EXECUTION_STATUS": "NOT_RUN",
    }
