"""Controls for the adapter -> collector live-application seam.

Attempt 1 of the terminal-approach intervention launched Isaac, created a valid
PRE_ARM_A, constructed the collector, and stopped at scene loading with

    unhandled AssertionError:

and an empty reason. The adapter owned a live ``IsaacApp``. The collector was
built with ``self._app.config`` -- a correct ``SimConfig`` -- and so held no
application at all. Every earlier gate passed because every earlier gate checked
configuration.

The invariant these controls encode:

    adapter has IsaacApp  +  collector has correct SimConfig
        !=
    collector has the adapter's IsaacApp

So nothing here compares configuration. Everything compares object identity,
because ``SimConfig`` is declarative and ``IsaacApp`` is the live thing, and only
one of them can open a stage.

No test in this file starts Isaac, fetches the Hospital asset, or runs an
episode. The application is a stub at the external-runtime boundary only; the
construction path under test is the production one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from navfm.arm_lifecycle import IsaacRuntimeAdapter, LifecycleRefused, Stage
from navfm.isaac.app import SimConfig
from navfm.isaac.collect import Collector, RuntimeBoundaryError

REPO = Path(__file__).resolve().parents[1]


class _StopAfterOpenStage(Exception):
    """Sentinel: reachability is the claim, not what the stage contains."""


class _FakeApp:
    """Records what the real lifecycle asks of a live application."""

    instances = 0

    def __init__(self, config: SimConfig | None = None) -> None:
        type(self).instances += 1
        self.config = config or SimConfig(hz=12.0, headless=True)
        self.opened: list[str] = []

    def open_stage(self, scene_usd: str) -> None:
        self.opened.append(scene_usd)
        raise _StopAfterOpenStage(scene_usd)


@pytest.fixture(autouse=True)
def _reset_instance_count() -> None:
    _FakeApp.instances = 0


def _collect_config() -> Any:
    from navfm.isaac.collect import CollectConfig

    return CollectConfig(scenes=["omniverse://example/hospital.usd"], episodes=1)


def _adapter_with(app: Any) -> IsaacRuntimeAdapter:
    """An adapter holding a live application, as initialise() would leave it."""
    adapter = IsaacRuntimeAdapter()
    adapter._app = app
    return adapter


# --- the seam ----------------------------------------------------------------

def test_the_adapter_hands_the_collector_its_own_application(tmp_path: Path) -> None:
    """Identity, not equality. Same config is the thing that was already true."""
    app = _FakeApp()
    adapter = _adapter_with(app)
    adapter.build_collector(tmp_path / "trajectory", _collect_config(), "PATH_VERTEX")

    assert adapter._collector._app is app
    assert _FakeApp.instances == 1


def test_the_collector_keeps_the_frozen_sim_configuration(tmp_path: Path) -> None:
    """The repair must not have traded configuration away for the app."""
    app = _FakeApp(SimConfig(hz=12.0, headless=True))
    adapter = _adapter_with(app)
    adapter.build_collector(tmp_path / "trajectory", _collect_config(), "PATH_VERTEX")

    assert adapter._collector.sim == app.config


def test_the_adapter_reports_the_binding_it_made(tmp_path: Path) -> None:
    app = _FakeApp()
    adapter = _adapter_with(app)
    result = adapter.build_collector(
        tmp_path / "trajectory", _collect_config(), "PATH_VERTEX")
    assert result["isaac_app_bound"] is True


def test_exactly_one_application_exists_per_arm(tmp_path: Path) -> None:
    """Two live simulators and the evidence cannot say which one was stepped."""
    app = _FakeApp()
    adapter = _adapter_with(app)
    adapter.build_collector(tmp_path / "trajectory", _collect_config(), "PATH_VERTEX")

    assert _FakeApp.instances == 1
    with pytest.raises(RuntimeBoundaryError) as excinfo:
        adapter._collector.run(["scene.usd"], 1)
    assert excinfo.value.category == "ISAAC_APP_SINGLE_OWNER_VIOLATION"


# --- the defect that produced Attempt 1 --------------------------------------

def test_a_collector_given_only_configuration_is_refused(tmp_path: Path) -> None:
    """Mandatory control: this is Attempt 1, reproduced exactly.

    It must fail, and it must fail with a named category before any stage is
    opened. If this ever passes, the seam test has stopped measuring the thing
    that cost an authorisation.
    """
    app = _FakeApp()
    config_only = Collector(
        tmp_path / "trajectory", _collect_config(), app.config)  # no isaac_app

    assert config_only.sim == app.config, "the configuration really is correct"
    assert config_only._app is None, "and there is still no application"

    with pytest.raises(RuntimeBoundaryError) as excinfo:
        config_only.open_scene("omniverse://example/hospital.usd")
    assert excinfo.value.category == "ISAAC_APP_NOT_BOUND_TO_COLLECTOR"
    assert app.opened == [], "no stage may be opened on the adapter's app either"


def test_the_refusal_is_not_a_bare_assertion(tmp_path: Path) -> None:
    """Attempt 1 recorded 'unhandled AssertionError:' with an empty reason."""
    collector = Collector(tmp_path / "trajectory", _collect_config(), SimConfig())
    with pytest.raises(RuntimeBoundaryError) as excinfo:
        collector.open_scene("scene.usd")
    assert not isinstance(excinfo.value, AssertionError)
    assert excinfo.value.category
    assert excinfo.value.detail.strip(), "a reason that is empty diagnoses nothing"
    assert len(str(excinfo.value)) > 40


def test_a_wrong_application_is_visible_as_a_mismatch(tmp_path: Path) -> None:
    """Adapter owns A, collector holds B: duplicate ownership, not a repair."""
    owned = _FakeApp()
    other = _FakeApp()
    adapter = _adapter_with(owned)
    adapter._collector = Collector(
        tmp_path / "trajectory", _collect_config(), owned.config, isaac_app=other)

    assert adapter._collector._app is not adapter._app
    assert _FakeApp.instances == 2, "two applications is the defect being detected"


def test_the_adapter_refuses_to_build_a_collector_with_no_runtime(
    tmp_path: Path,
) -> None:
    """Structured refusal, named stage -- not an attribute error three stages on."""
    adapter = IsaacRuntimeAdapter()
    with pytest.raises(LifecycleRefused) as excinfo:
        adapter.build_collector(
            tmp_path / "trajectory", _collect_config(), "PATH_VERTEX")
    assert excinfo.value.stage == Stage.COLLECTOR_READY.value
    assert str(excinfo.value.reason).strip()


# --- scene-load reachability -------------------------------------------------

def test_after_the_repair_the_lifecycle_reaches_open_stage(tmp_path: Path) -> None:
    """The call Attempt 1 never made, proven without fetching the asset."""
    app = _FakeApp()
    adapter = _adapter_with(app)
    adapter.build_collector(tmp_path / "trajectory", _collect_config(), "PATH_VERTEX")

    scene = "omniverse://example/hospital.usd"
    with pytest.raises(_StopAfterOpenStage):
        adapter.load_scene(scene, "hospital")

    assert app.opened == [scene], "exactly one stage open, with the frozen identifier"
    assert adapter.stages.get("HOSPITAL_SCENE_REQUESTED") is True
    assert adapter.stages.get("HOSPITAL_SCENE_LOADED") is not True


def test_open_stage_is_not_reached_without_a_bound_application(
    tmp_path: Path,
) -> None:
    """Order control: the application is validated before a stage is opened."""
    app = _FakeApp()
    adapter = _adapter_with(app)
    adapter._collector = Collector(
        tmp_path / "trajectory", _collect_config(), app.config)  # config only

    with pytest.raises(RuntimeBoundaryError):
        adapter.load_scene("omniverse://example/hospital.usd", "hospital")
    assert app.opened == []


def test_the_adapter_refuses_a_scene_before_a_collector_exists() -> None:
    """The stage order is collector, then scene -- never the reverse."""
    adapter = _adapter_with(_FakeApp())
    with pytest.raises(LifecycleRefused) as excinfo:
        adapter.load_scene("scene.usd", "hospital")
    assert excinfo.value.stage == Stage.SCENE_READY.value
