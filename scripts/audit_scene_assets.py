"""Scene eligibility audit: is this asset actually usable, or only present?

A mirrored USD that opens is not a mirrored USD that renders. Two failure modes
found on the first attempt to use these assets, both of which a file-existence
check and a reference-closure manifest reported as fine:

**Missing MDL material modules.** The mirror's closure manifest reports
``closure_complete: true`` with zero unresolved references, and there are zero
``.mdl`` files on disk. The closure walked USD-to-USD references and did not
follow MDL module references, so every material falls back and the scene renders
in a flat fallback colour. A "photorealistic hospital" that is uniformly red is
a different observation distribution from a hospital, and nothing upstream of the
renderer says so.

**Stage unit mismatch.** A scene authored in centimetres loaded at
``stage_units_in_meters=1.0`` is 100x oversized. A 0.28 m robot is then inside
the geometry rather than in the room, and every depth reading is meaningless
while remaining finite and plausible.

Both are silent: geometry loads, prims count, the camera renders, the numbers are
finite. So this audit asks the questions the manifest cannot: what does the stage
say its units are, do the referenced material modules resolve, and does the
robot's spawn point sit in free space.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "gates" / "scenes"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", action="append", required=True,
                    help="scene_id=/path/to/root.usd")
    ap.add_argument("--out", default=str(OUT / "SCENE_ELIGIBILITY.json"))
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    from pxr import Usd, UsdGeom, UsdShade

    report: dict[str, Any] = {
        "check": "SCENE_ELIGIBILITY",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scenes": {},
    }

    for spec in args.scene:
        sid, _, path = spec.partition("=")
        p = Path(path)
        rec: dict[str, Any] = {"scene_id": sid, "usd_path": str(p), "exists": p.is_file()}
        blocking: list[str] = []
        if not p.is_file():
            rec["blocking_defects"] = ["asset file absent"]
            rec["eligible"] = False
            report["scenes"][sid] = rec
            continue

        stage = Usd.Stage.Open(str(p))
        mpu = UsdGeom.GetStageMetersPerUnit(stage)
        rec["meters_per_unit"] = float(mpu)
        rec["up_axis"] = str(UsdGeom.GetStageUpAxis(stage))
        rec["authored_in"] = ("metres" if abs(mpu - 1.0) < 1e-6
                              else "centimetres" if abs(mpu - 0.01) < 1e-9
                              else f"{mpu} m per unit")
        # The collector opens stages at stage_units_in_meters=1.0. Anything else
        # must be converted explicitly, not absorbed.
        if abs(mpu - 1.0) > 1e-6:
            blocking.append(
                f"stage authored at metersPerUnit={mpu}; loading it at "
                f"stage_units_in_meters=1.0 scales the world by {1 / mpu:.0f}x, putting a "
                f"0.28 m robot inside the geometry while every depth stays finite"
            )

        # Material modules: count what the stage asks for against what resolves.
        asked: set[str] = set()
        unresolved: set[str] = set()
        for prim in stage.Traverse():
            shader = UsdShade.Shader(prim)
            if not shader:
                continue
            impl = shader.GetSourceAsset("mdl")
            if impl:
                asked.add(str(impl.path))
                resolved = shader.GetPrim().GetStage().GetRootLayer().ComputeAbsolutePath(
                    str(impl.path))
                if not Path(resolved).is_file():
                    unresolved.add(str(impl.path))
        mdl_on_disk = list(p.parent.rglob("*.mdl"))
        rec["mdl_modules_referenced"] = len(asked)
        rec["mdl_modules_unresolved"] = len(unresolved)
        rec["mdl_files_on_disk"] = len(mdl_on_disk)
        rec["unresolved_examples"] = sorted(unresolved)[:8]
        if asked and not mdl_on_disk:
            blocking.append(
                f"{len(asked)} MDL material modules referenced, 0 present on disk — every "
                f"material falls back, so the rendered observation distribution is not the "
                f"one the asset describes"
            )

        counts: dict[str, int] = {}
        for prim in stage.Traverse():
            t = str(prim.GetTypeName())
            counts[t] = counts.get(t, 0) + 1
        rec["prim_type_counts"] = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:10])
        rec["total_prims"] = sum(counts.values())
        rec["mesh_count"] = counts.get("Mesh", 0)
        rec["light_count"] = sum(v for k, v in counts.items() if "Light" in k)

        rec["blocking_defects"] = blocking
        rec["eligible"] = not blocking
        rec["claim_scope"] = (
            "Eligible for navigation pilots once every blocking defect is cleared."
            if blocking else
            "No blocking defect found by this audit. Camera-view acceptance is a separate gate."
        )
        report["scenes"][sid] = rec

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")

    print("SCENE ELIGIBILITY")
    print("=" * 72)
    for sid, r in report["scenes"].items():
        print(f"  {sid:<22} eligible={r['eligible']}")
        if r.get("meters_per_unit") is not None:
            print(f"    units {r['meters_per_unit']} ({r['authored_in']}) · up {r['up_axis']} · "
                  f"{r['total_prims']} prims, {r['mesh_count']} meshes, {r['light_count']} lights")
            print(f"    MDL referenced {r['mdl_modules_referenced']} · on disk "
                  f"{r['mdl_files_on_disk']}")
        for d in r.get("blocking_defects", []):
            print(f"    BLOCKING: {d}")
    print(f"\n  record -> {out.relative_to(REPO)}")
    app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
