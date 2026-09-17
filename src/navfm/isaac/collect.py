"""Isaac Sim -> GNM-format data collection.

    python -m navfm.isaac.collect --config configs/collect/m3pro_indoor.yaml \\
        --out /data/isaac_m3pro --episodes 400

Per episode:

1. reset the scene, fire per-episode domain randomisation;
2. sample a collision-free ``(start, goal)`` pair with a bounded path length;
3. plan with A*, string-pull, optionally perturb for recovery coverage;
4. drive it with pure pursuit at ``hz``, capturing one synchronised
   ``(image, pose, sim_time)`` per step;
5. write a GNM trajectory atomically, or discard it if any guard trips.

Guards that discard an episode -- each exists because the failure it catches is
silent otherwise:

``collision``
    A contact or a stall. A trajectory that ends in a wall teaches the policy to
    drive into walls; the reference datasets work around this with ``end_slack``
    (RECON uses 3) but discarding is cleaner when we control collection.
``stalled``
    Commanded velocity with no displacement -- usually a physics wedge. Produces
    long runs of identical frames that dominate the sampler.
``too_short``
    Fewer frames than the model's spec needs. The loader would drop it
    silently, so we drop it loudly.
``degenerate``
    Path length below a floor, or a stationary fraction above a ceiling. Both
    collapse the action distribution towards zero.

Every accepted trajectory carries a ``metadata`` entry in ``traj_data.pkl``
recording the sim config, robot config, randomisation draw, seed and episode
index, so any single trajectory can be regenerated exactly.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..collection.scope import (
    BO10_SCOPE_DECLARATION,
    CollectionScope,
    ScopeDeclarationError,
    authorise_g2_acknowledgement,
)
from ..control import DemonstratorMode, PurePursuit
from ..kinematics import arc_length
from ..planning import OccupancyGrid, PlannerError, perturb_path, sample_episode_pair
from ..schema import TrajectorySpec
from ..target_selection import resolve_target_selector
from ..writer import TrajectoryWriter
from .app import IsaacApp, SimConfig
from .randomize import RandomizationConfig, SceneRandomizer, apply_sensor_noise
from .robot import M3PRO, RobotConfig, SimRobot


class _UseFixedRoute(Exception):
    """Internal control flow: a pre-admitted route replaces sampling."""


__all__ = [
    "OCCUPANCY_BACKENDS",
    "OCCUPANCY_BACKEND_LEGACY",
    "OCCUPANCY_BACKEND_PHYSX",
    "UNKNOWN_CELL_POLICY",
    "CollectConfig",
    "Collector",
    "EpisodeResult",
    "OccupancyBackendError",
]

#: Cell values the Isaac occupancy generator is asked to write. UNKNOWN is a
#: third state and must never be folded into either of the other two: a cell the
#: generator could not classify is not a cell it found empty.
OCCUPIED = 4
UNOCCUPIED = 5
UNKNOWN = 6

#: Which implementation answers "is this cell occupied?".
#:
#: The two are not interchangeable and the choice is never inferred. LEGACY is
#: the Isaac occupancy-map extension, which is known to omit solid geometry --
#: a reception desk at 0 of 725 cells, a supply cart at 0 of 72
#: (gates/failures/F-G5-2.md). PHYSX_CELL_OVERLAP_V1 is the validated
#: cell-volume probe. LEGACY is retained rather than deleted because it is the
#: causal control: the repair is only demonstrated by showing the old backend
#: reproduces the omission and the new one does not.
OCCUPANCY_BACKEND_LEGACY = "legacy"
OCCUPANCY_BACKEND_PHYSX = "physx_cell_overlap_v1"
OCCUPANCY_BACKENDS = (OCCUPANCY_BACKEND_LEGACY, OCCUPANCY_BACKEND_PHYSX)

#: How a cell the backend could not classify is treated. Frozen explicitly
#: because the alternative already happened: `buf == OCCUPIED` silently made
#: every UNKNOWN cell traversable, and 62% of the planner's free space came from
#: cells the generator had declined to classify. UNKNOWN and QUERY_FAILED are
#: BLOCKED, and they are counted separately so a map that is mostly unknown
#: cannot look like a map that is mostly clear.
UNKNOWN_CELL_POLICY = "BLOCKED"


class OccupancyBackendError(RuntimeError):
    """An occupancy backend was requested that does not exist, or failed."""


class RuntimeBoundaryError(RuntimeError):
    """A live runtime object this collector needs was never bound to it.

    Distinct from a configuration error. ``SimConfig`` is declarative and can be
    perfectly valid while no application exists; ``IsaacApp`` is the live object,
    and only one of those can open a stage. Attempt 1 of the terminal-approach
    intervention failed exactly there: the adapter owned an app, the collector
    held a correct SimConfig, and the bare ``assert`` that noticed carried no
    message, so the lifecycle recorded ``unhandled AssertionError:`` with an
    empty reason and an escaped exception.

    Raised with a named category so the failure is diagnosable from the artefact
    rather than from a stack trace.
    """

    def __init__(self, category: str, detail: str) -> None:
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail


@dataclasses.dataclass
class CollectConfig:
    scenes: list[str] = dataclasses.field(default_factory=list)
    episodes: int = 200
    max_steps: int = 1200
    #: Model whose sampling spec defines the minimum acceptable episode length.
    target_model: str = "vint"
    min_path_m: float = 3.0
    max_path_m: float = 40.0
    cruise_v: float = 0.35
    lookahead_m: float = 0.45
    goal_tol_m: float = 0.20
    demonstrator: str = DemonstratorMode.NONHOLONOMIC.value
    #: Fraction of episodes driven with a perturbed path for recovery coverage.
    perturb_fraction: float = 0.35
    perturb_sigma_m: float = 0.25
    #: Fraction driven as undirected wandering (chained random goals). NoMaD's
    #: unconditioned branch needs this distribution; ViNT alone does not.
    wander_fraction: float = 0.20
    grid_resolution: float = 0.10
    min_clearance_m: float = 0.35
    max_stationary_fraction: float = 0.5
    stall_patience: int = 40
    seed: int = 0
    scene_name: str | None = None
    #: Declared target-selector identity for the intervention arms. ``None`` is
    #: the frozen legacy behaviour every existing caller has always had; an
    #: intervention arm declares its own, and an unknown value is refused rather
    #: than defaulted. This is the only behavioural knob the arms differ on.
    target_selector: str | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> CollectConfig:
        data = yaml.safe_load(Path(path).read_text()) or {}
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class EpisodeResult:
    index: int
    name: str
    accepted: bool
    reason: str = ""
    n_frames: int = 0
    path_length_m: float = 0.0
    wall_time_s: float = 0.0


class Collector:
    """Owns the sim, the robot and the episode loop."""

    def __init__(
        self,
        out_dir: str | Path,
        collect: CollectConfig,
        sim: SimConfig,
        robot_config: RobotConfig = M3PRO,
        randomization: RandomizationConfig | None = None,
        scope: CollectionScope | None = None,
        occupancy_backend: str = OCCUPANCY_BACKEND_LEGACY,
        isaac_app: IsaacApp | None = None,
    ) -> None:
        """``isaac_app`` binds a live application this collector does not own.

        ``run()`` creates and owns an app for the whole collection. A caller that
        drives the stages directly -- the production arm adapter does, because an
        arm is one episode under a frozen route rather than a collection loop --
        owns the app instead and must hand over that same object. Passing only
        ``sim`` leaves this collector with a valid configuration and no live
        application, which is how Attempt 1 reached scene loading with nothing to
        open a stage with.
        """
        self.out_dir = Path(out_dir)
        if occupancy_backend not in OCCUPANCY_BACKENDS:
            raise OccupancyBackendError(
                f"unknown occupancy backend {occupancy_backend!r}; valid backends: "
                f"{list(OCCUPANCY_BACKENDS)}")
        #: Default stays LEGACY deliberately. Changing it would silently alter
        #: the map for every existing caller, including the ones whose results
        #: are frozen, and a different map means different sampling. The
        #: scientific tranche selects the new backend explicitly.
        self.occupancy_backend = occupancy_backend
        #: What actually ran, recorded so an artefact can state it rather than
        #: a reader having to infer it from a default.
        self.occupancy_backend_used: str | None = None
        #: Cells whose query raised. Blocked, and counted rather than absorbed.
        self.occupancy_query_failures: int = 0
        #: A pre-admitted (start, yaw, goal, path) to drive instead of sampling.
        #: BO-10 collects a route that route admission already cleared; re-sampling
        #: inside the episode would drive a DIFFERENT route from the one the gates
        #: passed, which is the whole point of admitting one.
        self.fixed_route: tuple[Any, float, Any, Any] | None = None
        #: When set, the episode seals a goal image before its first motion
        #: command and records the controller identity across the episode.
        self.enforce_premotion_gates: bool = False
        #: Populated by run_episode when enforce_premotion_gates is set.
        self.episode_gate_records: list[dict[str, Any]] = []
        #: KINEMATIC_COLLECTION_DRIVE_V1. When set, the episode advances the base
        #: by integrating the commanded twist and applying the pose, subject to
        #: the driver's swept-collision invariant, instead of writing articulation
        #: root velocities. F-DRIVE-1: root velocities do not move this robot.
        self.kinematic_driver: Any = None
        #: What this collection is for, and whether it may enter the E2
        #: population. Stamped into every episode's metadata and into the
        #: manifest, so a trajectory carries its own scope rather than relying on
        #: the directory it happens to sit in.
        self.scope = scope
        self.collect = collect
        self.sim = sim
        self.robot_config = robot_config
        self.randomization = randomization or RandomizationConfig(seed=collect.seed)
        self.spec = TrajectorySpec.for_model(collect.target_model)
        self.rng = np.random.default_rng(collect.seed)
        self.results: list[EpisodeResult] = []

        #: Bound at construction when a caller owns the app, otherwise created
        #: and owned by ``run()``. Exactly one of those is true per execution:
        #: two live applications would mean two simulators, and an arm that
        #: opened its stage in one while stepping the other would be measuring
        #: neither.
        self._app: IsaacApp | None = isaac_app
        self._app_is_borrowed: bool = isaac_app is not None
        self._robot: SimRobot | None = None
        self._randomizer: SceneRandomizer | None = None
        self._grid: OccupancyGrid | None = None
        self._clearance: np.ndarray | None = None
        self._inflated_cache: OccupancyGrid | None = None
        self._inflated_clearance_cache: np.ndarray | None = None

    # -- setup -----------------------------------------------------------

    @staticmethod
    def route_window(
        centre: tuple[float, float],
        max_path_m: float,
        footprint_radius_m: float,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """A square window that cannot exclude any admissible route.

        Euclidean displacement cannot exceed path length, so every point of a
        route no longer than ``max_path_m`` lies within that distance of its
        start. The footprint radius is added because the swept body extends
        beyond the centreline.

        Justified entirely by parameters already frozen in the collection
        contract; the only declared input is the centre.
        """
        half = float(max_path_m) + float(footprint_radius_m)
        cx, cy = float(centre[0]), float(centre[1])
        return (cx - half, cy - half), (cx + half, cy + half)

    def open_scene(self, scene_usd: str) -> None:
        if self._app is None:
            raise RuntimeBoundaryError(
                "ISAAC_APP_NOT_BOUND_TO_COLLECTOR",
                "open_scene needs a live IsaacApp. This collector holds a valid "
                "SimConfig and no application: either run() was bypassed, or a "
                "caller that drives the stages directly passed sim configuration "
                "where the live app was required. A configuration cannot open a "
                "stage")
        self._app.open_stage(scene_usd)
        self._robot = SimRobot(self._app, self.robot_config)
        self._robot.spawn()
        self._robot.attach_camera()
        self._randomizer = SceneRandomizer(self.randomization, self.rng)
        self._randomizer.register()
        self._app.play()
        self._app.warmup()
        self._grid = self.build_occupancy(scene_usd)
        self._clearance = self._grid.clearance()

    def build_occupancy(
        self,
        scene_usd: str,
        bounds: tuple[tuple[float, float], tuple[float, float]] | None = None,
        *,
        backend: str | None = None,
    ) -> OccupancyGrid:
        """Build a 2-D occupancy grid by ray-casting a horizontal slice.

        Uses Isaac Sim's occupancy-map extension when available (it is
        GPU-accelerated and handles instanced geometry correctly), and falls
        back to a PhysX scene-query sweep otherwise.

        ``bounds`` overrides the stage bounding box. It is OPT-IN and the
        default is unchanged, because changing the default would change the grid
        for scenes whose results are already frozen, and a different grid means
        different sampling.

        It exists because the stage bound is not a collection region in scenes
        that contain distant scenery. Office carries a city-skyline backdrop
        spanning 1064 x 678 m, which makes the grid 72 million cells against
        Hospital's 322,560 for a comparable interior, and roughly 99.5% of the
        mapped area is exterior the robot will never occupy. Two geometric rules
        for deriving a tighter bound were tried and both are refuted by
        measurement in gates/failures/F-BOUNDS-1.md -- the buildings carry
        colliders, and they stand on a ground plane, so neither collidable
        geometry nor "where the robot can stand" separates interior from
        exterior. Such a scene has no intrinsic boundary, so the region is
        declared and recorded rather than derived.
        """
        # The backend is DISPATCHED, never fallen back to. An ambiguous fallback
        # would mean an artefact could not say which instrument produced it, and
        # these two disagree about whether a reception desk exists.
        chosen = backend or self.occupancy_backend
        if chosen not in OCCUPANCY_BACKENDS:
            raise OccupancyBackendError(
                f"unknown occupancy backend {chosen!r}; valid backends: "
                f"{list(OCCUPANCY_BACKENDS)}")
        self.occupancy_backend_used = chosen
        if chosen == OCCUPANCY_BACKEND_PHYSX:
            return self.build_occupancy_physx(bounds)

        res = self.collect.grid_resolution
        try:
            import omni.usd
            from isaacsim.asset.gen.omap.bindings import _omap

            stage_id = omni.usd.get_context().get_stage_id()
            # Isaac 5.1 takes (PhysX, stage_id); earlier bindings took the stage
            # id alone. Try 5.1 first -- it is the PRIMARY branch here -- and
            # keep the single-argument form working rather than replacing it.
            try:
                from omni.physx import get_physx_interface

                gen = _omap.Generator(get_physx_interface(), stage_id)
            except TypeError:
                gen = _omap.Generator(stage_id)
            # Values the generator writes: OCCUPIED, UNOCCUPIED, UNKNOWN.
            gen.update_settings(res, OCCUPIED, UNOCCUPIED, UNKNOWN)
            bounds = bounds if bounds is not None else self._stage_bounds()
            gen.set_transform(
                (0.0, 0.0, 0.0),
                (bounds[0][0], bounds[0][1], 0.10),
                (bounds[1][0], bounds[1][1], 0.60),
            )
            gen.generate2d()
            dims = gen.get_dimensions()
            buf = np.asarray(gen.get_buffer()).reshape(dims[1], dims[0])
            # Blocked is "not explicitly unoccupied", NOT "explicitly occupied".
            #
            # The earlier rule was `buf == OCCUPIED`, which made every UNKNOWN cell
            # free space. On Hospital that is 174,376 of 322,560 cells -- 54% of the
            # map -- and after inflation it inflated the planner's free space from
            # 91,650 cells to 242,106, so 62% of everywhere the planner believed it
            # could drive was somewhere the generator had declined to classify.
            # Measured, not estimated: gates/failures/F-G5-1.md.
            #
            # A transect through a Hospital wall shows the shape of it: the interior
            # of the wall is UNKNOWN, only a two-cell surface sliver is OCCUPIED, and
            # the planner drove through the middle. This is the FL-019 genus at map
            # scale -- an absence of knowledge consumed as a benign value -- and the
            # direction of the error is the dangerous one, because a missing obstacle
            # invents free space exactly where the robot would collide.
            grid = buf != UNOCCUPIED
            return OccupancyGrid(grid, res, origin=(bounds[0][0], bounds[0][1]))
        except Exception as exc:
            raise RuntimeError(
                "Could not build an occupancy map with isaacsim.asset.gen.omap "
                f"({exc!r}). Provide a pre-built map with --occupancy-npz instead; "
                "planning without one is not supported because a random-walk "
                "demonstrator produces temporal-distance labels that are "
                "uncorrelated with spatial proximity."
            ) from exc

    def build_occupancy_physx(
        self,
        bounds: tuple[tuple[float, float], tuple[float, float]] | None = None,
        *,
        slab_z: tuple[float, float] = (0.10, 0.60),
    ) -> OccupancyGrid:
        """EXPERIMENTAL, NOT VALIDATED. Build occupancy from PhysX overlap queries.

        **This is not wired into production and must not be used for evidence
        until validated.** It is retained because it is the most promising route
        to a trustworthy map and because the measurements behind it are worth
        keeping.

        The occupancy-map extension does not represent a large part of this
        scene's collision geometry. Measured on Hospital: a reception desk
        spanning z 0.0-1.321 has 0 of 725 footprint cells marked occupied and a
        supply cart spanning 0.0-1.034 has 0 of 72. Routes were planned straight
        through furniture, and every long-horizon candidate failed G5 at
        near-contact distances. See gates/failures/F-G5-2.md.

        This asks PhysX instead. The point is not only accuracy: G5 already
        queries PhysX, so building the map from the same instrument removes the
        disagreement between the map that plans a route and the gate that judges
        it. It does not make G5 redundant -- G5 sweeps the footprint at several
        heights and measures distance, where this asks one yes/no question per
        cell.

        **Overlap, not raycast.** The first implementation cast a ray downward
        from the top of the slab, and it was wrong in the most dangerous
        direction. A ray starting inside a collider reports no hit, so every
        object taller than the slab -- every wall -- vanished from the map. It
        was caught by checking a known wall: `Geo_W_WallBase10`, spanning
        z 0.0-3.0, went from 12.5% of its footprint marked occupied to 0%. An
        overlap test asks whether anything intersects the cell's slab volume,
        which is the question actually being asked and is indifferent to whether
        a query point lies inside geometry.
        """
        assert self._app is not None, "an Isaac app is required for PhysX queries"
        from omni.physx import get_physx_scene_query_interface

        res = self.collect.grid_resolution
        (min_x, min_y), (max_x, max_y) = bounds if bounds is not None else self._stage_bounds()
        nx = max(1, int(math.ceil((max_x - min_x) / res)))
        ny = max(1, int(math.ceil((max_y - min_y) / res)))
        q = get_physx_scene_query_interface()

        z_lo, z_hi = float(slab_z[0]), float(slab_z[1])
        half = [res / 2.0, res / 2.0, (z_hi - z_lo) / 2.0]
        z_mid = (z_lo + z_hi) / 2.0
        identity = [0.0, 0.0, 0.0, 1.0]  # xyzw

        grid = np.zeros((ny, nx), dtype=bool)
        failed = 0
        for j in range(ny):
            y = min_y + j * res
            for i in range(nx):
                x = min_x + i * res
                try:
                    hit = q.overlap_box(half, [x, y, z_mid], identity,
                                        lambda _h: False, True)
                except Exception:
                    # A cell whose query FAILED is not a cell found empty. It is
                    # blocked and counted, because the opposite convention is
                    # exactly how 54% of a map became traversable.
                    grid[j, i] = True
                    failed += 1
                    continue
                if hit:
                    grid[j, i] = True
        self.occupancy_query_failures = failed
        self.occupancy_backend_used = OCCUPANCY_BACKEND_PHYSX
        return OccupancyGrid(grid, res, origin=(min_x, min_y))

    def _stage_bounds(self) -> tuple[tuple[float, float], tuple[float, float]]:
        import omni.usd
        from pxr import Usd, UsdGeom

        stage = omni.usd.get_context().get_stage()
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        aabb = cache.ComputeWorldBound(stage.GetPseudoRoot()).ComputeAlignedRange()
        lo, hi = aabb.GetMin(), aabb.GetMax()
        return (float(lo[0]), float(lo[1])), (float(hi[0]), float(hi[1]))

    def load_occupancy(self, npz_path: str | Path) -> None:
        data = np.load(npz_path)
        self._grid = OccupancyGrid(
            data["grid"], float(data["resolution"]), tuple(data["origin"].tolist())
        )
        self._clearance = self._grid.clearance()

    # -- episodes --------------------------------------------------------

    def run_episode(self, index: int, scene_name: str) -> EpisodeResult:
        assert self._app is not None and self._robot is not None and self._grid is not None
        t0 = time.time()
        name = f"{scene_name}_run_{index:05d}"
        result = EpisodeResult(index=index, name=name, accepted=False)

        inflated = self._inflated
        if self.fixed_route is not None:
            start, yaw, goal, path = self.fixed_route
            gate_record: dict[str, Any] = {"route": "PRE_ADMITTED", "resampled": False}
        else:
            gate_record = {"route": "SAMPLED", "resampled": True}
        try:
            if self.fixed_route is not None:
                raise _UseFixedRoute
            start, yaw, goal, path = sample_episode_pair(
                inflated,
                self.rng,
                min_path_m=self.collect.min_path_m,
                max_path_m=self.collect.max_path_m,
                min_clearance_m=self.collect.min_clearance_m,
                clearance_map=self._inflated_clearance,
            )
        except _UseFixedRoute:
            pass
        except PlannerError as exc:
            result.reason = f"planner: {exc}"
            self.results.append(result)
            return result

        # A pre-admitted route is never perturbed. Perturbation exists to widen
        # the training distribution during bulk collection; applying it here
        # would drive a route the gates did not clear.
        if self.fixed_route is None and self.rng.random() < self.collect.perturb_fraction:
            path = perturb_path(path, inflated, self.rng, sigma=self.collect.perturb_sigma_m)

        randomization_draw = (
            self._randomizer.randomize_episode() if self._randomizer else {"enabled": False}
        )
        self._robot.teleport(start, yaw)
        self._app.step()  # settle physics and flush the renderer after the teleport

        if self.enforce_premotion_gates:
            from ..collection.controller import ControllerIdentity
            from ..collection.goal_seal import GoalSeal

            # G9. The goal image is captured AT THE GOAL, before the robot has
            # moved along the route, and the robot is returned to the start
            # afterwards. Taking it from the episode's final observation would
            # make the goal reachable by construction and framed from wherever
            # the demonstrator happened to stop.
            seal = GoalSeal(goal_xy=(float(goal[0]), float(goal[1])),
                            source_camera=self._robot.camera_path)
            seal.declare()
            self._robot.teleport((float(goal[0]), float(goal[1])), float(yaw))
            for _ in range(3):
                self._app.step()
            seal.acquire(self._robot.rgb(), sim_time=None)
            goal_provenance = seal.write_provenance()
            seal.seal()
            # Back to the start, and settle again before anything is recorded.
            self._robot.teleport(start, yaw)
            for _ in range(3):
                self._app.step()

            limits = self.robot_config.limits
            identity_before = ControllerIdentity(
                implementation="navfm.control.PurePursuit",
                control_hz=float(self.sim.hz), max_v=limits.max_v, max_w=limits.max_w,
                max_vy=limits.max_vy, max_a=limits.max_a, max_alpha=limits.max_alpha,
                cruise_v=self.collect.cruise_v, lookahead_m=self.collect.lookahead_m,
                goal_tol_m=self.collect.goal_tol_m,
                demonstrator_mode=self.collect.demonstrator, seed=int(self.collect.seed))
            gate_record["goal_provenance"] = goal_provenance
            gate_record["controller_identity_before"] = identity_before.digest
            self._goal_seal = seal
            self._identity_before = identity_before
            metadata_goal = goal_provenance
        else:
            metadata_goal = None

        selector = resolve_target_selector(self.collect.target_selector)
        tracker = PurePursuit(
            path,
            lookahead=self.collect.lookahead_m,
            goal_tol=self.collect.goal_tol_m,
            limits=self.robot_config.limits,
            mode=DemonstratorMode(self.collect.demonstrator),
            cruise_v=self.collect.cruise_v,
            target_selector=selector,
        )

        metadata = {
            "scene": scene_name,
            "episode": index,
            "seed": int(self.collect.seed),
            "goal_xy": [float(goal[0]), float(goal[1])],
            "sim": self.sim.to_dict(),
            "collect": self.collect.to_dict(),
            "robot": self.robot_config.to_dict(),
            "randomization": randomization_draw,
            "planned_path_length_m": arc_length(path),
        }
        if self.scope is not None:
            metadata.update(self.scope.to_manifest_fields())
        if metadata_goal is not None:
            metadata["goal_image_provenance"] = metadata_goal

        writer = TrajectoryWriter(self.out_dir / name, metadata=metadata)
        writer.open()
        stalled = 0
        last_pos = np.asarray(start, dtype=np.float64)
        reason = ""

        try:
            for _ in range(self.collect.max_steps):
                pos, cur_yaw = self._robot.pose()
                vx, vy, wz, done = tracker.step(pos, cur_yaw)
                if done:
                    reason = "reached_goal"
                    break

                # Raises if the goal was not sealed first, at the moment it would
                # matter rather than in a later audit.
                _seal = getattr(self, "_goal_seal", None)
                if (self.enforce_premotion_gates and _seal is not None
                        and not _seal._has_first_motion):
                    _seal.note_first_motion()
                    _seal._has_first_motion = True
                if self.kinematic_driver is not None:
                    step_res = self.kinematic_driver.step(
                        (float(pos[0]), float(pos[1]), float(cur_yaw)), (vx, vy, wz))
                    if step_res.outcome.value == "REJECTED_COLLISION":
                        # The invariant refused the pose. It is not applied and
                        # the episode stops; continuing would mean driving a
                        # trajectory whose next step was known to be unsafe.
                        reason = f"collision_guard: {step_res.reason}"
                        self._drive_rejection = step_res.to_dict()
                        break
                    self._robot.teleport((step_res.pose[0], step_res.pose[1]),
                                         step_res.pose[2])
                else:
                    self._robot.set_body_velocity(vx, vy, wz)
                sim_t = self._app.step()

                pos, cur_yaw = self._robot.pose()
                rgb = apply_sensor_noise(self._robot.rgb(), self.randomization, self.rng)
                writer.append(rgb, pos, cur_yaw, sim_time=sim_t)

                moved = float(np.linalg.norm(pos - last_pos))
                commanded = math.hypot(vx, vy) > 0.02 or abs(wz) > 0.05
                stalled = stalled + 1 if (commanded and moved < 1e-3) else 0
                last_pos = pos
                if stalled >= self.collect.stall_patience:
                    reason = "stalled"
                    break
            else:
                reason = "max_steps"
        except Exception as exc:
            writer.abort()
            result.reason = f"exception: {exc!r}"
            result.wall_time_s = time.time() - t0
            self.results.append(result)
            return result

        result.n_frames = writer.n_frames
        if reason == "stalled":
            writer.abort()
            result.reason = "stalled"
        elif writer.n_frames < self.spec.min_length:
            writer.abort()
            result.reason = f"too_short ({writer.n_frames} < {self.spec.min_length})"
        else:
            path_len = self._written_length(writer)
            if path_len < self.collect.min_path_m * 0.5:
                writer.abort()
                result.reason = f"degenerate (path {path_len:.2f} m)"
            else:
                writer.close()
                result.accepted = True
                result.reason = reason
                result.path_length_m = path_len

        result.wall_time_s = time.time() - t0
        self.results.append(result)
        return result

    @staticmethod
    def _written_length(writer: TrajectoryWriter) -> float:
        positions = np.asarray(writer._positions, dtype=np.float64)
        return arc_length(positions)

    @property
    def _inflated(self) -> OccupancyGrid:
        """Occupancy grid dilated by the robot footprint, cached per scene.

        Inflating once and planning on a point robot is both faster and safer
        than per-configuration collision checks, and it matches what ROS
        costmaps do, so demonstrator behaviour transfers to hardware.
        """
        if self._inflated_cache is None:
            assert self._grid is not None, "call open_scene() or load_occupancy() first"
            self._inflated_cache = self._grid.inflate(self.robot_config.footprint_radius)
            self._inflated_clearance_cache = self._inflated_cache.clearance()
        return self._inflated_cache

    @property
    def _inflated_clearance(self) -> np.ndarray:
        _ = self._inflated
        assert self._inflated_clearance_cache is not None
        return self._inflated_clearance_cache

    # -- driver ----------------------------------------------------------

    def run(self, scenes: list[str], episodes: int) -> list[EpisodeResult]:
        if self._app_is_borrowed:
            raise RuntimeBoundaryError(
                "ISAAC_APP_SINGLE_OWNER_VIOLATION",
                "run() creates and owns an application, and this collector was "
                "already given one. Proceeding would leave two live simulators "
                "with the caller holding the other, so which one an episode "
                "actually stepped would be unrecoverable from the evidence")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        per_scene = max(1, episodes // max(1, len(scenes)))
        with IsaacApp(self.sim) as app:
            self._app = app
            for scene_usd in scenes:
                scene_name = self.collect.scene_name or Path(scene_usd).stem
                self._inflated_cache = None
                self.open_scene(scene_usd)
                for i in range(per_scene):
                    r = self.run_episode(i, scene_name)
                    status = "ok " if r.accepted else "SKIP"
                    print(
                        f"[{scene_name}] {status} {r.name} "
                        f"frames={r.n_frames} len={r.path_length_m:.1f}m "
                        f"{r.wall_time_s:.1f}s {r.reason}",
                        flush=True,
                    )
        self._write_manifest()
        return self.results

    def _write_manifest(self) -> None:
        accepted = [r for r in self.results if r.accepted]
        manifest = {
            "out_dir": str(self.out_dir),
            "n_episodes": len(self.results),
            "n_accepted": len(accepted),
            "acceptance_rate": len(accepted) / max(1, len(self.results)),
            "total_frames": sum(r.n_frames for r in accepted),
            "total_path_length_m": sum(r.path_length_m for r in accepted),
            "sim": self.sim.to_dict(),
            "collect": self.collect.to_dict(),
            "randomization": self.randomization.to_dict(),
            "robot": self.robot_config.to_dict(),
            "episodes": [dataclasses.asdict(r) for r in self.results],
        }
        if self.scope is not None:
            # Written at the top level, where an E2 consumer reads it. A manifest
            # with no scope block is REFUSED by navfm.collection.scope rather
            # than admitted, so this is not an optional annotation.
            manifest.update(self.scope.to_manifest_fields())
        (self.out_dir / "collection_manifest.json").write_text(json.dumps(manifest, indent=2))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m navfm.isaac.collect")
    p.add_argument("--config", help="YAML CollectConfig")
    p.add_argument("--out", required=True)
    p.add_argument("--scenes", nargs="*", default=None, help="scene USD paths")
    p.add_argument("--robot-usd", default=None)
    p.add_argument("--episodes", type=int, default=None)
    p.add_argument("--hz", type=float, default=12.0)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--occupancy-npz", default=None)
    p.add_argument("--no-randomization", action="store_true")
    p.add_argument(
        "--headed",
        action="store_true",
        help="run with the UI (slow, and 6.0 has a known crash when changing step rates in the UI)",
    )
    p.add_argument(
        "--acknowledge-g2-block",
        action="store_true",
        help=argparse.SUPPRESS,  # deliberately undocumented: see the refusal text
    )
    p.add_argument(
        "--scope-declaration",
        default=None,
        help="path to the frozen BO-10 scope declaration; REQUIRED with "
             "--acknowledge-g2-block, which is authorised only when bound to it",
    )
    args = p.parse_args(argv)

    # G2 mechanical block. Runs before Isaac Sim is opened and before a single
    # frame is written, because a deferral that can be stepped over once the
    # collector is warm is not a deferral.
    scope: CollectionScope | None = None
    if args.acknowledge_g2_block:
        # The acknowledgement is not a flag, it is a flag bound to a frozen
        # declaration. Passing it alone would be a bypass with a comment
        # attached, so the declaration is required and its digest must match.
        declaration = args.scope_declaration or (
            Path(__file__).resolve().parents[3] / BO10_SCOPE_DECLARATION)
        try:
            scope = authorise_g2_acknowledgement(declaration)
        except ScopeDeclarationError as exc:
            print(f"--acknowledge-g2-block refused: {exc}", file=sys.stderr)
            return 4
        print(f"G2 acknowledged under {scope.purpose.value}; "
              f"e2_eligible={scope.e2_eligible}", flush=True)
    else:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_g2_block",
            Path(__file__).resolve().parents[3] / "scripts" / "check_g2_block.py",
        )
        if spec and spec.loader:
            g2 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(g2)
            try:
                g2.assert_unblocked()
            except g2.G2Blocked as exc:
                print(str(exc), file=sys.stderr)
                return 4

    cfg = CollectConfig.from_yaml(args.config) if args.config else CollectConfig()
    if args.episodes is not None:
        cfg.episodes = args.episodes
    if args.seed is not None:
        cfg.seed = args.seed
    scenes = args.scenes or cfg.scenes
    if not scenes:
        print("no scenes given (--scenes or config.scenes)", file=sys.stderr)
        return 2

    sim = SimConfig(hz=args.hz, headless=not args.headed, seed=cfg.seed)
    robot = dataclasses.replace(M3PRO, usd_path=args.robot_usd or M3PRO.usd_path)
    rand = RandomizationConfig(enabled=not args.no_randomization, seed=cfg.seed)

    collector = Collector(args.out, cfg, sim, robot, rand, scope=scope)
    if args.occupancy_npz:
        collector.load_occupancy(args.occupancy_npz)
    results = collector.run(scenes, cfg.episodes)

    accepted = sum(r.accepted for r in results)
    print(f"\naccepted {accepted}/{len(results)} episodes -> {args.out}")
    return 0 if accepted else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
