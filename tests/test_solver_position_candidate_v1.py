import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
from imu_coverage_base_v2 import COMMANDS
from solver_position_candidate_v1 import instrument_prefix


def test_single_preinitialize_factor_no_schedule_change():
    tree = ast.parse("sim = SimulationContext()\nsim.initialize_physics()\nsim.play()")
    result = ast.unparse(instrument_prefix(tree))
    assert (
        result.index("install_solver_candidate")
        < result.index("sim.initialize_physics")
        < result.index("sim.play")
    )
    assert result.count("install_solver_candidate(") == 1
    assert len(COMMANDS) == 16 and COMMANDS[2] == [0.05, 0.005] and COMMANDS[12] == [0, 0.4]


@pytest.mark.parametrize(
    "source", ["sim.play()", "sim.initialize_physics()\nsim.initialize_physics()"]
)
def test_boundary_drift_rejected(source):
    with pytest.raises(ValueError, match="boundary"):
        instrument_prefix(ast.parse(source))


def test_single_property_write_and_clamp_rejection(monkeypatch):
    from types import SimpleNamespace

    from solver_position_candidate_v1 import install_solver_candidate

    class Attr:
        def __init__(self, value):
            self.value = value
            self.writes = []

        def Get(self):
            return self.value

        def Set(self, value):
            self.writes.append(value)
            self.value = value
            return True

    root = SimpleNamespace(
        GetPath=lambda: "/World/Robot/base_footprint", HasAPI=lambda _: True, IsA=lambda _: False
    )
    sceneprim = SimpleNamespace(
        GetPath=lambda: "/physicsScene", HasAPI=lambda _: False, IsA=lambda _: True
    )
    position, velocity = Attr(32), Attr(1)
    maximum = Attr(255)
    articulation = SimpleNamespace(
        GetSolverPositionIterationCountAttr=lambda: position,
        GetSolverVelocityIterationCountAttr=lambda: velocity,
    )
    scene = SimpleNamespace(
        GetSolverTypeAttr=lambda: Attr("TGS"),
        GetMinPositionIterationCountAttr=lambda: Attr(1),
        GetMaxPositionIterationCountAttr=lambda: maximum,
        GetMinVelocityIterationCountAttr=lambda: Attr(0),
        GetMaxVelocityIterationCountAttr=lambda: Attr(255),
    )
    monkeypatch.setitem(
        sys.modules,
        "pxr",
        SimpleNamespace(
            UsdPhysics=SimpleNamespace(ArticulationRootAPI=object(), Scene=object()),
            PhysxSchema=SimpleNamespace(
                PhysxArticulationAPI=lambda _: articulation, PhysxSceneAPI=lambda _: scene
            ),
        ),
    )
    events = []
    stage = SimpleNamespace(Traverse=lambda: [root, sceneprim])
    sim = SimpleNamespace(get_physics_dt=lambda: 1 / 120)

    def mark(name, **values):
        events.append((name, values))

    install_solver_candidate(stage, sim, mark)
    assert position.writes == [64] and velocity.writes == []
    assert events[-1][1]["after_position"] == 64
    position.value = 32
    position.writes = []
    maximum.value = 32
    with pytest.raises(ValueError, match="clamp"):
        install_solver_candidate(stage, sim, mark)
    assert position.writes == [] and velocity.writes == []


def test_helper_import_bound_inside_separate_setup_exec(monkeypatch):
    from types import SimpleNamespace

    events = []

    def stub(stage, sim, mark):
        assert stage == "fixed_stage"
        events.append("install")
        mark("candidate")

    monkeypatch.setitem(
        sys.modules, "solver_position_candidate_v1", SimpleNamespace(install_solver_candidate=stub)
    )

    class Sim:
        def initialize_physics(self):
            events.append("initialize")

        def play(self):
            events.append("play")

    namespace = dict(sim=Sim(), usd="fixed_stage", phase_mark=lambda name: events.append(name))
    # This setup namespace intentionally does not inherit the wrapper globals.
    assert "install_solver_candidate" not in namespace
    tree = instrument_prefix(ast.parse("sim.initialize_physics()\nsim.play()"))
    exec(compile(tree, "separate-preserved-setup", "exec"), namespace)
    assert events == ["install", "candidate", "initialize", "play"]
