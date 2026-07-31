# Holonomic Execution of Nonholonomic Priors: A Forensically Validated Simulation Pipeline for Adapting Visual Navigation Foundation Models

**Frank Asante Van Laarhoven**

*Draft v0.1 — pre-registered experimental design. Every empirical slot is
marked `[E#.# — PENDING]` and bound to a cell of the pre-registered matrix in
`docs/EXPERIMENTS.md`; no such slot may be filled except by the script that
generates tables from run logs. This document is written before the results
exist, deliberately: the commit timestamp of this draft and of
`PREREGISTRATION.md` is part of the evidence.*

---

## Abstract

Visual navigation foundation models — GNM, ViNT and NoMaD — are trained on
~80–100 hours of real-robot data collected almost exclusively from
differential-drive and Ackermann platforms, and their published adaptation
results rest on a data format that has never been specified, an implementation
whose configuration files disagree with its papers, and normalisation
constants whose derivation was never published. We present, first, a forensic
audit of the reference implementation that surfaces eleven discrepancies
material to reproduction — including a latent yaw-wrapping defect in the
original preprocessing pipeline, two dataset-composition configuration keys
that are dead code, and evaluation metrics that vary with batch size by up to
0.46 in cosine similarity. Second, we contribute the first written,
machine-checkable specification of the GNM trajectory format, together with a
simulation-to-format pipeline in NVIDIA Isaac Sim whose compatibility is
*proven* — generated data is loaded through the unmodified reference
`ViNT_Dataset` class and our action-label computation is verified against the
reference implementation to 10⁻¹⁰. Third, we use this pipeline to ask a
question the original works could not: when a *holonomic* (mecanum) robot
executes a policy whose action prior is almost entirely nonholonomic, should
the adaptation data be collected under the robot's true kinematics or under
the prior's? We pre-register a 2×2 factorial over demonstration and execution
kinematics, a data-efficiency curve over {0, 0.25, 1, 4, 16} hours of
simulated data, and a physical-robot transfer study on a Yahboom ROSMASTER
M3 PRO. `[E2/E3/E6 — PENDING]`. All code, data, checkpoints hashes, and the
complete audit trail are released.

---

## 1. Introduction

A useful reproduction is an adversarial act. It assumes the published system
diverges from its description, goes looking for the divergences, and only then
builds on what survives. This paper applies that posture to the most-cited
line of visual navigation foundation models — GNM [1], ViNT [2] and NoMaD [3]
— because we want to *use* them, on a robot they were never trained for, with
data from a simulator they were never fed from, and every unexamined
assumption between their papers and their released code is a place our
experiment can silently die.

The reference implementation (`robodhruv/visualnav-transformer`) defines, by
its behaviour alone, the interchange format on which the entire line of work
rests: a directory of JPEG frames plus a pickled odometry dictionary. No
document specifies this format. Its constraints — image naming, yaw
continuity, minimum trajectory length, the per-robot normalisation constant
that makes actions commensurate across embodiments — exist only as the
implicit preconditions of one loader class, and several of them fail
*silently* when violated (§3). The training configurations shipped in the
repository disagree with the published papers on batch size, epoch count,
weight decay and scheduler semantics (§3.2); the repository has received no
commits in 22 months; and to our knowledge no third party has ever published
a matching-metrics reproduction of any of the three models. This is the
foundation on which downstream work, including ours, must stand. We therefore
audit it first and build second.

Our substantive question is kinematic. Every platform in the
GNM/ViNT/NoMaD training corpus — TurtleBot2, Jackal, Spot, Warthog, RC car,
ATV — is nonholonomic. The models' action space, normalised body-frame
waypoints `(Δx, Δy, cos Δψ, sin Δψ)`, *admits* lateral translation, but the
training distribution places almost no mass there: lateral displacement in
that corpus is a consequence of turning, never a commanded degree of freedom.
A mecanum-wheeled robot such as our target platform breaks this coupling. Two
opposing effects follow, and they attach to different stages of the pipeline:

