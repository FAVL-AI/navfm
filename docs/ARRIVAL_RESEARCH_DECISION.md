# Arrival under illumination shift: research decision and pilot protocol

Starting commit `cbddf90`, branch `agent/engineering-recording`. Phase A was
read-only. Candidate title under review: "Verified Arrival under Illumination
Shift for RGB Image-Goal Navigation". **Decision: REVISE.** The action-conditioned
verifier is not implemented in this milestone.

## Verified repository state

| Item | Evidence | State |
| --- | --- | --- |
| Corpora | `OPTION1_RESULTS.md`, `SIM_TO_REAL_RESULTS.md` | 10-trajectory original and 35-trajectory expanded admitted corpora (31/2/2) |
| Control | articulated control 01-06 | Sphere-wheel proxy qualified for sampled commands at 0.1 m/s, +/-0.4 rad/s only |
| Contact detection | positive control | One deliberate wall contact reported; five free cases report none |
| Reference stop | `src/navfm/collection/rgb_baseline.py` | Three consecutive ViNT temporal distances <=1 and waypoint <=0.15 m, latched; enabled in live runs |
| Live outcome | `option1-live-matched-20261007-02.json` | 0/6 arrivals, 0 stop events, all timeout |
| Lighting | `scripts/collect_option1.py` | One fixed rig: DistantLight 1500, DomeLight 800, in every corpus |

**Horizon claim: RETRACTED.** The Phase A draft argued that the 0.1 m/s cap
times the 20 s timeout (2.0 m) was below teacher route travel, so 0/6 arrivals
were a horizon artefact. Independent red-team review refuted it, and the
figures were re-derived from `frozen_routes.json`. Entering the 0.5 m radius
needs about 1.5 m of straight-line progress (start-goal 2.000 m S-bend, 1.970 m
junctions), or about 1.97 m / 1.60 m along the polylines (2.467 m / 2.104 m).
Both fit within 2.0 m. Realised paths were 1.82-1.95 m, yet final errors were
0.55-1.32 m: **the policy deviated from the route.** The 0/6 result is evidence
of closed-loop policy failure under this controller and speed cap, not only of
the budget.

**Stop rule cannot fire (VERIFIED from logs and source).** The ViNT distance head
regresses a step count (`(goal_time - curr_time) // waypoint_spacing`), capped at
`max_dist_cat` 20, with negatives labelled 20. On this 4 Hz corpus one unit is about
0.05 m. The reference threshold `<=1` therefore asks for about 0.05 m, roughly 10x
tighter than the 0.5 m success radius. Logged predictions never fell below 4.2;
they reached 4.2-4.7 on the junction routes, then rose back to about 10. The
waypoint `<=0.15 m` clause is close to always true at cruise, so it does not
discriminate. Upstream uses `close_threshold` to localise to a topological node,
not as a stop.

**Speed/time-base confound.** Teachers drove at 0.20-0.22 m/s; live runs cap
0.1 m/s. The six-frame 4 Hz context therefore spans about half the motion seen in
training. This is a candidate cause of the deviation, not yet tested.

**Split contamination.** `junction_run_0000/0001` are `split: test`. They were
already used in earlier live engineering runs, so the corpus test split is not
untouched and cannot be confirmatory. Any confirmatory claim needs new held-out
routes.

## Literature comparison

Verified against the arXiv abstract/HTML, proceedings pages or official repositories on 2026-10-09.
"Venue" distinguishes peer review from preprints.

| Work | Venue / status | Inputs | Stopping / verification | Conditions | Closest overlap |
| --- | --- | --- | --- | --- | --- |
| SLING, Wasserman, Yadav, Chowdhary, Gupta, Jain | CoRL 2022, PMLR 205:666-678 | (not stated on page) | Switches between goal discovery and geometric last-mile navigation | Sim + real robot | Last-mile precision |
| AnyImageNav, Deng, Yuan, Fang | arXiv 2604.05351 v3 preprint | RGB-D + pose | Relevance proximity gate, VGGT self-certification confidence, refinement on running max | Habitat only; no lighting experiments | Confidence-gated arrival |
| IEVE, Lei, Wang, Zhou, Li, Li | CVPR 2024; code XiaohanLei/IEVE | RGB-D modular | Explicit explore/verify/exploit actions; sequential matching; approach to confirm | HM3D-SEM sim | Ternary decision and act-to-confirm |
| SaferPath, Zhang, Jiang, Chen | arXiv 2603.01898; "ICRA 2026" label, acceptance not shown | Visual | Traversability map + MPC safety refinement; no stopping described | Unseen obstacles, narrow corridors | Safety comparator only |
| CARE, Kim, Sim, Kim, Sycara, Nam | CoRL 2025, arXiv 2506.03834 | RGB | Monocular depth + repulsive fields on ViNT/NoMaD; no stopping | Three real robots | Safety comparator only |
| Guerrier, Soma, Pavlasek, Beltrame | arXiv 2603.25937 v2 preprint | RGB | Evaluates GNM, ViNT, NoMaD, NaviBridger, CrossFormer | Real; motion blur, sunflare | Lookalike goal-recognition errors |
| RobustNav, Chattopadhyay, Hoffman, Mottaghi, Kembhavi | ICCV 2021; allenai/robustnav | RGB | Corruption benchmark incl. "Low Lighting" | PointNav/ObjectNav sim | Lighting degradation precedent |
| Tokyo 24/7, Torii et al. | CVPR 2015 | RGB | Day/sunset/night place recognition; later work reports >95% night Recall@1 with retrieval + re-ranking | Real query photos | Matching under illumination is mature |
| IGL-Nav, Guo et al. | ICCV 2025, arXiv 2508.00823 | RGB + predicted depth | 3DGS coarse-to-fine goal localisation | Sim + real | Geometric goal localisation |
| Suomela et al. | arXiv 2509.11791 v2, "ICRA 2026 camera ready" | (not stated in abstract) | Pretrained-representation policy, simulator-trained | Real wheeled robot, drone | Sim-to-real enabling evidence |
| GNM / ViNT / NoMaD | upstream `dca7981` | RGB history + goal RGB | Predicted temporal distance; upstream deployment stops at the final topological-map node | - | Backbone and reference stop |

