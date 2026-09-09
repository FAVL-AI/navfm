"""G8, G9, G10 — controller identity, goal seal, and long-horizon adequacy.

G10's boundary tests are the load-bearing part: a threshold that rounds a
failing value into a pass is worse than no threshold, because it produces a
dataset that documents a standard it does not meet.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from navfm.collection.controller import (
    ControllerIdentity,
    evaluate_controller_identity,
    verify_motion_occurred,
)
from navfm.collection.gates import GateKind, GateStatus
from navfm.collection.goal_seal import (
    GoalSeal,
    GoalSealError,
    evaluate_goal_seal,
    image_digest,
)
from navfm.collection.long_horizon import (
    LONG_HORIZON_THRESHOLDS,
    measure_from_trajectory,
    predict_from_route,
    window_counts,
)

CONTROL_HZ = 12.0
CRUISE_V = 0.35


def identity(**overrides: object) -> ControllerIdentity:
    base = dict(
        implementation="navfm.control.PurePursuit",
        control_hz=12.0, max_v=0.45, max_w=1.2, max_vy=0.35,
        max_a=0.8, max_alpha=3.0, cruise_v=0.35, lookahead_m=0.45,
        goal_tol_m=0.20, demonstrator_mode="nonholonomic", seed=0,
    )
    base.update(overrides)
    return ControllerIdentity(**base)  # type: ignore[arg-type]


def route_with_turns(leg_m: float = 4.0, legs: int = 4) -> np.ndarray:
    """A staircase: each corner is a 90 degree qualifying heading change."""
    pts = [(0.0, 0.0)]
    x = y = 0.0
    for i in range(legs):
        if i % 2 == 0:
            x += leg_m
        else:
            y += leg_m
        pts.append((x, y))
    return np.array(pts)


# ------------------------------------------------------------------- G8 ----
class TestG8ControllerIdentity:
    def test_an_unchanged_controller_passes(self) -> None:
        r = evaluate_controller_identity(identity(), identity())
        assert r.status is GateStatus.PASS
        assert r.kind is GateKind.POSTCONDITION

    def test_a_modified_velocity_parameter_fails(self) -> None:
        r = evaluate_controller_identity(identity(), identity(max_v=0.50))
        assert r.status is GateStatus.FAIL
        assert "max_v" in r.detail["changed_fields"]

    def test_a_changed_implementation_fails(self) -> None:
        r = evaluate_controller_identity(identity(), identity(implementation="other.Controller"))
        assert r.status is GateStatus.FAIL

    def test_a_changed_acceleration_limit_fails(self) -> None:
        r = evaluate_controller_identity(identity(), identity(max_alpha=2.0))
        assert r.status is GateStatus.FAIL

    def test_a_changed_seed_fails(self) -> None:
        r = evaluate_controller_identity(identity(), identity(seed=1))
        assert r.status is GateStatus.FAIL

    def test_an_infinite_limit_is_digested_not_dropped(self) -> None:
        """A digest ignoring an unbounded limit would not notice it being bounded."""
        unbounded = identity(max_a=math.inf)
        bounded = identity(max_a=0.8)
        assert unbounded.digest != bounded.digest
        assert evaluate_controller_identity(unbounded, bounded).status is GateStatus.FAIL

    def test_the_digest_is_stable_across_equal_identities(self) -> None:
        assert identity().digest == identity().digest

    def test_g8_does_not_claim_the_robot_moved(self) -> None:
        """The FL-013 genus: a command issued is not a base that moved."""
        r = evaluate_controller_identity(identity(), identity())
        assert r.status is GateStatus.PASS
        assert "does not establish that the robot moved" in r.detail["claim_boundary"]

        stationary = np.zeros((200, 2))
        motion = verify_motion_occurred(stationary, np.zeros(200))
        assert motion.status is GateStatus.FAIL, (
            "a wedged base must fail the motion postcondition even though G8 passed"
        )

    def test_realised_motion_passes_when_the_base_moved(self) -> None:
        pos = np.column_stack([np.linspace(0.0, 3.0, 100), np.zeros(100)])
        assert verify_motion_occurred(pos, np.zeros(100)).status is GateStatus.PASS

    def test_motion_from_an_unusable_pose_series_is_inconclusive(self) -> None:
        r = verify_motion_occurred(np.zeros((1, 2)), np.zeros(1))
        assert r.status is GateStatus.INCONCLUSIVE
        assert not r.admits


# ------------------------------------------------------------------- G9 ----
class TestG9GoalImageSeal:
    def make(self, image: bytes = b"goal-frame") -> GoalSeal:
        seal = GoalSeal(goal_xy=(3.0, 4.0), source_camera="/World/Robot/front_rgb")
        seal.declare()
        seal.acquire(image, sim_time=1.5)
        seal.write_provenance()
        seal.seal()
        return seal

    def test_a_pre_motion_goal_passes(self) -> None:
        seal = self.make()
        seal.note_first_motion()
        r = evaluate_goal_seal(seal)
        assert r.status is GateStatus.PASS
        assert r.kind is GateKind.PRECONDITION
        assert r.detail["goal_image_sha256"] == image_digest(b"goal-frame")

    def test_motion_before_the_seal_is_refused_at_the_call_site(self) -> None:
        """Refused when it happens, not diagnosed afterwards."""
        seal = GoalSeal(goal_xy=(1.0, 1.0), source_camera="/cam")
        seal.declare()
        seal.acquire(b"frame")
        with pytest.raises(GoalSealError, match="before the goal was sealed"):
            seal.note_first_motion()

    def test_a_goal_captured_after_first_motion_fails(self) -> None:
        """Reconstructed out-of-order sequence: the gate must reject it."""
        seal = GoalSeal(goal_xy=(1.0, 1.0), source_camera="/cam")
        seal.declare()
        seal.acquire(b"frame")
        seal.write_provenance()
        seal.seal()
        # Splice motion in ahead of the acquisition, as a buggy collector would.
        seal.events.insert(1, ("FIRST_MOTION_COMMAND", 0))
        r = evaluate_goal_seal(seal)
        assert r.status is GateStatus.FAIL
        assert "required order" in r.reason

    def test_reusing_the_final_observation_as_the_goal_fails(self) -> None:
        seal = self.make(image=b"last-frame")
        seal.note_first_motion()
        r = evaluate_goal_seal(seal, final_observation_digest=image_digest(b"last-frame"))
        assert r.status is GateStatus.FAIL
        assert "final observation" in r.reason

    def test_a_goal_hash_changed_after_sealing_fails(self) -> None:
        seal = self.make()
        seal.note_first_motion()
        r = evaluate_goal_seal(seal, current_goal_digest=image_digest(b"different"))
        assert r.status is GateStatus.FAIL
        assert "changed after it was sealed" in r.reason

    def test_an_incomplete_chronology_fails(self) -> None:
        seal = self.make()  # never noted first motion
        r = evaluate_goal_seal(seal)
        assert r.status is GateStatus.FAIL
        assert "incomplete" in r.reason

    def test_acquiring_before_declaring_is_refused(self) -> None:
        seal = GoalSeal(goal_xy=(0.0, 0.0), source_camera="/cam")
        with pytest.raises(GoalSealError, match="before the goal was declared"):
            seal.acquire(b"frame")

    def test_sealing_without_provenance_is_refused(self) -> None:
        seal = GoalSeal(goal_xy=(0.0, 0.0), source_camera="/cam")
        seal.declare()
        seal.acquire(b"frame")
        with pytest.raises(GoalSealError, match="cannot seal"):
            seal.seal()

    def test_pixel_similarity_is_not_the_provenance_decision(self) -> None:
        """A stationary robot's identical frames must not be the deciding evidence."""
        seal = self.make(image=b"same-scene")
        seal.note_first_motion()
        r = evaluate_goal_seal(seal)
        assert r.status is GateStatus.PASS
        assert "pixel similarity does not establish provenance" in (
            r.detail["provenance_is_the_event_order"]
        )


