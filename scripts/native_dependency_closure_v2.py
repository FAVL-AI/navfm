"""File identity for the complete selected native training import closure."""

from __future__ import annotations

import hashlib
import json
import marshal
import sys
import sysconfig
from pathlib import Path
from types import CodeType, FunctionType, ModuleType

from development_qualification_contracts_v1 import sha


def contract_digest(cfg):
    selected = {k: v for k, v in cfg.items() if k != "status"}
    proof = cfg.get("cpu_preflight_report")
    selected["inputs"] = sorted(
        [dict(row) for row in cfg["inputs"] if row["path"] != proof],
        key=lambda row: row["path"],
    )
    return hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()


def loaded_native_sources(modules=None):
    modules = sys.modules if modules is None else modules
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    records = []
    digests = {}
    for name, module in sorted(list(modules.items())):
        if module is None:
            continue
        filename = vars(module).get("__file__")
        if not filename:
            continue  # strict selected Torch embedded-object authentication is separate
        path = Path(filename).resolve()
        if path.is_relative_to(stdlib) and "site-packages" not in path.parts:
            continue
        if str(path) not in digests:
            digests[str(path)] = sha(path)
        records.append({"module": name, "source": str(path), "sha256": digests[str(path)]})
    return records


def verify_generated_remote(row, manifest, modules):
    binding = manifest.get("generated_remote_module")
    if (
        row["module"] != "_remote_module_non_scriptable"
        or not binding
        or row["sha256"] != binding["sha256"]
    ):
        raise ImportError("unauthenticated generated dependency")
    expected = {x["path"]: x["sha256"] for x in manifest["files"]}
    for name in (
        "torch.distributed.nn.jit.instantiator",
        "torch.distributed.nn.api.remote_module",
        "torch.distributed.nn.jit.templates.remote_module_template",
    ):
        parent = modules.get(name)
        filename = vars(parent).get("__file__") if parent is not None else None
        if not filename or expected.get(str(Path(filename).resolve())) != sha(Path(filename)):
            raise ImportError("generated dependency parent origin/hash drift")
    instantiator = modules["torch.distributed.nn.jit.instantiator"]
    remote = modules["torch.distributed.nn.api.remote_module"]
    path = Path(row["source"])
    if (
        path.name != "_remote_module_non_scriptable.py"
        or path.parent != Path(vars(instantiator)["INSTANTIATED_TEMPLATE_DIR_PATH"]).resolve()
        or path.is_symlink()
        or vars(remote).get("_NON_SCRIPTABLE_REMOTE_MODULE_MODULE")
        is not modules.get(row["module"])
    ):
        raise ImportError("generated dependency identity/path drift")
    module = modules[row["module"]]
    if type(module) is not ModuleType:
        raise ImportError("generated dependency module kind drift")
    compiled = compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
    definitions = {code.co_name: code for code in compiled.co_consts if isinstance(code, CodeType)}
    for name, code in definitions.items():
        actual = vars(module).get(name)
        if not isinstance(actual, FunctionType) or marshal.dumps(actual.__code__) != marshal.dumps(
            code
        ):
            raise ImportError("generated dependency function slot/code drift")
    if vars(module).get("_generated_methods") != [
        vars(module).get("forward_async"),
        vars(module).get("forward"),
    ]:
        raise ImportError("generated dependency method exports drift")
    return {
        "module": row["module"],
        "sha256": row["sha256"],
        "generator": "authenticated torch.distributed.nn.jit.instantiator",
        "export_identity": True,
    }


def verify_native_dependencies(cfg, modules=None):
    modules = sys.modules if modules is None else modules
    manifest = json.loads(Path(cfg["native_dependency_manifest"]).read_text())
    expected = {x["path"]: x["sha256"] for x in manifest["files"]}
    records = loaded_native_sources(modules)
    for row in records:
        if expected.get(row["source"]) != row["sha256"]:
            row["generated_authentication"] = verify_generated_remote(row, manifest, modules)
    return records
