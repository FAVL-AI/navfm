# ImageNav episode contract — DRAFT, not preregistered

**Status: draft specification. Not an amendment. Not in force.**

Held here deliberately. The standing gate is *no further protocol edits before
Amendment 5 is adjudicated under trigger-3*, and this document would otherwise
become Amendment 6 and jump that queue. When Amendment 5 is committed, this
becomes a candidate amendment in its own right and must be adjudicated on its
own account.

**Scope rule, from the supervisor and load-bearing:** this contract shall NOT be
retrofitted onto the two existing compatibility trajectories. Those remain valid
as what they are — 2/2 collected, 12/12 PASS, accepted by the unchanged ViNT
data path. The contract begins with *newly generated evaluation episodes* where
the goal is genuinely chosen and frozen before the rollout.

## The one property everything else protects

> The goal must exist as an independent, predeclared object before the robot
> begins moving. A final frame taken after a rollout must never be relabelled as
> the goal.

## Capture order (the goal is sealed before the robot moves)

```
freeze experiment config -> create episode_id -> choose goal BEFORE rollout
 -> place camera at goal pose -> capture independent goal RGB
 -> compute goal_image_sha256 -> record goal_pose
 -> record camera/config provenance
 -> write pre_rollout_manifest.json
 -> compute pre_rollout_manifest_sha256
 -> SEAL GOAL
 -> reset robot to start pose -> capture start RGB -> record start_pose
 -> hash start image -> verify start != goal
 -> begin rollout (record RGB + pose + yaw + timestamp per frame)
 -> policy stops -> capture final RGB -> record final_pose -> hash final image
 -> compare final against the PREDECLARED goal
 -> compute only metrics whose inputs exist
 -> evidence report -> W&B Artifact -> archive manifest + digests + env + commit
```

The goal image must not be: copied from the rollout after seeing the outcome;
selected because the robot finished there; replaced after a failed episode;
regenerated with a different camera configuration; or cropped/resized
differently from the model's observations. Goal RGB and rollout RGB use the same
declared camera pipeline unless an amendment says otherwise.

## Manifest fields

`episode_id`, `goal_defined_before_rollout: true`; `start{frame, pose{x,y,yaw},
image_sha256}`; `goal{source: independent_goal_capture, pose{x,y,yaw},
image_sha256}`; `final{frame, pose{x,y,yaw}, image_sha256}`;
`evaluation{goal_tolerance_m, goal_yaw_tolerance_deg}` both frozen before
rollout; `provenance{scene_id, scene_digest_sha256, robot_representation,
camera_id, camera_intrinsics_digest, camera_extrinsics_digest, controller_id,
model_id, checkpoint_sha256, code_commit, config_sha256, seed}`.

Per frame: `frame_id, timestamp, rgb_path, rgb_sha256, x, y, yaw, action,
stop_signal`; where available also collision state, executed linear/angular
velocity, model output, distance prediction, waypoint prediction, termination
state. These are what later diagnose overshoot, hesitation, late stopping and
never-stop.

## Mandatory invariants — all PASS, or the episode is BLOCKED

Goal chosen before rollout · goal image independently captured · **goal
cryptographically sealed before the start state is captured** (see below) ·
goal pose exists · goal image SHA-256 exists ·
start pose exists · start image SHA-256 exists · start pose differs from goal
pose · start image differs from goal image · final pose recorded after rollout ·
final image SHA-256 exists · RGB camera verified egocentric/front-facing · all
poses finite · all images readable · manifest immutable after rollout starts ·
tolerances declared before rollout.

Any failure gives **`BLOCKED — NOT ADMISSIBLE FOR EVALUATION`**, never partial
acceptance.

## Proving the goal existed beforehand

**Not by filesystem timestamps.** File modification and creation times are
mutable and change on copy, extraction and restoration, so an archive round-trip
would silently destroy the evidence — a check that certifies nothing after the
first `tar -x`. Ordering is established from the experiment record and a
cryptographic seal instead.

Before the start state is captured or any control action is issued, the goal
image bytes, `goal_pose`, camera identity/configuration and experiment
configuration are hashed into `pre_rollout_manifest.json`, and that manifest
itself receives a digest. Sealing precedes the start capture, not merely the
rollout.

The admission checker asserts:

```
goal_defined_before_rollout == true
goal_image_sha256           present
goal_pose                   present
pre_rollout_manifest_sha256 present

goal_capture_sim_step < start_capture_sim_step <= rollout_start_sim_step
first_action_sim_step > goal_seal_sim_step
```

Simulation step, not wall-clock and not file mtime: it is recorded by the
runtime, monotonic within an episode, and part of the sealed record.

**Append-only event ledger, each row carrying the previous row's digest:**

```json
{"seq":1,"event":"GOAL_CAPTURED",   "prev_sha256":null,        ...}
{"seq":2,"event":"GOAL_SEALED",     "prev_sha256":"<row 1>",   ...}
{"seq":3,"event":"START_CAPTURED",  "prev_sha256":"<row 2>",   ...}
{"seq":4,"event":"ROLLOUT_STARTED", "prev_sha256":"<row 3>",   ...}
{"seq":5,"event":"ROLLOUT_ENDED",   "prev_sha256":"<row 4>",   ...}
```

Retroactively substituting the goal then breaks the chain and is detectable,
which relabelling a final frame under a fresh timestamp is not.

## Termination

`MODEL_STOP`, `TIMEOUT`, `COLLISION_TERMINATION`, `SAFETY_TERMINATION`,
`SYSTEM_FAILURE`. **A timeout is not an ordinary model stop** and must not be
recorded as one.

## Metrics, and what each still needs

```
NE = distance(final_position, goal_position)          -- needs valid metric poses
SR = successful episodes / valid evaluation episodes  -- needs frozen criterion
SPL                                                    -- ALSO needs shortest_path_length_m
```

Whether SR requires position only, or position **and** yaw, must be frozen in
the evaluation protocol before execution and never chosen after observing
results. Each episode needs `shortest_path_length_m` and
`executed_path_length_m`, the former from a frozen, verified planner or
navigation-mesh procedure. Absent it: `SPL = BLOCKED, reason = shortest-path
reference unavailable`.

## Episode package

```
episode_<id>/ manifest.json
  goal/goal_rgb.jpg
  rollout/000000.jpg … final.jpg
  trajectory/{poses,yaw,timestamps,actions}.npy
  evidence/{compatibility_report,evaluation_report,digests,environment}.json
```

Manifest hashes the files; an experiment manifest hashes all episode manifests.
The chain another person needs: experiment manifest -> episode manifest -> goal /
start / final image digests -> trajectory digest -> config digest -> checkpoint
digest -> code commit.

## Cross-model rule

One frozen episode population, identical for GNM, ViNT and NoMaD: same episodes,
same independent goal images, same goal poses, same camera, same tolerances,
same shortest-path references, same success definition, same metric
implementation. No model receives different goals, easier starts, different
tolerances or a different population.

This yields **controlled navigation evaluation reproducibility** — a third thing,
distinct from Amendment 5's checkpoint/inference column and its public-data
training column. It is still not exact reproduction of the papers' real-world
numbers, and must not be described as such.

## Precondition before implementing any of this

**Run a duplication audit first.** The July fork already contained an evaluation
lineage nobody in this repository knew about, and `gnm-vlnverse-baseline`
carries tags through `v0.6-stop-head-train-val-protocol` — stop-policy work that
is exactly the termination behaviour this contract specifies. Search for
existing episode manifests, goal-image capture, shortest-path/navmesh
references and stop-policy implementations before writing new ones. That lesson
cost a full session once already.
