"""Finite kinematic camera acquisition, never robot navigation or plant qualification."""

import argparse
import json
import math
import pickle
from pathlib import Path

from development_qualification_contracts_v1 import sha
from offline_evaluation_contracts_v1 import atomic_snapshot as write
from prospective_data_contracts_v1 import (
    float32_position,
    frame_integrity,
    qualification_poses,
    safe_raw,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--qualify", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    if cfg["prospective"]["recipe"] != "two-static-rooms-v1":
        raise ValueError("capture recipe drift")
    spec = json.loads(args.spec.read_text())
    report = dict(status="STARTED", mode="qualify" if args.qualify else "acquire", frames=[])
    write(args.out / "capture.json", safe_raw(report))
    try:
        import numpy as np
        from PIL import Image

        from navfm.isaac.app import IsaacApp, SimConfig

        with IsaacApp(
            SimConfig(
                hz=12, resolution=(320, 240), rt_subframes=1, physics_substeps=1, warmup_frames=8
            )
        ) as sim:
            import omni.usd
            from isaacsim.sensors.camera import Camera
            from pxr import Gf, UsdGeom, UsdLux

            stage = omni.usd.get_context().get_stage()
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)
            layouts = spec["layouts"]
            for li, layout in enumerate(layouts):
                for index, values in enumerate(layout["objects"] + [[0, 0, -0.05, 6, 4, 0.1]]):
                    cube = UsdGeom.Cube.Define(stage, f"/World/Layout{li}/Box{index}")
                    cube.GetSizeAttr().Set(1.0)
                    cube.AddTranslateOp().Set(Gf.Vec3d(values[0] + 100 * li, *values[1:3]))
                    cube.AddScaleOp().Set(Gf.Vec3d(*values[3:]))
                    cube.GetDisplayColorAttr().Set([Gf.Vec3f(0.5, 0.5, 0.5)])
            light = UsdLux.DomeLight.Define(stage, "/World/Light")
            light.GetIntensityAttr().Set(1000.0)
            cam = Camera(prim_path="/World/Camera", resolution=(320, 240))
            if sim._version != (5, 0):
                raise ValueError("only pinned 5.x Camera acquisition admitted")
            sim._sim_manager.initialize_physics()
            sim.play()
            cam.initialize()
            cam.set_focal_length(
                cam.get_horizontal_aperture() / (2 * math.tan(math.radians(68) / 2))
            )
            sim.warmup()
            previous = None
            for li, layout in enumerate(layouts):
                for ri, route in enumerate(layout["routes"]):
                    route_id = (
                        f"technical_fixture_layout{li}_route{ri}" if args.qualify else route["id"]
                    )
                    directory = args.out / "data" / route_id
                    directory.mkdir(parents=True)
                    poses = (
                        qualification_poses(li, ri, route["poses"])
                        if args.qualify
                        else route["poses"]
                    )
                    positions, yaws, times = [], [], []
                    for tick, (x, y, yaw) in enumerate(poses):
                        x += 100 * li
                        rgba = None
                        position = [x + 0.2 * math.cos(yaw), y + 0.2 * math.sin(yaw), 0.55]
                        quat = np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])
                        candidate = dict(
                            route=route_id,
                            tick=tick,
                            teacher_pose=[x, y, yaw],
                            requested_camera_position=position,
                            represented_float32_position=float32_position(position),
                            requested_camera_quaternion=quat.tolist(),
                            pose_author_time=sim.sim_time(),
                            status="STARTED",
                        )
                        report["frames"].append(candidate)
                        write(args.out / "capture.json", safe_raw(report))
                        try:
                            cam.set_world_pose(np.array(position), quat, camera_axes="world")
                            candidate["hold_start_time"] = sim.sim_time()
                            for _ in range(4):
                                sim.step()
                            candidate["hold_end_time"] = sim.sim_time()
                            frame = cam.get_current_frame(clone=True)
                            rgba = np.asarray(frame.get("rgb"))
                            candidate.update(
                                camera={
                                    k: frame.get(k) for k in ("rendering_time", "rendering_frame")
                                },
                                rgb_shape=list(rgba.shape),
                                rgb_dtype=str(rgba.dtype),
                            )
                            actual, actual_quat = cam.get_world_pose(camera_axes="world")
                            candidate.update(
                                actual_camera_position=actual.tolist(),
                                actual_camera_quaternion=actual_quat.tolist(),
                                original_world_position_residual=(
                                    actual - np.asarray(position)
                                ).tolist(),
                            )
                            write(args.out / "capture.json", safe_raw(report))
                            previous = frame_integrity(
                                frame,
                                previous,
                                actual.tolist(),
                                position,
                                rgba.shape,
                                candidate["pose_author_time"],
                                candidate["hold_end_time"],
                            )
                            if not np.isfinite(rgba).all() or float(rgba[:, :, :3].std()) < 5:
                                raise ValueError("nonfinite/unusable RGB")
                            if not np.allclose(
                                actual_quat, quat, rtol=0, atol=1e-6
                            ) and not np.allclose(actual_quat, -quat, rtol=0, atol=1e-6):
                                raise ValueError("camera orientation mismatch")
                            image = directory / f"{tick}.jpg"
                            Image.fromarray(rgba[:, :, :3].astype(np.uint8)).save(image, quality=95)
                            candidate.update(status="PASS", sha256=sha(image))
                        except BaseException as exc:
                            candidate.update(
                                status="FAIL",
                                failure_reason=str(exc)
                                if isinstance(exc, ValueError)
                                else type(exc).__name__,
                            )
                            if rgba is not None and not rgba.dtype.hasobject:
                                np.save(directory / f"{tick}_failed.npy", rgba, allow_pickle=False)
                            raise
                        finally:
                            write(args.out / "capture.json", safe_raw(report))
                        positions.append([x, y])
                        yaws.append(yaw)
                        times.append(frame["rendering_time"])
                        write(args.out / "capture.json", safe_raw(report))
                    with (directory / "traj_data.pkl").open("wb") as stream:
                        pickle.dump(
                            dict(
                                position=np.asarray(positions),
                                yaw=np.asarray(yaws),
                                timestamp=np.asarray(times),
                            ),
                            stream,
                        )
            report["status"] = "PASS"
    except BaseException as exc:
        report.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        write(args.out / "capture.json", safe_raw(report))


if __name__ == "__main__":
    main()
