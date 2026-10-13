"""Finite controller/plant diagnosis; old plant and qualification remain unchanged."""

from __future__ import annotations

import math

from controller_telemetry_v1 import instrument, replace_once

TRIALS = [
    ("reset", 0.05, 0.005),
    ("carry", 0.0, -0.4),
    ("direct", 0.05, -0.005),
    ("reset", 0.0, 0.4),
    ("carry", 0.05, -0.005),
    ("direct", 0.0, 0.4),
    ("reset", 0.05, -0.005),
    ("carry", 0.0, 0.4),
    ("direct", 0.05, 0.005),
    ("reset", 0.0, -0.4),
    ("carry", 0.05, 0.005),
    ("direct", 0.0, -0.4),
]
TICKS = 3120


def info(tick):
    if tick < 120 or tick >= 3000:
        return {"trial": None, "mode": None, "stage": "startup" if tick < 120 else "tail"}
    trial, offset = divmod(tick - 120, 240)
    mode, v, w = TRIALS[trial]
    stage = "rest" if offset < 120 else "conditioning" if offset < 180 else "target"
    return {"trial": trial, "mode": mode, "stage": stage, "offset": offset, "target": [v, w]}


def command(tick):
    state = info(tick)
    if state["stage"] in ("startup", "tail", "rest"):
        return 0.0, 0.0
    v, w = state["target"]
    if state["stage"] == "conditioning":
        return (0.0, 0.0) if state["mode"] == "direct" else (v, -math.copysign(0.4, w))
    return v, w


def target_onset(tick, tracker, robot, sim, mark, preserve):
    state = info(tick)
    if state.get("offset") != 180:
        return
    before = tracker.integral
    if state["mode"] == "reset":
        tracker.reset()
    mark(
        "TARGET_ONSET",
        tick=tick,
        simulation_time=float(sim.current_time),
        diagnostic=state,
        antecedent="rest_start" if state["mode"] == "direct" else "opposite_turn_conditioning",
        integral_before_reset=before,
        integral_after_reset=tracker.integral,
        evaluation_only_pose=preserve(robot.pose()[0].tolist()),
        evaluation_only_orientation_wxyz=preserve(
            robot._articulation.get_world_poses()[1].tolist()
        ),
        evaluation_only_world_velocity=preserve(robot._articulation.get_velocities().tolist()),
        realized_joint_velocity=preserve(robot._articulation.get_joint_velocities().tolist()),
    )


def plant_readback(stage):
    from pxr import UsdPhysics, UsdShade

    drives = []
    for prim in stage.Traverse():
        if str(prim.GetPath()).startswith("/World/Robot") and prim.IsA(UsdPhysics.RevoluteJoint):
            joint = UsdPhysics.RevoluteJoint(prim)
            drive = UsdPhysics.DriveAPI.Get(prim, "angular")
            values = {
                "path": str(prim.GetPath()),
                "axis": joint.GetAxisAttr().Get(),
                "stiffness": drive.GetStiffnessAttr().Get(),
                "damping": drive.GetDampingAttr().Get(),
                "type": drive.GetTypeAttr().Get(),
                "max_force": drive.GetMaxForceAttr().Get(),
                "body0": [str(x) for x in joint.GetBody0Rel().GetTargets()],
                "body1": [str(x) for x in joint.GetBody1Rel().GetTargets()],
            }
            drives.append(values)
    collisions = []
    for link in ["fl_wheel", "fr_wheel", "rl_wheel", "rr_wheel"]:
        prim = stage.GetPrimAtPath("/World/Robot/" + link + "/QualifiedCollision")
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial(
            materialPurpose="physics"
        )
        record = {
            "path": str(prim.GetPath()),
            "active": prim.IsActive(),
            "type": prim.GetTypeName(),
            "radius": prim.GetAttribute("radius").Get(),
            "resolved_material": str(material.GetPath()) if material else None,
            "effective_solver_friction": "UNKNOWN",
        }
        if material:
            api = UsdPhysics.MaterialAPI(material.GetPrim())
            record["material_authored_values"] = {
                name: {"value": attr.Get(), "authored": attr.HasAuthoredValueOpinion()}
                for name, attr in [
                    ("static_friction", api.GetStaticFrictionAttr()),
                    ("dynamic_friction", api.GetDynamicFrictionAttr()),
                ]
            }
        collisions.append(record)
    return {
        "drives": drives,
        "collisions": collisions,
        "scope": "USD stage readback; unbound solver defaults remain unknown",
    }


def prepare(source):
    begin = source.index("def command(tick):")
    end = source.index("\ndef main():", begin)
    source = (
        source[:begin]
        + "def command(tick):\n    return diagnostic_command(tick)\n\n"
        + source[end:]
    )
    source = replace_once(source, "for tick in range(1200):", "for tick in range(3120):")
    source = replace_once(
        source,
        "            v, w = command(tick)",
        """            target_onset(tick,tracker,robot,sim,phase_mark,preserve_nonfinite)
            v, w = command(tick)""",
    )
    source = replace_once(
        source,
        "                    output = tracker.update(w, measured, 1 / 120)",
        """                    if diagnostic_info(tick)["stage"] == "target" and diagnostic_info(tick)["mode"] == "direct":
                        output = w  # Prescribed downstream test only, not deployment PI.
                    else:
                        output = tracker.update(w, measured, 1 / 120)""",
    )
    source = replace_once(
        source,
        '        names, idx = ns["names"], ns["idx"]',
        """        names, idx = ns["names"], ns["idx"]
        phase_mark("PLANT_USD_READBACK", readback=plant_readback(ns["usd"]))""",
    )
    source = replace_once(
        source,
        '            validate_evaluation(row)\n        rows = result["rows"]',
        """            validate_evaluation(row)
            row["diagnostic"] = diagnostic_info(tick)
            if diagnostic_info(tick).get("offset") == 119 or (diagnostic_info(tick).get("offset") == 179 and diagnostic_info(tick)["mode"] == "direct"):
                phase_mark("REST_READY", tick=tick, evaluation_v=row["evaluation_v"], evaluation_w=row["evaluation_w"], integral=tracker.integral)
                if abs(row["evaluation_v"]) > .01 or abs(row["evaluation_w"]) > .03 or tracker.integral != 0:
                    raise ValueError("fixed rest readiness failed")
        rows = result["rows"]""",
    )
    source = replace_once(
        source,
        "for start in range(120, 1080, 60):",
        "for start in [300 + 240*k for k in range(12)]:",
    )
    source = replace_once(source, "rows[1079:]", "rows[-121:]")
    source = replace_once(
        source, "len(gyro.guard.records) == 1080", "len(gyro.guard.records) == 3000"
    )
    source = replace_once(source, "simulation_ticks=1200", "simulation_ticks=3120")
    source = replace_once(source, "range(1200)) / 120", "range(3120)) / 120")
    source = instrument(source)
    source = replace_once(
        source,
        'if measured is not None and (v != 0 or w != 0) else {"reset": True, "recorded_output": output}',
        """if measured is not None and (v != 0 or w != 0) and not (diagnostic_info(tick)["stage"] == "target" and diagnostic_info(tick)["mode"] == "direct")
                               else {"pi_formula": "NOT_APPLICABLE" if diagnostic_info(tick)["stage"] == "target" and diagnostic_info(tick)["mode"] == "direct" else "RESET", "recorded_output": output}""",
    )
    return source
