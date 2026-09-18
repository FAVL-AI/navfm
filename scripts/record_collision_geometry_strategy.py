"""Adjudicate Decision B: what collision geometry may be derived from, and how.

The authoritative production URDF supplies collision geometry as meshes, so the
question is not which primitives look about right. It is what can be derived
from those meshes without inventing a dimension the vendor never stated.

That reframing settles more than it looks. The archive contains no vendor
dimension table at all, so every primitive this project could fit would be
measured from the meshes and then presented as a box -- a value laundered
through a shape. The meshes themselves are the only geometry the vendor
actually specified, which makes them the only defensible source.

Four evidence classes are kept apart throughout, because collapsing them is how
a measurement becomes a specification: what Yahboom states, what their mesh
measures, what their CAD measures, and what the robot measures. This tranche
can produce the second. It cannot produce the first or the fourth, and it is
forbidden from converting the third.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402
from navfm.isaac.mesh_geometry import (  # noqa: E402
    REFUSAL_CATEGORIES,
    convex_hull_measure,
    hull_backend,
    measure_mesh,
    read_binary_stl,
    transform_bounds,
)
from navfm.isaac.ros_package_resolver import RosPackageResolver  # noqa: E402

OUT = REPO / "gates/digital_twin/collision_geometry_strategy_20260918.json"
STAGING = pathlib.Path("/home/favl/Downloads/yahboom/extracted")
M3PRO_WS = STAGING / "M3Pro_ws-0.0.1_f08db69b" / "m3pro_ws"
URDF_REL = "src/M3Pro/urdf/m3pro.urdf"
AUTHORITATIVE_SHA = (
    "cb092310636677ab4bc9846efd30c39cbf4d953ae4fc140a411d8b4c2e56ae6e")
CAD = pathlib.Path("/home/favl/Downloads/ROSMASTER-M3Pro.x_t")

WHEEL_LINKS = ("lwheel1", "lwheel2", "rwheel1", "rwheel2")
ARM_LINKS = ("arm1", "arm2", "arm3", "arm4", "arm5", "Gripping",
             "rlink1", "rlink2", "rlink3", "llink1", "llink2", "llink3")


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _floats(text: str | None, default: tuple[float, float, float]
            ) -> tuple[float, float, float]:
    if not text:
        return default
    parts = [float(v) for v in text.split()]
    return (parts[0], parts[1], parts[2])


def inventory() -> list[dict[str, Any]]:
    """Every collision element, with the mesh it owns measured, not assumed."""
    urdf = M3PRO_WS / URDF_REL
    resolver = RosPackageResolver(source_roots=[M3PRO_WS / "src"])
    robot = ET.fromstring(urdf.read_bytes())
    rows: list[dict[str, Any]] = []

    for link in robot.findall("link"):
        name = str(link.get("name"))
        for collision in link.findall("collision"):
            geometry = collision.find("geometry")
            mesh = geometry.find("mesh") if geometry is not None else None
            if mesh is None:
                rows.append({"link": name, "geometry_kind": "PRIMITIVE_OR_OTHER",
                             "note": "not a mesh collision"})
                continue
            uri = str(mesh.get("filename"))
            outcome = resolver.resolve(uri)
            origin = collision.find("origin")
            xyz = _floats(origin.get("xyz") if origin is not None else None,
                          (0.0, 0.0, 0.0))
            rpy = _floats(origin.get("rpy") if origin is not None else None,
                          (0.0, 0.0, 0.0))
            scale = _floats(mesh.get("scale"), (1.0, 1.0, 1.0))

            row: dict[str, Any] = {
                "link": name, "geometry_kind": "MESH", "mesh_uri": uri,
                "resolution_status": outcome.status,
                "resource_relative": f"{outcome.package}/"
                                     f"{outcome.requested_resource}",
                "source_package": outcome.package,
                "collision_origin_xyz": list(xyz),
                "collision_origin_rpy": list(rpy),
                "scale_declared": mesh.get("scale") is not None,
                "scale": list(scale),
            }
            if not outcome.resolved or outcome.resolved_path is None:
                row["MEASURED"] = False
                rows.append(row)
                continue

            measured = measure_mesh(pathlib.Path(outcome.resolved_path))
            row["MEASURED"] = True
            row["mesh_sha256"] = measured.sha256
            row["mesh_format"] = measured.mesh_format
            row["unit_metadata"] = measured.unit_metadata
            row["triangle_count"] = measured.triangle_count
            row["unique_vertex_count"] = measured.unique_vertex_count
            row["raw_bounds_min"] = list(measured.bounds_min)
            row["raw_bounds_max"] = list(measured.bounds_max)
            row["raw_extents"] = list(measured.extents)
            row["centroid"] = list(measured.centroid)
            row["signed_volume"] = measured.signed_volume
            row["closed_surface"] = measured.is_closed_estimate
            row["transformed"] = transform_bounds(measured, xyz, rpy, scale)
            row["evidence_class"] = "VENDOR_MESH_DERIVED_VALUE"

            hull = convex_hull_measure(
                read_binary_stl(pathlib.Path(outcome.resolved_path)))
            row["convex_hull"] = hull
            if hull.get("MEASURED") and measured.is_closed_estimate:
                source_volume = abs(measured.signed_volume)
                hull_volume = float(hull["hull_volume"])
                row["hull_volume_ratio"] = (
                    hull_volume / source_volume if source_volume > 0 else None)
                row["hull_bounds_match_source"] = bool(
                    max(abs(a - b) for a, b in zip(
                        hull["hull_extents"], measured.extents, strict=True))
                    < 1e-6)
            rows.append(row)
    return rows


def unit_finding(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Say what the numbers are in, and on what evidence.

    STL declares no unit, so the answer cannot come from the file. It comes
    from the URDF, where a length is metres by specification, and from the
    magnitudes being consistent with that.
    """
    measured = [r for r in rows if r.get("MEASURED")]
    largest = max((max(r["raw_extents"]) for r in measured), default=0.0)
    wheels = [r for r in measured if r["link"] in WHEEL_LINKS]
    wheel_extent = max((max(r["raw_extents"]) for r in wheels), default=0.0)
    return {
        "MESH_UNIT_METADATA": "ABSENT",
        "detail": "binary STL carries no unit declaration; the format has no field "
                  "for one",
        "effective_unit": "METRES",
        "basis": [
            "URDF lengths are metres by specification, and no scale attribute is "
            "declared on any of these meshes, so the mesh numbers enter the model "
            "as metres unchanged",
            f"the largest extent across all collision meshes is {largest:.4f}, "
            "which is a plausible robot dimension in metres and implausible in "
            "millimetres or centimetres",
            f"the largest wheel extent is {wheel_extent:.4f}",
        ],
        "NOT_ASSUMED": "the unit is derived from the URDF contract and magnitude "
                       "consistency, not from a convention about STL files",
        "evidence_class": "DERIVED",
    }


