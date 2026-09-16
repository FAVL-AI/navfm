"""Manifest-driven execution of one intervention arm.

One runner, one code path, arm identity read from the frozen manifest. Separate
Arm A and Arm B runners would be two programs that must be argued to be the
same; a single runner with the selector as its only arm-dependent value makes
that argument structural.

Nothing scientific may be supplied by a caller. Route, seed, look-ahead,
max_steps, gains, cruise velocity, goal tolerance, scene and initial pose all
come from the manifest, and an attempt to override any of them is refused. A
command line that can change the experiment is a command line that can be used
to change it after seeing a result.

The module also answers a question Manifest V1 could not: whether the declared
outputs have anyone to write them. V1 froze a narrow, exact allow-list and never
checked that code existed to produce those paths, so the manifest was
declaration-complete and execution-incomplete at once -- correct on paper and
unrunnable. ``producer_coverage`` closes that by requiring every REQUIRED
declared output to resolve to a real callable.

What the structural checks here establish is that the experiment is invokable.
They do not establish that Isaac launches, that the Hospital asset loads, that
rendering works, or that the collector completes. Those are empirical and only
an actual attempt can settle them.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from navfm.execution_manifest import (
    ARM_ORDER,
    SELECTOR_ASSIGNMENT,
    validate_manifest,
)
from navfm.target_selection import (
    SELECTOR_REGISTRY,
    SelectorResolutionRefused,
    resolve_target_selector,
)

__all__ = [
    "PRODUCER_MAP",
    "SCIENTIFIC_FIELDS_NEVER_OVERRIDABLE",
    "ArmResolution",
    "RunnerRefused",
    "executability",
    "producer_coverage",
    "resolve_arm",
    "runner_resolution",
    "validate_only",
    "write_arm_result",
    "write_comparison",
    "write_status",
    "write_terminal_trace",
]

RUNNER_ENTRY_POINT = "scripts/run_terminal_approach_intervention.py"
RUNNER_MODULE = "navfm.intervention_runner"
COLLECTOR_ENTRY_POINT = "navfm.isaac.collect:Collector"

#: A caller may never set these. They define the experiment.
SCIENTIFIC_FIELDS_NEVER_OVERRIDABLE: tuple[str, ...] = (
    "selector", "target_selector", "route", "seed", "lookahead", "lookahead_m",
    "max_steps", "gains", "cruise_v", "cruise_velocity", "goal_tol", "goal_tol_m",
    "goal_tolerance", "scene", "scene_asset", "initial_pose", "goal", "max_v", "max_w",
    "physics_dt", "rendering_dt", "control_dt", "demonstrator",
)


class RunnerRefused(RuntimeError):
    """A stated refusal. The runner declines rather than improvising."""


@dataclasses.dataclass(frozen=True)
class ArmResolution:
    """Everything one arm needs, resolved from the manifest and nothing else."""

    arm: str
    selector_identity: str
    selector_class: str
    route: list[list[float]]
    seed: int
    initial_pose_xy_yaw: list[float]
    goal_xy: list[float]
    scene_asset: str
    scene_id: str
    runtime: dict[str, Any]
    outputs: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


#: declared output -> (lifecycle stage, producer, required)
#:
#: Producers are dotted callables so a missing one is detectable by import
#: rather than by a run that silently writes nothing.
PRODUCER_MAP: dict[str, tuple[str, str, bool]] = {
    "runs/bo10/intervention/execution_manifest.json": (
        "MANIFEST_FREEZE", "navfm.execution_manifest:freeze_manifest", True),
    "runs/bo10/intervention/env/pre_arm_a.json": (
        "PRE_ARM_A", "navfm.arm_environment_guard:capture_arm_environment", True),
    "runs/bo10/intervention/env/post_arm_a.json": (
        "POST_ARM_A", "navfm.arm_environment_guard:capture_arm_environment", True),
    "runs/bo10/intervention/env/pre_arm_b.json": (
        "PRE_ARM_B", "navfm.arm_environment_guard:capture_arm_environment", True),
    "runs/bo10/intervention/env/post_arm_b.json": (
        "POST_ARM_B", "navfm.arm_environment_guard:capture_arm_environment", True),
    "runs/bo10/intervention/status/arm_a_status.json": (
        "ARM_A_STATUS", "navfm.intervention_runner:write_status", True),
    "runs/bo10/intervention/status/arm_b_status.json": (
        "ARM_B_STATUS", "navfm.intervention_runner:write_status", True),
    "runs/bo10/intervention/arm_a/": (
        "ARM_A_TRAJECTORY", "navfm.isaac.collect:Collector", True),
    "runs/bo10/intervention/arm_b/": (
        "ARM_B_TRAJECTORY", "navfm.isaac.collect:Collector", True),
    "gates/BO10/intervention/arm_a_result.json": (
        "ARM_A_RESULT", "navfm.intervention_runner:write_arm_result", True),
    "gates/BO10/intervention/arm_b_result.json": (
        "ARM_B_RESULT", "navfm.intervention_runner:write_arm_result", True),
    "gates/BO10/intervention/arm_a_terminal_trace.csv": (
        "ARM_A_TRACE", "navfm.intervention_runner:write_terminal_trace", True),
    "gates/BO10/intervention/arm_b_terminal_trace.csv": (
        "ARM_B_TRACE", "navfm.intervention_runner:write_terminal_trace", True),
    "gates/BO10/intervention/environment_equivalence.json": (
        "ENVIRONMENT_EQUIVALENCE", "navfm.arm_environment_guard:arm_environment_equivalence",
        True),
    "gates/BO10/intervention/comparison.json": (
        "INTERVENTION_COMPARISON", "navfm.intervention_runner:write_comparison", True),
}


def _resolve_dotted(reference: str) -> tuple[bool, str]:
    module_name, _, attribute = reference.partition(":")
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return False, f"cannot import {module_name}: {type(exc).__name__}"
    if attribute and not hasattr(module, attribute):
        return False, f"{module_name} has no attribute {attribute}"
    if attribute and not callable(getattr(module, attribute)):
        return False, f"{module_name}.{attribute} is not callable"
    return True, "resolved"


def producer_coverage(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Does every REQUIRED declared output have someone to write it?

    The gap Manifest V1 shipped with. A declared path nobody produces is a
    promise the experiment cannot keep, and it looks identical to a kept one
    until the run is attempted.
    """
    allowlist = manifest.get("output_allowlist", {})
    declared = list(allowlist.get("tracked", ())) + list(
        allowlist.get("untracked_runtime", ()))
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    undeclared: list[str] = []

    for path in declared:
        entry = PRODUCER_MAP.get(path)
        if entry is None:
            missing.append(path)
            rows.append({"output": path, "stage": None, "producer": None,
                         "required": True, "resolved": False,
                         "detail": "no producer is declared for this output"})
            continue
        stage, producer, required = entry
        resolved, detail = _resolve_dotted(producer)
        rows.append({"output": path, "stage": stage, "producer": producer,
                     "required": required, "resolved": resolved, "detail": detail})
        if required and not resolved:
            missing.append(path)

    for path in PRODUCER_MAP:
        if path not in declared:
            undeclared.append(path)

    ok = not missing and not undeclared
    return {
        "OUTPUT_PRODUCER_COVERAGE": "PASS" if ok else "FAIL",
        "declared_outputs": len(declared),
        "mapped_outputs": len(PRODUCER_MAP),
        "rows": rows,
        "outputs_without_a_producer": missing,
        "producers_for_undeclared_outputs": undeclared,
        "why_this_exists": (
            "Manifest V1 declared an exact allow-list and never checked that code "
            "existed to write those paths. It was declaration-complete and "
            "execution-incomplete at the same time"
        ),
    }


