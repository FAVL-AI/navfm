"""Native EMA math and authenticated integration negative controls."""

import ast
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import native_ema_integration_v3 as repair


def binding():
    # Bind the packages this interpreter actually imports. authenticated_ema_class checks
    # each loaded module's file against this binding, so a fixed workstation path could only
    # ever pass inside the workstation's Isaac interpreter.
    import importlib.util

    root = Path(importlib.util.find_spec("diffusers").origin).resolve().parents[1]
    return {
        role: {"path": str(root / path), "sha256": repair.sha(root / path)}
        for role, path in [
            ("diffusers", "diffusers/training_utils.py"),
            ("transformers", "transformers/integrations/deepspeed.py"),
        ]
    }


@pytest.mark.torch
def test_native_shadow_counter_and_serialized_next_update():
    result = repair.cpu_ema_control(binding())
    assert result["status"] == "PASS" and result["counter_readbacks"] == [1, 2]
    assert result["frozen_parameter_copy"] and result["save_restore_next_update_equal"]


@pytest.mark.torch
def test_only_two_lookup_nodes_change():
    source = Path(binding()["diffusers"]["path"]).read_text()
    cls = next(
        n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "EMAModel"
    )
    original = copy.deepcopy(
        next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "step")
    )
    patched = repair.patched_step_tree(source).body[0]

    class Reverse(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id == "approved_deepspeed_api":
                return ast.Attribute(
                    value=ast.Name(id="transformers", ctx=ast.Load()),
                    attr="deepspeed",
                    ctx=ast.Load(),
                )
            return node

    assert ast.dump(Reverse().visit(patched)) == ast.dump(original)
    with pytest.raises(ValueError, match="exactly two"):
        repair.patched_step_tree(source.replace("transformers.deepspeed", "other.deepspeed"))


@pytest.mark.torch
def test_source_hash_tamper_rejected():
    rows = binding()
    rows["diffusers"]["sha256"] = "0" * 64
    with pytest.raises(ImportError, match="origin/hash"):
        repair.authenticated_ema_class(rows)


@pytest.mark.torch
def test_loaded_api_code_tamper_rejected(monkeypatch):
    import transformers.integrations.deepspeed as api

    monkeypatch.setattr(api, "is_deepspeed_zero3_enabled", lambda: False)
    with pytest.raises(ImportError, match="API code drift"):
        repair.authenticated_ema_class(binding())


@pytest.mark.torch
def test_loaded_native_math_tamper_rejected(monkeypatch):
    import diffusers.training_utils as training
    import torch

    monkeypatch.setattr(training.EMAModel, "step", torch.no_grad()(lambda self, params: None))
    with pytest.raises(ImportError, match="step code drift"):
        repair.authenticated_ema_class(binding())
