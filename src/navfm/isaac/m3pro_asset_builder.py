"""Deterministic collider reconstruction, validation and provenance.

F-TWIN-1 recorded Isaac's URDF importer squaring every box collider extent: the
chassis loaded as 84 x 55 x 6.4 mm instead of 290 x 235 x 80 mm, agreeing with
the square of the source value to eight significant figures on four independent
quantities. Cylinders were correct. Re-running the builder reproduced it.

So the admitted collision geometry is not taken from the import. It is
reconstructed from the source description, and then the import is *checked*
against that reconstruction. The two directions matter: deriving a correction by
inverting the defect would make the result agree with the importer, and the
importer is the thing under suspicion.

F-TWIN-1 also recorded why the original builder missed it -- it ran a census
counting rigid bodies, colliders and joints, and "counting is not measuring. A
collider of the wrong size is still one collider." Every check here compares
numbers.

Nothing in this module chooses an apparatus. It refuses to mark anything
production-admissible unless the caller supplies authoritative-source provenance,
and a reference input can never acquire that by being passed in twice.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from navfm.isaac.urdf_import import SourceModel

__all__ = [
    "AssetBuildRefused",
    "ColliderSpec",
    "ObservedCollider",
    "SourceRole",
    "emit_provenance",
    "reconstruct_colliders",
    "request_production_admission",
    "validate_colliders",
]

#: Absolute metres. Tight, because these are authored primitives rather than
#: measured ones: a millimetre of disagreement means the number was computed
#: differently, not observed differently. Declared before any failure is seen.
DIMENSION_TOLERANCE_M = 1e-6
TRANSFORM_TOLERANCE_M = 1e-6
ROTATION_TOLERANCE_RAD = 1e-6

#: A ratio this far from 1 is reported as a scale fault rather than a plain
#: dimension fault, so an operator is told which kind of wrong it is.
SCALE_FAULT_RATIO = 4.0


class SourceRole:
    """What a source description is allowed to be used for."""

    REFERENCE_ONLY = "REFERENCE_ONLY"
    AUTHORITATIVE = "AUTHORITATIVE"


class AssetBuildRefused(RuntimeError):
    """A stated refusal from the build/admission path, with a named category."""

    def __init__(self, category: str, detail: str) -> None:
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail


@dataclasses.dataclass(frozen=True)
class ColliderSpec:
    """What a collider must be, derived from the source and nothing else."""

    source_identity: str
    link: str
    usd_path: str
    primitive: str
    dimensions: tuple[float, ...]
    translation: tuple[float, float, float]
    rotation_rpy: tuple[float, float, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_identity": self.source_identity, "link": self.link,
            "usd_path": self.usd_path, "primitive": self.primitive,
            "dimensions": list(self.dimensions),
            "translation": list(self.translation),
            "rotation_rpy": list(self.rotation_rpy),
        }


@dataclasses.dataclass(frozen=True)
class ObservedCollider:
    """What a USD actually contains, however it got there."""

    usd_path: str
    link: str
    primitive: str
    dimensions: tuple[float, ...]
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_rpy: tuple[float, float, float] = (0.0, 0.0, 0.0)


def reconstruct_colliders(
    model: SourceModel, *, root_prim: str = "/m3pro"
) -> tuple[ColliderSpec, ...]:
    """Source collision elements -> intended USD collider specifications.

    Pure and deterministic: no Isaac process, no filesystem, no import. That is
    what lets the reconstruction be unit-tested against hand-checked numbers
    rather than against whatever the importer happened to produce.
    """
    if not model.collisions:
        raise AssetBuildRefused(
            "NO_COLLISION_GEOMETRY",
            f"{model.path} declares no collision elements; there is nothing to "
            "reconstruct and nothing an admitted asset could be checked against")

    specs: list[ColliderSpec] = []
    for element in model.collisions:
        specs.append(ColliderSpec(
            source_identity=element.identity,
            link=element.link,
            usd_path=f"{root_prim}/{element.link}/collisions/collision_{element.index}",
            primitive=element.primitive,
            # Carried across unchanged. The source value IS the intended value;
            # any arithmetic here would be a place for a defect to enter.
            dimensions=tuple(element.dimensions),
            translation=element.origin_xyz,
            rotation_rpy=element.origin_rpy,
        ))
    return tuple(specs)


def _close(a: float, b: float, tol: float) -> bool:
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= tol


def _scale_ratio(expected: tuple[float, ...], observed: tuple[float, ...]) -> float | None:
    """A single consistent factor between the two, if there is one."""
    ratios = [o / e for e, o in zip(expected, observed, strict=False) if e]
    if not ratios:
        return None
    if max(ratios) - min(ratios) > 1e-6 * max(1.0, max(ratios)):
        return None
    return ratios[0]


def validate_colliders(
    expected: tuple[ColliderSpec, ...],
    observed: tuple[ObservedCollider, ...],
) -> dict[str, Any]:
    """Compare every collider numerically. Counting is not measuring."""
    by_path = {o.usd_path: o for o in observed}
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for spec in expected:
        found = by_path.get(spec.usd_path)
        row: dict[str, Any] = {
            "usd_path": spec.usd_path, "source_identity": spec.source_identity,
            "expected": spec.as_dict(),
        }
        if found is None:
            row.update({"VERDICT": "FAIL", "category": "COLLIDER_MISSING",
                        "detail": "no collider at the expected prim path"})
            results.append(row)
            failures.append("COLLIDER_MISSING")
            continue

        row["observed"] = {
            "primitive": found.primitive, "dimensions": list(found.dimensions),
            "translation": list(found.translation),
            "rotation_rpy": list(found.rotation_rpy), "link": found.link}

        if found.link != spec.link:
            category = "COLLIDER_OWNERSHIP_MISMATCH"
            detail = f"collider belongs to {found.link!r}, source says {spec.link!r}"
        elif found.primitive != spec.primitive:
            category = "COLLIDER_PRIMITIVE_MISMATCH"
            detail = f"{found.primitive!r} where the source declares {spec.primitive!r}"
        elif len(found.dimensions) != len(spec.dimensions) or not all(
                _close(e, o, DIMENSION_TOLERANCE_M)
                for e, o in zip(spec.dimensions, found.dimensions, strict=False)):
            ratio = _scale_ratio(spec.dimensions, found.dimensions)
            if ratio is not None and (ratio > SCALE_FAULT_RATIO
                                      or ratio < 1.0 / SCALE_FAULT_RATIO):
                category = "SCALE_OR_DIMENSION_MISMATCH"
                detail = (f"every dimension is off by the same factor {ratio:g}; "
                          "this is a unit or scale fault, not a per-value error")
            else:
                category = "COLLIDER_DIMENSION_MISMATCH"
                detail = (f"expected {list(spec.dimensions)}, "
                          f"observed {list(found.dimensions)}")
                squares = [e * e for e in spec.dimensions]
                if all(_close(s, o, DIMENSION_TOLERANCE_M)
                       for s, o in zip(squares, found.dimensions, strict=False)):
                    detail += (". Each observed value is the square of the source "
                               "value -- the F-TWIN-1 defect")
        elif not all(_close(e, o, TRANSFORM_TOLERANCE_M)
                     for e, o in zip(spec.translation, found.translation, strict=False)):
            category = "COLLIDER_TRANSFORM_MISMATCH"
            detail = (f"translation {list(found.translation)} where the source says "
                      f"{list(spec.translation)}")
        elif not all(_close(e, o, ROTATION_TOLERANCE_RAD)
                     for e, o in zip(spec.rotation_rpy, found.rotation_rpy,
                                     strict=False)):
            category = "COLLIDER_TRANSFORM_MISMATCH"
            detail = (f"rotation {list(found.rotation_rpy)} where the source says "
                      f"{list(spec.rotation_rpy)}")
        else:
            category = ""
            detail = "dimensions, transform, primitive and ownership all agree"

        row.update({"VERDICT": "FAIL" if category else "PASS",
                    "category": category or None, "detail": detail})
        results.append(row)
        if category:
            failures.append(category)

    unexpected = [o.usd_path for o in observed
                  if o.usd_path not in {s.usd_path for s in expected}]
    for path in unexpected:
        results.append({"usd_path": path, "VERDICT": "FAIL",
                        "category": "COLLIDER_UNEXPECTED",
                        "detail": "present in the asset and absent from the source"})
        failures.append("COLLIDER_UNEXPECTED")

    return {
        "COLLIDER_VALIDATION": "PASS" if not failures else "FAIL",
        "expected_count": len(expected),
        "observed_count": len(observed),
        "failure_categories": sorted(set(failures)),
        "results": results,
        "method": ("every collider compared on primitive type, each dimension, "
                   "translation, rotation and owning link. A count is not a check"),
        "tolerances_m": {"dimension": DIMENSION_TOLERANCE_M,
                         "translation": TRANSFORM_TOLERANCE_M,
                         "rotation_rad": ROTATION_TOLERANCE_RAD},
    }


def emit_provenance(
    *,
    model: SourceModel,
    closure: dict[str, Any],
    source_role: str,
    specs: tuple[ColliderSpec, ...],
    validation: dict[str, Any] | None = None,
    importer: dict[str, Any] | None = None,
    raw_import_sha256: str | None = None,
    corrected_sha256: str | None = None,
    repository_head: str | None = None,
) -> dict[str, Any]:
    """The asset sidecar. Records what produced an asset, and what it may be used for."""
    if source_role not in (SourceRole.REFERENCE_ONLY, SourceRole.AUTHORITATIVE):
        raise AssetBuildRefused(
            "UNKNOWN_SOURCE_ROLE",
            f"{source_role!r} is not a source role this builder recognises")

    admissible = source_role == SourceRole.AUTHORITATIVE
    return {
        "check": "M3PRO_ASSET_PROVENANCE",
        "author": "Frank Asante Van Laarhoven",
        "source_role": source_role,
        "production_admissible": admissible,
        "why_not_admissible": None if admissible else (
            "this asset was built from a reference input. A reference description "
            "can validate the machinery; it cannot become the apparatus"),
        "repository_head": repository_head,
        "source": {"path": model.path, "sha256": model.sha256,
                   "robot_name": model.robot_name,
                   "link_count": len(model.links),
                   "joint_count": len(model.joints),
                   "collision_count": len(model.collisions)},
        "source_closure": {"member_count": closure["member_count"],
                           "closure_digest": closure["closure_digest"],
                           "external_reference_count":
                               closure["external_reference_count"]},
        "collider_specification": [s.as_dict() for s in specs],
        "collider_specification_digest": hashlib.sha256(
            json.dumps([s.as_dict() for s in specs], sort_keys=True).encode()
        ).hexdigest(),
        "importer": importer,
        "raw_import": {"sha256": raw_import_sha256,
                       "role": "RAW_IMPORT_DIAGNOSTIC",
                       "note": ("kept for comparison with the source-derived "
                                "reconstruction. Never the admitted geometry")},
        "corrected_asset": {"sha256": corrected_sha256},
        "validation": validation,
        "vendor_acquisition": {
            "source_url": "PENDING", "acquisition_timestamp": "PENDING",
            "archive_sha256": "PENDING", "upstream_commit_or_version": "PENDING",
            "extracted_closure_digest": "PENDING", "licence_status": "PENDING"},
        "physical_measurements": {
            "camera_x_m": "NOT_MEASURED", "camera_y_m": "NOT_MEASURED",
            "camera_z_m": "NOT_MEASURED", "camera_roll_rad": "NOT_MEASURED",
            "camera_pitch_rad": "NOT_MEASURED", "camera_yaw_rad": "NOT_MEASURED",
            "wheel_diameter_m": "NOT_MEASURED", "chassis_width_m": "NOT_MEASURED",
            "chassis_length_m": "NOT_MEASURED"},
        "claim_boundary": (
            "source fidelity only. Agreement with a description is not agreement "
            "with the physical robot, and no value here is a physical measurement"),
    }


def request_production_admission(provenance: dict[str, Any]) -> dict[str, Any]:
    """The gate a future production build must pass. Refuses reference inputs.

    This exists so that today's test fixture cannot become tomorrow's robot
    model by being passed through the same pipeline a second time.
    """
    role = provenance.get("source_role")
    if role != SourceRole.AUTHORITATIVE:
        raise AssetBuildRefused(
            "AUTHORITATIVE_SOURCE_NOT_ESTABLISHED",
            f"source_role is {role!r}. Production admission requires an "
            "authoritative description acquired with explicit provenance; the "
            "vendor acquisition fields are still PENDING")
    vendor = provenance.get("vendor_acquisition", {})
    pending = [k for k, v in vendor.items() if v == "PENDING"]
    if pending:
        raise AssetBuildRefused(
            "VENDOR_PROVENANCE_INCOMPLETE",
            f"vendor acquisition fields still pending: {sorted(pending)}")
    validation = provenance.get("validation") or {}
    if validation.get("COLLIDER_VALIDATION") != "PASS":
        raise AssetBuildRefused(
            "COLLIDER_VALIDATION_NOT_PASSED",
            f"collider validation is {validation.get('COLLIDER_VALIDATION')!r}")
    return {"PRODUCTION_ADMISSION": "PASS"}


def write_provenance(path: Path | str, provenance: dict[str, Any]) -> str:
    """Write, read back, and return the sidecar's own hash."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(provenance, indent=2) + "\n")
    back = json.loads(target.read_text())
    for key in ("source_role", "production_admissible", "source", "source_closure",
                "collider_specification_digest", "claim_boundary"):
        if key not in back:
            raise AssetBuildRefused(
                "PROVENANCE_INCOMPLETE", f"{key} missing after write-back")
    return hashlib.sha256(target.read_bytes()).hexdigest()
