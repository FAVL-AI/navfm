#!/usr/bin/env python3
"""Supervisor-authorised two-trajectory compatibility pilot: collection.

    ~/miniforge3/envs/isaac/bin/python scripts/pilot_collect.py --out ~/navfm-data/pilot

Collects **exactly two** diagnostic trajectories in Isaac Sim 5.1 using a cube
proxy in `simple_room`, and writes them in the Option 1 format. Authorised by
the narrow exception recorded in `docs/WORKFLOW.md`; it does not satisfy G1 or
G2, does not validate the M3 PRO model, and the trajectories are not admitted to
training, validation, benchmarking or performance claims.

The pilot tests the **file contract**, not robot dynamics, geometry or
navigation. The proxy is therefore driven kinematically along a scripted path:
introducing a controller, a planner or physics would add failure modes that have
nothing to do with the question being asked, and the question is whether data
this project collects is accepted by the unchanged ViNT data path.

    trajectory 1 -- mostly forward motion, small yaw drift
    trajectory 2 -- forward, one clear 90 degree turn, forward

Yaw is recorded unwrapped and continuous by construction: it is integrated from
the commanded rate rather than recovered from a quaternion, so it never wraps
and finding F1 cannot apply to it. Poses are the commanded poses, which for a
kinematic proxy are the achieved poses -- there is no controller error to
account for because there is no controller.

Each frame is captured after `IsaacApp.step()` returns, which blocks until the
renderer has finished, so the image and the pose refer to the same instant.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

COLLECTION_VERSION = "pilot_v1"
ROBOT_PATH = "/World/pilot_robot"
CAMERA_PATH = f"{ROBOT_PATH}/camera"


def _plan(kind: str, n: int, dt: float) -> list[tuple[float, float, float]]:
    """Commanded (x, y, yaw) per frame. Yaw integrated, never wrapped."""
    v = 0.35  # m/s
    x = y = yaw = 0.0
    out = []
    for i in range(n):
        # forward: a small constant rate keeps yaw non-degenerate without
        # turning -- a yaw column of exact zeros would let a broken yaw path
        # pass unnoticed. turn: one clear turn in the middle third, so position
        # and yaw both move.
        omega = 0.05 if kind == "forward" else (0.9 if (n // 3) <= i < (2 * n // 3) else 0.0)
        yaw += omega * dt
        x += v * math.cos(yaw) * dt
        y += v * math.sin(yaw) * dt
        out.append((x, y, yaw))
    return out


def _build_scene(app, assets_root: str, resolution: tuple[int, int]):
    """simple_room, a cube proxy, and a camera rigidly attached to it."""
    import omni.usd
    from pxr import Gf, UsdGeom

    app.open_stage(assets_root + "/Isaac/Environments/Simple_Room/simple_room.usd")
    stage = omni.usd.get_context().get_stage()

    xform = UsdGeom.Xform.Define(stage, ROBOT_PATH)
    # One matrix op, set every frame. Mixing translate/rotate ops invites an
    # ordering bug that shows up as a subtly wrong yaw rather than a crash.
    xform.ClearXformOpOrder()
    op = xform.AddTransformOp()

    body = UsdGeom.Cube.Define(stage, f"{ROBOT_PATH}/body")
    body.GetSizeAttr().Set(1.0)
    UsdGeom.Xformable(body).AddScaleOp().Set(Gf.Vec3f(0.18, 0.14, 0.09))

    cam = UsdGeom.Camera.Define(stage, CAMERA_PATH)
    # Forward-facing: USD cameras look down -Z, the robot drives along +X, so
    # rotate -90 about Y then -90 about X to put -Z onto +X with Z up.
    cam_xf = UsdGeom.Xformable(cam)
    cam_xf.AddTranslateOp().Set(Gf.Vec3d(0.10, 0.0, 0.12))
    cam_xf.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, -90.0))
    cam.GetFocalLengthAttr().Set(18.0)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.02, 100.0))

    from isaacsim.sensors.camera import Camera

    camera = Camera(prim_path=CAMERA_PATH, resolution=resolution)
    return op, camera


def _set_pose(op, x: float, y: float, yaw: float) -> None:
    from pxr import Gf

    m = Gf.Matrix4d()
    m.SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), math.degrees(yaw)))
    m.SetTranslateOnly(Gf.Vec3d(x, y, 0.12))
    op.Set(m)


def _write_option1(out_dir: Path, frames: list, poses: list, meta: dict) -> None:
    """Numbered RGB images plus traj_data.pkl with exactly position and yaw."""
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    for i, rgb in enumerate(frames):
        Image.fromarray(rgb[:, :, :3].astype(np.uint8)).save(out_dir / f"{i}.jpg", quality=95)

    position = np.asarray([[p[0], p[1]] for p in poses], dtype=np.float64)
    yaw = np.asarray([p[2] for p in poses], dtype=np.float64)
    assert position.shape == (len(frames), 2) and yaw.shape == (len(frames),)
    with open(out_dir / "traj_data.pkl", "wb") as fh:
        # Exactly two keys. The contract admits no others; provenance goes in
        # metadata.json beside it, which the reference loader never reads.
        pickle.dump({"position": position, "yaw": yaw}, fh)
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--hz", type=float, default=12.0)
    p.add_argument("--width", type=int, default=320)
    p.add_argument("--height", type=int, default=240)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)

    out_root = Path(args.out).expanduser()
    dt = 1.0 / args.hz

    from navfm.isaac.app import IsaacApp, SimConfig

    plans = [("pilot_0001", "forward"), ("pilot_0002", "turn")]
    written = []

    with IsaacApp(
        SimConfig(headless=True, hz=args.hz, seed=args.seed, resolution=(args.width, args.height))
    ) as app:
        assets_root = app.assets_root()
        op, camera = _build_scene(app, assets_root, (args.width, args.height))
        app.play()
        camera.initialize()
        app.warmup()

        for name, kind in plans:
            t0 = time.time()
            poses = _plan(kind, args.frames, dt)
            frames = []
            for x, y, yaw in poses:
                _set_pose(op, x, y, yaw)
                app.step()
                rgb = camera.get_rgba()
                if rgb is None or rgb.size == 0:
                    raise RuntimeError(
                        f"{name}: camera returned no image at frame {len(frames)}; the "
                        f"capture is not synchronised with the step"
                    )
                frames.append(np.asarray(rgb))
            meta = {
                "trajectory_id": name,
                "source": "Isaac Sim 5.1 simple_room, cube proxy",
                "scene_id": "simple_room",
                "robot_id": "cube_proxy",
                "camera_id": "pilot_forward_rgb",
                "controller_id": "scripted_kinematic",
                "motion": kind,
                "frame_count": len(frames),
                "image_width": args.width,
                "image_height": args.height,
                "hz": args.hz,
                "seed": args.seed,
                "collection_version": COLLECTION_VERSION,
                "collected_by_project": True,
                "pilot_evidence": True,
                "admitted_for_training": False,
                "note": (
                    "Supervisor-authorised two-trajectory compatibility pilot. Cube "
                    "proxy, format compatibility only. Does not satisfy G1 or G2 and "
                    "is not admitted for training, validation or benchmarking."
                ),
            }
            _write_option1(out_root / name, frames, poses, meta)
            written.append(name)
            print(
                f"{name}: {len(frames)} frames, "
                f"yaw {poses[0][2]:+.3f} -> {poses[-1][2]:+.3f} rad, "
                f"{time.time() - t0:.1f}s",
                flush=True,
            )

    print(f"\nwrote {len(written)} trajectories to {out_root}")
    print("Diagnostic pilot data. Not admitted for training, validation or benchmarking.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
