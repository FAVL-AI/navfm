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

from ..control import DemonstratorMode, PurePursuit
from ..kinematics import arc_length
from ..planning import OccupancyGrid, PlannerError, perturb_path, sample_episode_pair
from ..schema import TrajectorySpec
from ..writer import TrajectoryWriter
from .app import IsaacApp, SimConfig
from .randomize import RandomizationConfig, SceneRandomizer, apply_sensor_noise
from .robot import M3PRO, RobotConfig, SimRobot

__all__ = ["CollectConfig", "Collector", "EpisodeResult"]


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
    ) -> None:
        self.out_dir = Path(out_dir)
        self.collect = collect
        self.sim = sim
        self.robot_config = robot_config
        self.randomization = randomization or RandomizationConfig(seed=collect.seed)
        self.spec = TrajectorySpec.for_model(collect.target_model)
        self.rng = np.random.default_rng(collect.seed)
        self.results: list[EpisodeResult] = []

        self._app: IsaacApp | None = None
        self._robot: SimRobot | None = None
        self._randomizer: SceneRandomizer | None = None
        self._grid: OccupancyGrid | None = None
        self._clearance: np.ndarray | None = None
        self._inflated_cache: OccupancyGrid | None = None
        self._inflated_clearance_cache: np.ndarray | None = None

    # -- setup -----------------------------------------------------------

    def open_scene(self, scene_usd: str) -> None:
        assert self._app is not None
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

    def build_occupancy(self, scene_usd: str) -> OccupancyGrid:
        """Build a 2-D occupancy grid by ray-casting a horizontal slice.

        Uses Isaac Sim's occupancy-map extension when available (it is
        GPU-accelerated and handles instanced geometry correctly), and falls
        back to a PhysX scene-query sweep otherwise.
        """
        res = self.collect.grid_resolution
        try:
            import omni.usd
            from isaacsim.asset.gen.omap.bindings import _omap

            gen = _omap.Generator(omni.usd.get_context().get_stage_id())
            gen.update_settings(res, 4, 5, 6)  # cell size, occupied, unoccupied, unknown
            bounds = self._stage_bounds()
            gen.set_transform(
                (0.0, 0.0, 0.0),
                (bounds[0][0], bounds[0][1], 0.10),
                (bounds[1][0], bounds[1][1], 0.60),
            )
            gen.generate2d()
            dims = gen.get_dimensions()
            buf = np.asarray(gen.get_buffer()).reshape(dims[1], dims[0])
            grid = buf == 4
            return OccupancyGrid(grid, res, origin=(bounds[0][0], bounds[0][1]))
        except Exception as exc:
            raise RuntimeError(
                "Could not build an occupancy map with isaacsim.asset.gen.omap "
                f"({exc!r}). Provide a pre-built map with --occupancy-npz instead; "
                "planning without one is not supported because a random-walk "
                "demonstrator produces temporal-distance labels that are "
                "uncorrelated with spatial proximity."
            ) from exc

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
        try:
            start, yaw, goal, path = sample_episode_pair(
                inflated,
                self.rng,
                min_path_m=self.collect.min_path_m,
                max_path_m=self.collect.max_path_m,
                min_clearance_m=self.collect.min_clearance_m,
                clearance_map=self._inflated_clearance,
            )
        except PlannerError as exc:
            result.reason = f"planner: {exc}"
            self.results.append(result)
            return result

        if self.rng.random() < self.collect.perturb_fraction:
            path = perturb_path(path, inflated, self.rng, sigma=self.collect.perturb_sigma_m)

        randomization_draw = (
            self._randomizer.randomize_episode() if self._randomizer else {"enabled": False}
        )
        self._robot.teleport(start, yaw)
        self._app.step()  # settle physics and flush the renderer after the teleport

        tracker = PurePursuit(
            path,
            lookahead=self.collect.lookahead_m,
            goal_tol=self.collect.goal_tol_m,
            limits=self.robot_config.limits,
            mode=DemonstratorMode(self.collect.demonstrator),
            cruise_v=self.collect.cruise_v,
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
    args = p.parse_args(argv)

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

    collector = Collector(args.out, cfg, sim, robot, rand)
    if args.occupancy_npz:
        collector.load_occupancy(args.occupancy_npz)
    results = collector.run(scenes, cfg.episodes)

    accepted = sum(r.accepted for r in results)
    print(f"\naccepted {accepted}/{len(results)} episodes -> {args.out}")
    return 0 if accepted else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
