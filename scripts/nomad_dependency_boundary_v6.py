"""Authenticated, closed diffusion namespace imports without ambient path admission."""

from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
from pathlib import Path


class SourceLoader(importlib.abc.Loader):
    def __init__(self, path, digest):
        self.path, self.digest = Path(path), digest

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        data = self.path.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.digest:
            raise ImportError("authenticated diffusion source drift")
        module.__file__ = str(self.path)
        exec(compile(data, str(self.path), "exec"), module.__dict__)


class DiffusionFinder(importlib.abc.MetaPathFinder):
    def __init__(self, root, files):
        self.root = Path(root)
        self.files = {item["module"]: item for item in files}
        self.packages = {
            "diffusion_policy",
            "diffusion_policy.model",
            "diffusion_policy.model.diffusion",
        }

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.packages:
            spec = importlib.machinery.ModuleSpec(fullname, None, is_package=True)
            spec.submodule_search_locations = [str(self.root / fullname.replace(".", "/"))]
            return spec
        if fullname.startswith("diffusion_policy."):
            if fullname not in self.files:
                raise ImportError("undeclared diffusion import")
            item = self.files[fullname]
            return importlib.util.spec_from_file_location(
                fullname,
                self.root / item["path"],
                loader=SourceLoader(self.root / item["path"], item["sha256"]),
            )
        return None


def install_boundary(root, files):
    if any(
        name == "diffusion_policy" or name.startswith("diffusion_policy.") for name in sys.modules
    ):
        raise ImportError("preloaded diffusion namespace refused")
    finder = DiffusionFinder(root, files)
    sys.meta_path.insert(0, finder)
    return finder


def verify_loaded_dependencies(manifest, modules=None, approved=None, digest_cache=None):
    """Bind actual loaded dependency sources, rather than distribution metadata alone."""
    modules = sys.modules if modules is None else modules
    if approved is None:
        approved = {str(Path(x["path"]).resolve()): x["sha256"] for x in manifest["files"]}
    if digest_cache is None:
        digest_cache = {}
    namespaces = {"torch", "torchvision", "einops", "diffusers", "efficientnet_pytorch"}
    records = []
    for name, module in sorted(list(modules.items())):
        if name.split(".")[0] not in namespaces or module is None:
            continue
        filename = vars(module).get("__file__")
        if not filename:
            if name.startswith("torch._C."):
                parent = modules.get("torch._C")
                parent_file = vars(parent).get("__file__") if parent is not None else None
                if not parent_file:
                    raise ImportError("embedded dependency lacks authenticated binary: " + name)
                parent_path = str(Path(parent_file).resolve())
                parent_digest = cached_digest(parent_path, digest_cache)
                nested = parent
                attribute_path = name[len("torch._C.") :]
                if name == "torch._C._dynamo.autograd_compiler":
                    attribute_path = "_dynamo.compiled_autograd"
                for part in attribute_path.split("."):
                    nested = vars(nested).get(part) if nested is not None else None
                if approved.get(parent_path) != parent_digest or nested is not module:
                    raise ImportError("embedded dependency identity mismatch: " + name)
                records.append(
                    {
                        "module": name,
                        "kind": "embedded_binary_module",
                        "parent_source": parent_path,
                        "parent_sha256": parent_digest,
                        "attribute_path": attribute_path,
                    }
                )
                continue
            from authenticate_torch_wrappers_v6 import authenticate_wrapped_module

            records.append(
                {
                    "module": name,
                    **authenticate_wrapped_module(name, module, modules, approved, digest_cache),
                }
            )
            continue
        path = str(Path(filename).resolve())
        digest = cached_digest(path, digest_cache)
        if approved.get(path) != digest:
            raise ImportError("loaded dependency outside authenticated manifest: " + name)
        records.append({"module": name, "source": path, "sha256": digest})
    return records


def cached_digest(path, cache):
    if path not in cache:
        cache[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return cache[path]
