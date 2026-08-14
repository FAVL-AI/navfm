"""Is that darkness an empty world, or a window onto a distant one?

The acceptance gate used to ask "how many pixels have no useful depth?" and treat
the answer as void fraction. Those are different estimands. The canonical camera
clips at 100 m, so a legitimate view through an office window onto a city skyline
returns no depth and scored identically to the control world's unbounded black
nothing. Tightening the threshold from 0.35 to 0.10 fixed a false positive and
created a false negative, because:

    a bad observable + a better threshold = still a bad measurement

So the pixel classes are made explicit, and the rejection criterion moves onto the
one that actually means "empty world":

``NEAR_SCENE``
    geometry within the canonical camera's range.
``DISTANT_SCENE``
    no canonical depth return, but an independent probe finds real geometry along
    the same ray.
``VALID_ENVIRONMENT_BACKGROUND``
    an intentionally configured sky or dome accounts for the pixel.
``TRUE_VOID``
    no near geometry, no verified distant geometry, no environment background.

The independent-oracle rule from FL-018 applies directly: ``DISTANT_SCENE`` must
not be derived from the same 100 m depth buffer whose clipping caused the
ambiguity. A second camera is created at the *same world pose and the same
intrinsics*, differing only in far clip, which is set from the measured stage
bounds rather than picked. It is diagnostic-only -- never model input, never
written into Option 1.

Physics raycasts are deliberately not the authority here: a renderable prim need
not carry collision geometry, so a missed raycast would classify visible
architecture as void. Render-visible geometry is the question, so a render-based
probe answers it.

Every number leaves through a MeasurementEnvelope, so a run that loads no scene
reports NO_EVIDENCE rather than a tidy ``true_void_fraction`` of zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.measurement import Liveness, MeasurementEnvelope, not_run  # noqa: E402

OUT = REPO / "gates" / "scenes"
ROBOT_USD = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd"

#: Engineering thresholds, declared before the run. `true_void_fraction` replaces
#: the old raw background criterion; the value is carried over deliberately
#: unchanged so the fix cannot be confused with a loosening.
THRESHOLDS = {
    "true_void_fraction_max": 0.10,
    "structure_fraction_min": 0.15,
    "median_forward_depth_min_m": 1.5,
    "dominant_hue_fraction_max": 0.80,
    "distinct_colour_bins_min": 12,
    "note": (
        "true_void_fraction_max carries over the 0.10 previously applied to raw background. "
        "The observable changed; the threshold did not. Loosening it to admit a candidate "
        "would tune the gate to the scene rather than fix the measurement."
    ),
}

#: Cap on the diagnostic far clip, so a degenerate stage bound cannot produce an
#: absurd probe range. Declared, not silently applied.
DIAGNOSTIC_FAR_CAP_M = 20000.0


def digest_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:32]


#: Two environment colours for the differential sentinel pass. Far apart in every
#: channel so a pixel receiving environment light cannot render identically under
#: both, whatever the tonemapper does.
SENTINEL_A = (1.0, 0.0, 0.0)
SENTINEL_B = (0.0, 1.0, 0.0)
SENTINEL_MIN_DELTA = 12       # 8-bit levels, LDR fallback only
SENTINEL_MIN_REL_DELTA = 0.02  # HDR: 2% relative response, above renderer noise

#: LdrColor is uint8 and clips at 255, which destroys the differential exactly
#: where a bright sky lives -- a blown-out window would show zero delta under both
#: sentinels and be scored TRUE_VOID. HdrColor is float16 and retains the signal:
#: measured on a saturation fixture, 99.98% of the LDR frame sat at 255 while HDR
#: spanned 5.17 to 44.22 across those same pixels. So HDR is the oracle when the
#: renderer exposes it, and its absence is recorded rather than worked around.
PREFERRED_COLOUR_AOV = "HdrColor"


def classify(canon_depth: Any, probe_depth: Any, sentinel_a: Any, sentinel_b: Any, *,
             canon_far: float, hdr: bool = False,
             environment_exists: bool = True) -> dict[str, Any]:
    """Four-class split. Every class is earned by a positive observation.

    The precedence is strict, so no pixel can hold two classes:

    1. ``NEAR_SCENE``   geometry inside the canonical camera's range.
    2. ``DISTANT_SCENE`` the extended probe sees geometry the canonical camera
       clipped away.
    3. ``VALID_ENVIRONMENT_BACKGROUND`` the pixel *demonstrably responds* to the
       environment.
    4. ``TRUE_VOID``    nothing accounts for it.

    The third class used to be granted whenever the stage contained a DomeLight
    anywhere -- a scene-level fact standing in for a pixel-level claim, so adding
    a dome to an empty world would have laundered its void into a pass. It is now
    differential: the environment is rendered twice in two very different
    colours, and only pixels whose value *changes* are attributed to it. A void
    pixel is black under both and does not move. This distinguishes
    ``ENVIRONMENT_LIGHT_PRESENT`` from ``PIXEL_ENVIRONMENT_VISIBLE``, which are
    different facts: a dome can illuminate geometry without being the visible
    background for any particular ray.
    """
    import numpy as np

    c = np.asarray(canon_depth, dtype=np.float32)
    p = np.asarray(probe_depth, dtype=np.float32)
    total = int(c.size)

    near = np.isfinite(c) & (c > 0) & (c < canon_far)
    blind = ~near
    # The probe is consulted ONLY where the canonical camera returned nothing --
    # it is a second opinion about darkness, not a replacement depth source.
    distant = blind & np.isfinite(p) & (p > 0)
    unexplained = blind & ~distant

    if not environment_exists:
        # The stage contains no environment light at all, established by
        # traversal. There is nothing whose contribution could be measured, so
        # the environment class is positively ruled out and unexplained pixels
        # are void. This is NOT the same as a sentinel that failed to run:
        # "nothing to measure" is a determination, "could not measure" is
        # missing evidence. Conflating them turned the control world's genuine
        # 38.9% void into INDETERMINATE and weakened a negative control.
        env_bg = np.zeros_like(unexplained)
        unresolved = np.zeros_like(unexplained)
        delta_max = None
        mode = "no_environment_in_stage"
    elif sentinel_a is None or sentinel_b is None:
        # An environment exists but the differential did not execute. That is
        # missing evidence, not negative evidence: UNRESOLVED, never void.
        env_bg = np.zeros_like(unexplained)
        unresolved = unexplained.copy()
        delta_max = None
        mode = "NO_SENTINEL_EVIDENCE"
    else:
        a = np.asarray(sentinel_a, dtype=np.float32)[..., :3]
        b = np.asarray(sentinel_b, dtype=np.float32)[..., :3]
        if hdr:
            # Relative response: HDR is unbounded, so an absolute level would
            # mean different things in a dim corridor and a bright atrium.
            denom = np.maximum(np.maximum(np.abs(a), np.abs(b)).max(axis=-1), 1e-6)
            rel = np.abs(a - b).max(axis=-1) / denom
            env_bg = unexplained & (rel >= SENTINEL_MIN_REL_DELTA)
            # With HDR there is no clipping, so every unexplained pixel is
            # decidable and nothing is left unresolved on saturation grounds.
            unresolved = np.zeros_like(unexplained)
            delta_max = float(rel.max())
            mode = "differential_sentinel_hdr"
        else:
            delta = np.abs(a - b).max(axis=-1)
            env_bg = unexplained & (delta >= SENTINEL_MIN_DELTA)
            # LDR clips: a pixel saturated in BOTH passes cannot show a delta,
            # so its environment response is unobservable and it must not be
            # convicted of being void.
            sat = (a >= 254).all(axis=-1) & (b >= 254).all(axis=-1)
            unresolved = unexplained & ~env_bg & sat
            delta_max = float(delta.max())
            mode = "differential_sentinel_ldr"

    void = unexplained & ~env_bg & ~unresolved

    def frac(m: Any) -> float:
        return round(float(m.sum()) / total, 4)

    counts = {
        "near_scene_pixels": int(near.sum()),
        "distant_scene_pixels": int(distant.sum()),
        "valid_environment_background_pixels": int(env_bg.sum()),
        "true_void_pixels": int(void.sum()),
        "saturation_unresolved_pixels": int(unresolved.sum()),
    }
    # Exact integer accounting: a pixel the classifier forgot is a pixel it
    # cannot vouch for, so the shortfall is reported rather than absorbed.
    unclassified = total - sum(counts.values())
    return {
        "pixels_total": total,
        **counts,
        "unclassified_pixels": unclassified,
        "accounting_exact": unclassified == 0,
        "near_scene_fraction": frac(near),
        "distant_scene_fraction": frac(distant),
        "valid_environment_background_fraction": frac(env_bg),
        "true_void_fraction": frac(void),
        "raw_background_fraction": frac(blind),
        "saturation_unresolved_fraction": frac(unresolved),
        # Bound the quantity instead of forcing a point estimate. Unresolved
        # pixels could be either, so they widen the interval rather than being
        # silently assigned to whichever class is convenient.
        "void_lower_bound": frac(void),
        "void_upper_bound": round(float((void.sum() + unresolved.sum()) / total), 4),
        "sentinel_max_delta": delta_max,
        "sentinel_min_delta_required": SENTINEL_MIN_DELTA,
        "environment_attribution": mode,
        "_masks": {"near": near, "distant": distant, "env": env_bg, "void": void},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True, help="control, dome_launder, a USD path, or a URL")
    ap.add_argument("--scene-id", required=True)
    ap.add_argument("--pose", action="append", default=[],
                    help="x,y,yaw_deg[,label] -- repeatable; default is the origin pose")
    args = ap.parse_args()

    live = Liveness()
    envelopes: list[MeasurementEnvelope] = []
    record: dict[str, Any] = {
        "check": "SCENE_VISIBILITY_CLASSIFICATION",
        "scene_id": args.scene_id, "scene": args.scene,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "thresholds": THRESHOLDS,
        "independent_oracle": (
            "A second camera at the same world pose and intrinsics, differing only in far "
            "clip, set from measured stage bounds. DISTANT_SCENE is never derived from the "
            "canonical depth buffer whose clipping created the ambiguity (FL-018)."
        ),
        "diagnostic_only": "The probe is audit evidence. Never model input, never in Option 1.",
        "stage": "SIMULATION_DEVELOPMENT", "admission_status": "NOT_ADMITTED",
    }

    is_url = "://" in args.scene
    if args.scene not in ("control", "dome_launder") and not is_url and not Path(args.scene).is_file():
        print(f"REFUSED: no scene USD at {args.scene}", file=sys.stderr)
        envelopes.append(not_run("true_void_fraction", note=f"scene absent: {args.scene}"))
        _emit(record, envelopes, args.scene_id)
        return 2

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True, "renderer": "RaytracedLighting"})
    live = Liveness(process_started=True, runtime_started=True)

    try:
        import isaacsim.core.utils.stage as stage_utils
        import numpy as np
        import omni.replicator.core as rep
        from isaacsim.core.api import SimulationContext
        from PIL import Image
        from pxr import Gf, UsdGeom, UsdLux

        sim = SimulationContext(stage_units_in_meters=1.0)
        live = Liveness(**{**live.__dict__, "subject_open_attempted": True})

        if args.scene == "dome_launder":
            # The fixture that proves FL-021 is closed. A genuine unbounded void
            # PLUS a DomeLight: under the old scene-level rule every empty pixel
            # was forgiven because a dome existed somewhere. The dome here is
            # deliberately invisible to the camera -- zero intensity, so it
            # cannot be the visible background for any ray -- while remaining a
            # DomeLight the old test would have accepted.
            import omni.kit.commands
            from isaacsim.core.api.objects.ground_plane import GroundPlane
            from pxr import UsdLux as _UL

            GroundPlane(prim_path="/World/groundPlane", size=40.0)
            omni.kit.commands.execute("CreatePrim", prim_type="DistantLight",
                                      prim_path="/World/light")
            omni.kit.commands.execute("CreatePrim", prim_type="DomeLight",
                                      prim_path="/World/invisible_dome")
            dl = _UL.DomeLight(stage_utils.get_current_stage().GetPrimAtPath(
                "/World/invisible_dome"))
            dl.CreateIntensityAttr().Set(0.0)
        elif args.scene == "control":
            import omni.kit.commands
            from isaacsim.core.api.objects.ground_plane import GroundPlane

            GroundPlane(prim_path="/World/groundPlane", size=40.0)
            omni.kit.commands.execute("CreatePrim", prim_type="DistantLight",
                                      prim_path="/World/light")
            for i, (x, y) in enumerate([(2.0, 0.0), (3.5, 1.0), (3.0, -1.2)]):
                pth = f"/World/block_{i}"
                omni.kit.commands.execute("CreatePrim", prim_type="Cube", prim_path=pth)
                xf = UsdGeom.Xformable(stage_utils.get_current_stage().GetPrimAtPath(pth))
                xf.ClearXformOpOrder()
                xf.AddTranslateOp().Set(Gf.Vec3d(x, y, 0.35))
                xf.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.3, 0.3, 0.35))
        else:
            stage_utils.add_reference_to_stage(args.scene, "/World/Scene")

        stage_utils.add_reference_to_stage(str(ROBOT_USD), "/World/YahboomM3Pro")
        stage = stage_utils.get_current_stage()

        cam_path = "/World/YahboomM3Pro/camera_link/front_rgb_camera"
        cam_prim = stage.GetPrimAtPath(cam_path)
        if not cam_prim:
            envelopes.append(not_run("true_void_fraction", note="canonical camera prim absent"))
            _emit(record, envelopes, args.scene_id)
            app.close()
            return 2
        live = Liveness(**{**live.__dict__, "subject_open_succeeded": True})

        # -- measured stage bounds decide the diagnostic range ------------------
        lo = np.array([np.inf] * 3)
        hi = np.array([-np.inf] * 3)
        n_mesh = 0
        domes = []
        for prim in stage.Traverse():
            if UsdLux.DomeLight(prim):
                domes.append(UsdLux.DomeLight(prim))
        has_dome = bool(domes)
        for prim in stage.Traverse():
            if prim.GetTypeName() == "Mesh" and not str(prim.GetPath()).startswith(
                    "/World/YahboomM3Pro"):
                n_mesh += 1
                try:
                    b = UsdGeom.Boundable(prim).ComputeWorldBound(0, "default").GetBox()
                    mn, mx = b.GetMin(), b.GetMax()
                    lo = np.minimum(lo, [mn[0], mn[1], mn[2]])
                    hi = np.maximum(hi, [mx[0], mx[1], mx[2]])
                except Exception:
                    pass
        extent = float(np.linalg.norm(hi - lo)) if np.isfinite(lo).all() else 0.0
        diag_far = float(min(max(extent * 2.0, 1000.0), DIAGNOSTIC_FAR_CAP_M))
        record["stage"] = {
            "mesh_count": n_mesh, "has_environment_dome": has_dome,
            "bounds_min": [round(float(v), 2) for v in lo] if np.isfinite(lo).all() else None,
            "bounds_max": [round(float(v), 2) for v in hi] if np.isfinite(hi).all() else None,
            "diagonal_extent_m": round(extent, 2),
            "diagnostic_far_clip_m": diag_far,
            "diagnostic_far_rule": "2x measured stage diagonal, floor 1000 m, "
                                   f"cap {DIAGNOSTIC_FAR_CAP_M} m",
        }

        canon = UsdGeom.Camera(cam_prim)
        cr = canon.GetClippingRangeAttr().Get()
        canon_far = float(cr[1]) if cr else 100.0
        record["canonical_camera"] = {
            "prim": cam_path, "far_clip_m": canon_far,
            "focal_length_mm": float(canon.GetFocalLengthAttr().Get()),
            "horizontal_aperture_mm": float(canon.GetHorizontalApertureAttr().Get()),
        }

        # -- the independent probe: same pose, same intrinsics, extended range --
        probe_path = f"{cam_path}_diagnostic_probe"
        probe = UsdGeom.Camera.Define(stage, probe_path)
        probe.CreateFocalLengthAttr(canon.GetFocalLengthAttr().Get())
        probe.CreateHorizontalApertureAttr(canon.GetHorizontalApertureAttr().Get())
        probe.CreateVerticalApertureAttr(canon.GetVerticalApertureAttr().Get())
        probe.CreateClippingRangeAttr(Gf.Vec2f(0.05, diag_far))
        # Parented to the same link, zero local offset: identical pose by
        # construction rather than by copying a transform that could drift.
        pxf = UsdGeom.Xformable(probe.GetPrim())
        pxf.ClearXformOpOrder()
        pxf.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))
        pxf.AddRotateXYZOp().Set(Gf.Vec3d(90.0, 0.0, -90.0))

        rp_c = rep.create.render_product(cam_path, (320, 240))
        rp_p = rep.create.render_product(probe_path, (320, 240))
        available = set(rep.AnnotatorRegistry.get_registered_annotators())
        use_hdr = PREFERRED_COLOUR_AOV in available
        a_hdr = rep.AnnotatorRegistry.get_annotator(PREFERRED_COLOUR_AOV) if use_hdr else None
        a_rgb = rep.AnnotatorRegistry.get_annotator("rgb")
        a_dc = rep.AnnotatorRegistry.get_annotator("distance_to_camera")
        a_dp = rep.AnnotatorRegistry.get_annotator("distance_to_camera")
        a_rgb.attach(rp_c)
        if a_hdr is not None:
            a_hdr.attach(rp_c)
        record["colour_aov"] = {
            "preferred": PREFERRED_COLOUR_AOV,
            "available": sorted(n for n in available
                                if any(k in n.lower() for k in ("color", "hdr", "ldr"))),
            "using_hdr": use_hdr,
            "why": ("HdrColor is float16 and does not clip, so the environment differential "
                    "stays observable in a blown-out sky where LdrColor saturates at 255."
                    if use_hdr else
                    "HdrColor absent; falling back to LDR, where saturated pixels are "
                    "reported SATURATION_UNRESOLVED rather than convicted as void."),
        }
        a_dc.attach(rp_c)
        a_dp.attach(rp_p)

        sim.reset()
        for _ in range(40):
            sim.step(render=True)

        poses = args.pose or ["0,0,0,origin"]
        img_dir = OUT / "visibility" / args.scene_id
        img_dir.mkdir(parents=True, exist_ok=True)
        results = []
        robot = stage.GetPrimAtPath("/World/YahboomM3Pro")

        for i, spec in enumerate(poses):
            parts = spec.split(",")
            x, y, yaw = float(parts[0]), float(parts[1]), float(parts[2])
            label = parts[3] if len(parts) > 3 else f"pose_{i}"
            rxf = UsdGeom.Xformable(robot)
            rxf.ClearXformOpOrder()
            rxf.AddTranslateOp().Set(Gf.Vec3d(x, y, 0.05))
            rxf.AddRotateXYZOp().Set(Gf.Vec3d(0.0, 0.0, yaw))
            for _ in range(12):
                sim.step(render=True)

            rgb = np.asarray(a_rgb.get_data())
            dc = np.asarray(a_dc.get_data())
            dp = np.asarray(a_dp.get_data())
            if rgb.ndim == 3 and rgb.shape[2] == 4:
                rgb = rgb[:, :, :3]
            if dc.size == 0 or dp.size == 0:
                results.append({"pose": label, "status": "no frame"})
                continue

            # -- differential sentinel: the environment, twice, in two colours.
            # Only pixels whose value MOVES between them are receiving the
            # environment. A void pixel is black under both and does not move,
            # so a dome can no longer forgive a void merely by existing.
            sa = sb = None
            if domes:
                originals = [(d, d.GetColorAttr().Get(), d.GetIntensityAttr().Get(),
                              d.GetTextureFileAttr().Get()) for d in domes]
                try:
                    frames = []
                    for col in (SENTINEL_A, SENTINEL_B):
                        for d in domes:
                            # Colour ONLY. Intensity is preserved deliberately:
                            # an earlier version forced it to 3000 and thereby
                            # made an invisible dome visible, manufacturing the
                            # very contribution it was testing for. A dome that
                            # does not light the scene must stay dark in both
                            # passes so its pixels remain TRUE_VOID.
                            d.GetTextureFileAttr().Clear()
                            d.CreateColorAttr().Set(Gf.Vec3f(*col))
                        for _ in range(10):
                            sim.step(render=True)
                        src = a_hdr if a_hdr is not None else a_rgb
                        f = np.asarray(src.get_data())
                        frames.append(f[:, :, :3] if f.ndim == 3 and f.shape[2] == 4 else f)
                    sa, sb = frames
                finally:
                    # Restore before anything else reads the stage, so the
                    # diagnostic cannot leak into the canonical render.
                    for d, c0, i0, t0 in originals:
                        if c0 is not None:
                            d.CreateColorAttr().Set(c0)
                        if i0 is not None:
                            d.CreateIntensityAttr().Set(i0)
                        if t0 is not None:
                            d.CreateTextureFileAttr().Set(t0)
                    for _ in range(6):
                        sim.step(render=True)

            cls = classify(dc, dp, sa, sb, canon_far=canon_far, hdr=use_hdr,
                           environment_exists=bool(domes))
            masks = cls.pop("_masks")
            # Four-class label image for inspection: near / distant / env / void.
            lab = np.zeros((*masks["near"].shape, 3), dtype=np.uint8)
            lab[masks["near"]] = (40, 160, 40)
            lab[masks["distant"]] = (60, 90, 200)
            lab[masks["env"]] = (200, 170, 40)
            lab[masks["void"]] = (200, 40, 40)
            mp = img_dir / f"{label}_classes.png"
            Image.fromarray(lab).save(mp)
            ip = img_dir / f"{label}_pov.png"
            Image.fromarray(rgb.astype("uint8")).save(ip)

            cls.update(pose=label, x=x, y=y, yaw_deg=yaw,
                       class_mask=str(mp.relative_to(REPO)),
                       pov=str(ip.relative_to(REPO)),
                       pov_digest=digest_file(ip))
            results.append(cls)

        live = Liveness(**{**live.__dict__, "measurement_executed": True,
                           "artifact_written": True})
        record["poses"] = results

        measured = [r for r in results if "true_void_fraction" in r]
        if measured:
            worst = max(r["true_void_fraction"] for r in measured)
            envelopes.append(MeasurementEnvelope(
                measurement="true_void_fraction",
                liveness=live, value=worst,
                items_examined=sum(r["pixels_total"] for r in measured),
                expected_items=len(poses) * 320 * 240,
                evidence={"scene_id": args.scene_id,
                          "poses": [r["pose"] for r in measured],
                          "diagnostic_far_clip_m": diag_far},
                note="worst pose; a scene is only as good as its weakest audited viewpoint",
            ))
            envelopes.append(MeasurementEnvelope(
                measurement="distant_scene_fraction", liveness=live,
                value=max(r["distant_scene_fraction"] for r in measured),
                items_examined=sum(r["pixels_total"] for r in measured),
            ))
            lo = max(r["void_lower_bound"] for r in measured)
            hi = max(r["void_upper_bound"] for r in measured)
            t = THRESHOLDS["true_void_fraction_max"]
            # Bound the decision, do not force it. An interval straddling the
            # threshold is an honest INDETERMINATE, not a coin toss dressed as
            # a verdict.
            result = ("PASS" if hi <= t else "FAIL" if lo > t else "INDETERMINATE")
            record["verdict"] = {
                "void_lower_bound": lo, "void_upper_bound": hi,
                "true_void_fraction": worst, "threshold": t, "result": result,
                "rule": "PASS if upper<=t; FAIL if lower>t; else INDETERMINATE",
            }
        else:
            envelopes.append(not_run("true_void_fraction", note="no frame measured"))
            record["verdict"] = {"result": "NO_EVIDENCE"}

        _emit(record, envelopes, args.scene_id)
        print(f"\n  scene {args.scene_id}  meshes {n_mesh}  dome {has_dome}  "
              f"probe far {diag_far:.0f} m")
        for r in measured:
            print(f"    {r['pose']:<12} raw_bg {r['raw_background_fraction']:.3f}  "
                  f"near {r['near_scene_fraction']:.3f}  distant {r['distant_scene_fraction']:.3f}  "
                  f"env {r['valid_environment_background_fraction']:.3f}  "
                  f"TRUE_VOID {r['true_void_fraction']:.3f}")
        for e in envelopes:
            print(f"    {e.render()}")
        print(f"    VERDICT {record['verdict']['result']}")
        app.close()
        return 0 if record["verdict"]["result"] == "PASS" else 1
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        envelopes.append(not_run("true_void_fraction", note=record["error"][:200]))
        _emit(record, envelopes, args.scene_id)
        app.close()
        return 2


def _emit(record: dict[str, Any], envelopes: list[MeasurementEnvelope], scene_id: str) -> None:
    record["measurements"] = [e.to_json() for e in envelopes]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"scene_visibility_{scene_id}.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