- **At execution time**, a holonomic base can track a predicted `(Δx, Δy)`
  waypoint exactly, without the heading-alignment detour a differential base
  requires — a pure gain, if the predictions are good.
- **At data-collection time**, demonstrations that exploit holonomy move the
  action-label distribution off the support of the pretrained prior — a pure
  loss for transfer, if the prior matters.

Because these effects live at different stages, they are separable by
construction: we collect under both demonstration kinematics and evaluate
under both execution kinematics, giving a 2×2 whose interaction term is the
finding (§5, E2). The original works could not run this experiment; they had
no holonomic platform. To run it soundly, we need adaptation data whose
*format* fidelity is provable and whose *labels* are bit-compatible with what
the reference trainer computes — which returns us to the audit.

**Contributions.**

1. **A forensic audit of the reference implementation** (§3): eleven
   discrepancies between papers, configurations and code that are material to
   reproduction, each verified against source at a pinned commit and, where
   possible, empirically; including a latent label-corruption defect
   (yaw wrapping) that affects the *original* datasets, not merely new ones.
2. **The first written specification of the GNM trajectory format** (§4.1),
   encoded as machine-checkable constraints, with a validator, an atomic
   crash-safe writer, and a compatibility proof: data produced by our
   pipeline is loaded by the unmodified reference `ViNT_Dataset`, and our
   independent reimplementation of its action-label computation agrees with
   it to 10⁻¹⁰ across randomised trajectories.
3. **A deterministic Isaac Sim collection pipeline** (§4.2–4.4) with an
   explicit image–pose–timestamp synchronisation contract, a planner-based
   demonstrator whose design decisions are each tied to a property of the
   learning objective, and derivation procedures for the two normalisation
   constants the reference implementation hard-codes without provenance.
4. **A pre-registered empirical programme** (§5): the kinematics 2×2, a
   five-point data-efficiency curve with scratch and replay controls, a
   normalisation-constants ablation answering three unanswered upstream
   issues, and physical transfer trials on the M3 PRO. `[PENDING]`.

We claim no new architecture. The contribution is an audited foundation —
specification, proof of compatibility, provenance for every constant — of the
kind this line of work has not previously had, plus the first controlled
answer to the holonomy question it makes askable.

---

## 2. Related work

**Cross-embodiment navigation models.** GNM [1] established that aggregating
heterogeneous multi-robot data into a shared, speed-normalised waypoint action
space outperforms single-robot training even on the source platform, and that
a temporal context window can substitute for explicit embodiment
identification. ViNT [2] scaled the recipe (~80 h used, 8+ platforms),
replaced channel-stacked convolutional fusion with per-frame EfficientNet-B0
tokens under a Transformer, and — architecturally decisive for adaptation —
compressed the goal into a single replaceable token, enabling modality
swapping and full-model fine-tuning that its own ablation shows is necessary
(frozen-encoder success collapses from 0.82 to 0.32; Table 8 of [2]). NoMaD
[3] unified goal-conditioned and undirected behaviour via Bernoulli goal-token
masking and replaced the point-estimate action head with a ten-step
conditional diffusion policy, matching a 335 M-parameter subgoal-diffusion
system with 19 M parameters. Successor systems (SACSoN [4], MBRA/LogoNav [5],
CityWalker [6]) extend the data, not the interchange format; all inherit the
unspecified format we specify here.

**Sim-to-real for visual navigation.** Domain randomisation and procedural
scene generation are standard tools; what distinguishes our setting is that
the downstream consumer is a *pretrained* model with a fixed input
distribution (85×64 or 96×96, 4:3, ImageNet-normalised, no augmentation in
the reference trainer) and a fixed action normalisation, so the pipeline's
obligation is fidelity to those fixed choices rather than free design. We
know of no prior work that generates training data for this model family from
simulation with demonstrated loader-level compatibility.

**Reproduction studies.** Systematic reproduction audits are established in
machine learning broadly but rare in robot learning, where hardware
specificity gives non-reproduction an alibi. Our audit is narrower and deeper
than a survey: one codebase, at one pinned commit, read completely, with every
claim either verified in source, verified empirically, or marked unverified.