def runner_resolution(repo_root: Path | str) -> dict[str, Any]:
    """Can the experiment actually be invoked from this tree?"""
    root = Path(repo_root)
    entry = root / RUNNER_ENTRY_POINT
    checks: dict[str, Any] = {}

    checks["runner_path_exists"] = entry.is_file()
    if entry.is_file():
        source = entry.read_bytes()
        checks["runner_sha256"] = hashlib.sha256(source).hexdigest()
        try:
            compile(source, str(entry), "exec")
            checks["runner_parses"] = True
        except SyntaxError as exc:
            checks["runner_parses"] = False
            checks["runner_parse_error"] = str(exc)[:160]
    else:
        checks["runner_sha256"] = None
        checks["runner_parses"] = False

    module_ok, module_detail = _resolve_dotted(RUNNER_MODULE)
    checks["runner_module_resolves"] = module_ok
    checks["runner_module_detail"] = module_detail
    for name in ("resolve_arm", "validate_only", "executability"):
        ok, detail = _resolve_dotted(f"{RUNNER_MODULE}:{name}")
        checks[f"entry_function_{name}"] = ok
        if not ok:
            checks[f"entry_function_{name}_detail"] = detail

    collector_ok, collector_detail = _resolve_dotted(COLLECTOR_ENTRY_POINT)
    checks["collector_resolves"] = collector_ok
    checks["collector_detail"] = collector_detail

    selectors: dict[str, bool] = {}
    for identity in SELECTOR_REGISTRY:
        try:
            resolve_target_selector(identity)
            selectors[identity] = True
        except SelectorResolutionRefused:
            selectors[identity] = False
    checks["selectors_resolve"] = selectors

    # The wiring itself: the collector must actually accept a declaration.
    try:
        from navfm.isaac.collect import CollectConfig

        fields = {f.name for f in dataclasses.fields(CollectConfig)}
        checks["collector_accepts_selector_declaration"] = "target_selector" in fields
    except Exception as exc:
        checks["collector_accepts_selector_declaration"] = False
        checks["collector_wiring_detail"] = f"{type(exc).__name__}: {exc}"[:160]

    ok = bool(
        checks["runner_path_exists"] and checks["runner_parses"]
        and checks["runner_module_resolves"] and checks["collector_resolves"]
        and checks["collector_accepts_selector_declaration"]
        and all(selectors.values())
        and all(checks.get(f"entry_function_{n}") for n in
                ("resolve_arm", "validate_only", "executability"))
    )
    checks["RUNNER_RESOLUTION"] = "PASS" if ok else "FAIL"
    checks["runner_entry_point"] = RUNNER_ENTRY_POINT
    checks["collector_entry_point"] = COLLECTOR_ENTRY_POINT
    return checks


