import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from actuator_contact_diagnostic_v1 import (
    clearance,
    command,
    copy_contacts,
    prepare,
    setup_condition,
)


def test_fixed_schedule():
    assert command(239, "grounded") == (0, 0)
    assert command(240, "grounded") == (0.05, 0.005)
    assert command(240, "airborne") == (0, 0.4)
    assert command(840, "airborne") == (0, 0)
    assert sum(any(command(t, "grounded")) for t in range(960)) == 240


def test_actual_setup_namespace(monkeypatch):
    import actuator_contact_diagnostic_v1 as module

    observed = []
    monkeypatch.setattr(module, "install_condition", lambda *args: observed.append(args[-1]))
    tree = setup_condition(ast.parse("sim.initialize_physics()\nsim.play()"), "grounded")
    ns = dict(
        usd=object(),
        phase_mark=object(),
        sim=SimpleNamespace(
            initialize_physics=lambda: observed.append("initialize"),
            play=lambda: observed.append("play"),
        ),
    )
    exec(compile(tree, "test", "exec"), ns)
    assert observed == ["grounded", "initialize", "play"]


def test_nested_pose_clearance():
    assert clearance([[0, 0, 0.3]], [[1, 0, 0, 0]]) == pytest.approx(0.3)
    with pytest.raises(ValueError):
        clearance([[0, 0, float("nan")]], [[1, 0, 0, 0]])


def test_contact_empty_and_actual_vector_impulse():
    assert copy_contacts([], [], str) == []
    header = SimpleNamespace(
        actor0="/World/Robot/wheel",
        actor1="/World/Floor",
        collider0="w",
        collider1="f",
        contact_data_offset=0,
        num_contact_data=1,
        type=0,
    )
    point = SimpleNamespace(position=[0, 0, 0], normal=[0, 0, 1], impulse=[0, 0, 0.1], separation=0)
    assert copy_contacts([header], [point], str)[0]["points"][0]["impulse_Ns"] == [0, 0, 0.1]
    header.num_contact_data = True
    with pytest.raises(ValueError):
        copy_contacts([header], [point], str)


def test_transform_compiles_actual_source():
    source = (Path(__file__).parents[1] / "scripts/imu_coverage_base_v2.py").read_text()
    result = prepare(source, "grounded")
    compile(result, "transformed", "exec")
    assert "tracker.update(" not in result
    assert "range(1200)" not in result
    assert "simulation_ticks=960" in result


def test_unapplied_gravity_authored_explicitly():
    from actuator_contact_diagnostic_v1 import author_gravity

    class Attribute:
        value = None

        def Set(self, value):
            self.value = value
            return True

    attr = Attribute()
    api = SimpleNamespace(CreateDisableGravityAttr=lambda: attr)
    assert attr.value is None
    author_gravity(api, "grounded")
    assert attr.value is False
    author_gravity(api, "airborne")
    assert attr.value is True
