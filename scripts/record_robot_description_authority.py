"""Decide which vendor description is the whole-robot apparatus root.

Two descriptions of the M3 Pro exist in the vendor archive and they disagree
about things that matter: whether the wheels turn, how many cameras there are,
and what the camera link is called. Only one of them is what the robot loads
when it boots, and that is the one this record selects.

The comparison is reported rather than reconciled. Where the two differ the
difference is named and classified; nothing is merged, averaged or quietly
preferred, because a merged model would be a third robot that neither the
vendor nor the hardware has.

Four questions stay outside the decision and are restated here so they cannot
be absorbed into it: redistribution permission, agreement with the physical
robot, collider construction, and freedom from defects. The selected source has
broken sibling variants, mesh-only collision geometry and no licence that
covers it, and it is still what the production software loads.
"""

from __future__ import annotations

import collections
import datetime as _dt
import hashlib
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402
from navfm.isaac.description_authority import (  # noqa: E402
    DECISION_RULES,
    Candidate,
    classify_authority,
)

OUT = REPO / "gates/digital_twin/robot_description_authority_20260918.json"
STAGING = pathlib.Path("/home/favl/Downloads/yahboom/extracted")
M3PRO_WS = STAGING / "M3Pro_ws-0.0.1_f08db69b" / "m3pro_ws"
CAR_WS = STAGING / "yahboomcar_ws_8da310fb" / "yahboomcar_ws"

RUNTIME_REL = "src/M3Pro/urdf/m3pro.urdf"
MOVEIT_REL = "src/yahboom_M3Pro_description/urdf/M3Pro.urdf"
BRINGUP = "src/m3pro_bringup/launch/car_base.launch.py"
MOVEIT_LAUNCH = "src/M3Pro_config/launch/demo.launch.py"
MOVEIT_SETUP = "src/M3Pro_config/.setup_assistant"
MOVEIT_XACRO = "src/M3Pro_config/config/M3Pro.urdf.xacro"
MOVEIT_SRDF = "src/M3Pro_config/config/M3Pro.srdf"

PRIOR_EVIDENCE = (
    "gates/digital_twin/vendor_source_closure_20260918.json",
    "gates/digital_twin/production_description_chain_20260918.json",
    "gates/digital_twin/workspace_package_resolution_20260918.json",
    "gates/digital_twin/production_description_inventory_20260918.json",
)


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def workspace_digest(root: pathlib.Path) -> str:
    rows = sorted(f"{p.relative_to(root)}:{sha256_file(p)}"
                  for p in root.rglob("*") if p.is_file())
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def read_robot(path: pathlib.Path) -> dict[str, Any]:
    root = ET.fromstring(path.read_bytes())
    joints: dict[str, dict[str, Any]] = {}
    for joint in root.findall("joint"):
        origin, axis = joint.find("origin"), joint.find("axis")
        limit = joint.find("limit")
        parent, child = joint.find("parent"), joint.find("child")
        joints[str(joint.get("name"))] = {
            "type": joint.get("type"),
            "parent": parent.get("link") if parent is not None else None,
            "child": child.get("link") if child is not None else None,
            "xyz": origin.get("xyz") if origin is not None else None,
            "rpy": origin.get("rpy") if origin is not None else None,
            "axis": axis.get("xyz") if axis is not None else None,
            "lower": limit.get("lower") if limit is not None else None,
            "upper": limit.get("upper") if limit is not None else None,
            "effort": limit.get("effort") if limit is not None else None,
            "velocity": limit.get("velocity") if limit is not None else None,
        }
    return {
        "robot_name": root.get("name"),
        "links": [str(link.get("name")) for link in root.findall("link")],
        "joints": joints,
    }


