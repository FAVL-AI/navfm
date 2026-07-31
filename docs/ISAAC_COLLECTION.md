# Collecting GNM-format data in Isaac Sim

## A version correction up front

You asked for Isaac Sim 5.x + Isaac Lab. As of July 2026 that pairing is no
longer the right default, and the reason matters for this specific task:

* **Isaac Sim 6.0.1** (June 2026, Kit 110.1.2, Python 3.12) is the shipping
  release. 6.0 moved sensors to `isaacsim.sensors.experimental.rtx` and Core to
  `isaacsim.core.experimental.*`, so 5.x tutorials do not import.
* **There is no stable Isaac Lab for Isaac Sim 6.0.** Stable Isaac Lab is
  v2.3.2 (Isaac Sim 4.5/5.0/5.1, Python 3.11); the 6.0-compatible v3.0.0-beta2
  warns of breaking changes in its own README.
* **You do not need Isaac Lab.** Isaac Lab exists for massively-parallel RL
  environments. This task is one robot, one camera, ground-truth pose, recorded
  to disk. Standalone Isaac Sim does that with less machinery and — critically —
  6.0's deterministic-stepping story (`/ExternalSimulationTime`,
  `SimulationManager.setup_simulation` + `RenderingManager.set_dt`,
  `isaacsim.exp.base.zero_delay.kit`) is *materially better documented and
  better engineered* for exactly the (image, pose, timestamp) synchronisation
  this dataset format requires.

`navfm.isaac.app` targets **6.0.1 standalone** and falls back to the 5.x
namespace automatically, so either works. If you have a reason to stay on 5.1 +
Isaac Lab 2.3.2, nothing here breaks.

## Install

```bash
python3.12 -m venv .venv-isaac && source .venv-isaac/bin/activate
pip install -U pip
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
pip install "isaacsim[all,extscache]==6.0.1.0" --extra-index-url https://pypi.nvidia.com
export OMNI_KIT_ACCEPT_EULA=YES
pip install -e /path/to/navfm           # navfm itself, no torch needed
```

Note it is **not** plain `pip install isaacsim[all]` — the `extscache` extra,
the `--extra-index-url`, and a pinned version are all required.

**Driver:** Linux 595.58.03 tested. **GLIBC 2.35+** (Ubuntu 22.04 has exactly
2.35 — fine, but no headroom).

### OS / ROS decision

The M3 PRO ships **ROS 2 Humble**. Isaac Sim supports Humble only on **Ubuntu
22.04** (Jazzy is the 24.04 recommendation). If you want sim and robot on one
distro, build the sim host on **22.04 + Humble**.

## Hardware check: RTX 4080 SUPER 16 GB

NVIDIA's own requirements table lists **RTX 4080 / 16 GB VRAM as the minimum**,
and 16 GB as the "good" tier. Your card sits exactly there and is comfortably
sufficient for this workload:

* the docs' VRAM warning is about scenes rendering **>16 MP per frame**; a
  single 640×480 camera is 0.3 MP — two orders of magnitude under;
* the "large number of sensors" warning does not apply (one camera);
* the 4080 SUPER has RT cores (A100/H100 do not and are unsupported).

Pair it with **≥64 GB system RAM** (32 GB is the bare minimum and scene loading
is RAM-hungry) and NVMe. First load of a large environment USD "may take ten
minutes or more" from the S3 asset root — install the local Assets Pack.

### Local Assets Pack (do this; it makes runs reproducible and offline)

```bash
for i in 1 2 3 4 5; do
  wget https://downloads.isaacsim.nvidia.com/isaac-sim-assets-complete-6.0.1.00$i.zip
done
cat isaac-sim-assets-complete-6.0.1.00*.zip > assets.zip && unzip assets.zip -d ~/isaacsim_assets
export ISAACSIM_ASSET_ROOT=~/isaacsim_assets/Assets/Isaac/6.0
```

All five parts are required and must combine into one root containing both
`NVIDIA/` and `Isaac/`. MD5s are published on the download page — check them,
and record them in your artefact appendix.

## The robot

Yahboom publishes **no URDF on GitHub** — their `ROSMASTER-M3PRO` repo is a
README and a photo. The description package `yahboomcar_description`
(`urdf/`, `meshes/`, `launch/`, `rviz/`) exists only inside the tutorial
downloads:

* **Code-Firmware** bundle → contains `yahboomcar_ws` including
  `yahboomcar_description`
* **3D_Model_File** bundle → CAD, the authoritative source for wheelbase, track
  width and the camera mount transform
