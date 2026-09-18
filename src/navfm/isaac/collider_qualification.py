"""Canonicalise and assess a convex decomposition of a vendor collision mesh.

A single convex hull was measured inflating the M3 Pro arm links by up to 4.7x
against a limit frozen at 1.25, so decomposition is the remaining route. What
has to be established about it is narrow: that it is reproducible, that each
piece stays with the link that owns it, and that the union neither leaves the
robot uncovered nor invents obstacle where the robot has none.

Two things shape the measurements here. Eight of the eighteen vendor meshes are
not closed surfaces, so enclosed volume is undefined for exactly the parts that
set the navigation footprint, and every metric is therefore surface-based and
works the same on open and closed input. And the previous adequacy rule
compared hull bounds against source bounds, which a convex hull can never fail
because its extreme points are the source's; nothing here is allowed to depend
on a comparison that cannot come out badly.

Sampling is exhaustive rather than random -- every source vertex, every
generated hull vertex -- so determinism needs no seed on this side of the
measurement and cannot be improved by drawing again.

Canonicalisation uses exact float64 bytes. Rounding would be a way of declaring
a result reproducible by refusing to look closely, so if quantisation ever
proves necessary it has to be frozen and argued for before determinism is
judged, not introduced when a digest fails to match.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

import numpy as np

__all__ = [
    "ACCEPTANCE_CONTRACT",
    "ConvexPart",
    "canonical_digest",
    "canonical_part_digest",
    "coverage_report",
    "distance_to_convex_union",
    "distance_to_triangles",
    "evaluate_acceptance",
]

#: Frozen before the full population is evaluated. Thresholds that cannot be
#: justified are left as None, and a metric with no threshold is reported
#: rather than silently treated as passing.
ACCEPTANCE_CONTRACT: dict[str, Any] = {
    "FROZEN_BEFORE_FULL_POPULATION": True,
    "determinism": {
        "requirement": "five fresh processes, same mesh hash, same package, same "
                       "parameters, same seed, different output directories, no "
                       "cache reuse, identical canonical digest",
        "threshold": "exact equality",
    },
    "link_ownership": {
        "requirement": "every convex part belongs to exactly one collision "
                       "element of exactly one link; no part spans links and no "
                       "part is shared",
        "threshold": "exact",
    },
    "completeness": {
        "requirement": "every collision element in the authoritative URDF has at "
                       "least one convex part, and no part exists for an element "
                       "that has none",
        "threshold": "exact",
    },
    "under_coverage": {
        "requirement": "no source vertex may lie outside the union of the convex "
                       "parts by more than the limit. Under-coverage means the "
                       "simulated robot is smaller than the vendor's model, which "
                       "is the unsafe direction for navigation",
        "metric": "max over source vertices of the distance outside the union",
        "threshold_m": 0.001,
        "justification": "one millimetre is below the manufacturing tolerance of "
                         "a hobby-grade chassis and far below any clearance the "
                         "navigation stack reasons about, so a breach of it "
                         "indicates a derivation error rather than approximation",
    },
    "over_coverage": {
        "requirement": "generated geometry must not invent obstacle far from the "
                       "vendor surface",
        "metric": "p95 over generated hull vertices of the distance to the "
                  "nearest source triangle, reported per link",
        "threshold_m": None,
        "why_no_threshold": (
            "a defensible universal limit does not exist: the admissible excess "
            "depends on the part's role, and picking one number after seeing "
            "eighteen results would be describing them rather than testing them. "
            "Reported per link and judged per role instead"),
    },
    "preprocessing_fidelity": {
        "requirement": "where CoACD remeshes a non-closed source, the deviation "
                       "between source and preprocessed surface is measured and "
                       "recorded as a derivation",
        "metric": "max, p95 and RMSE of the two-way surface distance",
        "threshold_m": None,
        "why_no_threshold": "same reason; measured and reported, not gated",
    },
    "complexity": {
        "requirement": "hull count and vertex count per link are recorded so a "
                       "later runtime cost question has the numbers it needs",
        "threshold": None,
    },
    "sampling": {
        "source_to_collider": "every source vertex, exhaustive",
        "collider_to_source": "every generated hull vertex, exhaustive",
        "why_exhaustive": "a deterministic measurement that cannot be improved by "
                          "drawing again, and needs no seed of its own",
    },
    "non_tautological": (
        "bounds agreement is excluded. A convex hull inherits the source extreme "
        "points, so that comparison cannot fail and is not evidence"),
}


@dataclasses.dataclass(frozen=True)
class ConvexPart:
    """One convex piece, bound to the collision element that owns it."""

    link: str
    source_sha256: str
    part_index: int
    vertices: np.ndarray
    faces: np.ndarray

    def __post_init__(self) -> None:
        if self.vertices.ndim != 2 or self.vertices.shape[1] != 3:
            raise ValueError("vertices must be (N, 3)")
        if self.faces.ndim != 2 or self.faces.shape[1] != 3:
            raise ValueError("faces must be (M, 3)")


def canonical_part_digest(part: ConvexPart) -> str:
    """Digest one convex part independently of how it was serialised.

    Vertices are sorted lexicographically and faces are renumbered against that
    order, then each face's indices are rotated to start at its smallest and the
    face list is sorted. Two files describing the same solid in different vertex
    or triangle order therefore digest the same, while any change to the solid
    changes the digest. Exact float64 bytes throughout; nothing is rounded.
    """
    vertices = np.ascontiguousarray(part.vertices, dtype=np.float64)
    order = np.lexsort((vertices[:, 2], vertices[:, 1], vertices[:, 0]))
    sorted_vertices = vertices[order]
    remap = np.empty(len(order), dtype=np.int64)
    remap[order] = np.arange(len(order), dtype=np.int64)

    faces = remap[np.asarray(part.faces, dtype=np.int64)]
    # Rotate each face to start at its smallest index, preserving winding, then
    # sort the list. Winding is kept because a flipped triangle is a different
    # solid, not a different spelling of the same one.
    shift = np.argmin(faces, axis=1)
    rows = np.arange(faces.shape[0])[:, None]
    columns = (shift[:, None] + np.arange(3)[None, :]) % 3
    rotated = faces[rows, columns]
    face_order = np.lexsort((rotated[:, 2], rotated[:, 1], rotated[:, 0]))
    canonical_faces = rotated[face_order]

    digest = hashlib.sha256()
    digest.update(b"navfm-convex-part-v1")
    digest.update(part.link.encode())
    digest.update(part.source_sha256.encode())
    digest.update(np.asarray(sorted_vertices, dtype=">f8").tobytes())
    digest.update(np.asarray(canonical_faces, dtype=">i8").tobytes())
    return digest.hexdigest()


def canonical_digest(parts: list[ConvexPart]) -> dict[str, Any]:
    """Digest a whole decomposition, independent of part ordering."""
    per_part = sorted(canonical_part_digest(p) for p in parts)
    by_link: dict[str, list[str]] = {}
    for part in parts:
        by_link.setdefault(part.link, []).append(canonical_part_digest(part))
    combined = hashlib.sha256()
    combined.update(b"navfm-convex-set-v1")
    for entry in per_part:
        combined.update(entry.encode())
    return {
        "digest": combined.hexdigest(),
        "part_count": len(parts),
        "part_digests": per_part,
        "per_link": {k: sorted(v) for k, v in sorted(by_link.items())},
        "method": ("vertices lexicographically sorted, faces renumbered and "
                   "rotated to a canonical start with winding preserved, part "
                   "digests sorted. Exact float64 bytes; no rounding"),
    }


def _closest_on_triangles(points: np.ndarray, a: np.ndarray, ab: np.ndarray,
                          ac: np.ndarray) -> np.ndarray:
    """Distance from each point to each triangle, by barycentric clamping."""
    block = points[:, None, :]
    ap = block - a[None, :, :]
    d1 = np.einsum("ijk,jk->ij", ap, ab)
    d2 = np.einsum("ijk,jk->ij", ap, ac)
    aa = np.einsum("jk,jk->j", ab, ab)[None, :]
    bb = np.einsum("jk,jk->j", ab, ac)[None, :]
    cc = np.einsum("jk,jk->j", ac, ac)[None, :]
    denominator = aa * cc - bb * bb
    safe = np.where(np.abs(denominator) < 1e-30, 1.0, denominator)
    s = np.clip((cc * d1 - bb * d2) / safe, 0.0, 1.0)
    t = np.clip((aa * d2 - bb * d1) / safe, 0.0, 1.0)
    over = s + t > 1.0
    scale = np.where(over, s + t, 1.0)
    s = np.where(over, s / scale, s)
    t = np.where(over, t / scale, t)
    closest = (a[None, :, :] + s[:, :, None] * ab[None, :, :]
               + t[:, :, None] * ac[None, :, :])
    return np.sqrt(((block - closest) ** 2).sum(axis=2))


def distance_to_triangles(points: np.ndarray, triangles: np.ndarray,
                          chunk: int = 256) -> np.ndarray:
    """Unsigned distance from each point to the nearest triangle. numpy only.

    A bounding-sphere bound prunes the search before any triangle distance is
    computed: the nearest triangle cannot be one whose sphere starts further
    away than the closest sphere ends. The bound is exact, so pruning changes
    the cost and not the answer, which is asserted against a brute-force pass in
    the controls. Without it, base_link's 172k triangles against its hull
    vertices is a matrix that does not fit in memory.
    """
    points = np.ascontiguousarray(points, dtype=np.float64)
    if points.shape[0] == 0 or triangles.shape[0] == 0:
        return np.zeros(points.shape[0], dtype=np.float64)

    a = np.ascontiguousarray(triangles[:, 0], dtype=np.float64)
    b = np.ascontiguousarray(triangles[:, 1], dtype=np.float64)
    c = np.ascontiguousarray(triangles[:, 2], dtype=np.float64)
    ab, ac = b - a, c - a

    centres = (a + b + c) / 3.0
    radii = np.sqrt(np.maximum.reduce([
        ((a - centres) ** 2).sum(axis=1), ((b - centres) ** 2).sum(axis=1),
        ((c - centres) ** 2).sum(axis=1)]))

    best = np.empty(points.shape[0], dtype=np.float64)
    for start in range(0, points.shape[0], chunk):
        block = points[start:start + chunk]
        to_centre = np.sqrt(
            ((block[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2))
        upper = (to_centre + radii[None, :]).min(axis=1)
        lower = to_centre - radii[None, :]
        for row in range(block.shape[0]):
            candidates = np.flatnonzero(lower[row] <= upper[row])
            distances = _closest_on_triangles(
                block[row:row + 1], a[candidates], ab[candidates],
                ac[candidates])
            best[start + row] = distances.min()
    return best


def distance_to_convex_union(points: np.ndarray,
                             hulls: list[tuple[np.ndarray, np.ndarray]]
                             ) -> np.ndarray:
    """Signed distance outside the union of convex hulls; 0 or less means inside.

    For one convex solid the distance outside is the largest signed distance to
    any of its face planes, which is exact and needs no nearest-face search. A
    point is inside the union when it is inside any single hull, so the union
    distance is the minimum across hulls.
    """
    points = np.ascontiguousarray(points, dtype=np.float64)
    if not hulls:
        return np.full(points.shape[0], np.inf)
    outside = np.full(points.shape[0], np.inf)

    for vertices, faces in hulls:
        v = np.ascontiguousarray(vertices, dtype=np.float64)
        tri = v[np.asarray(faces, dtype=np.int64)]
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        keep = lengths > 1e-18
        if not keep.any():
            continue
        normals = normals[keep] / lengths[keep][:, None]
        offsets = np.einsum("ij,ij->i", normals, tri[keep][:, 0])
        # Orient every plane outward using the hull's own centroid.
        centre = v.mean(axis=0)
        sign = np.where(normals @ centre - offsets > 0, -1.0, 1.0)
        normals = normals * sign[:, None]
        offsets = offsets * sign
        signed = (points @ normals.T - offsets[None, :]).max(axis=1)
        outside = np.minimum(outside, signed)
    return outside


def coverage_report(source_vertices: np.ndarray, source_triangles: np.ndarray,
                    hulls: list[tuple[np.ndarray, np.ndarray]]) -> dict[str, Any]:
    """Two-way surface agreement, reported without an aggregate hiding a local one."""
    outside = distance_to_convex_union(source_vertices, hulls)
    under = np.clip(outside, 0.0, None)

    hull_vertices = (np.concatenate([v for v, _ in hulls], axis=0)
                     if hulls else np.zeros((0, 3)))
    over = (distance_to_triangles(hull_vertices, source_triangles)
            if len(hull_vertices) else np.zeros(0))

    def stats(values: np.ndarray) -> dict[str, float | None]:
        if values.size == 0:
            return {"max": None, "p95": None, "rmse": None, "mean": None}
        return {
            "max": float(values.max()),
            "p95": float(np.percentile(values, 95)),
            "rmse": float(np.sqrt((values ** 2).mean())),
            "mean": float(values.mean()),
        }

    return {
        "source_vertices_sampled": int(source_vertices.shape[0]),
        "hull_vertices_sampled": int(hull_vertices.shape[0]),
        "under_coverage_m": stats(under),
        "source_vertices_outside_union": int((outside > 1e-9).sum()),
        "over_coverage_m": stats(over),
        "sampling": "exhaustive; every source vertex and every hull vertex",
        "aggregate_caveat": ("max is reported alongside p95 so a local breach "
                             "cannot be averaged away"),
    }


def evaluate_acceptance(per_link: dict[str, dict[str, Any]],
                        required_links: set[str],
                        determinism_ok: bool) -> dict[str, Any]:
    """Apply the frozen contract. Role failures are never averaged into a pass."""
    limit = ACCEPTANCE_CONTRACT["under_coverage"]["threshold_m"]
    failures: list[dict[str, Any]] = []

    missing = sorted(required_links - set(per_link))
    for link in missing:
        failures.append({"link": link, "reason": "MISSING_COLLIDER"})
    extra = sorted(set(per_link) - required_links)
    for link in extra:
        failures.append({"link": link, "reason": "UNEXPECTED_COLLIDER"})

    for link in sorted(required_links & set(per_link)):
        entry = per_link[link]
        worst = entry.get("coverage", {}).get("under_coverage_m", {}).get("max")
        if worst is None:
            failures.append({"link": link, "reason": "UNDER_COVERAGE_NOT_MEASURED"})
        elif worst > limit:
            failures.append({"link": link, "reason": "UNDER_COVERAGE_EXCEEDED",
                             "max_m": worst, "limit_m": limit})
        if not entry.get("parts"):
            failures.append({"link": link, "reason": "NO_CONVEX_PARTS"})

    if not determinism_ok:
        failures.append({"link": "*", "reason": "DETERMINISM_NOT_DEMONSTRATED"})

    return {
        "ACCEPTED": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "contract": ACCEPTANCE_CONTRACT,
        "no_aggregate_override": ("a failure on any link fails the set. There is "
                                  "no whole-robot score that can outvote it"),
    }