def compare(runtime: dict[str, Any], moveit: dict[str, Any]) -> dict[str, Any]:
    """Classify every overlapping field. Nothing is reconciled."""
    fields = ("type", "parent", "child", "xyz", "rpy", "axis",
              "lower", "upper", "effort", "velocity")
    rows: list[dict[str, Any]] = []
    tally: collections.Counter[str] = collections.Counter()

    for name in sorted(set(runtime["joints"]) | set(moveit["joints"])):
        in_runtime = runtime["joints"].get(name)
        in_moveit = moveit["joints"].get(name)
        if in_runtime is None:
            tally["PRESENT_ONLY_IN_MOVEIT_DESCRIPTION"] += 1
            rows.append({"joint": name,
                         "classification": "PRESENT_ONLY_IN_MOVEIT_DESCRIPTION",
                         "moveit": in_moveit})
            continue
        if in_moveit is None:
            tally["PRESENT_ONLY_IN_RUNTIME_DESCRIPTION"] += 1
            rows.append({"joint": name,
                         "classification": "PRESENT_ONLY_IN_RUNTIME_DESCRIPTION",
                         "runtime": in_runtime})
            continue
        differing = {f: {"runtime": in_runtime[f], "moveit": in_moveit[f]}
                     for f in fields if in_runtime[f] != in_moveit[f]}
        if not differing:
            tally["IDENTICAL"] += 1
            rows.append({"joint": name, "classification": "IDENTICAL"})
            continue
        # Naming differences move a link's name without moving the link.
        naming_only = set(differing) <= {"parent", "child"}
        numeric = {"xyz", "rpy", "axis", "lower", "upper", "effort", "velocity"}
        if naming_only:
            classification = "NAMING_DIFFERENCE"
        elif set(differing) & numeric:
            classification = "NUMERICALLY_DIFFERENT"
        elif "type" in differing:
            classification = "JOINT_TYPE_DIFFERENT"
        else:
            classification = "AMBIGUOUS"
        tally[classification] += 1
        rows.append({"joint": name, "classification": classification,
                     "differing_fields": differing})

    link_only_runtime = sorted(set(runtime["links"]) - set(moveit["links"]))
    link_only_moveit = sorted(set(moveit["links"]) - set(runtime["links"]))
    return {
        "joint_rows": rows,
        "tally": dict(sorted(tally.items())),
        "links_only_in_runtime": link_only_runtime,
        "links_only_in_moveit": link_only_moveit,
        "shared_links": sorted(set(runtime["links"]) & set(moveit["links"])),
        "NOT_RECONCILED": (
            "differences are named, not merged. A merged model would be a third "
            "robot that neither the vendor nor the hardware has"),
    }


def completeness(model: dict[str, Any]) -> dict[str, str]:
    """What a candidate represents. Recorded, and not an input to the decision."""
    links, joints = model["links"], model["joints"]
    wheels = [n for n in links if "wheel" in n.lower()]
    arm = [n for n in joints if n.lower().startswith("arm") and
           joints[n]["type"] in {"revolute", "continuous", "prismatic"}]
    camera_links = [n for n in links if "camera" in n.lower() or n in
                    {"DCW2", "Camera"}]
    turning = [n for n in wheels
               if joints.get(f"{n}_Joint", {}).get("type") in
               {"revolute", "continuous"}]
    return {
        "chassis": "REPRESENTED" if "base_link" in links else "ABSENT",
        "mecanum_wheels": f"{len(wheels)} link(s)",
        "wheels_are_actuated":
            f"{len(turning)}/{len(wheels)} have a turning joint",
        "arm_dof": f"{len(arm)} actuated arm joint(s)",
        "camera_mechanical_mount":
            f"{len(camera_links)} camera link(s): {camera_links}",
        "rgb_depth_optical_frames": "NOT_REPRESENTED_IN_SOURCE",
        "tof_representation": "NOT_REPRESENTED_IN_SOURCE",
        "base_link": "REPRESENTED" if "base_link" in links else "ABSENT",
        "odom_frames": "NOT_REPRESENTED_IN_SOURCE",
    }


