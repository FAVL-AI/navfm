"""Wheel-actuated physics qualification; pose is read only after initial spawn."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from itertools import pairwise
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--robot", required=True)
    p.add_argument(
        "--friction", type=float, default=-1, help="negative preserves asset/default material"
    )
    p.add_argument("--yaw-gain", type=float, default=1)
    p.add_argument("--analytic-colliders", action="store_true")
    p.add_argument("--acceleration-drive", action="store_true")
    p.add_argument("--sphere-wheels", action="store_true")
    p.add_argument("--mixed-yaw-gain", type=float, default=1.0)
    p.add_argument("--bounded-policy-envelope", action="store_true")
    a = p.parse_args()
    if a.out.exists() or a.out.resolve().is_relative_to(REPO):
        p.error("new external output required")
    a.out.mkdir(parents=True)
    result = {
        "status": "RUNNING",
        "scope": "ARTICULATED_ENGINEERING",
        "acceptance": {
            "steady_v_absolute_error_m_s": 0.05,
            "steady_w_absolute_error_rad_s": 0.15,
            "wheel_rmse_rad_s": 0.5,
            "stop_distance_m": 0.05,
            "residual_v_m_s": 0.01,
            "residual_w_rad_s": 0.03,
            "reason": "25% of 0.2m/s and 0.6rad/s engineering commands; 5cm stop margin; residual measured last0.5s of2s stop. Not hardware calibration.",
        },
        "physics_dt": 1 / 120,
        "friction_requested": a.friction,
        "yaw_gain": a.yaw_gain,
        "analytic_colliders": a.analytic_colliders,
        "acceleration_drive": a.acceleration_drive,
        "sphere_wheels": a.sphere_wheels,
        "mixed_yaw_gain": a.mixed_yaw_gain,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "episodes": [],
    }
    (a.out / "source.py").write_bytes(Path(__file__).read_bytes())

    def save():
        (a.out / "qualification.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )

    save()
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True})
    try:
        import dataclasses

        import omni.physx
        import omni.usd
        from isaacsim.core.api import SimulationContext
        from isaacsim.core.utils import stage
        from pxr import Gf, PhysicsSchemaTools, PhysxSchema, UsdGeom, UsdPhysics, UsdShade

        from navfm.isaac.robot import M3PRO, SimRobot

        stage.create_new_stage()
        usd = omni.usd.get_context().get_stage()

        def box(name, xyz, size):
            q = UsdGeom.Cube.Define(usd, "/World/" + name)
            q.CreateSizeAttr(1.0)
            x = UsdGeom.XformCommonAPI(q)
            x.SetTranslate(Gf.Vec3d(*xyz))
            x.SetScale(Gf.Vec3f(*size))
            UsdPhysics.CollisionAPI.Apply(q.GetPrim())

        box("Floor", (0, 0, -0.05), (20, 20, 0.1))
        # Positive control starts at x=0 and drives into this wall; free tests start x=-3.
        box("ContactWall", (1.0, 0, 0.3), (0.1, 2, 0.6))
        stage.add_reference_to_stage(a.robot, "/World/Robot")
        drives = []
        if a.analytic_colliders:
            # Prospective analytic collision geometry; existing visual asset unchanged.
            for link in ["base_link", "fl_wheel", "fr_wheel", "rl_wheel", "rr_wheel"]:
                root = "/World/Robot/" + link
                usd.OverridePrim(root + "/collisions").SetActive(False)
                if link == "base_link":
                    shape = UsdGeom.Cube.Define(usd, root + "/QualifiedCollision")
                    shape.CreateSizeAttr(1.0)
                    x = UsdGeom.XformCommonAPI(shape)
                    x.SetScale(Gf.Vec3f(0.29, 0.235, 0.08))
                    x.SetTranslate(Gf.Vec3d(0, 0, 0.04))
                else:
                    shape = (
                        UsdGeom.Sphere.Define(usd, root + "/QualifiedCollision")
                        if a.sphere_wheels
                        else UsdGeom.Cylinder.Define(usd, root + "/QualifiedCollision")
                    )
                    shape.CreateRadiusAttr(0.04)
                    if not a.sphere_wheels:
                        shape.CreateHeightAttr(0.025)
                        shape.CreateAxisAttr("Y")
                UsdPhysics.CollisionAPI.Apply(shape.GetPrim())

        material = None
        if a.friction >= 0:
            material = UsdShade.Material.Define(usd, "/World/WheelMaterial")
            m = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
            m.CreateStaticFrictionAttr(a.friction)
            m.CreateDynamicFrictionAttr(a.friction)
            m.CreateRestitutionAttr(0.0)
        for q in usd.Traverse():
            path = str(q.GetPath())
            if path.startswith("/World/Robot"):
                if q.HasAPI(UsdPhysics.RigidBodyAPI):
                    PhysxSchema.PhysxContactReportAPI.Apply(q).CreateThresholdAttr(0.0)
                if material and q.HasAPI(UsdPhysics.CollisionAPI) and "wheel" in path:
                    UsdShade.MaterialBindingAPI.Apply(q).Bind(material, materialPurpose="physics")
                if q.IsA(UsdPhysics.RevoluteJoint):
                    d = UsdPhysics.DriveAPI.Get(q, "angular")
                    before = [d.GetStiffnessAttr().Get(), d.GetDampingAttr().Get()]
                    d.GetStiffnessAttr().Set(0.0)
                    d.GetDampingAttr().Set(1000.0 if a.acceleration_drive else 10.0)
                    if a.acceleration_drive:
                        d.GetTypeAttr().Set("acceleration")
                    drives.append(
                        {
                            "path": path,
                            "asset": before,
                            "observed": [d.GetStiffnessAttr().Get(), d.GetDampingAttr().Get()],
                            "axis": UsdPhysics.RevoluteJoint(q).GetAxisAttr().Get(),
                        }
                    )
        sim = SimulationContext(stage_units_in_meters=1, physics_dt=1 / 120, rendering_dt=1 / 120)
        sim.initialize_physics()
        sim.play()
        robot = SimRobot(app, dataclasses.replace(M3PRO, usd_path=a.robot))
        robot._attach()
        robot._articulation.initialize()
        names = list(robot._articulation.dof_names)
        idx = [
            next(i for i, n in enumerate(names) if n.startswith(s))
            for s in ["fl", "fr", "rl", "rr"]
        ]
        result.update(
            drives=drives,
            dof_names=names,
            wheel_indices=idx,
            geometry={"radius": 0.04, "k": 0.1625},
            robot_sha256=hashlib.sha256(Path(a.robot).read_bytes()).hexdigest(),
        )
        contacts = []

        def contact(headers, data):
            for h in headers:
                paths = [str(PhysicsSchemaTools.intToSdfPath(v)) for v in [h.actor0, h.actor1]]
                if any("/Robot/" in v for v in paths) and "/World/ContactWall" in paths:
                    contacts.append(
                        {"time": float(sim.current_time), "paths": paths, "type": int(h.type)}
                    )

        subscription = omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(
            contact
        )

        def drive(v, w):
            gain = a.yaw_gain if abs(v) < 1e-6 else a.mixed_yaw_gain
            target = np.zeros((1, len(names)), np.float32)
            target[0, idx] = [
                (v - 0.1625 * w * gain) / 0.04,
                (v + 0.1625 * w * gain) / 0.04,
            ] * 2
            robot._articulation.set_joint_velocity_targets(target)
            return target[0, idx]

        cases = [
            ("forward", 0.2, 0, 3),
            ("left", 0, 0.6, 3),
            ("right", 0, -0.6, 3),
            ("combined_left", 0.2, 0.6, 3),
            ("combined_right", 0.2, -0.6, 3),
            ("policy_left", 0.1, 0.4, 3),
            ("policy_right", 0.1, -0.4, 3),
            ("collision_positive", 0.2, 0, 7),
        ]
        if a.bounded_policy_envelope:
            cases = [
                ("forward", 0.1, 0, 3),
                ("left", 0, 0.4, 3),
                ("right", 0, -0.4, 3),
                ("combined_left", 0.1, 0.4, 3),
                ("combined_right", 0.1, -0.4, 3),
                ("collision_positive", 0.1, 0, 12),
            ]
            result["qualified_command_envelope"] = {
                "max_v": 0.1,
                "max_w": 0.4,
                "scope": "sampled commands only; outside envelope failures retained",
            }
        for name, v, w, seconds in cases:
            robot.teleport(
                (0.5 if name == "collision_positive" else -3, 0), 0
            )  # initial condition only
            drive(0, 0)
            for _ in range(120):
                sim.step(render=False)
            contacts.clear()
            rows = []
            for i in range(int((seconds + 2) * 120)):
                commanded = (v, w) if i < int(seconds * 120) else (0, 0)
                target = drive(*commanded)
                sim.step(render=False)
                xy, yaw = robot.pose()
                vel = np.asarray(robot._articulation.get_velocities()).reshape(-1, 6)[0]
                c, s = math.cos(yaw), math.sin(yaw)
                body_v = c * vel[0] + s * vel[1]
                joints = np.asarray(robot._articulation.get_joint_velocities()).reshape(
                    -1, len(names)
                )[0, idx]
                rows.append(
                    {
                        "t": float(sim.current_time),
                        "xy": xy.tolist(),
                        "yaw": yaw,
                        "v": float(body_v),
                        "w": float(vel[5]),
                        "target": target.tolist(),
                        "wheel": joints.tolist(),
                    }
                )
            steady = rows[120 : int(seconds * 120)]
            tail = rows[-60:]
            measured_v = float(np.mean([r["v"] for r in steady]))
            measured_w = float(np.mean([r["w"] for r in steady]))
            wheelerr = float(
                np.sqrt(np.mean([(np.asarray(r["target"]) - r["wheel"]) ** 2 for r in steady]))
            )
            stoprows = rows[int(seconds * 120) - 1 :]
            stopdist = float(sum(math.dist(x["xy"], y["xy"]) for x, y in pairwise(stoprows)))
            rv = max(abs(r["v"]) for r in tail)
            rw = max(abs(r["w"]) for r in tail)
            checks = {
                "v_tracking": abs(measured_v - v) <= 0.05,
                "w_tracking": abs(measured_w - w) <= 0.15,
                "wheel_tracking": wheelerr <= 0.5,
                "stopping_distance": stopdist <= 0.05,
                "residual_v": rv <= 0.01,
                "residual_w": rw <= 0.03,
                "collision_detector": bool(contacts)
                if name == "collision_positive"
                else not contacts,
            }
            if name == "collision_positive":
                checks.pop("v_tracking")
                checks.pop("w_tracking")
            ep = {
                "name": name,
                "command": [v, w],
                "steady_v": measured_v,
                "steady_w": measured_w,
                "wheel_rmse": wheelerr,
                "stop_distance": stopdist,
                "residual_v": rv,
                "residual_w": rw,
                "contacts": contacts.copy(),
                "checks": checks,
                "pass": all(checks.values()),
                "samples": len(rows),
            }
            (a.out / (name + ".json")).write_text(json.dumps(rows, allow_nan=False))
            result["episodes"].append(ep)
            save()
            print(
                name,
                {k: ep[k] for k in ["steady_v", "steady_w", "stop_distance", "pass"]},
                flush=True,
            )
        result["status"] = "PASS" if all(e["pass"] for e in result["episodes"]) else "FAIL"
        result["contact_subscription_active"] = subscription is not None
        usd.GetRootLayer().Export(str(a.out / "fixture.usda"))
        save()
    except Exception as e:
        result.update(status="ERROR", error=f"{type(e).__name__}: {e}")
        save()
        raise
    finally:
        app.close()


if __name__ == "__main__":
    main()
