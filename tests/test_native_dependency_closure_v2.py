"""Negative controls for the selected native import closure amendment."""

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import native_dependency_closure_v2 as closure
import preflight_native_adaptation_v2 as preflight


def test_duplicate_module_file_hash_once(tmp_path, monkeypatch):
    path = tmp_path / "native.py"
    path.write_text("x=1")
    a = ModuleType("a")
    a.__file__ = str(path)
    calls = []
    original = closure.sha
    monkeypatch.setattr(closure, "sha", lambda p: (calls.append(str(p)), original(p))[1])
    rows = closure.loaded_native_sources({"a": a, "alias": a})
    assert len(rows) == 2 and calls == [str(path)]


def test_unique_package_traversal_and_fresh_rehash(tmp_path, monkeypatch):
    root = tmp_path / "site-packages" / "native"
    root.mkdir(parents=True)
    a = root / "a.py"
    a.write_text("x=1")
    b = root / "b.py"
    b.write_text("x=2")
    rows = [{"source": str(a), "sha256": closure.sha(a)}] * 3
    calls = []
    original = preflight.sha
    monkeypatch.setattr(preflight, "sha", lambda p: (calls.append(str(p)), original(p))[1])
    files = preflight.capture_files({"files": []}, rows)
    assert calls == [str(b)] and len(files) == 2
    b.write_text("x=3")
    second = preflight.capture_files({"files": []}, rows)
    assert second[str(b)] != files[str(b)] and calls == [str(b), str(b)]


def test_foreign_origin_and_tamper_rejected(tmp_path):
    p = tmp_path / "native.py"
    p.write_text("x=1")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": [{"path": str(p), "sha256": closure.sha(p)}]}))
    cfg = {"native_dependency_manifest": str(manifest)}
    m = ModuleType("native")
    m.__file__ = str(p)
    assert closure.verify_native_dependencies(cfg, {"native": m})
    p.write_text("x=2")
    with pytest.raises(ImportError):
        closure.verify_native_dependencies(cfg, {"native": m})
    q = tmp_path / "ambient.py"
    q.write_text("x=1")
    m.__file__ = str(q)
    with pytest.raises(ImportError):
        closure.verify_native_dependencies(cfg, {"native": m})


def test_preflight_contract_binds_runtime_and_data():
    a = {
        "python": "p",
        "pairs": [1],
        "inputs": [{"path": "data", "sha256": "original"}],
        "status": "draft",
        "cpu_preflight_report": "proof",
    }
    b = dict(a, status="freeze", inputs=a["inputs"] + [{"path": "proof", "sha256": "self-cyclic"}])
    assert closure.contract_digest(a) == closure.contract_digest(b)
    assert closure.contract_digest(a) != closure.contract_digest(dict(a, python="foreign"))
    assert closure.contract_digest(a) != closure.contract_digest(dict(a, pairs=[2]))
    assert closure.contract_digest(a) != closure.contract_digest(
        dict(a, inputs=[{"path": "data", "sha256": "changed"}])
    )


def test_exact_generated_remote_identity_and_tamper(tmp_path):
    names = (
        "torch.distributed.nn.jit.instantiator",
        "torch.distributed.nn.api.remote_module",
        "torch.distributed.nn.jit.templates.remote_module_template",
    )
    modules = {}
    files = []
    for i, name in enumerate(names):
        p = tmp_path / f"parent{i}.py"
        p.write_text(f"x={i}")
        m = ModuleType(name)
        m.__file__ = str(p)
        modules[name] = m
        files.append({"path": str(p), "sha256": closure.sha(p)})
    p = tmp_path / "_remote_module_non_scriptable.py"
    p.write_text(
        "def forward_async(): return 1\ndef forward(): return 2\n_generated_methods = [forward_async, forward]\n"
    )
    generated = ModuleType("_remote_module_non_scriptable")
    generated.__file__ = str(p)
    exec(compile(p.read_bytes(), str(p), "exec"), generated.__dict__)
    modules[generated.__name__] = generated
    modules[names[0]].INSTANTIATED_TEMPLATE_DIR_PATH = str(tmp_path)
    modules[names[1]]._NON_SCRIPTABLE_REMOTE_MODULE_MODULE = generated
    manifest = {"files": files, "generated_remote_module": {"sha256": closure.sha(p)}}
    row = {"module": generated.__name__, "source": str(p), "sha256": closure.sha(p)}
    assert closure.verify_generated_remote(row, manifest, modules)["export_identity"]
    modules[names[1]]._NON_SCRIPTABLE_REMOTE_MODULE_MODULE = ModuleType("foreign")
    with pytest.raises(ImportError):
        closure.verify_generated_remote(row, manifest, modules)
    modules[names[1]]._NON_SCRIPTABLE_REMOTE_MODULE_MODULE = generated
    with pytest.raises(ImportError):
        closure.verify_generated_remote(dict(row, module="foreign"), manifest, modules)
    original = generated.forward
    generated.forward = generated.forward_async
    with pytest.raises(ImportError):
        closure.verify_generated_remote(row, manifest, modules)
    generated.forward = original
    parent = Path(files[0]["path"])
    previous = parent.read_bytes()
    parent.write_text("altered=1")
    with pytest.raises(ImportError):
        closure.verify_generated_remote(row, manifest, modules)
    parent.write_bytes(previous)
    p.write_text("value=2")
    row["sha256"] = closure.sha(p)
    with pytest.raises(ImportError):
        closure.verify_generated_remote(row, manifest, modules)
