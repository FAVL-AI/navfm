"""Tests for the START / CURRENT / GOAL contract.

The panel is a view; this is the thing being viewed. What matters is not that
the states can be stored but that they cannot be confused, so almost every test
here is about a refusal.

The refusal that matters most: a sealed goal cannot be replaced. An episode
whose target can move after the rollout can be made to succeed by redefining
success, and the resulting trajectory file is byte-for-byte indistinguishable
from an honest one. No downstream check can recover that -- which is why it is
enforced in the type rather than in operator discipline.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from navfm.isaac.navstate import (
    EpisodeRecorder,
    EpisodeReplay,
    GoalSealedError,
    NavigationEpisode,
    Pose2D,
    StateSnapshot,
    TransformRecord,
)


def _tf(frame="camera_link", parent="base_link", static=True):
    return TransformRecord(
        frame=frame, parent=parent, translation=(0.1, 0.0, 0.24),
        rotation_rpy=(0.0, 0.0, 0.0), is_static=static, source="fixed joint",
    )


def _snap(label="CURRENT", x=0.0, y=0.0, yaw=0.0, image=True):
    return StateSnapshot(
        label=label, pose=Pose2D(x, y, yaw),
        image_path=f"/tmp/{label.lower()}.jpg" if image else None,
        image_sha256="a" * 64 if image else None,
        transforms=(_tf(),), timestamp_utc="2026-08-13T09:00:00+00:00",
    )


class TestSealing:
    def test_a_sealed_goal_cannot_be_replaced(self) -> None:
        """The load-bearing refusal."""
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        ep.seal_goal(_snap("GOAL", x=2.0))
        with pytest.raises(GoalSealedError) as excinfo:
            ep.seal_goal(_snap("GOAL", x=99.0))
        assert "already sealed" in str(excinfo.value)
        assert ep.goal is not None
        assert ep.goal.evaluation_pose().x == 2.0, "the original goal must survive"

    def test_sealing_requires_a_start(self) -> None:
        ep = NavigationEpisode("e1")
        with pytest.raises(GoalSealedError, match="capture START"):
            ep.seal_goal(_snap("GOAL"))

    def test_a_goal_without_an_image_is_refused(self) -> None:
        """The image is what the policy navigates toward; a pose-only goal would
        be an oracle target wearing a goal's name."""
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        with pytest.raises(GoalSealedError, match="image and its digest"):
            ep.seal_goal(_snap("GOAL", image=False))

    def test_the_start_freezes_once_the_goal_is_sealed(self) -> None:
        """Moving the start line after the finish line is drawn is a new experiment."""
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        ep.seal_goal(_snap("GOAL", x=2.0))
        with pytest.raises(GoalSealedError, match="start is fixed"):
            ep.capture_start(_snap("START", x=5.0))

    def test_the_start_may_be_recaptured_before_sealing(self) -> None:
        """Setup is not the experiment. Before sealing, moving around is fine."""
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START", x=1.0))
        ep.capture_start(_snap("START", x=3.0))
        assert ep.start is not None and ep.start.pose.x == 3.0


class TestRunGuard:
    def test_running_without_a_sealed_goal_is_refused(self) -> None:
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        with pytest.raises(GoalSealedError, match="GOAL has not been sealed"):
            ep.require_ready()

    def test_running_without_a_start_is_refused(self) -> None:
        ep = NavigationEpisode("e1")
        with pytest.raises(GoalSealedError, match="START has not been captured"):
            ep.require_ready()

    def test_a_fully_defined_episode_is_permitted(self) -> None:
        """The other direction: without this, the refusals prove nothing."""
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        ep.seal_goal(_snap("GOAL", x=2.0))
        ep.require_ready()
        assert ep.is_ready_to_run


class TestTheGoalPoseDoesNotReachThePolicy:
    def test_the_policy_accessor_returns_an_image_and_nothing_else(self) -> None:
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        goal = ep.seal_goal(_snap("GOAL", x=2.0, y=3.0, yaw=1.1))
        obs = goal.policy_observation()
        assert isinstance(obs, str) and obs.endswith(".jpg")
        assert "2.0" not in str(obs) and "3.0" not in str(obs)

    def test_the_pose_is_reachable_only_through_the_evaluation_accessor(self) -> None:
        """Two accessors on one object, so the separation is a property of the
        type rather than of whoever wires the loop."""
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        goal = ep.seal_goal(_snap("GOAL", x=2.0, y=3.0))
        assert goal.evaluation_pose().x == 2.0
        assert goal.evaluation_pose().y == 3.0

    def test_distance_to_goal_is_available_for_evaluation(self) -> None:
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        ep.seal_goal(_snap("GOAL", x=3.0, y=4.0))
        ep.update_current(_snap("CURRENT", x=0.0, y=0.0))
        assert ep.distance_to_goal() == pytest.approx(5.0)

    def test_distance_is_none_before_the_episode_is_defined(self) -> None:
        assert NavigationEpisode("e1").distance_to_goal() is None


class TestCurrentIsTheOnlyMutableState:
    def test_frames_are_indexed_in_order(self) -> None:
        ep = NavigationEpisode("e1")
        for i in range(4):
            ep.update_current(_snap("CURRENT", x=float(i)))
        assert [s.frame_index for s in ep.history] == [0, 1, 2, 3]
        assert ep.current is not None and ep.current.pose.x == 3.0

    def test_history_is_a_tuple_so_a_caller_cannot_rewrite_it(self) -> None:
        ep = NavigationEpisode("e1")
        ep.update_current(_snap("CURRENT"))
        assert isinstance(ep.history, tuple)

    def test_a_snapshot_is_frozen(self) -> None:
        """A captured moment is a record. Mutating it would rewrite history."""
        s = _snap()
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.pose = Pose2D(9, 9, 9)  # type: ignore[misc]