---

## 3. A forensic audit of the reference implementation

All findings refer to `robodhruv/visualnav-transformer` at commit `dca7981`
(2024-09-14, repository HEAD at time of writing), papers [1–3], and the three
released checkpoints, whose exact byte sizes and formats we verified by
download (Appendix A). Findings are numbered F1–F12 and each carries its
consequence for reproduction. The full evidence trail, with file and line
references, is in the released `docs/METHODOLOGY.md`.

**F1 — The yaw-wrapping defect.** `ViNT_Dataset._compute_actions` computes
relative heading as `yaw[1:] − yaw[0]` with no angular wrapping. A trajectory
whose recorded yaw crosses the ±π branch cut therefore yields orientation
labels containing a spurious 2π discontinuity. The reference preprocessing
scripts (`process_bags.py`, `process_recon.py`) do not unwrap yaw before
serialisation. This is consequently a latent label-corruption channel in the
*original* training corpus, whose magnitude depends on each source dataset's
odometry conventions — we flag it; quantifying its prevalence in RECON/SACSoN
is future work. Our writer unwraps on serialisation; our validator rejects
wrapped trajectories.

**F2 — Dead configuration keys.** `goals_per_obs` is assigned
(`vint_dataset.py:99`) and never read; `negative_mining` mutates a list that
is never consulted after construction. Negative goal sampling in fact occurs
unconditionally at rate `1/(max_goal_dist+1)` ≈ 1/21. Consequence: the shipped
configuration's `goals_per_obs: 2` annotation on GO Stanford ("increase
dataset size") is inert — the released models were *not* trained with GO
Stanford double-weighted, contrary to what the configuration implies. Any
description of the training mixture must describe the sampler's behaviour,
not the configuration's vocabulary.

**F3 — Paper/configuration divergences, ViNT.** Batch 300 (paper) vs 256
(config); 30 epochs (paper) vs 100 (config); weight decay 0.001 (paper) vs
AdamW's default 0.01 (config sets none); the paper's "cosine, period 10"
scheduler vs `CosineAnnealingLR(T_max=epochs)` in code, which ignores the
period setting. Disambiguation: the released `vint.pth` records `epoch=29`,
i.e. the *paper's* regime. We reproduce the paper.

**F4 — Encoders are not ImageNet-pretrained**, despite an explicit
configuration comment: `EfficientNet.from_name` is random initialisation
(`from_pretrained` would load weights), and GNM's MobileNetV2 cannot be
pretrained at all — its stem is widened to 18/21 input channels.

**F5 — Checkpoint format triad.** `vint.pth` and `gnm.pth` are pickled
training dictionaries containing *live model objects* (loading executes
arbitrary code, and fails outright under `torch ≥ 2.6`'s `weights_only`
default); `nomad.pth` is a bare EMA state-dict with no optimiser state, which
is why the repository's own resume path cannot load it (upstream issue #10,
open since 2023, the maintainer's promised fix never shipped). Additionally,
`models.yaml` references two files that do not exist: `gnm_large.pth` (its
original hosting folder now returns 404; the released `gnm.pth` is the same
model) and `vint_late_fusion.pth` (never released).

**F6 — Metric definitions are non-standard.** The reduction
`action_reduce(x) = (x·m).mean()/(m.mean()+10⁻²)` scales every reported value
by `p/(p+0.01)` where `p` is the unmasked fraction; the logged cosine
similarities pass through it and are therefore not confined to [−1, 1].
Distance labels are raw integer timesteps, unnormalised — contradicting GNM's
claim that temporal distance is estimated in the normalised scale — with the
loss weighting's 10⁻² factor compensating. Reported metrics are additionally
batch-size dependent (upstream issue #51 documents cosine similarity falling
0.96 → 0.5 from batch 400 to 1). Consequence: every offline number in this
paper states its batch size (400 throughout) and whether the reference
reduction (`strict`) or a plain masked mean was used.