# ------------------------------------------------------------------ G10 ----
class TestG10WindowArithmetic:
    def test_window_counts_come_from_the_pinned_loader_spec(self) -> None:
        counts = window_counts(120)
        assert counts["gnm"] == 110      # 120 - 5 - 5
        assert counts["vint"] == 110
        assert counts["nomad"] == 109    # 120 - 3 - 8

    def test_nomad_is_the_scarcer_model_and_therefore_the_limit(self) -> None:
        counts = window_counts(50)
        assert counts["nomad"] < counts["gnm"]

    def test_a_short_trajectory_yields_no_windows(self) -> None:
        assert window_counts(5)["nomad"] == 0


class TestG10Boundaries:
    """Exactly at threshold PASSES; immediately below FAILS. No rounding."""

    def trajectory(self, n: int, total_m: float, legs: int = 4) -> tuple[np.ndarray, np.ndarray]:
        """A staircase built point by point, so the arc length is exact.

        Resampling a corner polyline was the first attempt and it is subtly
        wrong for a boundary test: linear interpolation across a corner cuts it,
        so a nominal 8.0 m route measures fractionally under 8.0 and the
        "exactly at threshold" case fails for a reason that has nothing to do
        with the gate. Points are placed at a uniform step instead, with turns
        falling on sample indices, so travelled distance is exactly
        ``(n - 1) * step``.
        """
        step = total_m / (n - 1)
        per_leg = max(1, math.ceil((n - 1) / legs))
        pts = [(0.0, 0.0)]
        x = y = 0.0
        for i in range(n - 1):
            if (i // per_leg) % 2 == 0:
                x += step
            else:
                y += step
            pts.append((x, y))
        return np.array(pts), np.zeros(n)

    def test_exactly_at_every_threshold_passes(self) -> None:
        pos, yaw = self.trajectory(n=120, total_m=8.0)
        r = measure_from_trajectory(pos, yaw)
        assert r.status is GateStatus.PASS, r.reason
        m = r.detail["measurement"]
        assert m["usable_frames"] == 120
        assert m["travelled_distance_m"] == pytest.approx(8.0)
        assert m["heading_change_count"] == 3, "exactly at the turn threshold too"

    def test_one_frame_below_the_frame_threshold_fails(self) -> None:
        """Distance is comfortably clear, so only the frame count can fail."""
        pos, yaw = self.trajectory(n=119, total_m=12.0)
        r = measure_from_trajectory(pos, yaw)
        assert r.status is GateStatus.FAIL
        assert r.detail["checks"]["usable_frames"] is False
        assert r.detail["checks"]["travelled_distance"] is True

    def test_a_distance_fractionally_below_eight_metres_fails(self) -> None:
        """7.999... must not round into a pass."""
        pos, yaw = self.trajectory(n=200, total_m=7.999)
        r = measure_from_trajectory(pos, yaw)
        assert r.status is GateStatus.FAIL
        assert r.detail["checks"]["travelled_distance"] is False
        assert r.detail["measurement"]["travelled_distance_m"] < 8.0

    def test_a_separation_below_five_metres_fails(self) -> None:
        """A closed loop travels far and separates by nothing."""
        loop = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0], [0.0, 0.0]])
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(loop, axis=0), axis=1))])
        t = np.linspace(0.0, s[-1], 200)
        pos = np.column_stack([np.interp(t, s, loop[:, 0]), np.interp(t, s, loop[:, 1])])
        r = measure_from_trajectory(pos, np.zeros(200))
        assert r.status is GateStatus.FAIL
        assert r.detail["checks"]["start_goal_separation"] is False

    def test_only_two_qualifying_turns_fails(self) -> None:
        pos, yaw = self.trajectory(n=200, total_m=20.0, legs=3)
        r = measure_from_trajectory(pos, yaw)
        assert r.detail["measurement"]["heading_change_count"] == 2
        assert r.status is GateStatus.FAIL
        assert r.detail["checks"]["heading_changes"] is False

    def test_insufficient_context_windows_fails(self) -> None:
        pos, yaw = self.trajectory(n=25, total_m=20.0)
        r = measure_from_trajectory(pos, yaw)
        assert r.detail["checks"]["context_windows"] is False
        assert r.status is GateStatus.FAIL

    def test_a_turn_below_thirty_degrees_does_not_qualify(self) -> None:
        """The angle threshold must discriminate, not merely exist."""
        shallow = np.array([[0.0, 0.0], [10.0, 0.0],
                            [10.0 + 10 * math.cos(math.radians(20)),
                             10 * math.sin(math.radians(20))]])
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(shallow, axis=0), axis=1))])
        t = np.linspace(0.0, s[-1], 300)
        pos = np.column_stack([np.interp(t, s, shallow[:, 0]), np.interp(t, s, shallow[:, 1])])
        r = measure_from_trajectory(pos, np.zeros(300))
        assert r.detail["measurement"]["heading_change_count"] == 0


