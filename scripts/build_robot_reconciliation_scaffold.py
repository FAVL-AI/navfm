"""Emit the robot-apparatus reconciliation scaffold.

One row per disputed quantity, one column per authority. The point is that a
number cannot move from one column to another without someone deciding it: a
local reference value sitting in the same cell as an adopted experimental value
is how the 0.048 wheel radius survived as long as it did.

Every cell is either evidenced locally or left PENDING. Nothing is inferred, and
no vendor or physical value is invented -- the vendor archive has not been
acquired and no dimension of the physical robot has been measured.

Run after the tooling commit, so the head it records contains the code that
produced it.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402
from navfm.isaac.urdf_import import UrdfImportRefused, parse_source, source_closure  # noqa: E402

OUT = REPO / "gates/BO10/robot_apparatus_reconciliation_20260917.json"

UPSTREAM_REL = "assets/robots/yahboom_m3_pro/source/yahboom_m3pro_upstream.urdf"
NAVFM_REL = "assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf"
TWIN_MANIFEST_REL = "assets/robots/yahboom_m3_pro/digital_twin_manifest.json"

#: Where a value came from. Explicit, so a local value cannot become an
#: experimental value by sitting in a table long enough.
AUTHORITY_CLASSES = (
    "VENDOR_SPECIFICATION",
    "VENDOR_ROBOT_DESCRIPTION",
    "LOCAL_REFERENCE",
    "UPSTREAM_REFERENCE",
    "SIMULATION_DERIVED",
    "PHYSICAL_MEASUREMENT",
    "EXPERIMENTAL_ADOPTION",
    "NOT_ESTABLISHED",
)

PENDING = "PENDING"
NOT_MEASURED = "NOT_MEASURED"


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def sha256_file(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _candidate(rel: str, role: str) -> dict[str, Any]:
    path = REPO / rel
    entry: dict[str, Any] = {
        "path": rel, "role": role, "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size if path.is_file() else None,
    }
    try:
        model = parse_source(path)
        closure = source_closure(path)
        entry.update({
            "parse_status": "PARSED",
            "robot_name": model.robot_name,
            "link_count": len(model.links),
            "joint_count": len(model.joints),
            "collision_count": len(model.collisions),
            "closure_member_count": closure["member_count"],
            "closure_digest": closure["closure_digest"],
            "external_reference_count": closure["external_reference_count"],
        })
    except UrdfImportRefused as exc:
        entry.update({
            "parse_status": "REFUSED",
            "refusal_category": exc.category,
            "refusal_detail": exc.detail,
            "note": ("this candidate is not well-formed XML and cannot be parsed "
                     "strictly. Its declared values are read from its own twin "
                     "manifest rather than by parsing it leniently"),
        })
    return entry


def _collider_values(rel: str) -> dict[str, Any]:
    """Geometry actually present in a parseable candidate."""
    try:
        model = parse_source(REPO / rel)
    except UrdfImportRefused:
        return {}
    out: dict[str, Any] = {}
    for element in model.collisions:
        out[element.identity] = {
            "primitive": element.primitive,
            "dimensions": list(element.dimensions),
            "origin_xyz": list(element.origin_xyz),
        }
    return out


def _row(quantity: str, role: str, *, upstream: Any = None, navfm: Any = None,
         notes: str = "") -> dict[str, Any]:
    return {
        "quantity": quantity,
        "semantic_role": role,
        "vendor_value": PENDING,
        "vendor_provenance": PENDING,
        "navfm_reference_value": navfm if navfm is not None else PENDING,
        "upstream_reference_value": upstream if upstream is not None else PENDING,
        "physical_measurement": NOT_MEASURED,
        "adopted_experimental_value": PENDING,
        "authority_class": "NOT_ESTABLISHED",
        "resolution_status": "UNRESOLVED",
        "notes": notes,
    }


def build_rows() -> list[dict[str, Any]]:
    upstream = _collider_values(UPSTREAM_REL)
    twin_path = REPO / TWIN_MANIFEST_REL
    twin = json.loads(twin_path.read_text()) if twin_path.is_file() else {}
    changes = {c.get("field"): c for c in twin.get("changes", [])}

    wheel_up = next(
        (v["dimensions"][0] for k, v in upstream.items()
         if "wheel" in k and v["primitive"] == "cylinder"), None)
    wheel_navfm = (changes.get("wheel_radius_m") or {}).get("to")
    chassis_up = next(
        (v["dimensions"] for k, v in upstream.items()
         if k.startswith("base_link") and v["primitive"] == "box"), None)
    camera_change = changes.get("camera_mount") or {}
    contract = camera_change.get("camera_contract", {})

    rows = [
        _row("wheel_radius_m", "drives odometry scale and commanded velocity",
             upstream=wheel_up, navfm=wheel_navfm,
             notes=("the two local candidates disagree. The navfm value is read "
                    "from its own twin manifest, which records the change and "
                    "marks it PROVISIONAL_SIMULATION_VALUE, physically_measured "
                    "false. Neither is a vendor value")),
        _row("camera_mount_topology", "what the camera is rigidly attached to",
             upstream="base_link (fixed joint)", navfm=contract.get("mount"),
             notes=("WITHDRAWN ASSUMPTION. Both local candidates attach the camera "
                    "rigidly to the chassis -- upstream by a fixed camera_joint "
                    "from base_link, navfm by a static mast. The physical M3 Pro "
                    "carries the depth camera on the 6-DOF manipulator, so neither "
                    "local topology matches the robot and neither models the arm")),
        _row("arm_mount_link_to_camera_extrinsic",
             "the only genuinely fixed camera calibration",
             notes=("measured from the arm link or bracket that physically carries "
                    "the camera, never from the chassis. This is the transform that "
                    "does not change when the manipulator moves")),
        _row("rgb_optical_frame_identity",
             "the frame of the RGB stream the model actually consumes",
             upstream="camera_optical_link (fixed from camera_link)",
             notes=("upstream already separates housing from optical frame. A "
                    "correctly attached camera is not a calibrated optical frame, "
                    "and GNM/ViNT/NoMaD consume the optical frame")),
        _row("navigation_arm_joint_vector",
             "the frozen six-joint pose that makes the camera pose reproducible",
             notes=("preregistered, not chosen per episode. With the arm locked the "
                    "manipulator is a controlled camera mast rather than a second "
                    "uncontrolled experimental factor")),
        _row("per_joint_tolerance",
             "admission band on each joint before a production capture",
             notes="declared before any episode, not fitted to an observed pose"),
        _row("camera_housing_datum",
             "named physical datum if the optical centre cannot be established",
             notes=("a measurement against a named datum is convertible later; one "
                    "against an assumed datum is not")),
        _row("chassis_extent_m", "collision footprint and underside clearance",
             upstream=chassis_up,
             notes=("upstream box extent as declared. The admitted asset's "
                    "colliders were squared by the importer; see F-TWIN-1")),
        _row("footprint_horizontal_extent_m",
             "what the planner inflates against",
             upstream=(max(chassis_up[:2]) if chassis_up else None),
             notes=("descriptive only. The frozen planner footprint is not "
                    "changed by this scaffold")),
    ]
    return rows


def main() -> int:
    head = _git("rev-parse", "HEAD")
    rows = build_rows()

    record: dict[str, Any] = {
        "check": "ROBOT_APPARATUS_RECONCILIATION",
        "artifact_semantics": "RECONCILIATION_SCAFFOLD_NO_APPARATUS_DECIDED",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": _dt.datetime.now(_dt.UTC).isoformat(),
        "repository_head": head,
        "ROBOT_DESCRIPTION_AUTHORITY": "PENDING_VENDOR_ACQUISITION",
        "AUTHORITATIVE_BASE": (
            "OFFICIAL_YAHBOOM_ROSMASTER_M3_PRO, once acquired with explicit "
            "provenance"),
        "PHYSICAL_CAMERA_EXTRINSIC": "MEASUREMENT_REQUIRED",
        "CAMERA_APPARATUS_MODEL": {
            "WITHDRAWN": "a fixed base_link -> camera extrinsic",
            "why_withdrawn": (
                "the depth camera on the physical M3 Pro is carried by the 6-DOF "
                "manipulator. A chassis-to-camera transform is therefore not a "
                "constant of the apparatus; it is a function of the arm pose"),
            "CAMERA_MOUNT": "MANIPULATOR_MOUNTED",
            "CAMERA_BASE_TRANSFORM": "configuration-dependent",
            "decomposition": [
                "base_link -> arm_base: from the authoritative description",
                "arm kinematic chain: authoritative description plus joint states",
                "arm mount link -> camera housing: physical measurement",
                "housing -> RGB optical frame: calibration where available",
            ],
            "FIXED_CAMERA_CALIBRATION": "arm_mount_link -> camera_optical_frame",
            "ARM_MOTION_DURING_NAVIGATION": "PROHIBITED",
            "NAVIGATION_ARM_CONFIGURATION": "NOT_ESTABLISHED",
            "arm_pose_verified_before_pre": False,
            "future_episode_precondition": (
                "ARM_NAVIGATION_POSE_ADMISSION: every joint within its predeclared "
                "tolerance of the frozen navigation pose, checked BEFORE the "
                "production PRE capture. An arm off-pose refuses the episode rather "
                "than recording one under an unknown camera geometry"),
            "local_descriptions_do_not_model_the_arm": True,
            "local_topologies_observed": {
                "upstream": "camera_joint is fixed, base_link -> camera_link",
                "navfm_twin": "static top_arm_mount -> camera_link",
            },
            "consequence": (
                "neither local candidate can supply the arm chain, which raises "
                "what the vendor archive has to provide"),
            "separate_later_experiment": (
                "deliberately moving the camera during navigation is a new "
                "intervention, not a variation folded into this baseline"),
        },
        "authority_classes": list(AUTHORITY_CLASSES),
        "candidates": {
            "upstream": _candidate(UPSTREAM_REL, "UPSTREAM_REFERENCE"),
            "navfm": _candidate(NAVFM_REL, "LOCAL_REFERENCE"),
        },
        "reconciliation": rows,
        "populated_cells": sum(
            1 for r in rows for k in ("navfm_reference_value",
                                      "upstream_reference_value")
            if r[k] not in (PENDING, None)),
        "pending_cells": sum(
            1 for r in rows for k in ("vendor_value", "adopted_experimental_value")
            if r[k] == PENDING) + sum(
            1 for r in rows if r["physical_measurement"] == NOT_MEASURED),
        "vendor_acquisition": {
            "source_url": PENDING, "acquisition_timestamp": PENDING,
            "archive_sha256": PENDING, "upstream_commit_or_version": PENDING,
            "extracted_closure_digest": PENDING,
            "licence_status": "NOT_DECLARED_BY_OFFICIAL_SOURCES",
        },
        "CLAIM_BOUNDARY": (
            "no apparatus decision is recorded here. Every adopted experimental "
            "value is PENDING and every physical measurement is NOT_MEASURED. A "
            "local reference value is not a vendor value and is not a measurement"),
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }

    sha = emit_evidence(OUT, record, required_keys=(
        "check", "ROBOT_DESCRIPTION_AUTHORITY", "candidates", "reconciliation",
        "vendor_acquisition", "CLAIM_BOUNDARY", "EXECUTION_STATUS"))

    print("=" * 70)
    print("ROBOT APPARATUS RECONCILIATION SCAFFOLD")
    print("=" * 70)
    print(f"HEAD                {head[:12]}")
    for name, candidate in record["candidates"].items():
        print(f"  {name:10s} {candidate['parse_status']:8s} "
              f"sha={str(candidate['sha256'])[:12]} "
              f"{candidate.get('refusal_category', '')}")
    print()
    print(f"{'quantity':32s} {'upstream':>12s} {'navfm':>12s}  adopted")
    for row in record["reconciliation"]:
        up = str(row["upstream_reference_value"])[:12]
        nv = str(row["navfm_reference_value"])[:12]
        print(f"  {row['quantity']:30s} {up:>12s} {nv:>12s}  "
              f"{row['adopted_experimental_value']}")
    print()
    print(f"populated cells     {record['populated_cells']}")
    print(f"pending cells       {record['pending_cells']}")
    print(f"licence status      {record['vendor_acquisition']['licence_status']}")
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha}")
    print("APPARATUS DECIDED   none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