Added after red-team review and verified at the proceedings pages:
Krantz et al., "Navigating to Objects Specified by Images", ICCV 2023
(arXiv 2304.01192). Its modular instance image-goal system re-identifies the goal
by matching features between view and goal image; 88% real-robot success is
reported; the exact matcher is not confirmed here. Hausler et al., Patch-NetVLAD,
CVPR 2021 (arXiv 2103.01486): patch descriptors reported invariant to
illumination and viewpoint. Chaplot, Parisotto, Salakhutdinov, Active Neural
Localization, ICLR 2018 (arXiv 1801.08214): learned actions to localise in fewer
steps, the closest precedent for action-conditioned verification. Unverified
leads, not to be cited until checked: Furgale & Barfoot (JFR 2010) and Paton,
Pomerleau & Barfoot (IROS 2016), on visual teach-and-repeat under appearance
change. ViNT topological deployment is structurally teach-and-repeat.

Corrections: AnyImageNav's RGB-D + pose inputs and its gate/self-certification
come from the v3 HTML method section (observation `o_t = (I_t, D_t, T_t)`), not
the abstract. The Tokyo 24/7 ">95% night Recall@1" figure came from an unnamed
re-ranking benchmark in search results and is withdrawn until sourced.

Absence of illumination-arrival experiments in these papers does not establish
a literature-wide gap.

## Tough-reviewer critique

1. **The failure is not shown.** No illumination variation exists in any corpus,
   and no episode has reached the goal region, so illumination-induced wrong stops
   have never been observed.
2. **The baseline is incomplete.** The reference stop has never fired, so its
   nominal false-arrival rate is unmeasured.
3. **The decision structure is not new.** IEVE publishes an explicit verify step
   and approach-to-confirm. AnyImageNav publishes confidence-gated arrival
   (with depth and pose).
4. **The obvious alternative is strong.** A feature-matching inlier check against
   the goal image plus hysteresis may solve the problem; it must be a baseline.
5. **What may remain open is narrow:** a bounded, RGB-only arrival check on a
   map-free ViNT-class policy, deployable on a low-cost robot. Treat it as a
   NEW COMBINATION / NEW EXPERIMENT hypothesis, not a scientific contribution.
6. **The data cannot yet support the claim.** Five corridor families with one
   primitive box; 2 development and 2 test trajectories; no lookalike hard
   negatives. Renderer intensity is not lux; real auto-exposure would confound
   illumination.

## Revised decision after red-team

The illumination study is **not admissible yet**: its prerequisite arrival
signal fails under nominal lighting. A wrong-stop rate pinned at zero by a
threshold that cannot fire cannot respond to illumination (floor effect).
**The illumination verifier is REJECTED as the next step.** Work continues
on baseline qualification: why the policy deviates, and whether any RGB arrival
signal from the backbone tracks true distance. The pilot protocol below is
**NOT FROZEN** (red-team verdict DO-NOT-FREEZE, archived under
`gates/redteam/`).

Scientific decision for Frank: whether paper 1 (a) re-scopes to a characterised
arrival/distance-signal failure of ViNT-class RGB policies, with illumination
as one later factor, or (b) first repairs the backbone (speed-matched data,
adequately budgeted fine-tuning of the distance head) and then returns to
illumination.

## Original revised plan (superseded where it conflicts with the above)

- **H0 (precondition).** With a horizon allowing at least 2x teacher route length
  at the qualified 0.1 m/s cap, ViNT plus the reference stop is measured for
  arrival, correct stop, wrong stop and overshoot under nominal lighting.
  If it does not arrive, the study becomes a policy-failure study.
- **H1 (diagnostic).** On teacher poses replayed under controlled relighting,
  goal/live illumination mismatch reduces the temporal-distance signal's
  discrimination of goal-region frames from non-goal and lookalike frames,
  and raises the wrong-stop rate at a development-calibrated threshold.
  **Falsifier:** discrimination and wrong-stop rate within pilot noise of the
  matched-lighting condition. Then the illumination framing is rejected and
  reported as a negative result.
- **Only if H1 holds:** compare lighting augmentation, hysteresis, a calibrated
  single-frame verifier and a feature-matching inlier verifier, all on the same
  backbone and controller. Active verification is considered only if those
  leave a measured gap.

## Rejected or deferred alternatives

| Alternative | Reason |
| --- | --- |
| Implement action-conditioned verifier now | No observed failure; IEVE overlap; strong simple baselines untested |
| Generic low-light navigation benchmark | RobustNav precedent; Guerrier already reports real perturbation evaluation |
| Temporal smoothing as contribution | Already the reference rule (three-frame latch) |
| Transfer GNM stop-head weights to ViNT | No compatibility or calibration evidence |

## Pilot protocol draft (NOT FROZEN)

Pilots are engineering diagnosis, kept separate from any confirmatory evaluation.

- Routes: the three existing live routes (`s_bend_run_0000`, `junction_run_0000`,
  `junction_run_0001`), same checkpoints, controller, camera and reference stop.
- H0 timeout: 50 simulation seconds. At the 0.1 m/s cap this permits 5.0 m of
  travel, which is at least 2 x the longest teacher route (2 x 2.296 m = 4.592 m).
  Stage 1 of the standing causal order (feasibility) must pass before any arrival
  or stop failure is attributed to the policy, the stop rule or the controller.
- Endpoints per episode: arrival (any frame within 0.5 m), correct stop
  (stop decision within 0.5 m), wrong stop (decision outside 0.5 m), overshoot
  (arrival then final distance > 0.5 m without stop), collision episode, timeout.
- Deployed inputs: RGB history and goal RGB only. Simulator pose, goal
  distance and lighting labels are evaluation-only.
- H1 lighting factors: goal image nominal vs degraded, live nominal vs degraded,
  constant vs transition. Renderer intensities are recorded as renderer settings,
  never as lux. Exposure, gain, noise and blur are held fixed.
- No thresholds are tuned on test trajectories.
- Required before freezing (red-team): per-episode decomposition into progress,
  lateral deviation and heading error; distance-head output against true distance
  on teacher replays, in metric units for both checkpoints; a speed-matched
  feasibility arm (teacher at 0.1 m/s or policy at 0.2 m/s) with a
  history-spacing control; dev-only pilot routes; episode or route as the unit,
  with a declared minimum detectable effect and a threshold-free metric (AUROC);
  pinned and logged RTX exposure, tonemap and DLSS settings, with a
  relight-unchanged negative control; replays on policy poses as well as teacher
  poses; "stop decision" defined as the latch frame, with late stops before
  timeout handled explicitly.

EXPERIMENTAL RESULTS: NOT YET AVAILABLE.

## Phase B engineering diagnosis: executed results (2026-10-09)

Scope: engineering diagnosis on the existing three live routes (one dev, two
corpus-test routes already used in earlier live runs) and admitted teacher
recordings. These results are not confirmatory evidence and make no improvement claim.
Released checkpoint only (`vint.pth`, SHA256 `155fd72d...aa1f`); reference stop
enabled; qualified sphere-wheel controller at 0.1 m/s.

