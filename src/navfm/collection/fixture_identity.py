"""Fixture identity for matched live runs against fixed goal photographs.

A fixed goal photograph is only a valid goal for a live episode when the live
scene is the scene that was photographed. This module builds a canonical
signature of everything that can change what the camera sees for one route
(scene prims, scene lights, camera mount and image settings) and compares it
with the signature of the goal-photo source collection. Any difference refuses
the run before execution.

USD extraction needs `pxr`, which is only importable inside a running Isaac
Sim app; signatures and comparison are pure Python.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

SIGNED_ATTRIBUTES = (
    "size",
    "xformOp:translate",
    "xformOp:scale",
    "xformOp:rotateXYZ",
    "xformOp:orient",
    "primvars:displayColor",
    "inputs:intensity",
    "inputs:color",
    "inputs:exposure",
    "inputs:angle",
)
GLOBAL_ROOTS = ("/World/Fixture/Sun", "/World/Fixture/Dome")


def scene_roots(scene_index: int) -> tuple[str, ...]:
    return (f"/World/Fixture/Scene{scene_index}", *GLOBAL_ROOTS)


def _plain(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, Iterable):
        return [_plain(v) for v in value]
    try:
        return _plain(list(value))
    except TypeError:
        return _plain(float(value))


def prim_signature(stage: Any, roots: Iterable[str]) -> dict[str, dict]:
    """Return {prim path: {type, api_schemas, attributes}} under the roots."""
    roots = tuple(roots)
    signature: dict[str, dict] = {}
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if not any(path == r or path.startswith(r + "/") for r in roots):
            continue
        attributes = {}
        for name in SIGNED_ATTRIBUTES:
            attribute = prim.GetAttribute(name)
            if attribute and attribute.HasAuthoredValue():
                value = attribute.Get()
                attributes[name] = _plain(
                    [value.real, *value.imaginary] if hasattr(value, "imaginary") else value
                )
        signature[path] = {
            "type": str(prim.GetTypeName()),
            "api_schemas": sorted(str(s) for s in prim.GetAppliedSchemas()),
            "attributes": attributes,
        }
    return signature


def camera_signature(manifest: Mapping) -> dict:
    robot = manifest["requested"]["robot"]
    return _plain(
        {
            "camera": robot["camera"],
            "camera_local_pose": manifest["camera_local_pose"],
            "resolution": manifest["requested"]["sim"].get("resolution"),
        }
    )


def digest(signature: Mapping) -> str:
    canonical = json.dumps(_plain(signature), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def compare(expected: Mapping, observed: Mapping, *, prefix: str = "") -> list[str]:
    """List every difference between two signatures; empty means identical."""
    differences = []
    for key in sorted(set(expected) | set(observed)):
        where = f"{prefix}{key}"
        if key not in observed:
            differences.append(f"missing in live: {where}")
        elif key not in expected:
            differences.append(f"absent from goal source: {where}")
        elif isinstance(expected[key], Mapping) and isinstance(observed[key], Mapping):
            differences.extend(compare(expected[key], observed[key], prefix=where + "."))
        elif _plain(expected[key]) != _plain(observed[key]):
            differences.append(f"changed: {where}: {expected[key]!r} -> {observed[key]!r}")
    return differences


def require_identical(expected: Mapping, observed: Mapping, *, what: str) -> None:
    differences = compare(expected, observed)
    if differences:
        shown = "; ".join(differences[:8])
        more = f" (+{len(differences) - 8} more)" if len(differences) > 8 else ""
        raise ValueError(f"{what} differs from goal-photo source: {shown}{more}")
