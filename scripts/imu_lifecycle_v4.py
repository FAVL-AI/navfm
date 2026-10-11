"""Fsynced lifecycle evidence around the preserved single IMU probe."""

from __future__ import annotations

import ast
import json
import math
import os
import time
from pathlib import Path


class PhaseLog:
    def __init__(self, path):
        self.path = Path(path)
        self.sequence = 0

    def mark(self, phase, **fields):
        self.sequence += 1
        record = {
            "sequence": self.sequence,
            "phase": phase,
            "wall_time": time.time(),
            "monotonic": time.monotonic(),
            **fields,
        }
        with self.path.open("a") as stream:
            stream.write(json.dumps(record, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def mark_expr(name):
    return ast.parse(f"phase_mark({name!r})").body[0]


def instrument_probe(source):
    class Instrument(ast.NodeTransformer):
        app = sensor = setup = isaac_import = 0

        def visit_ImportFrom(self, node):
            if node.module == "isaacsim" and any(a.name == "SimulationApp" for a in node.names):
                self.isaac_import += 1
                return [
                    mark_expr("BEFORE_ISAAC_IMPORT"),
                    ast.Try(
                        body=[node, mark_expr("AFTER_ISAAC_IMPORT")],
                        handlers=[
                            ast.ExceptHandler(
                                type=ast.Name(id="BaseException", ctx=ast.Load()),
                                name="import_error",
                                body=[
                                    ast.parse(
                                        "phase_mark('FAILURE', boundary='ISAAC_IMPORT', error_type=type(import_error).__name__)"
                                    ).body[0],
                                    ast.Raise(),
                                ],
                            )
                        ],
                        orelse=[],
                        finalbody=[],
                    ),
                ]
            return node

        def visit_Assign(self, node):
            self.generic_visit(node)
            if any(isinstance(t, ast.Name) and t.id == "ns" for t in node.targets) and isinstance(
                node.value, ast.Dict
            ):
                node.value.keys.append(ast.Constant("phase_mark"))
                node.value.values.append(ast.Name(id="phase_mark", ctx=ast.Load()))
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "SimulationApp"
            ):
                self.app += 1
                return [
                    ast.parse(
                        "phase_mark('LAUNCH_ENVIRONMENT', OMNICLIENT_HUB_MODE=os.environ.get('OMNICLIENT_HUB_MODE'))"
                    ).body[0],
                    mark_expr("BEFORE_APP"),
                    ast.Try(
                        body=[node, mark_expr("AFTER_APP")],
                        handlers=[
                            ast.ExceptHandler(
                                type=ast.Name(id="BaseException", ctx=ast.Load()),
                                name="startup_error",
                                body=[
                                    ast.parse(
                                        "phase_mark('FAILURE', error_type=type(startup_error).__name__)"
                                    ).body[0],
                                    ast.Raise(),
                                ],
                            )
                        ],
                        orelse=[],
                        finalbody=[],
                    ),
                ]
            return node

        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == "BodyGyro":
                self.sensor += 1
                node.func.id = "ObservedBodyGyro"
            if isinstance(node.func, ast.Name) and node.func.id == "setup_prefix":
                self.setup += 1
                node.func.id = "observed_setup_prefix"
            return node

        def visit_ExceptHandler(self, node):
            self.generic_visit(node)
            if node.name == "error":
                node.body.insert(
                    0, ast.parse("phase_mark('FAILURE', error_type=type(error).__name__)").body[0]
                )
            return node

    edit = Instrument()
    tree = edit.visit(ast.parse(source))
    if (edit.app, edit.sensor, edit.setup, edit.isaac_import) != (1, 1, 1, 1):
        raise ValueError("exact preserved probe instrumentation boundary required")
    return ast.fix_missing_locations(tree)


def instrument_stage(tree):
    class Stage(ast.NodeTransformer):
        count = 0

        def visit_Expr(self, node):
            self.generic_visit(node)
            call = node.value
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "create_new_stage"
            ):
                self.count += 1
                return [mark_expr("BEFORE_STAGE"), node, mark_expr("AFTER_STAGE")]
            return node

    edit = Stage()
    tree = edit.visit(tree)
    if edit.count != 1:
        raise ValueError("exact stage creation required")
    return ast.fix_missing_locations(tree)


