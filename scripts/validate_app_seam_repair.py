"""Record Attempt 1, and prove the adapter -> collector application seam.

Attempt 1 of the terminal-approach intervention is the first real execution this
project ever authorised. It entered the production lifecycle, created a valid
PRE_ARM_A, launched Isaac, constructed the collector, and stopped at scene
loading with ``unhandled AssertionError:`` and an empty reason.

It is not an Arm-A navigation outcome. No episode started, no trajectory exists,
and nothing about target selection can be concluded from it. The record this
emits says so in the fields a later reader would otherwise mine for a result.

The seam evidence proves the repair directly. The invariant it exists to make
unmissable:

    adapter has IsaacApp  +  collector has correct SimConfig
        !=
    collector has the adapter's IsaacApp

Configuration is declarative and can be perfectly valid while no application
exists. Only the live object can open a stage. So every check here compares
object identity, and the dataflow is read out of the actual signatures rather
than described.

Nothing here starts Isaac, fetches the Hospital asset, or runs an episode.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import inspect
import json
import pathlib
import subprocess
import sys
import tempfile
from typing import Any, cast

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.arm_lifecycle import (  # noqa: E402
    IsaacRuntimeAdapter,
    LifecycleRefused,
    Stage,
)
from navfm.evidence import emit_evidence  # noqa: E402
from navfm.isaac.app import SimConfig  # noqa: E402
from navfm.isaac.collect import CollectConfig, Collector, RuntimeBoundaryError  # noqa: E402

ATTEMPT_OUT = REPO / "gates/BO10/arm_a_attempt_001_20260917.json"
SEAM_OUT = REPO / "gates/BO10/adapter_collector_app_seam_20260917.json"

#: Where Attempt 1 left its capture. Preserved, never reused: it is the evidence
#: that the failed attempt entered the production lifecycle under a valid
#: environment, and a recycled PRE would erase that.
ATTEMPT_001_PRE_REL = "runs/bo10/intervention/arm_a/pre_capture.json"
ATTEMPT_001_HEAD = "01916dfa3a2901177ae1bc07caffd0881139d798"

TRACKED_SOURCES = (
    "src/navfm/isaac/collect.py",
    "src/navfm/arm_lifecycle.py",
    "src/navfm/arm_environment_guard.py",
    "scripts/run_terminal_approach_intervention.py",
)


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def sha256_file(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _blob_sha_at(commit: str, rel: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{rel}"],
                          capture_output=True, check=False)
    return hashlib.sha256(proc.stdout).hexdigest() if proc.returncode == 0 else None


class _StopAfterOpenStage(Exception):
    """Reachability is the claim. What the stage contains is not."""


class _FakeApp:
    """A live application object for the boundary, and nothing more.

    Typed as Any where it crosses into Collector: the point of the control is
    that a stub standing in at the external boundary still exercises the real
    construction path.
    """

    instances = 0

    def __init__(self) -> None:
        type(self).instances += 1
        self.config = SimConfig(hz=12.0, headless=True)
        self.opened: list[str] = []

    def open_stage(self, scene_usd: str) -> None:
        self.opened.append(scene_usd)
        raise _StopAfterOpenStage(scene_usd)


def _collect_config() -> CollectConfig:
    return CollectConfig(scenes=["omniverse://example/hospital.usd"], episodes=1)


def read_dataflow() -> dict[str, Any]:
    """The seam, read from the signatures rather than described."""
    collector_params = list(inspect.signature(Collector.__init__).parameters)
    build = inspect.getsource(IsaacRuntimeAdapter.build_collector)
    open_scene = inspect.getsource(Collector.open_scene)
    run = inspect.getsource(Collector.run)
    return {
        "collector_constructor_parameters": collector_params,
        "collector_accepts_a_live_app": "isaac_app" in collector_params,
        "adapter_passes_the_app": "isaac_app=self._app" in build,
        "open_scene_uses_a_bare_assert": "assert self._app is not None" in open_scene,
        "open_scene_raises_structured": "ISAAC_APP_NOT_BOUND_TO_COLLECTOR" in open_scene,
        "run_enforces_single_owner": "ISAAC_APP_SINGLE_OWNER_VIOLATION" in run,
        "old_dataflow": (
            "IsaacRuntimeAdapter.initialise created and entered an IsaacApp. "
            "build_collector then called Collector(out_dir, collect_config, "
            "self._app.config, M3PRO) -- correct for the `sim: SimConfig` "
            "parameter, and not an application. Collector.run is the only place "
            "that assigned self._app, via `with IsaacApp(self.sim) as app`, and "
            "the adapter never calls run: an arm is one episode under a frozen "
            "route, not a collection loop. So load_scene reached "
            "Collector.open_scene with self._app still None"),
        "corrected_dataflow": (
            "build_collector passes isaac_app=self._app, handing over the object "
            "it owns rather than describing it. open_scene refuses with a named "
            "category instead of a bare assert, and run refuses to create a "
            "second application when one was handed in"),
        "why_every_earlier_gate_passed": (
            "every earlier readiness level was measured through the rehearsal "
            "adapter, whose build_collector returns a dictionary and asserts "
            "nothing. The seam between two individually correct components was "
            "never exercised"),
    }


def prove_seam() -> dict[str, Any]:
    """Identity, invocation count, reachability, and the controls."""
    results: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="app_seam_") as raw:
        tmp = pathlib.Path(raw)

        _FakeApp.instances = 0
        app = _FakeApp()
        adapter = IsaacRuntimeAdapter()
        adapter._app = app
        built = adapter.build_collector(tmp / "traj", _collect_config(), "PATH_VERTEX")
        results["same_object"] = {
            "PASS": adapter._collector._app is app,
            "detail": "the collector holds the adapter's application, not a copy",
            "adapter_reported_binding": built.get("isaac_app_bound"),
        }
        results["single_owner"] = {
            "PASS": _FakeApp.instances == 1,
            "applications_constructed": _FakeApp.instances,
        }
        results["configuration_preserved"] = {
            "PASS": adapter._collector.sim == app.config,
            "detail": "the repair added the app without trading the config away",
        }

        scene = "omniverse://example/hospital.usd"
        reached = False
        try:
            adapter.load_scene(scene, "hospital")
        except _StopAfterOpenStage:
            reached = True
        results["scene_load_reachability"] = {
            "PASS": reached and app.opened == [scene],
            "open_stage_calls": len(app.opened),
            "scene_identifier_passed": app.opened[0] if app.opened else None,
            "detail": ("the call Attempt 1 never made, proven without fetching the "
                       "remote asset"),
        }

        # --- controls -------------------------------------------------------
        controls: dict[str, Any] = {}

        config_only = Collector(tmp / "c", _collect_config(), app.config)
        try:
            config_only.open_scene(scene)
            detected, category, reason = False, None, None
        except RuntimeBoundaryError as exc:
            detected, category, reason = True, exc.category, exc.detail
        controls["config_only_is_refused"] = {
            "DETECTED": detected and category == "ISAAC_APP_NOT_BOUND_TO_COLLECTOR",
            "category": category,
            "reason_is_non_empty": bool(reason and reason.strip()),
            "detail": ("Attempt 1 reproduced exactly: a correct SimConfig and no "
                       "application. This is the control that had to exist"),
        }

        other: Any = _FakeApp()
        mismatched = Collector(tmp / "m", _collect_config(), app.config, isaac_app=other)
        controls["wrong_application_is_visible"] = {
            "DETECTED": mismatched._app is not app,
            "detail": "adapter owns one application and the collector holds another",
        }

        borrowed = Collector(
            tmp / "b", _collect_config(), app.config, isaac_app=cast(Any, app))
        try:
            borrowed.run(["scene.usd"], 1)
            dup_detected, dup_category = False, None
        except RuntimeBoundaryError as exc:
            dup_detected, dup_category = True, exc.category
        controls["duplicate_application_is_refused"] = {
            "DETECTED": dup_detected and dup_category == "ISAAC_APP_SINGLE_OWNER_VIOLATION",
            "category": dup_category,
        }

        bare = IsaacRuntimeAdapter()
        try:
            bare.build_collector(tmp / "n", _collect_config(), "PATH_VERTEX")
            missing_detected, missing_stage = False, None
        except LifecycleRefused as exc:
            missing_detected, missing_stage = True, exc.stage
        controls["missing_runtime_is_refused_at_its_stage"] = {
            "DETECTED": missing_detected and missing_stage == Stage.COLLECTOR_READY.value,
            "stage": missing_stage,
        }

        ordered = IsaacRuntimeAdapter()
        ordered._app = _FakeApp()
        try:
            ordered.load_scene(scene, "hospital")
            order_detected, order_stage = False, None
        except LifecycleRefused as exc:
            order_detected, order_stage = True, exc.stage
        controls["scene_before_collector_is_refused"] = {
            "DETECTED": order_detected and order_stage == Stage.SCENE_READY.value,
            "stage": order_stage,
            "detail": "the order is collector, then scene -- never the reverse",
        }

        no_assert = "assert self._app is not None" not in inspect.getsource(
            Collector.open_scene)
        controls["bare_assertion_removed_from_the_boundary"] = {
            "DETECTED": no_assert,
            "detail": ("an assertion carries no category and, without a message, no "
                       "reason either. Attempt 1 recorded an empty one"),
        }

        results["negative_controls"] = {
            "verdict": "PASS" if all(c["DETECTED"] for c in controls.values()) else "FAIL",
            "results": controls,
        }

    passed = (results["same_object"]["PASS"] and results["single_owner"]["PASS"]
              and results["configuration_preserved"]["PASS"]
              and results["scene_load_reachability"]["PASS"]
              and results["negative_controls"]["verdict"] == "PASS")
    results["ADAPTER_COLLECTOR_APP_SEAM"] = "REPAIRED_AND_VALIDATED" if passed else "FAIL"
    return results


def head_content_coherence(head: str) -> dict[str, Any]:
    """Every recorded source identity must be the content at the named head."""
    rows = []
    for rel in TRACKED_SOURCES:
        recorded = sha256_file(REPO / rel)
        at_head = _blob_sha_at(head, rel)
        rows.append({"path": rel, "recorded_sha256": recorded,
                     "sha256_at_head": at_head, "matches": recorded == at_head})
    coherent = all(r["matches"] for r in rows)
    return {
        "HEAD_CONTENT_COHERENCE": "PASS" if coherent else "FAIL",
        "repository_head": head,
        "sources": rows,
        "rule": ("evidence recording a repository head must be emitted after the "
                 "commit that carries the sources it describes, or it names a head "
                 "that cannot reproduce it"),
    }


def attempt_record(head: str, stamp: str) -> dict[str, Any]:
    pre = REPO / ATTEMPT_001_PRE_REL
    capture = json.loads(pre.read_text()) if pre.is_file() else {}
    return {
        "check": "ARM_A_ATTEMPT_001",
        "artifact_semantics": "EXECUTION_ATTEMPT_RECORD_NO_SCIENTIFIC_RESULT",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "repository_head": head,
        "intervention_id": "TERMINAL_APPROACH_INTERVENTION_V1",
        "arm_id": "ARM_A_CONTROL",
        "attempt_id": "001",
        "CLASSIFICATION": "INFRASTRUCTURE_FAILURE_BEFORE_EPISODE",
        "executed_at_head": ATTEMPT_001_HEAD,
        "executed_under_contract": "V7",
        "executed_under_manifest": "EXECUTION_MANIFEST_V4",
        "observed": {
            "runner_entered_production_lifecycle": True,
            "execution_mode": "REAL",
            "pre_arm_a_created": True,
            "pre_arm_a_validates": capture.get("CAPTURE_VALIDATION") == "PASS",
            "isaac_process_launched": True,
            "isaac_runtime_available": True,
            "collector_constructed": True,
            "scene_request_path_entered": True,
            "hospital_scene_loaded": False,
            "episode_started": False,
            "trajectory_produced": False,
            "post_arm_a_created": False,
            "arm_b_touched": False,
            "stages_entered": [
                "MANIFEST_VALIDATED", "PRE_ENV_CAPTURED", "RUNTIME_INITIALISING",
                "COLLECTOR_READY", "SCENE_READY"],
            "refusal": {
                "stage": "SCENE_READY",
                "reason": "unhandled AssertionError: ",
                "reason_was_empty": True,
                "escaped_exception": True,
            },
            "provenance_of_these_facts": (
                "the PRE capture fields are measured from the artefact on disk; the "
                "stage trace and refusal are the structured result the run itself "
                "returned"),
        },
        "ATTEMPT_001_PRE_CAPTURE": {
            "path": ATTEMPT_001_PRE_REL,
            "sha256": sha256_file(pre),
            "label": capture.get("label"),
            "timestamp_utc": capture.get("timestamp_utc"),
            "capture_validation": capture.get("CAPTURE_VALIDATION"),
            "critical_digest": capture.get("critical_digest"),
            "PRESERVED": True,
            "never_reused": (
                "this capture belongs to attempt 001. A repaired attempt receives a "
                "new identity and a new capture; recycling this one would erase the "
                "evidence that the failed attempt entered the lifecycle under a "
                "valid environment"),
        },
        "EPISODE_STARTED": False,
        "ARM_A_SCIENTIFIC_RESULT": "NOT_OBSERVED",
        "NOT_A_NAVIGATION_OUTCOME": (
            "no episode ran, so this attempt has no success, no failure, no goal "
            "distance and no cross-track. Recording success=false would assert a "
            "completed trial that never began"),
        "excluded_from": [
            "n", "SR", "OSR", "goal distance", "cross-track", "treatment comparison"],
        "root_technical_failure": read_dataflow(),
        "NEXT_ATTEMPT_ID": "002",
        "reattempt_policy": {
            "automatic_retry": False,
            "admissible_only_after": [
                "infrastructure defect repaired",
                "repair independently tested",
                "controller behaviour unchanged",
                "new authoritative amendment frozen",
                "new manifest frozen",
                "new preflight current",
                "explicit human authorisation obtained",
            ],
            "freezing_a_manifest_is_not_authorisation": True,
        },
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_EXECUTION": "ATTEMPT_001_INFRASTRUCTURE_FAILURE",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }


def main() -> int:
    head = _git("rev-parse", "HEAD")
    stamp = _dt.datetime.now(_dt.UTC).isoformat()

    attempt = attempt_record(head, stamp)
    attempt_sha = emit_evidence(ATTEMPT_OUT, attempt, required_keys=(
        "CLASSIFICATION", "ATTEMPT_001_PRE_CAPTURE", "EPISODE_STARTED",
        "ARM_A_SCIENTIFIC_RESULT", "EXECUTION_STATUS"))

    seam = prove_seam()
    coherence = head_content_coherence(head)
    wiring = REPO / "gates/BO10/collector_wiring_regression_20260912.json"
    regression = json.loads(wiring.read_text()) if wiring.is_file() else {}

    record: dict[str, Any] = {
        "check": "ADAPTER_COLLECTOR_APP_SEAM",
        "artifact_semantics": "SEAM_VALIDATION_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "repository_head": head,
        "attempt_001_record": {"path": str(ATTEMPT_OUT.relative_to(REPO)),
                               "sha256": attempt_sha},
        "sources": {rel: sha256_file(REPO / rel) for rel in TRACKED_SOURCES},
        "dataflow": read_dataflow(),
        "proof": seam,
        "HEAD_CONTENT_COHERENCE": coherence,
        "ARM_A_BEHAVIOURAL_REGRESSION": {
            "artefact": {"path": str(wiring.relative_to(REPO)),
                         "sha256": sha256_file(wiring)},
            "verdict": regression.get("ARM_A_COLLECTOR_WIRING_REGRESSION"),
            "traces": {name: {"verdict": t["verdict"],
                              "steps_evaluated": t["steps_evaluated"],
                              "mismatches": sum(t["mismatches_by_channel"].values())}
                       for name, t in regression.get(
                           "regression", {}).get("traces", {}).items()},
            "CLAIM": ("the seam repair moved a runtime object and changed no "
                      "navigation mathematics"),
        },
        "INVARIANT": (
            "configuration compatibility is not live-runtime object propagation. "
            "An adapter holding an IsaacApp and a collector holding the correct "
            "SimConfig is not a collector holding the adapter's IsaacApp"),
        "CLAIM_BOUNDARY": (
            "this establishes that the application propagates and that scene "
            "loading is reachable. It does NOT establish that the Hospital asset "
            "loads, that the render loop runs, or that the collector completes an "
            "episode. No remote asset was fetched"),
        "isaac_launched": False,
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_ATTEMPT_002": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }
    seam_sha = emit_evidence(SEAM_OUT, record, required_keys=(
        "check", "dataflow", "proof", "HEAD_CONTENT_COHERENCE",
        "ARM_A_BEHAVIOURAL_REGRESSION", "EXECUTION_STATUS"))

    ok = (seam["ADAPTER_COLLECTOR_APP_SEAM"] == "REPAIRED_AND_VALIDATED"
          and coherence["HEAD_CONTENT_COHERENCE"] == "PASS"
          and record["ARM_A_BEHAVIOURAL_REGRESSION"]["verdict"] == "PASS")

    print("=" * 70)
    print("ADAPTER -> COLLECTOR APPLICATION SEAM")
    print("=" * 70)
    print(f"HEAD                {head[:12]}")
    print(f"attempt 001 record  {ATTEMPT_OUT.relative_to(REPO)}  {attempt_sha[:16]}...")
    print(f"  classification    {attempt['CLASSIFICATION']}")
    print(f"  PRE preserved     {attempt['ATTEMPT_001_PRE_CAPTURE']['sha256'][:16]}..."
          f"  validates={attempt['observed']['pre_arm_a_validates']}")
    print(f"  episode started   {attempt['EPISODE_STARTED']}")
    print(f"  scientific result {attempt['ARM_A_SCIENTIFIC_RESULT']}")
    print()
    print(f"same object         {seam['same_object']['PASS']}")
    print(f"applications built  {seam['single_owner']['applications_constructed']}")
    print(f"config preserved    {seam['configuration_preserved']['PASS']}")
    print(f"open_stage calls    {seam['scene_load_reachability']['open_stage_calls']}"
          f"  scene={seam['scene_load_reachability']['scene_identifier_passed']}")
    print()
    for name, result in seam["negative_controls"]["results"].items():
        print(f"  {name:44s} {'FIRED' if result['DETECTED'] else 'MISSED'}")
    print()
    for name, trace in record["ARM_A_BEHAVIOURAL_REGRESSION"]["traces"].items():
        print(f"  {name:36s} {trace['verdict']}  steps={trace['steps_evaluated']}  "
              f"mismatches={trace['mismatches']}")
    print()
    print(f"HEAD_CONTENT_COHERENCE  {coherence['HEAD_CONTENT_COHERENCE']}")
    for row in coherence["sources"]:
        if not row["matches"]:
            print(f"  incoherent {row['path']}: recorded {str(row['recorded_sha256'])[:12]}"
                  f" head {str(row['sha256_at_head'])[:12]}")
    print()
    print(f"artefact            {SEAM_OUT.relative_to(REPO)}")
    print(f"sha256              {seam_sha}")
    print(f"ADAPTER_COLLECTOR_APP_SEAM  {seam['ADAPTER_COLLECTOR_APP_SEAM']}")
    print("isaac launched      False")
    print("ARM_A_ATTEMPT_002   NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
