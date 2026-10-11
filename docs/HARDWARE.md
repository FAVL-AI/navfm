# Yahboom ROSMASTER M3 PRO — what is published, what is not

Everything below is sourced from Yahboom's product page, tutorial lessons and
GitHub, or from the component manufacturers. **Yahboom publishes far less hard
mechanical data for the M3 PRO than for its older ROSMASTER models.** Values
they do not publish are marked **UNVERIFIED** and appear in code as
`PROVISIONAL` constants. Do not build a sim2real claim on a guessed number.

## Confirmed

| Item | Value |
|---|---|
| Drive | **Mecanum, 4-wheel omnidirectional**, rear-wheel pendulum suspension |
| Wheels | 4 × **80 mm** mecanum, all four motors encodered |
| Chassis | aluminium alloy, oxidised/sandblasted |
| Battery | 12.6 V, 9600 mAh; low-voltage alarm below 10.3 V; `/battery` topic |
| Compute (SKU options) | Raspberry Pi 5 (8/16 GB), Jetson Nano B01, Jetson Orin Nano SUPER 8 GB, Jetson Orin NX SUPER 8/16 GB |
| ROS | **ROS 2 Humble**. On Pi 5 and Nano B01 the stack runs **inside Docker**; on Orin it runs natively |
| Real-time control | STM32 board over USB-C, micro-ROS agent on `/dev/myserial` |
| Arm | DOFBOT-PRO 6-DOF, ±0.5 mm repeatability, ~30 cm reach, ~410 g payload |
| Camera | **Orbbec DaBai DCW2**, binocular structured light + RGB, 40 mm baseline |
| RGB | 1920×1080@15 / 1280×720@15 / 640×480@15 / 640×360@15; **rolling shutter**; **15 fps cap at every resolution** |
| RGB FOV | 16:9 → H 86° / V 55°; **4:3 → H 64° / V 55°** |
| Depth | 640×400@15, global shutter, H 91° / V 62°, 0.15–5 m, <1 % @1 m, hardware D2C |
| Camera IMU | **none** |
| LiDAR | 2 × T-mini Plus, 360° 2D ToF, front-right + rear-left. 4000 Hz ranging, 6 Hz scan (6–12 adjustable), 0.05–12 m, 20 mm accuracy, 0.54° resolution |
| LiDAR topics | `/scan0` (left-rear, `laser0_frame`), `/scan1` (right-front, `laser1_frame`) |
| IMU | 9-axis on the STM32 board → `/imu/data_raw`. **Part number UNVERIFIED** |
| Odometry | wheel encoders, computed on the STM32 → `/odom_raw`, node `/YB_Node` |
| Control topic | `/cmd_vel` (`geometry_msgs/Twist`) with `linear.x`, `linear.y` **and** `angular.z` all used |
| TF frames | `odom`, `base_footprint`, `base_link`, `laser0_frame`, `laser1_frame`, `camera_link` |

## Unpublished — measure these before claiming anything

| # | Missing | How to get it |
|---|---|---|
| 1 | Wheelbase, track width, chassis L×W×H, mass | the **3D_Model_File** CAD bundle, or measure the `yahboomcar_description` URDF joint origins |
| 2 | **Max linear and angular velocity** | run Yahboom's own `ros2 launch calibration calibrate_linear.launch.py` and `calibrate_angular.launch.py`. ~10 minutes, and it is the correct method. Documented example commands use 0.1 m/s and 1.0 rad/s but those are illustrative, not limits |
| 3 | Camera mounting height and x-offset | the URDF — but note the camera is on the **arm**, so the transform is a function of joint angles, not a constant |
| 4 | IMU part number | STM32 schematic in the Firmware_DriverFile bundle, or `i2cdetect` |
| 5 | Whether `/odom` is EKF-fused with the IMU, and with what config | inspect the launch files in `yahboomcar_ws` on the robot image. The `/odom_raw` → `/odom` naming strongly implies an `imu_filter_madgwick` + `robot_localization` chain, but this is **UNVERIFIED** |

### Provisional values currently in the code

`navfm.control.M3PRO_LIMITS`:
`max_v = 0.45 m/s`, `max_w = 1.2 rad/s`, `max_vy = 0.35 m/s`,
`max_a = 0.8 m/s²`, `max_alpha = 3.0 rad/s²`.

`navfm.isaac.robot.CameraRig`: `x_offset = 0.16 m`, `height = 0.28 m`,
`pitch = 0°`, `hfov = 64°`.

`navfm.isaac.robot.M3PRO`: `footprint_radius = 0.24 m`.

`max_v` and `max_w` matter twice over: they bound the demonstrator, and they set
the deployment-time unnormalisation constant (the reference stack scales
predicted waypoints by `max_v / frame_rate`; its defaults are 0.2 m/s at 4 Hz).
Getting them wrong rescales every command the robot executes.

