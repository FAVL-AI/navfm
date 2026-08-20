#!/usr/bin/env python3
"""Enforce test-population *ownership* against ``tests/population_manifest.json``.

``check_test_population.py`` guards one marker set. This guards the whole
partition: which job owns which node ids, and whether that job actually ran them.

The distinction this script exists to preserve is that four states are not
interchangeable, and only one of them is evidence:

``executed``
    the node ran in a job that declares itself its owner.
``deselected``
    the node was excluded by marker from a job that is explicitly *not* its
    owner. Legitimate, but only against a pinned set -- otherwise "deselected"
    becomes a place to hide a test nobody runs.
``not collectable``
    the node's module could not import for want of its resource. Invisible in
    a population report (it appears in no key at all), so it can only be caught
    by comparing against a pinned total.
``skipped``
    the node was collected and then declined at runtime. Never acceptable for a
    node some job owns; F-M2-1 is what happens when it is tolerated.

Digests are recomputed from the manifest's own ``population`` map rather than
read from ``digests``: a stored digest that is never recomputed certifies only
itself. ``digests`` is cross-checked against the recomputation so that a hand
edit to either side is a failure rather than a silent agreement.

Usage::

    python scripts/check_population_sets.py REPORT --mode ordinary-hermetic \\
        --versions population/versions-3.12.json
    python scripts/check_population_sets.py REPORT --mode provisioned-owner \\
        --versions population/versions-owner.json --require-upstream-pin
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

MANIFEST = Path(__file__).resolve().parents[1] / "tests" / "population_manifest.json"

ORDINARY = "ordinary-hermetic"
OWNER = "provisioned-owner"

# Provenance a job must record for its population report to mean anything: the
# same node ids under a different torch are a different measurement.
REQUIRED_VERSIONS = {ORDINARY: ("python", "numpy"), OWNER: ("python", "numpy", "torch", "matplotlib")}

_REPORT_KEYS = ("collected", "deselected", "collection_errors", "outcomes", "skip_reasons")
_MANIFEST_KEYS = ("population", "digests", "upstream_commit", "upstream_path", "open_evidence_gaps")


class SchemaError(Exception):
    """The manifest or report is not the shape this checker validates."""


def node_id_digest(node_ids: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(node_ids)).encode()).hexdigest()


def load_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise SchemaError(f"{what} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{what} is not valid JSON: {path}: {exc}") from exc


def validate_manifest(manifest: Any) -> dict[str, list[str]]:
    if not isinstance(manifest, dict):
        raise SchemaError("manifest must be a JSON object")
    for key in _MANIFEST_KEYS:
        if key not in manifest:
            raise SchemaError(f"manifest is missing required key {key!r}")
    population = manifest["population"]
    if not isinstance(population, dict) or not population:
        raise SchemaError("manifest 'population' must be a non-empty object")
    for node, markers in population.items():
        if not isinstance(node, str) or not isinstance(markers, list):
            raise SchemaError(f"manifest population entry is malformed: {node!r} -> {markers!r}")
        if not all(isinstance(m, str) for m in markers):
            raise SchemaError(f"manifest population markers must be strings: {node!r}")
    return population


def validate_report(report: Any) -> None:
    if not isinstance(report, dict):
        raise SchemaError("report must be a JSON object")
    for key in _REPORT_KEYS:
        if key not in report:
            raise SchemaError(f"report is missing required key {key!r}")
    if not isinstance(report["collected"], dict) or not isinstance(report["outcomes"], dict):
        raise SchemaError("report 'collected' and 'outcomes' must be objects")


def sets_from(population: dict[str, list[str]]) -> dict[str, set[str]]:
    total = set(population)
    marked = {n for n, m in population.items() if m}
    return {
        "total": total,
        "hermetic": total - marked,
        "resource_union": marked,
        "upstream": {n for n, m in population.items() if "upstream" in m},
        "torch": {n for n, m in population.items() if "torch" in m},
        "plot": {n for n, m in population.items() if "plot" in m},
    }


def _diff(name: str, actual: set[str], expected: set[str]) -> list[str]:
    if actual == expected:
        return []
    lines = [f"{name}: set mismatch (have {len(actual)}, pinned {len(expected)})"]
    for label, nodes in (("missing", expected - actual), ("extra", actual - expected)):
        for node in sorted(nodes):
            lines.append(f"    {label}: {node}")
    return lines


def check_versions(versions: Any, mode: str) -> list[str]:
    if not isinstance(versions, dict):
        return ["resource-version provenance must be a JSON object"]
    absent = [k for k in REQUIRED_VERSIONS[mode] if not str(versions.get(k, "")).strip()]
    return [f"resource-version provenance is missing: {', '.join(absent)}"] if absent else []


def upstream_head(upstream_path: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(upstream_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def check(
    report: dict[str, Any],
    manifest: dict[str, Any],
    mode: str,
    versions: Any = None,
    upstream_path: Path | None = None,
) -> list[str]:
    """Return every violation. An empty list is the only passing result."""
    population = validate_manifest(manifest)
    validate_report(report)
    if mode not in (ORDINARY, OWNER):
        raise SchemaError(f"unknown ownership mode {mode!r}")

    pinned = sets_from(population)
    # A stored digest that is never recomputed certifies only itself.
    failures = [
        f"manifest digests['{name}'] is stale: records {entry.get('sha256', '')[:16]} / "
        f"{entry.get('count')}, population gives {node_id_digest(pinned[name])[:16]} / {len(pinned[name])}"
        for name, entry in manifest["digests"].items()
        if name in pinned
        and (
            entry.get("sha256") != node_id_digest(pinned[name])
            or entry.get("count") != len(pinned[name])
        )
    ]

    collected = set(report["collected"])
    deselected = set(report["deselected"])
    executed = collected - deselected
    skipped = {n for n, o in report["outcomes"].items() if o == "skipped"}
    gaps = {g["node_id"] for g in manifest["open_evidence_gaps"]}

    if report["collection_errors"]:
        failures.append(f"collection errors present: {sorted(report['collection_errors'])}")

    if mode == ORDINARY:
        # This leg owns the hermetic population and nothing else. An unmarked
        # resource-dependent test lands here and breaks the set, which is the
        # only way to notice ownership drift from inside a hermetic job.
        failures += _diff("hermetic executed", executed, pinned["hermetic"])
        stray = deselected - pinned["resource_union"]
        if stray:
            failures.append(f"deselected outside the pinned resource population: {sorted(stray)}")
    else:
        failures += _diff("owner executed", executed, pinned["total"])
        orphaned = sorted(pinned["resource_union"] & deselected)
        if orphaned:
            failures.append(f"owned node ids deselected from their owner job: {orphaned}")
        for name in ("upstream", "torch", "plot"):
            failures += _diff(f"{name} executed", executed & pinned[name], pinned[name])

    unexpected = sorted(skipped - gaps)
    if unexpected:
        failures.append(f"unexpected skips: {unexpected}")

    if versions is not None:
        failures += check_versions(versions, mode)

    if upstream_path is not None:
        actual = upstream_head(upstream_path)
        pin = manifest["upstream_commit"]
        if actual is None:
            failures.append(f"upstream checkout not readable at {upstream_path}")
        elif actual != pin:
            failures.append(f"upstream commit is {actual}, manifest pins {pin}")

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("report", help="population report JSON from --population-report")
    parser.add_argument("--mode", required=True, choices=[ORDINARY, OWNER])
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--versions", help="JSON file recording the resource versions in use")
    parser.add_argument("--upstream-path", help="checkout whose HEAD must equal the manifest pin")
    args = parser.parse_args(argv)

    try:
        report = load_json(Path(args.report), "population report")
        manifest = load_json(Path(args.manifest), "manifest")
        versions = load_json(Path(args.versions), "versions") if args.versions else None
        failures = check(
            report,
            manifest,
            args.mode,
            versions,
            Path(args.upstream_path) if args.upstream_path else None,
        )
    except SchemaError as exc:
        print("POPULATION OWNERSHIP INVARIANT VIOLATED", file=sys.stderr)
        print(f"  {exc}", file=sys.stderr)
        return 1

    if failures:
        print("POPULATION OWNERSHIP INVARIANT VIOLATED", file=sys.stderr)
        print(f"  mode {args.mode}: a node id that no job executes has no evidence\n", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}\n", file=sys.stderr)
        return 1

    pinned = sets_from(manifest["population"])
    executed = set(report["collected"]) - set(report["deselected"])
    print(
        f"population ownership OK ({args.mode}): {len(executed)} executed, "
        f"{len(set(report['deselected']))} deselected by declared ownership, "
        f"digest {node_id_digest(executed)[:16]}"
    )
    for name in sorted(pinned):
        print(f"  {name}: {len(pinned[name])} pinned, digest {node_id_digest(pinned[name])[:16]}")
    for node in sorted({g["node_id"] for g in manifest["open_evidence_gaps"]}):
        print(f"  OPEN EVIDENCE GAP (tracked, not baselined): {node}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
