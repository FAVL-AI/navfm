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
2. **Prevented amendment-induced loss of estimator specificity.** That draft
   reported the primary endpoint "with a 95 % CI", dropping the frozen
   "percentile-bootstrap" qualifier while routing bootstrap machinery to the
   continuous metrics alone. The amendment would itself have made the
   estimator *less* specified than the protocol it amends, reopening a degree
   of freedom the frozen section had already closed — the inverse of an
   amendment's purpose. Corrected above; the frozen interval procedure stands.
3. That draft claimed "no E-cell has run" without qualification, which a
   committed artefact in `gates/M1/` contradicts on its face. Corrected above
   with the precise evidential state.

The second round then refuted the *revision*, and four of its findings changed
this text: a "trajectory efficiency" secondary that was algebraically SPL's
own per-episode term and conditioned on a post-treatment outcome (removed); a
**construct-validity correction** to the displacement metric, which has no
intervener in simulation — the computation succeeds, but the metric name does
not describe the quantity produced, since `navfm.eval.metrics` substitutes the
executed path length when the field is absent (removed from E2); a
training-seed random intercept estimated from three levels, which is not
identifiable (removed, with seed variation left where v1 already carried it);
and the
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

## Amendment 2 — 2026-07-31 — G0.c decision rule

Committed before any released checkpoint is evaluated. Requirements specified by
the external methodological review archived at
`docs/reviews/2026-07-31-g0c-amendment-specification.md`, with corrections from
`docs/reviews/2026-07-31-remediation-order.md`, both received through the
programme's external methodological review channel. Layers A–D, the three
classification names and the historical-anchor framing originate in that channel
and are adopted here, not independently derived.

### Historical disclosure concerning 0.17398

> Amendment 1 preregistered an order-of-magnitude relationship to the
> checkpoint-associated value `avg_total_test_loss = 0.17398`. Before any
> released checkpoint was evaluated, that criterion was retired because the
> reference value was computed over an unrecoverable five-dataset mixture,
> whereas G0.c evaluates a reconstructed GO Stanford scene-grouped holdout. No
> new empirical result motivated the retirement. The change is disclosed because
> it removed a previously committed falsifiable condition, even though that
> condition compared non-equivalent estimands.

**Correction to the mandated text above, on factual verification.** The
condition was *not* preregistered by Amendment 1: `459c65c` contains no
reference to `0.17398`, and Amendment 1 is the E2 statistical analysis plan.
The condition entered at **`92e3004`**, this repository's first commit, as
E0.2's success criterion in `docs/EXPERIMENTS.md`, and was restated in
`docs/WORKFLOW.md` as gate G0.c's green condition at **`d4fc321`** when the
gated-execution documentation was created. Both were retired at **`d6cef79`**.
Its committed life therefore spans the repository's entire pre-freeze history.
The misattribution had shortened that life and so flattered the retirement.

An order-of-magnitude relationship is reinstated below **only** as Condition 7.
`0.17398` is not an equivalent reproduction target and is not the primary
endpoint.

### Artefact binding

Every artefact exists in this amendment's commit tree or is an externally
acquired binary pinned by a committed digest record.

| Artefact | Binding |
|---|---|
| Digest record | `gates/G0/SHA256SUMS` |
| ViNT checkpoint | `155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f` |
| GO Stanford archive | `1fe1411945abd9cd0f335e845fe40d3477aac641aeb5669c961ec9debc4fb8a4` |
| Split files | `gates/G0/splits/{train,test}/traj_names.txt` |
| Split digests | train `5355ea3cb74ebea9…`, test `697035319aa417ae…` |
| Split manifest | `gates/G0/splits/split_manifest.json` |
| Scene inventory | `gates/G0/splits/scene_of.tsv`, 3696 rows |
| Grouping / allocation | `scene_key_v1`, `scene_order_v1` |
| Execution declaration | `gates/G0/evaluation_declaration.json` |
| Evaluation-pair manifest | `gates/G0/evaluation_pairs.json`, produced in the pre-execution pass, digest verified by the freeze audit |
| Canonical environment identity | `4408691cfeb89860fdf42d3db9efed012650e72dfa8c37fb917131974cbde625` |
| Upstream + patch identity | `dca79815b704…`, archived diff `gates/G0/patch.diff` (`e8a8793aaff1db39…`), application status verified at runtime |
| Evaluator | `navfm.eval.offline`, commit recorded at runtime |
| Table-lineage schema | `table{N}.jsonl`, one row per (cell, seed) |