def options() -> list[dict[str, Any]]:
    """Characterise each derivation option. No option is ranked by convenience."""
    return [
        {"option": "A", "name": "source triangle mesh used directly",
         "source_basis": "authoritative vendor collision meshes",
         "deterministic": True,
         "physx_admissible": "ONLY_FOR_STATIC_GEOMETRY",
         "physx_note": ("PhysX triangle meshes do not collide with each other and "
                        "are not valid for dynamic or articulated bodies. Every "
                        "link here belongs to an articulation, so this fails on "
                        "the actual engine rule rather than on preference"),
         "preserves_link_ownership": True,
         "invents_dimensions": False,
         "cost": "highest; base_link alone is 172k triangles",
         "verdict": "NOT_ADMISSIBLE_FOR_ARTICULATED_LINKS"},
        {"option": "B", "name": "single convex hull per collision mesh",
         "source_basis": "authoritative vendor collision meshes",
         "deterministic": True,
         "deterministic_basis": "Qhull is deterministic for a fixed input and "
                                "fixed options; the input is pinned by mesh hash",
         "physx_admissible": True,
         "preserves_link_ownership": True,
         "invents_dimensions": False,
         "conservatism": "never smaller than the source, so containment holds by "
                         "construction",
         "cost": "low",
         "verdict": "ADMISSIBLE"},
        {"option": "C", "name": "convex decomposition per collision mesh",
         "source_basis": "authoritative vendor collision meshes",
         "deterministic": "ONLY_IF_PINNED",
         "deterministic_basis": ("depends on the decomposer, its version, its "
                                 "parameters and its seed. Admissible only with "
                                 "all of those frozen and a reproduced digest"),
         "physx_admissible": True,
         "preserves_link_ownership": True,
         "invents_dimensions": False,
         "conservatism": "tighter than a hull where the part is concave",
         "cost": "higher, and adds a dependency this repository does not have",
         "verdict": "ADMISSIBLE_ONLY_WHERE_A_HULL_IS_INADEQUATE"},
        {"option": "D", "name": "independently specified primitives",
         "source_basis": "a vendor dimension table, CAD, or physical measurement",
         "deterministic": True,
         "physx_admissible": True,
         "preserves_link_ownership": True,
         "invents_dimensions": "NO_IF_A_SOURCE_EXISTS",
         "verdict": "NOT_AVAILABLE",
         "why": ("no vendor dimension evidence exists in the acquired closure, "
                 "CAD association is not established and conversion is not "
                 "authorised, and nothing has been physically measured. Fitting a "
                 "primitive to a mesh and calling it a specification would launder "
                 "a mesh-derived value into a stated one")},
    ]


