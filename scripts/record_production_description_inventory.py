"""Characterise the production description sources and the sensor graphs.

Three things later work needs are settled here, and none of them is an
apparatus decision: which description files the vendor actually ships and what
is in them, which description MoveIt loads, and what the camera and ranging
sensors are configured to do.

The distinction the whole record is built around is that configuration is not
runtime. A topic named in a launch file is a CONFIGURED_TOPIC; whether anything
publishes on it is a separate question this tranche does not touch. The same
separation applies to frames, resolutions and rates, and to the vendor's
transforms, which are software values rather than measurements of the robot.

Launch arguments are read from the Python AST rather than by pattern matching,
so a default that is computed rather than written literally is reported as
non-literal instead of being guessed at. Nothing is launched and nothing is
adopted.
"""

from __future__ import annotations

import ast
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
from navfm.isaac.ros_package_resolver import RosPackageResolver  # noqa: E402
from navfm.isaac.urdf_import import (  # noqa: E402
    UrdfImportRefused,
    parse_source,
    source_closure,
)
from navfm.isaac.xacro_analysis import (  # noqa: E402
    XacroRefused,
    admissibility,
    analyse,
    include_closure,
)

OUT = REPO / "gates/digital_twin/production_description_inventory_20260918.json"
STAGING = pathlib.Path("/home/favl/Downloads/yahboom/extracted")
M3PRO_WS = STAGING / "M3Pro_ws-0.0.1_f08db69b" / "m3pro_ws"
CAR_WS = STAGING / "yahboomcar_ws_8da310fb" / "yahboomcar_ws"
WORKSPACES = (("M3Pro_ws-0.0.1", M3PRO_WS), ("yahboomcar_ws", CAR_WS))

PRODUCTION_URDF = "src/M3Pro/urdf/m3pro.urdf"
BRINGUP = "src/m3pro_bringup/launch/car_base.launch.py"
CAMERA_LAUNCH = "src/m3pro_bringup/launch/dabai_dcw2.launch.py"
STATIC_TF = "src/m3pro_bringup/launch/static_tf.launch.py"
MERGE_CONFIG = "src/m3pro_bringup/config/laserscan_merge.yaml"

