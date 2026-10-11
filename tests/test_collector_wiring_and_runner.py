"""Controls for collector selector wiring and the manifest-driven runner.

Two failure modes are worth more attention than the happy path.

An arm could receive the wrong selector while still being labelled correctly --
the one error a one-factor experiment cannot survive, because the result would
look like a null rather than like a bug. So a declaration must reach exactly the
selector it names, an unknown name is refused rather than defaulted, and absence
can never become the treatment.

A runner could accept a scientific value on the command line. An experiment
whose configuration can be typed at run time can be retyped after a result is
seen, so every scientific flag is refused by name.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from navfm.control import M3PRO_LIMITS, DemonstratorMode, PurePursuit
from navfm.execution_manifest import ARM_ORDER, SELECTOR_ASSIGNMENT
from navfm.intervention_runner import (
    PRODUCER_MAP,
    SCIENTIFIC_FIELDS_NEVER_OVERRIDABLE,
    RunnerRefused,
    build_collect_config,
    executability,
    producer_coverage,
    resolve_arm,
    runner_resolution,
    validate_only,
)
from navfm.isaac.collect import CollectConfig
from navfm.target_selection import (
    SELECTOR_REGISTRY,
    ArcLengthInterpolatedTargetSelector,
    LegacyVertexTargetSelector,
    SelectorResolutionRefused,
    resolve_target_selector,
)

REPO = Path(__file__).resolve().parents[1]
MANIFEST_V1 = Path(os.environ.get("NAVFM_ARCHIVE_ROOT", str(REPO))) / "runs/bo10/intervention/execution_manifest.json"

_SPEC = importlib.util.spec_from_file_location(
    "run_intervention", REPO / "scripts" / "run_terminal_approach_intervention.py")
assert _SPEC and _SPEC.loader
cli = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cli)


def _head() -> str:
    import subprocess

    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def manifest() -> dict[str, Any]:
    """A V2 manifest built for the current tree.

    Built rather than read: the frozen runtime manifest lives in the ignored
    evidence tree and is not present in a fresh checkout, and a test that needs
    it would pass or fail on whether someone had run the freeze.
    """
    from navfm.execution_manifest_v2 import build_manifest_v2

    return build_manifest_v2(
        REPO, head=_head(), frozen_at_utc="2026-09-12T00:00:00+00:00",
        manifest_path="runs/bo10/intervention/execution_manifest_v2.json")


@pytest.fixture
def manifest_file(tmp_path: Path, manifest: dict[str, Any]) -> Path:
    target = tmp_path / "execution_manifest_v2.json"
    target.write_text(json.dumps(manifest, indent=2))
    return target


# --------------------------------------------------------------------------
# selector wiring
# --------------------------------------------------------------------------


def test_the_collector_accepts_a_selector_declaration() -> None:
    assert "target_selector" in {f.name for f in __import__(
        "dataclasses").fields(CollectConfig)}
    assert CollectConfig().target_selector is None


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [("PATH_VERTEX", LegacyVertexTargetSelector),
     ("ARC_LENGTH_INTERPOLATED", ArcLengthInterpolatedTargetSelector)],
)
def test_a_declaration_reaches_the_selector_it_names(
    declaration: str, expected: type
) -> None:
    assert isinstance(resolve_target_selector(declaration), expected)


def test_absence_is_the_control_and_never_the_treatment() -> None:
    """Absence must be the frozen legacy behaviour. If it ever became the
    treatment, every pre-existing collection caller would silently change arm."""
    selector = resolve_target_selector(None)
    assert isinstance(selector, LegacyVertexTargetSelector)
    assert not isinstance(selector, ArcLengthInterpolatedTargetSelector)


def test_an_unknown_declaration_is_refused_not_defaulted() -> None:
    with pytest.raises(SelectorResolutionRefused, match="unknown target selector"):
        resolve_target_selector("ARC_LENGTH_INTERPOLATD")


def test_the_registry_is_keyed_by_target_type() -> None:
    assert set(SELECTOR_REGISTRY) == {"PATH_VERTEX", "ARC_LENGTH_INTERPOLATED"}
    for identity, cls in SELECTOR_REGISTRY.items():
        assert cls.target_type == identity


def test_the_wired_construction_preserves_legacy_arm_a() -> None:
    route = np.array([[0.0, 0.0], [3.0, 0.0], [3.0, 4.0]])
    config: dict[str, Any] = {
        "lookahead": 0.45, "goal_tol": 0.20, "limits": M3PRO_LIMITS,
        "mode": DemonstratorMode.NONHOLONOMIC, "cruise_v": 0.35}
    wired = PurePursuit(route.copy(), **config,
                        target_selector=resolve_target_selector("PATH_VERTEX"))
    default = PurePursuit(route.copy(), **config)
    for x in np.linspace(0.0, 3.0, 40):
        position = np.array([x, 0.1])
        assert wired.target(position).tolist() == default.target(position).tolist()
        assert wired._idx == default._idx


# --------------------------------------------------------------------------
# arm resolution
# --------------------------------------------------------------------------


@pytest.mark.parametrize("arm", ARM_ORDER)
def test_each_arm_resolves_to_its_frozen_selector(
    manifest: dict[str, Any], arm: str
) -> None:
    resolution = resolve_arm(manifest, arm)
    assert resolution.selector_class == SELECTOR_ASSIGNMENT[arm]["selector_class"]
    assert resolution.selector_identity == SELECTOR_ASSIGNMENT[arm]["target_type"]


def test_arms_share_every_scientific_value(manifest: dict[str, Any]) -> None:
    a = resolve_arm(manifest, "ARM_A_CONTROL")
    b = resolve_arm(manifest, "ARM_B_TREATMENT")
    assert a.route == b.route
    assert a.seed == b.seed
    assert a.initial_pose_xy_yaw == b.initial_pose_xy_yaw
    assert a.goal_xy == b.goal_xy
    assert a.scene_asset == b.scene_asset
    assert a.runtime == b.runtime
    assert a.selector_identity != b.selector_identity


def test_the_collect_config_differs_only_in_the_selector(
    manifest: dict[str, Any],
) -> None:
    import dataclasses

    a = dataclasses.asdict(build_collect_config(resolve_arm(manifest, "ARM_A_CONTROL")))
    b = dataclasses.asdict(build_collect_config(resolve_arm(manifest, "ARM_B_TREATMENT")))
    differing = [k for k in a if a[k] != b[k]]
    assert differing == ["target_selector"]


def test_an_unknown_arm_is_refused(manifest: dict[str, Any]) -> None:
    with pytest.raises(RunnerRefused, match="unknown arm"):
        resolve_arm(manifest, "ARM_C")


def test_a_missing_selector_declaration_is_refused(manifest: dict[str, Any]) -> None:
    import copy

    broken = copy.deepcopy(manifest)
    broken["arms"]["selectors"]["ARM_A_CONTROL"] = {}
    with pytest.raises(RunnerRefused, match="no selector"):
        resolve_arm(broken, "ARM_A_CONTROL")


def test_a_swapped_selector_class_is_refused(manifest: dict[str, Any]) -> None:
    import copy

    swapped = copy.deepcopy(manifest)
    swapped["arms"]["selectors"]["ARM_A_CONTROL"]["selector_class"] = (
        "navfm.target_selection.ArcLengthInterpolatedTargetSelector")
    with pytest.raises(RunnerRefused, match="frozen assignment"):
        resolve_arm(swapped, "ARM_A_CONTROL")


def test_an_unimplemented_selector_identity_is_refused(manifest: dict[str, Any]) -> None:
    import copy

    broken = copy.deepcopy(manifest)
    broken["arms"]["selectors"]["ARM_B_TREATMENT"]["target_type"] = "SOMETHING_NEW"
    with pytest.raises(RunnerRefused, match="does not implement"):
        resolve_arm(broken, "ARM_B_TREATMENT")


# --------------------------------------------------------------------------
# runner resolution and executability
# --------------------------------------------------------------------------


def test_the_runner_resolves() -> None:
    result = runner_resolution(REPO)
    assert result["RUNNER_RESOLUTION"] == "PASS"
    assert result["runner_path_exists"] and result["runner_parses"]
    assert result["collector_resolves"]
    assert result["collector_accepts_selector_declaration"]
    assert all(result["selectors_resolve"].values())


def test_a_missing_runner_is_detected(tmp_path: Path) -> None:
    """A manifest naming a nonexistent runner must be rejected."""
    result = runner_resolution(tmp_path)
    assert result["RUNNER_RESOLUTION"] == "FAIL"
    assert result["runner_path_exists"] is False


def test_executability_passes_and_states_its_boundary(manifest: dict[str, Any]) -> None:
    result = executability(manifest, REPO)
    assert result["EXECUTABILITY"] == "PASS"
    for fact in ("runner_resolved", "collector_resolved", "selector_wiring_present",
                 "selectors_resolved", "arm_a_dispatch_valid", "arm_b_dispatch_valid",
                 "required_output_producers_complete"):
        assert result[fact] is True
    assert "do NOT claim that Isaac will launch" in result["claim_boundary"]


# --------------------------------------------------------------------------
# producer coverage -- the gap Manifest V1 shipped with
# --------------------------------------------------------------------------


def test_every_declared_output_has_a_producer(manifest: dict[str, Any]) -> None:
    coverage = producer_coverage(manifest)
    assert coverage["OUTPUT_PRODUCER_COVERAGE"] == "PASS"
    assert coverage["outputs_without_a_producer"] == []
    assert coverage["producers_for_undeclared_outputs"] == []
    assert coverage["declared_outputs"] == coverage["mapped_outputs"] == len(PRODUCER_MAP)


def test_a_declared_output_with_no_producer_fails(manifest: dict[str, Any]) -> None:
    """The exact V1 defect, reproduced deliberately."""
    import copy

    broken = copy.deepcopy(manifest)
    broken["output_allowlist"]["tracked"].append(
        "gates/BO10/intervention/nobody_writes_this.json")
    coverage = producer_coverage(broken)
    assert coverage["OUTPUT_PRODUCER_COVERAGE"] == "FAIL"
    assert "gates/BO10/intervention/nobody_writes_this.json" in coverage[
        "outputs_without_a_producer"]


def test_a_producer_for_an_undeclared_output_fails(manifest: dict[str, Any]) -> None:
    import copy

    broken = copy.deepcopy(manifest)
    broken["output_allowlist"]["tracked"] = broken["output_allowlist"]["tracked"][:-1]
    coverage = producer_coverage(broken)
    assert coverage["OUTPUT_PRODUCER_COVERAGE"] == "FAIL"
    assert coverage["producers_for_undeclared_outputs"]


def test_an_unresolvable_producer_fails(
    manifest: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import navfm.intervention_runner as runner

    broken_map = dict(PRODUCER_MAP)
    broken_map["gates/BO10/intervention/comparison.json"] = (
        "INTERVENTION_COMPARISON", "navfm.nonexistent_module:write", True)
    monkeypatch.setattr(runner, "PRODUCER_MAP", broken_map)
    coverage = runner.producer_coverage(manifest)
    assert coverage["OUTPUT_PRODUCER_COVERAGE"] == "FAIL"
    assert "gates/BO10/intervention/comparison.json" in coverage[
        "outputs_without_a_producer"]


def test_every_producer_resolves_to_a_callable(manifest: dict[str, Any]) -> None:
    for row in producer_coverage(manifest)["rows"]:
        assert row["resolved"] is True, f"{row['output']}: {row['detail']}"


# --------------------------------------------------------------------------
# validate-only
# --------------------------------------------------------------------------


@pytest.mark.parametrize("arm", ARM_ORDER)
def test_validate_only_passes_without_launching_anything(
    arm: str, manifest_file: Path
) -> None:
    report = validate_only(manifest_file, arm, REPO)
    assert report["VALIDATE_ONLY"] == "PASS"
    assert report["isaac_launched"] is False
    assert report["production_capture_created"] is False
    assert report["scientific_artefact_written"] is False


def test_validate_only_refuses_an_unknown_arm(manifest_file: Path) -> None:
    report = validate_only(manifest_file, "ARM_C", REPO)
    assert report["VALIDATE_ONLY"] == "REFUSED"
    assert "unknown arm" in report["reason"]


@pytest.mark.archive
def test_manifest_v1_is_now_stale_and_refused() -> None:
    """V1 bound an earlier HEAD. It must refuse rather than run against a tree
    it never described -- which is exactly what stopped the first Arm-A
    authorisation, and must keep working."""
    assert MANIFEST_V1.is_file(), "required immutable V1 archive is absent"
    report = validate_only(MANIFEST_V1, "ARM_A_CONTROL", REPO)
    assert report["VALIDATE_ONLY"] == "REFUSED"
    assert "did not validate" in report["reason"]


def test_validate_only_refuses_a_missing_manifest(tmp_path: Path) -> None:
    report = validate_only(tmp_path / "nope.json", "ARM_A_CONTROL", REPO)
    assert report["VALIDATE_ONLY"] == "REFUSED"


def test_validate_only_refuses_a_stale_manifest(
    tmp_path: Path, manifest: dict[str, Any]
) -> None:
    stale = json.loads(json.dumps(manifest))
    stale["repository"]["head"] = "0" * 40
    target = tmp_path / "stale.json"
    target.write_text(json.dumps(stale))
    report = validate_only(target, "ARM_A_CONTROL", REPO)
    assert report["VALIDATE_ONLY"] == "REFUSED"
    assert "did not validate" in report["reason"]


def test_validate_only_refuses_an_unparseable_manifest(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    target.write_text("{not json")
    assert validate_only(target, "ARM_A_CONTROL", REPO)["VALIDATE_ONLY"] == "REFUSED"


# --------------------------------------------------------------------------
# the CLI refuses scientific overrides
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flag",
    ["--selector", "--target-selector", "--route", "--seed", "--lookahead",
     "--max-steps", "--gains", "--cruise-v", "--goal-tol", "--scene",
     "--initial-pose", "--goal", "--control-dt", "--demonstrator"],
)
def test_a_scientific_override_is_refused_by_name(flag: str) -> None:
    with pytest.raises(RunnerRefused, match="frozen manifest"):
        cli.refuse_scientific_overrides(
            ["--manifest", "m.json", "--arm", "ARM_A_CONTROL", flag, "x"])


def test_operational_arguments_are_permitted() -> None:
    cli.refuse_scientific_overrides(
        ["--manifest", "m.json", "--arm", "ARM_A_CONTROL", "--validate-only"])


def test_every_scientific_field_is_covered_by_the_refusal_list() -> None:
    for field in ("selector", "route", "seed", "max_steps", "scene", "goal"):
        assert field in SCIENTIFIC_FIELDS_NEVER_OVERRIDABLE


def test_the_cli_refuses_an_override_before_parsing(
    manifest_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["--manifest", str(manifest_file), "--arm", "ARM_A_CONTROL",
                     "--seed", "7", "--validate-only"])
    assert code == 2
    assert "REFUSED" in capsys.readouterr().out


def test_the_cli_refuses_execution_without_validate_only(
    manifest_file: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Execution is not the default. It requires explicit authorisation."""
    code = cli.main(["--manifest", str(manifest_file), "--arm", "ARM_A_CONTROL"])
    assert code == 2
    assert "requires explicit authorisation" in capsys.readouterr().out


