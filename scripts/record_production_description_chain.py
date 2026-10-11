"""Trace the production robot_description chain for the Orin M3 Pro.

Answers the tranche's central question from the launch graph: m3pro_bringup's
car_base.launch.py builds robot_description from package M3Pro, urdf/m3pro.urdf,
through xacro, and hands it to robot_state_publisher. That edge is cited, not
inferred.

Two findings change later work.

The camera is mounted on the arm, confirmed by the vendor's own description
rather than by product photography: DCW2_Joint is a fixed joint whose parent is
arm4. So base_link to camera is configuration-dependent through the arm chain,
and the fixed calibration is arm4 to camera_link. The vendor encodes a value for
it, which is a software value and not a measurement.

And every collision geometry in the production description is a mesh. The
collider reconstruction built in the reference tranche handles box, cylinder and
sphere, and refuses meshes by design. The conversion strategy chosen for
primitive geometry does not carry over unchanged, and that is better known now
than after an asset had been built.

Nothing is adopted. The chain is identified and left AWAITING_REVIEW.
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

OUT = REPO / "gates/digital_twin/production_description_chain_20260918.json"
STAGING = pathlib.Path("/home/favl/Downloads/yahboom/extracted")
M3PRO_WS = STAGING / "M3Pro_ws-0.0.1_f08db69b" / "m3pro_ws"
CAR_WS = STAGING / "yahboomcar_ws_8da310fb" / "yahboomcar_ws"

BRINGUP = "src/m3pro_bringup/launch/car_base.launch.py"
PRODUCTION_URDF = "src/M3Pro/urdf/m3pro.urdf"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def workspace(root: pathlib.Path, label: str) -> dict[str, Any]:
    rows = [(str(p.relative_to(root)), sha256_file(p))
            for p in sorted(root.rglob("*")) if p.is_file()]
    digest = hashlib.sha256(
        "\n".join(f"{p}:{h}" for p, h in rows).encode()).hexdigest()
    src = root / "src"
    return {
        "label": label,
        "staging_root": str(root),
        "file_count": len(rows),
        "closure_digest": digest,
        "packages": sorted(p.name for p in src.iterdir() if p.is_dir())
        if src.is_dir() else [],
        "embedded_git": (root / ".git").is_dir(),
    }


def bringup_graph() -> dict[str, Any]:
    """Trace the chain edge by edge, each cited to one line.

    Every edge is matched by its own pattern and each pattern must match exactly
    one line. A pattern that matches nothing means the chain is not what this
    function claims; a pattern that matches twice means the citation is
    ambiguous. Either way the trace refuses rather than reporting a graph it
    cannot support.
    """
    launch = M3PRO_WS / BRINGUP
    lines = launch.read_text(encoding="utf-8", errors="replace").splitlines()

    edges_wanted = (
        ("launch -> description file",
         r"^\s*model\s*=.*get_package_share_directory\(\s*['\"]M3Pro['\"]\s*\)"),
        ("description file -> robot_description (via xacro)",
         r"^\s*robot_description\s*=.*Command\(\[\s*['\"]xacro"),
        ("robot_description -> robot_state_publisher",
         r"^\s*parameters\s*=\s*\[\{\s*['\"]robot_description['\"]"),
        ("robot_state_publisher actually launched",
         r"^\s*robot_state_publisher_node\s*,\s*$"),
    )

    edges = []
    for name, pattern in edges_wanted:
        hits = [(n, line) for n, line in enumerate(lines, 1)
                if re.search(pattern, line)]
        if len(hits) != 1:
            raise SystemExit(
                f"chain edge {name!r} matched {len(hits)} lines in {BRINGUP}; "
                "the trace refuses to report an unsupported graph")
        number, line = hits[0]
        edges.append({"edge": name, "from": BRINGUP, "line": number,
                      "statement": line.strip()[:160]})

    return {
        "entry_point": BRINGUP,
        "entry_point_sha256": sha256_file(launch),
        "edges": edges,
        "resolved_description": PRODUCTION_URDF,
        "processed_through": "xacro (a plain URDF passes through unchanged)",
        "consumer": "robot_state_publisher",
        "method": ("one pattern per edge, each required to match exactly one "
                   "line, so a broken chain refuses instead of reporting"),
    }


def describe(path: pathlib.Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    links = [element.get("name") for element in root.findall("link")]
    joints = root.findall("joint")

    collision: collections.Counter[str] = collections.Counter()
    visual: collections.Counter[str] = collections.Counter()
    for link in root.findall("link"):
        pairs: tuple[tuple[str, collections.Counter[str]], ...] = (
            ("collision", collision), ("visual", visual))
        for tag, counter in pairs:
            for element in link.findall(tag):
                geometry = element.find("geometry")
                if geometry is not None:
                    for child in geometry:
                        counter[child.tag] += 1

    camera_edge = None
    for joint in joints:
        child_link = joint.find("child")
        if child_link is not None and child_link.get("link") == "camera_link":
            parent = joint.find("parent")
            origin = joint.find("origin")
            camera_edge = {
                "joint": joint.get("name"), "type": joint.get("type"),
                "parent_link": parent.get("link") if parent is not None else None,
                "origin_xyz": origin.get("xyz") if origin is not None else None,
                "origin_rpy": origin.get("rpy") if origin is not None else None,
                "authority_class": "VENDOR_SOFTWARE_VALUE",
                "not_a_measurement": True,
            }

    text = path.read_text(encoding="utf-8", errors="replace")
    refs = sorted(set(re.findall(r'filename="(package://[^"]+)"', text)))
    resolvable = 0
    for ref in refs:
        tail = ref[len("package://"):]
        package, _, rest = tail.partition("/")
        if (M3PRO_WS / "src" / package / rest).is_file():
            resolvable += 1

    wheels = [name for name in links if name and "wheel" in name.lower()]
    arm_joints = [j.get("name") for j in joints
                  if j.get("type") == "revolute"
                  and "wheel" not in (j.get("name") or "").lower()]

    return {
        "path": str(path.relative_to(M3PRO_WS)),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
        "robot_name": root.get("name"),
        "link_count": len(links),
        "joint_count": len(joints),
        "links": links,
        "joint_types": dict(collections.Counter(j.get("type") for j in joints)),
        "wheel_links": wheels,
        "revolute_non_wheel_joints": arm_joints,
        "collision_geometry": dict(collision),
        "visual_geometry": dict(visual),
        "package_references": len(refs),
        "references_resolvable_in_workspace": resolvable,
        "references_missing": len(refs) - resolvable,
        "camera_mount_edge": camera_edge,
    }


def licence_evidence() -> dict[str, Any]:
    """Read the licence at the package that actually ships the apparatus.

    The finding is not the declared string but where it came from. M3Pro's
    manifest still carries TurtleBot3's description, maintainer, authors and
    repository URLs, so its Apache 2.0 line is ROBOTIS's statement about
    ROBOTIS's package, inherited by copying a manifest and editing the name.
    It grants nothing about the M3 Pro meshes.
    """
    rows = []
    src = M3PRO_WS / "src"
    for manifest in sorted(src.glob("*/package.xml")):
        text = manifest.read_text(encoding="utf-8", errors="replace")

        def field(tag: str, text: str = text) -> str | None:
            found = re.search(rf"<{tag}[^>]*>([^<]*)</{tag}>", text)
            return found.group(1).strip() if found else None

        declared = field("license")
        urls = re.findall(r'<url[^>]*>([^<]*)</url>', text)
        foreign = [u for u in urls if "yahboom" not in u.lower()]
        rows.append({
            "package": manifest.parent.name,
            "declared_licence": declared,
            "declares_a_licence": bool(declared) and not (
                declared or "").startswith("TODO"),
            "maintainer_email": field("maintainer"),
            "description": (field("description") or "").strip()[:80],
            "repository_urls": urls,
                "manifest_is_third_party_copy": bool(foreign) and bool(declared)
            and not (declared or "").startswith("TODO"),
        })

    declaring = [r for r in rows if r["declares_a_licence"]]
    inherited = [r for r in rows if r["manifest_is_third_party_copy"]]

    urdf = (M3PRO_WS / PRODUCTION_URDF).read_text(encoding="utf-8", errors="replace")
    header = "\n".join(urdf.splitlines()[:4])

    return {
        "packages_examined": len(rows),
        "packages_declaring_a_licence": len(declaring),
        "packages_with_TODO": len(rows) - len(declaring),
        "rows": rows,
        "apparatus_package": "M3Pro",
        "apparatus_package_declared_licence": next(
            (r["declared_licence"] for r in rows if r["package"] == "M3Pro"), None),
        "INHERITED_MANIFEST_FINDING": {
            "packages": [r["package"] for r in inherited],
            "detail": ("the apparatus package M3Pro, and M3Pro_navigation "
                       "alongside it, still carry ROBOTIS TurtleBot3 metadata: a "
                       "TurtleBot3 description, a robotis.com maintainer, and "
                       "ROBOTIS-GIT repository and bugtracker URLs. The manifests "
                       "were copied and the name field edited. arm_util also "
                       "declares Apache-2.0 but carries its own metadata and is "
                       "not a copy; it ships no robot description"),
            "consequence": ("the Apache 2.0 line is ROBOTIS's statement about "
                            "ROBOTIS's package. It is not a Yahboom licence grant "
                            "covering m3pro.urdf or the 20 STL meshes"),
        },
        "urdf_carries_no_licence": "license" not in urdf.lower(),
        "urdf_header": header,
        "URDF_ORIGIN": {
            "exporter": "SolidWorks to URDF Exporter 1.6.0-1-g15f4949",
            "significance": ("the description was exported from a CAD assembly, "
                             "which is why every collision geometry is a mesh: the "
                             "exporter emits the visual mesh as the collision mesh. "
                             "The vendor also supplies ROSMASTER-M3Pro.x_t, a "
                             "Parasolid file, and a CAD source is where primitive "
                             "collider dimensions could legitimately come from. "
                             "That association is plausible and unproven"),
            "association_status": "HYPOTHESIS_NOT_ESTABLISHED",
        },
        "VERDICT": "LICENCE_NOT_ESTABLISHED_FOR_THE_APPARATUS_PACKAGE",
    }


def trace_discrimination() -> dict[str, Any]:
    """Run the control that proves the tracer can refuse, and record the result.

    The chain claim is only worth as much as the tracer's ability to reject a
    chain that is not there, so the verdict is measured here rather than
    asserted. A control that cannot be run is recorded as not run.
    """
    control = REPO / "scripts/validate_chain_trace_discrimination.py"
    proc = subprocess.run([sys.executable, str(control)],
                          capture_output=True, text=True, check=False)
    stdout = proc.stdout
    detected = next((line.strip() for line in stdout.splitlines()
                     if line.strip().startswith("detected ")), None)
    verdict = next((line.split()[-1] for line in stdout.splitlines()
                    if "VERDICT" in line), "NOT_RUN")
    return {
        "control_script": str(control.relative_to(REPO)),
        "exit_code": proc.returncode,
        "mutations_detected": detected,
        "VERDICT": verdict,
        "meaning": ("each edge of the claimed chain was mutated away in a scratch "
                    "copy and the tracer had to refuse. The real workspace is "
                    "never modified"),
    }


def main() -> int:
    observed_at = _dt.datetime.now(_dt.UTC).isoformat()
    production = describe(M3PRO_WS / PRODUCTION_URDF)
    graph = bringup_graph()

    mesh_only = set(production["collision_geometry"]) == {"mesh"}
    camera = production["camera_mount_edge"] or {}

    record: dict[str, Any] = {
        "check": "PRODUCTION_DESCRIPTION_CHAIN",
        "artifact_semantics": "CHAIN_IDENTIFIED_NOTHING_ADOPTED",
        "author": "Frank Asante Van Laarhoven",
        "provenance_observed_at": observed_at,
        "repository_head": _git("rev-parse", "HEAD"),
        "workspaces": [workspace(M3PRO_WS, "M3Pro_ws-0.0.1 (orin)"),
                       workspace(CAR_WS, "yahboomcar_ws (orin)")],
        "STAGING_PATHS_ARE_HOST_LOCAL": (
            "staging_root records where the measurement was taken on this host. "
            "It is not a reproducible identity and nothing in the repository may "
            "depend on it. The reproducible identity is closure_digest, and for "
            "the description itself its sha256. The vendor trees live outside "
            "the repository and no vendor byte is committed"),
        "extraction_note": (
            "yahboomcar_ws.zip ships 205 directories with mode d--------- and is "
            "not traversable as extracted. Directory modes were normalised in the "
            "staging copy only; no file content was altered and the original "
            "archive is byte-identical to acquisition"),
        "M3PRO_BRINGUP_GRAPH": graph,
        "TRACE_DISCRIMINATION": trace_discrimination(),
        "production_description": production,
        "PRODUCTION_DESCRIPTION_IDENTIFIED": True,
        "AUTHORITATIVE_ROBOT_DESCRIPTION": "AWAITING_REVIEW",
        "why_not_adopted": (
            "the chain is unambiguous, and adoption is a human apparatus decision. "
            "Identification is evidence; selection is not"),
        "MUTO_IDENTITY": {
            "VERDICT": "TUTORIAL_EXAMPLE_NOT_PRODUCTION",
            "evidence": [
                "no production launch in either Orin workspace references Muto",
                "the production chain resolves to M3Pro/urdf/m3pro.urdf",
                "Muto lives in the ROS2 course workspace, referenced only by an "
                "RViz display launch",
            ],
        },
        "CAMERA_MOUNT_FINDING": {
            "camera_is_arm_mounted": camera.get("parent_link", "").startswith("arm"),
            "joint": camera.get("joint"),
            "parent_link": camera.get("parent_link"),
            "joint_type": camera.get("type"),
            "vendor_encoded_extrinsic": {
                "xyz": camera.get("origin_xyz"), "rpy": camera.get("origin_rpy")},
            "authority_class": "VENDOR_SOFTWARE_VALUE",
            "significance": (
                "first-party confirmation, from the vendor's own production "
                "description, that the depth camera hangs off the arm chain. "
                "base_link to camera is configuration-dependent and the fixed "
                "calibration is arm4 to camera_link"),
            "still_required": (
                "a physical measurement of that same fixed transform. A vendor "
                "software value is not an as-built measurement"),
        },
        "COLLISION_GEOMETRY_FINDING": {
            "all_meshes": mesh_only,
            "collision_geometry": production["collision_geometry"],
            "consequence": (
                "the source-derived collider reconstruction built in the reference "
                "tranche handles box, cylinder and sphere and refuses meshes by "
                "design. The conversion strategy chosen against primitive geometry "
                "does not carry over unchanged to this description"),
            "decision_required": True,
        },
        "VENDOR_HARDWARE_RECONCILIATION": {
            "four_mecanum_wheels": {
                "status": "REPRESENTED",
                "evidence": production["wheel_links"]},
            "six_dof_arm": {
                "status": "REPRESENTED",
                "evidence": production["revolute_non_wheel_joints"]},
            "depth_camera": {
                "status": "REPRESENTED",
                "evidence": camera.get("joint")},
            "dual_tof": {
                "status": "NOT_REPRESENTED_IN_THIS_FILE",
                "note": ("laser handling lives in separate packages; not a defect "
                         "of the description")},
            "wheel_radius": {
                "status": "NOT_ENCODED_AS_PRIMITIVE",
                "note": ("geometry is mesh-based, so no radius literal exists to "
                         "compare against the 80 mm specification. It would have "
                         "to be measured from the mesh")},
        },
        "PARSER_STATUS": {
            "strict_xml": "the file parses as well-formed XML",
            "current_parser_verdict": "UNRESOLVED_DEPENDENCY",
            "reason": "no workspace-aware package:// resolver",
            "references_resolvable_in_workspace":
                f"{production['references_resolvable_in_workspace']}/"
                f"{production['package_references']}",
            "resolver_work": "NOT_IMPLEMENTED_IN_THIS_TRANCHE",
        },
        "LICENCE_EVIDENCE": licence_evidence(),
        "LICENCE": "NOT_AUTHORISED_PENDING_CLARIFICATION",
        "PRODUCTION_M3PRO_USD": "NOT_GENERATED",
        "SCIENTIFIC_ARM_A_N": 0,
        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "CLAIM_BOUNDARY": (
            "this identifies which description the vendor software loads. It "
            "adopts nothing, measures no physical quantity, and no vendor source "
            "is committed"),
    }

    sha = emit_evidence(OUT, record, required_keys=(
        "check", "M3PRO_BRINGUP_GRAPH", "production_description",
        "CAMERA_MOUNT_FINDING", "COLLISION_GEOMETRY_FINDING", "LICENCE_EVIDENCE",
        "TRACE_DISCRIMINATION",
        "AUTHORITATIVE_ROBOT_DESCRIPTION"))

    print("=" * 74)
    print("PRODUCTION DESCRIPTION CHAIN")
    print("=" * 74)
    for ws in record["workspaces"]:
        print(f"  {ws['label']:28s} files={ws['file_count']:4d} "
              f"packages={len(ws['packages']):2d} digest={ws['closure_digest'][:12]}")
    print()
    print(f"  entry point   {graph['entry_point']}")
    for edge in graph["edges"]:
        print(f"    :{edge['line']:<4d} {edge['edge']}")
    print(f"  resolves to   {graph['resolved_description']}")
    disc = record["TRACE_DISCRIMINATION"]
    print(f"  control       {disc['VERDICT']}  ({disc['mutations_detected']})")
    print()
    p = production
    print(f"  robot={p['robot_name']!r} links={p['link_count']} joints={p['joint_count']}")
    print(f"  wheels        {p['wheel_links']}")
    print(f"  arm joints    {len(p['revolute_non_wheel_joints'])} revolute")
    print(f"  collision     {p['collision_geometry']}")
    print(f"  package refs  {p['references_resolvable_in_workspace']}/"
          f"{p['package_references']} resolvable")
    print()
    c = record["CAMERA_MOUNT_FINDING"]
    print(f"  CAMERA        {c['joint']} type={c['joint_type']} "
          f"parent={c['parent_link']}  arm-mounted={c['camera_is_arm_mounted']}")
    print()
    lic = record["LICENCE_EVIDENCE"]
    print(f"  LICENCE       {lic['VERDICT']}")
    print(f"                {lic['packages_declaring_a_licence']}/"
          f"{lic['packages_examined']} packages declare a licence; "
          f"{len(lic['INHERITED_MANIFEST_FINDING']['packages'])} of those are "
          f"copied TurtleBot3 manifests, including the apparatus package")
    print(f"  URDF ORIGIN   {lic['URDF_ORIGIN']['exporter']}")
    print()
    print(f"  MUTO          {record['MUTO_IDENTITY']['VERDICT']}")
    print(f"  artefact      {OUT.relative_to(REPO)}")
    print(f"  sha256        {sha}")
    print("  AUTHORITATIVE_ROBOT_DESCRIPTION  AWAITING_REVIEW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