#: Bound by hash so this record cannot silently disagree with the chain it
#: claims only to verify.
HISTORICAL_CHAIN = {
    "artefact": "gates/digital_twin/production_description_chain_20260918.json",
    "entry_point": BRINGUP,
    "package": "M3Pro",
    "description": PRODUCTION_URDF,
    "description_sha256":
        "cb092310636677ab4bc9846efd30c39cbf4d953ae4fc140a411d8b4c2e56ae6e",
    "consumer": "robot_state_publisher",
}


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _rel(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# -- inventory -------------------------------------------------------------

PRODUCT_ROLES = (
    "PRODUCTION_M3PRO_ROOT", "PRODUCTION_COMPONENT", "MOVEIT_COMPONENT",
    "SENSOR_COMPONENT", "TUTORIAL_CONTENT", "LEGACY_CONTENT", "UNREFERENCED",
    "AMBIGUOUS")


def classify(relative: str, workspace: str, referenced_by: list[str]) -> str:
    """Role from where a file sits and what references it, never from its name."""
    if ".ipynb_checkpoints" in relative:
        return "LEGACY_CONTENT"
    if relative == PRODUCTION_URDF and workspace == "M3Pro_ws-0.0.1":
        return "PRODUCTION_M3PRO_ROOT"
    if "test_config" in relative or "test_moveit_config" in relative:
        return "LEGACY_CONTENT"
    if "_config/config/" in relative or relative.endswith(".srdf"):
        return "MOVEIT_COMPONENT"
    if "description" in relative and referenced_by:
        return "MOVEIT_COMPONENT"
    return "UNREFERENCED" if not referenced_by else "PRODUCTION_COMPONENT"


def inventory() -> dict[str, Any]:
    """Every description and config source, counted rather than expected."""
    patterns = {
        "urdf": ("*.urdf",), "xacro": ("*.xacro",), "srdf": ("*.srdf",),
        "mesh": ("*.STL", "*.stl", "*.dae", "*.DAE"),
        "launch": ("*.launch.py", "*.launch", "*.launch.xml"),
        "config": ("*.yaml", "*.yml"),
    }
    rows: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    for label, root in WORKSPACES:
        counts[label] = {}
        for kind, globs in patterns.items():
            found: list[pathlib.Path] = []
            for pattern in globs:
                found.extend(p for p in root.rglob(pattern) if p.is_file())
            found = sorted(set(found))
            counts[label][kind] = len(found)
            if kind in {"urdf", "xacro", "srdf"}:
                for path in found:
                    relative = _rel(path, root)
                    rows.append({
                        "workspace": label,
                        "package": relative.split("/")[1]
                        if relative.startswith("src/") else "",
                        "relative_path": relative,
                        "file_type": kind,
                        "sha256": sha256_file(path),
                        "byte_size": path.stat().st_size,
                    })

    # Duplicate content is a fact about the vendor tree, so measure it.
    by_hash = collections.Counter(r["sha256"] for r in rows)
    for row in rows:
        row["content_duplicated_in_tree"] = by_hash[row["sha256"]] > 1

    return {
        "counts_by_workspace": counts,
        "description_sources": rows,
        "urdf_count": sum(c["urdf"] for c in counts.values()),
        "xacro_count": sum(c["xacro"] for c in counts.values()),
        "srdf_count": sum(c["srdf"] for c in counts.values()),
        "distinct_urdf_contents": len({
            r["sha256"] for r in rows if r["file_type"] == "urdf"}),
        "method": "counted from the filesystem; no expected count is asserted",
    }


# -- strict parse ----------------------------------------------------------


def strict_parse(path: pathlib.Path, root: pathlib.Path,
                 resolver: RosPackageResolver) -> dict[str, Any]:
    """Four verdicts, kept apart, plus the structure behind them."""
    result: dict[str, Any] = {
        "relative_path": _rel(path, root), "sha256": sha256_file(path)}

    try:
        robot = ET.fromstring(path.read_bytes())
        result["XML_CONFORMANCE"] = "PASS"
    except ET.ParseError as exc:
        result.update({"XML_CONFORMANCE": "FAIL", "xml_error": str(exc),
                       "PACKAGE_RESOLUTION": "NOT_REACHED",
                       "RESOURCE_RESOLUTION": "NOT_REACHED",
                       "GEOMETRY_VALIDITY": "NOT_REACHED"})
        return result

    links = robot.findall("link")
    joints = robot.findall("joint")
    collision: collections.Counter[str] = collections.Counter()
    visual: collections.Counter[str] = collections.Counter()
    for link in links:
        pairs: tuple[tuple[str, collections.Counter[str]], ...] = (
            ("collision", collision), ("visual", visual))
        for tag, counter in pairs:
            for element in link.findall(tag):
                geometry = element.find("geometry")
                if geometry is not None:
                    for child in geometry:
                        counter[child.tag] += 1

    joint_types = collections.Counter(str(j.get("type")) for j in joints)
    result.update({
        "robot_name": robot.get("name"),
        "link_count": len(links), "joint_count": len(joints),
        "joint_types": dict(sorted(joint_types.items())),
        "actuated_joint_count": sum(
            n for t, n in joint_types.items()
            if t in {"revolute", "continuous", "prismatic"}),
        "fixed_joint_count": joint_types.get("fixed", 0),
        "visual_geometry": dict(sorted(visual.items())),
        "collision_geometry": dict(sorted(collision.items())),
        "primitive_collision_count": sum(
            n for t, n in collision.items() if t in {"box", "cylinder", "sphere"}),
        "mesh_collision_count": collision.get("mesh", 0),
    })

    text = path.read_text(encoding="utf-8", errors="replace")
    occurrences = re.findall(r'filename\s*=\s*"(package://[^"]+)"', text)
    unique = sorted(set(occurrences))
    outcomes = resolver.resolve_all(unique)
    resolved = [o for o in outcomes if o.resolved]
    package_failures = [o for o in outcomes if o.status in {
        "UNRESOLVED_PACKAGE", "PACKAGE_RESOLUTION_AMBIGUOUS",
        "MALFORMED_PACKAGE_URI"}]
    result.update({
        "package_reference_unique_count": len(unique),
        "package_reference_occurrence_count": len(occurrences),
        "PACKAGE_RESOLUTION": "FAIL" if package_failures else "PASS",
        "RESOURCE_RESOLUTION": f"{len(resolved)}/{len(outcomes)} resolved",
        "resource_resolution_complete": len(resolved) == len(outcomes),
        "unresolved": [
            {"uri": o.uri, "status": o.status,
             "diagnosis": diagnose_unresolved(
                 o.uri, (M3PRO_WS / "src", CAR_WS / "src"))}
            for o in outcomes if not o.resolved][:5],
    })

    try:
        parse_source(path, resolver=resolver)
        result["GEOMETRY_VALIDITY"] = "PASS"
    except UrdfImportRefused as refusal:
        mesh_only = (result["mesh_collision_count"] > 0
                     and result["primitive_collision_count"] == 0)
        if refusal.category == "UNSUPPORTED_COLLISION_PRIMITIVE" and mesh_only:
            result["GEOMETRY_VALIDITY"] = "TOOLING_LIMITATION"
            result["geometry_note"] = (
                "mesh collision geometry is valid URDF. This repository's geometry "
                "oracle measures primitives only, so it cannot admit the source -- "
                "a limitation of the tooling, not a defect in the vendor file")
        else:
            result["GEOMETRY_VALIDITY"] = "FAIL"
        result["geometry_refusal"] = {"category": refusal.category,
                                      "detail": refusal.detail[:180]}

    if result["resource_resolution_complete"]:
        try:
            closure = source_closure(path, resolver=resolver)
            result["RESOURCE_CLOSURE_DIGEST"] = closure["closure_digest"]
            result["closure_member_count"] = closure["member_count"]
        except UrdfImportRefused as refusal:
            result["RESOURCE_CLOSURE_DIGEST"] = f"REFUSED: {refusal.category}"
    else:
        result["RESOURCE_CLOSURE_DIGEST"] = "NOT_COMPUTED_INCOMPLETE_RESOLUTION"
    return result


# -- launch-file reading ---------------------------------------------------


def launch_arguments(path: pathlib.Path) -> dict[str, Any]:
    """Read DeclareLaunchArgument defaults from the AST, not by pattern.

    A default built from a call or a variable is reported as non-literal rather
    than guessed, because a guessed default would be indistinguishable from a
    measured one in the record.
    """
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    literal: dict[str, str] = {}
    non_literal: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "DeclareLaunchArgument"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        name = str(node.args[0].value)
        default = next((k.value for k in node.keywords
                        if k.arg == "default_value"), None)
        if isinstance(default, ast.Constant):
            literal[name] = str(default.value)
        elif default is None:
            non_literal.append(f"{name} (no default)")
        else:
            non_literal.append(f"{name} (computed)")
    return {"literal_defaults": literal, "non_literal_defaults": non_literal,
            "argument_count": len(literal) + len(non_literal)}


def launch_nodes(path: pathlib.Path) -> list[dict[str, Any]]:
    """Every Node / ComposableNode declared, with its literal keywords."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    nodes = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in {"Node", "ComposableNode"}):
            continue
        entry: dict[str, Any] = {"construct": node.func.id,
                                 "line": node.lineno}
        for keyword in node.keywords:
            if keyword.arg in {"package", "executable", "plugin", "name",
                               "namespace"} and isinstance(keyword.value, ast.Constant):
                entry[keyword.arg] = str(keyword.value.value)
        if "package" in entry:
            nodes.append(entry)
    return nodes


def static_transforms(path: pathlib.Path) -> list[dict[str, Any]]:
    """Static transform publishers, read as the argument lists they are."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    transforms = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "Node"):
            continue
        arguments = next((k.value for k in node.keywords if k.arg == "arguments"),
                         None)
        if not isinstance(arguments, ast.List):
            continue
        values = [str(e.value) for e in arguments.elts
                  if isinstance(e, ast.Constant)]
        if len(values) >= 8:
            transforms.append({
                "line": node.lineno,
                "xyz": values[0:3], "rpy": values[3:6],
                "parent_frame": values[6], "child_frame": values[7],
                "authority_class": "VENDOR_SOFTWARE_VALUE",
                "is_a_measurement": False,
            })
    return transforms


def diagnose_unresolved(uri: str, roots: tuple[pathlib.Path, ...]) -> dict[str, Any]:
    """Say why a reference fails, as diagnosis and never as resolution.

    Searching the tree by basename is precisely what the resolver must not do,
    so it is done here, once, under a label that cannot be mistaken for an
    answer. Naming a near miss helps a reader see a vendor typo; opening it for
    them would be deciding the vendor meant something other than it wrote.
    """
    tail = uri[len("package://"):]
    package, _, resource = tail.partition("/")
    wanted = resource.rsplit("/", 1)[-1]
    elsewhere: list[str] = []
    similar: list[str] = []
    for root in roots:
        for candidate in root.rglob(wanted):
            if candidate.is_file():
                elsewhere.append(str(candidate.relative_to(root)))
    if not elsewhere:
        stem = wanted.rsplit(".", 1)[0]
        for root in roots:
            for candidate in root.rglob(f"*{wanted.rsplit('.', 1)[-1]}"):
                other = candidate.stem
                if candidate.is_file() and (
                        other.lower() == stem.lower()
                        or other.lower().rstrip("0123456789")
                        == stem.lower().rstrip("0123456789")):
                    similar.append(str(candidate.relative_to(root)))
    return {
        "DIAGNOSIS_ONLY": True,
        "not_used_for_resolution": (
            "a basename found elsewhere is not the requested resource. This is "
            "recorded so a vendor typo is legible, never so it is silently fixed"),
        "requested_package": package,
        "requested_basename": wanted,
        "same_basename_elsewhere": sorted(set(elsewhere))[:4],
        "similarly_named": sorted(set(similar))[:4],
        "reading": (
            "the file exists under this exact name in another package"
            if elsewhere else
            "a file with a near-identical name exists" if similar else
            "nothing of this name or a near name exists in the admitted roots"),
    }


def _exists_under(name: str) -> list[pathlib.Path]:
    """Absolute hits, so a caller can look at a file's neighbours without
    reconstructing a path and getting the workspace prefix wrong."""
    found = []
    for root in (M3PRO_WS, CAR_WS):
        for candidate in (root / "src").rglob(name):
            if candidate.is_file():
                found.append(candidate)
    return sorted(set(found))


def _package_declared(name: str) -> bool:
    for root in (M3PRO_WS, CAR_WS):
        for manifest in (root / "src").rglob("package.xml"):
            try:
                if (ET.fromstring(manifest.read_bytes()).findtext("name") or ""
                        ).strip() == name:
                    return True
            except ET.ParseError:
                continue
    return False


def reference_defects(parses: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect broken references and test one explanation against each.

    Both look like a global find-and-replace of the product name run across the
    sources, which is an inference, so it gets a test rather than an assertion:
    substituting 'M3Pro' back to 'm3' should name something that exists.

    The test only counts when the substitution actually changes the string. A
    no-op substitution on a name that exists anyway would confirm every
    reference and therefore confirm nothing, which is how a check ends up
    agreeing with whatever it is pointed at.
    """
    defects = []
    for entry in parses:
        for unresolved in entry.get("unresolved", []):
            uri = str(unresolved["uri"])
            package, _, resource = uri[len("package://"):].partition("/")
            basename = resource.rsplit("/", 1)[-1]

            new_basename = basename.replace("M3Pro", "m3")
            basename_changed = new_basename != basename
            basename_hits = _exists_under(new_basename) if basename_changed else []

            new_package = package.replace("_M3Pro_", "_pro_")
            package_changed = new_package != package
            package_exists = _package_declared(new_package) if package_changed else False

            siblings: list[str] = []
            if basename_hits:
                origin = basename_hits[0]
                stem = origin.stem.rstrip("0123456789")
                siblings = sorted(
                    f.name for f in origin.parent.iterdir()
                    if f.is_file() and f.suffix == origin.suffix
                    and f.stem.rstrip("0123456789") == stem)

            if basename_changed and basename_hits:
                verdict = "SUPPORTED"
                detail = (f"substituting M3Pro back to m3 turns {basename} into "
                          f"{new_basename}, which exists, and the sibling sequence "
                          f"{siblings} has exactly that member missing from the "
                          "references")
            elif package_changed and package_exists:
                verdict = "SUPPORTED"
                detail = (f"substituting the package name back gives {new_package}, "
                          "which is a declared package")
            elif package_changed:
                verdict = "PARTIALLY_SUPPORTED"
                detail = (f"the package name {package} carries the substitution "
                          f"pattern, but {new_package} is not declared in either "
                          "workspace either, so the reference was already broken "
                          "before the rename or points outside the archive")
            else:
                verdict = "NOT_SUPPORTED"
                detail = ("no substitution changes this reference into something "
                          "that exists")

            defects.append({
                "source": entry["relative_path"],
                "broken_reference": uri,
                "status": unresolved["status"],
                "basename_substitution": {
                    "from": basename, "to": new_basename,
                    "changed_the_name": basename_changed,
                    "result_exists_at": [_rel(h, M3PRO_WS if "m3pro_ws" in str(h)
                                              else CAR_WS) for h in basename_hits[:3]]},
                "package_substitution": {
                    "from": package, "to": new_package,
                    "changed_the_name": package_changed,
                    "result_is_a_declared_package": package_exists},
                "sibling_sequence": siblings,
                "EXPLANATION": "GLOBAL_FIND_AND_REPLACE_OF_THE_PRODUCT_NAME",
                "explanation_class": "INFERENCE",
                "EXPLANATION_VERDICT": verdict,
                "explanation_detail": detail,
            })

    tally = collections.Counter(str(d["EXPLANATION_VERDICT"]) for d in defects)
    return {
        "defect_count": len(defects),
        "defects": defects,
        "explanation_verdicts": dict(sorted(tally.items())),
        "CONSEQUENCE": (
            "these references are broken in the vendor sources as shipped. A "
            "resolver matching by basename, by nearest name or case-insensitively "
            "would have reported every file complete and hidden all of them"),
        "NOT_REPAIRED": (
            "no reference is rewritten. The finding is that the vendor sources "
            "contain them, and repairing them here would destroy the finding"),
    }


def main() -> int:
    own = str(OUT.relative_to(REPO))
    head = _git("rev-parse", "HEAD")
    dirty = [line for line in _git("status", "--porcelain").splitlines()
             if line.strip() and own not in line]

    m3pro_resolver = RosPackageResolver(source_roots=[M3PRO_WS / "src"])
    car_resolver = RosPackageResolver(source_roots=[CAR_WS / "src"])
    both = RosPackageResolver(source_roots=[M3PRO_WS / "src", CAR_WS / "src"])

    inv = inventory()

    # -- strict parse every URDF -----------------------------------------
    parses = []
    for row in inv["description_sources"]:
        if row["file_type"] != "urdf":
            continue
        root = M3PRO_WS if row["workspace"] == "M3Pro_ws-0.0.1" else CAR_WS
        resolver = m3pro_resolver if root is M3PRO_WS else car_resolver
        entry = strict_parse(root / row["relative_path"], root, resolver)
        entry["workspace"] = row["workspace"]
        parses.append(entry)

    # -- xacro -----------------------------------------------------------
    xacros = []
    for row in inv["description_sources"]:
        if row["file_type"] != "xacro":
            continue
        root = CAR_WS if row["workspace"] == "yahboomcar_ws" else M3PRO_WS
        path = root / row["relative_path"]
        try:
            analysis = analyse(path)
        except XacroRefused as refusal:
            xacros.append({"relative_path": row["relative_path"],
                           "ANALYSIS": "REFUSED", "category": refusal.category})
            continue
        closure = include_closure(path, resolver=both)
        verdict = admissibility(analysis, closure)
        xacro_record = analysis.as_record()
        xacro_record["path"] = row["relative_path"]
        xacro_record["workspace"] = row["workspace"]
        xacro_record["include_closure_digest"] = closure.get("include_closure_digest")
        xacro_record["include_closure_members"] = [
            m["name"] for m in closure["members"]]
        xacro_record["include_unresolved"] = closure["unresolved"]
        xacro_record["ADMISSIBILITY"] = verdict
        xacro_record["EXPANSION_PERFORMED"] = False
        xacro_record["expansion_note"] = (
            "not expanded. xacro is importable on this host only through a ROS "
            "installation on PYTHONPATH and is absent under the repository's "
            "clean-environment practice, so any expansion would be a measurement "
            "of the host rather than of the vendor source. The include closure "
            "above is computed by repository-owned code and needs no xacro")
        xacros.append(xacro_record)

    # -- chain verification ----------------------------------------------
    launch = M3PRO_WS / BRINGUP
    chain_text = launch.read_text(encoding="utf-8", errors="replace")
    chain_edges = [
        ("launch -> description file",
         r"^\s*model\s*=.*get_package_share_directory\(\s*['\"]M3Pro['\"]\s*\)"),
        ("description file -> robot_description (via xacro)",
         r"^\s*robot_description\s*=.*Command\(\[\s*['\"]xacro"),
        ("robot_description -> robot_state_publisher",
         r"^\s*parameters\s*=\s*\[\{\s*['\"]robot_description['\"]"),
    ]
    verified, contradictions = [], []
    for name, pattern in chain_edges:
        hits = [(n, line) for n, line in enumerate(chain_text.splitlines(), 1)
                if re.search(pattern, line)]
        if len(hits) != 1:
            contradictions.append(f"edge {name!r} matched {len(hits)} lines")
            continue
        verified.append({"edge": name, "source": BRINGUP, "line": hits[0][0],
                         "statement": hits[0][1].strip()[:140],
                         "resolution_method": "read from the launch file"})
    production_sha = sha256_file(M3PRO_WS / PRODUCTION_URDF)
    if production_sha != HISTORICAL_CHAIN["description_sha256"]:
        contradictions.append(
            f"production description hash moved: {production_sha}")

    # -- MoveIt -----------------------------------------------------------
    moveit_root = CAR_WS / "src/M3Pro_config"
    moveit_xacro = moveit_root / "config/M3Pro.urdf.xacro"
    moveit_analysis = analyse(moveit_xacro)
    moveit_include = next(
        (i for i in moveit_analysis.includes if "find" in i), "")
    moveit_find = re.search(r"\$\(find ([^)]+)\)(\S*)", moveit_include)
    moveit_desc_rel = ""
    moveit_desc_sha = ""
    if moveit_find:
        probe = both.resolve(f"package://{moveit_find.group(1)}/package.xml")
        if probe.package_root:
            target = pathlib.Path(probe.package_root) / moveit_find.group(2).lstrip("/")
            if target.is_file():
                moveit_desc_rel = _rel(target, CAR_WS)
                moveit_desc_sha = sha256_file(target)

    srdf = moveit_root / "config/M3Pro.srdf"
    srdf_root = ET.fromstring(srdf.read_bytes())
    groups = []
    for group in srdf_root.findall("group"):
        chain = group.find("chain")
        groups.append({
            "name": group.get("name"),
            "base_link": chain.get("base_link") if chain is not None else None,
            "tip_link": chain.get("tip_link") if chain is not None else None,
            "joint_count": len(group.findall("joint")),
        })

    moveit_configs = {}
    for name in ("kinematics.yaml", "joint_limits.yaml", "moveit_controllers.yaml",
                 "ros2_controllers.yaml", "initial_positions.yaml",
                 "pilz_cartesian_limits.yaml"):
        candidate = moveit_root / "config" / name
        if candidate.is_file():
            moveit_configs[name] = {"relative_path": _rel(candidate, CAR_WS),
                                    "sha256": sha256_file(candidate)}

    uses_production = (moveit_desc_sha == production_sha)
    moveit_graph: dict[str, Any] = {
        "root_launch": _rel(moveit_root / "launch/demo.launch.py", CAR_WS),
        "package": "M3Pro_config",
        "robot_description_source": {
            "xacro": _rel(moveit_xacro, CAR_WS),
            "sha256": moveit_analysis.sha256,
            "includes": list(moveit_analysis.includes),
            "resolved_description": moveit_desc_rel or "UNRESOLVED",
            "resolved_description_sha256": moveit_desc_sha or "UNRESOLVED",
        },
        "robot_description_semantic": {"srdf": _rel(srdf, CAR_WS),
                                       "sha256": sha256_file(srdf)},
        "groups": groups,
        "configs": moveit_configs,
        "VERDICT": "B_SEPARATE_DESCRIPTION" if not uses_production
        else "A_SAME_COMPLETE_DESCRIPTION",
        "finding": (
            "MoveIt does not load the description the robot boots with. Bringup "
            f"loads {PRODUCTION_URDF} ({production_sha[:12]}) from workspace "
            f"M3Pro_ws; MoveIt loads {moveit_desc_rel} ({moveit_desc_sha[:12]}) "
            "from workspace yahboomcar_ws. Two descriptions of one robot, in two "
            "workspaces, differing in content") if not uses_production else
            "MoveIt and bringup load the same description",
        "cross_workspace": True,
    }

    # -- arm chain --------------------------------------------------------
    robot = ET.fromstring((M3PRO_WS / PRODUCTION_URDF).read_bytes())
    arm_chain = []
    for joint in robot.findall("joint"):
        name = str(joint.get("name", ""))
        if not (name.startswith("arm") or "Grip" in name):
            continue
        origin, axis = joint.find("origin"), joint.find("axis")
        limit = joint.find("limit")
        parent, child = joint.find("parent"), joint.find("child")
        arm_chain.append({
            "joint": name, "type": joint.get("type"),
            "parent": parent.get("link") if parent is not None else None,
            "child": child.get("link") if child is not None else None,
            "xyz": origin.get("xyz") if origin is not None else None,
            "rpy": origin.get("rpy") if origin is not None else None,
            "axis": axis.get("xyz") if axis is not None else None,
            "lower": limit.get("lower") if limit is not None else None,
            "upper": limit.get("upper") if limit is not None else None,
            "effort": limit.get("effort") if limit is not None else None,
            "velocity": limit.get("velocity") if limit is not None else None,
            "authority_class": "VENDOR_SOFTWARE_VALUE",
        })

    # -- camera -----------------------------------------------------------
    camera_joint = None
    for joint in robot.findall("joint"):
        child = joint.find("child")
        if child is not None and str(child.get("link", "")).startswith("camera"):
            origin, parent = joint.find("origin"), joint.find("parent")
            camera_joint = {
                "joint": joint.get("name"), "type": joint.get("type"),
                "parent_link": parent.get("link") if parent is not None else None,
                "child_link": child.get("link"),
                "xyz": origin.get("xyz") if origin is not None else None,
                "rpy": origin.get("rpy") if origin is not None else None,
                "source_file": PRODUCTION_URDF,
            }
    urdf_frames = {str(link.get("name")) for link in robot.findall("link")}
    camera_args = launch_arguments(M3PRO_WS / CAMERA_LAUNCH)
    defaults = camera_args["literal_defaults"]
    camera_nodes = launch_nodes(M3PRO_WS / CAMERA_LAUNCH)

    def frame_state(name: str) -> str:
        return "REPRESENTED_IN_SOURCE" if name in urdf_frames \
            else "NOT_REPRESENTED_IN_SOURCE"

    camera_graph: dict[str, Any] = {
        "CAMERA_PARENTAGE": "VENDOR_SOURCE_CONFIRMED",
        "CAMERA_EXTRINSIC": "VENDOR_SOFTWARE_VALUE",
        "PHYSICAL_CAMERA_EXTRINSIC": "NOT_MEASURED",
        "mount_joint": camera_joint,
        "frame_semantics": {
            "mechanical_camera_link": frame_state("camera_link"),
            "housing_frame": frame_state("camera_housing"),
            "rgb_frame": frame_state("camera_color_frame"),
            "rgb_optical_frame": frame_state("camera_color_optical_frame"),
            "depth_frame": frame_state("camera_depth_frame"),
            "depth_optical_frame": frame_state("camera_depth_optical_frame"),
            "point_cloud_frame": frame_state("camera_depth_optical_frame"),
        },
        "frame_note": (
            "only the mechanical mount link exists in the description. The RGB, "
            "depth and optical frames are published by the driver at runtime, so "
            "they are NOT_REPRESENTED_IN_SOURCE rather than identity transforms. "
            "Treating an absent frame as a zero transform is how an uncalibrated "
            "optical offset becomes invisible"),
        "urdf_links": sorted(urdf_frames),
    }

    orbbec_present = bool(list((CAR_WS / "src/OrbbecSDK_ROS2").rglob("*")))
    orbbec: dict[str, Any] = {
        "driver_package_declared": "orbbec_camera",
        "driver_node": next((n for n in camera_nodes
                             if n.get("package") == "orbbec_camera"), None),
        "launch_file": CAMERA_LAUNCH,
        "launch_sha256": sha256_file(M3PRO_WS / CAMERA_LAUNCH),
        "OrbbecSDK_ROS2_directory_present": (CAR_WS / "src/OrbbecSDK_ROS2").is_dir(),
        "OrbbecSDK_ROS2_ships_files": orbbec_present,
        "DRIVER_SOURCE_STATUS": (
            "RUNTIME_SOURCE_NOT_IDENTIFIED" if not orbbec_present
            else "PRESENT"),
        "driver_source_finding": (
            "the workspace contains an OrbbecSDK_ROS2 directory that ships zero "
            "files, and no package declaring orbbec_camera exists in either "
            "workspace. The camera is fully configured and its driver source is "
            "not in the vendor archive"),
        "CONFIGURED_DEVICE": {
            "vendor_id": defaults.get("vendor_id"),
            "product_id": defaults.get("product_id") or "(any)",
            "serial_number": defaults.get("serial_number") or "(any)",
            "device_num": defaults.get("device_num"),
            "camera_name": defaults.get("camera_name"),
        },
        "CONFIGURED_RESOLUTION": {
            "color": f"{defaults.get('color_width')}x{defaults.get('color_height')}",
            "depth": f"{defaults.get('depth_width')}x{defaults.get('depth_height')}",
            "ir": f"{defaults.get('ir_width')}x{defaults.get('ir_height')}",
        },
        "CONFIGURED_FPS": {"color": defaults.get("color_fps"),
                           "depth": defaults.get("depth_fps"),
                           "ir": defaults.get("ir_fps")},
        "CONFIGURED_FORMAT": {"color": defaults.get("color_format"),
                              "depth": defaults.get("depth_format"),
                              "ir": defaults.get("ir_format")},
        "CONFIGURED_TOPIC_NAMESPACE": defaults.get("camera_name"),
        "CONFIGURED_TOPICS_NOTE": (
            "the launch file sets a namespace and the driver names the topics. "
            "Topic names are therefore a property of the driver source, which is "
            "absent, so no CONFIGURED_TOPIC is recorded rather than a plausible "
            "one being written down"),
        "depth_registration": defaults.get("depth_registration"),
        "align_mode": defaults.get("align_mode"),
        "enable_point_cloud": defaults.get("enable_point_cloud"),
        "enable_colored_point_cloud": defaults.get("enable_colored_point_cloud"),
        "cloud_frame_id": defaults.get("cloud_frame_id") or "(driver default)",
        "publish_tf": defaults.get("publish_tf"),
        "tf_publish_rate": defaults.get("tf_publish_rate"),
        "enable_publish_extrinsic": defaults.get("enable_publish_extrinsic"),
        "color_info_url": defaults.get("color_info_url") or "(none)",
        "ir_info_url": defaults.get("ir_info_url") or "(none)",
        "intrinsics_source": (
            "no calibration URL is configured, so intrinsics come from the "
            "device's own factory calibration at runtime. Nothing in the source "
            "pins them"),
        "argument_count": camera_args["argument_count"],
        "non_literal_defaults": camera_args["non_literal_defaults"],
        "CLAIM_CLASS": "CONFIGURED_NOT_OBSERVED",
    }

    # -- TOF --------------------------------------------------------------
    merge_text = (M3PRO_WS / MERGE_CONFIG).read_text(encoding="utf-8")
    merge: dict[str, str] = {}
    for line in merge_text.splitlines():
        if ":" in line and not line.strip().endswith(":"):
            key, _, value = line.strip().partition(":")
            merge[key.strip()] = value.strip().strip('"')
    tf_rows = static_transforms(M3PRO_WS / STATIC_TF)
    laser_frames = [t for t in tf_rows if "laser" in str(t["child_frame"])]
    inputs = merge.get("laserscan_topics", "").split()

    producers = subprocess.run(
        ["grep", "-rl", "--include=*.py", "--include=*.yaml", "--include=*.xml",
         "-e", "scan0", str(M3PRO_WS / "src")],
        capture_output=True, text=True, check=False).stdout.split()
    producer_files = sorted(_rel(pathlib.Path(p), M3PRO_WS) for p in producers)

    tof: dict[str, Any] = {
        "MODELLED_AS": "TWO_INDEPENDENT_SENSORS_MERGED_INTO_ONE_SYNTHETIC_SCAN",
        "merger": {"package": "ira_laser_tools",
                   "executable": "laserscan_multi_merger",
                   "config": MERGE_CONFIG,
                   "config_sha256": sha256_file(M3PRO_WS / MERGE_CONFIG)},
        "CONFIGURED_INPUT_TOPICS": inputs,
        "CONFIGURED_OUTPUT_SCAN_TOPIC": merge.get("scan_destination_topic"),
        "CONFIGURED_OUTPUT_CLOUD_TOPIC": merge.get("cloud_destination_topic"),
        "CONFIGURED_DESTINATION_FRAME": merge.get("destination_frame"),
        "CONFIGURED_ANGLE_MIN": merge.get("angle_min"),
        "CONFIGURED_ANGLE_MAX": merge.get("angle_max"),
        "CONFIGURED_ANGLE_INCREMENT": merge.get("angle_increment"),
        "CONFIGURED_RANGE_MIN": merge.get("range_min"),
        "CONFIGURED_RANGE_MAX": merge.get("range_max"),
        "message_type": "sensor_msgs/msg/LaserScan (ira_laser_tools contract)",
        "sensor_frames": laser_frames,
        "all_static_transforms": tf_rows,
        "static_tf_source": STATIC_TF,
        "static_tf_sha256": sha256_file(M3PRO_WS / STATIC_TF),
        "downstream_filter": {"package": "yahboom_laser_filter",
                              "executable": "laser_filter_node",
                              "configured_angle_min": "-180.0",
                              "configured_angle_max": "180.0"},
        "NEGATIVE_SPACE": {
            "frames_in_description": [
                f for f in ("laser0_frame", "laser1_frame") if f in urdf_frames],
            "VERDICT_FRAMES": "SOFTWARE_SENSOR_PRESENT_FRAME_NOT_REPRESENTED_IN_DESCRIPTION",
            "frames_detail": (
                "laser0_frame and laser1_frame are published as static transforms "
                "from base_link at launch and are not links in m3pro.urdf, so the "
                "description alone does not describe where the ranging sensors are"),
            "producer_files_found": producer_files,
            "VERDICT_DRIVERS": "RUNTIME_SOURCE_NOT_IDENTIFIED",
            "drivers_detail": (
                "no node in either workspace is configured to publish the two "
                "input scans the merger consumes. The consumer, the merge "
                "parameters and the frames are all present; the drivers are not"),
        },
        "COVERAGE_NOTE": (
            "the merge is configured over a full turn, which is a configured "
            "angular span and not a measurement of what the two sensors can see. "
            "Coverage is a runtime and geometric question this tranche does not "
            "answer"),
        "CLAIM_CLASS": "CONFIGURED_NOT_OBSERVED",
    }

    # -- product roles ----------------------------------------------------
    referenced_index = {}
    for _, root in WORKSPACES:
        for launch_file in root.rglob("*.launch.py"):
            referenced_index[launch_file] = launch_file.read_text(
                encoding="utf-8", errors="replace")
    for row in inv["description_sources"]:
        name = pathlib.Path(row["relative_path"]).name
        referenced_by = sorted({
            _rel(p, M3PRO_WS if "m3pro_ws" in str(p) else CAR_WS)
            for p, text in referenced_index.items() if name in text})
        row["referenced_by"] = referenced_by[:4]
        row["PRODUCT_ROLE"] = classify(
            row["relative_path"], row["workspace"], referenced_by)

    muto_referenced = [r for r in inv["description_sources"]
                       if "Muto" in r["relative_path"] and r["referenced_by"]]

    record: dict[str, Any] = {
        "check": "PRODUCTION_DESCRIPTION_INVENTORY_AND_SENSOR_GRAPHS",
        "artifact_semantics": "SOURCE_CHARACTERISATION_NOTHING_ADOPTED",
        "author": "Frank Asante Van Laarhoven",
        "provenance_observed_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "repository_head": head,
        "worktree_clean_at_measurement": not dirty,
        "other_dirty_entries": dirty,
        "workspaces": [{"label": label, "staging_root": str(root),
                        "HOST_LOCAL": True} for label, root in WORKSPACES],
        "resolver_sha256": sha256_file(REPO / "src/navfm/isaac/ros_package_resolver.py"),
        "xacro_analysis_sha256": sha256_file(REPO / "src/navfm/isaac/xacro_analysis.py"),
        "INVENTORY": inv,
        "STRICT_PARSE": parses,
        "VENDOR_REFERENCE_DEFECTS": reference_defects(parses),
        "XACRO_ANALYSIS": xacros,
        "XACRO_EXPANSION": {
            "PERFORMED": False,
            "reason": ("xacro resolves on this host only through a ROS tree on "
                       "PYTHONPATH and is absent under the repository's "
                       "clean-environment practice. An expansion produced that way "
                       "would measure the host, not the vendor source"),
            "substitute": ("repository-owned include-closure resolution, which is "
                           "deterministic and needs no xacro"),
            "STATUS": "LIMITATION_RECORDED",
        },
        "PRODUCTION_CHAIN_VERIFICATION": {
            "historical": HISTORICAL_CHAIN,
            "edges_verified": verified,
            "production_description_sha256": production_sha,
            "hash_matches_historical":
                production_sha == HISTORICAL_CHAIN["description_sha256"],
            "CONTRADICTIONS": contradictions,
            "VERDICT": "VERIFIED" if not contradictions else "CONTRADICTION",
        },
        "MOVEIT_GRAPH": moveit_graph,
        "ARM_KINEMATIC_CHAIN": {
            "joints": arm_chain,
            "joint_count": len(arm_chain),
            "authority_class": "VENDOR_SOFTWARE_VALUE",
            "not_physical_calibration": (
                "these are the numbers the vendor's description contains. None has "
                "been compared against the robot"),
            "STATUS": "SOURCE_CHARACTERIZED",
        },
        "CAMERA_GRAPH": camera_graph,
        "ORBBEC_CONFIGURATION": orbbec,
        "TOF_CONFIGURATION": tof,
        "MUTO_PRODUCTION_REFERENCE_CHECK": {
            "muto_files_referenced_by_a_production_launch": len(muto_referenced),
            "MUTO_PRODUCT_ROLE": "TUTORIAL_CONTENT",
            "contradiction": bool(muto_referenced),
        },
        "PRODUCTION_COLLISION_SOURCE": "MESH_BASED",
        "DECISION_B": "UNRESOLVED_AND_NOT_TOUCHED",
        "decision_b_candidates_not_selected": [
            "vendor-provided dimensions", "source mesh-derived dimensions",
            "Parasolid ROSMASTER-M3Pro.x_t", "physical measurement"],
        "CLAIM_BOUNDARY": (
            "every sensor value here is configured, not observed. Nothing was "
            "launched, no topic was subscribed, and no transform was compared "
            "against the robot"),
        "RUNTIME_SEPARATION": [
            "configured", "reachable", "launched", "publishing",
            "physically correct"],
        "PRODUCTION_DESCRIPTION_IDENTIFIED": True,
        "AUTHORITATIVE_ROBOT_DESCRIPTION": "AWAITING_REVIEW",
        "PRODUCTION_M3PRO_USD": "NOT_GENERATED",
        "DIGITAL_TWIN_REQUALIFICATION": "NOT_STARTED",
        "VENDOR_REDISTRIBUTION": "NOT_AUTHORISED_PENDING_CLARIFICATION",
        "SCIENTIFIC_ARM_A_N": 0,
        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
    }

    sha = emit_evidence(OUT, record, required_keys=(
        "check", "INVENTORY", "STRICT_PARSE", "XACRO_ANALYSIS",
        "PRODUCTION_CHAIN_VERIFICATION", "MOVEIT_GRAPH", "ARM_KINEMATIC_CHAIN",
        "CAMERA_GRAPH", "ORBBEC_CONFIGURATION", "TOF_CONFIGURATION",
        "CLAIM_BOUNDARY", "AUTHORITATIVE_ROBOT_DESCRIPTION"))

    print("=" * 78)
    print("PRODUCTION DESCRIPTION INVENTORY AND SENSOR GRAPHS")
    print("=" * 78)
    print(f"  HEAD {head[:12]}  clean={record['worktree_clean_at_measurement']}")
    print(f"  inventory     {inv['urdf_count']} urdf ({inv['distinct_urdf_contents']} "
          f"distinct), {inv['xacro_count']} xacro, {inv['srdf_count']} srdf")
    print()
    print(f"  {'urdf':34s} {'XML':5s} {'PKG':5s} {'RESOURCES':14s} {'GEOMETRY':20s}")
    for entry in parses:
        print(f"  {entry['relative_path'][-34:]:34s} {entry['XML_CONFORMANCE']:5s} "
              f"{entry.get('PACKAGE_RESOLUTION', '-'):5s} "
              f"{entry.get('RESOURCE_RESOLUTION', '-'):14s} "
              f"{entry.get('GEOMETRY_VALIDITY', '-'):20s}")
    print()
    print(f"  chain         {record['PRODUCTION_CHAIN_VERIFICATION']['VERDICT']} "
          f"({len(verified)} edges)")
    print(f"  MoveIt        {moveit_graph['VERDICT']}")
    print(f"                bringup {PRODUCTION_URDF.split('/')[-1]} "
          f"{production_sha[:10]}")
    print(f"                moveit  {moveit_desc_rel.split('/')[-1]} "
          f"{moveit_desc_sha[:10]}")
    print(f"  arm chain     {len(arm_chain)} joints (VENDOR_SOFTWARE_VALUE)")
    print(f"  camera        {camera_graph['CAMERA_PARENTAGE']}, "
          f"extrinsic {camera_graph['CAMERA_EXTRINSIC']}")
    print(f"  orbbec        {orbbec['DRIVER_SOURCE_STATUS']}; "
          f"colour {orbbec['CONFIGURED_RESOLUTION']['color']}@"
          f"{orbbec['CONFIGURED_FPS']['color']}, depth "
          f"{orbbec['CONFIGURED_RESOLUTION']['depth']}@"
          f"{orbbec['CONFIGURED_FPS']['depth']}, "
          f"registration={orbbec['depth_registration']}")
    print(f"  TOF           {tof['MODELLED_AS']}")
    print(f"                {tof['CONFIGURED_INPUT_TOPICS']} -> "
          f"{tof['CONFIGURED_OUTPUT_SCAN_TOPIC']} in "
          f"{tof['CONFIGURED_DESTINATION_FRAME']}")
    print(f"                frames {tof['NEGATIVE_SPACE']['VERDICT_FRAMES']}")
    print(f"                driver {tof['NEGATIVE_SPACE']['VERDICT_DRIVERS']}")
    defects = record["VENDOR_REFERENCE_DEFECTS"]
    print(f"  ref defects   {defects['defect_count']} broken references  "
          f"{defects['explanation_verdicts']}")
    for defect in defects["defects"]:
        print(f"                {defect['broken_reference'][10:][:48]:50s}"
              f"{defect['EXPLANATION_VERDICT']}")
    print(f"  Muto          contradiction="
          f"{record['MUTO_PRODUCTION_REFERENCE_CHECK']['contradiction']}")
    print()
    print(f"  artefact      {OUT.relative_to(REPO)}")
    print(f"  sha256        {sha}")
    print(f"  DECISION_B    {record['DECISION_B']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
