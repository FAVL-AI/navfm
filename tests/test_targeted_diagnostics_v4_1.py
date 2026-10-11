"""Shared preflight schema coverage without host/runtime execution."""

import ast
import json
from pathlib import Path


def test_shared_freeze_keys_and_upstream_identity_preserved():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "scripts/development_qualification_contracts_v1.py").read_text())
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "frozen")
    keys = {
        n.slice.value
        for n in ast.walk(helper)
        if isinstance(n, ast.Subscript)
        and isinstance(n.value, ast.Name)
        and n.value.id == "cfg"
        and isinstance(n.slice, ast.Constant)
    }
    cfg = json.loads((root / "configs/eval/targeted_diagnostics_v4_1.json").read_text())
    assert keys <= cfg.keys()
    prior = json.loads((root / "configs/eval/nomad_compatibility_v3.json").read_text())
    for key in ["upstream", "upstream_files"]:
        assert cfg[key] == prior[key]
    original = json.loads((root / "configs/eval/targeted_diagnostics_v4.json").read_text())
    for key in original:
        if key != "status":
            assert cfg[key] == original[key]