def adequacy_rule() -> dict[str, Any]:
    """Freeze when one hull is enough, before any mesh is judged by it."""
    return {
        "FROZEN_BEFORE_EVALUATION": True,
        "rule": [
            "a single convex hull is adequate for a link when its hull bounds "
            "equal the source bounds to within 1e-6 m on every axis, and its hull "
            "volume does not exceed the source volume by more than the "
            "preregistered inflation limit",
            "a link failing the volume limit is a candidate for decomposition, "
            "not an automatic failure: the decision is recorded per link",
        ],
        "PREREGISTERED_INFLATION_LIMIT": 1.25,
        "limit_units": "hull volume divided by closed-source volume",
        "preregistered_before_measurement": True,
        "why_preregistered": (
            "a threshold chosen after seeing the numbers is a description of the "
            "numbers, not a test of them"),
        "clearance_caveat": (
            "volume ratio is a summary. A hull that bridges a concave gap can be "
            "within the limit and still close a gap the robot needs, so any link "
            "whose geometry is clearance-critical is reviewed on its own terms "
            "rather than on the ratio alone"),
        "articulation_rule": (
            "hulls are per collision element and never merged across links, so a "
            "whole-robot hull is excluded by construction"),
    }


def cad_association() -> dict[str, Any]:
    """Read-only. The file is not converted and no geometry is extracted."""
    if not CAD.is_file():
        return {"CAD_PRODUCT_ASSOCIATION": "UNPROVEN",
                "reason": f"no CAD file at {CAD}"}
    header = CAD.open("rb").read(400).decode("latin-1", errors="replace")
    probe = subprocess.run(
        ["grep", "-oac", "ROSMASTER-M3Pro", str(CAD)],
        capture_output=True, text=True, check=False)
    internal_hits = int(probe.stdout.strip() or 0)
    return {
        "path": str(CAD),
        "HOST_LOCAL": True,
        "byte_size": CAD.stat().st_size,
        "format": "Parasolid transmit (x_t)",
        "kernel_version": "Parasolid Version 32, build 255"
        if "Parasolid Version 32" in header else "UNREAD",
        "exported_on": "Windows_NT" if "Windows_NT" in header else "UNREAD",
        "internal_product_name_occurrences": internal_hits,
        "evidence_for": [
            "the filename names the product",
            f"the file body contains the string ROSMASTER-M3Pro "
            f"{internal_hits} time(s), which survives a rename and is therefore "
            "independent of the filename",
            "it was distributed by Yahboom in the same drop as the M3 Pro code",
            "the authoritative URDF was written by the SolidWorks URDF exporter, "
            "and Parasolid is a SolidWorks-native interchange format, so a common "
            "CAD origin is consistent",
        ],
        "evidence_missing": [
            "no geometric correspondence has been computed; that needs a Parasolid "
            "kernel and conversion is not authorised in this tranche",
            "no evidence that it is the same configuration as the URDF -- same arm "
            "variant, same camera, same options",
        ],
        "CAD_PRODUCT_ASSOCIATION": "SUPPORTED",
        "CAD_CONFIGURATION_ASSOCIATION": "UNPROVEN",
        "why_split": (
            "the internal name is real independent evidence that this is the M3 Pro "
            "product. It says nothing about which configuration, and a 189 MB full "
            "assembly and an 18-link simplified description need not correspond "
            "part for part"),
        "USED_FOR_DECISION_B": False,
        "not_used_because": (
            "the selected strategy needs no CAD dimension, so the question does not "
            "arise. Raising configuration association to SUPPORTED would need a "
            "read-only geometric comparison that is not authorised here"),
        "CONVERTED": False,
        "read_only_operations": ["first 400 bytes of the header", "a string count"],
    }


def vendor_dimensions() -> dict[str, Any]:
    """First-party stated dimensions present in the acquired closure."""
    found: list[dict[str, Any]] = []
    return {
        "search_scope": ["both Orin production workspaces", "all YAML and Python "
                         "configuration", "all README and Markdown in the archive"],
        "dimensions_found": found,
        "VENDOR_SPECIFIED_DIMENSIONS": "NONE_IN_ACQUIRED_CLOSURE",
        "consequence": (
            "there is no stated dimension in the archive to build a primitive "
            "from. Any primitive this project produced would be measured from the "
            "meshes and then presented as a shape, which is a mesh-derived value "
            "wearing a specification's clothes"),
        "note": (
            "figures such as an 80 mm wheel diameter appear in Yahboom's public "
            "product pages, which are not part of the acquired closure and are not "
            "cited as evidence here. Asking for a dimension table is already in "
            "the held support query"),
        "evidence_class_if_found_later": "VENDOR_SPECIFIED_DIMENSION",
    }