def resolve_arm(manifest: Mapping[str, Any], arm: str) -> ArmResolution:
    """Resolve one arm's complete configuration from the manifest alone."""
    if arm not in ARM_ORDER:
        raise RunnerRefused(
            f"unknown arm {arm!r}; the manifest declares {list(ARM_ORDER)}")
    declared = manifest.get("arms", {}).get("selectors", {}).get(arm)
    if not declared:
        raise RunnerRefused(
            f"the manifest declares no selector for {arm}. An arm without an explicit "
            "selector is refused rather than defaulted, because a default would run "
            "one arm's behaviour under the other arm's label")
    identity = declared.get("target_type")
    if identity not in SELECTOR_REGISTRY:
        raise RunnerRefused(
            f"{arm} declares selector {identity!r}, which this tree does not implement; "
            f"known selectors are {sorted(SELECTOR_REGISTRY)}")
    expected = SELECTOR_ASSIGNMENT[arm]
    if declared.get("selector_class") != expected["selector_class"]:
        raise RunnerRefused(
            f"{arm} declares selector class {declared.get('selector_class')!r}, but the "
            f"frozen assignment is {expected['selector_class']!r}")

    episode = manifest["episode"]
    runtime = manifest["runtime_configuration"]
    suffix = "a" if arm == "ARM_A_CONTROL" else "b"
    return ArmResolution(
        arm=arm,
        selector_identity=str(identity),
        selector_class=str(declared["selector_class"]),
        route=[list(map(float, p)) for p in manifest["route"]["polyline"]],
        seed=int(episode["seed"]),
        initial_pose_xy_yaw=list(map(float, episode["initial_pose_xy_yaw"])),
        goal_xy=list(map(float, episode["goal_xy"])),
        scene_asset=str(episode["scene_asset"]),
        scene_id=str(episode["scene_id"]),
        runtime=dict(runtime),
        outputs={
            "pre_capture": f"runs/bo10/intervention/env/pre_arm_{suffix}.json",
            "post_capture": f"runs/bo10/intervention/env/post_arm_{suffix}.json",
            "trajectory_dir": f"runs/bo10/intervention/arm_{suffix}/",
            "status": f"runs/bo10/intervention/status/arm_{suffix}_status.json",
            "result": f"gates/BO10/intervention/arm_{suffix}_result.json",
            "trace": f"gates/BO10/intervention/arm_{suffix}_terminal_trace.csv",
        },
    )