def instrument_initialization(tree):
    """Preserve setup, reposition without a sensor, then attach on a fresh PLAY."""

    class Init(ast.NodeTransformer):
        gyro = teleport = step = 0

        def visit_Assign(self, node):
            self.generic_visit(node)
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "ObservedBodyGyro"
            ):
                self.gyro += 1
                before = ast.parse(
                    "phase_mark('BEFORE_INITIAL_PLACEMENT', simulation_time=float(sim.current_time))\nrobot.teleport((-3, 0), 0)\ninitial_xy, initial_yaw = robot.pose()\ncapture_initialization_state(phase_mark, 'AFTER_INITIAL_PLACEMENT_STATE', robot, sim)\nphase_mark('BEFORE_STOP', simulation_time=float(sim.current_time))\nsim.stop()\nphase_mark('AFTER_STOP', simulation_time=float(sim.current_time))\ncapture_initialization_state(phase_mark, 'AFTER_STOP_STATE', robot, sim)"
                ).body
                after = ast.parse(
                    "gyro.sensor.resume()\nif gyro.sensor.is_paused():\n    raise ValueError('IMU enabled readback required')\nphase_mark('SENSOR_ENABLED', enabled=True, native_attachment='NOT_YET_PROVEN')\nphase_mark('BEFORE_RESTART_PLAY', simulation_time=float(sim.current_time))\nsim.play()\nrobot._articulation.initialize()\nrestart_xy, restart_yaw = robot.pose()\ncapture_initialization_state(phase_mark, 'AFTER_RESTART_STATE', robot, sim)\npose_predicates = dict(finite=all(np.isfinite(v) for v in [*initial_xy, *restart_xy, initial_yaw, restart_yaw]), xy_equal=bool(np.allclose(restart_xy, initial_xy, atol=1e-6, rtol=0)), yaw_equal=bool(abs(restart_yaw-initial_yaw)<=1e-6))\nphase_mark('INITIAL_POSE_COMPARISON', **preserve_nonfinite(dict(initial_xy=initial_xy.tolist(), restart_xy=restart_xy.tolist(), initial_yaw=float(initial_yaw), restart_yaw=float(restart_yaw), predicates=pose_predicates, simulation_time=float(sim.current_time))))\nif not all(pose_predicates.values()):\n    raise ValueError('initial pose changed across sensor restart')\nphase_mark('AFTER_RESTART_PLAY', simulation_time=float(sim.current_time), initial_xy=initial_xy.tolist(), restart_xy=restart_xy.tolist(), initial_yaw=float(initial_yaw), restart_yaw=float(restart_yaw))"
                ).body
                return [*before, node, *after]
            return node

        def visit_Expr(self, node):
            self.generic_visit(node)
            if ast.unparse(node) == "robot.teleport((-3, 0), 0)":
                self.teleport += 1
                return None
            if ast.unparse(node) == "sim.step(render=False)":
                self.step += 1
                return [node, *ast.parse("if tick < 120:\n    gyro.observe_readiness(tick)").body]
            return node

    edit = Init()
    tree = edit.visit(tree)
    if (edit.gyro, edit.teleport, edit.step) != (1, 1, 1):
        raise ValueError("exact initialization and startup boundaries required")
    return ast.fix_missing_locations(tree)


def preserve_nonfinite(value):
    """JSON-safe evidence only; original readings still reach strict validation."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_numeric": repr(value), "numeric_type": "float"}
    if isinstance(value, dict):
        return {key: preserve_nonfinite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [preserve_nonfinite(item) for item in value]
    return value


def initialization_only(tree):
    class Diagnostic(ast.NodeTransformer):
        count = 0

        def visit_For(self, node):
            self.generic_visit(node)
            if ast.unparse(node.iter) == "range(1200)":
                self.count += 1
                node.iter = ast.parse("range(120)", mode="eval").body
                return [
                    node,
                    *ast.parse(
                        "result['status']='INITIALIZATION_PASS'\n(a.out/'imu_qualification.json').write_text(json.dumps(result, allow_nan=False))\nreturn"
                    ).body,
                ]
            return node

    edit = Diagnostic()
    tree = edit.visit(tree)
    if edit.count != 1:
        raise ValueError("exact initialization diagnostic loop required")
    return ast.fix_missing_locations(tree)


def initialization_state(robot, sim):
    """Preserve partial GT initialization evidence; never a control input."""
    import numpy as np
    import omni.timeline

    articulation = robot._articulation
    state = {
        "root": robot.prim_path,
        "class_module": type(articulation).__module__,
        "class_name": type(articulation).__qualname__,
        "errors": [],
    }
    method = "is_physics_tensor_entity_valid" if robot._is_v6 else "is_physics_handle_valid"
    state["handle_validity_method"] = method
    measurements = {
        "simulation_time": lambda: float(sim.current_time),
        "timeline_time": lambda: float(omni.timeline.get_timeline_interface().get_current_time()),
        "physics_handle_valid": lambda: bool(getattr(articulation, method)()),
        "world_pose": lambda: [np.asarray(x).tolist() for x in articulation.get_world_poses()],
        "derived_xy_yaw": lambda: [robot.pose()[0].tolist(), float(robot.pose()[1])],
    }
    for name, read in measurements.items():
        try:
            state[name] = read()
        except BaseException as error:
            state["errors"].append({"field": name, "error_type": type(error).__name__})
    if "physics_handle_valid" in state:
        state["read_backend"] = (
            "physics_tensor" if state["physics_handle_valid"] else "USD_fallback"
        )
    if "world_pose" in state:
        state["xyz"] = state["world_pose"][0][0]
        state["orientation_wxyz"] = state["world_pose"][1][0]
    if "derived_xy_yaw" in state:
        state["xy"], state["yaw"] = state["derived_xy_yaw"]
    return preserve_nonfinite(state)


def capture_initialization_state(phase_mark, name, robot, sim):
    state = initialization_state(robot, sim)
    phase_mark(name, **state)
    if state["errors"]:
        raise ValueError("initialization state readback failed; partial evidence retained")
