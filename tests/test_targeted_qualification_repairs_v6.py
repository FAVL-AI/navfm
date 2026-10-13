"""Pure finite-wrapper and stopped-authoring controls."""

import ast
import hashlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from authenticate_torch_wrappers_v6 import authenticate_wrapped_module
from imu_lifecycle_v6 import instrument_initialization, instrument_probe


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "altered_binary",
        "changed_method",
        "wrong_original",
        "wrong_export",
        "wrong_descriptor",
        "wrong_descriptor_slot",
        "wrong_method_slot",
    ],
)
def test_backend_wrapper_inherited_code_original_export_and_binary(tmp_path, failure):
    source = tmp_path / "backend.py"
    source.write_text("""class ContextProp:
    def __init__(self,getter,setter):self.getter=getter;self.setter=setter
    def __get__(self,obj,kind):return self.getter()
class PropModule(types.ModuleType):
    def __init__(self,m,name):super().__init__(name);self.m=m
    def __getattr__(self,name):return self.m.__getattribute__(name)
class CudnnModule(PropModule):
    def __init__(self,m,name):super().__init__(m,name)
    enabled=ContextProp(torch._C.getter,torch._C.setter)
""")
    binary = tmp_path / "_C.so"
    binary.write_bytes(b"approved")
    native = SimpleNamespace(__file__=str(binary), getter=object(), setter=object())
    torch = types.ModuleType("torch")
    torch._C = native
    original = types.ModuleType("torch.backends.cudnn")
    original.__file__ = str(source)
    original.__dict__.update(types=types, torch=torch)
    exec(compile(source.read_text(), str(source), "exec", dont_inherit=True), original.__dict__)
    cls = original.CudnnModule
    wrapper = cls(original, "torch.backends.cudnn")
    parent = types.ModuleType("torch.backends")
    parent.cudnn = wrapper
    modules = {
        "torch": torch,
        "torch._C": native,
        "torch.backends": parent,
        "torch.backends.cudnn": wrapper,
    }
    approved = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [source, binary]}
    if failure == "altered_binary":
        binary.write_bytes(b"changed")
    if failure == "changed_method":
        cls.__init__.__code__ = cls.__init__.__code__.replace(
            co_consts=(*cls.__init__.__code__.co_consts, "tampered")
        )
    if failure == "wrong_original":
        wrapper.m = types.ModuleType("foreign")
    if failure == "wrong_export":
        parent.cudnn = types.ModuleType("foreign")
    if failure == "wrong_method_slot":
        cls.__getattr__ = cls.__init__
    if failure == "wrong_descriptor_slot":
        vars(cls)["enabled"].getter = native.setter
    if failure == "wrong_descriptor":
        vars(cls)["enabled"].getter = object()
    if failure:
        with pytest.raises(ImportError):
            authenticate_wrapped_module("torch.backends.cudnn", wrapper, modules, approved, {})
    else:
        result = authenticate_wrapped_module("torch.backends.cudnn", wrapper, modules, approved, {})
        assert any(x["qualname"] == "PropModule.__getattr__" for x in result["methods"])
        assert "ContextProp" in result["descriptors"]


@pytest.mark.parametrize("name", ["torch.ops", "torch.classes"])
def test_legacy_name_alone_no_longer_admitted(name):
    with pytest.raises(ImportError, match="class identity"):
        authenticate_wrapped_module(name, types.ModuleType(name), {}, {}, {})


def test_stopped_physical_authoring_precedes_sensor_and_preserves_guard():
    source = Path(__file__).resolve().parents[1] / "scripts/qualify_imu_controller_v1.py"
    text = ast.unparse(instrument_initialization(instrument_probe(source.read_text())))
    assert (
        text.index("sim.stop()")
        < text.index("author_stopped_initial_pose(")
        < text.index("gyro = ObservedBodyGyro")
        < text.index("sim.play()")
    )
    assert "range(1200)" in text and "atol=1e-06" in text
    assert "INITIAL_POSE_COMPARISON" in text and "set_velocities(np.zeros((1, 6)))" in text
