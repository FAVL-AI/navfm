"""Reuse the all-object CPU auditor with the reviewed finite v6 authentication."""

import sys

import dependency_import_audit_v5 as auditor
from authenticate_torch_wrappers_v6 import WRAPPERS, authenticate_wrapped_module
from nomad_dependency_boundary_v6 import verify_loaded_dependencies


def verify_one(manifest, modules, approved, digests):
    name = next(iter(modules))
    if name in WRAPPERS:
        return authenticate_wrapped_module(name, modules[name], sys.modules, approved, digests)
    return verify_loaded_dependencies(manifest, modules, approved, digests)


def verify_vf(module, binary, manifest, approved, digests):
    return authenticate_wrapped_module("torch._VF", module, sys.modules, approved, digests)


if __name__ == "__main__":
    auditor.verify_loaded_dependencies = verify_one
    auditor.authenticate_vf = verify_vf
    auditor.main()