def material_differences(
    runtime: dict[str, Any], moveit: dict[str, Any], comparison: dict[str, Any]
) -> dict[str, Any]:
    """Name the differences that change what the rival can safely be used for.

    A tally of nine numerically-different joints is not a finding until someone
    looks at which nine. Doing that here rather than leaving it to a reader is
    the difference between a record and a dump, and two of these differences
    decide how far the rival's planning authority actually reaches.
    """
    def arm_limits(model: dict[str, Any]) -> dict[str, tuple[str | None, str | None]]:
        return {n: (j["lower"], j["upper"]) for n, j in model["joints"].items()
                if n.lower().startswith("arm") and j["type"] == "revolute"}

    moveit_limits = arm_limits(moveit)
    runtime_limits = arm_limits(runtime)
    distinct_moveit = {v for v in moveit_limits.values()}
    distinct_runtime = {v for v in runtime_limits.values()}

    wheel_type_differs = [
        row["joint"] for row in comparison["joint_rows"]
        if "wheel" in row["joint"]
        and "type" in (row.get("differing_fields") or {})]
    axis_flipped = [
        row["joint"] for row in comparison["joint_rows"]
        if "axis" in (row.get("differing_fields") or {})]

    runtime_names = set(runtime["joints"])
    moveit_names = set(moveit["joints"])
    name_only_in_moveit = sorted(moveit_names - runtime_names)
    name_only_in_runtime = sorted(runtime_names - moveit_names)

    return {
        "ARM_JOINT_LIMITS": {
            "runtime": runtime_limits,
            "moveit": moveit_limits,
            "distinct_limit_pairs_runtime": len(distinct_runtime),
            "distinct_limit_pairs_moveit": len(distinct_moveit),
            "moveit_limits_are_uniform": len(distinct_moveit) == 1,
            "reading": (
                "the rival gives every revolute arm joint the same symmetric "
                "range while the production root gives each a different "
                "asymmetric one. A single repeated value across every joint is "
                "what a default looks like, and a per-joint asymmetric one is "
                "what a considered value looks like. This is an INFERENCE about "
                "which is a placeholder, not a measurement of the arm"
                if len(distinct_moveit) == 1 else
                "both sources give per-joint limits"),
            "CONSEQUENCE": (
                "the rival's joint limits must not be transplanted onto the "
                "production root. Neither set has been compared against the "
                "physical arm"),
        },
        "JOINT_NAME_MISMATCH": {
            "only_in_moveit": name_only_in_moveit,
            "only_in_runtime": name_only_in_runtime,
            "CONSEQUENCE": (
                "the rival names the fourth arm joint arm4_Joiint and the "
                "production root names it arm4_Joint, so the MoveIt planning "
                "group cannot bind to the production description as it stands. "
                "The rival's planning authority covers structure -- groups, end "
                "effector, solver choice -- and does not carry over to the "
                "production root without a rename that is itself an apparatus "
                "change"),
            "NOT_REPAIRED": True,
        },
        "WHEEL_ACTUATION": {
            "joints_whose_type_differs": wheel_type_differs,
            "runtime_type": "fixed",
            "moveit_type": "revolute with lower, upper, effort and velocity all 0",
            "reading": (
                "neither source models a turning wheel. One says so by typing the "
                "joint fixed and the other by giving a revolute joint a zero "
                "range, so a twin built from either has a base that does not roll "
                "in its own kinematics"),
            "CONSEQUENCE": "recorded as a VENDOR_MODEL_LIMITATION of both sources",
        },
        "AXIS_SIGN": {
            "joints": axis_flipped,
            "reading": (
                "axis directions differ in sign or direction on these joints, so "
                "a positive command means opposite motions in the two models"),
        },
        "ORIGIN_PRECISION_PATTERN": {
            "reading": (
                "the production root carries rounded origins such as 0 0 1.5708 "
                "where the rival carries raw exported ones such as 6.3751E-05 0 "
                "0.028395. That is consistent with the production file having "
                "been tidied after export and the rival being closer to the CAD "
                "output. INFERENCE, and it does not tell us which is nearer the "
                "physical robot"),
        },
        "SUMMARY": (
            "the two sources are not minor variants of one model. They differ in "
            "arm joint limits, axis directions, a joint name, wheel joint type "
            "and camera link naming, and they agree exactly on the camera mount "
            "transform and the wheel origins"),
    }


def negative_controls() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_description_authority.py",
         "-p", "no:warnings", "-q", "--tb=no"],
        cwd=REPO, capture_output=True, text=True, check=False,
        env={k: v for k, v in __import__("os").environ.items()
             if k != "PYTHONPATH"})
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return {
        "suite": "tests/test_description_authority.py",
        "exit_code": proc.returncode,
        "VERDICT": "PASS" if proc.returncode == 0 else "FAIL",
        "last_line": lines[-1][:110] if lines else "",
        "mutations": {
            "ROBOT_STATE_PUBLISHER_EDGE_REMOVED": "authority withdrawn",
            "BRINGUP_EDGE_REMOVED": "authority withdrawn",
            "BRINGUP_POINTED_AT_THE_RIVAL": "authority moves to the rival",
            "TWO_COMPETING_ROOTS_ONE_CONFIGURATION": "AMBIGUOUS, decision stops",
            "TWO_PRODUCTION_ROOTS_SEPARATE_CONFIGURATIONS": "AMBIGUOUS, stops",
            "TUTORIAL_SUBSTITUTED_FOR_THE_ROOT": "gains no authority",
            "RICHER_RIVAL_OFFERED": "still loses to the production chain",
            "COMPLETENESS_AS_AN_INPUT": "the Candidate type has no field for it",
        },
    }


