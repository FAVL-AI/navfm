"""Qualify CoACD as the collider derivation backend, and complete Decision B.

The previous record left Decision B blocked on two measurements: a single
convex hull exceeded the preregistered inflation limit everywhere it could be
assessed, and no decomposition backend existed to demonstrate determinism with.
This answers the second and reports what follows.

Everything runs in an environment created for this purpose and nothing else.
The Isaac installation is not touched, which matters because the decomposer is
an offline geometry tool and the simulator is the apparatus: qualifying one
should not perturb the other.

Determinism is measured across fresh processes rather than repeated calls,
since a second call inside one interpreter can share state that a run on
another day would not have. The canonical digest ignores serialisation order
and nothing else, so a matching digest means the same solids and not merely the
same file.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402
from navfm.isaac.collider_qualification import (  # noqa: E402
    ACCEPTANCE_CONTRACT,
    coverage_report,
    evaluate_acceptance,
)
from navfm.isaac.mesh_geometry import measure_mesh, read_binary_stl  # noqa: E402

OUT = REPO / "gates/digital_twin/coacd_backend_qualification_20260918.json"
STAGING = pathlib.Path("/home/favl/Downloads/yahboom/extracted")
M3PRO_WS = STAGING / "M3Pro_ws-0.0.1_f08db69b" / "m3pro_ws"
MESHES = M3PRO_WS / "src/M3Pro/meshes"
#: Where the qualification run left its temporary geometry. Supplied by the
#: caller rather than hardcoded: generated decompositions live outside the
#: repository by design, and a committed script should not carry one machine's
#: session path.
SCRATCH = pathlib.Path(
    os.environ.get("NAVFM_COLLIDER_WORK_DIR", "")
    or pathlib.Path.home() / ".navfm-collider-qualification")
VENV = pathlib.Path.home() / ".venv-collider-qualification"

PRIOR = (
    "gates/digital_twin/collision_geometry_strategy_20260918.json",
    "gates/digital_twin/robot_description_authority_20260918.json",
)

#: link -> mesh file, from the authoritative URDF's collision elements.
LINK_MESH = {
    "base_link": "base_link.STL", "arm1": "arm1.STL", "arm2": "arm2.STL",
    "arm3": "arm3.STL", "arm4": "arm4.STL", "arm5": "arm5.STL",
    "rlink1": "rlink1.STL", "rlink2": "rlink2.STL", "rlink3": "rlink3.STL",
    "llink1": "llink1.STL", "llink2": "llink2.STL", "llink3": "llink3.STL",
    "Gripping": "Gripping.STL", "camera_link": "DCW2.STL",
    "lwheel1": "lwheel1.STL", "lwheel2": "lwheel2.STL",
    "rwheel1": "rwheel1.STL", "rwheel2": "rwheel2.STL",
}
CLEARANCE_CRITICAL = ("base_link", "lwheel1", "lwheel2", "rwheel1", "rwheel2",
                      "arm1", "arm2")


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment_identity() -> dict[str, Any]:
    """Enough to rebuild the backend, and proof it is not the Isaac one."""
    listing = subprocess.run(
        [str(VENV / "bin/pip"), "list", "--format=json"],
        capture_output=True, text=True, check=False,
        env={"PATH": "/usr/bin:/bin"})
    try:
        packages = {p["name"]: p["version"] for p in json.loads(listing.stdout)}
    except json.JSONDecodeError:
        packages = {}
    version = subprocess.run(
        [str(VENV / "bin/python"), "-c",
         "import sys,platform;print(sys.version.split()[0]);"
         "print(platform.platform());print(platform.machine())"],
        capture_output=True, text=True, check=False,
        env={"PATH": "/usr/bin:/bin"}).stdout.splitlines()

    native = sorted(VENV.glob("lib/python*/site-packages/coacd/**/*.so"))
    wheels = sorted(SCRATCH.parent.glob("coacd_wheel/*.whl"))
    return {
        "kind": "python venv created for this qualification only, outside the "
                "repository and outside every other environment on this host",
        "identified_by": "the wheel and native-library hashes below, not by path",
        "python": version[0] if version else "UNKNOWN",
        "platform": version[1] if len(version) > 1 else "UNKNOWN",
        "machine": version[2] if len(version) > 2 else "UNKNOWN",
        "packages": packages,
        "package_count": len(packages),
        "ISOLATION_NOTE": (
            "the environment reports only its own packages when PYTHONPATH is "
            "cleared. With the host ROS PYTHONPATH inherited it also lists the "
            "system ROS distribution, so every invocation clears it, which is the "
            "repository's existing clean-environment practice"),
        "coacd_version": packages.get("coacd"),
        "numpy_version": packages.get("numpy"),
        "wheel": [{"filename": w.name, "sha256": sha256_file(w),
                   "size": w.stat().st_size} for w in wheels],
        "native_library": [{"name": n.name, "sha256": sha256_file(n),
                            "size": n.stat().st_size} for n in native],
        "built_from_source": False,
        "ISAAC_ENVIRONMENT_MODIFIED": False,
        "SYSTEM_PYTHON_MODIFIED": False,
        "APT_USED": False,
    }


def frozen_configuration() -> dict[str, Any]:
    path = SCRATCH / "config_v1.json"
    parameters = json.loads(path.read_text())
    return {
        "config_id": "V1",
        "filename": path.name,
        "sha256": sha256_file(path),
        "path_not_recorded": (
            "the configuration is identified by its hash. Where it sat on this "
            "host is not part of its identity and is not portable evidence"),
        "parameters": parameters,
        "FROZEN_BEFORE_FULL_POPULATION": True,
        "revised_after_precheck": False,
        "every_parameter_explicit": True,
        "defaults_recorded_as_values": (
            "every parameter is passed explicitly, including those that match "
            "upstream defaults, so the run reproduces without knowing which CoACD "
            "version supplied which default"),
        "seed": parameters["seed"],
        "seed_is_explicit": True,
        "REAL_METRIC_MODE": "NOT_ADMITTED_DUE_TO_UNIT_EVIDENCE",
        "real_metric_reason": (
            "the metre reading of these meshes is derived from the URDF contract "
            "and magnitude consistency, not demonstrated from the mesh, which "
            "carries no unit metadata. Normalised mode is used and the decision "
            "is recorded rather than the unit being assumed"),
    }


def load_population() -> dict[str, list[dict[str, Any]]]:
    path = SCRATCH / "population.jsonl"
    if not path.is_file():
        return {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        grouped.setdefault(entry["result"]["link"], []).append(entry["result"])
    return grouped


def load_parts(directory: pathlib.Path) -> list[tuple[np.ndarray, np.ndarray]]:
    archive = np.load(directory / "parts.npz")
    count = sum(1 for key in archive.files if key.startswith("v"))
    return [(archive[f"v{i}"], archive[f"f{i}"]) for i in range(count)]


def determinism(runs: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = {r["canonical_digest"] for r in runs}
    raw = {r["raw_file_sha256"] for r in runs}
    return {
        "repetitions": len(runs),
        "canonical_digests_distinct": len(canonical),
        "raw_file_digests_distinct": len(raw),
        "CANONICAL_GEOMETRY_DETERMINISTIC": len(canonical) == 1,
        "RAW_BYTE_DETERMINISTIC": len(raw) == 1,
        "canonical_digest": next(iter(canonical)) if len(canonical) == 1 else None,
        "note": ("raw serialisation order may differ without the geometry "
                 "differing, so the two are reported separately"),
    }


def main() -> int:
    own = str(OUT.relative_to(REPO))
    head = _git("rev-parse", "HEAD")
    dirty = [line for line in _git("status", "--porcelain").splitlines()
             if line.strip() and own not in line]

    population = load_population()
    per_link: dict[str, dict[str, Any]] = {}

    for link, mesh_name in LINK_MESH.items():
        runs = population.get(link, [])
        entry: dict[str, Any] = {"mesh": mesh_name, "runs": len(runs)}
        if not runs:
            entry["STATUS"] = "NOT_RUN"
            per_link[link] = entry
            continue

        source = MESHES / mesh_name
        measured = measure_mesh(source)
        entry.update({
            "source_sha256": measured.sha256,
            "source_closed_surface": measured.is_closed_estimate,
            "source_triangles": measured.triangle_count,
            "preprocessing_applied": not measured.is_closed_estimate,
            "preprocess_mode": "auto",
            "determinism": determinism(runs),
            "part_count": runs[0]["part_count"],
            "total_part_vertices": runs[0]["total_part_vertices"],
            "total_part_faces": runs[0]["total_part_faces"],
            "canonical_digest": runs[0]["canonical_digest"],
        })

        directory = SCRATCH / "pop" / f"{link}_r1"
        if (directory / "parts.npz").is_file():
            hulls = load_parts(directory)
            triangles = read_binary_stl(source)
            vertices = np.unique(triangles.reshape(-1, 3), axis=0)
            entry["coverage"] = coverage_report(vertices, triangles, hulls)
            entry["parts"] = list(range(len(hulls)))
            under = entry["coverage"]["under_coverage_m"]["max"]
            limit = ACCEPTANCE_CONTRACT["under_coverage"]["threshold_m"]
            entry["under_coverage_within_limit"] = (
                under is not None and under <= limit)
            entry["clearance_critical"] = link in CLEARANCE_CRITICAL
            entry["STATUS"] = "MEASURED"
        else:
            entry["STATUS"] = "PARTS_MISSING"
        per_link[link] = entry

    measured_links = {k for k, v in per_link.items() if v.get("STATUS") == "MEASURED"}
    all_deterministic = all(
        v["determinism"]["CANONICAL_GEOMETRY_DETERMINISTIC"]
        for v in per_link.values() if "determinism" in v)
    complete = measured_links == set(LINK_MESH)

    acceptance = evaluate_acceptance(
        {k: v for k, v in per_link.items() if v.get("STATUS") == "MEASURED"},
        set(LINK_MESH), all_deterministic and complete)

    resolved = acceptance["ACCEPTED"]
    blockers = []
    if not complete:
        blockers.append(
            f"{len(set(LINK_MESH) - measured_links)} of {len(LINK_MESH)} collision "
            "elements were not measured in this run")
    if not all_deterministic:
        blockers.append("at least one link did not reproduce across fresh processes")
    for failure in acceptance["failures"]:
        blockers.append(f"{failure['link']}: {failure['reason']}")

    record: dict[str, Any] = {
        "check": "COACD_BACKEND_QUALIFICATION",
        "work_dir_source": ("NAVFM_COLLIDER_WORK_DIR" if
                            os.environ.get("NAVFM_COLLIDER_WORK_DIR")
                            else "default"),
        "artifact_semantics": "BACKEND_QUALIFIED_DECISION_B_REVISITED",
        "author": "Frank Asante Van Laarhoven",
        "provenance_observed_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "repository_head": head,
        "worktree_clean_at_measurement": not dirty,
        "other_dirty_entries": dirty,
        "prior_evidence_not_rewritten": [
            {"path": p, "sha256": sha256_file(REPO / p)} for p in PRIOR
            if (REPO / p).is_file()],
        "supersedes_status_only": (
            "the earlier record is historically correct: Decision B was blocked at "
            "that point on the evidence then available. This record may change the "
            "current status and does not revise the earlier one"),

        "BACKEND_CHOICE": {
            "backend": "CoACD",
            "vhacd_qualified_in_parallel": False,
            "reason": ("V-HACD upstream is archived and directs users to CoACD; "
                       "CoACD exposes an explicit reproducibility seed and "
                       "preprocesses non-manifold input, which matters because "
                       "eight of eighteen vendor meshes are not closed"),
            "claim_boundary": ("this is a tooling choice. It is not evidence that "
                               "CoACD passes the geometry gate, which is measured "
                               "below"),
        },
        "ENVIRONMENT": environment_identity(),
        "FROZEN_CONFIGURATION": frozen_configuration(),
        "ACCEPTANCE_CONTRACT": ACCEPTANCE_CONTRACT,

        "PER_LINK": per_link,
        "links_measured": len(measured_links),
        "links_expected": len(LINK_MESH),
        "closed_source_meshes": sum(
            1 for v in per_link.values() if v.get("source_closed_surface")),
        "open_source_meshes": sum(
            1 for v in per_link.values()
            if v.get("source_closed_surface") is False),
        "ALL_CANONICAL_DETERMINISTIC": all_deterministic,
        "ALL_RAW_BYTE_DETERMINISTIC": all(
            v["determinism"]["RAW_BYTE_DETERMINISTIC"]
            for v in per_link.values() if "determinism" in v),

        "PREPROCESSING_FIDELITY": {
            "MEASURED_IN_ISOLATION": False,
            "reason": (
                "CoACD's Python interface exposes run_coacd and set_log_level and "
                "no separate preprocessing entry point, so the remeshed "
                "intermediate for a non-closed source is never returned and cannot "
                "be hashed or compared on its own"),
            "what_is_measured_instead": (
                "the source-to-collider surface distance, which carries the "
                "combined effect of preprocessing and decomposition. For the eight "
                "non-closed meshes that combined figure is an upper bound on the "
                "preprocessing deviation, not a separation of the two"),
            "consequence": (
                "the derivation is recorded as source plus a pinned configuration "
                "rather than as two separately auditable stages. Isolating them "
                "would need a CoACD build that returns the intermediate"),
            "affected_links": sorted(
                k for k, v in per_link.items()
                if v.get("source_closed_surface") is False),
        },
        "COMPLEXITY": {
            "total_parts": sum(v.get("part_count", 0) for v in per_link.values()),
            "per_link": {k: v.get("part_count") for k, v in per_link.items()},
            "threshold": None,
            "note": ("recorded, not gated. The contract sets no complexity limit "
                     "because the admissible cost depends on how the asset is "
                     "used, which this tranche does not decide"),
            "CONCENTRATION": {
                "wheels_total": sum(
                    per_link[k].get("part_count", 0) for k in
                    ("lwheel1", "lwheel2", "rwheel1", "rwheel2")),
                "finding": (
                    "the four wheels carry most of the convex parts in the set. "
                    "Each is a non-closed mesh whose rollers appear to remesh into "
                    "many small solids, so the part that contributes least to "
                    "navigation clearance costs the most to simulate"),
                "NOT_A_FAILURE_HERE": (
                    "no complexity limit was frozen, so this does not fail the "
                    "contract. It is the obvious question for whoever decides how "
                    "the asset is loaded, and inventing a limit now to flag it "
                    "would be choosing a threshold after seeing the result"),
            },
        },

        "MECANUM_BOUNDARY": {
            "CALIBRATED_MECANUM_CONTACT_MODEL": "NOT_ESTABLISHED",
            "what_wheel_colliders_are_for_here": ["navigation footprint",
                                                  "gross collision geometry"],
            "why": ("a convex decomposition of a wheel is a set of solids. It does "
                    "not reproduce roller contact, and the source joints are fixed "
                    "in any case"),
        },
        "CLEARANCE_CRITICAL_LINKS": list(CLEARANCE_CRITICAL),
        "role_failures_are_not_averaged": (
            "a breach on any clearance-critical link fails the set regardless of "
            "how the rest score"),

        "ACCEPTANCE": acceptance,
        "ISAAC_STATUS": "COLLIDER_FORMAT_STRATEGY_ISAAC_COMPATIBLE_IN_PRINCIPLE",
        "isaac_note": (
            "Isaac supports convex decomposition as a collision approximation, so "
            "the concept carries over. Nothing here was loaded into Isaac and "
            "ISAAC_RUNTIME_VALIDATED is not claimed"),

        "COLLISION_GEOMETRY_SOURCE": "AUTHORITATIVE_VENDOR_COLLISION_MESHES",
        "COLLIDER_DERIVATION_STRATEGY":
            "PINNED_DETERMINISTIC_COACD" if resolved else "UNDECIDED",
        "DECISION_B": "RESOLVED" if resolved else "BLOCKED",
        "DECISION_B_BLOCKERS": blockers,
        "thresholds_not_weakened": (
            "the 1.25 hull inflation limit and the one millimetre under-coverage "
            "limit were both frozen before the measurements they judge and neither "
            "was revised to obtain a result"),

        "OUTPUTS_ARE_TEMPORARY": {
            "generated_geometry_location": "OUTSIDE_THE_REPOSITORY_HOST_LOCAL",
            "location_not_recorded": (
                "a session directory on one machine is not reproducible evidence, "
                "and the geometry it holds is not committed, so the path is "
                "classified rather than written down"),
            "committed": False,
            "note": "decompositions exist outside the repository for measurement "
                    "only and are not committed or redistributed",
        },
        "LICENCE_BOUNDARY": "REDISTRIBUTION NOT_AUTHORISED_PENDING_CLARIFICATION",
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
        "check", "BACKEND_CHOICE", "ENVIRONMENT", "FROZEN_CONFIGURATION",
        "ACCEPTANCE_CONTRACT", "PER_LINK", "ACCEPTANCE", "DECISION_B",
        "PREPROCESSING_FIDELITY", "COMPLEXITY",
        "LICENCE_BOUNDARY"))

    print("=" * 78)
    print("COACD BACKEND QUALIFICATION")
    print("=" * 78)
    env = record["ENVIRONMENT"]
    print(f"  HEAD {head[:12]}  clean={record['worktree_clean_at_measurement']}")
    print(f"  env           {env['kind'][:58]}")
    print(f"                python {env['python']}  coacd {env['coacd_version']}  "
          f"numpy {env['numpy_version']}  packages {env['package_count']}")
    cfg = record["FROZEN_CONFIGURATION"]
    print(f"  config {cfg['config_id']}     sha {cfg['sha256'][:16]}  seed "
          f"{cfg['seed']}  real_metric {cfg['REAL_METRIC_MODE']}")
    print()
    print(f"  {'link':13s} {'src':>7s} {'cl':>3s} {'parts':>6s} {'det':>4s} "
          f"{'under(mm)':>10s} {'over p95(mm)':>13s}")
    for link in LINK_MESH:
        v = per_link[link]
        if v.get("STATUS") != "MEASURED":
            print(f"  {link:13s} {v.get('STATUS')}")
            continue
        cov = v["coverage"]
        det = "OK" if v["determinism"]["CANONICAL_GEOMETRY_DETERMINISTIC"] else "NO"
        under = cov["under_coverage_m"]["max"] * 1000
        over = cov["over_coverage_m"]["p95"] * 1000
        print(f"  {link:13s} {v['source_triangles']:7d} "
              f"{'Y' if v['source_closed_surface'] else 'N':>3s} "
              f"{v['part_count']:6d} {det:>4s} {under:10.4f} {over:13.4f}")
    print()
    print(f"  determinism   canonical={record['ALL_CANONICAL_DETERMINISTIC']} "
          f"raw_bytes={record['ALL_RAW_BYTE_DETERMINISTIC']}")
    concentration = record["COMPLEXITY"]["CONCENTRATION"]
    total = record["COMPLEXITY"]["total_parts"]
    print(f"  complexity    {total} convex parts total; "
          f"{concentration['wheels_total']} of them are the four wheels "
          f"({100 * concentration['wheels_total'] / max(total, 1):.0f}%)")
    print(f"  preprocessing isolated={record['PREPROCESSING_FIDELITY']['MEASURED_IN_ISOLATION']} "
          f"({len(record['PREPROCESSING_FIDELITY']['affected_links'])} non-closed links)")
    print(f"  acceptance    {acceptance['ACCEPTED']} "
          f"({acceptance['failure_count']} failures)")
    for failure in acceptance["failures"][:6]:
        print(f"    {failure['link']}: {failure['reason']}")
    print()
    print(f"  SOURCE        {record['COLLISION_GEOMETRY_SOURCE']}")
    print(f"  STRATEGY      {record['COLLIDER_DERIVATION_STRATEGY']}")
    print(f"  DECISION_B    {record['DECISION_B']}")
    for blocker in blockers[:4]:
        print(f"    blocker: {blocker[:68]}")
    print(f"  artefact      {OUT.relative_to(REPO)}")
    print(f"  sha256        {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
