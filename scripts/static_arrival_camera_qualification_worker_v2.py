"""Small camera-only technical fixture using the production capture primitives."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from importlib.metadata import version as distribution_version
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from offline_evaluation_contracts_v1 import atomic_snapshot  # noqa: E402
from prospective_data_contracts_v1 import safe_raw  # noqa: E402
from static_arrival_capture_worker_v1 import _capture_frame, _geometry, _set_lighting  # noqa: E402

from navfm.collection.static_arrival_capture import (  # noqa: E402
    CAMERA_SETTINGS,
    LIGHTING_SETTINGS,
    canonical_sha256,
)


def _persist_measurement_capsule(output: Path, report: dict, worker_input: dict) -> None:
    if (
        len(report["frames"]) != 8
        or any(row.get("status") != "PASS" for row in report["frames"])
        or worker_input.get("shutdown_contract", {}).get("fast_shutdown") is not False
    ):
        raise ValueError("complete v2 measurements/graceful-shutdown contract required")
    expected_ids = [row["image_id"] for row in report["frames"]]
    artifacts = {}
    for image_id in expected_ids:
        for relative in (
            f"capture_metadata/{image_id}.json",
            f"policy_inputs/images/{image_id}.jpg",
        ):
            path = output / relative
            artifacts[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    capsule = {
        "schema": "static_arrival_camera_measurement_capsule_v2",
        "measurement_status": "COMPLETE_BEFORE_SHUTDOWN",
        "schedule_sha256": worker_input["schedule_sha256"],
        "source_bindings_sha256": worker_input["source_bindings_sha256"],
        "worker_input_sha256": canonical_sha256(worker_input),
        "frames": report["frames"],
        "frames_sha256": canonical_sha256(report["frames"]),
        "artifacts": artifacts,
    }
    atomic_snapshot(output / "measurement_complete.json", safe_raw(capsule))


def _retain_failed_frame_diagnostics(camera, np, frame, output: Path, report, exc) -> None:
    """Persist best-effort failed-frame readbacks outside any admission path."""
    event = report["frames"][-1]
    event.update(status="FAIL", failure_type=type(exc).__name__)
    event["diagnostic_requested_body_pose_xy_yaw_rad"] = list(frame["body_pose_xy_yaw_rad"])
    yaw = float(frame["body_pose_xy_yaw_rad"][2])
    event["diagnostic_requested_camera_position"] = [
        float(frame["body_pose_xy_yaw_rad"][0])
        + report["camera_config"]["forward_offset_m"] * math.cos(yaw),
        float(frame["body_pose_xy_yaw_rad"][1])
        + report["camera_config"]["forward_offset_m"] * math.sin(yaw),
        report["camera_config"]["camera_height_m"],
    ]
    try:
        position, quaternion = camera.get_world_pose(camera_axes="world")
        event["diagnostic_actual_camera_position"] = position.tolist()
        event["diagnostic_actual_camera_quaternion"] = quaternion.tolist()
        event["diagnostic_pose_readback_status"] = "READ"
    except BaseException as readback_exc:
        event["diagnostic_pose_readback_status"] = "FAILED"
        event["diagnostic_pose_readback_error_type"] = type(readback_exc).__name__
    try:
        snapshot = camera.get_current_frame(clone=True)
        raw = np.asarray(snapshot.get("rgb"))
        event["diagnostic_snapshot_status"] = "READ"
        event["diagnostic_rendering_time"] = snapshot.get("rendering_time")
        event["diagnostic_rendering_frame"] = snapshot.get("rendering_frame")
        event["diagnostic_rgb_shape"] = list(raw.shape)
        event["diagnostic_rgb_dtype"] = str(raw.dtype)
        if not raw.dtype.hasobject:
            evidence = output / "failure_evidence" / f"{frame['image_id']}.npy"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            temporary = evidence.with_suffix(".npy.pending")
            with temporary.open("wb") as stream:
                np.save(stream, raw, allow_pickle=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, evidence)
            event["diagnostic_rgb_sha256"] = hashlib.sha256(evidence.read_bytes()).hexdigest()
    except BaseException as readback_exc:
        event["diagnostic_snapshot_status"] = "FAILED"
        event["diagnostic_snapshot_error_type"] = type(readback_exc).__name__
    atomic_snapshot(output / "capture_report.json", safe_raw(report))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--parent-nonce", required=True)
    args = parser.parse_args()
    if os.environ.get("NAVFM_STATIC_ARRIVAL_PARENT_NONCE") != args.parent_nonce:
        parser.error("parent-supervised qualification worker required")
    if os.environ.get("OMNICLIENT_HUB_MODE") != "disabled" or Path.cwd() != ROOT:
        parser.error("v2 child launch environment/cwd mismatch")

    worker_input = json.loads(args.input.read_text())
    if worker_input.get("mode") != "technical_camera_qualification_only":
        parser.error("qualification-only input required")
    if worker_input.get("family") != "TECHNICAL" or len(worker_input.get("episodes", [])) != 1:
        parser.error("one technical fixture episode required")
    if len(worker_input.get("frames", [])) != 8:
        parser.error("frozen eight-frame schedule required")
    if worker_input.get("schedule_sha256") != worker_input.get("bound_schedule_sha256"):
        parser.error("qualification schedule binding mismatch")
    shutdown_contract = worker_input.get("shutdown_contract", {})
    if (
        shutdown_contract.get("isaacsim_distribution_version") != "5.1.0.0"
        or shutdown_contract.get("fast_shutdown") is not False
        or shutdown_contract.get("close_return_required") is not True
        or shutdown_contract.get("measurement_capsule_required") is not True
    ):
        parser.error("v2 graceful-close contract mismatch")
    if (
        worker_input.get("camera") != CAMERA_SETTINGS
        or worker_input.get("lighting") != LIGHTING_SETTINGS
        or worker_input.get("warmup_sim_steps") != 8
        or worker_input.get("held_sim_steps_per_capture") != 4
    ):
        parser.error("camera, lighting, warmup, or hold contract mismatch")
    isaacsim_version = distribution_version("isaacsim")
    if isaacsim_version != worker_input["expected_isaacsim_version"]:
        parser.error("installed Isaac Sim distribution version differs from the freeze")

    import numpy as np

    from navfm.isaac.app import IsaacApp, SimConfig

    camera_config = worker_input["camera"]
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    report = {
        "schema": "static_arrival_camera_qualification_v1",
        "status": "STARTED",
        "qualification_only": True,
        "shutdown_returned": False,
        "shutdown_contract": worker_input["shutdown_contract"],
        "launch_observation": {
            "child_cwd": os.getcwd(),
            "child_hub_mode": os.environ.get("OMNICLIENT_HUB_MODE"),
            "simulation_app_fast_shutdown": False,
        },
        "bootstrap_compatibility_branch": None,
        "isaacsim_distribution_version": isaacsim_version,
        "family": "TECHNICAL",
        "camera_config": camera_config,
        "schedule_sha256": worker_input["schedule_sha256"],
        "source_bindings_sha256": worker_input["source_bindings_sha256"],
        "worker_input_sha256": canonical_sha256(worker_input),
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
                warmup_frames=worker_input["warmup_sim_steps"],
            ),
            fast_shutdown=False,
        ) as sim:
            # IsaacApp constructs SimulationApp before any Omniverse imports.
            import omni.usd
            from isaacsim.sensors.camera import Camera
            from pxr import Gf, UsdGeom, UsdLux, UsdPhysics

            stage = omni.usd.get_context().get_stage()
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
            _geometry(stage, UsdGeom, UsdPhysics, Gf, worker_input)
            _set_lighting(stage, UsdLux, UsdGeom, Gf, worker_input)
            camera = Camera(
                prim_path="/World/StaticArrival/QualificationCamera",
                resolution=(camera_config["width_px"], camera_config["height_px"]),
            )
            if sim._version != (5, 0):
                raise ValueError("camera adapter requires the bound Isaac Sim 5.x bootstrap branch")
            report["bootstrap_compatibility_branch"] = list(sim._version)
            sim._sim_manager.initialize_physics()
            sim.play()
            camera.initialize()
            camera.set_focal_length(
                camera.get_horizontal_aperture()
                / (2 * math.tan(math.radians(camera_config["horizontal_fov_deg"]) / 2))
            )
            sim.warmup()
            for frame in worker_input["frames"]:
                try:
                    previous = _capture_frame(
                        sim, camera, np, Image, frame, output, report, previous
                    )
                except BaseException as exc:
                    _retain_failed_frame_diagnostics(camera, np, frame, output, report, exc)
                    raise
                report["frames"][-1]["rgb_std"] = float(
                    np.asarray(previous.get("rgb"))[:, :, :3].std()
                )
                atomic_snapshot(output / "capture_report.json", safe_raw(report))
            report["status"] = "MEASUREMENTS_COMPLETE"
            report["shutdown_returned"] = False
            atomic_snapshot(output / "capture_report.json", safe_raw(report))
            _persist_measurement_capsule(output, report, worker_input)
        report["shutdown_returned"] = True
        if any(frame.get("status") != "PASS" for frame in report["frames"]):
            raise ValueError("qualification frame failure")
        report["status"] = "PASS"
    except BaseException as exc:
        report.update(status="FAIL", failure_type=type(exc).__name__)
        raise
    finally:
        atomic_snapshot(output / "capture_report.json", safe_raw(report))


if __name__ == "__main__":
    main()