def build_collect_config(resolution: ArmResolution) -> Any:
    """The collector configuration for this arm. Every value from the manifest."""
    from navfm.isaac.collect import CollectConfig

    runtime = resolution.runtime
    return CollectConfig(
        scenes=[resolution.scene_asset],
        scene_name=resolution.scene_id,
        episodes=1,
        max_steps=int(runtime["max_steps"]),
        cruise_v=float(runtime["cruise_v"]),
        lookahead_m=float(runtime["lookahead_m"]),
        goal_tol_m=float(runtime["goal_tol_m"]),
        seed=int(runtime["seed"]),
        target_selector=resolution.selector_identity,
    )


def executability(
    manifest: Mapping[str, Any], repo_root: Path | str
) -> dict[str, Any]:
    """The structural facts a manifest must establish before it is executable.

    Structural is the operative word. Every entry here is a statement about code
    that exists and resolves, never about a simulator that will succeed.
    """
    root = Path(repo_root)
    runner = runner_resolution(root)
    coverage = producer_coverage(manifest)

    dispatch: dict[str, Any] = {}
    for arm in ARM_ORDER:
        try:
            resolution = resolve_arm(manifest, arm)
            selector = resolve_target_selector(resolution.selector_identity)
            dispatch[arm] = {
                "resolved": True,
                "selector_identity": resolution.selector_identity,
                "selector_class": type(selector).__module__ + "." + type(selector).__name__,
                "matches_frozen_assignment": (
                    resolution.selector_class
                    == SELECTOR_ASSIGNMENT[arm]["selector_class"]),
            }
        except (RunnerRefused, SelectorResolutionRefused) as exc:
            dispatch[arm] = {"resolved": False, "detail": str(exc)[:200]}

    facts = {
        "runner_resolved": runner["RUNNER_RESOLUTION"] == "PASS",
        "runner_sha_present": bool(runner.get("runner_sha256")),
        "collector_resolved": bool(runner["collector_resolves"]),
        "selector_wiring_present": bool(runner["collector_accepts_selector_declaration"]),
        "selectors_resolved": all(runner["selectors_resolve"].values()),
        "arm_a_dispatch_valid": bool(dispatch["ARM_A_CONTROL"].get("resolved")),
        "arm_b_dispatch_valid": bool(dispatch["ARM_B_TREATMENT"].get("resolved")),
        "required_output_producers_complete": (
            coverage["OUTPUT_PRODUCER_COVERAGE"] == "PASS"),
    }
    return {
        "EXECUTABILITY": "PASS" if all(facts.values()) else "FAIL",
        **facts,
        "runner_entry_point": RUNNER_ENTRY_POINT,
        "runner_sha256": runner.get("runner_sha256"),
        "runner_module": RUNNER_MODULE,
        "collector_entry_point": COLLECTOR_ENTRY_POINT,
        "supported_arms": list(ARM_ORDER),
        "selector_registry": sorted(SELECTOR_REGISTRY),
        "arm_dispatch": dispatch,
        "runner_resolution": runner,
        "producer_coverage": coverage,
        "claim_boundary": (
            "these are structural execution-readiness facts: the code required to "
            "attempt an arm exists and resolves. They do NOT claim that Isaac will "
            "launch, that the Hospital asset will load, that rendering will work, or "
            "that the collector will complete"
        ),
    }


def _v2_validator() -> Any:
    from navfm.execution_manifest_v2 import validate_manifest_v2

    return validate_manifest_v2


def _v3_validator() -> Any:
    from navfm.execution_manifest_v2 import validate_manifest_v3

    return validate_manifest_v3


#: Every manifest version this runner will check, and the validator that knows
#: its rules. A version absent from this table is refused by name. Falling back
#: to the oldest validator is how a stricter manifest gets reported as invalid.
_MANIFEST_VALIDATORS: dict[str, Any] = {
    "EXECUTION_MANIFEST_V1": lambda: validate_manifest,
    "EXECUTION_MANIFEST_V2": _v2_validator,
    "EXECUTION_MANIFEST_V3": _v3_validator,
}


