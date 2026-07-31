"""Enforce the test-population invariant: evidence completeness, not a green count.

    python scripts/check_test_population.py gates/M2/test_population.json
    python scripts/check_test_population.py <report> --update   # re-pin, reviewed

F-M2-1 is the failure this exists to make impossible. An environment built from
the documented prerequisites could not import `matplotlib` or `cv2`, so
`vint_train.training.train_utils` was unimportable and the 26 upstream-marked
tests -- the compatibility proof the standing instructions call the
specification -- degraded to 9 passed, 6 skipped, 11 never collected. The suite
exited 0 and printed "228 passed". The proof was 65 % inert and the archive
would have recorded a green run as evidence that it ran.

Classification, per the accepted review: **evidence-completeness failure caused
by silent test-population contraction.** A failing test stops a gate. A
*missing* test lets the gate write a green summary, and only the population
distinguishes the two.

The three conditions, all asserted from the machine-readable report emitted by
``tests/conftest.py`` and never parsed from a summary line:

1. the expected required tests were collected -- by node id, not by count alone;
2. zero required tests were skipped, deselected, or lost to a collection error;
3. every collected required test passed.

The expectation is pinned in ``tests/population_manifest.json`` against the
upstream commit and a hash over the required node ids. Adding or removing a
required test changes that hash, so the pin can only move through an explicit,
reviewed commit -- which is the point. A silently shrinking specification is
what this guards.
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


def node_id_digest(node_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(node_ids)).encode()).hexdigest()


def upstream_commit(upstream_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(upstream_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def required_node_ids(report: dict[str, Any], marker: str) -> list[str]:
    return sorted(n for n, markers in report["collected"].items() if marker in markers)


def check(report: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    """Return a list of violations; empty means the invariant holds."""
    marker = manifest["required_marker"]
    failures: list[str] = []

    found = required_node_ids(report, marker)
    expected_count = int(manifest["expected_required_count"])
    expected_digest = str(manifest["required_node_ids_sha256"])

    # Condition 1 -- the expected required tests were collected.
    if len(found) != expected_count:
        failures.append(
            f"CONDITION 1 -- required test count is {len(found)}, pinned at {expected_count}. "
            f"A contraction here is the F-M2-1 failure mode: the specification shrank and "
            f"the suite still passed."
        )
    actual_digest = node_id_digest(found)
    if actual_digest != expected_digest:
        failures.append(
            f"CONDITION 1 -- required node-id set does not match the pin.\n"
            f"  pinned {expected_digest}\n  actual {actual_digest}\n"
            f"  Re-pin only through a reviewed commit: --update."
        )

    # Condition 2 -- none of them was skipped, deselected, or lost to collection.
    deselected = sorted(set(report["deselected"]) & set(found))
    if deselected:
        failures.append(f"CONDITION 2 -- required tests deselected: {deselected}")
    skipped = sorted(n for n in found if report["outcomes"].get(n) == "skipped")
    if skipped:
        reasons = {n: report["skip_reasons"].get(n, "(no reason recorded)") for n in skipped}
        detail = "\n".join(f"    {n}\n      {r}" for n, r in reasons.items())
        failures.append(f"CONDITION 2 -- required tests SKIPPED:\n{detail}")
    if report["collection_errors"]:
        failures.append(
            f"CONDITION 2 -- collection errors present: {report['collection_errors']}. "
            f"A run with a collection error has an unknown population."
        )
    uncollected = [n for n in found if n not in report["outcomes"]]
    if uncollected:
        failures.append(f"CONDITION 2 -- required tests collected but never run: {uncollected}")

    # Condition 3 -- all collected required tests passed.
    not_passed = sorted(
        n for n in found if report["outcomes"].get(n) not in {"passed", None} and n not in skipped
    )
    if not_passed:
        failures.append(
            f"CONDITION 3 -- required tests did not pass: "
            f"{ {n: report['outcomes'].get(n) for n in not_passed} }"
        )

    pinned_upstream = manifest.get("upstream_commit")
    actual_upstream = upstream_commit(Path(manifest["upstream_path"]))
    if actual_upstream is not None and pinned_upstream != actual_upstream:
        failures.append(
            f"PIN -- upstream commit is {actual_upstream}, manifest pins {pinned_upstream}. "
            f"The required-test expectation is only meaningful against the pinned reference."
        )
    return failures


def build_manifest(report: dict[str, Any], marker: str, upstream_path: str) -> dict[str, Any]:
    found = required_node_ids(report, marker)
    return {
        "_comment": (
            "Pinned test-population expectation. Guards against silent contraction of the "
            "upstream compatibility proof (F-M2-1). Update only through a reviewed commit."
        ),
        "required_marker": marker,
        "expected_required_count": len(found),
        "required_node_ids_sha256": node_id_digest(found),
        "required_node_ids": found,
        "upstream_path": upstream_path,
        "upstream_commit": upstream_commit(Path(upstream_path)),
        "informational_total_collected": len(report["collected"]),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("report", help="population report JSON from --population-report")
    p.add_argument("--manifest", default=str(MANIFEST))
    p.add_argument("--marker", default="upstream")
    p.add_argument("--upstream-path", default="third_party/visualnav-transformer")
    p.add_argument("--update", action="store_true", help="re-pin the manifest from this report")
    args = p.parse_args(argv)

    report = json.loads(Path(args.report).read_text())

    if args.update:
        manifest = build_manifest(report, args.marker, args.upstream_path)
        Path(args.manifest).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(
            f"re-pinned {args.manifest}: {manifest['expected_required_count']} required tests, "
            f"digest {manifest['required_node_ids_sha256'][:16]}..."
        )
        return 0

    manifest = json.loads(Path(args.manifest).read_text())
    failures = check(report, manifest)
    if failures:
        print("TEST POPULATION INVARIANT VIOLATED", file=sys.stderr)
        print(
            "evidence-completeness failure caused by silent test-population contraction\n",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  {failure}\n", file=sys.stderr)
        return 1

    print(
        f"test population OK: {manifest['expected_required_count']} required "
        f"'{manifest['required_marker']}' tests collected, none skipped or deselected, all passed; "
        f"upstream pinned at {str(manifest.get('upstream_commit'))[:12]}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
