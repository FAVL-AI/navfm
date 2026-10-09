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
goal and, as a negative control, another route's goal. The output also contains
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
  about equal on collection06 `right_run_0000` (4.22 vs 4.12). Under nominal
  lighting, the arrival signal can prefer a lookalike goal.

### Interpretation (INFERENCE, engineering scope)

The released ViNT arrival signal is not admissible as a stop under nominal
lighting in this domain. Its threshold is unreachable, and it does not reliably
encode goal identity. Separately, the closed-loop policy at the 0.1 m/s cap
approaches and then leaves the goal region. Candidate causes, none yet tested:
speed/time-base mismatch (teacher 0.2 m/s), the proxy controller's turn drift,
and domain gap. An illumination study built on this signal would measure a floor
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
