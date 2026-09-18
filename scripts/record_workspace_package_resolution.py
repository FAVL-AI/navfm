"""Re-evaluate the Muto descriptions under an explicit package-resolution contract.

All three were refused ``UNRESOLVED_DEPENDENCY``. That category was doing two
jobs at once -- the resource is absent, and the parser has no model of ROS
package resolution -- and the vendor trace showed it was always the second.
This record separates the two by measuring four things independently:

    XML validity  !=  package resolution  !=  resource existence  !=  geometry validity

so a file can now pass one and fail the next without either verdict being
inferred from the other. That is the whole point of the exercise: the old
result collapsed four questions into one refusal.

Resolution roots are supplied explicitly and nothing else is consulted. The
historical results are referenced, never rewritten. And a Muto file resolving
cleanly does not make it production apparatus: that was settled by the launch
graph, and parsing successfully is not evidence about product role.
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
from navfm.isaac.ros_package_resolver import (  # noqa: E402
    RESOLUTION_CLASSES,
    RosPackageResolver,
)
from navfm.isaac.urdf_import import (  # noqa: E402
    UrdfImportRefused,
    parse_source,
    source_closure,
)

OUT = REPO / "gates/digital_twin/workspace_package_resolution_20260918.json"
RESOLVER_SRC = REPO / "src/navfm/isaac/ros_package_resolver.py"
STAGING = pathlib.Path("/home/favl/Downloads/yahboom/extracted")
ROS2_WS = STAGING / "ros2_ws_0c3e33aa" / "ros2_ws"
M3PRO_WS = STAGING / "M3Pro_ws-0.0.1_f08db69b" / "m3pro_ws"

MUTO = ("Muto.urdf", "Muto_robot1.urdf", "Muto_robot2.urdf")
MUTO_DIR = "src/yahboomcar_description/urdf"

#: What the previous tranche recorded, bound by hash so this record cannot
#: silently disagree with a document it claims to supersede in scope only.
HISTORICAL = {
    "artefact": "gates/digital_twin/vendor_source_closure_20260918.json",
    "observation": ("all three Muto descriptions are refused UNRESOLVED_DEPENDENCY "
                    "for their package:// mesh references"),
    "verdict": "B_TUTORIAL_OR_EXAMPLE_CONTENT",
    "status": "UNCHANGED_AND_NOT_REWRITTEN",
}


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def measure_references(path: pathlib.Path) -> dict[str, Any]:
    """Count references by measuring, not by carrying an expected number forward."""
    text = path.read_text(encoding="utf-8", errors="replace")
    occurrences = re.findall(r'filename\s*=\s*"(package://[^"]+)"', text)
    unique = sorted(set(occurrences))
    by_package = collections.Counter(
        ref[len("package://"):].split("/", 1)[0] for ref in unique)
    return {
        "occurrence_count": len(occurrences),
        "unique_count": len(unique),
        "unique_references": unique,
        "packages_referenced": dict(sorted(by_package.items())),
        "method": "counted from the file; no expected value is asserted",
    }


def diagnose_absence(resolver: RosPackageResolver, uri: str) -> dict[str, Any]:
    """Say WHY a resource is absent, without letting the answer resolve it.

    A case-only mismatch and a genuinely missing file are different facts about
    the vendor material, and a resolver that quietly accepted either would have
    reported both as present. The diagnosis is recorded separately from the
    resolution and never feeds back into it: telling the user their file differs
    only in case is help, silently opening it is not.
    """
    outcome = resolver.resolve(uri)
    if outcome.package_root is None or outcome.requested_resource is None:
        return {"diagnosis": "NOT_APPLICABLE"}
    root = pathlib.Path(outcome.package_root)
    wanted = pathlib.PurePosixPath(outcome.requested_resource)
    directory = root / wanted.parent
    if not directory.is_dir():
        return {"diagnosis": "CONTAINING_DIRECTORY_ABSENT",
                "directory": str(wanted.parent)}
    siblings = sorted(entry.name for entry in directory.iterdir() if entry.is_file())
    case_matches = [name for name in siblings if name.lower() == wanted.name.lower()]
    if case_matches:
        return {
            "diagnosis": "CASE_ONLY_MISMATCH",
            "referenced": wanted.name,
            "present_in_package": case_matches,
            "consequence": ("this reference resolves on a case-insensitive "
                            "filesystem and fails on Linux, which is what the robot "
                            "runs. It is a defect in the vendor description, not in "
                            "the resolver"),
            "not_resolved_because": ("matching case-insensitively would mean deciding "
                                     "the vendor meant a different file than it wrote"),
        }
    return {
        "diagnosis": "ABSENT_UNDER_ANY_CASING",
        "referenced": wanted.name,
        "sibling_count": len(siblings),
        "nearest_siblings": siblings[:6],
        "not_resolved_because": ("no file of this name exists. A similarly named "
                                 "sibling is not evidence that it is the same asset"),
    }


def evaluate(path: pathlib.Path, resolver: RosPackageResolver) -> dict[str, Any]:
    """Answer the four questions separately, and say which were not reached."""
    result: dict[str, Any] = {
        "file": f"{MUTO_DIR}/{path.name}",
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
    }

    # 1. XML conformance, decided before anything else.
    try:
        root = ET.fromstring(path.read_bytes())
        result["XML_CONFORMANCE"] = "PASS"
        result["robot_name"] = root.get("name")
        result["link_count"] = len(root.findall("link"))
        result["joint_count"] = len(root.findall("joint"))
    except ET.ParseError as exc:
        result["XML_CONFORMANCE"] = "FAIL"
        result["xml_error"] = str(exc)
        result["PACKAGE_RESOLUTION"] = "NOT_REACHED"
        result["RESOURCE_RESOLUTION"] = "NOT_REACHED"
        result["GEOMETRY_VALIDITY"] = "NOT_REACHED"
        result["PRODUCT_ROLE"] = "TUTORIAL_CONTENT"
        return result

    # 2 and 3. Package resolution, then resource existence within it.
    references = measure_references(path)
    result["references"] = references
    outcomes = resolver.resolve_all(references["unique_references"])
    statuses = collections.Counter(o.status for o in outcomes)
    resolved = [o for o in outcomes if o.resolved]

    package_failures = [o for o in outcomes if o.status in {
        "UNRESOLVED_PACKAGE", "PACKAGE_RESOLUTION_AMBIGUOUS",
        "MALFORMED_PACKAGE_URI"}]
    resource_failures = [o for o in outcomes if o.status in {
        "UNRESOLVED_RESOURCE", "RESOURCE_PATH_TRAVERSAL", "SYMLINK_ESCAPE"}]

    result["PACKAGE_RESOLUTION"] = "FAIL" if package_failures else "PASS"
    result["RESOURCE_RESOLUTION"] = (
        f"{len(resolved)}/{len(outcomes)} resolved")
    result["resource_resolution_complete"] = len(resolved) == len(outcomes)
    result["resolution_statuses"] = dict(sorted(statuses.items()))
    result["resolution_classes"] = dict(sorted(collections.Counter(
        o.resolution_class or "NONE" for o in resolved).items()))
    result["failures"] = [
        {"uri": o.uri, "status": o.status, "reason": o.reason,
         **diagnose_absence(resolver, o.uri)}
        for o in (*package_failures, *resource_failures)][:5]

    # 4. Geometry validity, through the unchanged strict parser.
    try:
        model = parse_source(path, resolver=resolver)
        result["GEOMETRY_VALIDITY"] = "PASS"
        result["collision_elements"] = len(model.collisions)
    except UrdfImportRefused as refusal:
        result["GEOMETRY_VALIDITY"] = "FAIL"
        result["geometry_refusal"] = {"category": refusal.category,
                                      "detail": refusal.detail[:200]}

    # Resource closure, only where everything resolved.
    if result["resource_resolution_complete"]:
        try:
            closure = source_closure(path, resolver=resolver)
            result["RESOURCE_CLOSURE_DIGEST"] = closure["closure_digest"]
            result["closure_member_count"] = closure["member_count"]
            result["closure_excludes_host_paths"] = closure["digest_excludes_host_paths"]
        except UrdfImportRefused as refusal:
            result["RESOURCE_CLOSURE_DIGEST"] = f"REFUSED: {refusal.category}"
    else:
        result["RESOURCE_CLOSURE_DIGEST"] = "NOT_COMPUTED_INCOMPLETE_RESOLUTION"

    result["PRODUCT_ROLE"] = "TUTORIAL_CONTENT"
    result["product_role_basis"] = (
        "the launch graph, measured in the previous tranche. Resolution success "
        "is not evidence about product role and does not revise it")
    return result


def negative_controls() -> dict[str, Any]:
    """Run the resolver controls and record the measured outcome."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_ros_package_resolver.py",
         "-p", "no:warnings", "-q", "--tb=no"],
        cwd=REPO, capture_output=True, text=True, check=False,
        env={k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"})
    tail = [line for line in proc.stdout.splitlines() if line.strip()][-1:]
    return {
        "suite": "tests/test_ros_package_resolver.py",
        "exit_code": proc.returncode,
        "VERDICT": "PASS" if proc.returncode == 0 else "FAIL",
        "last_line": tail[0][:120] if tail else "",
        "controls": {
            "NO_GLOBAL_FALLBACK": "a package present on disk but outside the declared "
                                  "roots must return UNRESOLVED_PACKAGE",
            "ENVIRONMENT_INDEPENDENCE": "identical results under ROS_PACKAGE_PATH, "
                                        "AMENT_PREFIX_PATH, CMAKE_PREFIX_PATH, "
                                        "PYTHONPATH, COLCON_PREFIX_PATH pollution "
                                        "and a changed working directory",
            "DUPLICATE_PACKAGE": "two manifests declaring one name in one precedence "
                                 "class refuse, in either root order",
            "MISSING_PACKAGE": "distinct from missing resource",
            "MISSING_RESOURCE": "distinct from missing package",
            "WRONG_PACKAGE_BASENAME": "identical basenames in two packages resolve to "
                                      "their own package",
            "TRAVERSAL": "'..', encoded '..', and extra or encoded separators refused "
                         "before any read",
            "MALFORMED_URI": "structured refusal, never a traceback or a local-path "
                             "interpretation",
            "SYMLINK_ESCAPE": "a link leaving the package root refused unless "
                              "explicitly admitted",
            "MANIFEST_IDENTITY": "a directory named foo is not package foo unless its "
                                 "manifest says so",
            "STRICT_XML_UNCHANGED": "the tracked malformed NavFM URDF stays "
                                    "SOURCE_MALFORMED with and without a resolver",
        },
    }


def main() -> int:
    head = _git("rev-parse", "HEAD")
    own = str(OUT.relative_to(REPO))
    dirty = [line for line in _git("status", "--porcelain").splitlines()
             if line.strip() and own not in line]

    resolver = RosPackageResolver(source_roots=[ROS2_WS / "src"])
    inventory = resolver.inventory(relative_to=ROS2_WS)

    production = RosPackageResolver(source_roots=[M3PRO_WS / "src"])

    muto = [evaluate(ROS2_WS / MUTO_DIR / name, resolver) for name in MUTO]

    record: dict[str, Any] = {
        "check": "WORKSPACE_PACKAGE_RESOLUTION",
        "artifact_semantics": "RESOLVER_CAPABILITY_AND_REEVALUATION_NOTHING_ADOPTED",
        "author": "Frank Asante Van Laarhoven",
        "provenance_observed_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "repository_head": head,
        "worktree_clean_at_measurement": not dirty,
        "worktree_clean_excluding_this_artefact": ("this record's own output path is excluded from the check; everything else must be clean, so evidence is never measured against a tree that differs from the commit it names"),
        "other_dirty_entries": dirty,
        "resolver": {
            "module": str(RESOLVER_SRC.relative_to(REPO)),
            "sha256": sha256_file(RESOLVER_SRC),
            "ROS_PACKAGE_RESOLVER": "WORKSPACE_AWARE_STRICT",
            "RESOLUTION_ROOTS": "EXPLICIT_ONLY",
            "GLOBAL_FALLBACK": "DISABLED",
            "precedence": list(RESOLUTION_CLASSES),
            "precedence_frozen_before_evaluation": True,
            "ambiguity_policy": ("one name declared twice inside a precedence class "
                                 "refuses; no first-hit, alphabetical, mtime or "
                                 "nearest-directory tie-break exists"),
            "identity_source": "package.xml <name>",
            "consulted_environment_variables": [],
        },
        "resolution_roots": {
            "ros2_ws_source": str(ROS2_WS / "src"),
            "install_roots": [],
            "install_note": ("neither vendor workspace ships an ament install tree, "
                             "so install semantics are supported but not manufactured "
                             "here"),
            "HOST_LOCAL": ("these absolute paths record where the measurement ran. "
                           "Portable identity is the archive closure plus the "
                           "package-relative path plus the hash"),
        },
        "package_inventory": inventory,
        "production_workspace_inventory": {
            "root": str(M3PRO_WS / "src"),
            "package_count": len(production.package_names()),
            "packages": list(production.package_names()),
            "ambiguous_package_names": list(production.ambiguous_packages()),
            "note": ("recorded to show the resolver handles the nested production "
                     "layout. No production description is parsed or adopted here"),
        },
        "NEGATIVE_CONTROLS": negative_controls(),
        "HISTORICAL_RESULT": HISTORICAL,
        "MUTO_REEVALUATION": muto,
        "MUTO_REEVALUATION_STATUS": "COMPLETE",
        "MUTO_PRODUCT_ROLE": "TUTORIAL_CONTENT",
        "INTERPRETATION": {
            "separation": ("XML validity, package resolution, resource existence and "
                           "geometry validity are now four measurements rather than "
                           "one refusal"),
            "what_changed": "the resolver's scope, not the vendor files",
            "what_did_not_change": ("the strict XML parser, the geometry rules, the "
                                    "numeric validation, and the requirement that "
                                    "every dependency resolve"),
        },
        "CLAIM_BOUNDARY": (
            "the workspace-aware resolver resolves ROS package:// resources using "
            "explicit vendor workspace roots while strict source validation is "
            "unchanged. Nothing here makes any description authoritative"),
        "NOT_CLAIMED": [
            "Muto is authoritative",
            "Muto is the production M3 Pro description",
            "production apparatus is selected",
        ],
        "PRODUCTION_DESCRIPTION_IDENTIFIED": True,
        "AUTHORITATIVE_ROBOT_DESCRIPTION": "AWAITING_REVIEW",
        "PRODUCTION_M3PRO_USD": "NOT_GENERATED",
        "DECISION_B": "UNRESOLVED_AND_NOT_TOUCHED",
        "SCIENTIFIC_ARM_A_N": 0,
        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
    }

    sha = emit_evidence(OUT, record, required_keys=(
        "check", "resolver", "package_inventory", "NEGATIVE_CONTROLS",
        "HISTORICAL_RESULT", "MUTO_REEVALUATION", "CLAIM_BOUNDARY",
        "AUTHORITATIVE_ROBOT_DESCRIPTION"))

    print("=" * 76)
    print("WORKSPACE-AWARE PACKAGE RESOLUTION")
    print("=" * 76)
    r = record["resolver"]
    print(f"  HEAD          {head[:12]}  clean={record['worktree_clean_at_measurement']}")
    print(f"  resolver      {r['module']}")
    print(f"  sha256        {r['sha256']}")
    print(f"  precedence    {' > '.join(r['precedence'])}  (global fallback DISABLED)")
    print(f"  controls      {record['NEGATIVE_CONTROLS']['VERDICT']}  "
          f"{record['NEGATIVE_CONTROLS']['last_line']}")
    print()
    inv = record["package_inventory"]
    print(f"  ros2_ws       {inv['package_count']} packages, "
          f"{inv['manifest_count']} manifests, "
          f"ambiguous={inv['ambiguous_package_names'] or 'none'}")
    prod = record["production_workspace_inventory"]
    print(f"  m3pro_ws      {prod['package_count']} packages, "
          f"ambiguous={prod['ambiguous_package_names'] or 'none'}")
    print()
    print(f"  {'file':22s} {'XML':6s} {'PKG':6s} {'RESOURCES':12s} {'GEOMETRY':10s} closure")
    for entry in muto:
        print(f"  {entry['file'].split('/')[-1]:22s} "
              f"{entry['XML_CONFORMANCE']:6s} "
              f"{entry.get('PACKAGE_RESOLUTION')!s:6s} "
              f"{entry.get('RESOURCE_RESOLUTION')!s:12s} "
              f"{entry.get('GEOMETRY_VALIDITY')!s:10s} "
              f"{str(entry.get('RESOURCE_CLOSURE_DIGEST'))[:16]}")
        refs = entry.get("references", {})
        print(f"  {'':22s} refs unique={refs.get('unique_count')} "
              f"occurrences={refs.get('occurrence_count')} "
              f"packages={list(refs.get('packages_referenced', {}))}")
        if entry.get("geometry_refusal"):
            print(f"  {'':22s} geometry: {entry['geometry_refusal']['category']}")
    print()
    print(f"  MUTO_PRODUCT_ROLE  {record['MUTO_PRODUCT_ROLE']}  (from the launch graph)")
    print(f"  artefact      {OUT.relative_to(REPO)}")
    print(f"  sha256        {sha}")
    print("  AUTHORITATIVE_ROBOT_DESCRIPTION  AWAITING_REVIEW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
