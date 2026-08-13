"""Scene identity and provenance, so an image can be traced back to its world.

Camera geometry and scene identity are part of the data-generating process. If
either changes, the observation distribution changes -- so both must be versioned
and traceable exactly like a checkpoint or a dataset. The camera-height
experiment already demonstrated the first half empirically: same start, goal,
seed, policy and physics, camera the only change, and `pilot_0002` yaw moved from
+8.8 deg to +37.9 deg. This file makes the world equally traceable.

Two tiers, kept separate on purpose:

``ENGINEERING_CONTROL_WORLD``
    A ground plane, a distant light and a few primitives. Simple geometry
    exposes controller defects that a cluttered scene hides, so this is the
    right environment for physics, action-scale, camera-transform and loader
    regression. It is **not** a navigation environment and must never be
    described as an office or a warehouse.

``NAVIGATION_EXPERIMENT_WORLD``
    A real Isaac USD environment with walls, doors, furniture, occlusion and
    authored lighting. This is where visual-navigation pilots are collected.

Provenance is read from the mirrors' closure manifests rather than asserted:
each records its upstream URL, every referenced file with a digest, and whether
the reference closure reached a fixed point with nothing unresolved. A scene
whose closure is incomplete is not eligible, because a missing reference renders
as absent geometry rather than as an error.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "gates" / "scenes"
MIRROR = Path.home() / "robotics" / "FleetSafe-VLA" / "assets" / "mirror"

ISAAC_VERSION = "5.1.0.0"

#: Camera intrinsics, from the twin builder. Recorded here because the scene and
#: the camera together define the observation distribution; neither alone does.
CAMERA = {
    "mount": "top_arm",
    "viewpoint": "forward_egocentric",
    "height_above_ground_m": 0.280,
    "height_above_base_link_m": 0.240,
    "forward_offset_from_base_origin_m": 0.100,
    "optical_axis_robot_frame": [1.0, 0.0, 0.0],
    "up_axis_robot_frame": [0.0, 0.0, 1.0],
    "pitch_deg": 0.0,
    "yaw_deg": 0.0,
    "roll_deg": 0.0,
    "usd_rotate_xyz_deg": [90.0, 0.0, -90.0],
    "focal_length_mm": 18.0,
    "horizontal_aperture_mm": 20.955,
    "vertical_aperture_mm": 15.716,
    "hfov_deg": 60.4,
    "vfov_deg": 47.2,
    "clipping_range_m": [0.05, 100.0],
    "resolution": [320, 240],
    "provenance": "PROVISIONAL_SIMULATION_VALUE — mount geometry is represented, not measured",
}


def closure(name: str) -> dict[str, Any] | None:
    p = MIRROR / f"{name}.closure.json"
    return json.loads(p.read_text()) if p.is_file() else None


def eligibility() -> dict[str, Any]:
    """In-stage audit results, if any have been recorded."""
    p = OUT / "SCENE_ELIGIBILITY.json"
    return json.loads(p.read_text()).get("scenes", {}) if p.is_file() else {}


def scene_digest(d: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


def build() -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []

    # -- Tier 1: the world the first two pilots actually used ------------------
    control: dict[str, Any] = {
        "scene_id": "control_blocks_v1",
        "display_name": "Primitive control world",
        "tier": "ENGINEERING_CONTROL_WORLD",
        "indoor_outdoor": "NEITHER — unbounded void with a ground plane",
        "environment_type": "SYNTHETIC_PRIMITIVE",
        "source": "PROCEDURAL_IN_SCRIPT",
        "source_asset_id": None,
        "usd_path": None,
        "usd_digest": None,
        "isaac_version": ISAAC_VERSION,
        "constructed_by": "scripts/collect_yahboom_vint_pilot.py L119-143",
        "contents": {
            "ground_plane": {"prim": "/World/groundPlane", "size_m": 40.0},
            "lights": [{"type": "DistantLight", "prim": "/World/light"}],
            "obstacles": {"count": 3, "type": "Cube", "scale_m": [0.3, 0.3, 0.35]},
            "walls": 0, "ceiling": 0, "doors": 0, "furniture": 0, "sky_dome": 0,
        },
        "scene_dimensions_m": [40.0, 40.0, "unbounded"],
        "navigation_area_m2": 1600.0,
        "known_limitations": [
            "No walls, ceiling or sky dome. Every ray above the horizon terminates in "
            "nothing and renders black, which is the dominant feature of the resulting "
            "images and is a property of the world, not of the camera.",
            "No corridor geometry, doorways, furniture, occlusion or texture, so it "
            "supplies none of the visual structure a navigation model reads.",
            "A goal view here is a patch of floor and a primitive, not a destination.",
        ],
        "claim_scope": (
            "Valid evidence for physics, action scale, camera transform, loader "
            "compatibility and controller regression. NOT valid evidence of a realistic "
            "visual-navigation setup, and must never be described as an office, "
            "warehouse or corridor."
        ),
        "used_by": ["pilot_0001", "pilot_0002"],
        "eligible_for_navigation_pilots": False,
    }
    control["scene_digest"] = scene_digest(control)
    scenes.append(control)

    # -- Tier 2 candidates: real Isaac environments, provenance from closure ---
    for name, meta in (
        ("hospital_v1", {
            "display_name": "Isaac Hospital",
            "environment_type": "corridor",
            "environment_subclass": "healthcare_interior",
            "why_considered": "Long corridors, doorways, room transitions and junctions — "
                              "the geometry image-goal navigation is defined on.",
        }),
        ("simple_warehouse_v1", {
            "display_name": "Isaac Simple Warehouse",
            "environment_type": "warehouse",
            "environment_subclass": "industrial_interior",
            "why_considered": "Aisles, racking and pillars give occlusion and repeating "
                              "structure; less doorway/room-transition variety.",
        }),
    ):
        c = closure(name)
        if c is None:
            continue
        root = c.get("root_layer", "")
        usd = MIRROR / name / root
        files = c.get("files", [])
        s: dict[str, Any] = {
            "scene_id": name,
            "display_name": meta["display_name"],
            "tier": "NAVIGATION_EXPERIMENT_WORLD",
            "indoor_outdoor": "indoor",
            "environment_type": meta["environment_type"],
            "environment_subclass": meta["environment_subclass"],
            "source": "NVIDIA_ISAAC_ASSET",
            "source_base_url": c.get("source_base_url"),
            "source_asset_id": f"Isaac/5.1/Isaac/Environments/{meta['display_name']}",
            "usd_path": str(usd),
            "usd_exists": usd.is_file(),
            "usd_root_layer": root,
            "usd_digest": c.get("root_layer_sha256"),
            "closure_digest": c.get("closure_sha256"),
            "closure_complete": c.get("closure_complete"),
            "closure_rounds_to_fixed_point": c.get("rounds_to_fixed_point"),
            "referenced_file_count": c.get("file_count"),
            "total_bytes": c.get("total_bytes"),
            "unresolved_references": len(c.get("unresolved_references", c.get("unresolved", []))),
            "isaac_version": ISAAC_VERSION,
            "prop_count": sum(1 for f in files if "/Props/" in f.get("path", "")),
            "why_considered": meta["why_considered"],
            # Deliberately unfilled until measured in-stage. Asserting a bounding
            # box or a light count from a filename is the failure this file exists
            # to prevent.
            "scene_dimensions_m": "UNMEASURED — requires stage inspection",
            "prim_count": "UNMEASURED — requires stage inspection",
            "material_count": "UNMEASURED — requires stage inspection",
            "light_count": "UNMEASURED — requires stage inspection",
            "navigation_area_m2": "UNMEASURED — requires stage inspection",
            "semantic_objects": "UNMEASURED — requires stage inspection",
            "known_limitations": [
                "Geometry, lighting and navigable area are asserted by the asset, not yet "
                "measured in-stage by this repository.",
            ],
            "claim_scope": (
                "Eligible as a navigation-experiment world once stage inspection and the "
                "camera-view acceptance test pass. Not yet used for any collected pilot."
            ),
            "used_by": [],
        }
        # Eligibility comes from the in-stage audit, never from the closure flag.
        # The mirrors report closure_complete with zero unresolved references and
        # are nonetheless missing every MDL material module, because the closure
        # walked USD-to-USD references and did not follow MDL ones. Trusting the
        # flag would have marked both scenes ready to collect in.
        elig = eligibility().get(name)
        if elig is None:
            s["eligible_for_navigation_pilots"] = False
            s["eligibility_basis"] = "NOT AUDITED — run scripts/audit_scene_assets.py"
            s["blocking_defects"] = ["no in-stage eligibility audit on record"]
        else:
            s["eligible_for_navigation_pilots"] = bool(elig["eligible"])
            s["eligibility_basis"] = "gates/scenes/SCENE_ELIGIBILITY.json"
            s["blocking_defects"] = elig.get("blocking_defects", [])
            s["mdl_modules_referenced"] = elig.get("mdl_modules_referenced")
            s["mdl_files_on_disk"] = elig.get("mdl_files_on_disk")
            s["meters_per_unit"] = elig.get("meters_per_unit")
            s["measured_prim_count"] = elig.get("total_prims")
            s["measured_mesh_count"] = elig.get("mesh_count")
            s["measured_light_count"] = elig.get("light_count")
            s["closure_flag_disagrees_with_audit"] = bool(
                c.get("closure_complete") and not elig["eligible"])
        s["scene_digest"] = scene_digest(s)
        scenes.append(s)

    return {
        "schema": "navfm.scene_identity.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "isaac_version": ISAAC_VERSION,
        "camera_configuration": CAMERA,
        "principle": (
            "Camera geometry and scene identity are part of the data-generating process. "
            "If either changes the observation distribution changes, so both are versioned "
            "and traceable exactly like the checkpoint and the dataset. Any change to scene "
            "identity, camera mount height, camera transform, intrinsics, resolution or "
            "lighting creates a new experimental configuration ID."
        ),
        "scenes": scenes,
        "author": "Frank Asante Van Laarhoven",
    }


def main() -> int:
    if not MIRROR.is_dir():
        print(f"REFUSED: no asset mirror at {MIRROR}", file=sys.stderr)
        return 2
    m = build()
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "SCENE_MANIFEST.json"
    p.write_text(json.dumps(m, indent=2) + "\n")
    print(f"  {p.relative_to(REPO)}")
    for s in m["scenes"]:
        print(f"    {s['scene_id']:<22} {s['tier']:<28} "
              f"eligible={s['eligible_for_navigation_pilots']}")
        if s.get("closure_complete") is not None:
            print(f"      closure {s['closure_complete']} · {s['referenced_file_count']} files · "
                  f"unresolved {s['unresolved_references']} · digest {s['usd_digest'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
