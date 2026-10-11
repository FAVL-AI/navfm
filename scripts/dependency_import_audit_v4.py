"""One bounded import-only provenance audit; no model or CUDA calls."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import marshal
import sys
import types
from pathlib import Path

from nomad_dependency_boundary_v3 import verify_loaded_dependencies


def authenticate_vf(module, binary, manifest):
    approved = {str(Path(x["path"]).resolve()): x["sha256"] for x in manifest["files"]}
    cls = type(module)
    constructor = vars(cls).get("__init__")
    getter = vars(cls).get("__getattr__")
    if constructor is None or getter is None:
        raise ImportError("VF class methods missing")
    path = Path(constructor.__code__.co_filename).resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    binary_path = Path(vars(binary)["__file__"]).resolve()
    binary_digest = hashlib.sha256(binary_path.read_bytes()).hexdigest()
    if approved.get(str(path)) != digest or approved.get(str(binary_path)) != binary_digest:
        raise ImportError("VF source or binary unauthenticated")
    tree = ast.parse(path.read_text(), filename=str(path))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "VFModule"]
    if len(classes) != 1:
        raise ImportError("VF source class boundary changed")
    namespace = {"types": types, "torch": types.SimpleNamespace(_C=binary)}
    exec(
        compile(ast.Module(body=classes, type_ignores=[]), str(path), "exec", dont_inherit=True),
        namespace,
    )
    expected = namespace["VFModule"]
    if (
        cls.__module__ != "torch._VF"
        or cls.__qualname__ != "VFModule"
        or constructor.__code__ != expected.__init__.__code__
        or getter.__code__ != expected.__getattr__.__code__
    ):
        raise ImportError("VF class code identity mismatch")
    if vars(module).get("vf") is not vars(binary).get("_VariableFunctions"):
        raise ImportError("VF underlying binary member mismatch")
    return {
        "source": str(path),
        "source_sha256": digest,
        "binary_source": str(binary_path),
        "binary_sha256": binary_digest,
        "binary_member": "_VariableFunctions",
        "identity": True,
    }


def audit(manifest, modules):
    records = []
    for name, module in sorted(list(modules.items())):
        if (
            name.split(".")[0]
            not in {"torch", "torchvision", "einops", "diffusers", "efficientnet_pytorch"}
            or module is None
        ):
            continue
        cls = type(module)
        record = {
            "module": name,
            "class_module": cls.__module__,
            "class_qualname": cls.__qualname__,
            "source": vars(module).get("__file__"),
        }
        record["class_method_code_sha256"] = {
            n: hashlib.sha256(marshal.dumps(f.__code__)).hexdigest()
            for n, f in vars(cls).items()
            if isinstance(f, types.FunctionType)
        }
        record["spec_origin"] = getattr(vars(module).get("__spec__"), "origin", None)
        record["class_method_origins"] = {
            n: f.__code__.co_filename
            for n, f in vars(cls).items()
            if isinstance(f, types.FunctionType)
        }
        try:
            if name == "torch._VF":
                if vars(modules["torch"]).get("_VF") is not module:
                    raise ImportError("VF exported module identity mismatch")
                record["provenance"] = authenticate_vf(module, modules["torch._C"], manifest)
            else:
                record["provenance"] = verify_loaded_dependencies(
                    manifest, {name: module, "torch._C": modules["torch._C"]}
                )
            record["status"] = "AUTHENTICATED"
        except BaseException as error:
            record.update(status="UNCLASSIFIED", error_type=type(error).__name__, error=str(error))
        records.append(record)
    return records


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    out = Path(a.out)
    if out.exists():
        raise ValueError("new evidence path required")
    manifest = json.loads(Path(a.manifest).read_text())
    import_errors = []
    for name in ["torch", "torchvision", "einops", "diffusers", "efficientnet_pytorch"]:
        try:
            importlib.import_module(name)
        except BaseException as error:
            import_errors.append(
                {"module": name, "error_type": type(error).__name__, "error": str(error)}
            )
    records = audit(manifest, sys.modules)
    out.write_text(
        json.dumps(
            {
                "import_errors": import_errors,
                "records": records,
                "count": len(records),
                "unclassified": sum(r["status"] != "AUTHENTICATED" for r in records),
                "scope": "IMPORT_ONLY_NO_MODEL_NO_CUDA_CALL",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
