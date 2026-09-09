"""G7: is the collection camera really bolted to the robot and really facing forward?

Judged geometrically, never from the prim's name. A camera called
``front_rgb_camera`` that is world-fixed, or mounted backwards, passes every
name-based check and produces a dataset whose observations do not correspond to
the robot's heading.

Three positive properties are proved:

* the camera's transform *relative to the robot* is invariant while the robot
  moves -- so it is attached, not merely co-located;
* the camera's optical axis lies along robot-forward within a declared tolerance;
* the camera moves in the world when the robot moves, and its view yaw tracks
  robot yaw.

And three negative controls must FAIL, because a gate that cannot fail certifies
nothing (F-M2-1):

* the camera rotated 180 degrees                 -> must be rejected
* the camera detached and world-fixed            -> must be rejected
* the wrong prim offered as the collection camera -> must be rejected

If any negative control passes, the instrument is broken and collection stops.
"""

from __future__ import annotations

import argparse
import contextlib
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402

#: Optical axis must lie within this of robot-forward.
FORWARD_TOL_DEG = 15.0
#: Relative transform drift permitted across robot motion.
ATTACH_DRIFT_TOL_M = 1e-3
#: The robot must actually move for the attachment test to mean anything.
MIN_ROBOT_MOTION_M = 0.5

AMENDMENT_DIGEST = "a0c08324e7cc79963c6bf131177205f8f7c21874378ae0f0aa8097b6e3839303"