**F7 — NoMaD's distance-loss goal-masking is a no-op.** The code multiplies a
*scalar* (`F.mse_loss` under mean reduction) by a per-sample mask vector; the
result is `≈0.98×` the unmasked loss at `p_m = 0.5`. The distance head of the
released checkpoint was therefore trained on goal-masked samples too. Matching
that checkpoint requires reproducing the defect.

**F8 — Double scheduler stepping.** `train_eval_loop_nomad` steps the LR
scheduler twice per epoch; a `T_max=100` cosine completes at epoch 50 and then
ascends. We patch this, reversibly, and report which schedule each run used.

**F9 — Dataset-availability drift.** `cory_hall` is an *active* dataset in
all three training configurations yet has no public source in the repository
(a lossy mirror exists via Open X-Embodiment); `scand` is annotated "private"
and is in fact public under CC0. Training as shipped fails on a missing
directory.

**F10 — Unsplittable splits.** The reference `data_split.py` shuffles with an
unseeded RNG: no published split is recoverable. Our splits are a pure
function of trajectory (or scene-group) names under a keyed hash, with a
rank-based variant for small group counts where hash thresholding has a 51 %
probability of an empty test set at 3 scenes and an 0.8 split.

**F11 — Undocumented constants.** `metric_waypoint_spacing` per dataset and
the global `action_stats = ([−2.5, −4], [5, 4])` are hard-coded with no
derivation; three upstream issues (#45, #64, #67) request one and none was
answered. Because the NoMaD scheduler runs with `clip_sample=True`, an
under-scaled range does not merely compress fast motion — it *truncates* it.
§4.4 gives derivation procedures and E4 measures the consequence.

**F12 — Two of the logged metrics are the same number.** ViNT and GNM each
log `action_orien_cos_sim` and `multi_action_orien_cos_sim` as distinct
quantities. They are provably identical. Both architectures L2-normalise the
predicted heading columns before returning (`vint.py:135–137`,
`gnm.py:85–87`), and the corresponding label columns are unit-norm by
construction in `calculate_sin_cos`; for unit vectors the mean per-waypoint
cosine `(1/T)Σₖ pₖ·lₖ` and the flattened cosine `(Σₖ pₖ·lₖ)/(√T·√T)` are the
same expression. The redundancy does not hold for the `xy` pair, whose columns
are cumulative sums of unbounded deltas. Consequence: a reproduction that
reports both as independent evidence double-counts one measurement, and a
reimplementation that accidentally computes one in place of the other passes
every check that compares against the reference logs. We report one, and pin
the identity with a test executed against the reference function itself.

The dependency stack has additionally rotted in ways that block naive
reproduction (Python 3.8.5 EOL, CUDA 10, a `diffusers==0.11.1` pin whose
unbounded `huggingface_hub` requirement now resolves to an incompatible 1.x,
ROS 1 EOL). Appendix B gives the verified working 2026 stack and the minimal
reversible patch set.

---

## 4. The pipeline

```
                         ┌─────────────────────────  ISAAC SIM 6.0.1 (headless) ─────────────────────────┐
                         │                                                                               │
  scene USDs ──────────► │  occupancy map ─► inflate(footprint) ─► sample (start,goal) ─► A* ─► smooth   │
  (≥10 environments)     │        │                                        │                    │        │
                         │        │                              perturb (35% of episodes)  pure pursuit │
  m3pro.usd ───────────► │        │                                        │                    │        │
  (measured URDF→USD)    │        ▼                                        ▼                    ▼        │
                         │  per-episode DR ──► step(): physics_dt == render_dt == 1/12 s,               │
                         │  (lights, materials)        wait_for_render, rt_subframes=4, warmup burst     │
                         │                                   │                                           │
                         │                     synchronised (RGB 640×480, pose, sim_time) per step       │
                         └───────────────────────────────────┼───────────────────────────────────────────┘
                                                             ▼
                              TrajectoryWriter: 4:3 crop ► JPEG {t}.jpg ► yaw unwrap ► fsync ► atomic rename
                                                             │
                                                             ▼
        ┌──────────────── GNM-format dataset:  <scene>_run_<n>/{0.jpg … T-1.jpg, traj_data.pkl+metadata} ──┐
        │                                                                                                  │
        ▼                      ▼                          ▼                              ▼                 │
  navfm.validate         navfm.stats               navfm.splits                 reference ViNT_Dataset  ◄──┘
  (9 constraints,        (derive spacing +         (deterministic,              (UNMODIFIED, loads our
   PASS/FAIL gate)        action_stats + clip%)     scene-grouped holdout)       data: the proof)
                                                                                       │
                                                                                       ▼
                                                    fine-tune ViNT (16 GB: 64×4 accum, frozen BN, bf16)
                                                                                       │
                                                             ┌─────────────────────────┴─────────────┐
                                                             ▼                                       ▼
                                                 offline eval (batch 400,               closed-loop eval: sim (held-out
                                                 reference-exact metrics + ADE/FDE m)   scenes) and real M3 PRO (E6)
```

### 4.1 The format, specified and proven

We reduce the loader's implicit preconditions to nine explicit constraints
(layout, pickled-dictionary schema, image-count equality, unpadded integer
naming, dtype/finiteness, **yaw continuity**, minimum length as a function of
the sampling geometry, registration of the normalisation constant, 4:3 aspect
discipline), each with its silent-failure mode documented. Three artefacts
operationalise the specification: a validator that checks all nine and
reports, per trajectory, the number of training samples the reference index
arithmetic will actually extract; a writer that is *incapable* of emitting a
violating trajectory (staging directory, schema check, fsync, atomic rename —
an interrupted collector leaves nothing the reference split tooling would
index); and the compatibility proof, run in CI: a dataset written by the
writer is loaded by the unmodified reference class, tuple shapes and dtypes
are asserted against the reference's actual 7-tuple contract (whose docstring
is itself stale — F-adjacent, documented), and our independent
`compute_actions` is asserted equal to the reference `_compute_actions` to
10⁻¹⁰ over randomised curved trajectories, under both the ViNT and NoMaD
sampling geometries.