### H0 run 01: INVALID, retained

`arrival-h0-pretrained-20261009-01` was launched with `--route-spec`. In the
current collector that flag adds expansion-layout `DoorPartition` prims, which
are absent from the fixed goal photographs (collection05) and the earlier live
runs. The start image differed from the earlier run (mean absolute pixel
difference 18.1). The robot hit a partition at 16.1 s. Stopped by the author
after one episode; it is not a matched replication. Repair: the original
invocation (default routes, `--route-id`). Process lesson: `--route-spec`
silently changes scene geometry. The manifest has no fixture digest to catch it,
so a fixture-identity gate is required before any further matched run.

### H0 run 02: 50 s horizon, valid

Replication check against `option1-live-pretrained-20261007-04`: no partition
prims; start image mean absolute difference 0.29 (max 5); pose difference
<=5 mm and <=0.005 rad up to frame 239.

| Route | Closest m (frame) | Final m | Net progress m | Max lateral m | Final heading err rad | Pred. distance min / at closest | Spearman pred vs true | Stop | Contact |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| s_bend_run_0000 | 1.209 (180) | 1.707 | 0.293 | 1.707 | -1.825 | 4.86 / 13.00 | 0.30 | none | Obstacle |
| junction_run_0000 | 0.584 (228) | 1.869 | 0.101 | 1.869 | 2.791 | 5.72 / 10.00 | -0.54 | none | WallLeft |
| junction_run_0001 | 0.705 (200) | 2.977 | -1.007 | 2.439 | 2.722 | 4.39 / 11.94 | 0.07 | none | WallLeft |

**H0 FAILS.** 0/3 arrivals, 0/3 stops, 3/3 contact episodes. Closest approach
falls at frames 180-228 (15-19 s); the policy then drives away from the goal and
pins against geometry. Extra horizon converts timeouts into collisions. Contact
times are global simulation time; per-episode onset is not reported.
Evidence: `arrival-h0-pretrained-20261009-02/` and `-decomposition.json`.

### Open-loop teacher replay (no simulator; on-route at training speed)

`scripts/score_teacher_replay.py` replays admitted teacher recordings at 4 Hz
through the live preprocessing, model and stop rule, with each recording's own
goal and, as a negative control, another route's goal. Correction (Frank,
2026-10-09): speed matching cannot explain this result, because the replay has no
live controller. Units, labels, preprocessing and threshold must be audited first. The output also contains
three collection05 recordings rejected at admission (`left_run_0001`,
`right_run_0000`, `right_run_0001`); the figures below use the **8 admitted
non-test** recordings only (6 train, 2 dev).
Evidence: `arrival-teacher-replay-20261009-01.json`.

- Reference stop fires in **0/8**, even on-route at the training speed.
  Minimum predicted distance per recording is 2.75-9.9; the `<=1` threshold is not reached.
- Predicted vs true distance Spearman: 0.54-0.94 on 6/8; 0.31 (`s_bend_run_0000`)
  and -0.23 (collection07 `left_run_0001`) on the others.
- Goal-identity negative control: within 0.5 m of the true goal, the mean
  prediction to a *different* route's goal was lower than to the true goal on
  `straight_run_0000` (4.58 vs 9.19) and `s_bend_run_0000` (3.61 vs 9.88), and
  about equal on collection06 `right_run_0000` (4.22 vs 4.12). **WITHDRAWN (milestone 4):** in all
  three cases the "wrong" goal was the sibling route variant in the *same scene*,
  whose endpoint is 0.25 m from the true goal, so the place was not wrong. The
  negative control was invalid; see the cross-scene re-run below.

### Interpretation (INFERENCE, engineering scope)

The released ViNT arrival signal is not admissible as a stop under nominal
lighting in this domain. Its threshold is unreachable, and it does not reliably
encode goal identity. Separately, the closed-loop policy at the 0.1 m/s cap
approaches and then leaves the goal region. Candidate causes, none yet tested:
speed/time-base mismatch (teacher 0.2 m/s), the proxy controller's turn drift,
and a training-to-evaluation appearance/domain mismatch. All runs are
simulation-only, so this is not a sim-to-real gap. An illumination study built on this signal would measure a floor
effect. The lookalike confusion is the phenomenon the paper intended to study,
and it already appears without illumination change.

### Retained failures

| Attempt | Failure | Disposition |
| --- | --- | --- |
| Phase A horizon claim | Refuted by red-team | Retracted |
| H0 run 01 | Wrong invocation added partitions | Invalid; retained; fixture gate required |
| decomposition draft | Expected status `COMPLETED`; collector writes `PASS` | Corrected before any reported number |
| Full suite | 3 `test_environment_identity_v8` failures | Also fail with this milestone's files removed; worktree path / git-ignored `runs/bo10` evidence absent here |

### Decision needed from Frank

1. **Re-scope paper 1** to a characterised arrival-signal failure of ViNT-class
   RGB policies: unreachable stop threshold, lookalike preference and closed-loop
   departure. Illumination becomes a later factor.
2. **Repair first:** run a speed-matched closed-loop arm (0.2 m/s qualification
   or 0.1 m/s teacher data) and a budgeted fine-tune of the distance head, then
   re-test H0 before any illumination work.

Option 2's speed-matched check is cheap and does not prejudge option 1.

## Option 2 milestone 1: fixture identity gate (2026-10-09)

Decision (Frank): qualify and repair the baseline before re-scoping.

`src/navfm/collection/fixture_identity.py` signs every prim under the route's
scene plus the global Sun/Dome lights: type, applied schemas, size, transforms,
colour and light inputs, rounded to 1e-6. The collector compares this signature
with the goal-photo source collection's `fixture.usda` before any episode. The
route specification must also be equal, and per episode the camera mount, local
pose and resolution must match the goal source. Mismatch writes
`REFUSED_FIXTURE_IDENTITY` and exits 3. Previously `SimulationApp.close()`
returned status 0 after a failure; failed collections now exit 1.

| Control | Invocation | Result |
| --- | --- | --- |
| Negative 1 | `--route-spec` (H0 run 01 recipe), goals from collection05 | Refused before execution: DoorPartition0/2 absent from goal source, obstacle moved (exit 0 before the exit-code repair; retained) |
| Negative 2 | Original invocation, goals from collection05 | Refused before execution, exit 3 |
| Positive | Original invocation, goals from `arrival-goals-current-20261009-01` | 3/3 episodes PASS (12-step check), 64 signed prims per scene |
| Unit | `tests/test_fixture_identity.py` | 6 passed, incl. partition and lighting negative controls |