def _provenance(robot: str) -> dict[str, Any]:
    import hashlib
    import platform
    import subprocess

    def _sh(*c: str) -> str:
        try:
            return subprocess.run(c, capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception:
            return "UNAVAILABLE"
    isaac_version = "UNKNOWN"
    with contextlib.suppress(Exception):
        from importlib.metadata import version
        isaac_version = version("isaacsim")
    try:
        rsha = hashlib.sha256(Path(robot).read_bytes()).hexdigest()
    except Exception:
        rsha = "UNREADABLE"
    return {
        "hostname": platform.node(), "interpreter": sys.executable,
        "isaac_sim_version": isaac_version,
        "git_head": _sh("git", "-C", str(REPO), "rev-parse", "HEAD"),
        "worktree_dirty": bool(_sh("git", "-C", str(REPO), "status", "--porcelain")),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "amendment_digest_pinned": AMENDMENT_DIGEST,
        "robot_asset": robot, "robot_asset_sha256": rsha,
        "gpu": _sh("nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--robot", required=True)
    ap.add_argument("--camera-prim", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    from isaacsim.core.api import SimulationContext
    from pxr import Gf, UsdGeom

    rec: dict[str, Any] = {
        "check": "G7_CAMERA_HARD_GATE",
        "artifact_semantics": "DIAGNOSTIC_ONLY_NOT_AN_EXPECTATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": _provenance(args.robot),
        "judged": "GEOMETRICALLY, never from the prim name",
        "tolerances": {"forward_deg": FORWARD_TOL_DEG,
                       "attach_drift_m": ATTACH_DRIFT_TOL_M,
                       "min_robot_motion_m": MIN_ROBOT_MOTION_M},
        "claim_boundary": ("Concerns camera identity, attachment and orientation only. "
                           "No image quality, no calibration, no physical-hardware claim."),
    }

    try:
        import dataclasses

        from navfm.isaac.robot import M3PRO, SimRobot

        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0)
        # A ground plane, so the articulation has something to rest on.
        from isaacsim.core.api.objects.ground_plane import GroundPlane
        GroundPlane(prim_path="/World/groundPlane", size=40.0)

        # Spawn through the PRODUCTION path. Validating a camera this harness
        # created itself would certify the harness, not the collector.
        robot_cfg = dataclasses.replace(M3PRO, usd_path=args.robot)
        robot = SimRobot(app, robot_cfg)
        # The timeline must be running before spawn(): the articulation's
        # physics tensor entity is created by the simulation, not by the prim.
        sim.initialize_physics()
        sim.play()
        for _ in range(3):
            sim.step(render=False)
        robot.spawn()
        stage = stage_utils.get_current_stage()
        for _ in range(5):
            sim.step(render=False)
        robot.attach_camera()
        for _ in range(3):
            sim.step(render=True)

        rec["production_camera_path"] = robot.camera_path
        rec["camera_config"] = {
            "height_m": robot_cfg.camera.height,
            "x_offset_m": robot_cfg.camera.x_offset,
            "y_offset_m": robot_cfg.camera.y_offset,
            "resolution": list(robot_cfg.camera.resolution),
        }

        xcache = UsdGeom.XformCache()

        def world_of(path: str) -> Any:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                return None
            return xcache.GetLocalToWorldTransform(prim)

        def pose_of(path: str) -> tuple[Any, Any] | None:
            m = world_of(path)
            if m is None:
                return None
            t = m.ExtractTranslation()
            return np.array([t[0], t[1], t[2]]), m

        base_path = "/World/Robot/base_link"
        cam_path = args.camera_prim

        def move_robot(x: float, y: float, yaw: float) -> None:
            """Move the robot through the PRODUCTION primitive, not a raw xform.

            The camera must follow because it is parented to the robot, and
            teleport() is what the collector actually calls between episodes.
            """
            robot.teleport((x, y), yaw)
            for _ in range(3):
                sim.step(render=False)
            xcache.Clear()

        def relative(cam: str, base: str) -> Any:
            pc, mc = pose_of(cam) or (None, None)
            pb, mb = pose_of(base) or (None, None)
            if pc is None or pb is None:
                return None
            return np.array(mc.ExtractTranslation()) - np.array(mb.ExtractTranslation())

        def optical_axis(path: str) -> Any:
            """USD cameras look down local -Z. Return that axis in world space."""
            m = world_of(path)
            if m is None:
                return None
            r = m.ExtractRotationMatrix()
            v = Gf.Vec3d(0, 0, -1) * r
            a = np.array([v[0], v[1], v[2]], dtype=float)
            n = np.linalg.norm(a)
            return a / n if n > 1e-9 else a

        def robot_forward() -> Any:
            """Robot-forward from the GROUND-TRUTH articulation pose.

            Reading it from the USD xform would be fragile: with fabric enabled
            the USD transform need not reflect physics, and a stale read would
            look like a camera-orientation defect rather than a stale read.
            """
            _pos, yaw = robot.pose()
            return np.array([math.cos(yaw), math.sin(yaw), 0.0], dtype=float)

        def forward_angle_deg(path: str) -> float | None:
            oa = optical_axis(path)
            if oa is None:
                return None
            fwd = robot_forward()
            oa2 = np.array([oa[0], oa[1]])
            f2 = np.array([fwd[0], fwd[1]])
            if np.linalg.norm(oa2) < 1e-9 or np.linalg.norm(f2) < 1e-9:
                return None
            oa2 /= np.linalg.norm(oa2)
            f2 /= np.linalg.norm(f2)
            return float(math.degrees(math.acos(float(np.clip(np.dot(oa2, f2), -1, 1)))))

        def evaluate(cam: str) -> dict[str, Any]:
            """The complete G7 predicate, applied to whatever camera is offered."""
            xcache.Clear()
            move_robot(0.0, 0.0, 0.0)
            p0 = pose_of(cam)
            if p0 is None:
                return {"exists": False, "verdict": "FAIL", "reason": "camera prim not found"}
            rel0 = relative(cam, base_path)
            ang0 = forward_angle_deg(cam)
            cam0 = p0[0].copy()
            b0 = (pose_of(base_path) or (None, None))[0]
            gt0 = np.asarray(robot.pose()[0], dtype=float)

            move_robot(2.0, 1.0, math.radians(40.0))
            p1 = pose_of(cam)
            rel1 = relative(cam, base_path)
            ang1 = forward_angle_deg(cam)
            b1 = (pose_of(base_path) or (None, None))[0]

            robot_moved = float(np.linalg.norm(b1 - b0)) if b0 is not None else 0.0
            cam_moved = float(np.linalg.norm(p1[0] - cam0))
            # Ground-truth motion, so a stale USD read is distinguishable from a
            # camera that genuinely failed to follow the robot.
            gt_moved = float(np.linalg.norm(np.asarray(robot.pose()[0]) - gt0))
            drift = (float(np.linalg.norm(rel1 - rel0))
                     if (rel0 is not None and rel1 is not None) else None)

            attached = drift is not None and drift <= ATTACH_DRIFT_TOL_M
            moved_with_robot = cam_moved >= MIN_ROBOT_MOTION_M
            forward = (ang0 is not None and ang0 <= FORWARD_TOL_DEG
                       and ang1 is not None and ang1 <= FORWARD_TOL_DEG)
            inside = float(np.linalg.norm(cam0 - b0)) < 1e-6 if b0 is not None else False

            checks = {
                "camera_exists": True,
                "attached_to_robot": bool(attached),
                "moves_with_robot": bool(moved_with_robot),
                "faces_robot_forward": bool(forward),
                "not_world_fixed": bool(cam_moved > 1e-6),
                "not_coincident_with_base": bool(not inside),
            }
            move_robot(0.0, 0.0, 0.0)   # restore
            return {
                "exists": True, "checks": checks,
                "relative_drift_m": drift,
                "camera_world_moved_m": cam_moved,
                "robot_world_moved_m": robot_moved,
                "robot_ground_truth_moved_m": gt_moved,
                "usd_readback_is_live": bool(robot_moved > 1e-6 or gt_moved <= 1e-6),
                "forward_angle_deg_before": ang0,
                "forward_angle_deg_after": ang1,
                "verdict": "PASS" if all(checks.values()) else "FAIL",
                "failed": [k for k, v in checks.items() if not v],
            }

        # ---- the real camera ------------------------------------------------
        rec["camera_prim"] = cam_path
        prim = stage.GetPrimAtPath(cam_path)
        rec["camera_exists"] = bool(prim and prim.IsValid())
        if prim and prim.IsValid():
            parent = prim.GetParent()
            rec["camera_parent"] = str(parent.GetPath()) if parent else None
            m = world_of(cam_path)
            t = m.ExtractTranslation()
            rec["camera_world_translation"] = [float(t[0]), float(t[1]), float(t[2])]
            oa = optical_axis(cam_path)
            rec["camera_optical_axis_world"] = [float(v) for v in oa] if oa is not None else None
            cam = UsdGeom.Camera(prim)
            if cam:
                with contextlib.suppress(Exception):
                    rec["focal_length"] = float(cam.GetFocalLengthAttr().Get())
                    rec["horizontal_aperture"] = float(cam.GetHorizontalApertureAttr().Get())
        rec["positive"] = evaluate(cam_path)

        # ---- negative controls ---------------------------------------------
        negatives: dict[str, Any] = {}

        # 1. rotate the camera 180 degrees
        if prim and prim.IsValid():
            xf = UsdGeom.Xformable(prim)
            saved = xf.GetXformOpOrderAttr().Get()
            xf.ClearXformOpOrder()
            xf.AddRotateYOp().Set(180.0)
            for _ in range(2):
                sim.step(render=False)
            xcache.Clear()
            negatives["rotated_180"] = evaluate(cam_path)
            xf.ClearXformOpOrder()
            if saved:
                with contextlib.suppress(Exception):
                    xf.GetXformOpOrderAttr().Set(saved)
            for _ in range(2):
                sim.step(render=False)
            xcache.Clear()

        # 2. a world-fixed camera that is not parented to the robot
        world_cam_path = "/World/DetachedCamera"
        wc = UsdGeom.Camera.Define(stage, world_cam_path)
        UsdGeom.Xformable(wc).AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.28))
        for _ in range(2):
            sim.step(render=False)
        xcache.Clear()
        negatives["detached_world_fixed"] = evaluate(world_cam_path)

        # 3. the wrong prim offered as the collection camera
        negatives["wrong_prim"] = evaluate("/World/Robot/lidar_link")

        rec["negative_controls"] = negatives
        rec["negative_controls_all_rejected"] = all(
            n.get("verdict") == "FAIL" for n in negatives.values())

        if not rec["negative_controls_all_rejected"]:
            rec["G7_CAMERA"] = "CAMERA_INSTRUMENT_REVIEW_REQUIRED"
            rec["g7_reason"] = ("a negative control passed; the gate cannot detect the failure "
                               "it claims to detect, so collection must not proceed")
        elif rec["positive"].get("verdict") == "PASS":
            rec["G7_CAMERA"] = "PASS"
            rec["g7_reason"] = "camera is attached, moves with the robot and faces forward"
        else:
            rec["G7_CAMERA"] = "FAIL"
            rec["g7_reason"] = f"failed checks: {rec['positive'].get('failed')}"

    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-3000:]
        rec["G7_CAMERA"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=(
            "check", "artifact_semantics", "G7_CAMERA"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
