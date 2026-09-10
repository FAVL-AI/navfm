# BO-03 / BO-10 — a newly collected Hospital trajectory, accepted by all three frameworks

**Frozen 2026-09-11.** Frank Asante Van Laarhoven.

---

## Result

**A newly collected Hospital simulator trajectory was written in the published
loader-facing trajectory format and successfully consumed by the pinned GNM, ViNT
and NoMaD data paths.**

| Framework | Samples | Tuple | Action | Context |
|---|---|---|---|---|
| GNM | 1190 | 7 | `[5, 4]` dx/dy/cos/sin | 5 |
| ViNT | 1190 | 7 | `[5, 4]` dx/dy/cos/sin | 5 |
| NoMaD | 1189 | 7 | `[8, 2]` dx/dy | 3 |

All three from the **same** trajectory, at pinned upstream `dca7981`. Distances
are `int64`, action values finite, no synthetic fallback anywhere.

The sample counts are not expected to match. The three frameworks declare
different context sizes and prediction horizons, so the number of valid sampling
windows in one trajectory differs between them by construction.

---

## Limitation

**This proves framework/data compatibility, not successful navigation or dataset
quality.** The collected episode reached the maximum step budget and stopped
**1.679 m from the sealed goal**, outside the **0.20 m** goal tolerance.

**One trajectory is sufficient for an execution/compatibility proof but is not
sufficient for training, validation and held-out evaluation.**

The trajectory was admitted because `reached_goal` is not among the frozen
post-episode conditions — those are the six adequacy thresholds plus data
integrity. It was admitted for meeting what was frozen, **not** because
goal-reaching was checked and passed.

---

## Status

| | |
|---|---|
| `BO-03_REAL_DATA_COMPATIBILITY` | **COMPLETE** |
| `BO-10_PIPELINE_COLLECTION` | **COMPLETE** |
| `BO-10_HOSPITAL_COLLECTION` | **COMPLETE_FOR_COMPATIBILITY_PURPOSE** |
| `NAVIGATION_TASK_COMPLETION` | **FAIL / NOT ACHIEVED** |
| `DATASET_QUALITY_FOR_FINE_TUNING` | **NOT ESTABLISHED** |
| `BO-11_FINE_TUNING` | **NOT_READY_INSUFFICIENT_ADMITTED_DATA** |

The Hospital collection status is deliberately not a bare *COMPLETE*, which
would read as successful navigation.

---

## The trajectory

`runs/bo10/hospital_bo10_run_00001` — immutable, `e2_eligible = false`.

- 1200 frames, 1200 matching images, all positions and yaws finite
- 25.707 m travelled, 17.976 m start-to-end separation
- **3 distinct realised turn events**, 1189 limiting context windows
- goal image sealed **before** first motion and byte-distinct from the final
  observation
- controller identity unchanged across the episode
- zero collision-guard rejections across 1200 applied poses
- `traj_data.pkl` SHA-256 `40b9890d96973b3b910e218cfd0e64fd5453e881822ebcce62bd7da99b30ef09`

`hospital_bo10_run_00000` remains **`COLLECTED_NOT_ADMITTED`** and untouched: its
realised path contained one 172° turning episode rather than three.

---

## An observation that is not yet a finding

| | planned | realised |
|---|---|---|
| turn magnitudes | 50.7°, −58.4°, 94.4° | 131.3°, −101.9°, 166.3° |
| path length | 23.25 m | 25.71 m |

Realised turns were **amplified** relative to plan and the realised path was
longer, terminating at `max_steps`.

**Causal classification: UNRESOLVED.** It is not asserted that overshoot caused
the amplification, that amplification caused `max_steps`, that pure pursuit is the
root cause, or that route geometry is. The observations are *consistent with*
execution deviation; causality is not established from one production trajectory.

`max_steps` being reached does not by itself show the budget is too low. Two
different defects would look identical here — a route that should have completed
inside the budget but wasted it, versus a budget structurally insufficient for the
route — and they are not yet distinguished.

---

## What may and may not be claimed

**May:** newly collected Hospital simulator data exists · official loader-facing
structure was produced · GNM accepts it · ViNT accepts it · NoMaD accepts it ·
the goal image was independently sealed before motion · provenance and admission
evidence exists · the BO-03 compatibility question is closed.

**May not:** successful Hospital navigation · reliable goal reaching · stopping
success · any dataset-quality claim · model-performance improvement · sim-to-real
success · real-robot safety · contact-dynamics fidelity · physical M3 Pro
clearance.

Open throughout: **F-TWIN-1**, `PHYSICAL_M3_PRO_GROUND_CLEARANCE = NOT_MEASURED`,
`DYNAMIC_WHEEL_DRIVE_V1 = DEFERRED`.

---

## How the trajectory came to be admissible

Five instrument defects were found and repaired before this trajectory existed.
Each was capable of producing a confident wrong answer.

1. **The occupancy map decoded unknown cells as free space.** 54% of Hospital's
   map was `UNKNOWN`; 62% of the planner's apparent free space came from cells the
   generator had declined to classify.
2. **The map omitted solid geometry.** A reception desk (0 of 725 cells) and a
   supply cart (0 of 72) were entirely absent. Replaced with a validated
   cell-volume PhysX probe; 1,089 colliders now checked, zero planner-invisible.
3. **The collector could not drive the robot.** Articulation root-velocity
   commands moved it 0.0036 m in 40 steps. Replaced by a preregistered kinematic
   drive with an independent swept-collision invariant.
4. **The realised-turn metric was representation-dependent.** It counted 3 turns
   on a planned polyline and 1 on the driven path. Corrected so event semantics
   apply to continuously curved executions.
5. **The route population produced mostly straight routes.** A preregistered
   turning population with spatially separated anchors produced 20 admissible
   candidates where the shortest-path population produced 3.

Alongside these, eight defects were found in the *validation apparatus itself* —
recorded in `gates/failures/H-VALIDATION-HARNESS.md`. Seven pointed toward false
failure; the eighth was the evidence guard correctly refusing to write an
unserialisable artefact rather than a partial one.

The two most recent are worth naming here. **`H-LMDB-1`**: ViNT and NoMaD first
reported *failure* because three models shared one LMDB cache in one process —
reporting that verbatim would have been a false negative against upstream on the
exact question this tranche existed to answer. **`H-EVIDENCE-KEY-1`**:
`emit_evidence` refused to write a 96-candidate result whose failure-distribution
dictionary used tuple keys, rather than writing a version that parsed and
silently lacked the distribution.

---

## Next

A separate execution-completion diagnostic, preregistered and **not executed**:
`BO10_EXECUTION_COMPLETION_DIAGNOSTIC_V1` — why did an otherwise admissible
trajectory terminate at `max_steps` 1.679 m from its goal?

BO-11 does not start until a collection plan exists. One compatibility trajectory
must not become both training and evaluation data.
