"""Measure vendor collision meshes, and check colliders derived from them.

The authoritative production URDF supplies collision geometry as meshes, so
Decision B is not "what boxes look about right" but "what can be derived from
these meshes without inventing a dimension". Measuring a mesh is allowed and is
a measurement; the values it yields are vendor-mesh-derived and are never the
same thing as a dimension Yahboom states.

Reading is numpy-only and deliberately so. Binary STL is a fixed-layout format,
so the reader needs no geometry library, and that keeps every validation
control runnable in the ordinary test environment rather than only where a
heavier stack happens to be installed. Convex-hull measurement does need such a
stack, so it is optional and reports its own absence instead of silently
skipping.

The validator exists because of F-TWIN-1: Isaac's URDF importer was measured
squaring every box collider extent, and the check that was supposed to catch it
counted colliders instead of measuring them. A collider of the wrong size is
still one collider. So nothing here is allowed to pass on a count, on an
aggregate bound, or on a total volume: every comparison is per link, against
the source that link owns, bound to that source's hash.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

__all__ = [
    "REFUSAL_CATEGORIES",
    "ColliderRefused",
    "MeshMeasurement",
    "convex_hull_measure",
    "hull_backend",
    "measure_mesh",
    "read_binary_stl",
    "rotation_matrix",
    "transform_bounds",
    "validate_collider_set",
]

#: Every way a derived collider set can be refused. Named rather than boolean,
#: because "the wheel is 1000x too big" and "the wheel belongs to the wrong
#: link" need different repairs.
REFUSAL_CATEGORIES: tuple[str, ...] = (
    "DIMENSION_MISMATCH",
    "UNIT_SCALE_MISMATCH",
    "ORIENTATION_MISMATCH",
    "SOURCE_IDENTITY_MISMATCH",
    "MISSING_COLLIDER",
    "DUPLICATE_COLLIDER_OWNERSHIP",
    "UNEXPECTED_COLLIDER",
    "CONTAINMENT_VIOLATION",
    "NON_FINITE_GEOMETRY",
)

_STL_HEADER = 84
_STL_TRIANGLE = 50


class ColliderRefused(RuntimeError):
    """A stated refusal from the collider path, carrying a named category."""

    def __init__(self, category: str, detail: str) -> None:
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail


@dataclasses.dataclass(frozen=True)
class MeshMeasurement:
    """What a mesh is, measured. Every value here is mesh-derived."""

    path: str
    sha256: str
    mesh_format: str
    triangle_count: int
    vertex_count: int
    unique_vertex_count: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    extents: tuple[float, float, float]
    centroid: tuple[float, float, float]
    signed_volume: float
    is_closed_estimate: bool
    #: STL carries no unit declaration. Recorded so nobody later reads the
    #: numbers as metres because they happen to look like metres.
    unit_metadata: str = "ABSENT"
    evidence_class: str = "VENDOR_MESH_DERIVED_VALUE"

    def as_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def read_binary_stl(path: Path | str) -> np.ndarray:
    """Return an (N, 3, 3) array of triangle vertices. numpy only.

    Binary STL is 80 header bytes, a uint32 triangle count, then 50 bytes per
    triangle. The length check is what distinguishes it from ASCII, since an
    ASCII file's first bytes can look like anything.
    """
    target = Path(path)
    if not target.is_file():
        raise ColliderRefused("SOURCE_IDENTITY_MISMATCH", f"no mesh at {target}")
    raw = target.read_bytes()
    if len(raw) < _STL_HEADER:
        raise ColliderRefused("NON_FINITE_GEOMETRY", f"{target} is too short to be STL")

    count = int(struct.unpack("<I", raw[80:84])[0])
    expected = _STL_HEADER + _STL_TRIANGLE * count
    if len(raw) != expected:
        raise ColliderRefused(
            "NON_FINITE_GEOMETRY",
            f"{target} declares {count} triangles, which needs {expected} bytes, "
            f"but the file is {len(raw)}; it is not binary STL")

    body = np.frombuffer(raw, dtype=np.uint8, count=_STL_TRIANGLE * count,
                         offset=_STL_HEADER).reshape(count, _STL_TRIANGLE)
    # Bytes 12..48 of each record are the three vertices; 0..12 is the normal
    # and 48..50 the attribute count, both ignored.
    vertices = body[:, 12:48].copy().view(np.float32).reshape(count, 3, 3)
    return np.asarray(vertices, dtype=np.float64)


def measure_mesh(path: Path | str) -> MeshMeasurement:
    """Measure one mesh without modifying it."""
    target = Path(path)
    triangles = read_binary_stl(target)
    flat = triangles.reshape(-1, 3)
    if not np.isfinite(flat).all():
        raise ColliderRefused("NON_FINITE_GEOMETRY",
                              f"{target} contains non-finite vertices")

    low = flat.min(axis=0)
    high = flat.max(axis=0)
    # Signed volume by the divergence theorem. Meaningful only for a closed
    # surface, so whether it is closed is reported alongside it rather than
    # assumed.
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    signed = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)

    # Vertices are matched by value, which is how STL encodes shared corners:
    # it stores every triangle independently and leaves identity implicit.
    unique_rows, inverse = np.unique(flat, axis=0, return_inverse=True)
    indexed = inverse.reshape(-1, 3)
    edge_pairs = np.concatenate([indexed[:, [0, 1]], indexed[:, [1, 2]],
                                 indexed[:, [2, 0]]])
    _, counts = np.unique(np.sort(edge_pairs, axis=1), axis=0,
                          return_counts=True)
    closed = bool((counts == 2).all())
    unique = unique_rows

    return MeshMeasurement(
        path=str(target),
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        mesh_format="STL_BINARY",
        triangle_count=int(triangles.shape[0]),
        vertex_count=int(flat.shape[0]),
        unique_vertex_count=int(unique.shape[0]),
        bounds_min=tuple(float(v) for v in low),  # type: ignore[arg-type]
        bounds_max=tuple(float(v) for v in high),  # type: ignore[arg-type]
        extents=tuple(float(v) for v in (high - low)),  # type: ignore[arg-type]
        centroid=tuple(float(v) for v in flat.mean(axis=0)),  # type: ignore[arg-type]
        signed_volume=signed,
        is_closed_estimate=closed,
    )


def rotation_matrix(rpy: tuple[float, float, float]) -> np.ndarray:
    """URDF fixed-axis roll, pitch, yaw, applied as R = Rz @ Ry @ Rx."""
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


def transform_bounds(
    measurement: MeshMeasurement,
    xyz: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rpy: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> dict[str, Any]:
    """Bounds of the mesh's own corner set after the collision transform.

    The eight corners are rotated rather than the axis-aligned box being
    reused, because rotating a box and boxing a rotation are different answers
    and the second one silently grows.
    """
    low = np.asarray(measurement.bounds_min) * np.asarray(scale)
    high = np.asarray(measurement.bounds_max) * np.asarray(scale)
    corners = np.array([[x, y, z] for x in (low[0], high[0])
                        for y in (low[1], high[1])
                        for z in (low[2], high[2])])
    placed = corners @ rotation_matrix(rpy).T + np.asarray(xyz)
    return {
        "bounds_min": [float(v) for v in placed.min(axis=0)],
        "bounds_max": [float(v) for v in placed.max(axis=0)],
        "extents": [float(v) for v in (placed.max(axis=0) - placed.min(axis=0))],
        "method": "the mesh's eight corners are transformed, not its box",
    }


def hull_backend() -> dict[str, Any]:
    """Report whether convex-hull measurement is possible, rather than skipping."""
    try:
        import scipy
        from scipy.spatial import ConvexHull  # noqa: F401
    except ImportError as exc:
        return {"AVAILABLE": False, "backend": None, "reason": str(exc),
                "consequence": "convex-hull measurements are NOT_MEASURED here"}
    return {"AVAILABLE": True, "backend": "scipy.spatial.ConvexHull (Qhull)",
            "version": scipy.__version__}


def convex_hull_measure(vertices: np.ndarray) -> dict[str, Any]:
    """Convex hull of a vertex set, or a recorded absence.

    Qhull is deterministic for a fixed input and fixed options, so the hull is
    reproducible from the mesh hash. The options used are recorded with the
    result, because a hull computed under different options is a different hull.
    """
    backend = hull_backend()
    if not backend["AVAILABLE"]:
        return {"MEASURED": False, **backend}
    from scipy.spatial import ConvexHull

    points = np.unique(vertices.reshape(-1, 3), axis=0)
    hull = ConvexHull(points, qhull_options="Qt")
    low, high = points[hull.vertices].min(axis=0), points[hull.vertices].max(axis=0)
    return {
        "MEASURED": True,
        "backend": backend["backend"],
        "qhull_options": "Qt",
        "input_unique_vertices": int(points.shape[0]),
        "hull_vertex_count": int(len(hull.vertices)),
        "hull_facet_count": int(len(hull.simplices)),
        "hull_volume": float(hull.volume),
        "hull_area": float(hull.area),
        "hull_bounds_min": [float(v) for v in low],
        "hull_bounds_max": [float(v) for v in high],
        "hull_extents": [float(v) for v in (high - low)],
        "evidence_class": "VENDOR_MESH_DERIVED_VALUE",
    }


def validate_collider_set(
    source: dict[str, dict[str, Any]],
    generated: dict[str, dict[str, Any]],
    *,
    relative_tolerance: float = 1e-4,
    require_containment: bool = True,
) -> dict[str, Any]:
    """Compare a derived collider set against the source geometry, per link.

    Nothing passes on a count. F-TWIN-1 was a defect that a counting check
    certified as correct, so every comparison here is between one link's
    collider and the source that link owns, keyed by link and bound to the
    source mesh hash. Equal totals, equal aggregate bounds and equal volume are
    all insufficient by construction.
    """
    findings: list[dict[str, Any]] = []

    missing = sorted(set(source) - set(generated))
    for link in missing:
        findings.append({"category": "MISSING_COLLIDER", "link": link,
                         "detail": f"{link} has source collision geometry and no "
                                   "generated collider"})
    unexpected = sorted(set(generated) - set(source))
    for link in unexpected:
        findings.append({"category": "UNEXPECTED_COLLIDER", "link": link,
                         "detail": f"{link} has a generated collider and no source "
                                   "collision geometry"})

    owners: dict[str, list[str]] = {}
    for link, entry in generated.items():
        owners.setdefault(str(entry.get("source_sha256", "")), []).append(link)
    for sha, links in owners.items():
        expected_links = [k for k, v in source.items()
                          if str(v.get("sha256", "")) == sha]
        if len(links) > 1 and len(expected_links) <= 1:
            findings.append({
                "category": "DUPLICATE_COLLIDER_OWNERSHIP",
                "link": ", ".join(sorted(links)),
                "detail": f"{len(links)} links share source mesh {sha[:12]} which "
                          f"belongs to {expected_links or ['no link']}"})

    for link in sorted(set(source) & set(generated)):
        want, got = source[link], generated[link]

        if str(want.get("sha256")) != str(got.get("source_sha256")):
            findings.append({
                "category": "SOURCE_IDENTITY_MISMATCH", "link": link,
                "detail": f"collider for {link} cites source "
                          f"{str(got.get('source_sha256'))[:12]}, but {link} owns "
                          f"{str(want.get('sha256'))[:12]}"})
            continue

        expected = np.asarray(want["extents"], dtype=float)
        actual = np.asarray(got["extents"], dtype=float)
        if not np.isfinite(actual).all():
            findings.append({"category": "NON_FINITE_GEOMETRY", "link": link,
                             "detail": f"{link} collider extents are not finite"})
            continue

        if np.allclose(expected, actual, rtol=relative_tolerance, atol=1e-9):
            continue

        ratio = np.divide(actual, expected,
                          out=np.full_like(actual, np.nan),
                          where=np.abs(expected) > 1e-12)
        finite = ratio[np.isfinite(ratio)]
        category = "DIMENSION_MISMATCH"
        note = ""
        if finite.size and np.allclose(finite, finite[0], rtol=1e-3):
            factor = float(finite[0])
            for candidate, name in ((1000.0, "x1000"), (0.001, "/1000"),
                                    (100.0, "x100"), (0.01, "/100")):
                if math.isclose(factor, candidate, rel_tol=1e-3):
                    category, note = "UNIT_SCALE_MISMATCH", (
                        f"every axis is scaled by {name}, which is a unit error "
                        "rather than a geometry error")
                    break
        elif sorted(np.round(actual, 9).tolist()) == sorted(
                np.round(expected, 9).tolist()):
            category, note = "ORIENTATION_MISMATCH", (
                "the same extents appear on different axes, so the collider is "
                "permuted rather than resized")

        findings.append({
            "category": category, "link": link,
            "source_extents": [float(v) for v in expected],
            "generated_extents": [float(v) for v in actual],
            "per_axis_ratio": [None if not math.isfinite(v) else float(v)
                               for v in ratio],
            "detail": note or f"{link} collider extents differ from its source"})

        if require_containment and (actual < expected - 1e-9).any():
            findings.append({
                "category": "CONTAINMENT_VIOLATION", "link": link,
                "detail": f"{link} collider is smaller than its source geometry on "
                          "at least one axis, so it under-covers the robot"})

    return {
        "ADMITTED": not findings,
        "finding_count": len(findings),
        "findings": findings,
        "links_compared": len(set(source) & set(generated)),
        "relative_tolerance": relative_tolerance,
        "method": ("per link, against the source that link owns, keyed by link and "
                   "bound to the source mesh hash. Counts, aggregate bounds and "
                   "total volume are never sufficient"),
    }