Protocol constants: batch size 400; reference (strict) reduction; `num_workers`
0; `drop_last` false; shuffle under `torch.Generator().manual_seed(seed)`.

### Scene-grouped reconstruction

`scene_key_v1 = ^(no\d+|sim\d+)`; 3,696 trajectories; 53 reconstructed scenes;
zero unparsed; whole-scene allocation by `scene_order_v1` in ascending BLAKE2b
order; ~20 % holdout by trajectory share within each naming family; **760
held-out trajectories**; **15 held-out scenes (8 `no*`, 7 `sim*`)**; no scene in
both partitions. Described as **reconstructed** because `traj_data.pkl` carries
no native scene identifier. Both naming families retained, composition reported;
this amendment does not claim `sim*` means simulated data nor that the families
differ in acquisition modality (F-M2-3).

### Layer A — procedural validity

Enforced by `--preregistration-commit` (5 checks) and
`scripts/protocol_freeze_audit.py` (16 checks), all outcomes recorded.
Failure of any item:

> Gate execution invalid — no evidential classification. This is not a result.

### Layer B — instrument consistency, separated by variance source

**Checkpoint arm — deterministic.** `model_seed` 0, `evaluation_seed` 0,
executed twice. Identity means **exact equality of the parsed numerical and
lineage records**, not bit-identical serialized output: archives carry
timestamps and paths that differ by construction. Required identical: raw
implemented metric values, checkpoint digest, dataset and split digests,
evaluator commit, environment identity, configuration identity, evidence class,
seed declarations, table-lineage inputs. **No coefficient-of-variation
threshold is applied to a deterministic computation.**

**Control arm — three predeclared `model_seed` values 0, 1, 2**, all at
`evaluation_seed` 0. Python, NumPy, PyTorch and CUDA seeded before model
construction; replay recreates identical parameters and outputs; `random_init`
true; `checkpoint` null; evidence class ineligible for scientific tables. Across
seeds at least one parameter differs — three distinct initialisations, not three
dataloader permutations.

**Population identity across arms.** All five executions share one evaluation
population, verified at runtime against the pinned pair manifest in draw order.
Goal sampling uses a navfm-controlled stream isolated from model
initialisation; a mismatch aborts as gate execution invalid.

### Layer C — behavioural sanity ordering

**Primary implemented loss aggregate: `strict/total_loss`**, required **lower**
for the checkpoint than for the control, compared **against each of the three
initialisations individually**. Exact equality (a tie) **fails**. Secondary
implemented orderings, same rule: `strict/action_loss` and `strict/dist_loss`
lower.

Cosine similarities are **descriptive only** and are not independent
classificatory evidence: the two orientation cosines are algebraically identical
(F12), and a randomly initialised network emitting near-constant predictions can
score arbitrarily on a corpus whose headings are not directionally uniform.
Descriptive measures **must not rescue a failed implemented-loss ordering**.

Rank correlation of temporal distance is **not part of G0.c** — not implemented,
no manifest key, no column. It may become a criterion only if separately
implemented and preregistered before execution.

### Layer D — historical-anchor interpretation

Descriptive: order of magnitude versus 0.17398; direction of deviation;
plausible causes (dataset population including F-M2-3, split reconstruction,
weighting, batching, audit findings); whether any direct comparison remains
defensible.

### Per-family descriptive breakdown

Metrics reported separately for `no*` and `sim*` beside pooled numbers.
Descriptive/diagnostic only — not a criterion, not an endpoint, not entering any
multiplicity family, asserting nothing about family origin.

### Classification 2 — Reconstructed but not reproduced

Available only if **all seven conditions pass. They are conjunctive.**

1. **Procedurally valid execution.** Amendment exists at the declared commit;
   commit recorded and an ancestor of the execution commit; all pinned artefacts
   resolve in the amendment commit's tree; worktree clean or declared; no prior
   G0.c result directory; checkpoint digest matches at runtime; canonical
   environment identity matches; split and dataset digests match.
2. **Complete instrument execution.** No required test absent, skipped,
   deselected or uncollected; upstream-marked population equals the pinned count
   against the pinned upstream commit and manifest hash; all required outputs
   produced; all seeds and deterministic repetitions complete; all lineage
   records and manifests present; no contamination-barrier override used for a
   scientific table.
3. **Deterministic checkpoint-arm repeatability**, as defined in Layer B.
4. **Random-control replayability and distinctness**, as defined in Layer B.
5. **Metric validity and completeness.** Every classificatory metric implemented
   before execution, with a declared manifest key and declared role; finite;
   within its mathematically valid range; traceable through the lineage record
   to raw outputs; not duplicating another classificatory metric algebraically
   or deterministically.
