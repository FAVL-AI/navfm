"""The camera hangs off an articulation link, not off the robot root.

G7 measured the defect on 2026-09-09: the robot moved 2.236 m and the camera
moved 0.000 m. ``attach_camera`` had created the prim under ``/World/Robot``,
which is the plain xform the USD reference was added beneath and which physics
never touches. The links under it are what move.

Nothing about the result looked wrong from inside the collector. The prim
existed, it was named ``Camera_front``, ``rgb()`` returned images, and every one
of them was from a viewpoint that never turned with the base. That is why the
gate judges geometrically and why this pins the structure: a name is not
evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

from navfm.isaac.robot import M3PRO, SimRobot

REPO = Path(__file__).resolve().parents[1]
G7_ARTEFACT = REPO / "gates/BO10/g7_camera_hard_gate_20260909.json"


def robot() -> SimRobot:
    return SimRobot(app=None, config=M3PRO)


class TestCameraIsParentedToAMovingLink:
    def test_the_camera_is_not_a_direct_child_of_the_robot_root(self) -> None:
        r = robot()
        assert r.camera_path != f"{r.prim_path}/Camera_front", (
            "a camera parented to the robot root is world-fixed in effect: physics "
            "moves the links beneath the root, not the root itself"
        )

    def test_the_camera_hangs_off_the_base_link(self) -> None:
        r = robot()
        assert r.camera_parent_path == "/World/Robot/base_link"
        assert r.camera_path == "/World/Robot/base_link/Camera_front"

    def test_the_parent_link_is_configurable_without_moving_the_root(self) -> None:
        r = SimRobot(app=None, config=M3PRO, camera_parent_link="camera_link")
        assert r.camera_path == "/World/Robot/camera_link/Camera_front"
        assert r.camera_path.startswith(r.prim_path + "/")

    def test_the_camera_path_is_strictly_below_its_parent(self) -> None:
        r = robot()
        assert r.camera_path.startswith(r.camera_parent_path + "/")
        assert r.camera_parent_path != r.prim_path


class TestTheG7ArtefactRecordsAMeasuredPass:
    """Guards the result itself: a PASS with a control that did not fire is not a pass."""

    def test_the_artefact_exists_and_passed(self) -> None:
        assert G7_ARTEFACT.is_file(), "G7 must be re-run after any camera-mounting change"
        rec = json.loads(G7_ARTEFACT.read_text())
        assert rec["G7_CAMERA"] == "PASS"

    def test_all_three_negative_controls_were_rejected(self) -> None:
        rec = json.loads(G7_ARTEFACT.read_text())
        assert rec["negative_controls_all_rejected"] is True
        controls = rec["negative_controls"]
        for name in ("rotated_180", "detached_world_fixed", "wrong_prim"):
            assert controls[name]["verdict"] == "FAIL", (
                f"{name} passed; a gate that cannot detect it certifies nothing"
            )

    def test_the_detached_control_fails_on_attachment_specifically(self) -> None:
        """Not merely 'fails somehow' -- it must fail on the property it tests."""
        rec = json.loads(G7_ARTEFACT.read_text())
        failed = rec["negative_controls"]["detached_world_fixed"]["failed"]
        assert "attached_to_robot" in failed
        assert "moves_with_robot" in failed

    def test_the_rotated_control_fails_on_orientation_specifically(self) -> None:
        rec = json.loads(G7_ARTEFACT.read_text())
        assert "faces_robot_forward" in rec["negative_controls"]["rotated_180"]["failed"]

    def test_the_positive_case_actually_moved_the_robot(self) -> None:
        """A pass from a robot that never moved would prove nothing (FL-019)."""
        rec = json.loads(G7_ARTEFACT.read_text())
        positive = rec["positive"]
        assert positive["robot_world_moved_m"] > rec["tolerances"]["min_robot_motion_m"]
        assert positive["camera_world_moved_m"] > rec["tolerances"]["min_robot_motion_m"]
        assert positive["usd_readback_is_live"] is True

    def test_the_measured_drift_is_within_tolerance(self) -> None:
        rec = json.loads(G7_ARTEFACT.read_text())
        assert rec["positive"]["relative_drift_m"] < rec["tolerances"]["attach_drift_m"]