def decomposition_backend() -> dict[str, Any]:
    """Can a convex decomposition actually be produced here, and reproduced?

    trimesh exposes the call but delegates the work, so the API existing proves
    nothing. Determinism cannot be demonstrated for a computation that cannot be
    run, and a strategy whose determinism is not demonstrated is not admissible.
    """
    import shutil

    backends: dict[str, Any] = {}
    for module in ("coacd", "pyvhacd"):
        try:
            __import__(module)
            backends[module] = "PRESENT"
        except ImportError:
            backends[module] = "ABSENT"
    for binary in ("testVHACD", "vhacd", "VHACD"):
        backends[binary] = shutil.which(binary) or "ABSENT"
    try:
        import trimesh
        api = {"trimesh": trimesh.__version__,
               "exposes_convex_decomposition":
                   hasattr(trimesh.Trimesh, "convex_decomposition")}
    except ImportError:
        api = {"trimesh": "ABSENT", "exposes_convex_decomposition": False}

    usable = any(v == "PRESENT" or (isinstance(v, str) and v.startswith("/"))
                 for v in backends.values())
    return {
        "AVAILABLE": usable,
        "api": api,
        "backends": backends,
        "finding": (
            "trimesh exposes convex_decomposition and every backend it delegates "
            "to is absent, so the call exists and the computation cannot be "
            "performed" if not usable else "a decomposition backend is present"),
        "consequence": (
            "determinism cannot be demonstrated for a computation that cannot be "
            "run, and an undemonstrated determinism claim is not a basis for "
            "admitting a strategy"),
    }


def controls() -> dict[str, Any]:
    # PYTHONPATH is set to the repository's own src rather than inherited or
    # stripped. Inheriting it would let a host ROS tree in; stripping it leaves
    # navfm unimportable under any interpreter that has not installed it, which
    # made this control report a collection error as a failed control.
    import os

    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    environment["PYTHONPATH"] = str(REPO / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_mesh_geometry.py",
         "-p", "no:warnings", "-q", "--tb=short"],
        cwd=REPO, capture_output=True, text=True, check=False, env=environment)
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return {
        "suite": "tests/test_mesh_geometry.py",
        "exit_code": proc.returncode,
        "VERDICT": "PASS" if proc.returncode == 0 else "FAIL",
        "last_line": lines[-1][:110] if lines else "",
        "interpreter": sys.executable,
        "stderr_tail": proc.stderr.strip().splitlines()[-2:] if proc.stderr else [],
        "refusal_categories": list(REFUSAL_CATEGORIES),
        "controls": {
            "F_TWIN_1_SQUARED_EXTENTS": "every extent squared, as measured "
                                        "historically, is refused DIMENSION_MISMATCH",
            "POSITIVE_CONTROL": "a correct collider set is admitted, so the check "
                                "can pass as well as fail",
            "UNIT_SCALE": "x1000, /1000, x100 and /100 are refused and named as "
                          "unit errors rather than geometry errors",
            "AXIS_PERMUTATION": "the same extents on different axes are refused as "
                                "ORIENTATION_MISMATCH, not as a size error",
            "CONTAINMENT": "a collider smaller than its source is refused",
            "WRONG_MESH_SIMILAR_SIZE": "a near-identical mesh from another link is "
                                       "refused on source identity, not size",
            "DROPPED_COLLIDER": "a missing link collider is refused",
            "DUPLICATE_WITH_DROP": "equal total count with one link duplicated and "
                                   "one dropped is refused",
            "UNEXPECTED_COLLIDER": "a collider for a link with no source collision "
                                   "geometry is refused",
            "SWAPPED_SET_EQUAL_AGGREGATES": "two links exchanging colliders keeps "
                                            "every aggregate identical and is still "
                                            "refused",
            "HULL_BACKEND_ABSENCE": "reported rather than skipped",
        },
        "counting_is_never_sufficient": (
            "F-TWIN-1 passed a check that counted colliders. Three controls here "
            "hold the count constant and still require refusal"),
    }


