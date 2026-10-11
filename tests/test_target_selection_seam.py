"""Controls for the target-selection injection seam.

Two properties matter here and they pull in opposite directions.

The seam must be **invisible**: an existing caller that never heard of it must
get exactly the frozen behaviour, or every unrelated code path in the repository
silently changed the day the hook landed.

The seam must also be **narrow**: an injected selector must be able to change
what the tracker steers at and nothing else. That is checked structurally, by
asking what the selector is actually handed, rather than by trusting a docstring
that says it behaves.
"""

from __future__ import annotations

import inspect
import math
from typing import Any

import numpy as np
import pytest

from navfm.control import M3PRO_LIMITS, DemonstratorMode, PurePursuit
from navfm.target_selection import (
    LegacyVertexTargetSelector,
    TargetSelection,
    TargetSelector,
)

PATH = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [2.0, 1.0], [2.0, 2.0]])
CONFIG: dict[str, Any] = {
    "lookahead": 0.45,
    "goal_tol": 0.20,
    "limits": M3PRO_LIMITS,
    "mode": DemonstratorMode.NONHOLONOMIC,
    "cruise_v": 0.35,
}


def _tracker(**kwargs: Any) -> PurePursuit:
    return PurePursuit(PATH.copy(), **CONFIG, **kwargs)


# --------------------------------------------------------------------------
# the seam is invisible by default
# --------------------------------------------------------------------------


def test_default_construction_uses_the_legacy_selector() -> None:
    assert isinstance(_tracker()._selector, LegacyVertexTargetSelector)


def test_existing_callers_need_not_know_the_seam_exists() -> None:
    """The signature gained a keyword with a default; nothing became required."""
    signature = inspect.signature(PurePursuit.__init__)
    parameter = signature.parameters["target_selector"]
    assert parameter.default is None
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    required = [
        name for name, p in signature.parameters.items()
        if name != "self" and p.default is inspect.Parameter.empty
    ]
    assert required == ["path"]


def test_default_and_explicit_legacy_agree_step_for_step() -> None:
    default = _tracker()
    injected = _tracker(target_selector=LegacyVertexTargetSelector())
    for x in np.linspace(0.0, 2.0, 40):
        position = np.array([x, 0.0])
        assert default.target(position).tolist() == injected.target(position).tolist()
        assert default._idx == injected._idx
        assert default.finished == injected.finished


# --------------------------------------------------------------------------
# the legacy selector is a transcription, not a tidy-up
# --------------------------------------------------------------------------


def test_advance_condition_is_strictly_less_than() -> None:
    """A pose exactly one look-ahead from the current vertex must NOT advance.
    Relaxing this to <= would be a silent behaviour change at the boundary."""
    selector = LegacyVertexTargetSelector()
    exactly = np.array([0.0 - 0.45, 0.0])
    assert selector.select_target(PATH, exactly, 0, 0.45).next_index == 0
    inside = np.array([0.0 - 0.45 + 1e-9, 0.0])
    assert selector.select_target(PATH, inside, 0, 0.45).next_index == 1


def test_it_advances_one_vertex_at_a_time_not_to_the_furthest_qualifying() -> None:
    """Legacy stops at the first vertex that is not within the look-ahead. It
    does not search forward. Preserved because Arm A is the frozen behaviour."""
    selector = LegacyVertexTargetSelector()
    dense = np.array([[0.0, 0.0], [0.1, 0.0], [0.2, 0.0], [5.0, 0.0]])
    selection = selector.select_target(dense, np.array([0.0, 0.0]), 0, 0.45)
    assert selection.next_index == 3
    far = selector.select_target(dense, np.array([0.0, 0.0]), 2, 0.45)
    assert far.next_index == 3


def test_index_never_exceeds_the_final_vertex() -> None:
    selector = LegacyVertexTargetSelector()
    selection = selector.select_target(PATH, np.array([2.0, 2.0]), 4, 0.45)
    assert selection.next_index == 4
    assert selection.point.tolist() == [2.0, 2.0]


def test_index_is_monotone_and_never_rewinds() -> None:
    tracker = _tracker()
    seen = [tracker._idx]
    for x in np.linspace(2.0, 0.0, 30):
        tracker.target(np.array([x, 0.0]))
        seen.append(tracker._idx)
    assert seen == sorted(seen)


