"""Pure source/object authentication and passive diagnostic boundaries."""

import ast
import hashlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dependency_import_audit_v4 import audit, authenticate_vf
from imu_lifecycle_v4 import initialization_only, instrument_initialization, instrument_probe


@pytest.mark.parametrize("failure", [None, "wrong_member", "altered_source", "altered_binary"])
def test_vf_authentication(tmp_path, failure):
    source = tmp_path / "_VF.py"
    source.write_text(
        "class VFModule(types.ModuleType):\n    def __init__(self,name):\n        super().__init__(name)\n        self.vf=torch._C._VariableFunctions\n    def __getattr__(self,name):\n        return getattr(self.vf,name)\n"
    )
    binary = tmp_path / "_C.so"
    binary.write_bytes(b"authentic")
    parent = SimpleNamespace(__file__=str(binary), _VariableFunctions=object())
    ns = {"__name__": "torch._VF", "types": types, "torch": SimpleNamespace(_C=parent)}
    exec(compile(source.read_text(), str(source), "exec"), ns)
    module = ns["VFModule"]("torch._VF")
    manifest = {
        "files": [
            {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in [source, binary]
        ]
    }
    if failure == "wrong_member":
        module.vf = object()
    if failure == "altered_source":
        source.write_text("changed")
    if failure == "altered_binary":
        binary.write_bytes(b"changed")
    if failure:
        with pytest.raises(ImportError):
            authenticate_vf(module, parent, manifest)
    else:
        assert authenticate_vf(module, parent, manifest)["identity"]


def test_all_loaded_rejections_preserved(tmp_path):
    binary = tmp_path / "_C.so"
    binary.write_bytes(b"authentic")
    manifest = {
        "files": [{"path": str(binary), "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}]
    }
    records = audit(
        manifest,
        {
            "torch._C": SimpleNamespace(__file__=str(binary)),
            "torch.a": types.ModuleType("torch.a"),
            "torch.b": types.ModuleType("torch.b"),
        },
    )
    assert len(records) == 3
    assert sum(r["status"] == "UNCLASSIFIED" for r in records) == 2


def test_initialization_only_preserves_predicates_before_guard():
    source = Path(__file__).resolve().parents[1] / "scripts/qualify_imu_controller_v1.py"
    text = ast.unparse(
        initialization_only(instrument_initialization(instrument_probe(source.read_text())))
    )
    assert "for tick in range(120):" in text and "for tick in range(1200):" not in text
    assert text.index("INITIAL_POSE_COMPARISON") < text.index(
        "if not all(pose_predicates.values())"
    )
    assert "AFTER_STOP_STATE" in text and "AFTER_RESTART_STATE" in text
    assert "INITIALIZATION_PASS" in text


def test_partial_initialization_state_is_saved_before_rejection(monkeypatch):
    from imu_lifecycle_v4 import capture_initialization_state

    timeline = SimpleNamespace(
        get_timeline_interface=lambda: SimpleNamespace(get_current_time=lambda: 0.0)
    )
    omni = types.ModuleType("omni")
    omni.timeline = timeline
    monkeypatch.setitem(sys.modules, "omni", omni)
    monkeypatch.setitem(sys.modules, "omni.timeline", timeline)

    def unavailable():
        raise ValueError("test missing pose")

    articulation = SimpleNamespace(
        is_physics_handle_valid=lambda: False, get_world_poses=unavailable
    )
    robot = SimpleNamespace(
        _articulation=articulation, _is_v6=False, prim_path="/World/Robot", pose=unavailable
    )
    events = []
    with pytest.raises(ValueError, match="partial evidence retained"):
        capture_initialization_state(
            lambda name, **fields: events.append(fields),
            "AFTER_STOP_STATE",
            robot,
            SimpleNamespace(current_time=0.0),
        )
    assert events[0]["physics_handle_valid"] is False
    assert events[0]["handle_validity_method"] == "is_physics_handle_valid"
    assert {x["field"] for x in events[0]["errors"]} == {"world_pose", "derived_xy_yaw"}