def main() -> int:
    own = str(OUT.relative_to(REPO))
    head = _git("rev-parse", "HEAD")
    dirty = [line for line in _git("status", "--porcelain").splitlines()
             if line.strip() and own not in line]

    urdf = M3PRO_WS / URDF_REL
    urdf_sha = hashlib.sha256(urdf.read_bytes()).hexdigest()
    rows = inventory()
    measured = [r for r in rows if r.get("MEASURED")]
    hulls_measured = [r for r in measured if r.get("convex_hull", {}).get("MEASURED")]

    rule = adequacy_rule()
    limit = float(rule["PREREGISTERED_INFLATION_LIMIT"])
    hull_adequate, hull_inadequate, hull_unknown = [], [], []
    for row in measured:
        ratio = row.get("hull_volume_ratio")
        if ratio is None:
            hull_unknown.append(row["link"])
        elif ratio <= limit:
            hull_adequate.append({"link": row["link"], "ratio": round(ratio, 4)})
        else:
            hull_inadequate.append({"link": row["link"], "ratio": round(ratio, 4)})

    wheels = [r for r in measured if r["link"] in WHEEL_LINKS]
    arms = [r for r in measured if r["link"] in ARM_LINKS]

    control_result = controls()
    decomposition = decomposition_backend()
    cad = cad_association()
    dimensions = vendor_dimensions()

    source_requirements = {
        "an_admitted_geometry_source_exists": True,
        "it_is_the_geometry_the_vendor_specified": True,
        "no_alternative_source_is_available": (
            dimensions["VENDOR_SPECIFIED_DIMENSIONS"] == "NONE_IN_ACQUIRED_CLOSURE"
            and cad.get("CAD_CONFIGURATION_ASSOCIATION") == "UNPROVEN"),
        "introduces_no_unsupported_dimensions": True,
        "can_be_validated_independently": control_result["VERDICT"] == "PASS",
    }
    source_decided = all(source_requirements.values())

    hull_adequate_anywhere = bool(hull_adequate)
    derivation_requirements = {
        "single_hull_meets_the_preregistered_adequacy_rule_somewhere":
            hull_adequate_anywhere,
        "fallback_decomposition_can_be_produced": decomposition["AVAILABLE"],
        "fallback_determinism_demonstrated": decomposition["AVAILABLE"],
        "preserves_per_link_ownership_and_transforms": True,
        "compatible_with_intended_physx_use": True,
        "validator_can_refuse_a_wrong_result": control_result["VERDICT"] == "PASS",
    }
    derivation_decided = all(derivation_requirements.values())
    resolved = source_decided and derivation_decided

    record: dict[str, Any] = {
        "check": "COLLISION_GEOMETRY_STRATEGY",
        "artifact_semantics": "DECISION_B_SOURCE_AND_STRATEGY_ADJUDICATED",
        "author": "Frank Asante Van Laarhoven",
        "provenance_observed_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "repository_head": head,
        "worktree_clean_at_measurement": not dirty,
        "other_dirty_entries": dirty,
        "measurement_interpreter": sys.executable,
        "hull_backend": hull_backend(),

        "DECISION_B_QUESTION": (
            "given that the authoritative production URDF provides mesh collision "
            "geometry rather than primitives, what geometry source and "
            "deterministic transformation can create PhysX-admissible collision "
            "shapes without inventing robot dimensions?"),
        "NOT_REDEFINED_AS": "what boxes look approximately right",

        "AUTHORITATIVE_ROBOT_DESCRIPTION": "M3Pro/urdf/m3pro.urdf",
        "authoritative_sha256": urdf_sha,
        "authoritative_sha_matches_decision": urdf_sha == AUTHORITATIVE_SHA,

        "EVIDENCE_CLASSES": {
            "A_VENDOR_SPECIFIED_DIMENSION": "stated by Yahboom in the acquired "
                                            "source or docs",
            "B_VENDOR_MESH_DERIVED_DIMENSION": "measured from the authoritative "
                                               "vendor mesh",
            "C_CAD_DERIVED_DIMENSION": "measured from the Parasolid file once "
                                       "product association is proven",
            "D_PHYSICAL_MEASURED_DIMENSION": "measured from the actual robot",
            "RULE": "B and C are never labelled A. This tranche can produce B "
                    "only",
        },

        "COLLISION_INVENTORY": rows,
        "collision_element_count": len(rows),
        "mesh_collision_count": len(measured),
        "all_resolved": all(r.get("MEASURED") for r in rows),
        "all_identity_origin": all(
            r["collision_origin_xyz"] == [0.0, 0.0, 0.0]
            and r["collision_origin_rpy"] == [0.0, 0.0, 0.0] for r in measured),
        "any_scale_declared": any(r["scale_declared"] for r in measured),

        "UNIT_FINDING": unit_finding(rows),
        "SINGLE_HULL_ADEQUACY_RULE": rule,
        "WATERTIGHTNESS": {
            "closed_surface_links": sorted(
                r["link"] for r in measured if r.get("closed_surface")),
            "open_surface_links": sorted(
                r["link"] for r in measured if not r.get("closed_surface")),
            "finding": (
                "several vendor collision meshes are not closed surfaces, and they "
                "include base_link and all four wheels. An enclosed volume is "
                "undefined for an open surface, so any volumetric adequacy test is "
                "unassessable for exactly the parts that decide the navigation "
                "footprint"),
            "consequence": (
                "this limits what any volume-based method can claim about those "
                "links, independently of which strategy is chosen"),
        },
        "ADEQUACY_RULE_SELF_CRITIQUE": {
            "finding": (
                "the bounds half of the frozen adequacy rule cannot discriminate. "
                "A convex hull's extreme points are the source's extreme points, "
                "so hull bounds always equal source bounds and that comparison can "
                "never fail"),
            "consequence": ("the volume ratio is doing all the work. The bounds "
                            "comparison is retained as a corruption check on the "
                            "hull computation, not as an adequacy criterion"),
            "measured_bounds_always_matched": all(
                r.get("hull_bounds_match_source", True) for r in measured
                if "hull_bounds_match_source" in r),
        },
        "HULL_ADEQUACY": {
            "hulls_measured": len(hulls_measured),
            "adequate_within_preregistered_limit": hull_adequate,
            "exceeding_limit": hull_inadequate,
            "not_assessable": hull_unknown,
            "not_assessable_reason": "volume ratio needs a closed source surface",
        },

        "OPTION_ANALYSIS": options(),

        "WHEEL_FINDINGS": {
            "links": [r["link"] for r in wheels],
            "measured": [{"link": r["link"], "extents": r["raw_extents"],
                          "triangles": r["triangle_count"],
                          "hull_ratio": r.get("hull_volume_ratio")}
                         for r in wheels],
            "joint_type_in_source": "fixed",
            "roller_geometry": "NOT_ASSESSED",
            "wheel_radius_evidence_class": "VENDOR_MESH_DERIVED_VALUE",
            "FUNCTIONAL_NAVIGATION_COLLIDER": "a hull of the wheel mesh gives the "
                                              "base a correct footprint for "
                                              "kinematic navigation",
            "CALIBRATED_MECANUM_CONTACT_MODEL": "FUTURE_WORK",
            "boundary": (
                "a hull of a Mecanum wheel is a smooth solid. It cannot reproduce "
                "roller contact, and the source joints are fixed, so no version of "
                "this models Mecanum dynamics. Collision geometry loading is not "
                "contact fidelity"),
        },

        "ARM_FINDINGS": {
            "links": [r["link"] for r in arms],
            "measured": [{"link": r["link"], "extents": r["raw_extents"],
                          "hull_ratio": r.get("hull_volume_ratio")}
                         for r in arms],
            "per_link_ownership_required": True,
            "whole_robot_hull": "FORBIDDEN",
            "rules": [
                "each collider stays attached to the link that owns it",
                "local transforms are preserved",
                "no collider spans a joint",
                "no two articulated links are merged",
                "self-collision must not be created by construction",
            ],
        },

        "VENDOR_DIMENSION_EVIDENCE": dimensions,
        "CAD_ASSOCIATION": cad,
        "PHYSICAL_MEASUREMENT_GAPS": {
            "wheel_diameter": "NOT_MEASURED",
            "chassis_length_width_height": "NOT_MEASURED",
            "wheel_centre_positions": "NOT_MEASURED",
            "arm_base_mounting_transform": "NOT_MEASURED",
            "navigation_arm_pose": "NOT_MEASURED",
            "camera_mounting_datum": "NOT_MEASURED",
            "blocks_this_decision": False,
            "why_not": ("this decision is about which source and which "
                        "transformation are defensible. Whether the source matches "
                        "the robot is a different question, and answering it "
                        "requires the robot"),
        },

        "EXTENT_VALIDATION_CONTRACT": {
            "per_collider_required": [
                "source local bounds", "generated local bounds",
                "transformed bounds", "centre offset", "orientation",
                "containment relation", "source mesh hash"],
            "aggregate_checks_are_insufficient": True,
            "containment": "a generated collider must never be smaller than its "
                           "source where conservative containment is required",
        },
        "NEGATIVE_CONTROLS": control_result,

        "STRATEGY_TABLE": [
            {"strategy": "raw source triangle meshes", "source": "vendor meshes",
             "deterministic": True, "physx": "static only",
             "link_ownership": True, "invents_dimensions": False,
             "mecanum_fidelity": "no", "validatable": True,
             "decision": "REJECTED_ON_PHYSX_RULE"},
            {"strategy": "convex hull", "source": "vendor meshes",
             "deterministic": True, "physx": True, "link_ownership": True,
             "invents_dimensions": False, "mecanum_fidelity": "no",
             "validatable": True, "decision": "SELECTED"},
            {"strategy": "convex decomposition", "source": "vendor meshes",
             "deterministic": "only if fully pinned", "physx": True,
             "link_ownership": True, "invents_dimensions": False,
             "mecanum_fidelity": "no", "validatable": True,
             "decision": "CONDITIONAL_FALLBACK"},
            {"strategy": "source-specified primitives", "source": "none exists",
             "deterministic": True, "physx": True, "link_ownership": True,
             "invents_dimensions": False, "mecanum_fidelity": "no",
             "validatable": True, "decision": "UNAVAILABLE_NO_SOURCE"},
            {"strategy": "mesh-fitted primitives", "source": "vendor meshes",
             "deterministic": True, "physx": True, "link_ownership": True,
             "invents_dimensions": "PRESENTS_MESH_DERIVED_AS_SPECIFIED",
             "mecanum_fidelity": "no", "validatable": True,
             "decision": "REJECTED_LAUNDERS_EVIDENCE_CLASS"},
            {"strategy": "CAD-derived primitives", "source": "Parasolid",
             "deterministic": True, "physx": True, "link_ownership": True,
             "invents_dimensions": False, "mecanum_fidelity": "no",
             "validatable": "not yet", "decision": "BLOCKED_ASSOCIATION_UNPROVEN"},
            {"strategy": "physical-measurement primitives", "source": "the robot",
             "deterministic": True, "physx": True, "link_ownership": True,
             "invents_dimensions": False, "mecanum_fidelity": "no",
             "validatable": True, "decision": "FUTURE_AS_BUILT_VALIDATION"},
        ],

        "DECOMPOSITION_BACKEND": decomposition,
        "SOURCE_REQUIREMENTS": source_requirements,
        "DERIVATION_REQUIREMENTS": derivation_requirements,
        "COLLISION_GEOMETRY_SOURCE":
            "AUTHORITATIVE_VENDOR_COLLISION_MESHES" if source_decided
            else "UNDECIDED",
        "COLLISION_GEOMETRY_SOURCE_STATUS":
            "DECIDED" if source_decided else "UNDECIDED",
        "COLLIDER_DERIVATION_STRATEGY":
            "DETERMINISTIC_CONVEX_HULL_PER_COLLISION_ELEMENT" if derivation_decided
            else "UNDECIDED",
        "COLLIDER_DERIVATION_STATUS":
            "DECIDED" if derivation_decided else "BLOCKED",
        "DERIVATION_BLOCKERS": [
            reason for flag, reason in (
                (not hull_adequate_anywhere,
                 "a single convex hull exceeds the preregistered inflation limit "
                 "on every link where the limit can be assessed, so the primary "
                 "strategy does not apply anywhere it can be tested"),
                (not decomposition["AVAILABLE"],
                 "the fallback needs a convex decomposition and no backend exists "
                 "in either available environment, so its determinism cannot be "
                 "demonstrated"),
            ) if flag],
        "THRESHOLD_NOT_MOVED": (
            "the 1.25 inflation limit was preregistered before any mesh was "
            "measured and is not revised here. Raising it until hulls passed "
            "would turn the test into a description of the result"),
        "FALLBACK_STRATEGY": (
            "controlled convex decomposition, per link, only where a single hull "
            "exceeds the preregistered inflation limit or closes a "
            "clearance-critical gap, and only with decomposer, version, "
            "parameters and seed frozen and a reproduced digest"),
        "PRIMITIVE_FITTING": "NOT_USED_WITHOUT_INDEPENDENT_DIMENSION_SOURCE",
        "PRIMITIVE_RECONSTRUCTION": "NOT_SUPPORTED_BY_SOURCE",
        "DECISION_B": "RESOLVED" if resolved else "BLOCKED",

        "CAD_ROLE": "INDEPENDENT_GEOMETRY_CORROBORATION_PENDING_ASSOCIATION",
        "PHYSICAL_MEASUREMENT_ROLE": "AS_BUILT_VALIDATION",

        "FUNCTIONAL_VS_CALIBRATED": {
            "mesh_derived_hulls_may_support": "DT_LEVEL_1_FUNCTIONAL",
            "they_do_not_establish": "DT_LEVEL_2_CALIBRATED",
            "why": ("a hull is faithful to the vendor's mesh. Whether the vendor's "
                    "mesh is faithful to the robot is unmeasured, and a twin that "
                    "reproduces a model exactly still reproduces whatever the model "
                    "gets wrong"),
        },
        "LICENCE_BOUNDARY": {
            "REDISTRIBUTION": "NOT_AUTHORISED_PENDING_CLARIFICATION",
            "committed_here": ["hashes", "measurements", "transformation rules",
                               "validation results"],
            "not_committed_here": ["vendor meshes", "vendor URDF", "CAD",
                                   "generated hulls", "USD"],
        },

        "CLAIM_BOUNDARY": (
            "this decides a source and a transformation rule. No collider was "
            "generated, no asset was built, and nothing was compared against the "
            "physical robot"),
        "PRODUCTION_M3PRO_USD": "NOT_GENERATED",
        "DIGITAL_TWIN_REQUALIFICATION": "NOT_STARTED",
        "PHYSICAL_CAMERA_EXTRINSIC": "NOT_MEASURED",
        "SCIENTIFIC_ARM_A_N": 0,
        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
    }

    sha = emit_evidence(OUT, record, required_keys=(
        "check", "DECISION_B_QUESTION", "COLLISION_INVENTORY", "UNIT_FINDING",
        "OPTION_ANALYSIS", "STRATEGY_TABLE", "NEGATIVE_CONTROLS",
        "CAD_ASSOCIATION", "VENDOR_DIMENSION_EVIDENCE", "DECISION_B",
        "CLAIM_BOUNDARY"))

    print("=" * 78)
    print("DECISION B -- COLLISION GEOMETRY SOURCE AND STRATEGY")
    print("=" * 78)
    print(f"  HEAD {head[:12]}  clean={record['worktree_clean_at_measurement']}")
    print(f"  urdf sha matches decision: {record['authoritative_sha_matches_decision']}")
    print(f"  hull backend  {record['hull_backend'].get('backend')}")
    print(f"  controls      {control_result['VERDICT']}  {control_result['last_line']}")
    print()
    print(f"  collisions    {record['mesh_collision_count']} mesh, "
          f"all resolved={record['all_resolved']}, "
          f"identity origin={record['all_identity_origin']}, "
          f"scale declared={record['any_scale_declared']}")
    print(f"  units         {record['UNIT_FINDING']['MESH_UNIT_METADATA']} in file; "
          f"effective {record['UNIT_FINDING']['effective_unit']}")
    print()
    print(f"  {'link':14s} {'extents (m)':34s} {'tris':>7s} {'hull/src':>9s}")
    for row in measured:
        ext = "  ".join(f"{v:.4f}" for v in row["raw_extents"])
        ratio = row.get("hull_volume_ratio")
        print(f"  {row['link']:14s} {ext:34s} {row['triangle_count']:7d} "
              f"{(f'{ratio:.3f}' if ratio else '-'):>9s}")
    print()
    adequacy = record["HULL_ADEQUACY"]
    print(f"  hull adequacy limit {limit}  adequate="
          f"{len(adequacy['adequate_within_preregistered_limit'])} "
          f"exceeding={len(adequacy['exceeding_limit'])} "
          f"unassessable={len(adequacy['not_assessable'])}")
    if adequacy["exceeding_limit"]:
        print(f"    exceeding: {adequacy['exceeding_limit']}")
    print()
    print(f"  vendor dims   {dimensions['VENDOR_SPECIFIED_DIMENSIONS']}")
    print(f"  CAD           product={cad.get('CAD_PRODUCT_ASSOCIATION')} "
          f"configuration={cad.get('CAD_CONFIGURATION_ASSOCIATION')} "
          f"converted={cad.get('CONVERTED')}")
    print()
    print(f"  watertight    {len(record['WATERTIGHTNESS']['closed_surface_links'])} "
          f"closed, {len(record['WATERTIGHTNESS']['open_surface_links'])} open "
          f"({', '.join(record['WATERTIGHTNESS']['open_surface_links'][:5])})")
    print(f"  decomposition backend available: {decomposition['AVAILABLE']}")
    print()
    print(f"  SOURCE        {record['COLLISION_GEOMETRY_SOURCE']} "
          f"[{record['COLLISION_GEOMETRY_SOURCE_STATUS']}]")
    print(f"  STRATEGY      {record['COLLIDER_DERIVATION_STRATEGY']} "
          f"[{record['COLLIDER_DERIVATION_STATUS']}]")
    for blocker in record["DERIVATION_BLOCKERS"]:
        print(f"    blocker: {blocker[:70]}")
    print(f"  PRIMITIVES    {record['PRIMITIVE_RECONSTRUCTION']}")
    print(f"  DECISION_B    {record['DECISION_B']}")
    print(f"  artefact      {OUT.relative_to(REPO)}")
    print(f"  sha256        {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
