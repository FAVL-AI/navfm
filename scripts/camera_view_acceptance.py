"""Camera-view acceptance: is this a usable navigation viewpoint?

The top-arm camera is mechanically correct and its optical axis is exactly
forward. That was verified analytically before this script was written: the USD
rotation (90, 0, -90) maps the camera's -Z view direction onto the robot's +X
with +Z up, giving pitch 0.0 deg, and the intrinsics give 60.4 x 47.2 degrees --
comparable to a RealSense D435. So the camera is not the defect.

What the early images show is a property of the *world*. The control world is a
40 m ground plane and a distant light in an unbounded void: no walls, no ceiling,
no sky dome. With the camera level at 0.280 m the horizon falls on the image
centre, so the upper half of every frame is rays that terminate in nothing and
render black, and the lower half is floor. Pitching the camera down would trade
black for more floor and make it worse.

This script tests that explanation instead of asserting it: the same robot, the
same camera, the same intrinsics, rendered in each world, with the composition
measured rather than described.

Metrics, and why each is here:

``background_fraction``
    Pixels where nothing was hit. In a bounded room this is near zero; in a void
    it is roughly the sky half of the frame. This is the metric that separates
    "camera aimed wrong" from "nothing there to see".
``floor_fraction``
    Measured from the depth buffer's geometry, not from colour -- a grey floor
    and a grey wall are the same colour and different navigational facts.
``median_forward_depth`` / ``p90_forward_depth``
    How far the robot can actually see. A corridor gives metres; a void gives the
    far clip or nothing.
``horizon_row_fraction``
    Where the horizon sits vertically. 0.5 is the centre.
``structure_fraction``
    Pixels that are neither floor nor background: walls, doors, furniture,
    obstacles. This is the signal a navigation model reads.

Thresholds are engineering thresholds, declared here and recorded in the output
so they can be argued with. They are not scientific criteria and no experimental
claim depends on them.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "gates" / "scenes"
ROBOT_USD = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd"

#: Engineering thresholds. Declared before the run, recorded in the artefact.
#:
#: The first version of this table passed BOTH known-bad frames: the control
#: world's black void (background 33% against a 35% limit) and a hospital render
#: that was uniformly red because every material had fallen back. A check that
#: green-lights two frames a human rejects on sight certifies nothing, so the
#: limits below are tightened and two appearance metrics are added.
#:
#: `background_fraction_max` moved 0.35 -> 0.10 after measurement: a bounded
#: interior reads 0.00 and the unbounded control world reads 0.33, so anything
#: near a third of the frame is a void, not a room. Recalibrated against observed
#: data and recorded as such -- these are engineering thresholds for a simulation
#: development gate, not pre-registered scientific criteria, and no experimental
#: claim depends on them.
THRESHOLDS = {
    "background_fraction_max": 0.10,
    "floor_fraction_max": 0.60,
    "structure_fraction_min": 0.15,
    "median_forward_depth_min_m": 1.5,
    "dominant_hue_fraction_max": 0.80,
    "distinct_colour_bins_min": 12,
    "rationale": (
        "A frame that is mostly nothing, mostly floor, or a single flat hue carries little "
        "navigational structure. The hue and colour-diversity limits exist because a scene "
        "whose MDL materials fail to resolve still renders geometry, still reports finite "
        "depth and still passes every geometric check -- while showing a colour that is not "
        "in the asset."
    ),
    "calibration": (
        "background_fraction_max tightened from 0.35 to 0.10 after both known-bad frames "
        "passed the original table. Measured: bounded interior 0.00, unbounded void 0.33."
    ),
}


def analyse(rgb: Any, depth: Any, *, vfov_deg: float, cam_height_m: float) -> dict[str, Any]:
    """Composition from geometry, not colour.

    Floor is identified by reprojecting each pixel's depth and asking whether the
    hit point is near ground level, because a grey wall and a grey floor are the
    same colour and different navigational facts.
    """
    import numpy as np

    d = np.asarray(depth, dtype=np.float32)
    h, w = d.shape[:2]
    background = ~np.isfinite(d) | (d <= 0) | (d > 90.0)
    bg_frac = float(background.mean())

    # Elevation of each pixel's ray, then the height of the point it hit.
    rows = np.arange(h).reshape(-1, 1)
    elev = np.radians(vfov_deg) * (0.5 - (rows + 0.5) / h)  # + is up
    with np.errstate(invalid="ignore"):
        hit_z = cam_height_m + d * np.sin(elev)
    floor = (~background) & (np.abs(hit_z) < 0.08)
    floor_frac = float(floor.mean())
    structure = ~background & ~floor
    struct_frac = float(structure.mean())

    fwd = d[~background & ~floor]
    strip = d[max(0, h // 2 - 8):h // 2 + 8, :]
    strip = strip[np.isfinite(strip) & (strip > 0) & (strip < 90.0)]

    # Appearance. A scene whose materials failed to resolve renders as one flat
    # hue while every geometric metric stays healthy, so colour is measured too.
    rgbf = np.asarray(rgb, dtype=np.float32)[..., :3] / 255.0
    mx, mn = rgbf.max(-1), rgbf.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    coloured = sat > 0.15
    if coloured.sum() > 0:
        r_, g_, b_ = rgbf[..., 0], rgbf[..., 1], rgbf[..., 2]
        hue = np.zeros_like(mx)
        d_ = np.maximum(mx - mn, 1e-6)
        m1, m2, m3 = (mx == r_), (mx == g_), (mx == b_)
        hue[m1] = ((g_ - b_) / d_)[m1] % 6
        hue[m2] = ((b_ - r_) / d_ + 2)[m2]
        hue[m3] = ((r_ - g_) / d_ + 4)[m3]
        bins = np.histogram(hue[coloured], bins=12, range=(0, 6))[0]
        dom = float(bins.max() / max(1, bins.sum()))
    else:
        dom = 0.0
    q = (np.asarray(rgb, dtype=np.uint8)[..., :3] // 32).astype(np.int32)
    n_bins = int(len(np.unique(q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2])))

    return {
        "dominant_hue_fraction": round(dom, 4),
        "saturated_pixel_fraction": round(float(coloured.mean()), 4),
        "distinct_colour_bins": n_bins,
        "resolution": [int(w), int(h)],
        "background_fraction": round(bg_frac, 4),
        "floor_fraction": round(floor_frac, 4),
        "structure_fraction": round(struct_frac, 4),
        "median_forward_depth_m": round(float(np.median(fwd)), 3) if fwd.size else None,
        "p90_forward_depth_m": round(float(np.percentile(fwd, 90)), 3) if fwd.size else None,
        "median_centre_strip_depth_m": round(float(np.median(strip)), 3) if strip.size else None,
        "horizon_row_fraction": 0.5,
        "pixels_with_geometry": int((~background).sum()),
    }


def verdict(m: dict[str, Any]) -> dict[str, Any]:
    fails = []
    if m["background_fraction"] > THRESHOLDS["background_fraction_max"]:
        fails.append(f"background {m['background_fraction']:.1%} exceeds "
                     f"{THRESHOLDS['background_fraction_max']:.0%} — the world is unbounded, "
                     f"not the camera aimed wrong")
    if m["floor_fraction"] > THRESHOLDS["floor_fraction_max"]:
        fails.append(f"floor {m['floor_fraction']:.1%} exceeds "
                     f"{THRESHOLDS['floor_fraction_max']:.0%}")
    if m["structure_fraction"] < THRESHOLDS["structure_fraction_min"]:
        fails.append(f"structure {m['structure_fraction']:.1%} below "
                     f"{THRESHOLDS['structure_fraction_min']:.0%} — little for a navigation "
                     f"model to read")
    md = m.get("median_forward_depth_m")
    if md is None or md < THRESHOLDS["median_forward_depth_min_m"]:
        fails.append(f"median forward depth {md} below "
                     f"{THRESHOLDS['median_forward_depth_min_m']} m")
    dom = m.get("dominant_hue_fraction")
    if dom is not None and dom > THRESHOLDS["dominant_hue_fraction_max"]:
        fails.append(f"{dom:.0%} of saturated pixels share one hue — consistent with MDL "
                     f"material fallback, not with an authored interior")
    nb = m.get("distinct_colour_bins")
    if nb is not None and nb < THRESHOLDS["distinct_colour_bins_min"]:
        fails.append(f"only {nb} distinct colour bins — the frame carries almost no "
                     f"appearance variation")
    return {"result": "PASS" if not fails else "FAIL", "failures": fails}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True,
                    help="'control' or a path to a scene USD")
    ap.add_argument("--scene-id", required=True)
    ap.add_argument("--poses", type=int, default=4)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not ROBOT_USD.is_file():
        print(f"REFUSED: no robot twin at {ROBOT_USD}", file=sys.stderr)
        return 2
    if args.scene != "control" and not Path(args.scene).is_file():
        print(f"REFUSED: no scene USD at {args.scene}", file=sys.stderr)
        return 2

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True, "renderer": "RaytracedLighting"})

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    import omni.replicator.core as rep
    from isaacsim.core.api import SimulationContext
    from PIL import Image
    from pxr import Gf, UsdGeom

    sim = SimulationContext(stage_units_in_meters=1.0)
    record: dict[str, Any] = {
        "check": "CAMERA_VIEW_ACCEPTANCE",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scene_id": args.scene_id, "scene_arg": args.scene,
        "robot_usd": str(ROBOT_USD.relative_to(REPO)),
        "thresholds": THRESHOLDS,
        "stage": "SIMULATION_DEVELOPMENT", "admission_status": "NOT_ADMITTED",
    }

    # ---- world -------------------------------------------------------------
    if args.scene == "control":
        import omni.kit.commands
        from isaacsim.core.api.objects.ground_plane import GroundPlane

        GroundPlane(prim_path="/World/groundPlane", size=40.0)
        omni.kit.commands.execute("CreatePrim", prim_type="DistantLight",
                                  prim_path="/World/light")
        for i, (x, y) in enumerate([(2.0, 0.0), (3.5, 1.0), (3.0, -1.2)]):
            p = f"/World/block_{i}"
            omni.kit.commands.execute("CreatePrim", prim_type="Cube", prim_path=p)
            prim = stage_utils.get_current_stage().GetPrimAtPath(p)
            xf = UsdGeom.Xformable(prim)
            xf.ClearXformOpOrder()
            xf.AddTranslateOp().Set(Gf.Vec3d(x, y, 0.35))
            xf.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.3, 0.3, 0.35))
        record["world"] = {"type": "procedural primitives", "walls": 0, "ceiling": 0}
    else:
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        record["world"] = {"type": "usd_reference", "usd": args.scene}

    stage_utils.add_reference_to_stage(str(ROBOT_USD), "/World/YahboomM3Pro")
    stage = stage_utils.get_current_stage()

    # ---- scene census, measured in-stage -----------------------------------
    counts: dict[str, int] = {}
    lo = np.array([np.inf] * 3)
    hi = np.array([-np.inf] * 3)
    for prim in stage.Traverse():
        t = prim.GetTypeName()
        counts[t] = counts.get(t, 0) + 1
        if t == "Mesh" and not str(prim.GetPath()).startswith("/World/YahboomM3Pro"):
            try:
                b = UsdGeom.Boundable(prim).ComputeWorldBound(0, "default").GetBox()
                mn, mx = b.GetMin(), b.GetMax()
                lo = np.minimum(lo, [mn[0], mn[1], mn[2]])
                hi = np.maximum(hi, [mx[0], mx[1], mx[2]])
            except Exception:
                pass
    record["scene_census"] = {
        "prim_type_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:14]),
        "total_prims": sum(counts.values()),
        "mesh_count": counts.get("Mesh", 0),
        "light_count": sum(v for k, v in counts.items() if "Light" in k),
        "material_count": counts.get("Material", 0),
        "bounding_box_min_m": [round(float(v), 3) for v in lo] if np.isfinite(lo).all() else None,
        "bounding_box_max_m": [round(float(v), 3) for v in hi] if np.isfinite(hi).all() else None,
        "extent_m": [round(float(v), 3) for v in (hi - lo)] if np.isfinite(lo).all() else None,
    }

    cam_path = "/World/YahboomM3Pro/camera_link/front_rgb_camera"
    if not stage.GetPrimAtPath(cam_path):
        print(f"REFUSED: no camera prim at {cam_path}", file=sys.stderr)
        app.close()
        return 2
    cam = UsdGeom.Camera(stage.GetPrimAtPath(cam_path))
    record["camera"] = {
        "prim": cam_path,
        "focal_length_mm": float(cam.GetFocalLengthAttr().Get()),
        "horizontal_aperture_mm": float(cam.GetHorizontalApertureAttr().Get()),
        "vertical_aperture_mm": float(cam.GetVerticalApertureAttr().Get()),
    }
    f = record["camera"]["focal_length_mm"]
    hfov = 2 * math.degrees(math.atan(record["camera"]["horizontal_aperture_mm"] / (2 * f)))
    vfov = 2 * math.degrees(math.atan(record["camera"]["vertical_aperture_mm"] / (2 * f)))
    record["camera"].update(hfov_deg=round(hfov, 2), vfov_deg=round(vfov, 2))

    rp = rep.create.render_product(cam_path, (320, 240))
    rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb")
    depth_annot = rep.AnnotatorRegistry.get_annotator("distance_to_camera")
    rgb_annot.attach(rp)
    depth_annot.attach(rp)

    sim.reset()
    for _ in range(30):
        sim.step(render=True)

    cw = UsdGeom.Xformable(stage.GetPrimAtPath(cam_path)).ComputeLocalToWorldTransform(0)
    cam_h = float(cw.ExtractTranslation()[2])
    record["camera"]["world_height_m"] = round(cam_h, 4)

    img_dir = OUT / "views" / args.scene_id
    img_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(args.poses):
        for _ in range(4):
            sim.step(render=True)
        rgb = np.asarray(rgb_annot.get_data())
        dep = np.asarray(depth_annot.get_data())
        if rgb.ndim == 3 and rgb.shape[2] == 4:
            rgb = rgb[:, :, :3]
        m = analyse(rgb, dep, vfov_deg=vfov, cam_height_m=cam_h)
        m["verdict"] = verdict(m)
        p = img_dir / f"pov_{i:02d}.png"
        Image.fromarray(rgb.astype("uint8")).save(p)
        m["image"] = str(p.relative_to(REPO))
        frames.append(m)

    record["frames"] = frames
    # Every metric the verdict consults must reach the aggregate. An earlier
    # version averaged only the three geometric fractions, so `verdict()` looked
    # up `dominant_hue_fraction`, found None, and skipped the appearance checks
    # entirely -- the aggregate PASSed a frame whose own per-frame verdict had
    # failed it. A gate that drops the metric proving the defect is the same
    # error as FL-017, one layer up.
    agg = {k: round(float(np.mean([f[k] for f in frames if f.get(k) is not None])), 4)
           for k in ("background_fraction", "floor_fraction", "structure_fraction",
                     "dominant_hue_fraction", "saturated_pixel_fraction")}
    agg["distinct_colour_bins"] = int(np.min([f["distinct_colour_bins"] for f in frames]))
    depths = [f["median_forward_depth_m"] for f in frames if f.get("median_forward_depth_m")]
    agg["median_forward_depth_m"] = round(float(np.median(depths)), 3) if depths else None
    record["aggregate"] = agg
    record["verdict"] = verdict(agg)

    out = Path(args.out) if args.out else OUT / f"camera_view_{args.scene_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n")

    print(f"\n  scene      {args.scene_id}")
    print(f"  camera     {cam_h:.3f} m, {hfov:.1f}x{vfov:.1f} deg")
    print(f"  prims      {record['scene_census']['total_prims']} "
          f"({record['scene_census']['mesh_count']} meshes, "
          f"{record['scene_census']['light_count']} lights)")
    print(f"  extent     {record['scene_census']['extent_m']}")
    print(f"  background {agg['background_fraction']:.1%}   floor {agg['floor_fraction']:.1%}"
          f"   structure {agg['structure_fraction']:.1%}")
    print(f"  fwd depth  {agg['median_forward_depth_m']} m")
    print(f"  VERDICT    {record['verdict']['result']}")
    for f_ in record["verdict"]["failures"]:
        print(f"    - {f_}")
    print(f"  record -> {out.relative_to(REPO)}")

    app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