The proof pattern matters more than the artefacts: *compatibility with an
unspecified format is an empirical claim, and we discharge it empirically,
against the reference implementation itself, not against our reading of it.*

### 4.2 Deterministic capture in Isaac Sim

The format binds `t.jpg` to `position[t]` at one simulated instant; the
renderer conspires against this. Isaac Sim 6.0 runs three clocks (run loop,
physics, renderer) and pipelines ~3 frames in flight, so the naive
read-after-update pairs each pose with an image ~3 steps stale — a systematic
label skew of ~7.5 cm at our speeds, comfortably larger than the 2.9 cm
inter-frame spacing it corrupts. Our capture contract: physics, render and
run-loop dt pinned equal (12 Hz) via the paired
`SimulationManager.setup_simulation` / `RenderingManager.set_dt` calls;
stepping exclusively through the Replicator orchestrator with
`wait_for_render=True`, which blocks until the frame the step produced is the
frame a subsequent read returns; timestamps exclusively from the simulation
clock, never the timeline; an 8-frame warm-up burst discarded after `play()`
(the frames-in-flight buffer plus margin); 4 RT subframes after teleports;
DLSS forced to quality mode, whose default performance mode artefacts below
~600×600 — precisely our regime. 12 Hz is not arbitrary: it divides by 3 into
the reference deployment stack's 4 Hz policy rate, and respects the physical
camera's universal 15 fps ceiling, so no simulated frame rate makes a
fidelity claim the hardware cannot honour.

### 4.3 The demonstrator is a modelling decision

