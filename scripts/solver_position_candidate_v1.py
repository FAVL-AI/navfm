"""One prospective TGS position-iteration factor; physical plant remains unchanged."""

import ast


def instrument_prefix(tree):
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and isinstance(n.value.func.value, ast.Name)
        and n.value.func.value.id == "sim"
        and n.value.func.attr == "initialize_physics"
    ]
    if len(calls) != 1 or calls[0] not in tree.body:
        raise ValueError("exact pre-initialize solver boundary required")
    index = tree.body.index(calls[0])
    tree.body[index:index] = ast.parse(
        "from solver_position_candidate_v1 import install_solver_candidate\n"
        "install_solver_candidate(usd, sim, phase_mark)"
    ).body
    return ast.fix_missing_locations(tree)


def install_solver_candidate(stage, sim, mark):
    from pxr import PhysxSchema, UsdPhysics

    roots = [
        p
        for p in stage.Traverse()
        if p.HasAPI(UsdPhysics.ArticulationRootAPI) and str(p.GetPath()).startswith("/World/Robot/")
    ]
    scenes = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
    if len(roots) != 1 or len(scenes) != 1:
        raise ValueError("unique robot articulation and physics scene required")
    articulation = PhysxSchema.PhysxArticulationAPI(roots[0])
    position = articulation.GetSolverPositionIterationCountAttr()
    velocity = articulation.GetSolverVelocityIterationCountAttr()
    scene = PhysxSchema.PhysxSceneAPI(scenes[0])
    properties = dict(
        root=str(roots[0].GetPath()),
        scene=str(scenes[0].GetPath()),
        before_position=position.Get(),
        velocity=velocity.Get(),
        solver=scene.GetSolverTypeAttr().Get(),
        min_position=scene.GetMinPositionIterationCountAttr().Get(),
        max_position=scene.GetMaxPositionIterationCountAttr().Get(),
        min_velocity=scene.GetMinVelocityIterationCountAttr().Get(),
        max_velocity=scene.GetMaxVelocityIterationCountAttr().Get(),
        physics_dt=float(sim.get_physics_dt()),
    )
    mark("SOLVER_CANDIDATE_BEFORE", **properties)
    if (
        properties["before_position"] != 32
        or properties["velocity"] != 1
        or properties["solver"] != "TGS"
        or abs(properties["physics_dt"] - 1 / 120) > 1e-12
    ):
        raise ValueError("baseline solver contract mismatch")
    if (
        not properties["min_position"] <= 64 <= properties["max_position"]
        or not properties["min_velocity"] <= 1 <= properties["max_velocity"]
    ):
        raise ValueError("candidate blocked by scene iteration clamp")
    if not position.Set(64) or position.Get() != 64 or velocity.Get() != 1:
        raise ValueError("solver candidate authoring failed")
    mark(
        "SOLVER_CANDIDATE_AUTHORED",
        **{**properties, "after_position": position.Get()},
        evidence_scope="USD attributes; not independent native iteration telemetry",
    )
