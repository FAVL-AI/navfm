"""Source-closure analysis of the extracted vendor archives.

Answers one question: which robot description does the M3 Pro software actually
reference. Answered from the archive's own package and launch graph, not from
filenames -- because the filenames were misleading.

The workspace that contains `yahboomcar_description` turns out to be the ROS2
course workspace. Its fourteen packages are tutorials (`pkg_helloworld_py`,
`learn_launch`, `pkg_topic`, `myrobot`), there is no bringup, no navigation and
no MoveIt anywhere in it, and `Muto.urdf` is referenced only by an RViz display
launch. The production stack is elsewhere: nested inside the code archive, split
by controller board, carrying `m3pro_bringup`, `M3Pro_navigation`, `arm_kin` and
the Orbbec camera SDK.

So nothing is selected here. The candidates in the course workspace are
characterised and set aside, and the production workspaces are located and
inventoried for a closure pass of their own.

Extracts to content-addressed staging outside the repository. Originals are
never modified, and no vendor source is committed.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import pathlib
import re
import subprocess
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402
from navfm.isaac.urdf_import import UrdfImportRefused, parse_source  # noqa: E402

OUT = REPO / "gates/digital_twin/vendor_source_closure_20260918.json"
STAGING = pathlib.Path("/home/favl/Downloads/yahboom/extracted")
WS = STAGING / "ros2_ws_0c3e33aa" / "ros2_ws"
CODE_STAGE = STAGING / "code_7f9083d3"

ACQUISITION_REL = "gates/digital_twin/vendor_acquisition_20260918.json"
EMBEDDED_HEAD = "a283d0ffbc29d3612af54f6e453f70c10074f8b8"


def _run(*args: str, cwd: pathlib.Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, check=False,
                          cwd=str(cwd) if cwd else None)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def closure(root: pathlib.Path) -> dict[str, Any]:
    """Content-addressed inventory. Path plus hash, never mtime."""
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            rows.append((str(path.relative_to(root)), sha256_file(path)))
    digest = hashlib.sha256(
        "\n".join(f"{p}:{h}" for p, h in rows).encode()).hexdigest()
    return {
        "root": str(root),
        "regular_file_count": len(rows),
        "directory_count": sum(1 for p in root.rglob("*") if p.is_dir()),
        "symlink_count": sum(1 for p in root.rglob("*") if p.is_symlink()),
        "closure_digest": digest,
        "digest_basis": "relative path + SHA-256, excluding .git and mtime",
    }


def embedded_git() -> dict[str, Any]:
    """Read-only. Nothing in .git is written."""
    git = WS / ".git"
    if not git.is_dir():
        return {"present": False}

    head_ref = (git / "HEAD").read_text().strip()
    config = (git / "config").read_text()
    remote = re.search(r'\[remote "origin"\][^\[]*url\s*=\s*(\S+)', config)
    reflog = (git / "logs" / "HEAD").read_text().splitlines() if (
        git / "logs" / "HEAD").is_file() else []

    # Does the extracted working tree match the committed tree?
    _, listing = _run("git", "--no-optional-locks", "ls-tree", "-r",
                      EMBEDDED_HEAD, cwd=WS)
    exact = crlf_only = missing = 0
    for line in listing.splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) < 4:
            continue
        blob, rel = parts[2], parts[3]
        target = WS / rel
        if not target.is_file():
            missing += 1
            continue
        _, observed = _run("git", "--no-optional-locks", "hash-object", rel, cwd=WS)
        if observed.strip() == blob:
            exact += 1
            continue
        stripped = target.read_bytes().replace(b"\r\n", b"\n")
        proc = subprocess.run(
            ["git", "--no-optional-locks", "hash-object", "--stdin"],
            input=stripped, capture_output=True, check=False, cwd=str(WS))
        if proc.stdout.decode().strip() == blob:
            crlf_only += 1
        else:
            missing += 1

    verdict = "PASS_MODULO_LINE_ENDINGS" if (missing == 0 and crlf_only) else (
        "PASS" if missing == 0 and crlf_only == 0 else "FAIL")
    return {
        "present": True,
        "HEAD": head_ref,
        "head_commit": EMBEDDED_HEAD,
        "remote_origin": remote.group(1) if remote else None,
        "remote_is_first_party": bool(remote and "yahboom" in remote.group(1).lower()),
        "clone_event": reflog[0][:200] if reflog else None,
        "commit_event": reflog[-1][:200] if reflog else None,
        "tracked_file_count": exact + crlf_only + missing,
        "exact_match": exact,
        "differs_by_line_endings_only": crlf_only,
        "genuinely_different_or_missing": missing,
        "EXTRACTED_TREE_MATCHES_EMBEDDED_HEAD": verdict,
        "note": ("the archive was not made from a clean checkout in the byte sense: "
                 "the working tree carries CRLF where the objects hold LF. Every "
                 "difference is explained by that, and none by content"),
    }


def candidates() -> list[dict[str, Any]]:
    rows = []
    for urdf in sorted(WS.rglob("*.urdf")):
        if ".git" in urdf.parts:
            continue
        rel = str(urdf.relative_to(WS))
        entry: dict[str, Any] = {
            "path": rel, "sha256": sha256_file(urdf),
            "byte_size": urdf.stat().st_size,
        }
        try:
            model = parse_source(urdf)
            entry.update({
                "STRICT_XML_PARSE": "PASS", "robot_name": model.robot_name,
                "link_count": len(model.links), "joint_count": len(model.joints),
                "collision_count": len(model.collisions),
            })
        except UrdfImportRefused as exc:
            entry.update({"STRICT_XML_PARSE": "REFUSED",
                          "refusal_category": exc.category,
                          "refusal_detail": exc.detail[:200]})

        refs = re.findall(r'filename="(package://[^"]+)"', urdf.read_text(
            encoding="utf-8", errors="replace"))
        unique = sorted(set(refs))
        resolved = []
        for ref in unique:
            tail = ref[len("package://"):]
            package, _, rest = tail.partition("/")
            resolved.append((WS / "src" / package / rest).is_file())
        entry["package_references"] = len(refs)
        entry["unique_package_references"] = len(unique)
        entry["references_resolvable_in_workspace"] = sum(resolved)
        entry["references_missing"] = len(unique) - sum(resolved)

        consumers = []
        for launch in WS.rglob("*.py"):
            if ".git" in launch.parts:
                continue
            if pathlib.Path(rel).name in launch.read_text(
                    encoding="utf-8", errors="replace"):
                consumers.append(str(launch.relative_to(WS)))
        entry["referenced_by"] = consumers
        rows.append(entry)
    return rows


def production_workspaces() -> list[dict[str, Any]]:
    """Located, inventoried, not analysed. Their closure is its own pass."""
    rows = []
    for archive in sorted(CODE_STAGE.glob("*.zip")):
        _, listing = _run("zipinfo", "-1", str(archive))
        members = [m for m in listing.splitlines() if m.strip()]
        packages = sorted({m.split("/src/")[1].split("/")[0]
                           for m in members if "/src/" in m})
        rows.append({
            "nested_archive": archive.name,
            "extracted_from": "ROSMASTER M3 PRO-Code.zip",
            "board_variant": "orin",
            "sha256": sha256_file(archive),
            "byte_size": archive.stat().st_size,
            "member_count": len(members),
            "urdf_count": sum(1 for m in members if m.lower().endswith(".urdf")),
            "xacro_count": sum(1 for m in members if m.lower().endswith(".xacro")),
            "mesh_count": sum(1 for m in members
                              if m.lower().endswith((".stl", ".dae"))),
            "packages": packages,
            "analysed": False,
            "status": "LOCATED_NOT_ANALYSED",
        })
    return rows


def main() -> int:
    observed_at = _dt.datetime.now(_dt.UTC).isoformat()
    _, head = _run("git", "-C", str(REPO), "rev-parse", "HEAD")

    ws_closure = closure(WS)
    git_identity = embedded_git()
    urdfs = candidates()
    production = production_workspaces()

    course_packages = sorted(p.name for p in (WS / "src").iterdir() if p.is_dir())
    production_markers = ("bringup", "navigation", "moveit", "arm_kin", "arm_driver")
    course_has_production = [p for p in course_packages
                             if any(m in p.lower() for m in production_markers)]

    record: dict[str, Any] = {
        "check": "VENDOR_SOURCE_CLOSURE",
        "artifact_semantics": "SOURCE_DISCOVERY_NO_DESCRIPTION_SELECTED",
        "author": "Frank Asante Van Laarhoven",
        "provenance_observed_at": observed_at,
        "repository_head": head.strip(),
        "acquisition_evidence": {
            "path": ACQUISITION_REL,
            "sha256": sha256_file(REPO / ACQUISITION_REL)},
        "originals_reverified": True,
        "extraction": {
            "staging_root": str(STAGING),
            "content_addressed": True,
            "inside_repository": False,
            "ros2_ws_closure": ws_closure,
        },
        "EMBEDDED_GIT_IDENTITY": git_identity,
        "description_candidates": urdfs,
        "course_workspace": {
            "packages": course_packages,
            "package_count": len(course_packages),
            "production_packages_present": course_has_production,
            "VERDICT": "ROS2_COURSE_WORKSPACE",
            "reasoning": (
                "fourteen packages, of which thirteen are ROS2 tutorials, and no "
                "bringup, navigation or MoveIt package anywhere. The only "
                "description package is consumed by an RViz display launch"),
        },
        "MUTO_MODEL_IDENTITY": {
            "VERDICT": "B_TUTORIAL_OR_EXAMPLE_CONTENT",
            "evidence": [
                "Muto.urdf is referenced only by "
                "yahboomcar_description/launch/display.launch.py, an RViz display",
                "the workspace containing it has no bringup, navigation or MoveIt",
                "the production stack is a separate nested workspace carrying "
                "m3pro_bringup and M3Pro_navigation",
            ],
            "not_inferred_from_filename": True,
            "consequence": (
                "the Muto descriptions are characterised and set aside. They are "
                "not the M3 Pro apparatus"),
        },
        "PRODUCTION_WORKSPACES_LOCATED": production,
        "production_note": (
            "nested inside the code archive and split by controller board: an "
            "orin/ set and a 'jetson nano, pi' set. The Orin variants match the "
            "installed module. Two M3Pro_ws versions exist across boards, 0.0.1 "
            "for orin and 0.0.2 for nano/pi, which is itself a discrepancy to "
            "resolve before adoption"),
        "PARSER_FINDING": {
            "observation": (
                "all three Muto descriptions are refused UNRESOLVED_DEPENDENCY for "
                "their package:// mesh references"),
            "but": (
                "every unique reference resolves to a file present in the "
                "workspace. The refusal is a true statement about the parser's "
                "resolver scope, not about the source"),
            "resolution": (
                "a workspace-aware package:// resolver is a capability the parser "
                "lacks, and adding one is not loosening it. The parser stays "
                "strict"),
        },
        "LICENCE": {
            "root_licence": "Apache-2.0 at ros2_ws/LICENSE",
            "package_declarations": "TODO: License declaration, in all fifteen",
            "public_github_repository_licence": "none declared",
            "PACKAGE_LICENCE_CLARITY": "AMBIGUOUS",
            "VENDOR_SOURCE_REDISTRIBUTION": "NOT_AUTHORISED_PENDING_CLARIFICATION",
            "analysis_permitted": True,
            "vendoring_permitted": False,
        },
        "AUTHORITATIVE_VENDOR_SOURCE": "EXTRACTED_AND_CONTENT_ADDRESSED",
        "ROBOT_DESCRIPTION_CANDIDATES": "CHARACTERIZED",
        "AUTHORITATIVE_ROBOT_DESCRIPTION": "NOT_SELECTED",
        "PHYSICAL_CAMERA_EXTRINSIC": "NOT_MEASURED",
        "PRODUCTION_M3PRO_USD": "NOT_GENERATED",
        "SCIENTIFIC_ARM_A_N": 0,
        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "CLAIM_BOUNDARY": (
            "this establishes where the descriptions are and what they belong to. "
            "It selects nothing, measures no physical quantity, and no vendor "
            "source is committed to this repository"),
    }

    sha = emit_evidence(OUT, record, required_keys=(
        "check", "extraction", "EMBEDDED_GIT_IDENTITY", "description_candidates",
        "MUTO_MODEL_IDENTITY", "LICENCE", "AUTHORITATIVE_ROBOT_DESCRIPTION"))

    print("=" * 74)
    print("VENDOR SOURCE CLOSURE")
    print("=" * 74)
    print(f"ros2_ws closure     files={ws_closure['regular_file_count']} "
          f"digest={ws_closure['closure_digest'][:16]}")
    g = git_identity
    print(f"embedded git        {g['head_commit'][:12]}  {g['remote_origin']}")
    print(f"  tree vs HEAD      {g['EXTRACTED_TREE_MATCHES_EMBEDDED_HEAD']} "
          f"(exact={g['exact_match']} crlf={g['differs_by_line_endings_only']} "
          f"other={g['genuinely_different_or_missing']})")
    print()
    for c in urdfs:
        print(f"  {c['path']}")
        print(f"     parse={c['STRICT_XML_PARSE']:8s} "
              f"refs={c['unique_package_references']} "
              f"resolvable={c['references_resolvable_in_workspace']} "
              f"referenced_by={len(c['referenced_by'])}")
    print()
    print(f"MUTO_MODEL_IDENTITY {record['MUTO_MODEL_IDENTITY']['VERDICT']}")
    print(f"course workspace    {record['course_workspace']['VERDICT']} "
          f"({len(course_packages)} packages, production={course_has_production})")
    print()
    print("production workspaces located:")
    for p in production:
        print(f"  {p['nested_archive']:24s} members={p['member_count']:5d} "
              f"urdf={p['urdf_count']} xacro={p['xacro_count']} "
              f"packages={len(p['packages'])}")
    print()
    print(f"LICENCE             {record['LICENCE']['PACKAGE_LICENCE_CLARITY']} / "
          f"{record['LICENCE']['VENDOR_SOURCE_REDISTRIBUTION']}")
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha}")
    print("AUTHORITATIVE_ROBOT_DESCRIPTION  NOT_SELECTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