class TestG10KindsAreDistinct:
    def test_a_route_prediction_is_labelled_a_forecast(self) -> None:
        r = predict_from_route(route_with_turns(), control_hz=CONTROL_HZ, cruise_v=CRUISE_V)
        assert r.kind is GateKind.PREDICTED_CAPABILITY
        assert r.detail["estimator"]["is_a_forecast"] is True

    def test_a_trajectory_measurement_is_a_postcondition(self) -> None:
        pos = np.column_stack([np.linspace(0, 10, 300), np.zeros(300)])
        r = measure_from_trajectory(pos, np.zeros(300))
        assert r.kind is GateKind.POSTCONDITION
        assert r.detail["frame_count_is_recorded_not_estimated"] is True

    def test_the_thresholds_are_labelled_predeclared_not_model_requirements(self) -> None:
        r = predict_from_route(route_with_turns(), control_hz=CONTROL_HZ, cruise_v=CRUISE_V)
        assert "PREDECLARED" in r.detail["thresholds"]["label"]
        assert "not requirements published by GNM, ViNT or NoMaD" in (
            r.detail["threshold_semantics"]
        )

    def test_the_frozen_threshold_values_are_what_the_contract_says(self) -> None:
        t = LONG_HORIZON_THRESHOLDS
        assert (t.min_usable_frames, t.min_travelled_distance_m,
                t.min_start_goal_separation_m, t.min_heading_changes,
                t.heading_change_deg, t.min_valid_context_windows) == (
            120, 8.0, 5.0, 3, 30.0, 30)


class TestG10InputValidation:
    def test_mismatched_positions_and_yaws_are_refused(self) -> None:
        with pytest.raises(ValueError, match="taking the shorter would hide"):
            measure_from_trajectory(np.zeros((10, 2)), np.zeros(9))

    def test_a_bad_position_shape_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"\(T, 2\)"):
            measure_from_trajectory(np.zeros((10, 3)), np.zeros(10))

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_a_nonpositive_rate_is_refused(self, bad: float) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            predict_from_route(route_with_turns(), control_hz=CONTROL_HZ, cruise_v=bad)


def test_controller_identity_is_frozen_dataclass() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity().max_v = 9.9  # type: ignore[misc]