@pytest.mark.parametrize("arm", ARM_ORDER)
def test_the_cli_validate_only_succeeds(
    arm: str, manifest_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["--manifest", str(manifest_file), "--arm", arm, "--validate-only"])
    assert code == 0
    assert "VALIDATE_ONLY       PASS" in capsys.readouterr().out


def test_the_cli_rejects_an_unknown_arm_choice(manifest_file: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--manifest", str(manifest_file), "--arm", "ARM_C", "--validate-only"])


# --------------------------------------------------------------------------
# manifest version dispatch
#
# A manifest checked by an older validator fails on its version field alone,
# which reports a newer and stricter manifest as invalid. That happened to V2
# once and was fixed with a branch; the branch then did the same thing to V3,
# because "everything else" still meant the V1 validator. The dispatch is a
# table so that an unmapped version is refused by name instead of quietly
# falling through to the oldest checker in the chain.
# --------------------------------------------------------------------------


def test_every_shipped_manifest_version_has_a_validator() -> None:
    from navfm.execution_manifest import MANIFEST_VERSION
    from navfm.execution_manifest_v2 import MANIFEST_V2_VERSION, MANIFEST_V3_VERSION
    from navfm.intervention_runner import _MANIFEST_VALIDATORS

    for version in (MANIFEST_VERSION, MANIFEST_V2_VERSION, MANIFEST_V3_VERSION):
        assert version in _MANIFEST_VALIDATORS, version


def test_each_version_dispatches_to_a_distinct_validator() -> None:
    """A table that mapped everything to one validator would pass the test
    above and reintroduce the defect it exists to prevent."""
    from navfm.intervention_runner import _MANIFEST_VALIDATORS

    resolved = {name: factory() for name, factory in _MANIFEST_VALIDATORS.items()}
    assert len(set(resolved.values())) == len(resolved), resolved


def test_an_unmapped_manifest_version_is_refused_by_name(tmp_path: Path) -> None:
    """Negative control. Falling back to the V1 validator is the failure mode."""
    from navfm.intervention_runner import validate_only

    target = tmp_path / "future.json"
    target.write_text(json.dumps({"manifest_version": "EXECUTION_MANIFEST_V9"}))
    outcome = validate_only(target, "ARM_A_CONTROL", Path(__file__).resolve().parents[1])
    assert outcome["VALIDATE_ONLY"] == "REFUSED"
    assert "EXECUTION_MANIFEST_V9" in outcome["reason"]
    assert "known_versions" in outcome
