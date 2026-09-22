"""Read-only: why does the official Isaac hospital render too dark to present?

The demo's render gate failed on illumination after the material problem was
eliminated, and the useful question is which kind of failure it is. A scene
with no lights, a scene whose lights are switched off, a scene lit somewhere
other than where the camera stands, and a scene lit normally but rendered with
an exposure that hides it are four different problems with four different
fixes, and guessing between them by looking at a dark picture is how the wrong
one gets applied.

So this changes nothing. It composes the stage two ways -- referenced into a
new stage, as the demo does, and opened directly -- because that is the one
comparison that can show whether the demo's own loading choice is what dropped
the lighting. Every light is enumerated from the composed stage and classified
on its measured state rather than its name, since a prim called ceiling_light
that is deactivated illuminates nothing.

Emissive fixtures are counted separately from UsdLux lights on purpose. A
glowing ceiling panel in the frame looks like proof the scene is lit and is
not: emission is a material property, and whether it contributes to the camera
depends on the renderer.

No light is created, moved, enabled, disabled or retuned, no setting is
changed, and nothing is saved.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HOSPITAL_USD = (
    "https://omniverse-content-production.s3-us-west-2.amazonaws.com"
    "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
ROBOT_USD = (Path(__file__).resolve().parents[1]
             / "assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd")
CAMERA_PRIM = "/World/YahboomM3Pro/camera_link/front_rgb_camera"
BO10_START = (-39.90271172754076, 23.12059657138799, -1.3986055122719583)

LIGHT_TYPES = ("DomeLight", "RectLight", "SphereLight", "DiskLight",
               "DistantLight", "CylinderLight", "GeometryLight", "PortalLight")


def light_record(prim: Any, usd_lux: Any, usd_geom: Any) -> dict[str, Any]:
    """Everything that decides whether this light contributes. Measured, not named."""
    entry: dict[str, Any] = {
        "path": str(prim.GetPath()),
        "type": prim.GetTypeName(),
        "active": bool(prim.IsActive()),
        "loaded": bool(prim.IsLoaded()),
        "is_instance_proxy": bool(prim.IsInstanceProxy()),
    }

    imageable = usd_geom.Imageable(prim)
    with_visibility = imageable.ComputeVisibility() if imageable else None
    entry["computed_visibility"] = str(with_visibility) if with_visibility else None
    entry["purpose"] = str(imageable.ComputePurpose()) if imageable else None

    # An ancestor switched off silently removes a light that looks fine itself.
    inactive_ancestor = None
    parent = prim.GetParent()
    while parent and parent.GetPath() != parent.GetPath().GetParentPath():
        if not parent.IsActive():
            inactive_ancestor = str(parent.GetPath())
            break
        parent = parent.GetParent()
    entry["inactive_ancestor"] = inactive_ancestor

    light = usd_lux.LightAPI(prim) if hasattr(usd_lux, "LightAPI") else None
    for name, getter in (("intensity", "GetIntensityAttr"),
                         ("exposure", "GetExposureAttr"),
                         ("color", "GetColorAttr"),
                         ("enable_color_temperature",
                          "GetEnableColorTemperatureAttr"),
                         ("color_temperature", "GetColorTemperatureAttr"),
                         ("normalize", "GetNormalizeAttr")):
        value = None
        if light is not None and hasattr(light, getter):
            try:
                attribute = getattr(light, getter)()
                value = attribute.Get() if attribute else None
            except Exception:
                value = None
        if value is not None and hasattr(value, "__len__") and not isinstance(
                value, str):
            entry[name] = [float(component) for component in value]
        else:
            entry[name] = value

    texture = prim.GetAttribute("inputs:texture:file")
    entry["texture_file"] = str(texture.Get()) if texture and texture.Get() else None

    intensity = entry.get("intensity")
    exposure = entry.get("exposure") or 0.0
    effective = None
    if isinstance(intensity, (int, float)):
        effective = float(intensity) * (2.0 ** float(exposure))
    entry["effective_intensity"] = effective

    if not entry["active"]:
        classification = "PRESENT_BUT_INACTIVE"
    elif inactive_ancestor is not None:
        classification = "PRESENT_BUT_BLOCKED_BY_COMPOSITION"
    elif entry["computed_visibility"] == "invisible":
        classification = "PRESENT_BUT_HIDDEN"
    elif not entry["loaded"]:
        classification = "PRESENT_BUT_UNLOADED"
    elif effective is not None and effective <= 1e-6:
        classification = "PRESENT_BUT_ZERO_OR_NEAR_ZERO_OUTPUT"
    elif effective is None:
        classification = "UNKNOWN"
    else:
        classification = "PRESENT_AND_EFFECTIVE"
    entry["classification"] = classification
    return entry


def inspect_stage(stage: Any, usd_lux: Any, usd_geom: Any,
                  usd: Any) -> dict[str, Any]:
    lights: list[dict[str, Any]] = []
    emissive_materials = 0
    fixture_like = 0
    prim_count = 0

    for prim in stage.TraverseAll():
        prim_count += 1
        type_name = str(prim.GetTypeName())
        if type_name in LIGHT_TYPES or type_name.endswith("Light"):
            lights.append(light_record(prim, usd_lux, usd_geom))
        name = prim.GetName().lower()
        if any(token in name for token in ("light", "lamp", "luminaire")):
            fixture_like += 1
        for attribute in prim.GetAttributes():
            attr_name = attribute.GetName()
            if "emissive" in attr_name.lower() or "emission" in attr_name.lower():
                emissive_materials += 1
                break

    layers = stage.GetRootLayer().subLayerPaths
    default_prim = stage.GetDefaultPrim()

    references: list[str] = []
    payloads_unloaded = 0
    for prim in stage.TraverseAll():
        if prim.HasAuthoredReferences():
            references.append(str(prim.GetPath()))
        if prim.HasAuthoredPayloads() and not prim.IsLoaded():
            payloads_unloaded += 1

    return {
        "root_layer": stage.GetRootLayer().identifier,
        "sublayers": list(layers),
        "default_prim": str(default_prim.GetPath()) if default_prim else None,
        "up_axis": str(usd_geom.GetStageUpAxis(stage)),
        "metres_per_unit": float(usd_geom.GetStageMetersPerUnit(stage)),
        "total_prims": prim_count,
        "prims_with_authored_references": len(references),
        "reference_sample": references[:8],
        "payloads_present_but_unloaded": payloads_unloaded,
        "USDLUX_LIGHT_COUNT": len(lights),
        "light_count_by_type": {
            t: sum(1 for entry in lights if entry["type"] == t)
            for t in sorted({str(entry["type"]) for entry in lights})},
        "lights": lights,
        "classification_tally": {
            c: sum(1 for entry in lights if entry["classification"] == c)
            for c in sorted({str(entry["classification"]) for entry in lights})},
        "LIGHT_FIXTURE_GEOMETRY_PRESENT": fixture_like > 0,
        "fixture_like_prim_count": fixture_like,
        "EMISSIVE_MATERIAL_PRESENT": emissive_materials > 0,
        "prims_with_emissive_attribute": emissive_materials,
        "usd_version": getattr(usd, "GetVersion", lambda: "unknown")(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(Path.home() / "navfm-demo"))
    ap.add_argument("--warmup", type=int, default=200)
    args = ap.parse_args()

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) / f"illumination_inspection_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True, "renderer": "RaytracedLighting"})

    import carb
    import numpy as np
    import omni.replicator.core as rep
    from isaacsim.core.api import SimulationContext
    from isaacsim.core.utils import stage as stage_utils
    from PIL import Image as PILImage
    from pxr import Gf, Usd, UsdGeom, UsdLux

    report: dict[str, Any] = {
        "check": "HOSPITAL_ILLUMINATION_INSPECTION",
        "READ_ONLY": True,
        "changes_made": "none: no light created, moved, enabled, disabled or "
                        "retuned; no setting altered; no stage saved",
        "observed_at": datetime.now(UTC).isoformat(),
        "hospital_usd": HOSPITAL_USD,
        "camera_prim": CAMERA_PRIM,
        "SCIENTIFIC_ARM_A_N": 0,
        "ARM_A_ATTEMPT_003": "NOT_STARTED",
        "ARM_B": "NOT_STARTED",
        "PRODUCTION_M3PRO_USD": "NOT_GENERATED",
    }

    # (a) The demo's own loading path: referenced into a new stage.
    stage_utils.create_new_stage()
    sim = SimulationContext(physics_dt=1.0 / 60.0, rendering_dt=1.0 / 60.0,
                            stage_units_in_meters=1.0)
    stage_utils.add_reference_to_stage(HOSPITAL_USD, "/World/Scene")
    sim.initialize_physics()
    sim.play()
    for _ in range(args.warmup):
        sim.step(render=True)
    referenced = inspect_stage(stage_utils.get_current_stage(),
                               UsdLux, UsdGeom, Usd)
    report["COMPOSITION_REFERENCED_INTO_NEW_STAGE"] = referenced

    # Camera diagnostics from the BO-10 start pose, stationary, no policy.
    stage_utils.add_reference_to_stage(str(ROBOT_USD), "/World/YahboomM3Pro")
    for _ in range(20):
        sim.step(render=True)
    prim = stage_utils.get_current_stage().GetPrimAtPath("/World/YahboomM3Pro")
    xform = UsdGeom.Xformable(prim)
    xform.ClearXformOpOrder()
    xform.AddTranslateOp().Set(Gf.Vec3d(BO10_START[0], BO10_START[1], 0.0))
    xform.AddRotateZOp().Set(float(np.degrees(BO10_START[2])))

    render_product = rep.create.render_product(CAMERA_PRIM, (320, 240))
    annotator = rep.AnnotatorRegistry.get_annotator("rgb")
    annotator.attach([render_product])
    for _ in range(args.warmup):
        sim.step(render=True)

    frame = np.asarray(annotator.get_data())[..., :3].copy()
    PILImage.fromarray(frame).save(out / "stationary_frame.png")
    luminance = np.asarray(frame, dtype=np.float64).mean(axis=2)
    report["LUMINANCE_DIAGNOSTICS"] = {
        "frame": "stationary_frame.png",
        "resolution": [int(frame.shape[1]), int(frame.shape[0])],
        "mean": round(float(luminance.mean()), 3),
        "median": round(float(np.median(luminance)), 3),
        "p5": round(float(np.percentile(luminance, 5)), 3),
        "p50": round(float(np.percentile(luminance, 50)), 3),
        "p95": round(float(np.percentile(luminance, 95)), 3),
        "max": round(float(luminance.max()), 3),
        "percent_near_black": round(
            float((luminance < 5.0).mean() * 100.0), 2),
        "percent_saturated": round(
            float((luminance > 250.0).mean() * 100.0), 2),
        "warmup_frames": args.warmup,
        "note": "engineering diagnostics, not scientific metrics",
    }

    # Renderer and exposure state, read and not touched.
    settings = carb.settings.get_settings()
    keys = [
        "/rtx/rendermode", "/rtx/pathtracing/spp",
        "/rtx/post/tonemap/op", "/rtx/post/tonemap/cameraShutter",
        "/rtx/post/tonemap/fNumber", "/rtx/post/tonemap/isoSubjectValue",
        "/rtx/post/histogram/enabled", "/rtx/sceneDb/ambientLightIntensity",
        "/rtx/useViewLightingMode", "/rtx/directLighting/enabled",
        "/rtx/indirectDiffuse/enabled", "/rtx/domeLight/upperLowerStrategy",
        "/app/renderer/resolution/width",
    ]
    report["RENDER_SETTINGS"] = {
        "requested_renderer": "RaytracedLighting (SimulationApp argument)",
        "settings": {k: settings.get(k) for k in keys},
        "note": "read only; nothing tuned",
    }

    # (b) The same layer opened directly, to see whether the demo's reference
    # loading is itself what dropped the lighting.
    stage_utils.open_stage(HOSPITAL_USD)
    for _ in range(60):
        sim.step(render=True)
    opened = inspect_stage(stage_utils.get_current_stage(), UsdLux, UsdGeom, Usd)
    report["COMPOSITION_OPENED_DIRECTLY"] = opened

    referenced_lights = referenced["USDLUX_LIGHT_COUNT"]
    opened_lights = opened["USDLUX_LIGHT_COUNT"]
    effective_referenced = referenced["classification_tally"].get(
        "PRESENT_AND_EFFECTIVE", 0)
    report["LOADING_PATH_COMPARISON"] = {
        "lights_when_referenced": referenced_lights,
        "lights_when_opened": opened_lights,
        "reference_loading_drops_lights": bool(opened_lights > referenced_lights),
        "reading": (
            "if the two counts differ, the demo's own loading choice is part of "
            "the problem. If they agree, the asset is the same either way and "
            "the cause lies in the lights themselves or in the renderer"),
    }

    # An effective light is not the same as interior illumination. A DomeLight
    # lights the sky and a building shell blocks it; a SphereLight parented to a
    # vending machine lights a vending machine. Counting effective lights and
    # calling the result "usable interior lighting" was the first version of
    # this verdict, and it was wrong in the permissive direction, so the
    # classification is by role rather than by count.
    effective_lights = [entry for entry in referenced["lights"]
                        if entry["classification"] == "PRESENT_AND_EFFECTIVE"]
    environment = [e for e in effective_lights if e["type"] == "DomeLight"]
    interior = [e for e in effective_lights
                if e["type"] != "DomeLight" and "/World/Scene/BP_" not in e["path"]]
    prop_attached = [e for e in effective_lights
                     if "/World/Scene/BP_" in e["path"]]

    if referenced_lights == 0:
        root_cause = "A_NO_USDLUX_LIGHTS_IN_COMPOSED_STAGE"
    elif effective_referenced == 0:
        root_cause = "B_LIGHTS_EXIST_BUT_ARE_INACTIVE_OR_HIDDEN"
    elif not interior and (environment or prop_attached):
        root_cause = "E_LIGHTS_EXIST_OUTSIDE_THE_RELEVANT_HOSPITAL_REGION"
    else:
        root_cause = "UNRESOLVED_REQUIRES_FURTHER_EVIDENCE"

    report["ILLUMINATION_ROOT_CAUSE"] = root_cause
    report["LIGHT_ROLES"] = {
        "environment_dome": [e["path"] for e in environment],
        "prop_attached": [e["path"] for e in prop_attached],
        "interior_area_or_room": [e["path"] for e in interior],
    }
    report["root_cause_basis"] = (
        f"{referenced_lights} UsdLux light(s), {effective_referenced} effective: "
        f"{len(environment)} environment dome, {len(prop_attached)} parented to "
        f"props, {len(interior)} lighting the interior. A dome is occluded by the "
        "building shell and a light inside a vending machine lights a vending "
        "machine")
    report["HOSPITAL_SHIPS_USABLE_INTERIOR_LIGHTS"] = bool(interior)
    report["verdict_corrected"] = (
        "an earlier version of this verdict counted effective lights and would "
        "have reported usable interior lighting on the strength of a dome and "
        "four vending-machine lights. Role, not count")

    (out / "light_inventory.json").write_text(json.dumps(
        {"referenced": referenced["lights"], "opened": opened["lights"]},
        indent=2))
    (out / "stage_composition.json").write_text(json.dumps(
        {"referenced": {k: v for k, v in referenced.items() if k != "lights"},
         "opened": {k: v for k, v in opened.items() if k != "lights"}}, indent=2))
    (out / "render_settings.json").write_text(
        json.dumps(report["RENDER_SETTINGS"], indent=2))
    (out / "luminance_diagnostics.json").write_text(
        json.dumps(report["LUMINANCE_DIAGNOSTICS"], indent=2))
    (out / "inspection_report.json").write_text(json.dumps(report, indent=2))

    print("=" * 74)
    print("HOSPITAL ILLUMINATION INSPECTION -- READ ONLY")
    print("=" * 74)
    print(f"  referenced stage: {referenced['total_prims']} prims, "
          f"{referenced_lights} UsdLux lights")
    print(f"  opened stage:     {opened['total_prims']} prims, "
          f"{opened_lights} UsdLux lights")
    print(f"  by type:          {referenced['light_count_by_type']}")
    print(f"  classification:   {referenced['classification_tally']}")
    print(f"  fixtures by name: {referenced['fixture_like_prim_count']}  "
          f"emissive attrs: {referenced['prims_with_emissive_attribute']}")
    lum = report["LUMINANCE_DIAGNOSTICS"]
    print(f"  luminance:        mean {lum['mean']}  median {lum['median']}  "
          f"p95 {lum['p95']}  max {lum['max']}")
    print(f"                    near-black {lum['percent_near_black']}%  "
          f"saturated {lum['percent_saturated']}%")
    roles = report["LIGHT_ROLES"]
    print(f"  roles:            {len(roles['environment_dome'])} dome, "
          f"{len(roles['prop_attached'])} prop-attached, "
          f"{len(roles['interior_area_or_room'])} interior")
    print(f"  ROOT CAUSE:       {root_cause}")
    print(f"  ships usable interior lights: "
          f"{report['HOSPITAL_SHIPS_USABLE_INTERIOR_LIGHTS']}")
    print(f"  output:           {out}")

    app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
