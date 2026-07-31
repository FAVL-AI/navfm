# Experiment matrix and publication plan

The framing: this is an **empirical systems and transfer** contribution, not an
architecture contribution. Do not claim a new model. Claim a validated pipeline,
a controlled study of simulation-to-real transfer for pretrained navigation
foundation models, and a specific finding about holonomic bases.

Every run below fits in 1–2 GPU-hours on the RTX 4080 SUPER (see
`docs/METHODOLOGY.md` §6), so the full matrix is a few days of compute, not
months. That is the reason to do it properly.

---

## Hypotheses

**H1 — Simulation data adapts ViNT to a new embodiment.**
Fine-tuning ViNT on Isaac-collected M3 PRO data improves closed-loop success on
held-out *simulated* environments over zero-shot ViNT, and the improvement
survives transfer to the physical robot.
*Null result is publishable and would itself be informative.*

**H2 — Holonomic execution helps; holonomic demonstration hurts.**
The pretrained action prior has near-zero mass on lateral motion. Executing
predicted `(dx, dy)` waypoints on a mecanum base should help (no nonholonomic
detour), while *collecting* strafing demonstrations should hurt (labels off the
prior's support). This predicts the 2×2 ordering
`(nonholo-demo, holo-exec) > (nonholo, nonholo) > (holo, holo) > (holo, nonholo)`.
This is the sharpest and most novel question in the project.

**H3 — Data efficiency.** ViNT's own CARLA result claims <1 h of target data
suffices. Test whether that holds for simulation-sourced data and a mecanum
platform, as a curve, not a point.

**H4 — Derived normalisation constants matter.** Replacing the hard-coded
`action_stats` / `metric_waypoint_spacing` with values derived from the target
platform changes measurable performance. Cheap to test, and it answers three
unanswered upstream issues.

**H5 — Appearance randomisation dominates the sim2real gap** for these
RGB-only, geometry-output models — more than dynamics randomisation does.

---

## Matrix

### E0 — Pipeline validation (do this first, it gates everything)

| Run | What | Success criterion |
|---|---|---|
| E0.1 | Load navfm-written data through upstream `ViNT_Dataset` | `tests/test_upstream_compat.py` passes (**done**) |
| E0.2 | Evaluate released `vint.pth` on GO Stanford test split, batch 400 | total test loss within an order of magnitude of the checkpoint's recorded 0.17398 |
| E0.3 | Fine-tune ViNT on GO Stanford train for 1 epoch | loss decreases; no BatchNorm-drift rise in epoch 1 |
| E0.4 | Collect 20 Isaac episodes, validate, register, split | `navfm.validate` PASS, acceptance rate > 70 % |

Report E0.2's number. Nobody has published a reproduction of these models;
even a single verified offline number is a contribution to the record.

### E1 — Zero-shot baselines (no fine-tuning)

Closed-loop in held-out Isaac scenes, `N ≥ 30` episodes per cell, bootstrap CIs.

| Arm | Model | Execution |
|---|---|---|
| E1.1 | ViNT (released) | differential PD (reference `pd_controller`) |
| E1.2 | ViNT (released) | holonomic |
| E1.3 | NoMaD (released), goal-conditioned | differential |
| E1.4 | GNM (released) | differential |
| E1.5 | pure-pursuit oracle on the ground-truth plan | — (upper bound) |
| E1.6 | random-waypoint policy | — (lower bound) |

E1.5 and E1.6 are not padding: without them, "0.62 success" is uninterpretable.

### E2 — H2, the 2×2 (the headline experiment)

| Arm | Demonstrator | Execution |
|---|---|---|
| E2.1 | nonholonomic | differential |
| E2.2 | nonholonomic | **holonomic** |
| E2.3 | holonomic | differential |
| E2.4 | holonomic | holonomic |

Same data volume, same seeds, same scenes in every cell. Report the interaction
term, not just the four means. Include the lateral-energy ratio of each training
set (`navfm.stats` reports it) as the mechanistic explanation.

#### E2 hypotheses

Scoped to E2, and written `E2-H1 … E2-H4` wherever ambiguity with the
document-level hypotheses H1–H5 above is possible. E2 is the experiment that
tests document-level **H2**; the four below are what H2 decomposes into.
Stated verbatim in `paper/draft.md` §5 and pinned by `PREREGISTRATION.md`
Amendment 1.

- **E2-H1 (primary).** A policy trained on trajectories generated under one
  kinematic regime exhibits systematic degradation when executed under a
  different regime, even when visual observations, goal definitions, and
  evaluation environments are held constant.
- **E2-H2.** That degradation is not fully explained by path length or action
  discretisation, and manifests differently across success, collision,
  trajectory-efficiency, and stopping metrics.
- **E2-H3.** Demonstration-side and execution-side changes are asymmetric.
- **E2-H4.** Some apparent transfer improvements disappear or reverse under
  fixed batching, seed control, and evidence-valid evaluation.

#### Analysis plan

Fixed in `PREREGISTRATION.md` Amendment 1 before any E2 observation exists;
that file is authoritative and this is a summary of it. Success is modelled by
mixed-effects logistic regression — demonstration regime, execution regime and
their interaction as fixed effects; random intercepts for scene and for
start–goal configuration nested within scene, because both recur across arms
by design and are repeated measures rather than independent observations.
Training seed is deliberately *not* a random effect: three levels do not
identify a variance component, and seed variation is carried by the frozen
"mean ± CI over seeds" per-cell summary instead.

The primary endpoint is the interaction term with a **95 % percentile-bootstrap
CI**, as frozen in v1 — 10 000 resamples of scenes with their episodes,
refitting each time. Because a logistic interaction is non-collapsible, the
four model-predicted cell probabilities are reported alongside it, and the
frozen ordering prediction is adjudicated against those; if coefficient and
ordering disagree, both are reported and the disagreement is the result.

Secondaries are **SPL and collisions per episode**, with Holm-corrected
p-values across the two plus uncorrected percentile CIs, both labelled.
Trajectory efficiency is *not* reported separately — it is algebraically SPL's
own per-episode term — and maximum displacement before intervention is an E6
metric, not an E2 one. No collapsing of the factorial into pairwise contrasts
is reported.

Four items remain open by design and **block collection gate G2** until a
further dated amendment fixes them: estimation software and tolerance, the
held-out scene count, the exact per-cell episode count, and the estimator
implementation itself.

### E3 — H3, the data-efficiency curve

Fine-tune on `{0, 0.25, 1, 4, 16}` hours of Isaac data × `{with, without}`
pretrained initialisation × `{with, without}` GO Stanford replay at 25 %.
Ten cells. The scratch arm is what makes "pretraining helps" a measurement
rather than an assumption.

### E4 — H4, normalisation constants

| Arm | `metric_waypoint_spacing` | `action_stats` |
|---|---|---|
| E4.1 | published `recon` value (0.25) | published |
| E4.2 | derived from our data | published |
| E4.3 | derived | derived |

E4.2 vs E4.3 isolates the diffusion-head normalisation (NoMaD only; ViNT does
not use `action_stats`).

### E5 — H5, randomisation ablation

`{none, lighting only, lighting + materials, full}` × `{with, without}` sensor
noise. Evaluate on held-out scenes *and* on the real robot — the sim-only
column will mislead if reported alone.

### E6 — Real-robot transfer (the claim that carries the paper)

Physical M3 PRO, 3 environments not represented in the Isaac scenes, ≥ 20
episodes each. Report success rate, SPL, collisions per episode, and maximum
displacement before intervention (the ViNT paper's metric, so numbers are
comparable). Zero-shot ViNT vs the best fine-tuned arm from E2/E3.

**This is the gate on publishability.** Everything before E6 is simulation
talking to itself.

---

## Metrics and reporting

Offline (per `navfm.eval.metrics`, matching upstream definitions exactly):
`action_loss`, `dist_loss`, `action_waypts_cos_sim`,
`multi_action_waypts_cos_sim`, plus ADE/FDE in **metres** (multiply normalised
ADE by `metric_waypoint_spacing` — normalised MSE is not interpretable and
reviewers will ask).

Closed-loop: success rate, SPL, collisions/episode, max displacement before
intervention.

Non-negotiables for the write-up:

* **State the evaluation batch size.** Upstream issue #51: cosine similarity
  drops 0.96 → 0.5 between batch 400 and batch 1. A metric without its batch
  size is not a metric here.
* **Bootstrap CIs on every cell** (`navfm.eval.metrics.bootstrap_ci`). The
  original papers report point estimates with no trial counts; at N = 20–40 the
  normal approximation is not safe.
* **Report the reference-quirk flags you used.** `action_reduce`'s `+1e-2`,
  the NoMaD `dist_loss` no-op, the double `lr_scheduler.step()`. Say which you
  reproduced and which you fixed. Reviewers who know this codebase will check.
* **Scene-level holdout**, always (`--group-by scene`). A trajectory-level
  random split over four USD scenes measures memorisation.
* **Seeds.** Three per cell minimum; report mean ± CI over seeds, and fix the
  scene/episode sampling seed so cells see identical scenarios.

---

## Negative results are outcomes, not setbacks

A negative, null, or inconclusive result in any pre-registered cell is a
reportable outcome and is reported with the same prominence as a positive one.
That is not magnanimity; it is what makes the programme's research questions
answerable. RQ1 asks under what conditions a performance claim can be
independently reconstructed and considered evidentially valid — a cell that
fails to reconstruct is *direct evidence* about those conditions. RQ2 asks how
demonstration/execution/evaluation mismatch affects the validity of transfer
claims — an absent or reversed effect answers it as informatively as a present
one. RQ3 asks whether calibrated evidence supports better decisions than
uncalibrated policy output — "it does not" is a finding.

The frozen pre-registration already commits to reporting all cells regardless
of sign, including a negative E6. This section states why that commitment
costs nothing: under RQ1–RQ3 the sign of the effect is not the deliverable,
the validity of the inference is.

## Failure record convention (`gates/failures/`)

Every failure that threatens a claim gets a record, whether it was caught by a
test, a gate, a review, or a person reading the archive months later. The
purpose is not blame-keeping. It is that **claim correction yield** — the
number and materiality of conclusions changed, narrowed, or rejected once the
controls are applied — is one of the programme's five KPIs, and a KPI with no
ledger is a slogan.

One file per failure, `gates/failures/F-<scope>-<n>.md`, with these nine
fields, all of them required:

| Field | What it records |
|---|---|
| 1. What failed | the specific behaviour, not a category |
| 2. How detected | test, gate, review, manual inspection — and whether it was found by the control that was supposed to find it |
| 3. Claim threatened | the sentence, table, or README statement that would have been wrong |
| 4. Source | exactly one of: data / code / configuration / protocol / environment / measurement |
| 5. Correction | what changed, with the commit |
| 6. Pre-registered? | was the affected analysis or protocol pre-registered at the time of failure |
| 7. Results changed? | did any reported number, table, or conclusion move — and if none existed yet, say so |
| 8. Residual uncertainty | what is still not known after the correction |
| 9. Gate blocked or reopened | which gate, if any, was blocked, failed, or had to be re-run |

Field 7 is the one that feeds the KPI, and it is answered honestly even when
the honest answer is "no results existed yet, so nothing moved" — a defect
caught before it could contaminate a number is the cheapest possible
correction, and the ledger should show that the controls are catching things
early rather than only recording expensive failures.

## Threats to validity, and the mitigation for each

| Threat | Mitigation |
|---|---|
| Scene diversity too low (4 stock USDs) | Infinigen procedural generation or NuRec; report the scene count prominently; do not overclaim generalisation |
| M3 PRO mechanical parameters are guessed | run the vendor's own `calibrate_linear` / `calibrate_angular`; mark every unmeasured value PROVISIONAL until then (`docs/HARDWARE.md`) |
| Camera locked to a stowed arm pose is not stock configuration | state it; report the fixed transform |
| Rolling vs global shutter | state it; consider a rolling-shutter post-process as an ablation |
| Ground-truth pose has no odometry drift | `--odometry-noise` injects a calibrated drift model; run it as an ablation |
| Held-out sim scenes are still Isaac scenes | E6 is the only real answer |
| Comparing to paper numbers collected on different robots in different buildings | never claim a direct comparison; use paper numbers as context, your own baselines as the comparison |

---

## Venue and framing

**CoRL / ICRA / IROS / RA-L**, or a datasets-and-benchmarks track. The story:

> Navigation foundation models are trained on real-robot data from
> differential-drive platforms. We ask whether simulation can supply the
> adaptation data for a new embodiment, and specifically for a holonomic one
> whose action space the pretrained prior barely covers. We contribute a
> validated simulation-to-GNM-format pipeline, a controlled study of the
> demonstration/execution kinematics interaction, and real-robot transfer
> results.

What makes it more than a reproduction:

1. the format specification and validator, checked against the reference loader
   (and the yaw-unwrapping bug it exposes in the original preprocessing);
2. the holonomic demonstration/execution 2×2 — a question the original papers
   could not ask, because they had no holonomic platform;
3. derived rather than inherited normalisation constants, answering three
   open questions about the reference implementation;
4. a sim2real data-efficiency curve where the original has a single point.

Release the code, the Isaac scenes, the collected dataset, the checkpoint
hashes, and the exact upstream commit + patch set. Given that no public
reproduction of these models exists, the artefact is a substantial part of the
contribution.
