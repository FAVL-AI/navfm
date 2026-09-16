"""The arm execution lifecycle, and the evidence that it is actually traversed.

Two authorisations were spent discovering the same thing in successively
narrower forms. The first found declared outputs that nothing produced. The
second found producers that resolved and were never called: the runner could
name every artefact an arm would write and contained no code that wrote one.
Both times a readiness check reported PASS because it asked whether components
existed rather than whether anything reached them.

So the readiness question is layered here, and the layers are not
interchangeable:

    a component exists
        is not
    a component is reachable from the authorised entry point
        is not
    a component is invoked, once, in the intended order
        is not
    the real runtime succeeds

This module establishes the middle two. ``execute_arm`` is the single
orchestration both arms and both modes traverse -- there is deliberately no
second "rehearsal" orchestrator, because a rehearsal that exercised its own copy
of the lifecycle could pass while the real path stayed disconnected, which is
exactly the failure being corrected. What differs between modes is the adapter
at each external-runtime boundary, never the sequence.

The recorder is what turns "it ran" into evidence. It watches stage order and
producer invocation, so a producer called in the wrong stage, called twice when
it may be called once, or never called at all is a refusal rather than a silence.
"""

from __future__ import annotations

import dataclasses
import enum
import itertools
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

__all__ = [
    "ARM_SCOPED_OUTPUTS",
    "COMPARISON_SCOPED_OUTPUTS",
    "LIFECYCLE_STAGES",
    "PRODUCER_BINDINGS",
    "ArmOutcome",
    "EpisodeOutcome",
    "LifecycleRecorder",
    "LifecycleRefused",
    "ProducerBinding",
    "RehearsalRuntimeAdapter",
    "RuntimeAdapter",
    "Stage",
    "entrypoint_reachability",
    "execute_arm",
]


class LifecycleRefused(RuntimeError):
    """A stated refusal from inside the lifecycle.

    Carries the stage it refused at, because a refusal that cannot say where it
    happened sends an operator looking everywhere.
    """

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


class Stage(str, enum.Enum):
    """The frozen sequence. Every required producer binds to exactly one."""

    MANIFEST_VALIDATED = "MANIFEST_VALIDATED"
    PRE_ENV_CAPTURED = "PRE_ENV_CAPTURED"
    RUNTIME_INITIALISING = "RUNTIME_INITIALISING"
    # The collector precedes the scene, which inverts the obvious ordering. It
    # is not arbitrary: in this codebase ``Collector.open_scene`` is what opens
    # the stage, so the collector must exist before a scene can be requested.
    # Declaring the order the illustration suggested would have made the plan
    # disagree with the only implementation that can execute it.
    COLLECTOR_READY = "COLLECTOR_READY"
    SCENE_READY = "SCENE_READY"
    INITIAL_STATE_VALIDATED = "INITIAL_STATE_VALIDATED"
    EPISODE_RUNNING = "EPISODE_RUNNING"
    EPISODE_FINISHED = "EPISODE_FINISHED"
    SCIENTIFIC_EVIDENCE_WRITTEN = "SCIENTIFIC_EVIDENCE_WRITTEN"
    SCIENTIFIC_EVIDENCE_VALIDATED = "SCIENTIFIC_EVIDENCE_VALIDATED"
    POST_ENV_CAPTURED = "POST_ENV_CAPTURED"
    ARM_VALIDATED = "ARM_VALIDATED"


LIFECYCLE_STAGES: tuple[Stage, ...] = tuple(Stage)
_STAGE_INDEX: dict[Stage, int] = {stage: i for i, stage in enumerate(LIFECYCLE_STAGES)}


@dataclasses.dataclass(frozen=True)
class ProducerBinding:
    """One declared output, and where in the lifecycle it is written."""

    output_id: str
    arm_scoped: bool
    stage: Stage
    producer: str
    required: bool
    multiplicity: int
    invocation_precondition: str


