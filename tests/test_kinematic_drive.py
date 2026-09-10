"""Defining controls A-I for KINEMATIC_COLLECTION_DRIVE_V1.

The guard is the whole point of choosing kinematic drive over naive teleporting,
so it is proved against geometry whose answer is known, in both directions: safe
motion must succeed, and unsafe motion must be refused *and not applied*.

The distinction that matters throughout: a rejected pose is never applied. A
guard that reported a violation and moved anyway would be a diagnostic, not an
invariant.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from navfm.collection.kinematic_drive import (
    DriveOutcome,
    KinematicDriveConfig,
    KinematicDriver,
    integrate_se2,
    swept_poses,
)

CFG = KinematicDriveConfig()


class OpenSpace:
    def pose_is_free(self, x: float, y: float, yaw: float) -> bool:
        return True


@dataclasses.dataclass
class WallAtX:
    """Blocking geometry occupying a band in x, as a footprint-aware test."""

    x_min: float
    x_max: float
    radius: float = 0.24

    def pose_is_free(self, x: float, y: float, yaw: float) -> bool:
        return not (x + self.radius > self.x_min and x - self.radius < self.x_max)


@dataclasses.dataclass
class BlockedYawBand:
    """Free everywhere, except while heading lies in a band. Rotation control."""

    lo: float
    hi: float

    def pose_is_free(self, x: float, y: float, yaw: float) -> bool:
        return not (self.lo <= yaw <= self.hi)


class TestIntegration:
    def test_forward_motion_advances_along_heading(self) -> None:
        p = integrate_se2((0.0, 0.0, 0.0), (0.45, 0.0, 0.0), 1.0)
        assert p[0] == pytest.approx(0.45)
        assert p[1] == pytest.approx(0.0)

    def test_body_frame_velocity_is_rotated_into_the_world(self) -> None:
        p = integrate_se2((0.0, 0.0, math.pi / 2), (0.45, 0.0, 0.0), 1.0)
        assert p[0] == pytest.approx(0.0, abs=1e-9)
        assert p[1] == pytest.approx(0.45)

    def test_heading_wraps_to_the_shortest_branch(self) -> None:
        p = integrate_se2((0.0, 0.0, 3.0), (0.0, 0.0, 1.0), 1.0)
        assert -math.pi <= p[2] <= math.pi

    def test_sweep_interpolates_the_short_way_round(self) -> None:
        """Otherwise a step across +/-pi tests poses the robot never occupies."""
        poses = swept_poses((0.0, 0.0, 3.10), (0.0, 0.0, -3.10), 8)
        for _, _, yaw in poses:
            assert abs(yaw) > 3.0, f"swept through {yaw}, which is the long way"

    def test_sweep_ends_at_the_candidate(self) -> None:
        end = (1.0, 2.0, 0.5)
        assert swept_poses((0.0, 0.0, 0.0), end, 4)[-1] == pytest.approx(end)


class TestDefiningControls:
    def driver(self, guard: object) -> KinematicDriver:
        return KinematicDriver(guard=guard, config=CFG)  # type: ignore[arg-type]

    def test_A_clear_straight_translation_succeeds(self) -> None:
        r = self.driver(OpenSpace()).step((0.0, 0.0, 0.0), (0.35, 0.0, 0.0))
        assert r.outcome is DriveOutcome.APPLIED
        assert r.pose[0] > 0.0

    def test_B_clear_rotation_succeeds(self) -> None:
        r = self.driver(OpenSpace()).step((0.0, 0.0, 0.0), (0.0, 0.0, 0.8))
        assert r.outcome is DriveOutcome.APPLIED
        assert r.pose[2] > 0.0

    def test_C_obstacle_at_the_candidate_pose_rejects_motion(self) -> None:
        # Positioned so ONE step reaches the wall. Two earlier drafts did not:
        # the footprint radius is 0.24 and a step is 0.0292 m, so the start must
        # sit within (radius + step) of the wall face or the guard correctly
        # allows the move and the test asserts something untrue.
        guard = WallAtX(x_min=0.0, x_max=0.5)
        d = self.driver(guard)
        start = (-0.25, 0.0, 0.0)
        assert guard.pose_is_free(*start), "the starting pose must itself be clear"
        r = d.step(start, (0.35, 0.0, 0.0))
        assert r.outcome is DriveOutcome.REJECTED_COLLISION
        assert r.pose == start, "a rejected pose must not be applied"
        assert d.rejections == 1 and d.applied == 0

    def test_D_obstacle_on_the_sweep_but_not_the_endpoint_rejects_motion(self) -> None:
        """The case an endpoint-only check passes and a sweep must not."""
        class ThinWallMidway:
            def pose_is_free(self, x: float, y: float, yaw: float) -> bool:
                return not (0.010 < x < 0.012)

        d = self.driver(ThinWallMidway())
        start, twist = (0.0, 0.0, 0.0), (0.35, 0.0, 0.0)
        end = integrate_se2(start, twist, CFG.dt)
        assert ThinWallMidway().pose_is_free(*end), "the endpoint itself is clear"
        r = d.step(start, twist)
        assert r.outcome is DriveOutcome.REJECTED_COLLISION
        assert r.pose == start

    def test_E_a_large_dt_cannot_step_over_a_wall(self) -> None:
        """The sweep's reason for existing.

        A first draft commanded a huge velocity, but the driver clamps to max_v
        first, so the step never became large and nothing was demonstrated. The
        way a step gets large is a large dt, so that is what is tested -- with
        the per-step limits raised to match, otherwise the integration-fault
        check fires and the sweep is never reached.
        """
        class ThinWall:
            def pose_is_free(self, x: float, y: float, yaw: float) -> bool:
                return not (0.20 < x < 0.25)

        big = dataclasses.replace(CFG, dt=1.0, max_step_translation_m=1.0,
                                  max_step_rotation_rad=2.0)
        d = KinematicDriver(guard=ThinWall(), config=big)
        start, twist = (0.0, 0.0, 0.0), (0.45, 0.0, 0.0)
        end = integrate_se2(start, twist, big.dt)
        assert end[0] > 0.25, "the candidate is beyond the wall"
        assert ThinWall().pose_is_free(*end), "and is itself clear, so only the sweep can catch it"
        r = d.step(start, twist)
        assert r.outcome is DriveOutcome.REJECTED_COLLISION
        assert r.pose == start

    def test_an_integration_fault_beyond_the_per_step_limit_is_refused(self) -> None:
        """A pose jump larger than the limits permit in one dt is not applied."""
        big_dt = dataclasses.replace(CFG, dt=1.0)
        d = KinematicDriver(guard=OpenSpace(), config=big_dt)
        r = d.step((0.0, 0.0, 0.0), (0.45, 0.0, 0.0))
        assert r.outcome is DriveOutcome.REJECTED_COLLISION
        assert "integration fault" in r.reason
        assert r.pose == (0.0, 0.0, 0.0)

    def test_F_a_clear_route_is_not_falsely_rejected(self) -> None:
        d = self.driver(OpenSpace())
        pose = (0.0, 0.0, 0.0)
        for _ in range(200):
            r = d.step(pose, (0.35, 0.0, 0.0))
            assert r.outcome is DriveOutcome.APPLIED
            pose = r.pose
        assert d.rejections == 0
        assert pose[0] == pytest.approx(200 * 0.35 * CFG.dt)

    def test_G_zero_command_produces_zero_displacement(self) -> None:
        d = self.driver(OpenSpace())
        r = d.step((1.0, 2.0, 0.3), (0.0, 0.0, 0.0))
        assert r.outcome is DriveOutcome.NO_COMMAND
        assert r.pose == (1.0, 2.0, 0.3)
        assert d.applied == 0 and d.rejections == 0, "not asked is not refused"

    def test_H_a_safe_non_zero_command_produces_measurable_displacement(self) -> None:
        """The direction F-DRIVE-1 failed in: commands must actually move the base."""
        d = self.driver(OpenSpace())
        pose = (0.0, 0.0, 0.0)
        for _ in range(40):
            pose = d.step(pose, (0.35, 0.0, 0.0)).pose
        assert pose[0] > 1.0, f"40 steps at 0.35 m/s moved only {pose[0]:.4f} m"

    def test_I_a_blocked_command_leaves_the_pose_short_of_the_obstacle(self) -> None:
        """The command may exist; the realised pose must not cross the obstacle."""
        guard = WallAtX(x_min=1.0, x_max=2.0)
        d = self.driver(guard)
        pose = (0.0, 0.0, 0.0)
        for _ in range(400):
            r = d.step(pose, (0.35, 0.0, 0.0))
            pose = r.pose
        assert pose[0] + 0.24 <= 1.0 + 1e-9, "the footprint crossed into the wall"
        assert d.rejections > 0, "the guard must have refused at least once"

    def test_rotation_into_blocked_geometry_is_refused(self) -> None:
        d = self.driver(BlockedYawBand(lo=0.05, hi=1.0))
        r = d.step((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        assert r.outcome is DriveOutcome.REJECTED_COLLISION
        assert r.pose[2] == 0.0


class TestClaimBoundaries:
    def test_the_motion_model_declares_what_it_does_not_evaluate(self) -> None:
        d = KinematicDriver(guard=OpenSpace()).to_dict()
        assert d["motion_model"] == "KINEMATIC_SE2"
        for field in ("contact_response", "wheel_dynamics", "mecanum_roller_fidelity",
                      "slip_traction_fidelity"):
            assert d[field] == "NOT_EVALUATED"

    def test_velocity_limits_are_enforced(self) -> None:
        d = KinematicDriver(guard=OpenSpace(), config=CFG)
        r = d.step((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
        assert r.commanded[0] == pytest.approx(CFG.max_v)

    def test_the_guard_is_consulted_for_every_applied_pose(self) -> None:
        """A driver that applied without asking would be a teleport."""
        class CountingGuard:
            def __init__(self) -> None:
                self.calls = 0

            def pose_is_free(self, x: float, y: float, yaw: float) -> bool:
                self.calls += 1
                return True

        g = CountingGuard()
        KinematicDriver(guard=g, config=CFG).step((0.0, 0.0, 0.0), (0.35, 0.0, 0.0))
        assert g.calls == CFG.sweep_substeps
