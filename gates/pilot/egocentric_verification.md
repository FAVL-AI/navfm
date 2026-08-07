# Egocentric-camera verification — `pilot_0001` and `pilot_0002`

Evidence about the two already-published pilot trajectories. Raw measured values
in `egocentric_verification.json`; the probe that produced them is
`scripts/egocentric_check.py`.

## The question

Are the captured RGB observations rendered from a camera rigidly mounted on the
simulated robot, or from an Isaac Sim world / viewport / spectator camera? The
images alone cannot answer this — a world camera placed at robot height, looking
forward, produces frames of the same visual character. It must be established
from the simulator configuration and from behaviour.

## The fixed transform

```
T_world_camera(t) = T_world_robot(t) x T_robot_camera
```

`T_robot_camera` is set once at scene build and never touched during capture:

| | |
|---|---|
| Camera prim | `/World/pilot_robot/camera` |
| Parent prim | `/World/pilot_robot` — the robot, **not** `/World` |
| Translation | `(0.10, 0.00, 0.12)` m in the robot frame |
| Rotation | `(90, 0, -90)` deg XYZ — puts the USD camera's `-Z` onto the robot's `+X`, Z up |
| Focal length | 18.0 mm |

No look-at, no tracking target, no orbit control, no viewport inheritance, and
no reorientation independent of the robot.

## Three independent probes

| Probe | What it establishes | Result |
|---|---|---|
| **A. Structural** | the camera prim's parent is the robot prim | `/World/pilot_robot` — **PASS** |
| **B. Extrinsic** | the camera's local transform is constant across poses | constant — **PASS** |
| **C. Behavioural** | rotate the robot **+90 deg in place, zero translation**; the view must swing to the new heading | mean abs pixel change **54.852** — **PASS** |
| C. control | translate 0.6 m with no rotation | mean abs pixel change **8.591** — **PASS** |

**Interpretation of probe C.** It is the decisive one. Under pure robot rotation
with no translation, a world or spectator camera would continue to observe the
same part of the environment and would be expected to show approximately **zero**
change. The measured change is 54.852, roughly six times the change produced by
translating 0.6 m. The view follows the robot's heading.

## Conclusion

**Both pilot trajectories use robot-mounted forward-facing observations.**

## What this does NOT establish

The verification is narrow and must not be read as upgrading the pilot:

* it does **not** make the pilot an admitted training dataset;
* it does **not** validate a Yahboom M3 Pro model — the robot is a cube proxy;
* it does **not** validate a hospital scene; the scene is `simple_room`;
* it does **not** establish a goal-image contract — start and goal observations
  are not recorded as designated endpoints;
* it does **not** constitute a camera-calibration record; intrinsics and
  extrinsics are not carried in the trajectory metadata;
* it does **not** complete G1 or G2, and does not open general collection;
* the images are 320x240, not 640x480.

The pilot proved exactly one thing, and this verification adds exactly one more:
two trajectories collected by our own Isaac Sim pipeline can be represented in
the agreed Option 1 ViNT format and are accepted by the unchanged ViNT data
path, and their RGB observations are egocentric.