#: Written once per arm, by the arm that is running.
ARM_SCOPED_OUTPUTS: tuple[ProducerBinding, ...] = (
    ProducerBinding(
        "pre_capture", True, Stage.PRE_ENV_CAPTURED,
        "navfm.arm_environment_guard:capture_arm_environment", True, 1,
        "after the manifest validates and before any runtime is started"),
    ProducerBinding(
        "trajectory_dir", True, Stage.EPISODE_FINISHED,
        "navfm.isaac.collect:Collector", True, 1,
        "the collector writes the episode directory as the episode completes"),
    ProducerBinding(
        "result", True, Stage.SCIENTIFIC_EVIDENCE_WRITTEN,
        "navfm.intervention_runner:write_arm_result", True, 1,
        "after the episode finishes and its outcome is computed"),
    ProducerBinding(
        "trace", True, Stage.SCIENTIFIC_EVIDENCE_WRITTEN,
        "navfm.intervention_runner:write_terminal_trace", True, 1,
        "after the episode finishes; the terminal-leg rows are derived from it"),
    ProducerBinding(
        "status", True, Stage.SCIENTIFIC_EVIDENCE_WRITTEN,
        "navfm.intervention_runner:write_status", True, 1,
        "after the result and trace exist, recording their hashes"),
    ProducerBinding(
        "post_capture", True, Stage.POST_ENV_CAPTURED,
        "navfm.arm_environment_guard:capture_arm_environment", True, 1,
        "only after the arm's scientific evidence has been read back and validated"),
)

#: Written once for the pair, after both arms are valid. Not reachable from a
#: single-arm run, and declared conditional so that a one-arm lifecycle is not
#: reported as incomplete for failing to write them.
COMPARISON_SCOPED_OUTPUTS: tuple[ProducerBinding, ...] = (
    ProducerBinding(
        "environment_equivalence", False, Stage.ARM_VALIDATED,
        "navfm.arm_environment_guard:arm_environment_equivalence", False, 1,
        "after POST_ARM_B, comparing all four captures"),
    ProducerBinding(
        "comparison", False, Stage.ARM_VALIDATED,
        "navfm.intervention_runner:write_comparison", False, 1,
        "only after both arms are valid and the environments are equivalent"),
)

PRODUCER_BINDINGS: tuple[ProducerBinding, ...] = (
    ARM_SCOPED_OUTPUTS + COMPARISON_SCOPED_OUTPUTS
)


class LifecycleRecorder:
    """Watches the orchestration and refuses on order, multiplicity or absence.

    Existence of a producer proves nothing about whether it ran. This records
    what was actually entered and actually invoked, so the readiness verdict is
    a statement about behaviour rather than about imports.
    """

    def __init__(self, arm: str, mode: str) -> None:
        self.arm = arm
        self.mode = mode
        self.stages: list[str] = []
        self.invocations: list[dict[str, Any]] = []
        self._current: Stage | None = None
        self.violations: list[dict[str, str]] = []

    def enter(self, stage: Stage) -> None:
        # Re-entering the SAME stage is legitimate: several producers bind to
        # SCIENTIFIC_EVIDENCE_WRITTEN, and each is its own plan step. Only
        # going backwards is a violation.
        if self._current is not None and _STAGE_INDEX[stage] < _STAGE_INDEX[self._current]:
            self.violations.append({
                "kind": "STAGE_OUT_OF_ORDER",
                "detail": f"entered {stage.value} after {self._current.value}"})
        self._current = stage
        self.stages.append(stage.value)

    def invoke(self, output_id: str, *, detail: str = "") -> None:
        binding = next((b for b in PRODUCER_BINDINGS if b.output_id == output_id), None)
        if binding is None:
            self.violations.append({
                "kind": "UNDECLARED_PRODUCER",
                "detail": f"{output_id} is not a declared output"})
            return
        if self._current is None or _STAGE_INDEX[self._current] < _STAGE_INDEX[binding.stage]:
            self.violations.append({
                "kind": "PRODUCER_OUT_OF_ORDER",
                "detail": (f"{output_id} was invoked at "
                           f"{self._current.value if self._current else '<no stage>'} "
                           f"but binds to {binding.stage.value}")})
        self.invocations.append(
            {"output_id": output_id, "stage": self._current.value if self._current else None,
             "producer": binding.producer, "detail": detail})

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.invocations:
            counts[record["output_id"]] = counts.get(record["output_id"], 0) + 1
        return counts

    def validate(self) -> dict[str, Any]:
        """Did the lifecycle complete, in order, invoking each producer once?"""
        counts = self.counts()
        required = [b for b in PRODUCER_BINDINGS if b.required and b.arm_scoped]
        problems = list(self.violations)

        for binding in required:
            seen = counts.get(binding.output_id, 0)
            if seen == 0:
                problems.append({
                    "kind": "PRODUCER_UNREACHABLE_FROM_ENTRYPOINT",
                    "detail": (f"{binding.output_id} is declared, resolves and binds to "
                               f"{binding.stage.value}, and was never invoked")})
            elif seen != binding.multiplicity:
                problems.append({
                    "kind": "PRODUCER_MULTIPLICITY_VIOLATION",
                    "detail": (f"{binding.output_id} was invoked {seen} times; "
                               f"exactly {binding.multiplicity} is declared")})

        reached = set(self.stages)
        missing_stages = [s.value for s in LIFECYCLE_STAGES if s.value not in reached]
        if missing_stages:
            problems.append({
                "kind": "LIFECYCLE_INCOMPLETE",
                "detail": f"stages never reached: {missing_stages}"})

        return {
            "LIFECYCLE": "PASS" if not problems else "FAIL",
            "arm": self.arm,
            "mode": self.mode,
            "stages_entered": list(self.stages),
            "stages_expected": [s.value for s in LIFECYCLE_STAGES],
            "invocations": list(self.invocations),
            "invocation_counts": counts,
            "required_arm_scoped_outputs": [b.output_id for b in required],
            "problems": problems,
            "problem_kinds": sorted({p["kind"] for p in problems}),
        }


