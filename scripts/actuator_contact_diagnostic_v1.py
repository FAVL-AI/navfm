"""Fixed direct targets in fresh grounded and floating unloaded arms."""

import ast

from controller_telemetry_v1 import checked_array, instrument, replace_once

TARGETS = [(0.05, 0.005), (0, -0.4), (0.05, -0.005), (0, 0.4)]


def command(tick, condition):
    if tick < 120 or tick >= 840:
        return 0.0, 0.0
    cell, offset = divmod(tick - 120, 180)
    targets = TARGETS if condition == "grounded" else TARGETS[::-1]
    return (0.0, 0.0) if offset < 120 else targets[cell]


def setup_condition(tree, condition):
    if condition not in ("grounded", "airborne"):
        raise ValueError("unknown condition")
    calls = [
        n
        for n in tree.body
        if isinstance(n, ast.Expr) and ast.unparse(n) == "sim.initialize_physics()"
    ]
    if len(calls) != 1:
        raise ValueError("pre-initialize boundary drift")
    index = tree.body.index(calls[0])
    tree.body[index:index] = ast.parse(
        "from actuator_contact_diagnostic_v1 import install_condition\n"
        + f"install_condition(usd, sim, phase_mark, {condition!r})"
    ).body
    if condition == "airborne":
        changes = 0
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Call)
                and ast.unparse(n.func) == "dataclasses.replace"
                and any(isinstance(a, ast.Name) and a.id == "M3PRO" for a in n.args)
            ):
                n.keywords.append(ast.keyword(arg="spawn_height", value=ast.Constant(0.30)))
                changes += 1
        if changes != 1:
            raise ValueError("one robot initialization configuration required")
    return ast.fix_missing_locations(tree)


def author_gravity(api, condition):
    if condition not in ("grounded", "airborne"):
        raise ValueError("unknown condition")
    if not api.CreateDisableGravityAttr().Set(condition == "airborne"):
        raise ValueError("gravity authoring failed")


