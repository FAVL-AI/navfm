import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from development_qualification_contracts_v1 import sha
from native_dependency_closure_v2 import verify_native_dependencies


def test_original_verifier_exact_entry_and_all_three_rejections(tmp_path):
    origin = tmp_path / "vint.py"
    origin.write_text("native=1\n")
    original_sha = sha(origin)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": [{"path": str(origin), "sha256": original_sha}]}))
    cfg = {"native_dependency_manifest": str(manifest)}
    module = ModuleType("vint_train.models.vint.vint")
    module.__file__ = str(origin)
    assert verify_native_dependencies(cfg, {module.__name__: module})[0]["sha256"] == original_sha
    origin.write_text("native=2\n")
    with pytest.raises(ImportError):
        verify_native_dependencies(cfg, {module.__name__: module})
    foreign = tmp_path / "foreign.py"
    foreign.write_text("native=1\n")
    module.__file__ = str(foreign)
    with pytest.raises(ImportError):
        verify_native_dependencies(cfg, {module.__name__: module})
    module.__file__ = str(origin)
    origin.write_text("native=1\n")
    extra = ModuleType("unexpected")
    extra.__file__ = str(foreign)
    with pytest.raises(ImportError):
        verify_native_dependencies(cfg, {module.__name__: module, extra.__name__: extra})