class TestPose:
    def test_heading_error_takes_the_short_way_round(self) -> None:
        """3.0 rad to -3.0 rad is a small turn, not a nearly-full one. Getting
        this wrong makes a robot spin the long way to correct a tiny error."""
        a, b = Pose2D(0, 0, 3.0), Pose2D(0, 0, -3.0)
        assert abs(a.heading_error_to(b)) < 0.3

    def test_distance_is_planar(self) -> None:
        assert Pose2D(0, 0, 0).distance_to(Pose2D(3, 4, 2.0)) == pytest.approx(5.0)


class TestRecordAndReplay:
    def test_a_recording_round_trips(self, tmp_path) -> None:
        ep = NavigationEpisode("e42", scene="simple_room", robot="yahboom_m3_pro")
        ep.capture_start(_snap("START"))
        ep.seal_goal(_snap("GOAL", x=2.0, y=1.0))
        rec = EpisodeRecorder(ep, tmp_path)
        for i in range(5):
            snap = ep.update_current(_snap("CURRENT", x=float(i) * 0.2))
            rec.record_step(snap, control_mode="ViNT", commanded=(0.4, 0.0, 0.1),
                            achieved=(0.39, 0.0, 0.1),
                            policy_output={"waypoint_normalised": [1.0, 0.0]})
        path = rec.finalise()

        rp = EpisodeReplay(path)
        assert len(rp) == 5
        assert rp.episode_id == "e42"
        assert rp.goal is not None and rp.goal["pose"][0] == 2.0
        assert rp.at(2)["pose"][0] == pytest.approx(0.4)
        assert rp.at(2)["control_mode"] == "ViNT"

    def test_replay_clamps_rather_than_wraps(self, tmp_path) -> None:
        """Wrapping would make frame -1 show the last frame, which reads as the
        robot having finished when it has not started."""
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        ep.seal_goal(_snap("GOAL", x=1.0))
        rec = EpisodeRecorder(ep, tmp_path)
        for i in range(3):
            rec.record_step(ep.update_current(_snap("CURRENT", x=float(i))),
                            control_mode="MANUAL", commanded=(0, 0, 0), achieved=(0, 0, 0))
        rp = EpisodeReplay(rec.finalise())
        assert rp.at(-5)["pose"][0] == pytest.approx(0.0)
        assert rp.at(99)["pose"][0] == pytest.approx(2.0)

    def test_an_empty_recording_raises_rather_than_returning_a_default(self, tmp_path) -> None:
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        ep.seal_goal(_snap("GOAL", x=1.0))
        rp = EpisodeReplay(EpisodeRecorder(ep, tmp_path).finalise())
        with pytest.raises(IndexError):
            rp.at(0)

    def test_the_manifest_carries_its_admission_boundary(self, tmp_path) -> None:
        """A recording that does not say what it is may be cited as what it is not."""
        ep = NavigationEpisode("e1")
        ep.capture_start(_snap("START"))
        ep.seal_goal(_snap("GOAL", x=1.0))
        data = json.loads(EpisodeRecorder(ep, tmp_path).finalise().read_text())
        assert data["admission_status"] == "NOT_ADMITTED"
        assert data["stage"] == "SIMULATION_DEVELOPMENT"
        assert "not a demonstration" in data["claim_boundary"]


class TestTransformsShowTheCameraIsBolted:
    def test_a_static_mount_is_marked_static(self) -> None:
        """This is what lets the panel *show* rigid attachment rather than
        assert it: the camera-to-base transform must not change while the
        camera's world transform does."""
        t = _tf(static=True)
        assert t.is_static and t.parent == "base_link"
        assert t.as_dict()["translation"] == (0.1, 0.0, 0.24)


class TestUiPredicates:
    """A panel must know whether a button should be enabled before it is pressed.

    Raising is right at the moment of action and wrong when drawing a widget, so
    both exist. These must agree with the guards they mirror -- a predicate that
    says "ready" where require_ready() raises would produce an enabled button
    that throws when clicked.
    """

    def test_predicates_agree_with_the_guard_they_mirror(self) -> None:
        ep = NavigationEpisode("e1")
        assert ep.can_run()[0] is False
        with pytest.raises(GoalSealedError):
            ep.require_ready()

        ep.capture_start(_snap("START"))
        assert ep.can_run()[0] is False
        with pytest.raises(GoalSealedError):
            ep.require_ready()

        ep.seal_goal(_snap("GOAL", x=1.0))
        assert ep.can_run()[0] is True
        ep.require_ready()

    def test_each_refusal_carries_a_reason_a_user_can_act_on(self) -> None:
        ep = NavigationEpisode("e1")
        assert "START" in ep.can_seal_goal()[1]
        ep.capture_start(_snap("START"))
        assert ep.can_seal_goal()[0] is True
        ep.seal_goal(_snap("GOAL", x=1.0))
        ok, why = ep.can_capture_start()
        assert ok is False and "new one" in why

    def test_reset_is_unavailable_until_a_start_exists(self) -> None:
        ep = NavigationEpisode("e1")
        assert ep.can_reset_to_start()[0] is False
        ep.capture_start(_snap("START"))
        assert ep.can_reset_to_start()[0] is True
