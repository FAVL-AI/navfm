"""Acceptance test: is the capture camera rigidly mounted on the robot, or a
world/spectator camera?

Three independent probes. A world camera passes none of them; a robot-mounted
camera passes all three.

  A. structural -- the camera prim's parent is the robot prim
  B. extrinsic  -- the camera's LOCAL transform is constant during capture
  C. behavioural -- rotate the robot +90 deg in place, no translation. The image
     must change. If it does not, the camera is not following the robot.
"""

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, "/home/favl/projects/navfm/src")
from navfm.isaac.app import IsaacApp, SimConfig

ROBOT = "/World/pilot_robot"
CAM = f"{ROBOT}/camera"

with IsaacApp(SimConfig(headless=True, hz=12.0, resolution=(320, 240))) as app:
    import math

    import omni.usd
    from pxr import Gf, UsdGeom

    app.open_stage(app.assets_root() + "/Isaac/Environments/Simple_Room/simple_room.usd")
    stage = omni.usd.get_context().get_stage()
    xf = UsdGeom.Xform.Define(stage, ROBOT)
    xf.ClearXformOpOrder()
    op = xf.AddTransformOp()
    body = UsdGeom.Cube.Define(stage, f"{ROBOT}/body")
    body.GetSizeAttr().Set(1.0)
    UsdGeom.Xformable(body).AddScaleOp().Set(Gf.Vec3f(0.18, 0.14, 0.09))
    cam = UsdGeom.Camera.Define(stage, CAM)
    cxf = UsdGeom.Xformable(cam)
    cxf.AddTranslateOp().Set(Gf.Vec3d(0.10, 0, 0.12))
    cxf.AddRotateXYZOp().Set(Gf.Vec3f(90, 0, -90))
    cam.GetFocalLengthAttr().Set(18.0)

    from isaacsim.sensors.camera import Camera

    camera = Camera(prim_path=CAM, resolution=(320, 240))
    app.play()
    camera.initialize()
    app.warmup()

    # A: structural
    cam_prim = stage.GetPrimAtPath(CAM)
    parent = cam_prim.GetParent().GetPath().pathString
    R = {"camera_parent": parent, "structural_pass": parent == ROBOT}

    def local_xform():
        return UsdGeom.Xformable(cam_prim).GetLocalTransformation()

    def shoot(x, y, yaw):
        m = Gf.Matrix4d()
        m.SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), math.degrees(yaw)))
        m.SetTranslateOnly(Gf.Vec3d(x, y, 0.12))
        op.Set(m)
        for _ in range(3):
            app.step()
        return np.asarray(camera.get_rgba())[:, :, :3].astype(float), local_xform()

    img0, lx0 = shoot(0.0, 0.0, 0.0)
    img90, lx90 = shoot(0.0, 0.0, math.pi / 2)  # rotate in place, NO translation
    imgT, lxT = shoot(0.6, 0.0, 0.0)  # translate, no rotation

    # B: extrinsic constancy
    same = lx0 == lx90 == lxT
    R["extrinsics_constant"] = bool(same)

    # C: behavioural
    d_rot = float(np.abs(img0 - img90).mean())
    d_tr = float(np.abs(img0 - imgT).mean())
    R["mean_abs_dpix_rotate_90deg_in_place"] = round(d_rot, 3)
    R["mean_abs_dpix_translate_0p6m"] = round(d_tr, 3)
    R["rotation_changes_view"] = d_rot > 5.0
    R["translation_changes_view"] = d_tr > 5.0
    R["egocentric_verdict"] = (
        "PASS" if (parent == ROBOT and same and d_rot > 5.0 and d_tr > 5.0) else "FAIL"
    )
    out = sys.argv[1] if len(sys.argv) > 1 else "egocentric_verification.json"
    pathlib.Path(out).write_text(json.dumps(R, indent=2, sort_keys=True) + "\n")