* or `scp` it straight off the robot: `~/yahboomcar_ws/src/` (native) or
  `/root/yahboomcar_ws/src/` (inside Docker on Pi 5 / Nano B01)

A useful structural template for a clean xacro→URDF→USD pipeline is
[`automaticaddison/yahboom_rosmaster`](https://github.com/automaticaddison/yahboom_rosmaster)
— but it is the **X3**, not the M3 PRO: single lidar, no arm, unverified
geometry match. Use it for structure, not for numbers.

### URDF → USD

```bash
# GUI: File > Import, or headless via isaacsim.asset.importer.urdf
python -m navfm.isaac.urdf_import --urdf yahboomcar_description/urdf/yahboomcar.urdf \
    --out assets/m3pro.usd --robot-type Holonomic --base-type Mobile \
    --collision convex-decomposition
```

Three things to fix after import, in order of how badly they bite:

1. **Inertials.** Vendor URDFs in this price segment routinely ship placeholder
   inertia tensors. PhysX will be unstable or subtly wrong. Recompute from the
   CAD, or from uniform-density primitives fitted to the meshes.
2. **Mecanum rollers.** URDF cannot express roller-based contact. Modelling 40
   free-spinning rollers is slow and fragile. `navfm.isaac.robot.SimRobot`
   therefore commands **body-frame velocity on the articulation root** and does
   not simulate wheel contact at all. This is the right trade for a dataset
   whose labels are `(image, SE(2) pose)` — wheel fidelity contributes nothing
   to those labels. If a later experiment needs slip, swap in
   `isaacsim.robot.wheeled_robots`'s holonomic controller.
3. **Wheel drives** (only if you do simulate wheels): set
   `UsdPhysics.DriveAPI` **stiffness = 0, damping high** (~15000) for velocity
   control.

### Camera

The physical camera is an **Orbbec DaBai DCW2** mounted on the **DOFBOT-PRO
arm** — so its extrinsics are a function of six joint angles. The GNM format
has no place for a time-varying camera transform and the models assume a static
viewpoint, so we **lock the arm to a stowed pose** and treat the camera as
rigid. State this deviation in any paper.

Intrinsics we match, and why:

| | Value | Reason |
|---|---|---|
| Resolution | 640 × 480 | already 4:3, so the GNM pipeline's centre crop is a no-op |
| H-FOV | **64°** | the DCW2's **4:3** RGB mode. Its 16:9 mode is 86° × 55°, but capturing 16:9 and letting the pipeline crop to 4:3 would throw away ~25 % of the width and leave sim and real with different effective FOVs |
| V-FOV | 55° | DCW2 spec |
| Frame rate | 12 Hz capture | the real sensor caps at **15 fps at every resolution**; 12 divides by 3 into the reference stack's 4 Hz policy rate |
| Shutter | global (Isaac) vs **rolling** (real) | an unmodelled gap; matters under fast yaw. Document it |
| Depth | not captured | GNM-family models are RGB-only. Capture it anyway if you want a future ablation — `annotators=["rgb", "distance_to_image_plane"]` |

Mount height and x-offset are **PROVISIONAL** in `navfm.isaac.robot.CameraRig`
(0.28 m, 0.16 m). Measure them.

## The synchronisation contract

This is the part that determines whether your dataset is correct, and it is the
part that fails silently.

Three independent clocks exist in Isaac Sim 6.0 (run loop, physics, renderer),
and multi-tick rendering is **on by default**. Three specific failure modes:

1. **Frames in flight.** The RTX renderer pipelines ~3 frames. Read a pose right
   after `app.update()` and you pair it with an image from ~3 steps earlier — a
   systematic label offset that looks like a small time constant and destroys
   the action labels. **Fix:** `rep.orchestrator.step(wait_for_render=True)`
   blocks until the frame is rendered; read pose and image immediately after.
   The docs are explicit: with `wait_for_render=False` "the annotation and
   writer data may correspond to a previous frame".
2. **Clock drift.** If `physics_dt > loop_dt`, timeline time and physics time
   diverge *within* a physics step. **Fix:** set them equal, as a pair —
   `SimulationManager.setup_simulation(dt)` **and** `RenderingManager.set_dt(dt)`
   — and read time only from `SimulationManager.get_simulation_time()`. Never
   from `omni.timeline`.
3. **Cold start.** The first frames after `timeline.play()` come from an
   unwarmed frames-in-flight buffer. **Fix:** discard a warm-up burst
   (`SimConfig.warmup_frames = 8`, ≥ the 3-slot buffer plus margin).

Also: `rt_subframes=4` re-renders each frame to kill ghosting after teleports,
and DLSS must be forced to Quality mode (`/rtx/post/dlss/execMode = 2`) because
the default Performance mode produces visible artefacts below ~600×600 — which
is exactly our regime.

**Known 6.0 crash:** changing the physics step rate or per-tick dt from their
defaults *in the full UI app* is a documented fatal crash. Do rate configuration
in headless standalone Python only. `navfm.isaac.app.IsaacApp` defaults to
headless.

All of this is implemented in `IsaacApp.step()`; the contract is that any sensor
or pose read performed after `step()` returns refers to the same instant.

## Scenes

Shipped environment USDs under `${ASSETS}/Isaac/Environments/`:
`simple_room.usd`, `hospital.usd`, `office.usd`, `warehouse.usd`,
`warehouse_with_forklifts.usd`, `warehouse_multiple_shelves.usd`,
`full_warehouse.usd`, `small_warehouse_digital_twin.usd`,
`gridroom_black.usd`, `gridroom_curved.usd`, `default_environment.usd`.

**Matterport3D / HSSD: no first-party import path exists** — I could find no
importer or scene pack in the 6.0 docs. The official alternatives for scene
diversity are **Infinigen**-based procedural generation
(`tutorial_replicator_infinigen_sdg`), **NuRec** neural volume rendering of
reconstructed real scenes (`isaacsim.replicator.nurec_utils`, new in 6.0.1), and
**MobilityGen** (`isaacsim.replicator.experimental.mobility_gen`) which is
purpose-built for mobile-robot trajectory generation and can ingest a ROS
occupancy map via `OccupancyMap.from_ros_yaml`. If you need Matterport, plan a
custom glTF/OBJ → USD conversion.

Scene diversity is the main lever on sim2real generalisation here, so this is
worth real effort: 4 stock scenes is enough for a pipeline demo and **not**
enough for a transfer claim. Use `--group-by scene` splits so the claim you make
is about held-out environments.

## Demonstrator design

The most consequential and least obvious decisions in the whole collector.

**Why a planner, not a random walk.** The models learn a temporal distance
`d(o_t, o_g)`. Under a random walk, temporal distance is uncorrelated with
spatial proximity, so the distance head learns noise — and the distance head is
what the topological localisation in `navigate.py` depends on. The demonstrator
must be approximately optimal.

**Why not *purely* optimal.** A shortest-path demonstrator collapses the state
distribution onto the optimal path and never shows the policy how to recover
from being off it. The reference datasets get recovery coverage for free from
human teleoperation error. We recreate it deliberately: `perturb_fraction: 0.35`
of episodes follow a smoothly-perturbed path (temporally correlated lateral
noise, endpoints exact, every vertex collision-checked).

**Why smooth tracking.** Bang-bang or jerky demonstrations put high-frequency
content into the action labels that a 5-waypoint regressor cannot represent —
it shows up as an irreducible action-loss floor. Pure pursuit with a 0.45 m
look-ahead gives curvature-continuous motion.

**Why nonholonomic by default.** See `docs/METHODOLOGY.md` §7 (C2). Every
platform in the pretraining mix is differential-drive or Ackermann. Collecting
strafing demonstrations moves the label distribution off the pretrained prior's
support. `demonstrator: nonholonomic` is the default; `holonomic` is the
ablation arm, and `BaseKinematics` controls *execution* independently so the
2×2 is clean.

**Rate arithmetic.** At `cruise_v = 0.35 m/s` and 12 Hz, inter-frame spacing is
~0.029 m; with `waypoint_spacing = 3` the effective metric spacing is ~0.088 m,
close to `go_stanford`'s 0.12 m — the nearest platform in the pretraining mix
(TurtleBot2, indoor, 0.5 m/s). Keeping the normalised action scale near a
platform the model has seen is what makes the pretrained prior useful rather
than merely present.

## Episode guards

An episode is **discarded** on: collision or stall (`stall_patience: 40` steps
of commanded-but-no-motion), fewer frames than the target model's minimum
(`TrajectorySpec.min_length`), path length below half the minimum, or any
exception. Each guard exists because the failure is silent otherwise: a
trajectory ending in a wall teaches wall-driving; a stalled one contributes
hundreds of identical frames that dominate the sampler.

Acceptance rate is recorded in `collection_manifest.json`. If it drops below
~70 %, the scene is too cluttered for the footprint or `min_clearance_m` is too
aggressive.

## Reproducibility

Every accepted trajectory's `traj_data.pkl` carries a `metadata` dict with the
full `SimConfig`, `CollectConfig`, `RobotConfig`, the randomisation draw, the
seed and the episode index — so any single trajectory can be regenerated
exactly. `collection_manifest.json` aggregates the run.