The models learn a temporal distance `d(o_t, o_g)` and goal-directed
waypoints; both labels are meaningful only under an approximately optimal
demonstrator — under a random walk, temporal distance decouples from spatial
proximity and the distance head, which the deployment stack's topological
localisation depends on, learns noise. But a *purely* optimal demonstrator
collapses the state distribution onto shortest paths and starves the policy
of recovery behaviour, which the original corpus obtained for free from human
teleoperation error. Our demonstrator therefore: plans on an
footprint-inflated occupancy grid (A*, no corner-cutting, string-pulled to
remove the 22.5°-quantised staircase that would otherwise be *imitated* as
periodic yaw oscillation); tracks with pure pursuit at 0.45 m look-ahead
(curvature-continuous motion — jerky demonstrations put spectral content into
the labels that a 5-waypoint regressor cannot represent, surfacing as an
irreducible loss floor); and perturbs 35 % of episodes with temporally
correlated lateral noise, endpoint-pinned and per-vertex collision-checked —
sustained offsets the policy must correct, not per-step jitter that is merely
label noise. Episodes are discarded, loudly and with logged reasons, on
collision, stall, sub-minimum length, or degenerate path — each guard
matching a silent failure of the reference sampler documented in §3/§4.1.
Every accepted trajectory embeds its complete generative configuration
(sim/collect/robot/randomisation/seed) and is individually regenerable.

### 4.4 Constants with provenance

`metric_waypoint_spacing` is estimated as the frame-weighted mean inter-frame
displacement — the only definition consistent with the constant's *use* as
the divisor mapping one recorded step to a normalised displacement of 1.0 —
reported with dispersion diagnostics (a cross-trajectory spread above ~15 %
indicates an inconsistent demonstrator and gates collection, not training).
`action_stats` is estimated as symmetric quantile bounds over the exact
quantity NoMaD normalises (first-order deltas of normalised local-frame
waypoints), reported alongside the fraction of deltas the *published* bounds
would clip under `clip_sample=True`. E4 measures whether provenance matters;
F11 explains why nobody previously could.

### 4.5 Platform: kinematics, optics, and two declared deviations

The M3 PRO is a 4-wheel mecanum platform (80 mm wheels) carrying an Orbbec
DaBai DCW2 on a 6-DOF arm. We match the camera's **4:3 mode** (64°×55°,
640×480) rather than its wider 16:9 mode, because the reference pipeline
centre-crops to 4:3 — capturing 16:9 would discard ~25 % of the width and
give simulation and reality different effective fields of view. Two
deviations from stock configuration are declared rather than hidden: (i) the
arm is locked to a stowed pose and the camera treated as rigid — the format
has no representation for time-varying extrinsics and the models assume a
static viewpoint; (ii) the simulated base is velocity-driven at the
articulation root rather than wheel-contact-simulated — URDF cannot express
mecanum rollers, the labels consume only base pose, and contact-level
fidelity would purchase instability with no label-level return. Every
mechanical constant the vendor does not publish (max velocities, wheelbase,
mass, camera mount) is measured on hardware by a documented procedure before
any transfer claim (Appendix D); the vendor's own velocity-calibration
launch files are the instrument for the speed envelope.

---

## 5. Pre-registered experimental design

Design constants: held-out evaluation is **scene-grouped** (whole
environments, never trajectories, F10); every closed-loop cell runs ≥ 30
episodes over identical scenario seeds across arms, 3 training seeds per
cell, percentile-bootstrap 95 % CIs (the original papers report point
estimates without trial counts; at N = 20–40 the normal approximation is not
safe); every offline metric states batch size (400) and reduction variant
(F6). Oracle (pure pursuit on the ground-truth plan) and random-waypoint
floors calibrate every table.

**E0 — Pipeline validation (gates, partially complete).** The compatibility
proof passes in CI `[DONE]`. Offline evaluation of released `vint.pth` on a
GO Stanford holdout — to our knowledge the first published reproduction
number for this model family — `[E0.2 — PENDING]`.

**E1 — Zero-shot baselines.** Released ViNT, GNM, NoMaD on held-out Isaac
scenes under the reference controller; ViNT additionally under holonomic
execution. `[PENDING]`