## Downloads

All from the [tutorial page](https://www.yahboom.net/study/ROSMASTER-M3PRO):

| Bundle | Contains |
|---|---|
| Code-Firmware | `yahboomcar_ws` incl. `yahboomcar_description` (urdf + meshes), `M3Pro_demo` |
| 3D_Model_File | CAD — authoritative for geometry |
| Robot_Image_System_File | full SD/SSD image; the description package is also inside |
| Instruction_Manual | possible source for the missing dimensions |

Yahboom's [GitHub repo](https://github.com/YahboomTechnology/ROSMASTER-M3PRO) is
a README and a photo — **no source, no URDF, no meshes**. Same for the sibling
ROSMASTER repos.

Third-party structural reference:
[`automaticaddison/yahboom_rosmaster`](https://github.com/automaticaddison/yahboom_rosmaster)
— a well-organised ROS 2 package set for the **ROSMASTER X3** (also mecanum)
with `rosmaster_x3.urdf.xacro`, modular sensor xacros and `ros2_controllers.yaml`.
Different sensor suite, no arm, geometry match unverified. Good template, not a
source of numbers.

## Implications for this project

1. **Mecanum breaks an implicit assumption of the pretrained models.** Every
   platform in the GNM/ViNT/NoMaD training mix is differential-drive or
   Ackermann. The action space admits lateral motion; the training distribution
   barely uses it. This is hypothesis H2 in `docs/EXPERIMENTS.md` and the most
   novel question the project can ask.
2. **The camera is on the arm.** The GNM format has no field for a time-varying
   camera transform and the models assume a static viewpoint. We lock the arm to
   a stowed pose. This is a deviation from stock configuration and must be
   stated in any write-up.
3. **15 fps rolling-shutter RGB.** Do not collect above 15 Hz — a higher sim
   rate would be a fidelity claim the hardware cannot honour. The rolling
   shutter is an unmodelled appearance gap under fast yaw.
4. **ROS 2 Humble constrains the sim host to Ubuntu 22.04**, since Isaac Sim
   supports Humble only there (Jazzy is the 24.04 recommendation). GLIBC 2.35 on
   22.04 is exactly Isaac Sim 6.0.1's minimum — no headroom.
5. **Dual LiDAR is available but unused.** GNM-family models are RGB-only. The
   LiDARs are still valuable: use them to build the ground-truth occupancy map
   for closed-loop collision scoring on the real robot, which is otherwise hard
   to measure objectively.

## Isaac Sim 5.1 — verified invocation (measured 2026-08-07)

Recorded because it was got wrong once: a search for launcher-bundle artefacts
concluded Isaac Sim was absent when it is pip-installed in a conda environment
(`gates/failures/F-PILOT-1.md`).

| | |
|---|---|
| Interpreter | `~/miniforge3/envs/isaac/bin/python` — Python 3.11.15 |
| Isaac Sim | 5.1.0.0, 25 `isaacsim-*` packages |
| Launcher artefacts | **none** — this is a pip install, so there is no `python.sh` or `isaac-sim.sh` |
| Headless bring-up | `SimulationApp({"headless": True})` → app ready in **68.5 s** (first run; shader/kernel caches warm afterwards) |
| GPU seen by Warp | RTX 4080 SUPER, 16 GiB, sm_89; CUDA Toolkit 12.8, Warp 1.8.2 |

**The 5.x PRIMARY namespaces are not importable until `SimulationApp` has
started.** Kit's extension system injects them at startup, so a bare
`import isaacsim.core.api` at module scope raises `ModuleNotFoundError` and this
is expected, not a broken install. Verified importable *after* startup:
`isaacsim.core.api`, `isaacsim.core.prims`, `isaacsim.sensors.camera`,
`isaacsim.storage.native`. `SimulationContext.initialize_physics()` plus stepping
verified in the same run.

`import isaacsim` fails in `~/.venv-train` by design — the two environments are
never merged, and that failure is not evidence about the machine.

**Reconfirmed 2026-09-05**, during the G2 runtime reproduction. Same interpreter
and same Isaac Sim 5.1.0.0 / 25 distributions; `nvidia-smi` reports NVIDIA
GeForce RTX 4080 SUPER, **driver 580.173.02**, 16376 MiB — the driver version the
2026-08-07 record did not carry. Method: `nvidia-smi --query-gpu=name,
driver_version,memory.total --format=csv,noheader` plus `importlib.metadata`
over the `isaacsim-*` distributions, captured before execution into
`~/navfm-runtime-evidence/g2-20260905/isaac_runtime_identity.json`. Three
headless harnesses then ran to completion against PhysX in that session, which
is behavioural confirmation rather than a version string alone. This is an
identity and availability check; **no throughput or performance figure is
claimed.**
