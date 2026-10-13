"""Authenticated native EMA step with the current integration API lookup only."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
from pathlib import Path
from types import CodeType

from development_qualification_contracts_v1 import sha


def definition(code, name):
    return next(x for x in code.co_consts if isinstance(x, CodeType) and x.co_name == name)


def patched_step_tree(source):
    tree = ast.parse(source)
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "EMAModel")
    step = copy.deepcopy(
        next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == "step")
    )

    class Replace(ast.NodeTransformer):
        count = 0

        def visit_Attribute(self, node):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "transformers"
                and node.attr == "deepspeed"
            ):
                self.count += 1
                return ast.copy_location(
                    ast.Name(id="approved_deepspeed_api", ctx=ast.Load()), node
                )
            return self.generic_visit(node)

    transform = Replace()
    step = transform.visit(step)
    if transform.count != 2:
        raise ValueError("expected exactly two native integration lookups")
    return ast.fix_missing_locations(ast.Module(body=[step], type_ignores=[]))


def authenticated_ema_class(binding):
    training = importlib.import_module("diffusers.training_utils")
    api = importlib.import_module("transformers.integrations.deepspeed")
    for role, module in [("diffusers", training), ("transformers", api)]:
        row = binding[role]
        path = Path(module.__file__).resolve()
        if str(path) != row["path"] or sha(path) != row["sha256"]:
            raise ImportError("EMA integration source origin/hash drift")
    source = Path(training.__file__).read_text()
    compiled = compile(source, str(Path(training.__file__).resolve()), "exec", dont_inherit=True)
    expected = definition(definition(compiled, "EMAModel"), "step")
    original = training.EMAModel.step.__wrapped__
    if original.__code__ != expected:
        raise ImportError("native EMA loaded step code drift")
    api_source = Path(api.__file__).read_text()
    expected_api = definition(
        compile(api_source, str(Path(api.__file__).resolve()), "exec", dont_inherit=True),
        "is_deepspeed_zero3_enabled",
    )
    if api.is_deepspeed_zero3_enabled.__code__ != expected_api:
        raise ImportError("EMA integration loaded API code drift")
    if api.is_deepspeed_zero3_enabled():
        raise RuntimeError("single-device smoke does not configure DeepSpeed")
    tree = patched_step_tree(source)
    namespace = dict(original.__globals__, approved_deepspeed_api=api)
    exec(
        compile(
            tree,
            str(Path(training.__file__).resolve()) + ":native_ema_v3",
            "exec",
            dont_inherit=True,
        ),
        namespace,
    )
    result = type("NativeEMAIntegrationV3", (training.EMAModel,), {"step": namespace["step"]})
    result.integration_provenance = {
        "diffusers": binding["diffusers"],
        "transformers": binding["transformers"],
        "lookup_replacements": 2,
        "adapter_sha256": sha(Path(__file__)),
        "patched_ast_sha256": hashlib.sha256(
            ast.dump(tree, include_attributes=False).encode()
        ).hexdigest(),
    }
    return result


def cpu_ema_control(binding):
    import io

    import torch

    cls = authenticated_ema_class(binding)
    p = torch.nn.Parameter(torch.tensor([1.0, -2.0]))
    fixed = torch.nn.Parameter(torch.tensor([7.0]), requires_grad=False)
    ema = cls([p, fixed], power=0.75, use_ema_warmup=True)
    with torch.no_grad():
        p.copy_(torch.tensor([3.0, 4.0]))
        fixed.copy_(torch.tensor([8.0]))
    ema.step([p, fixed])
    assert (
        ema.optimization_step == 1
        and torch.equal(ema.shadow_params[0], p)
        and torch.equal(ema.shadow_params[1], fixed)
    )
    saved = io.BytesIO()
    torch.save(ema.state_dict(), saved)
    saved.seek(0)
    restored = cls([p, fixed], power=0.75, use_ema_warmup=True)
    restored.load_state_dict(torch.load(saved, map_location="cpu", weights_only=True))
    with torch.no_grad():
        p.copy_(torch.tensor([5.0, -4.0]))
        fixed.copy_(torch.tensor([9.0]))
    old = ema.shadow_params[0].clone()
    decay = 1 - 2 ** (-0.75)
    expected = old - (1 - decay) * (old - p)
    ema.step([p, fixed])
    restored.step([p, fixed])
    assert ema.optimization_step == restored.optimization_step == 2
    assert torch.equal(ema.shadow_params[0], expected) and torch.equal(ema.shadow_params[1], fixed)
    assert all(
        torch.equal(a, b) for a, b in zip(ema.shadow_params, restored.shadow_params, strict=True)
    )
    assert ema.cur_decay_value == decay and not ema.shadow_params[0].requires_grad
    return {
        "status": "PASS",
        "counter_readbacks": [1, 2],
        "shadow_values_match_native_formula": True,
        "frozen_parameter_copy": True,
        "save_restore_next_update_equal": True,
        "integration": cls.integration_provenance,
    }