**E2 — The kinematics 2×2 (primary).** Demonstration ∈ {nonholonomic,
holonomic} × execution ∈ {differential, holonomic}, equal data volume, seeds
and scenes. Pre-registered prediction: execution main effect positive,
demonstration main effect negative, ordering (nonholo-demo, holo-exec) >
(nonholo, diff) > (holo, holo) > (holo, diff). The manipulated variable is
checked *before training* via the collected sets' lateral-energy ratio
(collection gate G2.d); the mechanism claim stands or falls with the
interaction term, which we commit to reporting with its CI regardless of
sign. `[PENDING]`

**E3 — Data efficiency.** {0, 0.25, 1, 4, 16} h × {pretrained, scratch} ×
{25 % GO Stanford replay, none}. ViNT's own adaptation evidence is a single
point (<1 h, CARLA); this is the curve that point gestures at. `[PENDING]`

**E4 — Constants provenance.** Published vs derived
`metric_waypoint_spacing`; published vs derived `action_stats` (NoMaD arm),
with the measured clipped fraction as the mediating variable. `[PENDING]`

**E5 — Randomisation ablation.** {none, lighting, +materials, full} ×
{±sensor noise}, evaluated in simulation *and* carried into E6 — the
simulation column alone is known to mislead. `[PENDING]`