### Defect found by the gate: every earlier matched live run used mismatched goals

Collection05 holds the only s_bend/junction goal photographs. It was recorded with
earlier scene code: obstacle at x=2.4 m (current code: 3.5+0.1*(scene%5) = 3.8 /
3.9 m) and five per-scene DistantLights (1200-1600, same rotation). USD distant
lights are not limited by hierarchy, so total directional intensity was 7000,
against 1500 in every live run. Verified from `fixture.usda` text. Collection05 has no
`lighting` record; 06 and 07 do and match current code.

**Consequence.** Every matched live comparison so far (`option1-live-*-20261007-*`
and H0 run 02) paired goal photographs from a scene with different obstacle
placement and directional lighting from the live scene. In the live view near
the goal the obstacle is visible; in the goal photograph it is not. Those runs
are therefore **not valid baseline-competence evidence.** They are retained as
evidence of goal/live scene mismatch: an unintended confound of exactly the
geometry-plus-illumination kind this project must isolate. The open-loop
teacher replay is unaffected: each recording is scored against its own goal from
the same collection. H0 must be re-run against the current-scene goals.

### Environment-identity test failures

The full suite stands at 2560 passed, 2 skipped, 3 failed. The failures are
`tests/test_environment_identity_v8.py`. They are BO-10 intervention controls
that pin the main checkout path and its git-ignored, immutable
`runs/bo10/intervention/arm_a/pre_capture.json`. That file exists under
`/home/favl/projects/navfm/runs` but not in this worktree, and must not be copied.
The arrival experiments do not use `navfm.arm_environment_guard` or BO-10
captures. Assessment: no effect on the validity of this milestone; they remain
failing and are not described as passed.

## Option 2 milestone 2: arrival-signal audit (2026-10-09)

### Actual distance-label semantics (VERIFIED, pinned upstream `dca7981`)

