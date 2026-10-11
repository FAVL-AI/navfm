"""Pure authenticated import and lifecycle controls; no model/simulator imports."""

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from imu_lifecycle_v2 import PhaseLog, instrument_probe, instrument_stage
from nomad_dependency_boundary_v2 import (
    DiffusionFinder,
    install_boundary,
    verify_loaded_dependencies,
)


def finder(tmp_path):
    p = tmp_path / "diffusion_policy/model/diffusion/conditional_unet1d.py"
    p.parent.mkdir(parents=True)
    p.write_text("VALUE = 7\n")
    item = {
        "module": "diffusion_policy.model.diffusion.conditional_unet1d",
        "path": str(p.relative_to(tmp_path)),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    return DiffusionFinder(tmp_path, [item]), item, p


def test_authenticated_source_import(tmp_path):
    boundary, item, _ = finder(tmp_path)
    spec = boundary.find_spec(item["module"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.VALUE == 7
    assert module.__file__.startswith(str(tmp_path))


def test_changed_dependency_refused_before_execution(tmp_path):
    boundary, item, p = finder(tmp_path)
    p.write_text('raise RuntimeError("must never execute")\n')
    spec = boundary.find_spec(item["module"])
    with pytest.raises(ImportError, match="drift"):
        spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_undeclared_diffusion_import_refused(tmp_path):
    boundary, _, _ = finder(tmp_path)
    with pytest.raises(ImportError, match="undeclared"):
        boundary.find_spec("diffusion_policy.untrusted")
    assert boundary.find_spec("unrelated") is None


def test_preloaded_namespace_refused(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "diffusion_policy", SimpleNamespace())
    with pytest.raises(ImportError, match="preloaded"):
        install_boundary(tmp_path, [])


def test_lifecycle_fsync_and_sequence(tmp_path, monkeypatch):
    import imu_lifecycle_v2

    calls = []
    monkeypatch.setattr(imu_lifecycle_v2.os, "fsync", lambda fd: calls.append(fd))
    log = PhaseLog(tmp_path / "phases.jsonl")
    log.mark("BEFORE_APP", OMNICLIENT_HUB_MODE="disabled")
    log.mark("FAILURE", error_type="ControlledError")
    rows = [json.loads(x) for x in log.path.read_text().splitlines()]
    assert [r["sequence"] for r in rows] == [1, 2]
    assert len(calls) == 2 and rows[0]["OMNICLIENT_HUB_MODE"] == "disabled"


def test_lifecycle_transformation_preserves_physics():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/qualify_imu_controller_v1.py").read_text()
    tree = instrument_probe(source)
    text = ast.unparse(tree)
    assert "range(1200)" in text
    assert "phase_mark('BEFORE_APP')" in text and "phase_mark('AFTER_APP')" in text
    assert text.count("ObservedBodyGyro(robot, sim)") == 1
    assert "OMNICLIENT_HUB_MODE" in text
    assert (
        text.index("BEFORE_ISAAC_IMPORT")
        < text.index("from isaacsim import SimulationApp")
        < text.index("AFTER_ISAAC_IMPORT")
    )
    assert "boundary='ISAAC_IMPORT'" in text
    with pytest.raises(ValueError):
        instrument_probe(source.replace("SimulationApp({", "ChangedApp({"))


def test_stage_markers_exact_boundary():
    tree = ast.parse("stage.create_new_stage()\nvalue=7")
    text = ast.unparse(instrument_stage(tree))
    assert text.index("BEFORE_STAGE") < text.index("create_new_stage") < text.index("AFTER_STAGE")
    with pytest.raises(ValueError):
        instrument_stage(ast.parse("value=7"))


def test_loaded_dependency_origin_is_authenticated(tmp_path):
    approved = tmp_path / "approved.py"
    ambient = tmp_path / "ambient.py"
    approved.write_text("VALUE=7")
    ambient.write_text("VALUE=7")
    manifest = {
        "files": [
            {"path": str(approved), "sha256": hashlib.sha256(approved.read_bytes()).hexdigest()}
        ]
    }
    assert verify_loaded_dependencies(
        manifest, {"einops": SimpleNamespace(__file__=str(approved))}
    )[0]["source"] == str(approved)
    with pytest.raises(ImportError, match="outside authenticated"):
        verify_loaded_dependencies(manifest, {"einops": SimpleNamespace(__file__=str(ambient))})


def test_embedded_torch_module_requires_exact_authenticated_parent_identity(tmp_path):
    binary = tmp_path / "_C.so"
    binary.write_bytes(b"pinned binary")
    nested = SimpleNamespace()
    parent = SimpleNamespace(__file__=str(binary), _dynamo=SimpleNamespace(eval_frame=nested))
    manifest = {
        "files": [{"path": str(binary), "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}]
    }
    modules = {"torch._C": parent, "torch._C._dynamo.eval_frame": nested}
    assert verify_loaded_dependencies(manifest, modules)[1]["kind"] == "embedded_binary_module"
    modules["torch._C._dynamo.eval_frame"] = SimpleNamespace()
    with pytest.raises(ImportError, match="identity mismatch"):
        verify_loaded_dependencies(manifest, modules)
