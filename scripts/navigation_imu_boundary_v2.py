"""Selected-start native IMU lifecycle and explicit collector binding."""

import ast
import json
import math
from pathlib import Path

from imu_controller_boundary_v1 import BodyGyro, GyroGuard, bind_collector_source
from imu_lifecycle_v6 import PhaseLog, capture_initialization_state, preserve_nonfinite


def initialize(robot, sim, xy, yaw, episode):
    import numpy as np
    import omni.usd
    from isaacsim.core.prims import XFormPrim
    from pxr import UsdPhysics

    phases = PhaseLog(Path(episode) / "imu_lifecycle.jsonl")
    mark = phases.mark
    capture_initialization_state(mark, "BEFORE_SELECTED_START_STOP", robot, sim)
    sim.stop()
    capture_initialization_state(mark, "AFTER_SELECTED_START_STOP", robot, sim)
    if robot._articulation.is_physics_handle_valid():
        raise ValueError("STOP required before sensor creation")
    paths = list(robot._articulation._prim_paths)
    if len(paths) != 1:
        raise ValueError("one physical root required")
    prim = omni.usd.get_context().get_stage().GetPrimAtPath(paths[0])
    if not prim or not prim.HasAPI(UsdPhysics.RigidBodyAPI):
        raise ValueError("physical root must be rigid body")
    target = np.array([[float(xy[0]), float(xy[1]), robot.config.spawn_height]])
    orientation = np.array([[math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]])
    if not np.isfinite(target).all() or not np.isfinite(orientation).all():
        raise ValueError("finite selected initialization required")
    authored = XFormPrim(paths[0], reset_xform_properties=False, usd=True)
    authored.set_world_poses(positions=target, orientations=orientation, usd=True)
    pos, quat = authored.get_world_poses(usd=True)
    mark(
        "SELECTED_ROOT_AUTHORED",
        **preserve_nonfinite(
            dict(
                path=paths[0],
                xyz=np.asarray(pos).tolist(),
                orientation=np.asarray(quat).tolist(),
                target=target.tolist(),
            )
        ),
    )
    if not np.allclose(pos, target, atol=1e-6, rtol=0) or not np.allclose(
        quat, orientation, atol=1e-6, rtol=0
    ):
        raise ValueError("selected USD placement mismatch")
    gyro = BodyGyro(robot, sim)
    gyro.evidence_path = Path(episode) / "imu_controller_readings.jsonl"
    gyro.sensor.resume()
    if gyro.sensor.is_paused():
        raise ValueError("IMU enable readback required")
    mark("SENSOR_CREATED_ENABLED", metadata=gyro.metadata)
    sim.play()
    robot._articulation.initialize()
    robot._articulation.set_velocities(np.zeros((1, 6)))
    actual_xy, actual_yaw = robot.pose()
    predicates = dict(
        finite=bool(np.isfinite([*actual_xy, actual_yaw]).all()),
        xy=bool(np.allclose(actual_xy, xy, atol=1e-6, rtol=0)),
        yaw=abs(math.atan2(math.sin(actual_yaw - yaw), math.cos(actual_yaw - yaw))) <= 1e-6,
    )
    capture_initialization_state(mark, "AFTER_SELECTED_START_PLAY", robot, sim)
    mark(
        "SELECTED_START_PREDICATES",
        **preserve_nonfinite(
            dict(predicates=predicates, xy=actual_xy.tolist(), yaw=float(actual_yaw))
        ),
    )
    if not all(predicates.values()):
        raise ValueError("selected physics placement mismatch")
    guard = GyroGuard(gyro.path)
    for tick in range(120):
        sim.step(render=False)
        raw = gyro.interface.get_sensor_reading(gyro.path, use_latest_data=True, read_gravity=False)
        mark(
            "NATIVE_WARMUP",
            **preserve_nonfinite(
                dict(
                    tick=tick,
                    valid=bool(raw.is_valid),
                    sensor_time=float(raw.time),
                    simulation_time=float(sim.current_time),
                    angular_velocity=[
                        float(raw.ang_vel_x),
                        float(raw.ang_vel_y),
                        float(raw.ang_vel_z),
                    ],
                )
            ),
        )
        if tick in (118, 119):
            guard.accept(raw, float(sim.current_time), gyro.path)
    mark("NATIVE_READY", metadata=gyro.metadata)
    return gyro


