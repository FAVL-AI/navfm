"""Authenticate the finite observed PyTorch module-wrapper shapes without execution."""

from __future__ import annotations

import ast
import types
from pathlib import Path

from nomad_dependency_boundary_v5 import cached_digest

WRAPPERS = {
    "torch._VF": ("torch._VF", "VFModule"),
    "torch.ops": ("torch._ops", "_Ops"),
    "torch.classes": ("torch._classes", "_Classes"),
    "torch.backends.cudnn": ("torch.backends.cudnn", "CudnnModule"),
    "torch.backends.mkldnn": ("torch.backends.mkldnn", "MkldnnModule"),
    "torch.backends.quantized": ("torch.backends.quantized", "QuantizedEngine"),
}


def nested_codes(code):
    yield code
    for item in code.co_consts:
        if isinstance(item, types.CodeType):
            yield from nested_codes(item)


def authenticate_wrapped_module(name, module, modules, approved, digests):
    if name not in WRAPPERS:
        raise ImportError("undeclared module wrapper")
    cls = type(module)
    if (cls.__module__, cls.__qualname__) != WRAPPERS[name]:
        raise ImportError("wrapper class identity mismatch")
    torch = modules["torch"]
    binary = modules["torch._C"]
    binary_path = str(Path(vars(binary)["__file__"]).resolve())
    binary_hash = cached_digest(binary_path, digests)
    if approved.get(binary_path) != binary_hash:
        raise ImportError("wrapper binary mismatch")
    parent_name, attribute = name.rsplit(".", 1)
    if vars(modules[parent_name]).get(attribute) is not module:
        raise ImportError("wrapper exported identity mismatch")
    compiled = {}
    methods = []
    descriptors = []

    def check_function(function, owner, slot):
        code = function.__code__
        path = str(Path(code.co_filename).resolve())
        digest = cached_digest(path, digests)
        if approved.get(path) != digest:
            raise ImportError("wrapper method source mismatch")
        if path not in compiled:
            compiled[path] = list(
                nested_codes(compile(Path(path).read_text(), path, "exec", dont_inherit=True))
            )
        if not any(
            code == expected and expected.co_qualname == f"{owner.__qualname__}.{slot}"
            for expected in compiled[path]
        ):
            raise ImportError("wrapper method code mismatch")
        if "torch" in function.__globals__ and function.__globals__["torch"] is not torch:
            raise ImportError("wrapper global torch identity mismatch")
        methods.append({"qualname": code.co_qualname, "source": path, "sha256": digest})

    seen = set()

    def check_class(candidate):
        if candidate in seen:
            return
        seen.add(candidate)
        for ancestor in candidate.__mro__:
            if ancestor in (object, types.ModuleType):
                continue
            own_functions = [
                v for v in vars(ancestor).values() if isinstance(v, types.FunctionType)
            ]
            if not own_functions:
                raise ImportError("wrapper class definition missing")
            origin = own_functions[0]
            path = str(Path(origin.__code__.co_filename).resolve())
            if approved.get(path) != cached_digest(path, digests):
                raise ImportError("wrapper class source mismatch")
            definitions = [
                n
                for n in ast.walk(ast.parse(Path(path).read_text()))
                if isinstance(n, ast.ClassDef) and n.name == ancestor.__name__
            ]
            if len(definitions) != 1 or origin.__globals__.get(ancestor.__name__) is not ancestor:
                raise ImportError("wrapper class definition identity mismatch")
            definition = definitions[0]

            def resolve(expression, namespace=origin.__globals__):
                if isinstance(expression, ast.Name):
                    return namespace.get(expression.id)
                if isinstance(expression, ast.Attribute):
                    parent = resolve(expression.value)
                    return vars(parent).get(expression.attr) if parent is not None else None
                return None

            expected_bases = tuple(resolve(base) for base in definition.bases) or (object,)
            if ancestor.__bases__ != expected_bases:
                raise ImportError("wrapper class bases mismatch")
            expected_slots = {}
            descriptor_calls = {}

            def declarations(
                nodes, expected_slots=expected_slots, descriptor_calls=descriptor_calls
            ):
                for node in nodes:
                    if isinstance(node, ast.FunctionDef):
                        kind = "property" if node.decorator_list else "method"
                        expected_slots[node.name] = kind
                    elif isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                                descriptor_calls[target.id] = node.value
                    elif isinstance(node, ast.If):
                        declarations(node.body)
                        declarations(node.orelse)

            declarations(definition.body)
            actual_slots = {
                key: "method" if isinstance(value, types.FunctionType) else "property"
                for key, value in vars(ancestor).items()
                if isinstance(value, (types.FunctionType, property))
            }
            if actual_slots != expected_slots:
                raise ImportError("wrapper class attribute slots mismatch")
            for slot, call in descriptor_calls.items():
                expected_class = resolve(call.func)
                if (
                    isinstance(expected_class, type)
                    and hasattr(expected_class, "__get__")
                    and (
                        slot not in vars(ancestor)
                        or type(vars(ancestor)[slot]) is not expected_class
                    )
                ):
                    raise ImportError("descriptor attribute slot mismatch")
            for slot, value in vars(ancestor).items():
                if isinstance(value, types.FunctionType):
                    check_function(value, ancestor, slot)
                elif isinstance(value, property):
                    for f in [value.fget, value.fset, value.fdel]:
                        if f is not None:
                            check_function(f, ancestor, slot)
                elif type(value).__module__.startswith("torch.") and hasattr(
                    type(value), "__get__"
                ):
                    call = descriptor_calls.get(slot)
                    if call is None or not isinstance(call.func, ast.Name):
                        raise ImportError("descriptor definition slot mismatch")
                    if origin.__globals__.get(call.func.id) is not type(value):
                        raise ImportError("descriptor class identity mismatch")
                    check_class(type(value))
                    descriptors.append(type(value).__qualname__)
                    fields = [field for field in ["getter", "setter"] if field in vars(value)]
                    if fields and (fields != ["getter", "setter"] or len(call.args) != 2):
                        raise ImportError("descriptor binary slots mismatch")
                    for field, argument in zip(fields, call.args, strict=False):
                        if (
                            not isinstance(argument, ast.Attribute)
                            or not isinstance(argument.value, ast.Attribute)
                            or argument.value.attr != "_C"
                            or not isinstance(argument.value.value, ast.Name)
                            or argument.value.value.id != "torch"
                            or argument.attr not in vars(binary)
                            or vars(value)[field] is not vars(binary)[argument.attr]
                        ):
                            raise ImportError("descriptor binary member mismatch")

    check_class(cls)
    definition_module = modules.get(cls.__module__)
    constructor = vars(cls)["__init__"]
    if name.startswith("torch.backends."):
        original = vars(module).get("m")
        if (
            type(original) is not types.ModuleType
            or vars(original) is not constructor.__globals__
            or vars(original).get(cls.__name__) is not cls
        ):
            raise ImportError("wrapped original module identity mismatch")
        original_path = str(Path(vars(original)["__file__"]).resolve())
        if approved.get(original_path) != cached_digest(original_path, digests):
            raise ImportError("wrapped original source mismatch")
    elif name == "torch._VF":
        if vars(module).get("vf") is not vars(binary).get("_VariableFunctions"):
            raise ImportError("VF binary member mismatch")
        if constructor.__globals__.get(cls.__name__) is not cls:
            raise ImportError("VF definition identity mismatch")
    else:
        if (
            definition_module is None
            or vars(definition_module).get(cls.__name__) is not cls
            or vars(definition_module).get(attribute) is not module
        ):
            raise ImportError("ops/classes definition identity mismatch")
    return {
        "kind": "authenticated_module_wrapper",
        "methods": methods,
        "descriptors": descriptors,
        "binary_source": binary_path,
        "binary_sha256": binary_hash,
        "export_identity": True,
        "wrapper": name,
    }
