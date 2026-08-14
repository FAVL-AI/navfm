"""Render-validity matrix: why each scene passes or fails, side by side.

Three claims are kept apart here because they fail independently and the first
two can both be true while the third is false:

    dependency resolver   "the files exist"
    Isaac runtime         "the materials resolve, compile and bind"
    rendered observable   "the scene is visually valid"

Collapsing them into one implementation is what produced FL-018: a repair
verified by the same enumeration that discovered the defect, reporting complete
while the rendered output did not move at all.

So this reads each column from a *different* artefact — the mirror manifest, the
runtime audit and the camera-view record — and refuses to fill a cell from a
source that did not independently measure it. A missing source renders as
`NO EVIDENCE`, never blank and never as a pass.

Render digests are recorded per state so that "the observable did not change" is
a checkable fact rather than a recollection.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SCENES = REPO / "gates" / "scenes"
DST = SCENES / "RENDER_VALIDITY_MATRIX.md"

#: Each column is one observed state, not one scene: the same scene before and
#: after a repair are different states and must be comparable side by side.
STATES: list[tuple[str, str, str]] = [
    # (column label, camera_view record stem, mirror manifest stem or "")
    ("control_world", "control_blocks_v1", ""),
    ("hospital_A_original", "hospital_v1", ""),
    ("hospital_B_first_repair", "hospital_v1_repaired_stateB", ""),
    ("hospital_C_321", "hospital_v1_repaired", "hospital_v1"),
    ("warehouse_A_original", "simple_warehouse_v1", ""),
    ("warehouse_B_repaired", "simple_warehouse_v1_repaired", "simple_warehouse_v1"),
]

ROWS: list[tuple[str, str, str]] = [
    # (row label, source artefact, dotted lookup)
    ("background fraction", "view", "aggregate.background_fraction"),
    ("structure fraction", "view", "aggregate.structure_fraction"),
    ("floor fraction", "view", "aggregate.floor_fraction"),
    ("median forward depth (m)", "view", "aggregate.median_forward_depth_m"),
    ("dominant hue fraction", "view", "aggregate.dominant_hue_fraction"),
    ("distinct colour bins", "view", "aggregate.distinct_colour_bins"),
    ("saturated pixel fraction", "view", "aggregate.saturated_pixel_fraction"),
    ("render verdict", "view", "verdict.result"),
    ("MDL modules required", "mirror", "closure.mdl.required"),
    ("MDL modules present", "mirror", "closure.mdl.present"),
    ("textures required", "mirror", "closure.textures.required"),
    ("textures present", "mirror", "closure.textures.present"),
    ("dependency closure", "mirror", "closure.full_render_closure"),
    ("runtime MDL errors", "runtime", "summary.mdl_errors"),
    ("materials compiled", "runtime", "summary.materials_compiled"),
    ("visible meshes unbound", "runtime", "summary.visible_meshes_unbound"),
    ("fallback materials", "runtime", "summary.fallback_materials"),
]


def dig(d: Any, path: str) -> Any:
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def load(stem: str, prefix: str) -> dict[str, Any] | None:
    p = SCENES / f"{prefix}{stem}.json"
    return json.loads(p.read_text()) if p.is_file() else None


def render_digest(stem: str) -> str:
    p = SCENES / "views" / stem / "pov_00.png"
    if not p.is_file():
        return "ABSENT"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def main() -> int:
    cols: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]] = []
    for label, view_stem, mirror_stem in STATES:
        cols.append((
            label,
            load(view_stem, "camera_view_"),
            load(mirror_stem, "mirror_manifest_") if mirror_stem else None,
            load(view_stem, "runtime_material_audit_"),
        ))

    present = [c for c in cols if c[1] or c[2] or c[3]]
    if not present:
        print("REFUSED: no scene evidence on record", file=sys.stderr)
        return 2

    head = "| Metric | " + " | ".join(c[0] for c in present) + " |"
    sep = "|---" * (len(present) + 1) + "|"
    out = [
        "# Render-validity matrix",
        "",
        "Three independent contracts, read from three different artefacts. A cell is",
        "`NO EVIDENCE` when its source did not measure it — never blank, never a pass.",
        "",
        "```",
        "dependency resolver   \"the files exist\"",
        "        !=",
        "Isaac runtime         \"materials resolve, compile and bind\"",
        "        !=",
        "rendered observable   \"the scene is visually valid\"",
        "```",
        "",
        "Collapsing these into one implementation produced FL-018: a repair verified by",
        "the same enumeration that discovered the defect, reporting complete while the",
        "rendered output did not move.",
        "",
        head, sep,
    ]

    for label, source, path in ROWS:
        cells = []
        for _, view, mirror, runtime in present:
            src = {"view": view, "mirror": mirror, "runtime": runtime}[source]
            v = dig(src, path) if src else None
            cells.append("NO EVIDENCE" if v is None else str(v))
        out.append(f"| {label} | " + " | ".join(cells) + " |")

    # Render digests: "the observable did not change" as a checkable fact.
    out.append("| **render digest (sha256/16)** | "
               + " | ".join(f"`{render_digest(s[1])}`" for s in STATES
                            if any(c[0] == s[0] for c in present)) + " |")

    out += [
        "",
        "## Causal history, preserved",
        "",
        "The sequence is recorded as it happened rather than tidied. That STATE A and",
        "STATE B produced materially identical output is first-class evidence, not an",
        "embarrassment to smooth over: an unchanged observable after a repair claimed",
        "causal is evidence against the repair until something else explains it.",
        "",
        "| State | Dependency count by the resolver of the day | Closure flag | Observable |",
        "|---|---|---|---|",
        "| A — original mirror | 10 MDL, 20 textures (old walk) | `closure_complete: true` | hue-collapsed |",
        "| B — first repair | 30/30 fetched, same walk | `FULL_RENDER_CLOSURE: true` | **materially identical to A** |",
        "| C — corrected walk | 69 MDL, 252 textures | `FULL_RENDER_CLOSURE: true` | see matrix |",
        "",
        "**Evidence gap, stated plainly.** STATE B's rendered image was deleted during a",
        "pre-commit cleanup before this comparison was designed, so its pixel digest is",
        "unrecoverable — the intermediate mirror state no longer exists to re-render from.",
        "Its metrics survive in `camera_view_hospital_v1_repaired.json` and are identical",
        "to STATE A on background, floor, structure and forward depth. The",
        "\"unchanged observable\" claim therefore rests on metric identity, not pixel",
        "identity. Recorded rather than quietly downgraded.",
        "",
        "## Negative controls",
        "",
        "Two frames are retained permanently, and the validator must keep rejecting both",
        "**for different reasons** — a validator that rejects them for the same generic",
        "reason has lost the ability to tell the failure classes apart.",
        "",
        "| Fixture | Must fail on |",
        "|---|---|",
        "| `views/control_blocks_v1/pov_00.png` | background fraction — unbounded void |",
        "| `views/hospital_v1/pov_00.png` | dominant hue — material collapse |",
        "",
        "Author: Frank Asante Van Laarhoven",
    ]
    DST.write_text("\n".join(out) + "\n")
    print(f"  {DST.relative_to(REPO)}  ({len(present)} states x {len(ROWS)} metrics)")
    for label, view, mirror, runtime in present:
        have = [n for n, s in (("view", view), ("mirror", mirror), ("runtime", runtime)) if s]
        print(f"    {label:<26} sources: {', '.join(have) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