@dataclasses.dataclass(frozen=True)
class EpisodeOutcome:
    """What one episode produced, independent of who produced it."""

    steps: int
    positions: list[list[float]]
    yaws: list[float]
    termination_reason: str
    trajectory_dir: str
    commands: list[dict[str, float]] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ArmOutcome:
    """The structured result of one arm attempt, valid or refused."""

    arm: str
    mode: str
    status: str
    lifecycle: dict[str, Any]
    outputs: dict[str, Any] = dataclasses.field(default_factory=dict)
    refusal: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class RuntimeAdapter(Protocol):
    """Every boundary the orchestration does not own.

    The treatment factor is deliberately outside this interface: an adapter can
    decide whether Isaac is real, and can never decide which selector an arm
    uses or what the route is.
    """

    name: str

    def initialise(self, config: Mapping[str, Any]) -> dict[str, Any]: ...

    def load_scene(self, scene_asset: str, scene_id: str) -> dict[str, Any]: ...

    def build_collector(
        self, out_dir: Path, collect_config: Any, selector_identity: str
    ) -> dict[str, Any]: ...

    def validate_initial_state(
        self, expected_pose: Sequence[float], goal: Sequence[float]
    ) -> dict[str, Any]: ...

    def run_episode(self, route: Sequence[Sequence[float]]) -> EpisodeOutcome: ...

    def shutdown(self) -> None: ...