def test_returned_point_is_a_view_into_the_path_as_before() -> None:
    """The pre-seam implementation returned a view. Copying would be tidier and
    would also be a behaviour change, so it is not done."""
    selection = LegacyVertexTargetSelector().select_target(PATH, np.array([0.0, 0.0]), 1, 0.45)
    assert selection.point.base is PATH or np.shares_memory(selection.point, PATH)


def test_target_type_is_recorded_for_evidence() -> None:
    assert LegacyVertexTargetSelector.target_type == "PATH_VERTEX"


def test_legacy_selector_satisfies_the_protocol() -> None:
    assert isinstance(LegacyVertexTargetSelector(), TargetSelector)


# --------------------------------------------------------------------------
# the seam is narrow
# --------------------------------------------------------------------------


def test_selector_is_never_handed_the_tracker() -> None:
    """Structural, not aspirational: a selector given the tracker could reach
    the speed law, the limits, the goal predicate and dt. It is not given it."""
    parameters = [
        p for p in inspect.signature(LegacyVertexTargetSelector.select_target).parameters
        if p != "self"
    ]
    assert parameters == ["path", "position", "index", "lookahead"]
    for forbidden in ("tracker", "limits", "cruise_v", "mode", "goal_tol", "dt", "max_steps"):
        assert forbidden not in parameters


def test_behavioural_surface_is_exactly_one_method() -> None:
    behavioural = [
        name for name in dir(LegacyVertexTargetSelector)
        if not name.startswith("_") and callable(getattr(LegacyVertexTargetSelector, name))
    ]
    assert behavioural == ["select_target"]


def test_an_injected_selector_cannot_change_the_speed_law() -> None:
    """A selector that returns the same target produces the same command, no
    matter what else it tries to be."""

    class Meddler:
        target_type = "MEDDLER"

        def __init__(self) -> None:
            self.cruise_v = 99.0
            self.max_w = 99.0

        def select_target(
            self, path: np.ndarray, position: np.ndarray, index: int, lookahead: float
        ) -> TargetSelection:
            return LegacyVertexTargetSelector().select_target(path, position, index, lookahead)

    baseline = _tracker()
    meddled = _tracker(target_selector=Meddler())
    for x in np.linspace(0.0, 2.0, 25):
        position, yaw = np.array([x, 0.0]), 0.3
        assert baseline.step(position, yaw) == meddled.step(position, yaw)


def test_the_seam_does_not_disturb_the_existing_treatment_subclass() -> None:
    """InterpolatedLookaheadPursuit advances the inherited index through
    super().target(); rerouting that through the seam must not change it."""
    from navfm.collection.interpolated_target import InterpolatedLookaheadPursuit

    treatment = InterpolatedLookaheadPursuit(PATH.copy(), **CONFIG)
    legacy = _tracker()
    for x in np.linspace(0.0, 2.0, 25):
        position = np.array([x, 0.0])
        treatment.target(position)
        legacy.target(position)
        assert treatment._idx == legacy._idx, "index advancement must match the control arm"


def test_override_surface_still_reports_target_only() -> None:
    """The intervention contract's audit must still see one behavioural
    override after the seam exists."""
    from navfm.collection.interpolated_target import InterpolatedLookaheadPursuit

    base = {n for n in dir(PurePursuit) if not n.startswith("__")}
    overridden = sorted(n for n in base if n in InterpolatedLookaheadPursuit.__dict__)
    behavioural = [n for n in overridden if n not in {"target_type"}]
    assert behavioural == ["target"]


# --------------------------------------------------------------------------
# the tracker still behaves
# --------------------------------------------------------------------------


def test_goal_predicate_and_stop_branch_are_untouched() -> None:
    tracker = _tracker()
    assert tracker.step(np.array([2.0, 1.95]), 0.0) == (0.0, 0.0, 0.0, True)


def test_in_place_turn_regime_still_triggers_beyond_75_degrees() -> None:
    tracker = _tracker()
    _vx, _vy, wz, _done = tracker.step(np.array([0.0, 0.0]), math.radians(180.0))
    assert abs(wz) == pytest.approx(M3PRO_LIMITS.max_w)


def test_path_shorter_than_two_waypoints_still_refused() -> None:
    with pytest.raises(ValueError, match="at least two waypoints"):
        PurePursuit(np.array([[0.0, 0.0]]), **CONFIG)
