"""Camera-only Isaac acquisition worker for the frozen development schedule."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from development_qualification_contracts_v1 import sha  # noqa: E402
from offline_evaluation_contracts_v1 import atomic_snapshot  # noqa: E402
from prospective_data_contracts_v1 import float32_position, frame_integrity, safe_raw  # noqa: E402

from navfm.collection.static_arrival_capture import (  # noqa: E402
    canonical_sha256,
    training_scene_boxes,
)


def _save_json_lines(path: Path, rows: list[dict]) -> None:
    text = "".join(json.dumps(row, allow_nan=False, sort_keys=True) + "\n" for row in rows)
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("w") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _geometry(stage, UsdGeom, UsdPhysics, Gf, family_input: dict) -> None:
    for scene in sorted({row["scene_index"] for row in family_input["episodes"]}):
        episode = next(row for row in family_input["episodes"] if row["scene_index"] == scene)
        root = f"/World/StaticArrival/Scene{scene}"
        boxes = training_scene_boxes(scene, episode["wall_half_width_m"], episode["partitions"])
        if canonical_sha256(boxes) != episode["geometry_sha256"]:
            raise ValueError("scene builder output differs from the bound geometry digest")
        for box in boxes:
            prim_path = f"{root}/{box['name']}"
            cube = UsdGeom.Cube.Define(stage, prim_path)
            cube.CreateSizeAttr(1.0)
            xform = UsdGeom.XformCommonAPI(cube)
            xform.SetTranslate(Gf.Vec3d(*box["xyz"]))
            xform.SetScale(Gf.Vec3f(*box["size"]))
            cube.CreateDisplayColorAttr([Gf.Vec3f(*box["color"])])
            if box["collision"]:
                UsdPhysics.CollisionAPI.Apply(cube.GetPrim())


def _set_lighting(stage, UsdLux, UsdGeom, Gf, config: dict) -> None:
    light = config["lighting"]
    sun = UsdLux.DistantLight.Define(stage, "/World/StaticArrival/Sun")
    sun.CreateIntensityAttr(light["distant_intensity"])
    UsdGeom.XformCommonAPI(sun).SetRotate(Gf.Vec3f(*light["distant_rotation_xyz_deg"]))
    dome = UsdLux.DomeLight.Define(stage, "/World/StaticArrival/Dome")
    dome.CreateIntensityAttr(light["dome_intensity"])


def _capture_frame(sim, camera, np, Image, frame: dict, output: Path, report: dict, previous):
    image_id = frame["image_id"]
    x, y, yaw = frame["body_pose_xy_yaw_rad"]
    camera_config = report["camera_config"]
    position = [
        x + camera_config["forward_offset_m"] * math.cos(yaw),
        y + camera_config["forward_offset_m"] * math.sin(yaw),
        camera_config["camera_height_m"],
    ]
    quaternion = [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]
    event = {
        "image_id": image_id,
        "episode_id": frame["episode_id"],
        "role": frame["role"],
        "status": "STARTED",
    }
    report["frames"].append(event)
    atomic_snapshot(output / "capture_report.json", safe_raw(report))
    try:
        camera.set_world_pose(np.asarray(position), np.asarray(quaternion), camera_axes="world")
        pose_author_time = sim.sim_time()
        for _ in range(4):
            sim.step()
        hold_end_time = sim.sim_time()
        snapshot = camera.get_current_frame(clone=True)
        rgba = np.asarray(snapshot.get("rgb"))
        actual_position, actual_quaternion = camera.get_world_pose(camera_axes="world")
        expected_size = (camera_config["height_px"], camera_config["width_px"], 4)
        integrity = frame_integrity(
            snapshot,
            previous,
            actual_position.tolist(),
            position,
            rgba.shape,
            pose_author_time,
            hold_end_time,
        )
        if not np.isfinite(rgba).all() or rgba.shape != expected_size:
            raise ValueError("invalid RGB shape or nonfinite pixel")
        if float(rgba[:, :, :3].std()) < 5.0:
            raise ValueError("unusable low-contrast RGB")
        if not np.allclose(actual_quaternion, quaternion, rtol=0, atol=1e-6) and not np.allclose(
            actual_quaternion, -np.asarray(quaternion), rtol=0, atol=1e-6
        ):
            raise ValueError("camera orientation mismatch")
        image_path = output / "policy_inputs" / "images" / f"{image_id}.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgba[:, :, :3].astype(np.uint8)).save(image_path, quality=95)
        event.update(
            status="PASS",
            image_path=str(image_path.relative_to(output)),
            image_sha256=sha(image_path),
            camera={key: snapshot.get(key) for key in ("rendering_time", "rendering_frame")},
            requested_camera_position=position,
            represented_float32_position=float32_position(position),
            actual_camera_position=actual_position.tolist(),
            actual_camera_quaternion=actual_quaternion.tolist(),
            pose_author_time=pose_author_time,
            hold_end_time=hold_end_time,
            rgb_shape=list(rgba.shape),
            rgb_dtype=str(rgba.dtype),
            fixture_integrity=integrity,
        )
        # Pose, labels, scene identity, strata and timestamps are kept in
        # evaluator metadata, never alongside policy image inputs.
        metadata_path = output / "capture_metadata" / f"{image_id}.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "image_id": image_id,
            "episode_id": frame["episode_id"],
            "role": frame["role"],
            "rendering_time": snapshot.get("rendering_time"),
            "rendering_frame": snapshot.get("rendering_frame"),
            "actual_camera_position": actual_position.tolist(),
            "actual_camera_quaternion": actual_quaternion.tolist(),
            "image_sha256": event["image_sha256"],
        }
        if "stratum" in frame:
            metadata["stratum"] = frame["stratum"]
            metadata["scored_decision"] = frame["scored_decision"]
        atomic_snapshot(metadata_path, safe_raw(metadata))
        return snapshot
    except BaseException as exc:
        event.update(status="FAIL", failure_type=type(exc).__name__)
        if "snapshot" in locals():
            raw = np.asarray(snapshot.get("rgb"))
            if not raw.dtype.hasobject:
                partial = output / "failure_evidence" / f"{image_id}.npy"
                partial.parent.mkdir(parents=True, exist_ok=True)
                np.save(partial, raw, allow_pickle=False)
        raise
    finally:
        atomic_snapshot(output / "capture_report.json", safe_raw(report))


def _make_evaluator_labels(config: dict, family_input: dict, output: Path, report: dict) -> None:
    metadata = {
        event["image_id"]: json.loads(
            (output / "capture_metadata" / f"{event['image_id']}.json").read_text()
        )
        for event in report["frames"]
    }
    episodes = [
        episode for episode in config["episodes"] if episode["family"] == family_input["family"]
    ]
    rows = []
    for episode in episodes:
        goal_frame = episode["goal_reference_image_id"]
        goal = metadata[goal_frame]["actual_camera_position"][:2]
        for frame in episode["query_frames"]:
            observation = metadata[frame["image_id"]]
            query = observation["actual_camera_position"][:2]
            distance = math.dist(query, goal)
            rows.append(
                {
                    "image_id": frame["image_id"],
                    "episode_id": episode["episode_id"],
                    "goal_id": episode["goal_id"],
                    "coordinate_frame": f"scene_{episode['scene_index']}_metres",
                    "query_camera_xy_m": query,
                    "goal_camera_xy_m": goal,
                    "distance_m": distance,
                    "geometric_proximity_label": distance <= 0.5,
                    "stratum": frame["stratum"],
                    "access": "EVALUATOR_ONLY_NOT_DECISION_INPUT",
                }
            )
    path = output / "evaluator_only" / "geometric_labels.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _save_json_lines(path, rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--family-input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--parent-nonce", required=True)
    args = parser.parse_args()
    if os.environ.get("NAVFM_STATIC_ARRIVAL_PARENT_NONCE") != args.parent_nonce:
        parser.error("parent-supervised worker invocation required")
    config = json.loads(args.config.read_text())
    family_input = json.loads(args.family_input.read_text())
    if config.get("runtime_authorized") is not True:
        parser.error("capture configuration is preparation-only")
    gate = config.get("runtime_gate", {})
    if any(
        gate.get(name, {}).get("status") != "PASS"
        for name in ("known_fixture_camera", "training_scene_camera")
    ):
        parser.error("camera runtime qualification evidence is incomplete")
    if family_input.get("family") not in {episode["family"] for episode in config["episodes"]}:
        parser.error("unknown family input")
    if family_input.get("schedule_sha256") != canonical_sha256(config):
        parser.error("schedule binding mismatch")
    if family_input.get("source_bindings_sha256") != canonical_sha256(config["source_bindings"]):
        parser.error("source binding digest mismatch")

    import numpy as np
    import omni.usd
    from isaacsim.sensors.camera import Camera
    from PIL import Image
    from pxr import Gf, UsdGeom, UsdLux, UsdPhysics

    from navfm.isaac.app import IsaacApp, SimConfig

    camera_config = config["camera"]
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    report: dict = {
        "schema": "static_arrival_camera_capture_v2",
        "status": "STARTED",
        "family": family_input["family"],
        "fixture_only": False,
        "camera_config": camera_config,
        "schedule_sha256": family_input["schedule_sha256"],
        "source_bindings_sha256": family_input["source_bindings_sha256"],
        "family_input_sha256": canonical_sha256(family_input),
        "frames": [],
    }
    atomic_snapshot(output / "capture_report.json", safe_raw(report))
    previous = None
    try:
        with IsaacApp(
            SimConfig(
                hz=camera_config["sim_hz"],
                resolution=(camera_config["width_px"], camera_config["height_px"]),
                rt_subframes=1,
                physics_substeps=1,
                warmup_frames=camera_config["warmup_sim_steps"],
            )
        ) as sim:
            stage = omni.usd.get_context().get_stage()
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
            _geometry(stage, UsdGeom, UsdPhysics, Gf, family_input)
            _set_lighting(stage, UsdLux, UsdGeom, Gf, config)
            camera = Camera(
                prim_path="/World/StaticArrival/Camera",
                resolution=(camera_config["width_px"], camera_config["height_px"]),
            )
            if sim._version != (5, 0):
                raise ValueError("camera adapter requires the qualified Isaac Sim 5.0 runtime")
            sim._sim_manager.initialize_physics()
            sim.play()
            camera.initialize()
            camera.set_focal_length(
                camera.get_horizontal_aperture()
                / (2 * math.tan(math.radians(camera_config["horizontal_fov_deg"]) / 2))
            )
            sim.warmup()
            for frame in family_input["frames"]:
                previous = _capture_frame(sim, camera, np, Image, frame, output, report, previous)
                atomic_snapshot(output / "capture_report.json", safe_raw(report))
        if any(frame["status"] != "PASS" for frame in report["frames"]):
            raise ValueError("capture frame failure")
        _make_evaluator_labels(config, family_input, output, report)
        report["status"] = "PASS"
    except BaseException as exc:
        report.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        atomic_snapshot(output / "capture_report.json", safe_raw(report))


if __name__ == "__main__":
    main()