def record_tracking(robot, sim, held, path, gyro):
    """Post-render-step independent body-frame evaluation; never controller input."""
    import numpy as np
    from imu_controller_boundary_v1 import validate_evaluation

    q = np.asarray(robot._articulation.get_world_poses()[1]).reshape(-1, 4)[0]
    vel = np.asarray(robot._articulation.get_velocities()).reshape(-1, 6)[0]
    w, x, y, z = q
    forward = np.array([1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)])
    vertical = np.array([2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)])
    now = float(sim.current_time)
    dt = now - held.get("evaluation_previous_time", now - 1 / 12)
    if not 0 < dt <= 1 / 12 + 1e-6:
        raise ValueError("tracking capture interval invalid")
    held["evaluation_previous_time"] = now
    row = dict(
        time=now,
        dt=dt,
        command=list(held["command"]),
        evaluation_v=float(forward @ vel[:3]),
        evaluation_w=float(vertical @ vel[3:]),
        orientation_wxyz=q.tolist(),
        world_velocity=vel.tolist(),
    )
    validate_evaluation(row)
    if abs(float(q @ q) - 1) > 1e-3:
        raise ValueError("unit evaluation orientation required")
    if gyro.guard.records:
        sample = gyro.guard.records[-1]
        row.update(
            native_sample_time=sample["time"],
            native_rate_z=sample["angular_velocity"][2],
            native_sample_age_s=now - sample["time"],
            native_minus_evaluation_rate=sample["angular_velocity"][2] - row["evaluation_w"],
        )
    with Path(path).open("a") as stream:
        stream.write(json.dumps(row, allow_nan=False) + "\n")


def bind(source):
    tree = bind_collector_source(source)

    class Edit(ast.NodeTransformer):
        factory = placement = contact = metadata = 0

        def visit_Assign(self, node):
            self.generic_visit(node)
            if any(isinstance(t, ast.Name) and t.id == "body_gyro" for t in node.targets):
                node.value = ast.Constant(None)
                self.factory += 1
                return [node, ast.parse("navigation_active = False").body[0]]
            return node

        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            if node.name == "on_physics_step":
                block = next(item for item in node.body if isinstance(item, ast.Try))
                measured = [
                    item
                    for item in block.body
                    if isinstance(item, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "measured" for t in item.targets)
                ]
                if len(measured) != 1:
                    raise ValueError("one native sample per callback required")
                block.body.remove(measured[0])
                block.body.insert(1, measured[0])
                node.body.insert(
                    0,
                    ast.parse(
                        "if body_gyro is None:\n    wheel_targets(0.,0.,0.)\n    held['idle'] += 1\n    return"
                    ).body[0],
                )
            if node.name == "step":
                node.body.append(
                    ast.parse(
                        "if navigation_active:\n    record_tracking(robot,sim,held,episode/'controller_evaluation.jsonl',body_gyro)"
                    ).body[0]
                )
            return node

        def visit_Expr(self, node):
            self.generic_visit(node)
            if ast.unparse(node) == "robot.teleport(start_xy, start_yaw)":
                self.placement += 1
                return ast.parse(
                    "body_gyro = initialize(robot,sim,start_xy,start_yaw,episode)"
                ).body
            return node

        def visit_If(self, node):
            self.generic_visit(node)
            if ast.unparse(node.test).startswith("any((p.startswith(robot.prim_path)"):
                pass
            # Locate the contact condition by its exact original string representation.
            if "p.startswith(robot.prim_path)" in ast.unparse(
                node.test
            ) and "/World/Fixture/" in ast.unparse(node.test):
                node.test = ast.parse(
                    "any(p.startswith(robot.prim_path) for p in paths)", mode="eval"
                ).body
                self.contact += 1
            return node

        def visit_Constant(self, node):
            if node.value == "articulation root angular velocity z (ideal gyro)":
                self.metadata += 1
                node.value = "native body-local IsaacImuSensor angular velocity z"
            return node

    edit = Edit()
    tree = edit.visit(tree)
    if (edit.factory, edit.placement, edit.contact, edit.metadata) != (1, 1, 1, 1):
        raise ValueError("exact selected-start and controller boundaries required")
    # Activation is after cold input/recording setup; no evaluation log during conditioning.
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "feedback_start" for t in node.targets
        ):
            for parent in ast.walk(tree):
                for _, items in ast.iter_fields(parent):
                    if isinstance(items, list) and node in items:
                        items[items.index(node) : items.index(node)] = ast.parse(
                            "navigation_active = True\nheld['evaluation_previous_time'] = float(sim.current_time)"
                        ).body
                        return ast.fix_missing_locations(tree)
    raise ValueError("one navigation evaluation activation required")
