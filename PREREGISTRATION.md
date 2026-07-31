# Pre-registration

This file freezes the experimental protocol *before any result exists*. Its
git commit timestamp is part of the paper's evidence: hypotheses recorded
here predate every number in `runs/`. Amendments are permitted only as new
dated sections below — never edits to this one.

## Frozen protocol (v1)

- **Hypotheses H1–H5** as stated in `docs/EXPERIMENTS.md`, verbatim at the
  commit introducing this file.
- **Primary endpoint:** the E2 interaction term (demonstration × execution
  kinematics) on closed-loop success in held-out simulated scenes, with 95 %
  percentile-bootstrap CI.
- **Pre-registered E2 ordering prediction:**
  (nonholo-demo, holo-exec) > (nonholo, diff) > (holo, holo) > (holo, diff).
- **Cells:** ≥ 30 closed-loop episodes per cell; identical scenario seeds
  across arms within an experiment; 3 training seeds per cell; mean ± CI over
  seeds.
- **Splits:** scene-grouped holdout only. No trajectory-level splits appear
  in any reported table.
- **Offline metrics:** batch size 400, reference (`strict`) reduction, plus
  ADE/FDE converted to metres. Both reduction variants archived.
- **Manipulation check:** E2 proceeds only if the two collected corpora
  separate on lateral-energy ratio at collection gate G2.d; otherwise
  collection parameters are revised and re-collected *before* any training,
  and the revision is logged here as an amendment.
- **Reporting commitment:** all pre-registered cells are reported regardless
  of sign, including a negative E6.
- **Exclusion rules:** episodes excluded only by the collector's automated
  guards (collision/stall/short/degenerate) or by hardware fault noted in the
  trial log at the time of the trial. No post-hoc exclusions.

## Amendments

## Amendment 1 — 2026-07-31 (pre-results: no E2 observation exists)

**Evidential state at this commit.** No closed-loop episode has been executed,
in simulation or on hardware. `runs/` does not exist and is gitignored. The
only committed numeric artefacts are the M1 pipeline smoke outputs in
`gates/M1/`, which include cells named `e2_nonholo_diff_seed{0,1,2}` and a
"Table 4 — E2 …" heading. Those names are placeholders exercising the table
generator: the underlying runs are randomly initialised models on synthetic
noise images, and they contain **no observation of closed-loop success, scene,
or start–goal configuration** — none of the three variables this plan
concerns. This amendment therefore cannot have been shaped by any datum
bearing on E2, and the naming in that archive is recorded here so the claim
can be checked rather than taken.

**Statistical analysis plan for E2, fixed before any E2 observation exists.**

- **Success (binary).** Mixed-effects logistic regression, logit link. Fixed
  effects: demonstration regime, execution regime, and their interaction.
  Random effects: random intercepts for **scene**, and for **start–goal
  configuration nested within scene** (nested, not crossed — configurations
  are scene-specific by construction). No random slopes. Both are random
  because the same scenes and the same start–goal pairs recur across *arms* by
  design: they are repeated measures, not independent nuisance observations,
  and modelling them as fixed would understate the standard error of exactly
  the term this experiment turns on.
- **Training seed is deliberately NOT a random effect.** Frozen v1 runs 3
  training seeds per cell, and a variance component estimated from three
  levels is not identifiable. Seed variation is carried where v1 already put
  it — in the frozen "mean ± CI over seeds" per-cell summary, which stands
  unchanged — not in the episode-level model.
- **Reporting scale, and how the frozen ordering prediction is adjudicated.**
  A logistic interaction is a contrast of log-odds, and log-odds interactions
  are non-collapsible: the coefficient can be non-zero while the
  probability-scale ordering of the four cells holds, and can be near zero
  while that ordering is violated. Both are therefore reported from the same
  fit: the interaction coefficient on the log-odds scale (the primary
  endpoint), and the four model-predicted cell probabilities, against which
  the frozen ordering prediction is adjudicated. If the two disagree, both are
  reported and the disagreement is the result; neither is selected after the
  fact as the one that speaks.
- **Model-fit failure.** "Failure" means either optimiser non-convergence
  **or** a random-effect variance estimated at the boundary (a singular fit,
  which typically converges and so would otherwise slip through). A fixed
  ladder: (1) drop the nested start–goal-configuration intercept; (2) fall
  back to fixed-effects logistic regression with cluster-robust standard
  errors clustered on scene. The rung is selected **once, from the full-data
  fit, and then held fixed across every bootstrap refit** — re-selecting per
  refit would make the interval a mixture of estimators with different
  estimands. The rung used is reported with the result.
- **Primary endpoint: unchanged, including its interval procedure.** The E2
  interaction term with a **95 % percentile-bootstrap CI**, exactly as frozen
  in v1. The mixed-effects model supplies the point estimate; the interval
  remains a percentile bootstrap — 10 000 resamples (matching
  `bootstrap_ci(n_boot=10_000)` in `src/navfm/eval/metrics.py`), resampling
  scenes with replacement and carrying each scene's episodes with it, relabelling
  duplicate draws as distinct random-effect levels, refitting on every
  resample, and taking the 2.5th and 97.5th percentiles of the interaction
  coefficient. This amendment does **not** substitute a Wald or
  profile-likelihood interval for the frozen bootstrap.
- **Secondary metrics: SPL and collisions per episode.** Hierarchical
  bootstrap — not "hierarchical or pairing-respecting", which left the analyst
  a choice: resample scenes with replacement, then start–goal configurations
  within scene, 10 000 resamples, 95 % percentile CIs.