def main() -> int:
    own = str(OUT.relative_to(REPO))
    head = _git("rev-parse", "HEAD")
    dirty = [line for line in _git("status", "--porcelain").splitlines()
             if line.strip() and own not in line]

    runtime_path = M3PRO_WS / RUNTIME_REL
    moveit_path = CAR_WS / MOVEIT_REL
    runtime_model = read_robot(runtime_path)
    moveit_model = read_robot(moveit_path)

    # MoveIt's own record of which description it was built from. A first-party
    # declaration is better evidence than inferring the target from the xacro
    # include, so it is read rather than assumed -- and the two are compared.
    setup_text = (CAR_WS / MOVEIT_SETUP).read_text(encoding="utf-8")
    declared_package = re.search(r"urdf:\s*\n\s*package:\s*(\S+)", setup_text)
    declared_path = re.search(r"urdf:\s*\n(?:.*\n)?\s*relative_path:\s*(\S+)",
                              setup_text)
    setup_declares = {
        "package": declared_package.group(1) if declared_package else None,
        "relative_path": declared_path.group(1) if declared_path else None,
    }
    setup_matches_resolved = (
        setup_declares["package"] == "yahboom_M3Pro_description"
        and setup_declares["relative_path"] == "urdf/M3Pro.urdf")
    bringup_text = (M3PRO_WS / BRINGUP).read_text(encoding="utf-8")

    # Does any production bringup file reach the MoveIt sources at all?
    cross = subprocess.run(
        ["grep", "-rl", "-e", "M3Pro_config", "-e", "yahboom_M3Pro_description",
         str(M3PRO_WS / "src" / "m3pro_bringup")],
        capture_output=True, text=True, check=False).stdout.split()

    candidates = [
        Candidate(
            identity=f"M3Pro/{RUNTIME_REL.split('/', 2)[2]}",
            sha256=sha256_file(runtime_path),
            robot_name=str(runtime_model["robot_name"]),
            reached_by_production_bringup=True,
            reaches_robot_state_publisher=True,
            reached_by_manipulator_tooling=False,
            shares_configuration_with_production=True),
        Candidate(
            identity=f"yahboom_M3Pro_description/{MOVEIT_REL.split('/', 2)[2]}",
            sha256=sha256_file(moveit_path),
            robot_name=str(moveit_model["robot_name"]),
            reached_by_production_bringup=False,
            reaches_robot_state_publisher=True,
            reached_by_manipulator_tooling=True,
            shares_configuration_with_production=False,
            planning_semantics=("arm_group", "grip_group",
                                "end effector gripper on arm5",
                                "KDL kinematics solver", "joint limits",
                                "named states up/down/init/open/close")),
    ]
    verdict = classify_authority(candidates)

    comparison = compare(runtime_model, moveit_model)
    camera_runtime = runtime_model["joints"].get("DCW2_Joint", {})
    camera_moveit = moveit_model["joints"].get("DCW2_Joint", {})
    camera_agrees = all(
        camera_runtime.get(f) == camera_moveit.get(f)
        for f in ("type", "parent", "xyz", "rpy"))

    record: dict[str, Any] = {
        "check": "ROBOT_DESCRIPTION_AUTHORITY",
        "artifact_semantics": "APPARATUS_SOURCE_AUTHORITY_DECIDED",
        "author": "Frank Asante Van Laarhoven",
        "provenance_observed_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "repository_head": head,
        "worktree_clean_at_measurement": not dirty,
        "other_dirty_entries": dirty,
        "prior_evidence_not_rewritten": [
            {"path": p, "sha256": sha256_file(REPO / p)} for p in PRIOR_EVIDENCE
            if (REPO / p).is_file()],

        "DEFINITION": {
            "AUTHORITATIVE_WHOLE_ROBOT_DESCRIPTION": (
                "the vendor-supplied robot-description source that the production "
                "M3 Pro software actually uses to publish robot_description for "
                "the physical whole-robot configuration"),
            "decided_by": "the production execution and reference chain",
            "explicitly_not_decided_by": [
                "filename", "completeness", "which file parses most cleanly",
                "which model is easiest to import", "mesh quality",
                "which model best fits our intended simulator", "recency"],
            "why": ("every one of those is a way to end up simulating a robot the "
                    "vendor does not ship"),
            "frozen_before_candidates_were_scored": True,
        },
        "DECISION_RULES": list(DECISION_RULES),

        "CANDIDATES": [
            {**candidates[0].as_record(),
             "workspace": "M3Pro_ws-0.0.1",
             "package": "M3Pro",
             "relative_path": RUNTIME_REL,
             "link_count": len(runtime_model["links"]),
             "joint_count": len(runtime_model["joints"]),
             "referenced_by_production_bringup": {
                 "entry_point": BRINGUP,
                 "evidence": "model= assignment from package M3Pro, then xacro, "
                             "then robot_state_publisher parameters",
                 "line_evidence_in": PRIOR_EVIDENCE[1]},
             "referenced_by_moveit": False},
            {**candidates[1].as_record(),
             "workspace": "yahboomcar_ws",
             "package": "yahboom_M3Pro_description",
             "relative_path": MOVEIT_REL,
             "link_count": len(moveit_model["links"]),
             "joint_count": len(moveit_model["joints"]),
             "referenced_by_production_bringup": False,
             "referenced_by_moveit": {
                 "entry_point": MOVEIT_LAUNCH,
                 "mechanism": "MoveItConfigsBuilder('M3Pro', "
                              "package_name='M3Pro_config')",
                 "first_party_declaration": MOVEIT_SETUP,
                 "declared_urdf_package": setup_declares["package"],
                 "declared_urdf_relative_path": setup_declares["relative_path"],
                 "declaration_matches_the_resolved_file": setup_matches_resolved,
                 "xacro": MOVEIT_XACRO,
                 "srdf": MOVEIT_SRDF,
                 "setup_assistant_sha256": sha256_file(CAR_WS / MOVEIT_SETUP)}},
        ],

        "CONFIGURATION_SEPARATION": {
            "bringup_references_moveit_sources": bool(cross),
            "files_found": cross,
            "finding": ("no file under m3pro_bringup references M3Pro_config or "
                        "yahboom_M3Pro_description, so the two descriptions are "
                        "never loaded as competing roots in one configuration"),
            "consequence": "rule C does not apply",
            "bringup_mentions_robot_state_publisher":
                "robot_state_publisher" in bringup_text,
            "moveit_publishes_independently": (
                "MoveIt's generated rsp launch publishes robot_description within "
                "the MoveIt configuration. That is a separate configuration, not a "
                "second root inside the production one"),
        },

        "SOURCE_COMPARISON": comparison,
        "MATERIAL_DIFFERENCES": material_differences(
            runtime_model, moveit_model, comparison),
        "COMPLETENESS": {
            "runtime": completeness(runtime_model),
            "moveit": completeness(moveit_model),
            "NOT_AN_INPUT": (
                "recorded for the reader. Authority is not completeness, and this "
                "section is not consulted by the classifier"),
        },

        "CAMERA_AUTHORITY": {
            "CAMERA_TO_ARM_TOPOLOGY_AUTHORITY": "PRODUCTION_RUNTIME_DESCRIPTION",
            "runtime_joint": {"name": "DCW2_Joint", **camera_runtime},
            "moveit_joint": {"name": "DCW2_Joint", **camera_moveit},
            "both_sources_agree_on_parentage_and_transform": camera_agrees,
            "corroboration": (
                "the rival source encodes the same fixed joint, the same parent "
                "arm4 and the same transform, so the arm mounting is corroborated "
                "rather than contested. Only the child link name differs"),
            "CAMERA_EXTRINSIC": "VENDOR_SOFTWARE_VALUE",
            "PHYSICAL_CAMERA_EXTRINSIC": "NOT_MEASURED",
            "SECOND_CAMERA_IN_RIVAL": {
                "joint": "Camera_Joint",
                "detail": moveit_model["joints"].get("Camera_Joint"),
                "reading": (
                    "the MoveIt source additionally carries a revolute Camera "
                    "joint on base_link that the production root does not have. "
                    "It does not contradict the arm mounting; it is a second "
                    "entity, and which physical part it corresponds to is not "
                    "established here"),
                "status": "UNRECONCILED_DIFFERENCE",
            },
        },

        "BROKEN_REFERENCE_IMPACT": {
            "runtime_root": {
                "affected": False,
                "detail": ("m3pro.urdf resolves 18 of 18 references. The "
                           "arM3Pro.STL defect is in the M3Pro_robot1 and "
                           "M3Pro_robot2 sibling variants, which the production "
                           "chain does not load"),
                "blocks_authority": False},
            "sibling_variants": {
                "affected": True,
                "files": ["src/M3Pro/urdf/M3Pro_robot1.urdf",
                          "src/M3Pro/urdf/M3Pro_robot2.urdf"],
                "blocks_authority": False,
                "detail": "a broken sibling does not invalidate a root that does "
                          "not depend on it"},
            "moveit_source": {
                "affected": True,
                "detail": ("references package dofbot_M3Pro_descripton, which is "
                           "declared nowhere; 19 of 20 references resolve"),
                "blocks_authority": False,
                "note": "it is not being selected as the whole-robot root anyway, "
                        "and this defect is not the reason"},
            "NOT_REPAIRED": True,
        },

        "SEPARATED_VERDICTS": {
            "SOURCE_AUTHORITY": "WHOLE_ROBOT_RUNTIME_AUTHORITY",
            "SOURCE_CONFORMANCE": "XML_VALID",
            "RESOURCE_CLOSURE": "COMPLETE (18/18)",
            "MODEL_COMPLETENESS": "PARTIAL - see COMPLETENESS",
            "why_separate": ("a source can be authoritative and defective at the "
                             "same time. Authority is a fact about the vendor's "
                             "software, not a certificate of quality"),
        },

        "NEGATIVE_CONTROLS": negative_controls(),
        "AUTHORITY_VERDICT": verdict,

        "SELECTED_SOURCE_IDENTITY": {
            "package": "M3Pro",
            "package_xml_sha256": sha256_file(M3PRO_WS / "src/M3Pro/package.xml"),
            "relative_path": RUNTIME_REL,
            "source_sha256": sha256_file(runtime_path),
            "byte_size": runtime_path.stat().st_size,
            "workspace_closure_digest": workspace_digest(M3PRO_WS),
            "embedded_git": (M3PRO_WS / ".git").is_dir(),
            "bringup_entry_point": BRINGUP,
            "bringup_sha256": sha256_file(M3PRO_WS / BRINGUP),
            "resource_closure": "18/18 resolved",
            "reproducible_from": ("archive closure digest plus package-relative "
                                  "path plus file hash, never a host path"),
        },

        "AUTHORITATIVE_ROBOT_DESCRIPTION": verdict[
            "AUTHORITATIVE_ROBOT_DESCRIPTION"],
        "AUTHORITY_SCOPE": verdict["AUTHORITY_SCOPE"],
        "MOVEIT_DESCRIPTION_ROLE": verdict["roles"].get(candidates[1].identity),
        "MOVEIT_AUTHORITY_REACH": {
            "covers": ["planning group membership", "end effector declaration",
                       "kinematics solver choice", "named states",
                       "SRDF collision semantics"],
            "does_not_cover": [
                "joint limits, which differ from the production root and look "
                "like a uniform default in the rival",
                "joint naming, which does not match the production root",
                "whole-robot structure"],
            "why": ("scoping the rival is not the same as importing it. Its "
                    "planning structure is usable; its numbers are a separate "
                    "question and were not adopted"),
        },
        "SELECTED_SOURCE_LIMITATIONS": [
            "collision geometry is mesh-only; no primitive dimensions exist in it",
            "wheel joints are fixed, so the source does not model wheel rotation",
            "RGB, depth and optical camera frames are not represented",
            "the two ranging sensors are not represented as links",
            "no licence in the archive covers it",
            "every numeric value in it is a vendor software value",
        ],

        "AUTHORITY_IS_NOT_PHYSICAL_CALIBRATION": (
            "selecting this source establishes nothing about the actual wheel "
            "radius, chassis dimensions, camera extrinsic, TOF mounting, joint "
            "zero offsets or as-built tolerances. All remain subject to physical "
            "reconciliation"),
        "AUTHORITY_IS_NOT_REDISTRIBUTION_PERMISSION": (
            "REDISTRIBUTION stays NOT_AUTHORISED_PENDING_CLARIFICATION. Saying "
            "this is the source the production software uses is not a licence to "
            "publish it or anything derived from it"),
        "AUTHORITY_IS_NOT_A_COLLIDER_STRATEGY": (
            "how collision geometry is built from this source is Decision B and "
            "is untouched"),

        "ORBBEC_RUNTIME_DRIVER": "NOT_PRESENT_IN_ACQUIRED_CLOSURE",
        "TOF_DEVICE_DRIVERS": "NOT_IDENTIFIED_IN_ACQUIRED_CLOSURE",
        "driver_absence_note": (
            "these affect sensor-runtime reproducibility, not structural source "
            "authority, and do not block this decision"),
        "CAD_ROLE": "CAD_GEOMETRY_REFERENCE_CANDIDATE",
        "cad_note": ("ROSMASTER-M3Pro.x_t is not the robot_description authority, "
                     "was not converted, and does not override the ROS production "
                     "graph. Its product association remains unestablished"),

        "REDISTRIBUTION": "NOT_AUTHORISED_PENDING_CLARIFICATION",
        "DECISION_B": "UNRESOLVED_AND_NOT_TOUCHED",
        "PRODUCTION_DESCRIPTION_IDENTIFIED": True,
        "PRODUCTION_M3PRO_USD": "NOT_GENERATED",
        "DIGITAL_TWIN_REQUALIFICATION": "NOT_STARTED",
        "MUTO_PRODUCT_ROLE": "TUTORIAL_CONTENT",
        "SCIENTIFIC_ARM_A_N": 0,
        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
    }

    sha = emit_evidence(OUT, record, required_keys=(
        "check", "DEFINITION", "DECISION_RULES", "CANDIDATES",
        "SOURCE_COMPARISON", "NEGATIVE_CONTROLS", "AUTHORITY_VERDICT",
        "SELECTED_SOURCE_IDENTITY", "AUTHORITATIVE_ROBOT_DESCRIPTION",
        "AUTHORITY_IS_NOT_PHYSICAL_CALIBRATION"))

    print("=" * 78)
    print("ROBOT DESCRIPTION AUTHORITY")
    print("=" * 78)
    print(f"  HEAD {head[:12]}  clean={record['worktree_clean_at_measurement']}")
    print(f"  controls      {record['NEGATIVE_CONTROLS']['VERDICT']}  "
          f"{record['NEGATIVE_CONTROLS']['last_line']}")
    print()
    for entry in record["CANDIDATES"]:
        print(f"  {entry['identity']:46s} {entry['sha256'][:12]}")
        print(f"    robot={entry['robot_name']!r} links={entry['link_count']} "
              f"joints={entry['joint_count']}  bringup="
              f"{bool(entry['referenced_by_production_bringup'])} "
              f"moveit={bool(entry['referenced_by_moveit'])}")
    print()
    print(f"  comparison    {comparison['tally']}")
    print(f"    only runtime links {comparison['links_only_in_runtime']}")
    print(f"    only moveit links  {comparison['links_only_in_moveit']}")
    material = record["MATERIAL_DIFFERENCES"]
    print(f"    arm limits uniform in rival: "
          f"{material['ARM_JOINT_LIMITS']['moveit_limits_are_uniform']}")
    print(f"    joint name mismatch: "
          f"{material['JOINT_NAME_MISMATCH']['only_in_moveit']} vs "
          f"{material['JOINT_NAME_MISMATCH']['only_in_runtime']}")
    print(f"    wheels differ in type: "
          f"{len(material['WHEEL_ACTUATION']['joints_whose_type_differs'])}")
    print()
    camera = record["CAMERA_AUTHORITY"]
    print(f"  camera        {camera['CAMERA_TO_ARM_TOPOLOGY_AUTHORITY']}")
    print(f"                both sources agree: "
          f"{camera['both_sources_agree_on_parentage_and_transform']}")
    print(f"                extrinsic {camera['CAMERA_EXTRINSIC']}, physical "
          f"{camera['PHYSICAL_CAMERA_EXTRINSIC']}")
    print()
    print(f"  VERDICT       {verdict['VERDICT']}")
    print(f"  AUTHORITATIVE {record['AUTHORITATIVE_ROBOT_DESCRIPTION']}")
    print(f"  SCOPE         {record['AUTHORITY_SCOPE']}")
    print(f"  MOVEIT ROLE   {record['MOVEIT_DESCRIPTION_ROLE']}")
    print()
    print(f"  REDISTRIBUTION {record['REDISTRIBUTION']}")
    print(f"  DECISION_B     {record['DECISION_B']}")
    print(f"  artefact      {OUT.relative_to(REPO)}")
    print(f"  sha256        {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