**E6 — Physical transfer (the gate on every claim).** Three environments
disjoint from the simulation scenes, ≥ 20 episodes per arm, zero-shot ViNT vs
the best arm of E2/E3. Metrics: success, SPL, collisions per episode (scored
against the robot's dual-LiDAR ground truth), and maximum displacement before
intervention for comparability with [2]'s cross-embodiment table. The
intervention protocol is committed before the first trial. A negative result
here, with this audit trail, is reported as the finding it would be.
`[PENDING]`

### Results

*(Tables 3–8 are emitted by `scripts/make_tables.py` from `runs/` logs;
this section intentionally contains no hand-typed numbers. Slots below bind
one-to-one to matrix cells.)*

| Table | Contents | Status |
|---|---|---|
| 3 | E0.2 reproduction number + E1 zero-shot baselines vs oracle/floor | PENDING |
| 4 | E2 2×2 with interaction term and CIs; lateral-energy ratios of the two corpora | PENDING (ratios at gate G2.d) |
| 5 | E3 efficiency curves, 4 arms × 5 volumes | PENDING |
| 6 | E4 constants ablation + clipped fractions | PENDING |
| 7 | E5 randomisation × {sim, real} | PENDING |
| 8 | E6 physical transfer | PENDING |

---

## 6. Limitations

Stated here before a reviewer states them. (i) Scene diversity is bounded by
what Isaac Sim ships plus procedural generation; we target ≥ 10 environments
and report the count prominently — transfer claims scale with it. (ii) The
simulated camera is global-shutter; the physical RGB sensor is
rolling-shutter at 15 fps — an unmodelled appearance gap under fast yaw.
(iii) Training labels use ground-truth simulation pose; the original corpus
used drifting odometry, so our policies never see drift (an injection
ablation is provided but not pre-registered). (iv) The arm-locked camera and
root-velocity base model are deviations from stock hardware configuration
(§4.5). (v) F1's prevalence in the original corpus is flagged, not
quantified. (vi) All E-slots are unfilled at draft v0.1; nothing in §5 is a
result.

## 7. Reproducibility statement

Released: the pipeline and audit (`navfm`, github.com/FAVL-AI/navfm, MIT), the pinned reference
commit and reversible patch set with printed diffs, SHA-256 hashes of all
three released checkpoints as downloaded, the collected datasets with
embedded per-trajectory generative metadata, scene identifiers/generators,
`PREREGISTRATION.md` with its commit timestamp, every gate output (G0–G6,
`docs/WORKFLOW.md`), and per-cell run directories (config, git SHA, dataset
hash, raw episode logs) from which all tables regenerate by script. The
compatibility proof runs in public CI against a fresh clone of the reference
repository. Dataset licences are inherited and stated; GO Stanford's
CC BY-NC-SA non-commercial term is respected and our own data is released
permissively.

---

## References

[1] D. Shah, A. Sridhar, A. Bhorkar, N. Hirose, S. Levine. *GNM: A General
Navigation Model to Drive Any Robot.* ICRA 2023. arXiv:2210.03370.
[2] D. Shah, A. Sridhar, N. Dashora, K. Stachowicz, K. Black, N. Hirose,
S. Levine. *ViNT: A Foundation Model for Visual Navigation.* CoRL 2023.
arXiv:2306.14846.
[3] A. Sridhar, D. Shah, C. Glossop, S. Levine. *NoMaD: Goal Masked
Diffusion Policies for Navigation and Exploration.* ICRA 2024.
arXiv:2310.07896.
[4] N. Hirose et al. *SACSoN: Scalable Autonomous Control for Social
Navigation.* RA-L 2023.
[5] N. Hirose et al. *Learning to Drive Anywhere with Model-Based
Reannotation.* 2025. arXiv:2505.05592.
[6] *CityWalker: Learning Embodied Urban Navigation from Web Videos.* 2024.
arXiv:2411.17820.

---

## Appendix A — Checkpoint provenance (verified by download, 2026-07)

| File | Bytes | Drive ID | Format | Identity evidence |
|---|---|---|---|---|
| `vint.pth` | 430,167,114 | `1ckrceGb…` | pickled training dict (live `ViNT` object) | `epoch=29`, `avg_total_test_loss=0.17398`, context 5 → the paper-regime `vint-5c` run |
| `gnm.pth` | 104,806,886 | `1bzCPd…` | pickled training dict (live `GNM` object) | `epoch=29`, encoding 1024 (= GNM-large geometry); `models.yaml`'s `gnm_large.pth` is this file under its dead former name |
| `nomad.pth` | 76,473,631 | `1YJhkk…` | bare `OrderedDict`, 645 keys | EMA weights (the deployed model; raw weights never released) |

SHA-256 hashes are recorded at Phase-0 gate G0.b and shipped in the artefact.
No official Hugging Face mirror of any checkpoint exists.

## Appendix B — The 2026 dependency matrix (each row empirically verified)

| Pin / break | Resolution |
|---|---|
| `diffusers==0.11.1` pulls `huggingface_hub` 1.x → `HfFolder` ImportError | `huggingface_hub==0.25.2` |
| `torch ≥ 2.6` `weights_only` default vs pickled checkpoints | explicit `weights_only=False` at two load sites (patch P1/P2) |
| torch/torchvision skew → `torchvision::nms` missing | matched-pair installs only |
| `EMAModel` signature change post-0.12 | stay on 0.11.1 (patch applied only if newer) |
| `diffusion_policy` not on PyPI; README clone URL is SSH-only | HTTPS clone, editable install |
| `opencv-python==4.6.0.66` wheel/Qt failures | headless variant, `MPLBACKEND=Agg` |
| `roslz4` wheels end at cp38 | `rosbags` (pure Python) for conversion |
| ROS 1 Noetic EOL 2025-05 | RobotecAI ROS 2 port for deployment |

## Appendix C — Audit finding → mitigation map

| Finding | Mitigation in the released pipeline |
|---|---|
| F1 yaw wrapping | writer unwraps; validator rejects |
| F2 dead keys | mixtures described by sampler behaviour; documented |
| F3 paper/config divergence | paper regime reproduced; both documented |
| F4 no pretraining | documented; fine-tuning starts from released weights, mooting it |
| F5 checkpoint triad | trust-gated hash-verified loader normalising all three formats |
| F6 metric quirks | reference-exact metrics with a `strict` toggle; batch size always stated |
| F7 dist-loss no-op | reproduced when matching the checkpoint; documented |
| F8 double step | reversible patch; per-run schedule recorded |
| F9 availability drift | corrected dataset table; config patch |
| F10 unseeded splits | keyed-hash / rank-based deterministic splits |
| F11 unexplained constants | derivation procedures + E4 |
| F12 duplicate orientation metric | identity pinned by an oracle test; one reported, both stored |

## Appendix D — Measured platform constants

*(Populated at Phase-1 gate G1; each value with instrument and procedure.
Until then every value in the codebase is marked PROVISIONAL and the paper
makes no claim depending on one.)*
