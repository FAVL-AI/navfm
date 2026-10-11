"""Controls for LEVEL 4.5 -- is the REAL lifecycle reachable from the runner?

V6 froze a tree whose manifest declared the real adapter by dotted path while
nothing constructed it and ``mode="REAL"`` was passed nowhere. Every readiness
level had been measured through the rehearsal adapter, so the gate reported
READY_FOR_ARM_A_ATTEMPT for a runner that could only refuse the canonical
Arm-A invocation.

The lesson these controls encode is narrow and worth stating exactly: a dotted
path in a manifest is a string. Producer coverage learned this at V2 and the
adapter learned it again at V6, one layer up. So nothing here asserts that a
name resolves. Everything asserts that something was *built*, and that the
count is observed rather than declared.

The probe stops at MANIFEST_VALIDATED on purpose. The next stage writes a
capture labelled PRE_ARM_A, and no arm is authorised.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
RUNNER_REL = "scripts/run_terminal_approach_intervention.py"
GATE_REL = "scripts/validate_real_mode_reachability.py"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner() -> Any:
    return _load(REPO / RUNNER_REL, "arm_runner_under_test")


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load(REPO / GATE_REL, "reachability_gate_under_test")


# --- structural --------------------------------------------------------------

def test_the_runner_has_a_real_entry_point(runner: Any) -> None:
    assert callable(runner.run_real_arm)


def test_the_real_entry_point_defaults_to_the_isaac_adapter(runner: Any) -> None:
    """Not that a manifest names it -- that this function builds it."""
    import inspect

    source = inspect.getsource(runner.run_real_arm)
    assert "IsaacRuntimeAdapter if runtime_factory is None" in source
    assert 'mode="REAL"' in source


def test_the_runtime_factory_is_not_reachable_from_the_command_line(
    runner: Any,
) -> None:
    """A CLI that can swap the runtime can swap the experiment after a result."""
    import inspect

    assert "runtime_factory" not in inspect.getsource(runner.build_parser)
    parser = runner.build_parser()
    flags = {action.dest for action in parser._actions}
    assert "runtime_factory" not in flags


# --- the probe ---------------------------------------------------------------

def test_the_entry_point_enters_real_mode_and_builds_the_given_adapter(
    runner: Any, tmp_path: Path,
) -> None:
    built: list[str] = []

    class _Probe:
        def __init__(self) -> None:
            built.append("constructed")

    bad = tmp_path / "unparseable.json"
    bad.write_text("{ not json")
    outcome, runtime = runner.run_real_arm(
        bad, "ARM_A_CONTROL", REPO, runtime_factory=_Probe)

    assert outcome.mode == "REAL"
    assert built == ["constructed"]
    assert isinstance(runtime, _Probe)


def test_the_probe_refuses_before_the_stage_that_writes_a_capture(
    runner: Any, tmp_path: Path,
) -> None:
    """PRE_ENV_CAPTURED writes PRE_ARM_A. The probe must stop before it."""
    from navfm.arm_lifecycle import LIFECYCLE_STAGES

    bad = tmp_path / "unparseable.json"
    bad.write_text("{ not json")
    outcome, _ = runner.run_real_arm(
        bad, "ARM_A_CONTROL", REPO, runtime_factory=lambda: object())

    assert outcome.status == "REFUSED"
    assert outcome.refusal is not None
    assert outcome.refusal["stage"] == "MANIFEST_VALIDATED"

    stages = [s.value for s in LIFECYCLE_STAGES]
    assert stages.index("MANIFEST_VALIDATED") < stages.index("PRE_ENV_CAPTURED")
    assert outcome.lifecycle["stages_entered"] == []


def test_the_probe_consumes_no_production_label(runner: Any, tmp_path: Path) -> None:
    bad = tmp_path / "unparseable.json"
    bad.write_text("{ not json")
    outcome, _ = runner.run_real_arm(
        bad, "ARM_A_CONTROL", REPO, runtime_factory=lambda: object())
    blob = json.dumps(outcome.as_dict(), default=str)
    for label in ("PRE_ARM_A", "POST_ARM_A", "PRE_ARM_B", "POST_ARM_B"):
        assert label not in blob


def test_the_probe_writes_nothing_at_all(runner: Any, tmp_path: Path) -> None:
    """The lifecycle returns before it creates an output root."""
    bad = tmp_path / "unparseable.json"
    bad.write_text("{ not json")
    before = {p for p in tmp_path.rglob("*")}
    runner.run_real_arm(bad, "ARM_A_CONTROL", REPO, runtime_factory=lambda: object())
    assert {p for p in tmp_path.rglob("*")} == before


# --- the criterion, attacked one field at a time -----------------------------

def test_a_correct_observation_is_accepted(gate: Any) -> None:
    """A criterion that rejects everything would sweep the mutations below."""
    assert gate.probe_reasons(**gate._PASSING_PROBE) == []


@pytest.mark.parametrize("mutation", [
    {"mode": "REHEARSAL"},
    {"constructed": 0},
    {"constructed": 2},
    {"used_given_factory": False},
    {"refused_at": "<entry>"},
    {"entered": ["MANIFEST_VALIDATED"]},
    {"production_labels": ["PRE_ARM_A"]},
])
def test_each_criterion_can_fail(gate: Any, mutation: dict[str, Any]) -> None:
    observation = {**gate._PASSING_PROBE, **mutation}
    assert gate.probe_reasons(**observation), mutation


# --- the historical defect ---------------------------------------------------

#: The V6 freeze. Its runner is the tree this gate exists to reject, and it
#: stays readable from history forever -- so the control is pinned to it rather
#: than to HEAD, which would make the test skip itself the moment it passed.
V6_FREEZE_COMMIT = "356ef56cee20e2d82e5275e8316d9d3158fbd665"


def test_the_runner_at_the_v6_freeze_is_rejected_by_this_gate(
    gate: Any, tmp_path: Path,
) -> None:
    """Permanent. If this ever passes, the gate stopped measuring anything."""
    source = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{V6_FREEZE_COMMIT}:{RUNNER_REL}"],
        capture_output=True, check=False)
    assert source.returncode == 0, "the V6 runner is no longer readable from history"
    assert b"run_real_arm" not in source.stdout, (
        "the V6 runner is supposed to lack a real entry point; that is the defect")
    historical = tmp_path / "runner_at_v6.py"
    historical.write_bytes(source.stdout)
    verdict = gate.structural_reachability(_load(historical, "runner_at_v6"))
    assert verdict["REAL_MODE_STRUCTURAL_REACHABILITY"] == "FAIL"
    assert any("run_real_arm" in reason for reason in verdict["reasons"])


# --- the command line --------------------------------------------------------

def test_real_execution_is_off_by_default(runner: Any) -> None:
    """No other flag may imply it, and the default must refuse."""
    manifest = "runs/bo10/intervention/execution_manifest_v3.json"
    assert runner.main(["--manifest", manifest, "--arm", "ARM_A_CONTROL"]) == 2


def test_execution_modes_are_mutually_exclusive(runner: Any) -> None:
    """Two modes at once leaves it ambiguous which one ran."""
    manifest = "runs/bo10/intervention/execution_manifest_v3.json"
    assert runner.main([
        "--manifest", manifest, "--arm", "ARM_A_CONTROL",
        "--rehearse", "--authorise-real-execution"]) == 2


def test_scientific_overrides_are_still_refused(runner: Any) -> None:
    """The new flag must not have widened what the command line accepts."""
    from navfm.intervention_runner import RunnerRefused

    with pytest.raises(RunnerRefused):
        runner.refuse_scientific_overrides(["--seed=7"])