- **Two metrics are deliberately NOT used as E2 secondaries**, each for a
  stated reason, so that the omission is a commitment rather than an oversight:
  - *Trajectory efficiency* is not a separate metric. Defined the obvious way
    — reference path ÷ executed path over successful episodes — it is
    algebraically the per-episode term SPL already computes
    (`optimal / max(executed, optimal)`, `src/navfm/eval/metrics.py:294–298`),
    so `SPL = success rate × mean(efficiency | success)`. Reporting both would
    put two deterministically related quantities into one multiplicity
    correction, and conditioning on success would additionally stratify on a
    post-treatment outcome the manipulation is hypothesised to move.
  - *Maximum displacement before intervention* is an E6 metric and is not
    reported for E2. There is no intervener in simulation, and
    `navfm.eval.metrics` substitutes the executed path length when the field
    is absent, so in E2 the metric would silently report path length under a
    name that promises something else.
- **Multiplicity.** The interaction term is the sole primary endpoint and is
  not corrected. The two secondaries are reported with Holm-corrected p-values
  across the two, alongside uncorrected 95 % percentile CIs, with both
  labelled as such — a percentile CI is not itself Holm-corrected, and the
  table says which quantity carries the correction.
- **Stopping.** The per-cell episode count is fixed in the run manifest before
  collection begins and is not revised afterwards. No interim analysis is
  performed, and no episodes are added to a cell after any analysis of that
  cell has been run.
- **Hypotheses.** The E2 hypotheses **H1–H4** as stated in `paper/draft.md`
  §5 at this commit. These are scoped to E2 and are *not* the document-level
  hypotheses H1–H5 of `docs/EXPERIMENTS.md` that the frozen section pins;
  where ambiguity is possible the E2 set is written `E2-H1 … E2-H4`.
**What this amendment deliberately does NOT fix, and the gate that must.**
Four decisions depend on E2 design constants that do not yet exist, and
pretending to close them here would be precision without a basis — an
unfalsifiable number written before the thing it describes. They are deferred
*by name*, with a gate, so that deferral cannot become silence:

1. **Estimation software, optimiser, and convergence tolerance.** Different
   implementations disagree about what converges; the choice must be pinned to
   a version, not left to whoever writes the estimator.
2. **The number of held-out scenes.** The primary interval resamples scenes,
   so its effective sample size *is* the scene count. No document fixes it
   (`docs/EXPERIMENTS.md` says only "held-out Isaac scenes"). A percentile
   bootstrap over a single-digit number of clusters is near-degenerate, and
   that must be known before it is relied on.
3. **The per-cell episode count**, fixed as an exact number rather than the
   frozen lower bound of ≥ 30.
4. **The estimator implementation itself.** No mixed-model dependency is
   declared in `pyproject.toml` and no such code exists in `src/`. This plan
   is currently a commitment, not a capability.

**Gate condition.** All four are fixed in a further dated amendment to this
file, together with the estimator's type-I error rate measured on simulated
null data and its tolerance, **before the first E2 episode is collected** —
that is, before collection gate G2 opens. No E2 collection may begin while any
of the four is open. This is a blocking condition on the gate, not a note.

**Fixing or rescuing?** **Fixing** — the determination required by red-team
trigger 3, and the answer returned by two independent adversarial rounds
against two successive drafts of this amendment (both archived under
`gates/redteam/`; both classified it *fixing*, and both refuted the draft they
were given on other grounds). Three corrections the first round forced,
recorded here because the corrections are the evidence:

1. That draft said v1 "named the endpoint and the ordering prediction but not
   the estimator". That was inaccurate. Frozen v1 *does* fix an interval
   procedure (95 % percentile bootstrap) and an aggregation level (mean ± CI
   over seeds). What v1 lacked is the **model**: nothing said how the
   interaction term itself is estimated from episode-level outcomes. That gap,
   and only that gap, is what this amendment closes.
2. That draft reported the primary endpoint "with a 95 % CI", dropping the
   frozen "percentile-bootstrap" qualifier while routing bootstrap machinery
   to the continuous metrics alone. That would have *reopened* a degree of
   freedom the frozen section had already closed — the inverse of an
   amendment's purpose. Corrected above; the frozen interval procedure stands.
3. That draft claimed "no E-cell has run" without qualification, which a
   committed artefact in `gates/M1/` contradicts on its face. Corrected above
   with the precise evidential state.

The second round then refuted the *revision*, and four of its findings changed
this text: a "trajectory efficiency" secondary that was algebraically SPL's
own per-episode term and conditioned on a post-treatment outcome (removed); a
displacement metric that has no intervener in simulation and would have
reported path length under another name (removed from E2); a training-seed
random intercept estimated from three levels, which is not identifiable
(removed, with seed variation left where v1 already carried it); and the
absence of any statement reconciling a non-collapsible log-odds interaction
with a frozen prediction stated as a cell ordering (both now reported from the
same fit). Its remaining findings concern design constants that do not yet
exist and are deferred by name under the gate condition above.

No E2 observation exists, so no result can have shaped this plan. The
amendment removes analytic degrees of freedom — random-effects structure,
fit-failure fallback, resample count and level, secondary-metric selection,
multiplicity, reporting scale, optional stopping — that would otherwise have
been resolved after seeing data. Nothing in the frozen section is edited,
relaxed, redirected, or reinterpreted by it.

**Commit order, for the record.** `paper/draft.md` §5 was committed at
`8005f45` with the sentence "This plan is fixed in `PREREGISTRATION.md`
Amendment 1" while this amendment was still uncommitted — the two land one
commit apart in the same session. The binding requirement in this file's
preamble is that the pre-registration predate every number in `runs/`, which
it does: `runs/` does not exist. It is recorded here anyway, because an
audit trail that omits its own awkward orderings is not an audit trail.

Refutation and verdict archived under `gates/redteam/`.
