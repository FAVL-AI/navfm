# `F-DRIVE-1` — the collector cannot drive the robot

**Status: OPEN. Blocks BO-10 production collection.** Found 2026-09-10, on the
first execution of `run_episode` against an admitted route.

## What was observed

The episode ran and was rejected by the collector's own `stalled` guard after
51 frames: velocity was commanded and the base did not move.

Isolated with a direct measurement — teleport to the admitted start, then
command a constant 0.35 m/s forward for 40 steps:

| | |
|---|---|
| teleport landed at the start pose | yes, to 4 decimal places |
| timeline playing | yes |
| articulation reports velocities | yes, non-zero |
| **displacement over 40 steps** | **0.0036 m** |
| **displacement with `render=True`** | **0.0000 m** |

The trace shows the base vibrating in place: x moves between −39.9028 and
−39.9023 and returns.

## Root cause

`SimRobot.set_body_velocity` sets the **articulation root velocity** via
`Articulation.set_velocities`. For an articulation whose wheels are in contact
with the ground, the PhysX solver overrides an imposed root velocity every step:
the constraint and contact solve wins, and the commanded velocity is discarded
before it produces displacement.

The design intent is documented at the top of `src/navfm/isaac/robot.py`:

> The base is velocity-driven, not wheel-driven. […] We therefore command
> body-frame velocity on the articulation root and spin the visual wheels
> kinematically.

That decision is defensible on its own terms — the label pipeline only reads the
base pose, so wheel-level fidelity buys little. **It was never validated.** The
docstring asserts a mechanism that does not move this robot.

## Why it survived this long

`navfm/isaac/` was carried as "implemented but NEVER EXECUTED", and every
Isaac-dependent result up to now measured something other than driving. G7's
camera gate moved the robot **by `teleport()`**, not by `set_body_velocity`, and
recorded 2.236 m of motion — which reads like evidence the robot moves, and is
not evidence that it can be *driven*.

This is precisely the genus the repository already names. FL-013: "optimizer.step()
returning is not evidence the model changed". The `G8_CONTROLLER_IDENTITY` gate
written earlier in this same session carries the warning in its own docstring:

> A controller can issue commands to an articulation that is wedged, unauthored
> or asleep, and the digest is identical in every case. […] Realised motion is a
> POSTCONDITION.

The gate was right, the separation was right, and the thing it warned about is
what happened.

## What this does NOT invalidate

- The obstacle-map repair and its acceptance. Those measure the map, not motion.
- `HOSPITAL_BO10_REPAIRED_MAP_RERUN_V1`: 3 of 96 admissible. Route admission is
  a read-only geometric study and drives nothing.
- G3–G7, G9, G10-as-prediction. None depends on the base moving.
- The frozen Hospital and Office route-set results.

## What it does block

BO-10 production collection, and therefore the GNM/ViNT/NoMaD real-trajectory
compatibility proof. No trajectory has been written.

## The decision this needs, which is not mine to take

Two repairs are available and they are **not scientifically equivalent**:

**A. Kinematic base drive.** Integrate the commanded twist and set the base pose
each step, bypassing contact dynamics. Cheap, robust, and produces exactly the
`(image, SE(2) pose)` the GNM format needs. It abandons contact physics: the
robot would pass through anything the planner's map failed to represent, so the
obstacle map becomes the *only* thing standing between the dataset and a
trajectory that drives through furniture. That coupling is worth stating plainly
given what this session found in the map.

**B. Wheel-level drive.** Command the wheel joints, as `robot.py`'s own docstring
suggests via `isaacsim.robot.wheeled_robots.HolonomicController`. Physically
faithful, and it interacts with two open findings: F-TWIN-1 (box colliders in the
twin are squared) and FL-002 (wheel joints imported with zero stiffness and zero
damping). Mecanum rollers are also not represented in the URDF, which is the
reason A was chosen originally.

The choice changes what a collected trajectory *means* — whether it is a
kinematic path through a validated map, or a physically driven one. It is a
scientific-semantic decision, not an implementation detail, so it is recorded
here rather than made.
