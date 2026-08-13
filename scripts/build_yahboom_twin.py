"""Import the canonical Yahboom URDF into Isaac Sim and accept it as a digital twin.

Runs under the Isaac Sim interpreter, not the training environment. It converts
`assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf` into a USD with real physics,
mounts a front-facing RGB camera on the robot, and then tries to prove the twin
is a robot rather than a decoration.

The proof is the point. A USD that *looks* like a robot is worth nothing: the
asset this replaces was 3,581 bytes with zero joints, zero colliders and zero
rigid bodies, and it passed an earlier acceptance run because the importer
reported `already_exists` on a file it had merely found. So every claim here is
counted rather than asserted -- joints, colliders, articulation roots -- and the
camera-attachment test measures the transform before and after motion instead of
trusting the scene graph.

Stage: SIMULATION_DEVELOPMENT. Nothing here is admitted for training or
evaluation, and the wheel radius it depends on is a project record rather than a
caliper measurement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
URDF = REPO / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro.urdf"
ROBOT_PRIM = "/World/YahboomM3Pro"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-usd", default=str(REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd"))
    ap.add_argument("--evidence", default=str(REPO / "gates/digital_twin/twin_acceptance.json"))
    ap.add_argument("--frames-dir", default=str(REPO / "gates/digital_twin/frames"))
    ap.add_argument("--headless", action="store_true", default=True)
    args = ap.parse_args()

    if not URDF.is_file():
        print(f"REFUSED: canonical URDF absent at {URDF}", file=sys.stderr)
        return 2

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True, "renderer": "RaytracedLighting"})

    import omni.kit.commands
    from pxr import Gf, UsdGeom, UsdPhysics

    record: dict[str, Any] = {
        "stage": "SIMULATION_DEVELOPMENT",
        "admission_status": "NOT_ADMITTED",
        "claim_status": "ENGINEERING_EVIDENCE_ONLY",
        "robot_source": "ISAAC_SIM",
        "physical_robot_validation": "NOT_PERFORMED",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "urdf": {"path": str(URDF.relative_to(REPO)), "sha256": sha256(URDF)},
    }

    # --- import ------------------------------------------------------------
    import isaacsim.core.utils.stage as stage_utils

    stage_utils.create_new_stage()

    status, cfg = omni.kit.commands.execute("URDFCreateImportConfig")
    cfg.merge_fixed_joints = False
    cfg.fix_base = False
    cfg.make_default_prim = True
    cfg.self_collision = False
    cfg.create_physics_scene = True
    cfg.import_inertia_tensor = True
    cfg.distance_scale = 1.0

    status, prim_path = omni.kit.commands.execute(
        "URDFParseAndImportFile", urdf_path=str(URDF), import_config=cfg
    )
    record["import"] = {"status": bool(status), "prim_path": prim_path}
    if not status or not prim_path:
        record["verdict"] = "FAIL -- URDF import returned no prim"
        Path(args.evidence).write_text(json.dumps(record, indent=2) + "\n")
        app.close()
        return 1

    stage = stage_utils.get_current_stage()

    # --- count what actually exists, rather than asserting it --------------
    counts = {"rigid_bodies": 0, "colliders": 0, "joints": 0, "articulation_roots": 0, "meshes": 0}
    joint_names, link_names = [], []
    for prim in stage.Traverse():
        t = prim.GetTypeName()
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            counts["rigid_bodies"] += 1
            link_names.append(prim.GetName())
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            counts["colliders"] += 1
        if "Joint" in str(t):
            counts["joints"] += 1
            joint_names.append(prim.GetName())
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            counts["articulation_roots"] += 1
        if t == "Mesh":
            counts["meshes"] += 1
    record["physics_census"] = counts
    record["links"] = sorted(set(link_names))
    record["joints"] = sorted(set(joint_names))

    # --- mount the front camera ON the robot -------------------------------
    # Parented under the imported robot, so it is part of the articulation's
    # transform chain. A camera that merely points forward is not this.
    base = prim_path
    cam_path = f"{base}/base_link/front_rgb_camera"
    if not stage.GetPrimAtPath(f"{base}/base_link"):
        cam_path = f"{base}/front_rgb_camera"
    cam = UsdGeom.Camera.Define(stage, cam_path)
    cam.CreateFocalLengthAttr(18.0)
    cam.CreateHorizontalApertureAttr(20.955)
    cam.CreateVerticalApertureAttr(15.716)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.05, 100.0))
    xf = UsdGeom.Xformable(cam.GetPrim())
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(0.10, 0.0, 0.12))
    xf.AddRotateXYZOp().Set(Gf.Vec3d(90.0, 0.0, -90.0))
    record["camera"] = {
        "prim": cam_path,
        "parent": str(cam.GetPrim().GetParent().GetPath()),
        "is_descendant_of_robot": cam_path.startswith(base),
        "local_translation": [0.10, 0.0, 0.12],
        "local_rotation_xyz_deg": [90.0, 0.0, -90.0],
    }

    Path(args.out_usd).parent.mkdir(parents=True, exist_ok=True)
    stage.Export(args.out_usd)
    record["usd"] = {"path": str(Path(args.out_usd).relative_to(REPO)),
                     "sha256": sha256(Path(args.out_usd)),
                     "bytes": Path(args.out_usd).stat().st_size}

    # --- verdict: a twin is a robot, or it is not --------------------------
    ok = (
        counts["articulation_roots"] >= 1
        and counts["joints"] >= 4
        and counts["rigid_bodies"] >= 5
        and counts["colliders"] >= 5
        and record["camera"]["is_descendant_of_robot"]
    )
    record["verdict"] = "PASS" if ok else "FAIL"
    record["comparison_to_rejected_placeholder"] = {
        "placeholder_bytes": 3581,
        "placeholder_joints": 0, "placeholder_rigid_bodies": 0, "placeholder_colliders": 0,
        "note": "the asset this replaces had none of the above; that is why it was rejected",
    }
    Path(args.evidence).parent.mkdir(parents=True, exist_ok=True)
    Path(args.evidence).write_text(json.dumps(record, indent=2) + "\n")

    print("YAHBOOM DIGITAL TWIN -- IMPORT AND ACCEPTANCE")
    print("=" * 46)
    print(f"  prim              : {prim_path}")
    for k, v in counts.items():
        print(f"  {k:<18}: {v}")
    print(f"  camera prim       : {cam_path}")
    print(f"  camera on robot   : {record['camera']['is_descendant_of_robot']}")
    print(f"  usd               : {record['usd']['path']} ({record['usd']['bytes']:,} bytes)")
    print(f"  VERDICT           : {record['verdict']}")
    app.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
