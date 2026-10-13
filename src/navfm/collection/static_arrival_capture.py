"""Preparation contracts for camera-only static-arrival capture.

This module binds a deterministic development schedule to the existing
training-scene geometry. It does not start Isaac, decode images, run an
encoder, fit a calibrator, or authorize collection.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, cast

FAMILY_SCENES = {
    "F0": (0, 5),
    "F1": (1, 6),
    "F2": (2, 7),
    "F3": (8,),
    "F4": (9,),
}
FAMILY_ROLES = {
    "F0": "fit",
    "F1": "fit",
    "F2": "fit",
    "F3": "threshold_selection",
    "F4": "descriptive_assessment",
}
SCENE_HALF_WIDTH_M = {
    0: 2.0,
    1: 2.1,
    2: 2.2,
    5: 1.9,
    6: 2.04,
    7: 2.18,
    8: 2.32,
    9: 2.46,
}
PARTITIONED_SCENES = frozenset((5, 6, 7, 8, 9))
STRATA = ("near_goal", "boundary_negative", "repeated_structure_candidate", "ordinary_negative")
CAMERA_SETTINGS = {
    "width_px": 320,
    "height_px": 240,
    "horizontal_fov_deg": 68.0,
    "camera_height_m": 0.55,
    "forward_offset_m": 0.2,
    "axes": "world; +X forward, +Z up",
    "quaternion_order": "WXYZ",
    "rgb_channels": 3,
    "sim_hz": 16,
    "held_sim_steps_per_capture": 4,
    "capture_cadence_target_hz": 4,
    "warmup_sim_steps": 8,
    "timestamp_source": "native rendering_time and rendering_frame from same cloned frame snapshot",
    "timestamp_policy": "record actual values; require strict acquisition-order increase; never infer time from frame index",
}
LIGHTING_SETTINGS = {
    "source": "existing option1 training collector",
    "distant_light_count": 1,
    "distant_intensity": 1500.0,
    "distant_rotation_xyz_deg": [-45.0, 30.0, 0.0],
    "dome_intensity": 800.0,
    "per_episode_variation": "none",
}
CAPTURE_PER_EPISODE = 44
DECISIONS_PER_EPISODE = 24
EXPECTED_POPULATION = {
    "episodes": 20,
    "references": 160,
    "queries": 720,
    "decisions": 480,
    "by_role": {"fit": 12, "threshold_selection": 4, "descriptive_assessment": 4},
    "decisions_per_stratum": 120,
}
BOUND_SOURCE_PATHS = (
    "src/navfm/collection/scene_layouts.py",
    "src/navfm/collection/demonstrations.py",
    "src/navfm/collection/static_arrival_capture.py",
    "scripts/collect_option1.py",
    "scripts/prospective_capture_v1.py",
    "scripts/prospective_data_contracts_v1.py",
    "scripts/prospective_collection_contracts_v1.py",
    "scripts/offline_evaluation_contracts_v1.py",
    "scripts/static_arrival_capture_worker_v1.py",
    "scripts/static_arrival_capture_launcher_v1.py",
    "configs/collection/option1_expansion_25.json",
    "configs/splits/arrival_split_v2.json",
    "configs/eval/arrival_measures_v1.json",
    "configs/eval/prospective_collection_v2.json",
    "docs/STATIC_ARRIVAL_RULE_DEVELOPMENT_ACQUISITION_V1.md",
)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bound_source_manifest(root: Path) -> list[dict[str, str]]:
    return [{"path": name, "sha256": source_sha256(root / name)} for name in BOUND_SOURCE_PATHS]


def verify_source_manifest(config: dict[str, Any], root: Path) -> None:
    """Require exact source-path coverage and current bytes before an attempt."""

    declared = config.get("source_bindings")
    if not isinstance(declared, list):
        raise ValueError("source binding manifest missing")
    if any(
        not isinstance(row, dict)
        or set(row) != {"path", "sha256"}
        or not isinstance(row["path"], str)
        or not isinstance(row["sha256"], str)
        for row in declared
    ):
        raise ValueError("malformed source binding row")
    names = [row["path"] for row in declared]
    if len(names) != len(set(names)) or set(names) != set(BOUND_SOURCE_PATHS):
        raise ValueError("source binding coverage mismatch")
    actual = {row["path"]: row["sha256"] for row in bound_source_manifest(root)}
    if any(declared_row["sha256"] != actual[declared_row["path"]] for declared_row in declared):
        raise ValueError("bound source hash mismatch")


def camera_center_xy(pose: list[float], camera_x_offset_m: float = 0.2) -> tuple[float, float]:
    x, y, yaw = (float(value) for value in pose)
    return x + camera_x_offset_m * math.cos(yaw), y + camera_x_offset_m * math.sin(yaw)


def acquisition_id(episode_id: str, role: str, index: int) -> str:
    """Stable opaque capture ID; role and stratum are stored separately."""

    token = hashlib.sha256(f"{episode_id}\0{role}\0{index}".encode()).hexdigest()[:24]
    return f"staticarr2_{token}"


def _frame(
    image_id: str,
    role: str,
    pose: list[float],
    *,
    segment: str | None = None,
    context_only: bool = False,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "image_id": image_id,
        "role": role,
        "body_pose_xy_yaw_rad": [round(float(value), 9) for value in pose],
    }
    if segment is not None:
        item["stratum"] = segment
        item["scored_decision"] = not context_only
    return item


def build_schedule() -> dict[str, Any]:
    """Return the deterministic 20-episode schedule from the v1 strata."""

    episodes = []
    for family, scene_indices in FAMILY_SCENES.items():
        for within_family in range(4):
            scene_index = scene_indices[min(within_family // 2, len(scene_indices) - 1)]
            episode_id = f"static_arrival_v2_{family}_episode_{within_family:02d}"
            goal_id = f"{episode_id}_requested_goal"
            origin_y = scene_index * 20.0
            goal_x = 1.2 + 0.2 * within_family

            reference_frames = []
            reference_poses = []
            for node_index in range(8):
                pose = [goal_x - 1.4 + 0.2 * node_index, origin_y, 0.0]
                reference_poses.append(pose)
                reference_frames.append(
                    _frame(acquisition_id(episode_id, "reference", node_index), "reference", pose)
                )

            query_frames = []
            segment_centers = {
                "near_goal": (goal_x - 0.2, math.pi / 2.0),
                "boundary_negative": (goal_x - 0.75, 0.0),
                "repeated_structure_candidate": (goal_x + 1.25, 0.0),
                "ordinary_negative": (goal_x - 1.25, 0.0),
            }
            for stratum_index, stratum in enumerate(STRATA):
                center_x, center_yaw = segment_centers[stratum]
                for frame_index in range(9):
                    # A fixed pose sequence creates distinct authored views; it is
                    # not a continuous-motion path or a velocity measurement.
                    offset = (frame_index - 4) * 0.01
                    pose = [center_x + offset, origin_y, center_yaw + (frame_index - 4) * 0.005]
                    query_frames.append(
                        _frame(
                            acquisition_id(episode_id, "query", stratum_index * 9 + frame_index),
                            "query",
                            pose,
                            segment=stratum,
                            context_only=frame_index < 3,
                        )
                    )

            episodes.append(
                {
                    "episode_id": episode_id,
                    "goal_id": goal_id,
                    "family": family,
                    "partition_role": FAMILY_ROLES[family],
                    "scene_index": scene_index,
                    "scene_identity": f"legacy_corridor_scene_{scene_index}",
                    "scene_origin_y_m": origin_y,
                    "wall_half_width_m": SCENE_HALF_WIDTH_M[scene_index],
                    "partitions": scene_index in PARTITIONED_SCENES,
                    "goal_reference_index": 7,
                    "goal_camera_xy_m": list(camera_center_xy(reference_poses[-1])),
                    "reference_frames": reference_frames,
                    "query_frames": query_frames,
                }
            )

    root = Path(__file__).resolve().parents[3]
    prior_collection = json.loads(
        (root / "configs/eval/prospective_collection_v2.json").read_text()
    )
    return {
        "schema_version": 2,
        "status": "PREPARATION_ONLY",
        "runtime_authorized": False,
        "runtime_gate": {
            "status": "BLOCKED_CAMERA_CADENCE_AND_TRAINING_SCENE_NOT_QUALIFIED",
            "known_fixture_camera": {
                "status": "NOT_RUN",
                "required_camera": "320x240 RGB, 68 degree HFOV, 0.55 m height, 0.20 m offset",
                "required_sim_hz": 16,
                "required_held_steps": 4,
            },
            "training_scene_camera": {
                "status": "NOT_RUN",
                "required_scene_families": ["F0", "F1", "F2", "F3", "F4"],
                "requirement": "verify builder construction and camera capture on these families before collection",
            },
        },
        "purpose": "static geometric-proximity development calibration pilot",
        "seed_policy": "deterministic pose schedule; no random layout regeneration",
        "groups": [
            {"family": family, "scene_indices": list(scenes), "role": FAMILY_ROLES[family]}
            for family, scenes in FAMILY_SCENES.items()
        ],
        "camera": CAMERA_SETTINGS,
        "lighting": LIGHTING_SETTINGS,
        "scene_adapter": {
            "builder": "navfm.collection.scene_layouts.legacy_boxes",
            "collision_geometry": "preserve each builder box collision flag",
            "scenes": [
                {
                    "scene_index": scene,
                    "wall_half_width_m": SCENE_HALF_WIDTH_M[scene],
                    "partitions": scene in PARTITIONED_SCENES,
                    "appearance_family": f"F{scene % 5}",
                    "geometry_sha256": canonical_sha256(
                        training_scene_boxes(
                            scene,
                            SCENE_HALF_WIDTH_M[scene],
                            scene in PARTITIONED_SCENES,
                        )
                    ),
                }
                for scene in sorted(SCENE_HALF_WIDTH_M)
            ],
        },
        "source_bindings": bound_source_manifest(root),
        "worker_python": prior_collection["python"],
        "registry_root": "~/navfm-training-evidence/static-arrival-training-v2/execution-registry",
        "acquisition": {
            "process_unit": "one complete appearance family per process",
            "processes": 5,
            "episodes_per_family": 4,
            "reference_then_query": True,
            "reference_nodes_per_episode": 8,
            "query_frames_per_episode": 36,
            "query_segments_per_episode": [
                {"name": name, "frames": 9, "context_frames": 3, "scored_decisions": 6}
                for name in STRATA
            ],
            "history": "four immediately preceding query captures, newest-first; decisions use only frames 3-8 within each segment",
            "label": {
                "target": "camera optical-center XY within 0.5 m of requested goal reference camera optical center",
                "query_pose_channel": "evaluator_only",
                "goal_pose_channel": "evaluator_only",
                "decision_input": "RGB history, ordered RGB references, requested goal image identity only",
            },
            "frame_identity_policy": "globally unique immutable IDs; references and queries are distinct acquisition records",
        },
        "population": EXPECTED_POPULATION,
        "exclusions": {
            "known_source_trajectory_ids_excluded": prior_collection["prospective"][
                "known_trajectory_ids"
            ],
            "accessed_pilot_status": prior_collection["collection"]["prior_layout_exposure"],
            "exposed_development": [
                "s_bend_run_0000",
                "s_bend_run_0001",
                "junction_run_0000",
                "junction_run_0001",
            ],
            "retired_exposed_test": ["junction_run_0000", "junction_run_0001"],
            "sealed_heldout": [f"heldout_layout_{letter}" for letter in "ABCDEF"],
            "rule": "never read or import old RGB, labels, outcomes, pilot outputs, or sealed heldout assets",
        },
        "wall_budget": {
            "status": "PROPOSED_NOT_AUTHORIZED_NOT_MEASURED",
            "whole_process_cap_seconds_per_family": 600,
            "pre_reap_attempt_allowance_seconds": 570,
            "child_reap_reserve_seconds": 10,
            "verification_and_finalization_reserve_seconds": 20,
            "processes": 5,
            "aggregate_ceiling_seconds": 3000,
            "scope": "each family process, including startup, stage construction, warmup, all captures, incremental persistence, SDK close, child reap, and final ledger; no additional 190-second cap",
            "prior_190_second_cap": "applied to the separate 144-frame two-room pilot only; it does not cap this 880-image proposal",
            "no_retry_or_extension": True,
        },
        "episodes": episodes,
    }


def validate_schedule(
    config: dict[str, Any], *, prior_ids: set[str] | None = None
) -> dict[str, int]:
    if config.get("schema_version") != 2 or type(config.get("runtime_authorized")) is not bool:
        raise ValueError("static-arrival acquisition schema/authorization flag required")
    runtime_gate = config.get("runtime_gate", {})
    if config["runtime_authorized"] and any(
        runtime_gate.get(name, {}).get("status") != "PASS"
        for name in ("known_fixture_camera", "training_scene_camera")
    ):
        raise ValueError("camera runtime qualification gates are incomplete")
    expected_groups = [
        {"family": family, "scene_indices": list(scenes), "role": FAMILY_ROLES[family]}
        for family, scenes in FAMILY_SCENES.items()
    ]
    if config.get("groups") != expected_groups:
        raise ValueError("fit/selection/assessment family binding mismatch")
    if config.get("camera") != CAMERA_SETTINGS or config.get("lighting") != LIGHTING_SETTINGS:
        raise ValueError("camera or lighting contract drift")
    if config.get("population") != EXPECTED_POPULATION:
        raise ValueError("declared population summary mismatch")
    budget = config.get("wall_budget", {})
    if (
        budget.get("status") != "PROPOSED_NOT_AUTHORIZED_NOT_MEASURED"
        or budget.get("whole_process_cap_seconds_per_family") != 600
        or budget.get("pre_reap_attempt_allowance_seconds") != 570
        or budget.get("child_reap_reserve_seconds") != 10
        or budget.get("verification_and_finalization_reserve_seconds") != 20
        or budget.get("processes") != 5
    ):
        raise ValueError("proposed whole-family process budget drift")
    scene_rows = config.get("scene_adapter", {}).get("scenes", [])
    scene_map = {row.get("scene_index"): row for row in scene_rows}
    if len(scene_rows) != len(SCENE_HALF_WIDTH_M) or set(scene_map) != set(SCENE_HALF_WIDTH_M):
        raise ValueError("declared training scene set mismatch")
    for scene_index, row in scene_map.items():
        if (
            row.get("wall_half_width_m") != SCENE_HALF_WIDTH_M[scene_index]
            or row.get("partitions") is not (scene_index in PARTITIONED_SCENES)
            or row.get("appearance_family") != f"F{scene_index % 5}"
        ):
            raise ValueError("training-scene variant binding mismatch")
        expected_geometry = canonical_sha256(
            training_scene_boxes(
                scene_index,
                SCENE_HALF_WIDTH_M[scene_index],
                scene_index in PARTITIONED_SCENES,
            )
        )
        if row.get("geometry_sha256") != expected_geometry:
            raise ValueError("training-scene geometry digest mismatch")
    episodes = config.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != EXPECTED_POPULATION["episodes"]:
        raise ValueError("fixed 20-episode population required")
    expected_episode_ids = [
        f"static_arrival_v2_{family}_episode_{index:02d}"
        for family in FAMILY_SCENES
        for index in range(4)
    ]
    if [episode.get("episode_id") for episode in episodes] != expected_episode_ids:
        raise ValueError("fixed episode order/identity binding mismatch")
    seen_ids: set[str] = set()
    seen_episode_ids: set[str] = set()
    seen_goal_ids: set[str] = set()
    roles: Counter[str] = Counter()
    strata: Counter[str] = Counter()
    refs = queries = decisions = 0
    family_counts: Counter[str] = Counter()
    for episode in episodes:
        family = episode.get("family")
        if family not in FAMILY_SCENES or episode.get("partition_role") != FAMILY_ROLES[family]:
            raise ValueError("episode family/partition binding mismatch")
        if episode.get("scene_index") not in FAMILY_SCENES[family]:
            raise ValueError("scene is outside its declared appearance family")
        if episode.get("wall_half_width_m") != SCENE_HALF_WIDTH_M[episode["scene_index"]]:
            raise ValueError("scene geometry binding mismatch")
        if episode.get("partitions") is not (episode["scene_index"] in PARTITIONED_SCENES):
            raise ValueError("partition geometry binding mismatch")
        family_counts[family] += 1
        episode_id = episode.get("episode_id")
        goal_id = episode.get("goal_id")
        if not isinstance(episode_id, str) or not episode_id or episode_id in seen_episode_ids:
            raise ValueError("duplicate or missing episode identity")
        if not isinstance(goal_id, str) or not goal_id or goal_id in seen_goal_ids:
            raise ValueError("duplicate or missing requested-goal identity")
        if goal_id != f"{episode_id}_requested_goal":
            raise ValueError("requested-goal identity binding mismatch")
        if episode.get("scene_identity") != f"legacy_corridor_scene_{episode['scene_index']}":
            raise ValueError("training-scene identity mismatch")
        seen_episode_ids.add(episode_id)
        seen_goal_ids.add(goal_id)
        roles[episode["partition_role"]] += 1
        reference_frames = episode.get("reference_frames")
        query_frames = episode.get("query_frames")
        if len(reference_frames) != 8 or len(query_frames) != 36:
            raise ValueError("episode reference/query population mismatch")
        expected_reference_ids = [
            acquisition_id(episode_id, "reference", index) for index in range(8)
        ]
        expected_query_ids = [
            acquisition_id(episode_id, "query", stratum_index * 9 + index)
            for stratum_index, _ in enumerate(STRATA)
            for index in range(9)
        ]
        if [frame.get("image_id") for frame in reference_frames] != expected_reference_ids:
            raise ValueError("ordered reference identity binding mismatch")
        if [frame.get("image_id") for frame in query_frames] != expected_query_ids:
            raise ValueError("ordered query identity binding mismatch")
        if reference_frames[7]["image_id"] != acquisition_id(episode_id, "reference", 7):
            raise ValueError("requested terminal must be ordered reference node 7")
        if episode.get("goal_id") == "" or episode.get("goal_reference_index") != 7:
            raise ValueError("requested goal identity mismatch")
        expected_goal_camera = camera_center_xy(reference_frames[7]["body_pose_xy_yaw_rad"])
        actual_goal_camera = episode.get("goal_camera_xy_m")
        if (
            not isinstance(actual_goal_camera, list)
            or len(actual_goal_camera) != 2
            or any(
                not math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=1e-9)
                for actual, expected in zip(actual_goal_camera, expected_goal_camera, strict=True)
            )
        ):
            raise ValueError("goal camera-center label source mismatch")
        for frame in (*reference_frames, *query_frames):
            image_id = frame.get("image_id")
            if not isinstance(image_id, str) or not image_id or image_id in seen_ids:
                raise ValueError("duplicate or missing acquisition identity")
            seen_ids.add(image_id)
            pose = frame.get("body_pose_xy_yaw_rad")
            if (
                not isinstance(pose, list)
                or len(pose) != 3
                or any(not math.isfinite(float(value)) for value in pose)
            ):
                raise ValueError("nonfinite or malformed scheduled pose")
            if frame.get("role") not in ("reference", "query"):
                raise ValueError("unsupported frame role")
        if any(frame.get("role") != "reference" for frame in reference_frames):
            raise ValueError("reference role mismatch")
        if any(frame.get("role") != "query" for frame in query_frames):
            raise ValueError("query role mismatch")
        refs += len(reference_frames)
        queries += len(query_frames)
        query_strata = Counter(frame.get("stratum") for frame in query_frames)
        if query_strata != Counter({stratum: 9 for stratum in STRATA}):
            raise ValueError("query stratum frame population mismatch")
        for stratum in STRATA:
            segment = [frame for frame in query_frames if frame.get("stratum") == stratum]
            if [frame.get("scored_decision") for frame in segment] != [
                False,
                False,
                False,
                True,
                True,
                True,
                True,
                True,
                True,
            ]:
                raise ValueError("segment context/decision assignment mismatch")
            strata[stratum] += sum(frame["scored_decision"] is True for frame in segment)
            decisions += sum(frame["scored_decision"] is True for frame in segment)
            distances = [
                math.dist(
                    camera_center_xy(frame["body_pose_xy_yaw_rad"]), episode["goal_camera_xy_m"]
                )
                for frame in segment
            ]
            if stratum == "near_goal" and any(distance > 0.5 for distance in distances):
                raise ValueError("scheduled positive stratum exceeds the frozen 0.5 m target")
            if stratum == "boundary_negative" and any(
                not 0.5 < distance < 1.0 for distance in distances
            ):
                raise ValueError("scheduled boundary stratum violates its declared range")
            if stratum in {"repeated_structure_candidate", "ordinary_negative"} and any(
                distance < 1.0 for distance in distances
            ):
                raise ValueError("scheduled negative stratum is inside the declared 1.0 m range")
    if family_counts != Counter({family: 4 for family in FAMILY_SCENES}):
        raise ValueError("four episodes per declared family required")
    expected_roles = cast(dict[str, int], EXPECTED_POPULATION["by_role"])
    if roles != Counter(expected_roles):
        raise ValueError("fit/selection/assessment assignment mismatch")
    if (refs, queries, decisions) != (160, 720, 480):
        raise ValueError("fixed reference/query/decision totals required")
    if any(count != EXPECTED_POPULATION["decisions_per_stratum"] for count in strata.values()):
        raise ValueError("fixed decision quota per stratum required")
    excluded = set(prior_ids or ())
    exposed = set(config["exclusions"]["exposed_development"])
    retired = set(config["exclusions"]["retired_exposed_test"])
    heldout = set(config["exclusions"]["sealed_heldout"])
    known_source_ids = set(config["exclusions"]["known_source_trajectory_ids_excluded"])
    if seen_ids & (excluded | exposed | retired | heldout | known_source_ids):
        raise ValueError("new acquisition identity overlaps an exclusion")
    if seen_episode_ids & (excluded | exposed | retired | heldout | known_source_ids):
        raise ValueError("episode identity overlaps an exclusion")
    return {
        "episodes": len(episodes),
        "references": refs,
        "queries": queries,
        "decisions": decisions,
    }


def capture_worker_input(config: dict[str, Any], family: str) -> dict[str, Any]:
    """Return only the acquisition schedule, never geometric target labels."""

    if family not in FAMILY_SCENES:
        raise ValueError("unknown family")
    episodes = [episode for episode in config["episodes"] if episode["family"] == family]
    if len(episodes) != 4:
        raise ValueError("family episode count mismatch")
    allowed_frame_keys = {"image_id", "role", "body_pose_xy_yaw_rad", "stratum", "scored_decision"}
    geometry_rows = {row["scene_index"]: row for row in config["scene_adapter"]["scenes"]}
    frame_rows = []
    for episode in episodes:
        for frame in (*episode["reference_frames"], *episode["query_frames"]):
            frame_rows.append(
                {
                    "episode_id": episode["episode_id"],
                    **{key: value for key, value in frame.items() if key in allowed_frame_keys},
                }
            )
    return {
        "family": family,
        "camera": config["camera"],
        "lighting": config["lighting"],
        "episodes": [
            {
                "episode_id": episode["episode_id"],
                "goal_id": episode["goal_id"],
                "scene_index": episode["scene_index"],
                "scene_identity": episode["scene_identity"],
                "geometry_sha256": geometry_rows[episode["scene_index"]]["geometry_sha256"],
                "coordinate_frame": f"scene_{episode['scene_index']}_metres",
                "wall_half_width_m": episode["wall_half_width_m"],
                "partitions": episode["partitions"],
                "goal_reference_image_id": episode["reference_frames"][7]["image_id"],
                "reference_count": len(episode["reference_frames"]),
                "query_count": len(episode["query_frames"]),
            }
            for episode in episodes
        ],
        "frames": frame_rows,
    }


def evaluator_label_rows(config: dict[str, Any], family: str) -> list[dict[str, Any]]:
    """Derive evaluator-only proximity labels; callers must keep this file apart."""

    rows = []
    for episode in config["episodes"]:
        if episode["family"] != family:
            continue
        goal_xy = tuple(float(value) for value in episode["goal_camera_xy_m"])
        for frame in episode["query_frames"]:
            query_xy = camera_center_xy(frame["body_pose_xy_yaw_rad"])
            distance = math.dist(query_xy, goal_xy)
            rows.append(
                {
                    "image_id": frame["image_id"],
                    "episode_id": episode["episode_id"],
                    "goal_id": episode["goal_id"],
                    "coordinate_frame": f"scene_{episode['scene_index']}_metres",
                    "query_camera_xy_m": list(query_xy),
                    "goal_camera_xy_m": list(goal_xy),
                    "distance_m": distance,
                    "geometric_proximity_label": distance <= 0.5,
                    "stratum": frame["stratum"],
                    "access": "EVALUATOR_ONLY_NOT_DECISION_INPUT",
                }
            )
    return rows


def training_scene_boxes(scene_index: int, wall_half_width_m: float, partitions: bool):
    """Adapt the actual training scene builder without creating a robot stack."""

    from navfm.collection.scene_layouts import legacy_boxes

    return legacy_boxes(scene_index, wall_half_width_m, partitions=partitions)