def install_condition(stage, sim, mark, condition):
    from pxr import PhysxSchema, UsdPhysics

    links = [
        p
        for p in stage.Traverse()
        if str(p.GetPath()).startswith("/World/Robot/") and p.HasAPI(UsdPhysics.RigidBodyAPI)
    ]
    roots = [p for p in links if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
    scenes = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
    if not links or len(roots) != 1 or len(scenes) != 1:
        raise ValueError("unique articulation/scene required")
    if not all(p.HasAPI(PhysxSchema.PhysxContactReportAPI) for p in links):
        raise ValueError("contact reporting required on all links")
    before = [
        {
            "path": str(p.GetPath()),
            "schema_applied": p.HasAPI(PhysxSchema.PhysxRigidBodyAPI),
            "disabled": PhysxSchema.PhysxRigidBodyAPI(p).GetDisableGravityAttr().Get(),
        }
        for p in links
    ]
    mark("GRAVITY_BEFORE_AUTHORING", links=before)
    for p in links:
        author_gravity(PhysxSchema.PhysxRigidBodyAPI.Apply(p), condition)
    flags = [
        dict(
            path=str(p.GetPath()),
            disabled=PhysxSchema.PhysxRigidBodyAPI(p).GetDisableGravityAttr().Get(),
            contact_threshold=PhysxSchema.PhysxContactReportAPI(p).GetThresholdAttr().Get(),
        )
        for p in links
    ]
    art = PhysxSchema.PhysxArticulationAPI(roots[0])
    scene = PhysxSchema.PhysxSceneAPI(scenes[0])
    mark(
        "CONDITION_CONFIGURED",
        condition=condition,
        gravity_flags=flags,
        position=art.GetSolverPositionIterationCountAttr().Get(),
        velocity=art.GetSolverVelocityIterationCountAttr().Get(),
        solver=scene.GetSolverTypeAttr().Get(),
        physics_dt=float(sim.get_physics_dt()),
    )
    if any(
        x["disabled"] != (condition == "airborne") or x["contact_threshold"] != 0 for x in flags
    ):
        raise ValueError("gravity/contact flag mismatch")
    if (
        art.GetSolverPositionIterationCountAttr().Get() != 32
        or art.GetSolverVelocityIterationCountAttr().Get() != 1
        or scene.GetSolverTypeAttr().Get() != "TGS"
        or abs(sim.get_physics_dt() - 1 / 120) > 1e-12
    ):
        raise ValueError("original solver contract required")


def clearance(position, quaternion):
    p = checked_array(position, 3)
    q = checked_array(quaternion, 4)
    if abs(sum(x * x for x in q) - 1) > 1e-3:
        raise ValueError("unit quaternion required")
    w, x, y, z = q
    # World-Z row of WXYZ rotation. Sphere centres are relative to base_footprint.
    row = [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]
    # Correct world Z = matrix row 2; unlike body-z column used for rate projection.
    sphere = min(
        p[2] + sum(a * b for a, b in zip(row, (cx, cy, 0.04), strict=True)) - 0.04
        for cx in [-0.0775, 0.0775]
        for cy in [-0.085, 0.085]
    )
    box = min(
        p[2] + sum(a * b for a, b in zip(row, (cx, cy, cz), strict=True))
        for cx in [-0.145, 0.145]
        for cy in [-0.1175, 0.1175]
        for cz in [0.04, 0.12]
    )
    return min(sphere, box)


def copy_contacts(headers, data, path_string):
    records = []
    for h in headers:
        paths = [path_string(h.actor0), path_string(h.actor1)]
        if not any(p.startswith("/World/Robot/") for p in paths):
            continue
        start, count = h.contact_data_offset, h.num_contact_data
        if (
            type(start) is not int
            or type(count) is not int
            or start < 0
            or count < 0
            or start + count > len(data)
        ):
            raise ValueError("contact buffer schema mismatch")
        records.append(
            dict(
                paths=paths,
                type=int(h.type),
                colliders=[path_string(h.collider0), path_string(h.collider1)],
                points=[
                    dict(
                        position=list(data[i].position),
                        normal=list(data[i].normal),
                        impulse_Ns=list(data[i].impulse),
                        separation=data[i].separation,
                    )
                    for i in range(start, start + count)
                ],
            )
        )
    return records


def passive_sample(tick, robot, sim, condition, mark, preserve):
    import omni.physx
    from pxr import PhysicsSchemaTools

    articulation = robot._articulation
    q = checked_array(articulation.get_joint_positions(), 4)
    dq = checked_array(articulation.get_joint_velocities(), 4)
    xyz, wxyz = articulation.get_world_poses()
    height = clearance(xyz, wxyz)
    efforts = {}
    for method in ("get_applied_joint_efforts", "get_measured_joint_efforts"):
        value = getattr(articulation, method)()
        efforts[method] = (
            {"status": "UNKNOWN"}
            if value is None
            else {"status": "OBSERVED", "value_Nm": checked_array(value, 4)}
        )
    # Native immediate report is valid for one step: copy before the next step.
    headers, data = omni.physx.get_physx_simulation_interface().get_contact_report()
    contacts = copy_contacts(headers, data, lambda v: str(PhysicsSchemaTools.intToSdfPath(v)))
    fields = dict(
        tick=tick,
        simulation_time=float(sim.current_time),
        condition=condition,
        joint_positions_rad=q,
        joint_velocities_rad_s=dq,
        root_xyz=checked_array(xyz, 3),
        root_orientation_wxyz=checked_array(wxyz, 4),
        clearance_m=height,
        efforts=efforts,
        contact_observation="IMMEDIATE_QUERY_COMPLETED",
        contacts=contacts,
        impulse_scope="raw contact impulse, not instantaneous force or motor torque",
    )
    mark("PASSIVE_PLANT_SAMPLE", **preserve(fields))
    if condition == "airborne" and (height <= 0.1 or contacts):
        raise ValueError("airborne clearance/no-contact condition failed")
    from imu_controller_boundary_v1 import validate_evaluation

    for record in contacts:
        for point in record["points"]:
            validate_evaluation(point)
    if tick in [239 + 180 * k for k in range(4)]:
        mark("PRETARGET_STATE", next_target_tick=tick + 1, **preserve(fields))


def prepare(source, condition):
    start = source.index("COMMANDS = [")
    end = source.index("\ndef main():", start)
    source = (
        source[:start]
        + f"def command(tick):\n    return diagnostic_command(tick, {condition!r})\n\n"
        + source[end:]
    )
    source = replace_once(
        source,
        "output = tracker.update(w, measured, 1 / 120)",
        "output = w  # Fixed direct wheel target; no PI update",
    )
    source = source.replace("range(1200)", "range(960)")
    source = replace_once(
        source, "for start in range(120, 1080, 60):", "for start in [240+180*k for k in range(4)]:"
    )
    source = replace_once(source, "rows[1079:]", "rows[-121:]")
    source = replace_once(
        source, "len(gyro.guard.records) == 1080", "len(gyro.guard.records) == 840"
    )
    source = replace_once(source, "simulation_ticks=1200", "simulation_ticks=960")
    source = instrument(source)
    source = replace_once(
        source,
        "            sim.step(render=False)",
        "            sim.step(render=False)\n            passive_sample(tick, robot, sim, "
        + repr(condition)
        + ", phase_mark, preserve_nonfinite)",
    )
    source = replace_once(
        source,
        'if measured is not None and (v != 0 or w != 0) else {"reset": True, "recorded_output": output}',
        'if False else {"pi_formula": "BYPASSED_DIRECT", "recorded_output": output}',
    )
    return source