- `vint_dataset.py`: label = `(goal_time - curr_time) // waypoint_spacing`, the
  number of subsampled frames between observation and goal. It is a step count,
  not metres. Negatives (another trajectory's frame) are labelled
  `max_dist_cat` = 20 (`vint.yaml` `distance: 0..20`).
- A sampled goal offset of 0 is replaced by a negative, so **label 0 is never a
  positive example**; positives span 1..20. Regression is MSE (`alpha` 0.5 with
  the action loss).
- Metres per step differ by dataset (`data_config.yaml`: RECON 0.25, SACSoN 0.255,
  GO Stanford 0.12, SCAND 0.38, TartanDrive 0.72). In this corpus one step is
  0.05 m of teacher motion (`option1_m3pro`), so 0.5 m is about 10 label units.
  Because the teacher stops about 0.12 m short of the goal, the mean label within 0.5 m is 4.5-5.7.
- Pinned deployment (`navigate.py`) never thresholds distance to the goal image
  directly. It localises to topological-map nodes with `--close-threshold`
  default **3** and stops when the localised node is the final node.
- The project rule (`rgb_baseline.py`: three consecutive predictions <=1 and
  waypoint <=0.15 m) is a project choice with no upstream counterpart and no
  recorded justification.

### Audit results (`arrival-signal-audit-20261009-01.json`)

8 admitted non-test teacher recordings (6 train, 2 dev), open loop, released
checkpoint `155fd72d`, six-step adapted `d0f412e6`, and 20-step n25 seed0 `1ee4c2fa`.

| Finding | Evidence | Class |
| --- | --- | --- |
| Project threshold below the model's output floor | Goal-as-current control (history = goal image) predicts 1.9-6.6 (released), never <=1; rule fires 0/8 for all three checkpoints | **Implementation defect** |
| Near-goal calibration acceptable on 5/8 | Released mean prediction within 0.5 m 3.66-4.25 vs label 4.5-5.7 | Model OK on these |
| Near-goal failure on 3/8 | `straight_run_0000`, `s_bend_run_0000`, 07 `left_run_0001`: 9.2-10.7 vs label ~5.3; Spearman -0.41 to 0.32 | **Remaining model failure** |
| Upstream threshold 3 (not fitted) | Own goal fires 2/8 (true 0.11-0.35 m); wrong goal fires 1/8 released and 2/8 adapted (true 0.31-0.55 m to own goal) | Real false arrival under ranking ambiguity |
| Adaptation | Six-step and 20-step checkpoints reproduce the released behaviour within about 1 unit | Failure exists in original and adapted |

### Render-history hypothesis: tested and not supported

The three failing recordings were the only ones whose goal photograph was 20-26%
darker than the final teacher frame (ratio 0.74-0.80, vs 0.91-0.99 for the others;
mostly the first episode recorded in a new scene). Recorded renderer settings show
auto-exposure **disabled** (`/rtx/post/histogram/enabled = False`, tonemap op 6).
A pose-identical intervention recaptured goals after 8 vs 96 render steps
(`arrival-goal-settle{8,96}-20261009-01`, routes s_bend 0/1 and the retired
junction 0/1, diagnostic only). Settling changed one goal materially
(junction_run_0000: pixel mean absolute difference 11.3, ratio 0.88 to 0.96). Predictions on identical
frames barely moved (near-goal 2.91 vs 3.04; s_bend_run_0000 8.84 vs 9.01).
The darkness correlation is therefore not established as causal; with n=8 it was
confounded with route and recording order. Goal-photo texture (mean gradient
0.98-1.54) does not separate good from bad recordings either. The 3/8 failures
remain **unexplained**.

Dataset-design finding: every route endpoint faces a near-blank wall at close
range. Goal photographs carry little distinctive content, which plausibly
underlies the ranking ambiguity. This is an INFERENCE to test with
landmark-bearing endpoints, not a conclusion.

### Changes

- `scripts/score_teacher_replay.py`: admission filter, several checkpoints,
  label-unit fit, goal-as-current control, both stop rules,
  `--goal-override-root` for pose-identical recaptures, explicit
  `--include-retired-test` for diagnostics.
- `scripts/collect_option1.py`: records renderer exposure settings;
  `--goal-settle-steps` (default 8 = historical behaviour).
- `scripts/qualify_articulated_control.py`: `--speed-matched-envelope`
  (0.2 m/s with the live 0.4 rad/s cap) for milestone 3.

## Option 2 milestone 3: controller and sampling diagnosis (2026-10-09)

### Controller tracking at both speeds

Same sphere-wheel proxy, acceleration drives and yaw gains (1.5 pure / 0.8 mixed),
unchanged absolute gates. Speed envelope added prospectively; nothing re-tuned.

| Command v / w | 0.1 m/s envelope (`articulated-control-20261007-06`) | 0.2 m/s envelope (`articulated-control-20261009-07`) |
| --- | --- | --- |
| forward | 0.100 / 0.000 PASS | 0.200 / 0.000 PASS |
| pure turn +/-0.4 | 0.374 / -0.417 PASS (~0.03 m/s drift) | 0.376 / -0.421 PASS (~0.03 m/s drift) |
| combined v, +/-0.4 | 0.402 / -0.459 PASS | **0.110 / -0.119 FAIL** (~28% of request) |
| 0.2, +/-0.2 | not tested | 0.062 / -0.070 "PASS" |
| collision positive | contact reported | contact reported |

The 0.2/+/-0.2 cases pass only because the absolute 0.15 rad/s tolerance exceeds
the command itself. That gate is **non-discriminating** for small turn commands and
is not counted as qualification. The mixed yaw gain was calibrated at 0.1 m/s;
turning while moving at 0.2 m/s is unqualified. A 0.2 m/s closed-loop arm would
confound speed with under-turning, so it was not run.

### Matched sampling arms

Motion per observation was matched to training (teacher 0.05 m per 4 Hz step)
inside the qualified 0.1 m/s envelope by deciding at 2 Hz (PD `dt` = 0.5 s).
Everything else was identical: released checkpoint, `upstream_t3` stop rule, 50 s
budget, fixture-verified current-scene goals (`arrival-goal-settle8-20261009-01`),
and routes s_bend 0/1 (dev) plus junction 0/1 (retired test, diagnostic).

| Arm | Actual period / displacement per decision | Arrived <=0.5 m | Correct stop | Wrong stop | Contact | Timeout |
| --- | --- | --- | --- | --- | --- | --- |
| A 4 Hz `arrival-matched-a4hz-20261009-01` | 0.25 s / 0.024-0.025 m | 1/4 | 0/4 | 0/4 | 4/4 | 4/4 |
| B 2 Hz `arrival-matched-b2hz-20261009-01` | 0.50 s / 0.045-0.049 m | 1/4 | 0/4 | 1/4 (stop at 2.56 m) | 3/4 | 3/4 |

Per episode, closest approach was 0.31-1.19 m at frames 159-254 (13-21 s),
followed by departure (max lateral deviation 1.7-2.7 m) and contact at frames
355-509. In 2/8 episodes the robot passed within 0.31-0.45 m with minimum
predicted distance 4.2-5.7, so the stop rule did not fire. With n=4 per arm,
matching the sampling time-base does **not** restore competence; the
speed/time-base hypothesis is not supported.

### Implementation defects versus remaining model failures

| Item | Status |
| --- | --- |
| Goal photographs from a different scene (obstacle position, lighting) | Defect; repaired by fixture gate and current-scene goals |
| Collector exit 0 on failure | Defect; repaired |
| Project stop threshold below output floor | Defect; documented `upstream_t3` alternative added; default unchanged |
| Policy time-base 0.025 vs 0.05 m per step | Mismatch; 2 Hz arm matches it; no competence gain |
| 0.2 m/s turning | Controller limitation; unqualified, not used |
| Closed-loop departure after closest approach | **Remaining model failure** |
| Near-goal distance prediction too high on some routes; wrong-goal preference | **Remaining model failure** |

## Option 2 milestone 5: revised split (frozen before tuning)

`configs/splits/arrival_split_v1.json` (SHA256 `e0551eb8...94be6`) retires
`junction_run_0000/0001` from confirmatory use; they remain development
evidence. Held-out groups are specified but **NOT COLLECTED**. The current scene
generator varies appearance by `scene_index % 5`, so a new index (e.g. 20)
recreates a training scene. In the existing corpus, training scenes 8 and 9
already share those parameters with dev scene 3 and retired-test scene 4, so
dev/test are not appearance-disjoint from training. Held-out groups require a
new layout family with landmark-bearing endpoints, and they are sealed until a
confirmatory protocol is frozen.

## Option 2 milestone 4: budgeted fine-tuning and goal semantics (2026-10-09)

### Training budget (documented before running)

Released ViNT, upstream objective unchanged (`alpha` 0.5, distance term weight
`alpha*1e-2`), batch 4, AdamW lr 1e-5, frozen BatchNorm, 31 admitted training
trajectories of the expanded corpus (945 pairs, 236 steps per epoch), 20 epochs
(4,720 steps), three seeds (0/11/22). Dev-only evaluation at epochs 1/2/5/10/20.
Earlier budgets (6-20 steps) were under 0.1 epoch. Trainer regression: the
recorded n25 seed0 20-step command reproduced checkpoint `1ee4c20a...`
byte-identically.

| Dev (83 fixed pairs, 2 trajectories) | Released | Epoch 10 (3 seeds) | Epoch 20 (3 seeds) |
| --- | --- | --- | --- |
| Waypoint ADE (cm) | 4.84 | 1.97-2.09 | 1.92-2.00 |
| Distance MAE, positives (label units) | 3.90 | 1.98-2.09 | 1.87-2.06 |
| Distance Spearman, positives | 0.54 | 0.86-0.88 | 0.87-0.89 |
| Mean prediction, 6 negatives (label 20) | 9.18 | 10.9-11.3 | 11.8-12.7 |

Train losses (all seeds): `dist_loss` 23-24 to 5.7-6.0; `action_loss` 0.21 to
0.03. Curves plateau between epochs 10 and 20. Epoch 20 was selected on dev distance
MAE (lowest in 2/3 seeds), fixed before any closed-loop run. Checkpoints:
`option1-arrival-n31-e20-seed{0,11,22}-20261009-01/epoch_020.pth` (seed0 SHA256
`c7686983...0d5d7c`).

### Training-to-deployment goal mismatch (implementation finding)

Training and fixed-pair evaluation use **future frames of the same trajectory**
as goals. The live/collector goal is a **separately captured photograph** at the
exact endpoint (teleport plus settle; about 0.12 m beyond the teacher's final frame).
Pinned upstream deployment uses topological-map nodes: frames from a prior
traversal. On open-loop current-scene recordings with photograph goals, the
fine-tuned checkpoints rank well (Spearman 0.70-0.93) but predict 8-15.6 near the
goal (label ~5.4), so threshold 3 never fires.

Pose-identical settle intervention on fine-tuned seeds 0/11 (same frames, goal
photo after 8 vs 96 render steps): junction_run_0000, the only goal materially
changed by settling, drops from 10.89 to 8.37 and from 10.21 to 8.11. The
released model moved 2.91 to 3.04. **Fine-tuning increased sensitivity to
goal-photograph render state** (1 route x 2 seeds; causal but small).

Prior-traversal goals (final frame of the 96-step traversal, scored on the
independent 8-step traversal; `arrival-goal-traversal-final-frame-20261009-01`)
with **cross-scene** negatives (`arrival-goal-traversal-score-20261009-03.json`).
Threshold 3 is the pinned default, not fitted:

| Checkpoint | Own-goal near-goal prediction | Own fires (true distance at fire) | Cross-scene wrong-goal fires | Wrong-goal minimum prediction |
| --- | --- | --- | --- | --- |
| Released | 1.68-2.35 | 4/4 (0.30-0.57 m; 2/4 outside 0.5 m) | 1/4 (s_bend_0; min 2.94) | 2.94-6.93 |
| Fine-tuned, 3 seeds | 3.27-6.26 | 11/12 (0.13-0.26 m) | 0/12 | 4.59-11.24 |

Open-loop, four routes, two scenes. The dev scenes are partly appearance-aliased
with training scenes 8/9 (split v1). These are engineering diagnostics, not
held-out evidence.

### Closed-loop retest under normal lighting (milestone 6, competence check)

Matched arms with identical fixture-verified scene, prior-traversal goals, 2 Hz
decisions (0.05 m per decision), the `upstream_t3` stop rule, a 50 s budget and
the qualified 0.1 m/s controller, on four development routes. Fine-tuned seed 0
was fixed in advance from dev metrics.

| Route | Released closest m (frame) | Released outcome | Fine-tuned closest m (frame) | Fine-tuned outcome |
| --- | --- | --- | --- | --- |
| s_bend_run_0000 | 1.108 (165) | timeout, contact | 0.898 (221) | timeout, contact |
| s_bend_run_0001 | 1.092 (187) | timeout, contact | 0.716 (238) | timeout, contact |
| junction_run_0000 | 1.157 (162) | timeout, contact | 0.477 (255) | **stop at 0.527 m**, no contact |
| junction_run_0001 | 0.322 (267) | timeout, contact | **0.087 (244)** | no stop (min prediction 4.38), contact |

| Endpoint (denominator 4 attempted episodes) | Released | Fine-tuned seed 0 |
| --- | --- | --- |
| Arrival (any frame <=0.5 m) | 1/4 | 2/4 |
| Correct terminal stop (<=0.5 m) | 0/4 | 0/4 |
| Wrong terminal stop (>0.5 m) | 0/4 | 1/4 (0.527 m) |
| Missed arrival / overshoot | 1/4 | 1/4 |
| Collision episode | 4/4 | 3/4 |
| Completion (correct stop, no contact) | 0/4 | 0/4 |

Evidence: `arrival-closedloop-{released,ft-seed0}-20261009-01` and their
`-decomposition.json` files.

**The normal-light baseline is NOT competent.** Fine-tuning improves closest
approach on 4/4 paired routes (one seed; n=4; no significance claimed) but
yields no correct stop. At closest approach the heading differs from the goal
frame by 9-21 degrees, and closed-loop predictions stay at 4.3-5.3 even 0.087 m
from the goal; on teacher frames the same model fired at 0.13-0.26 m. The
remaining failure is closed-loop distribution shift: the policy visits headings
and lateral offsets absent from the straight-on teacher demonstrations, and
both waypoints and distances degrade there.

Illumination isolation (step 6) was **not started**, because competence under
normal lighting is not established.

### Next decision for Frank

1. **Recovery data (recommended):** teacher demonstrations with prospective
   heading and lateral perturbations (DAgger-style relabelling of off-route
   states), trained with the same budget, to target the measured closed-loop shift.
2. **New layout family and sealed held-out groups (split v1):** needed for any
   confirmatory claim and for honest dev-only stop calibration. All four
   current routes are now development routes.
3. A stop-threshold calibration on dev can be prepared, but cannot be evaluated
   until held-out groups exist.

## Directive 4: controller re-qualification, failure decomposition, held-out freeze (2026-10-09)

### Controller: the milestone 3 qualification was non-discriminating

Milestone 3 counted the 0.1 m/s envelope as qualified from one saturated
command (0.1 m/s, +/-0.4 rad/s). In-episode audit
(`scripts/audit_closed_loop_episodes.py`, evidence `closedloop-audit-20261009-01.json`)
compared every held policy command with the yaw rate the base actually realised
before first contact. Across all 16 earlier closed-loop episodes (released and
fine-tuned, 2 Hz and 4 Hz arms) the realised/commanded yaw-rate slope was
**0.16-0.34**; typical commands were 0.1-0.2 rad/s. A free-space sweep at the
same proxy settings (`articulated-control-20261009-08`) shows a deadband: at
0.1 m/s, commands of 0.05 / 0.1 / 0.2 / 0.3 rad/s realised 0.00 / 0.015 / 0.06-0.08
/ 0.12-0.14 rad/s; only 0.4 tracked. Replaying one episode's logged commands in
free space gave slope 0.35. The deficit is therefore the open-loop wheel map
(skid-steer sphere-wheel proxy), not the scene. **Every earlier closed-loop
episode, and every model-failure attribution drawn from them, is confounded by
a base that realised about a fifth of the commanded turning.**

The training teacher is a separate, kinematic `pose_step` teacher at 0.2 m/s
with turn rates up to 0.7 rad/s; it never used the wheel controller.

Repair: a PI loop on measured body yaw rate (ideal gyro; base-controller input
only, never a policy input; `src/navfm/collection/yaw_rate_tracker.py`, gains
fixed before testing: ff 1.0, kp 1.0, ki 4.0). Acceptance was declared in the
qualifier before running: per case |error| <= max(0.03, 0.25|w|); logged-command
replay slope in [0.8, 1.2], sign agreement >= 0.9.

| Run | PI rate | Sweep (20 turn cases, 0.1 and 0.2 m/s) | Replay slope (speed) | Status |
| --- | --- | --- | --- | --- |
| 08 open loop | none | 0.1 m/s: only +/-0.4 pass; 0.2 m/s: none pass | 0.35 (logged 0.1) | FAIL |
| 09 | 12 Hz | 0.1 m/s 0.2/0.3 fail (stick-slip limit cycle, ~0.5 s period); 0.2 m/s all pass | 0.69 | FAIL |
| 12 | 12 Hz | as 09 | 0.88 (0.2) | FAIL |
| **10** | **120 Hz** | **all pass** | **0.85 (logged 0.1)** | **PASS** |
| **11** | **120 Hz** | **all pass** | **0.88 (0.2)** | **PASS** |

The rate was chosen after seeing 09 fail; the 120 Hz loop corresponds to a
motor-controller loop running independently of the 2-4 Hz policy. The collector
now runs it from a physics-step callback (`--yaw-feedback`), refuses unless the
qualification describes the same tracker with a command replay, and records the
number of physics-step updates per episode (6000/6000 observed in the one valid
episode). Limits: the replay set is one episode; tracking inside a cluttered
scene is measured per episode by the audit, not assumed.

### Four-episode failure decomposition (fine-tuned seed 0, milestone 6)

Declared thresholds: goal region 0.5 m, route departure 0.5 m from the route
polyline, settled = < 0.01 m motion in the last 1 s after a stop.

| Route | Event order (s) | Entered goal region | Declared arrival | Settled after stop | First event | Realised/commanded yaw |
| --- | --- | --- | --- | --- | --- | --- |
| s_bend_run_0000 | departure 12.4, contact 35.3 (WallLeft), timeout 49.9 | no (closest 0.90 m) | no | n/a | route departure | 0.21 |
| s_bend_run_0001 | departure 12.6, contact 26.5 (Obstacle), timeout 49.9 | no (closest 0.72 m) | no | n/a | route departure | 0.15 |
| junction_run_0000 | entry 19.5, departure 23.1, stop 24.0 | yes | yes, at 0.527 m (after leaving the region) | yes (0.0003 m) | goal-region entry | 0.13 |
| junction_run_0001 | entry 15.3, departure 25.4, contact 29.4 (Obstacle), timeout 49.9 | yes (closest 0.087 m) | no (min prediction 4.38) | n/a | goal-region entry | 0.12 |

Counts (n = 4): goal region entered 2/4; arrival declared 1/4 (wrong, 0.527 m);
settled after stop 1/1; route departure before any goal entry 2/4 (both
s_bend, at ~12 s, the first bend); collision 3/4; timeout 3/4. The released
checkpoint shows the same pattern (s_bend departures at 12.1-12.2 s; junction_1
entry without stop). With realised turning at 12-21% of command, the two s_bend
departures are not attributable to the model.

### Controller-repaired retest: first attempt INVALID (retained)

`arrival-closedloop-yawfb-{released,ft-seed0}-20261009-01`: 1 of 8 episodes ran;
the other 7 were refused by the source-stability gate because collector and
`scene_layouts.py` were edited during the run (process error, gate worked as
designed). The one valid episode (released, s_bend_run_0000) realised slope
0.76 in-episode (was 0.16-0.21), yet still departed at 12.3 s: the policy drove
straight at the first bend and then turned left (yaw 0.5 -> 1.1 rad) where the
route turns right, with predicted distance never below 8.7. One episode;
treated as a lead, not a finding.

### Held-out freeze: `heldout_layouts_v1` under `arrival_split_v2`

Three independent red-team passes (`gates/redteam/trigger4-heldout-freeze-2026-10-09.md`):
DO-NOT-FREEZE, DO-NOT-FREEZE, FREEZE-WITH-AMENDMENTS; all pass-3 amendments
applied before this freeze. `arrival_split_v2.json` amends v1 only by enlarging
held-out from 3 to 6 groups, before any held-out data exists.

- Six explicit layouts (scene indices 40-45, reserved), two routes each (12
  routes); starts and lengths matched to training; palettes, obstacles and
  end-wall landmarks new (every colour >= 0.15 from every training colour); the
  two goals in a group are 1.2-1.4 m apart and dominated by landmarks of different
  shape and colour at both the endpoint and the teacher final-frame pose.
- Generator `scripts/make_heldout_layouts_v1.py` refuses to write unless every
  route passes: kinematic teacher completes within 360 steps (133-137 used),
  clearance >= 0.34 m, goal landmark fraction >= 0.3 (0.40-0.57), goal not
  reachable by driving straight.
- Frozen protocol: teacher 360 steps, policy 600 steps at 0.1 m/s, 12 Hz,
  arrival radius 0.5 m. Primary endpoint completion; decision rule completion
  >= 10/12 against goal-blind nulls (~6/12); goal-swap control criterion;
  descriptive only.
- Enforcement: collection, admission, replay, summary, decompose and audit
  refuse sealed ids, reserved indices, route geometry within 0.1 m and scenes
  reproducing half a sealed scene; unsealing needs the pinned ledger, a declared
  role slot, the protocol budget and all routes; policy roles need checkpoints
  pre-declared in `configs/splits/heldout_layouts_v1_checkpoints.json` (not yet
  created); scoring needs the run recorded in the ledger.
- Documented residuals: not robust to a determined operator; goal-swap tooling
  not built yet.
- Status: FROZEN SPECIFICATION, NOT COLLECTED, NOT SCORED. Previously inspected
  dev and retired-test routes remain diagnostic/development data.

### Controller-repaired retest (valid, pinned source `d2f071b`)

`arrival-closedloop-yawfb-{released,ft-seed0}-20261009-02`: same routes, goals
(prior-traversal final frames), 2 Hz, `upstream_t3`, 50 s, 0.1 m/s as milestone
6, plus the 120 Hz yaw-rate loop (qualification `articulated-control-20261009-10`).
Verification of all 8 manifests: status PASS, checkpoint sha256 as declared,
qualification sha256 matches, 600/600 frames recorded and on disk with
`traj_data.pkl`, 6000/6000 feedback updates, contact subscription active,
fixture signatures identical across arms and to milestone 6. No problems.

| Arm / route | Entered region (s) | Min / final goal m (t) | Declared | Settled | Departure (s) | Contact (s, prim) | Timeout | Pred. at closest / min | Yaw slope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| released s_bend_0 | no | 1.109 (13.0) / 2.316 | no | n/a | 12.3 | 37.3 WallLeft | yes | 10.76 / 6.46 | 0.75 |
| released s_bend_1 | no | 1.088 (13.9) / 2.086 | no | n/a | 12.3 | 35.8 WallLeft | yes | 12.53 / 6.81 | 0.66 |
| released junction_0 | 22.3 | 0.476 (24.4) / 2.136 | no | n/a | 11.1 | 41.8 Obstacle | yes | 6.41 / 4.98 | 0.73 |
| released junction_1 | no | 0.501 (21.2) / 2.013 | no | n/a | 8.7 | 42.2 WallLeft | yes | 5.18 / 3.89 | 0.74 |
| ft s_bend_0 | no | 0.651 (19.6) / 1.299 | no | n/a | 12.8 | 29.4 Obstacle | yes | 10.85 / 6.49 | 0.71 |
| ft s_bend_1 | no | 0.577 (19.8) / 1.198 | no | n/a | 13.2 | 29.5 Obstacle | yes | 13.73 / 8.18 | 0.61 |
| ft junction_0 | 16.4 | 0.117 (21.0) / 1.198 | no | n/a | 25.9 | 32.1 Obstacle | yes | 4.79 / 3.56 | 0.64 |
| ft junction_1 | 16.0 | 0.156 (20.7) / 1.388 | no | n/a | 25.3 | 32.0 Obstacle | yes | 12.94 / 5.97 | 0.75 |

Elapsed 49.9 s in every episode (timeout). Counts (n = 4 per arm):

| Endpoint | Released | Fine-tuned seed 0 |
| --- | --- | --- |
| Entered goal region | 1/4 | 2/4 |
| Declared arrival (any) | 0/4 | 0/4 |
| Correct stop | 0/4 | 0/4 |
| Collision episode | 4/4 | 4/4 |
| Timeout | 4/4 | 4/4 |
| Route departure before any goal entry | 4/4 | 2/4 (s_bend) |

Paired differences against milestone 6 (open-loop wheel map), one seed, no
significance claimed: closest approach improved on 2/4 released routes
(junction_0 1.157 -> 0.476, s_bend unchanged ~1.1, junction_1 0.322 -> 0.501
worse) and on 2/4 fine-tuned routes (s_bend 0.898 -> 0.651, 0.716 -> 0.577);
fine-tuned junction_0 went from a wrong stop at 0.527 m to passing 0.117 m with
no stop; junction_1 0.087 -> 0.156 m, again no stop.

In-episode tracking rose from 0.16-0.34 to 0.61-0.75 (regression slope) but did
not reach the 0.8 free-space criterion; in-episode commands are small (median
|w| 0.03-0.09 rad/s), where the loop has not settled within a 0.5 s hold. The
controller is improved, not fully qualified for this command distribution.

**Decision.** Controller repair did not resolve the failures. Two distinct
failures remain, each localised by its own evidence (INFERENCE, n = 2 per
pattern):

1. **Bend following (s_bend, both checkpoints, 4/4):** departure at 12.3-13.2 s at
   the first bend from an on-route start, with turning realised at 0.61-0.75 of
   command. The released model's s_bend predictions are uncorrelated with true
   distance (Spearman -0.16, -0.07). This is a navigation failure that begins on
   route, so off-route recovery diagnosis is necessary but not sufficient: the
   bend itself must be diagnosed (commanded vs teacher curvature at the bend).
2. **Arrival recognition (fine-tuned junction, 2/2):** the robot entered the goal
   region and passed 0.117 m and 0.156 m from the goal with heading within
   2.7-7.8 degrees of the goal frame, yet the prediction stayed at 4.79 and 12.94
   (rule threshold 3), so it drove on and collided. On teacher frames the same
   checkpoint fired at 0.13-0.26 m.

Held-out remains sealed; no held-out run is justified while development
routes fail.

### Bend diagnosis (offline, no simulator; `bend-probe-*-20261009-01.json`)

Question: at the s_bend bends, does the model predict the turn on the teacher's
own frames (on-route, training speed and spacing), or only fail after closed-loop
drift? Method: each checkpoint sees six teacher frames 0.05 m apart and the
prior-traversal goal; the predicted waypoint-2 bearing is compared with the true
bearing to the teacher's own pose three steps (9 frames) ahead, excluding frames
where that lookahead runs past the route end. True bearings span -15..+15 deg.

| Route | Released corr / MAE | Fine-tuned corr / MAE |
| --- | --- | --- |
| s_bend_run_0000 | 0.11 / 11.7 deg | 0.40 / 4.7 deg |
| s_bend_run_0001 | -0.07 / 10.1 deg | 0.28 / 7.4 deg |
| junction_run_0001 (control) | 0.25 / 9.3 deg | 0.53 / 2.7 deg |

Closed-loop on s_bend_run_0000 the fine-tuned policy reached the first vertex
on route (x 1.61, y +0.37, yaw 13 deg vs teacher 30 -> -49 deg) and then
predicted bearings of -1..+1 deg for the next 8 s, holding yaw near 10 deg and
leaving the route.

INFERENCE (two s_bend routes, one seed): the bend failure starts before any
closed-loop drift: even on teacher states the model's turn prediction at the
s_bend is weak (correlation 0.28-0.40 fine-tuned, none released), weaker than
on the junction control. Recovery data alone would address drift after a
missed turn, not the missed turn itself. Supported next intervention: training
data with more bend and double-turn approaches on training layouts, collected
together with perturbed-start recovery demonstrations, evaluated against an
equal-budget baseline, with this probe as the development check.

### Goal-image identity (resolved, no evidence changed)

The audit's goal check refused all eight retest episodes. Cause: three
representations of one goal, hashed differently by design. The declared source
is a teacher trajectory JPEG; the goal root stores those exact bytes under the
name `goal.png`; the collector decodes them to RGB uint8 pixels (the model's
input) and writes a PNG re-encoding of those pixels into the episode, whose hash
is `fixed_goal_sha256`. The audit had compared the root's JPEG hash with the
episode PNG hash. The check now verifies each representation against its own
record (source bytes == declared `source_sha256` == episode `goal_source_frame`;
episode PNG == `fixed_goal_sha256`; decoded source pixels == consumed pixels)
and records all three hashes plus the consumed-pixel hash. All eight episodes
pass: identical 240x320x3 uint8 pixels. No manifest was modified; regression
tests cover the valid JPEG/PNG pair and three genuinely changed-goal cases.

### Retest under frozen measures (`closedloop-yawfb-measures-v1-20261009-02.json`)

No exclusions. These runs predate per-run budget recording; their budget was
600 frames (launch script). Navigation success is reported as **goal-region
visit** because no goal-blind control row exists yet.

| Measure (n = 4 per arm) | Released | Fine-tuned seed 0 |
| --- | --- | --- |
| Goal-region visit (before contact) | 1/4 (1.3 s inside) | 2/4 (9.4 s and 9.1 s inside) |
| Correct stop | 0/4 | 0/4 |
| Wrong stop | 0/4 | 0/4 |
| Collision before task end | 4/4 | 4/4 |
| Timeout | 4/4 | 4/4 |
| In-episode tracking (diagnostic) | OUTSIDE_BAND, slope 0.69-0.77 | INSUFFICIENT (< 20 turn commands) |
| Admitted trajectory rate | not applicable (policy runs) | not applicable |