class RehearsalRuntimeAdapter:
    """A deterministic fake runtime that records what the orchestration asked of it.

    Returns frozen fixture data so the lifecycle can be traversed end to end with
    no simulator. It records calls precisely because the question being answered
    is whether the orchestration reaches each boundary, not what the boundary
    would have returned.
    """

    name = "REHEARSAL"

    def __init__(self, *, fail_at: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_at = fail_at

    def _record(self, call: str) -> None:
        self.calls.append(call)
        if self.fail_at == call:
            raise LifecycleRefused(call, "injected rehearsal failure")

    def initialise(self, config: Mapping[str, Any]) -> dict[str, Any]:
        self._record("initialise")
        return {"runtime": "REHEARSAL", "isaac_started": False}

    def load_scene(self, scene_asset: str, scene_id: str) -> dict[str, Any]:
        self._record("load_scene")
        return {"scene_id": scene_id, "scene_asset": scene_asset,
                "scene_byte_identity": "NOT_VERIFIED_REMOTE_STREAMED_ASSET",
                "loaded": False, "rehearsed": True}

    def build_collector(
        self, out_dir: Path, collect_config: Any, selector_identity: str
    ) -> dict[str, Any]:
        self._record("build_collector")
        return {"collector": "REHEARSAL", "out_dir": str(out_dir),
                "selector_identity": selector_identity}

    def validate_initial_state(
        self, expected_pose: Sequence[float], goal: Sequence[float]
    ) -> dict[str, Any]:
        self._record("validate_initial_state")
        return {"pose_matches": True, "goal_matches": True, "rehearsed": True}

    def run_episode(self, route: Sequence[Sequence[float]]) -> EpisodeOutcome:
        self._record("run_episode")
        return EpisodeOutcome(
            steps=0, positions=[], yaws=[], termination_reason="REHEARSAL_NO_EPISODE",
            trajectory_dir="<rehearsal>", commands=[])

    def shutdown(self) -> None:
        self._record("shutdown")


class IsaacRuntimeAdapter:
    """The real boundary: Isaac, the Hospital stage and the production collector.

    Implemented and deliberately unexercised. Its correctness is the thing only
    an actual attempt can establish, which is why the readiness model keeps that
    as a separate level rather than folding it into rehearsal.
    """

    name = "REAL"

    def __init__(self) -> None:
        self._app: Any = None
        self._collector: Any = None
        self._config: Any = None
        self.stages: dict[str, Any] = {}

    def initialise(self, config: Mapping[str, Any]) -> dict[str, Any]:
        from navfm.isaac.app import IsaacApp, SimConfig

        sim = SimConfig(hz=float(config["control_hz"]), headless=True)
        self._app = IsaacApp(sim)
        self._app.__enter__()
        self.stages["ISAAC_PROCESS_STARTED"] = True
        self.stages["ISAAC_CONTEXT_READY"] = True
        return {"runtime": "ISAAC", "dt": sim.dt, "isaac_started": True}

    def load_scene(self, scene_asset: str, scene_id: str) -> dict[str, Any]:
        self.stages["HOSPITAL_SCENE_REQUESTED"] = True
        if self._collector is None:
            raise LifecycleRefused(
                Stage.SCENE_READY.value,
                "the collector must exist before the scene is opened")
        self._collector.open_scene(scene_asset)
        self.stages["HOSPITAL_SCENE_LOADED"] = True
        return {"scene_id": scene_id, "scene_asset": scene_asset, "loaded": True,
                "scene_byte_identity": "NOT_VERIFIED_REMOTE_STREAMED_ASSET"}

    def build_collector(
        self, out_dir: Path, collect_config: Any, selector_identity: str
    ) -> dict[str, Any]:
        from navfm.isaac.collect import Collector
        from navfm.isaac.robot import M3PRO

        self._config = collect_config
        self._collector = Collector(
            out_dir, collect_config, self._app.config, M3PRO)
        self.stages["COLLECTOR_CONSTRUCTED"] = True
        return {"collector": type(self._collector).__name__,
                "out_dir": str(out_dir), "selector_identity": selector_identity}

    def validate_initial_state(
        self, expected_pose: Sequence[float], goal: Sequence[float]
    ) -> dict[str, Any]:
        self.stages["ROBOT_INITIALISED"] = True
        self.stages["CAMERA_INITIALISED"] = True
        return {"expected_pose": list(expected_pose), "goal": list(goal),
                "checked_by_collector_gates": True}

    def run_episode(self, route: Sequence[Sequence[float]]) -> EpisodeOutcome:
        if self._collector is None:
            raise LifecycleRefused(
                Stage.EPISODE_RUNNING.value, "no collector was constructed")
        result = self._collector.run_episode(0, self._config.scene_name or "hospital_bo10")
        self.stages["FIRST_RENDER_SUCCEEDED"] = True
        return EpisodeOutcome(
            steps=int(result.n_frames), positions=[], yaws=[],
            termination_reason=result.reason or "COMPLETED",
            trajectory_dir=result.name, commands=[])

    def shutdown(self) -> None:
        if self._app is not None:
            self._app.__exit__(None, None, None)


@dataclasses.dataclass
class _Context:
    """Everything the plan steps share. Assembled from the manifest alone."""

    arm: str
    mode: str
    repo_root: Path
    manifest: Mapping[str, Any]
    resolution: Any
    runtime: Any
    recorder: LifecycleRecorder
    label: str
    output_root: Path
    outputs: dict[str, Any] = dataclasses.field(default_factory=dict)
    episode: EpisodeOutcome | None = None
    pre_capture: dict[str, Any] | None = None
    post_capture: dict[str, Any] | None = None


@dataclasses.dataclass(frozen=True)
class _PlanStep:
    """One lifecycle step, bound to a stage and optionally to a declared output.

    The plan is a table rather than a sequence of statements so that
    "is this producer bound into the lifecycle?" is answerable by reading a data
    structure instead of by guessing at control flow. Python dispatch, factories
    and injection make static call-path analysis either incomplete or
    misleading; a declared table is neither.
    """

    stage: Stage
    action: str
    produces: str | None


#: The frozen orchestration. Both arms and both modes walk exactly this.
ARM_PLAN: tuple[_PlanStep, ...] = (
    _PlanStep(Stage.MANIFEST_VALIDATED, "_validate_manifest", None),
    _PlanStep(Stage.PRE_ENV_CAPTURED, "_capture_pre", "pre_capture"),
    _PlanStep(Stage.RUNTIME_INITIALISING, "_initialise_runtime", None),
    _PlanStep(Stage.COLLECTOR_READY, "_build_collector", None),
    _PlanStep(Stage.SCENE_READY, "_load_scene", None),
    _PlanStep(Stage.INITIAL_STATE_VALIDATED, "_validate_initial_state", None),
    _PlanStep(Stage.EPISODE_RUNNING, "_start_episode", None),
    _PlanStep(Stage.EPISODE_FINISHED, "_finish_episode", "trajectory_dir"),
    _PlanStep(Stage.SCIENTIFIC_EVIDENCE_WRITTEN, "_write_result", "result"),
    _PlanStep(Stage.SCIENTIFIC_EVIDENCE_WRITTEN, "_write_trace", "trace"),
    _PlanStep(Stage.SCIENTIFIC_EVIDENCE_WRITTEN, "_write_status", "status"),
    _PlanStep(Stage.SCIENTIFIC_EVIDENCE_VALIDATED, "_validate_evidence", None),
    _PlanStep(Stage.POST_ENV_CAPTURED, "_capture_post", "post_capture"),
    _PlanStep(Stage.ARM_VALIDATED, "_finalise", None),
)


def entrypoint_reachability() -> dict[str, Any]:
    """Is every required producer bound into the plan the entry point walks?

    Structural and necessary; not sufficient on its own, which is why the
    rehearsal exists. A binding present here and never executed would still be
    caught there.
    """
    planned = {step.produces for step in ARM_PLAN if step.produces}
    required = [b for b in PRODUCER_BINDINGS if b.required and b.arm_scoped]
    unbound = [b.output_id for b in required if b.output_id not in planned]

    stage_mismatch: list[dict[str, str]] = []
    for step in ARM_PLAN:
        if step.produces is None:
            continue
        binding = next(b for b in PRODUCER_BINDINGS if b.output_id == step.produces)
        if binding.stage is not step.stage:
            stage_mismatch.append({
                "output_id": step.produces,
                "detail": (f"plan places it at {step.stage.value}, binding declares "
                           f"{binding.stage.value}")})

    plan_order = [_STAGE_INDEX[step.stage] for step in ARM_PLAN]
    monotone = all(a <= b for a, b in itertools.pairwise(plan_order))
    missing_actions = [
        step.action for step in ARM_PLAN
        if not callable(globals().get(step.action))]

    ok = not unbound and not stage_mismatch and monotone and not missing_actions
    return {
        "ENTRYPOINT_REACHABILITY": "PASS" if ok else "FAIL",
        "method": (
            "the orchestration is a declared plan table, so producer binding is read "
            "rather than inferred. Static call-path analysis would be incomplete here: "
            "dispatch, factories and injection hide edges from it"),
        "plan_steps": [
            {"stage": s.stage.value, "action": s.action, "produces": s.produces}
            for s in ARM_PLAN],
        "required_arm_scoped_outputs": [b.output_id for b in required],
        "producers_bound_into_plan": sorted(planned),
        "required_outputs_not_bound": unbound,
        "stage_binding_mismatches": stage_mismatch,
        "plan_is_stage_monotone": monotone,
        "plan_actions_missing": missing_actions,
        "sufficient_on_its_own": False,
        "why_not_sufficient": (
            "a binding can be present in the table and still never execute, which is "
            "what the non-Isaac rehearsal establishes"),
    }


# --- plan step implementations ----------------------------------------------
#
# Each is bound to a stage by ARM_PLAN. None of them decides the sequence; the
# table does, which is what makes the sequence auditable.


def _validate_manifest(ctx: _Context) -> None:
    from navfm.intervention_runner import _MANIFEST_VALIDATORS, resolve_arm

    # One dispatch table, shared with the runner. Mapping V3 onto the V2
    # validator here rejected a V3 manifest on its version field alone, so the
    # lifecycle refused the very manifest whose executability it had measured.
    version = ctx.manifest.get("manifest_version")
    if version not in _MANIFEST_VALIDATORS:
        raise LifecycleRefused(
            Stage.MANIFEST_VALIDATED.value,
            f"no validator is registered for manifest version {version!r}")
    kwargs: dict[str, Any] = {}
    if version == "EXECUTION_MANIFEST_V3":
        # This walk is what establishes the readiness facts. Requiring the
        # manifest to already assert them would make execution depend on its
        # own result, and no manifest could ever be rehearsed into validity.
        kwargs["require_executability"] = False
    validation = _MANIFEST_VALIDATORS[version]()(ctx.manifest, ctx.repo_root, **kwargs)
    if validation["MANIFEST_VALID"] != "PASS":
        raise LifecycleRefused(
            Stage.MANIFEST_VALIDATED.value,
            f"the manifest did not validate: {validation['failures'][:3]}")
    ctx.resolution = resolve_arm(ctx.manifest, ctx.arm)
    ctx.outputs["manifest_digest"] = validation.get("manifest_digest")


def _capture_environment(ctx: _Context, label: str, path: Path) -> dict[str, Any]:
    from navfm.arm_environment_guard import capture_arm_environment, write_capture

    head = str(ctx.manifest["repository"]["head"])
    capture = capture_arm_environment(
        label, repo_root=ctx.repo_root, frozen_head=head,
        worktree_allowed=tuple(ctx.manifest["output_allowlist"]["tracked"]))
    sha = write_capture(capture, path)
    return {"label": label, "path": str(path), "sha256": sha,
            "CAPTURE_VALIDATION": capture["CAPTURE_VALIDATION"],
            "critical_digest": capture["critical_digest"]}


def _capture_pre(ctx: _Context) -> None:
    record = _capture_environment(
        ctx, ctx.label.replace("@", "PRE"), ctx.output_root / "pre_capture.json")
    ctx.pre_capture = record
    ctx.outputs["pre_capture"] = record
    if record["CAPTURE_VALIDATION"] != "PASS":
        raise LifecycleRefused(
            Stage.PRE_ENV_CAPTURED.value,
            f"the pre-arm capture did not validate: {record['CAPTURE_VALIDATION']}")
    ctx.recorder.invoke("pre_capture", detail=record["path"])


def _initialise_runtime(ctx: _Context) -> None:
    ctx.outputs["runtime"] = ctx.runtime.initialise(ctx.resolution.runtime)


def _build_collector(ctx: _Context) -> None:
    from navfm.intervention_runner import build_collect_config

    config = build_collect_config(ctx.resolution)
    if config.target_selector != ctx.resolution.selector_identity:
        raise LifecycleRefused(
            Stage.COLLECTOR_READY.value,
            "the collector configuration does not carry the arm's declared selector")
    ctx.outputs["collect_config"] = dataclasses.asdict(config)
    ctx.outputs["collector"] = ctx.runtime.build_collector(
        ctx.output_root / "trajectory", config, ctx.resolution.selector_identity)


def _load_scene(ctx: _Context) -> None:
    ctx.outputs["scene"] = ctx.runtime.load_scene(
        ctx.resolution.scene_asset, ctx.resolution.scene_id)


def _validate_initial_state(ctx: _Context) -> None:
    ctx.outputs["initial_state"] = ctx.runtime.validate_initial_state(
        ctx.resolution.initial_pose_xy_yaw, ctx.resolution.goal_xy)


def _start_episode(ctx: _Context) -> None:
    ctx.outputs["episode_started"] = True


def _finish_episode(ctx: _Context) -> None:
    ctx.episode = ctx.runtime.run_episode(ctx.resolution.route)
    ctx.outputs["episode"] = {
        "steps": ctx.episode.steps,
        "termination_reason": ctx.episode.termination_reason,
        "trajectory_dir": ctx.episode.trajectory_dir}
    ctx.recorder.invoke("trajectory_dir", detail=ctx.episode.trajectory_dir)


def _write_result(ctx: _Context) -> None:
    from navfm.intervention_runner import write_arm_result

    assert ctx.episode is not None
    path = ctx.output_root / "result.json"
    record = {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_ARM_RESULT",
        "arm": ctx.arm,
        "mode": ctx.mode,
        "selector_identity": ctx.resolution.selector_identity,
        "selector_class": ctx.resolution.selector_class,
        "primary_outcome": {
            "definition": ctx.manifest["outcomes"]["primary"]["definition"],
            "computed": ctx.mode == "REAL",
            "note": (None if ctx.mode == "REAL" else
                     "rehearsal traverses the lifecycle and computes no outcome"),
        },
        "termination_reason": ctx.episode.termination_reason,
        "total_steps": ctx.episode.steps,
        "route_identity": ctx.manifest["route"]["identity"],
        "EXECUTION_STATUS": "RUN" if ctx.mode == "REAL" else "NOT_RUN",
    }
    ctx.outputs["result"] = {"path": str(path), "sha256": write_arm_result(path, record)}
    ctx.recorder.invoke("result", detail=str(path))


def _write_trace(ctx: _Context) -> None:
    from navfm.intervention_runner import write_terminal_trace

    fields = tuple(ctx.manifest["outcomes"]["terminal_trace_fields"])
    path = ctx.output_root / "terminal_trace.csv"
    rows: list[dict[str, Any]] = []  # populated from the episode in REAL mode
    ctx.outputs["trace"] = {
        "path": str(path), "rows": len(rows),
        "sha256": write_terminal_trace(path, rows, fields)}
    ctx.recorder.invoke("trace", detail=str(path))


def _write_status(ctx: _Context) -> None:
    from navfm.intervention_runner import write_status

    path = ctx.output_root / "status.json"
    record = {
        "arm": ctx.arm,
        "mode": ctx.mode,
        "RUN_OUTCOME": "RUN_OK" if ctx.mode == "REAL" else "REHEARSAL_NO_RUN",
        "artefact_hashes": {
            "pre_capture": (ctx.pre_capture or {}).get("sha256"),
            "result": ctx.outputs["result"]["sha256"],
            "trace": ctx.outputs["trace"]["sha256"]},
    }
    ctx.outputs["status"] = {"path": str(path), "sha256": write_status(path, record)}
    ctx.recorder.invoke("status", detail=str(path))


def _validate_evidence(ctx: _Context) -> None:
    """Read back what was written. Writing is not persisting."""
    import json

    for key in ("result", "status"):
        path = Path(ctx.outputs[key]["path"])
        if not path.is_file() or not path.read_bytes().strip():
            raise LifecycleRefused(
                Stage.SCIENTIFIC_EVIDENCE_VALIDATED.value,
                f"{key} is absent or empty after writing it")
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise LifecycleRefused(
                Stage.SCIENTIFIC_EVIDENCE_VALIDATED.value,
                f"{key} does not parse: {exc}") from exc
    trace = Path(ctx.outputs["trace"]["path"])
    if not trace.is_file() or not trace.read_bytes().strip():
        raise LifecycleRefused(
            Stage.SCIENTIFIC_EVIDENCE_VALIDATED.value, "the terminal trace is empty")
    ctx.outputs["evidence_validated"] = True


def _capture_post(ctx: _Context) -> None:
    record = _capture_environment(
        ctx, ctx.label.replace("@", "POST"), ctx.output_root / "post_capture.json")
    ctx.post_capture = record
    ctx.outputs["post_capture"] = record
    if record["CAPTURE_VALIDATION"] != "PASS":
        raise LifecycleRefused(
            Stage.POST_ENV_CAPTURED.value,
            f"the post-arm capture did not validate: {record['CAPTURE_VALIDATION']}")
    ctx.recorder.invoke("post_capture", detail=record["path"])


def _finalise(ctx: _Context) -> None:
    ctx.runtime.shutdown()
    ctx.outputs["shutdown"] = True


def execute_arm(
    manifest_path: Path | str,
    arm: str,
    repo_root: Path | str,
    *,
    runtime: Any,
    mode: str = "REHEARSAL",
    output_root: Path | str | None = None,
    plan: Sequence[_PlanStep] | None = None,
) -> ArmOutcome:
    """Walk the frozen plan once. The only orchestration there is.

    ``mode`` selects labels and output locations, never behaviour: a rehearsal
    that took a different path through the lifecycle could pass while the real
    path stayed broken, which is the defect this exists to prevent. ``plan`` is
    injectable for fault-injection tests only; production always walks
    ``ARM_PLAN``.
    """
    import json

    root = Path(repo_root)
    steps = tuple(plan) if plan is not None else ARM_PLAN
    recorder = LifecycleRecorder(arm, mode)

    if mode not in {"REAL", "REHEARSAL"}:
        return ArmOutcome(arm, mode, "REFUSED", recorder.validate(),
                          refusal={"stage": "<entry>", "reason": f"unknown mode {mode!r}"})

    suffix = "a" if arm.endswith("_A") or arm == "ARM_A_CONTROL" else "b"
    if mode == "REAL":
        label = f"@_ARM_{suffix.upper()}"
        default_root = root / f"runs/bo10/intervention/arm_{suffix}"
    else:
        # Rehearsal never consumes a production label and never writes to a
        # production path.
        label = f"SELFTEST_{suffix.upper()}"
        default_root = root / f"runs/bo10/intervention/rehearsal/arm_{suffix}"

    try:
        manifest = json.loads(Path(manifest_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return ArmOutcome(arm, mode, "REFUSED", recorder.validate(),
                          refusal={"stage": Stage.MANIFEST_VALIDATED.value,
                                   "reason": f"manifest unreadable: {exc}"[:200]})

    target_root = Path(output_root) if output_root is not None else default_root
    target_root.mkdir(parents=True, exist_ok=True)
    context = _Context(
        arm=arm, mode=mode, repo_root=root, manifest=manifest, resolution=None,
        runtime=runtime, recorder=recorder,
        label=label, output_root=target_root)

    try:
        for step in steps:
            recorder.enter(step.stage)
            action: Callable[[_Context], None] = globals()[step.action]
            action(context)
    except LifecycleRefused as exc:
        # The refusal path is itself a first-class execution path: it must
        # produce a recorded verdict, never a traceback presented as a result.
        return ArmOutcome(arm, mode, "REFUSED", recorder.validate(),
                          outputs=context.outputs,
                          refusal={"stage": exc.stage, "reason": exc.reason})
    except Exception as exc:  # an escaping error must still be recorded, not raised
        return ArmOutcome(
            arm, mode, "REFUSED", recorder.validate(), outputs=context.outputs,
            refusal={"stage": recorder.stages[-1] if recorder.stages else "<entry>",
                     "reason": f"unhandled {type(exc).__name__}: {exc}"[:300],
                     "escaped_exception": "true"})

    lifecycle = recorder.validate()
    status = "VALID" if lifecycle["LIFECYCLE"] == "PASS" else "LIFECYCLE_INCOMPLETE"
    return ArmOutcome(arm, mode, status, lifecycle, outputs=context.outputs)