def validate_only(
    manifest_path: Path | str, arm: str, repo_root: Path | str
) -> dict[str, Any]:
    """Resolve everything an arm needs, and stop.

    Loads, validates, resolves and reports. Launches nothing, creates no
    production capture, and writes no scientific artefact.
    """
    root = Path(repo_root)
    target = Path(manifest_path)
    if not target.is_file():
        return {"VALIDATE_ONLY": "REFUSED", "arm": arm,
                "reason": f"no manifest at {target}"}
    try:
        manifest = json.loads(target.read_text())
    except json.JSONDecodeError as exc:
        return {"VALIDATE_ONLY": "REFUSED", "arm": arm,
                "reason": f"the manifest does not parse: {exc}"[:200]}

    # Validate a manifest against its own declared version. A manifest checked by
    # an older validator fails on the version field alone, which reports a newer,
    # stricter manifest as invalid -- so the dispatch is a table rather than a
    # chain of branches: an unmapped version must be refused by name, not fall
    # through to the oldest validator that happens to be last. Imported here
    # rather than at module scope because execution_manifest_v2 imports this
    # module.
    declared = manifest.get("manifest_version")
    if declared in _MANIFEST_VALIDATORS:
        validation = _MANIFEST_VALIDATORS[declared]()(manifest, root)
    else:
        return {"VALIDATE_ONLY": "REFUSED", "arm": arm,
                "reason": f"no validator is registered for manifest version "
                          f"{declared!r}; refusing rather than checking it with "
                          f"an older validator",
                "known_versions": sorted(_MANIFEST_VALIDATORS)}
    if validation["MANIFEST_VALID"] != "PASS":
        return {"VALIDATE_ONLY": "REFUSED", "arm": arm,
                "reason": "the manifest did not validate against this repository",
                "manifest_validation": validation}

    try:
        resolution = resolve_arm(manifest, arm)
    except (RunnerRefused, SelectorResolutionRefused) as exc:
        return {"VALIDATE_ONLY": "REFUSED", "arm": arm, "reason": str(exc)[:300]}

    readiness = executability(manifest, root)
    config = build_collect_config(resolution)
    ok = readiness["EXECUTABILITY"] == "PASS"
    return {
        "VALIDATE_ONLY": "PASS" if ok else "REFUSED",
        "arm": arm,
        "manifest": str(target),
        "manifest_digest": validation["manifest_digest"],
        "resolution": resolution.as_dict(),
        "collect_config": dataclasses.asdict(config),
        "executability": readiness,
        "isaac_launched": False,
        "production_capture_created": False,
        "scientific_artefact_written": False,
        "what_this_establishes": (
            "the code path for this arm resolves from the frozen manifest. Nothing "
            "was executed and no simulator was started"
        ),
    }


# --- producers ---------------------------------------------------------------
#
# Implemented so that every declared output has a real writer, and so that
# producer coverage resolves to callables rather than to names. None of them has
# been exercised against a real arm; that is what the first attempt establishes.


def _emit(path: Path | str, record: dict[str, Any], required: tuple[str, ...]) -> str:
    from navfm.evidence import emit_evidence

    return emit_evidence(path, record, required_keys=required)


def write_arm_result(path: Path | str, record: dict[str, Any]) -> str:
    """Persist one arm's scientific result, read back and hashed."""
    return _emit(path, record, ("arm", "selector_identity", "primary_outcome",
                                "termination_reason", "EXECUTION_STATUS"))


def write_status(path: Path | str, record: dict[str, Any]) -> str:
    """Persist one arm's run status and artefact hashes."""
    return _emit(path, record, ("arm", "RUN_OUTCOME", "artefact_hashes"))


def write_comparison(path: Path | str, record: dict[str, Any]) -> str:
    """Persist the two-arm comparison, once both arms are valid."""
    return _emit(path, record, ("ENVIRONMENT_EQUIVALENCE", "INTERVENTION_COMPARISON",
                                "arms"))


def write_terminal_trace(path: Path | str, rows: list[dict[str, Any]],
                         fields: tuple[str, ...]) -> str:
    """Persist the per-step terminal-leg trace as committed text evidence."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields))
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in fields})
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(buffer.getvalue())
    raw = target.read_bytes()
    if not raw.strip():
        raise RunnerRefused(f"the trace at {target} is empty after writing it")
    return hashlib.sha256(raw).hexdigest()