6. **Predeclared behavioural sanity ordering**, complete, as defined in Layer C.
7. **Limited historical-anchor relationship.** The checkpoint's declared
   total-loss quantity `L` — that is, `strict/total_loss` — satisfies
   **0.1 ≤ L / 0.17398 ≤ 10**, equivalently 0.017398 ≤ L ≤ 1.7398. Reported as a
   historical-anchor sanity condition, **not a reproduction tolerance**. Any
   deviation is interpreted in light of the non-equivalent dataset population,
   the reconstructed split and the unrecoverable upstream mixture. Satisfying it
   does **not** establish reproduction; failing it prevents Classification 2 but
   does **not** by itself establish non-reconstructability.

### Classification 3 — Not reconstructable

Reserved for cases where the relationship between the released artefacts,
available code, available data and the reported upstream evaluation cannot be
reconstructed to a scientifically defensible minimum.

**Not to be used for:** a high loss; failure to outperform the random control;
failure of deterministic replay; a corrupted download; an environment mismatch;
missing seeds; incomplete execution; a failed test; an implementation defect; an
inconvenient or unexpected metric value. Those are respectively behavioural
findings or invalid gate executions.

**May be assigned only** where all applicable acquisition and procedural
controls completed but a load-bearing element remains unavailable or
irrecoverably ambiguous — for example: the checkpoint cannot be associated with
a defensible evaluation configuration; the required evaluation population cannot
be identified or reconstructed; the reported metric cannot be computed from the
released code or artefacts; the original mixture or weighting is indispensable
and unrecoverable; the relationship to the reported upstream result cannot be
stated without unsupported assumptions; artefact incompatibility prevents a
meaningful evaluation despite verified files and a valid environment.

The report must identify the exact missing or ambiguous element and explain why
no narrower reconstruction is defensible. Classification 3 is an evidential
finding about the limits of the released record, not a synonym for gate failure.

### Classification 1 — Reproduced

Available only if an evaluation materially equivalent to the reported upstream
evaluation is reconstructed and satisfies a preregistered numerical equivalence
criterion. Given F10, the unrecoverable original splits and the five-dataset
composition behind 0.17398, it is not expected unless new documentary or
artefactual evidence recovers the missing protocol. **The meaning of
reproduction is not weakened to make Classification 1 attainable.**

### Outcome mapping, declared before execution

| Layer B | Layer C | Outcome |
|---|---|---|
| Fails | Not adjudicated | Gate execution invalid — no evidential classification |
| Passes | All preregistered conditions pass | Classification 2, subject also to Conditions 1–5 and 7 |
| Passes | Partial behavioural conditions pass | Valid instrument execution with insufficient behavioural evidence for Classification 2 |
| Passes | Behavioural sanity ordering fails | Valid negative behavioural finding; not Classification 2 and not Classification 3 |
| Passes | Upstream relationship remains scientifically indefensible because of irrecoverable specification | Classification 3, if the reserved-scope requirements are met |
| Passes | All Layer-C orderings pass; **Condition 7 fails** | Valid instrument execution with failed historical-anchor sanity. This is a diagnostic outcome. It blocks Classification 2, is not Classification 3, does not populate the preregistered scientific result table, and mandates investigation of scale, normalisation, evaluator configuration, dataset identity, checkpoint identity, or other pipeline factors before any subsequent execution. Any execution following that investigation constitutes a new experimental run, receives a new run identity, and records an explicit lineage link to the originating diagnostic run. The original diagnostic run remains immutable and is not reclassified retrospectively. |

Every partial case has a declared home. No outcome may be assigned
retrospectively by narrative discretion. The partial-Layer-C outcome is a
diagnostic result and must not populate the preregistered scientific result
table as "Reconstructed but not reproduced".

**Declared expected classification: 2**, on the reasoning that the available
evidence indicates the target evaluation and the original splits are
non-equivalent.

### Epistemic limits

This amendment does not validate itself. The freeze audit establishes declared
procedural properties, not scientific validity. Conformance to the pinned
upstream implementation establishes consistency with it, not conceptual
correctness of the upstream metric or design. A green gate does not guarantee a
correct scientific conclusion. G0.c can fail — procedurally as an invalid
execution, and evidentially as a negative behavioural finding, a diagnostic
outcome, or a non-reconstructability finding.

Whether this amendment constitutes fixing rather than rescuing is a
determination for red-team review under trigger 3, recorded in
`gates/redteam/`. It is not claimed here.
