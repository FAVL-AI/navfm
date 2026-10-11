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

## Amendment 3 — 2026-08-07 — compatibility correction and patch-identity re-binding

Narrow by construction. This amendment updates the upstream-patch-identity
binding and declares the tolerance under which the compatibility correction is
accepted. It changes no classification rule, no layer, no condition, no seed
and no population. Amendments 1 and 2 are untouched; the frozen section is
untouched.

**Evidential state.** No released checkpoint has been evaluated. `runs/` does
not exist. No G0.c metric exists. `vint.pth` has never been loaded.

### Corrected compatibility rationale

The released GO Stanford representation is uniformly incompatible with the
released loader under current NumPy semantics. Contemporaneous NumPy accepted
the relevant ragged-array construction only through deprecated behaviour and
did not provide a clean explicit-coercion reference path. The proposed scalar
coercion is therefore classified as a numerical-semantics-preserving
compatibility adaptation, not era-fidelity restoration.

### Asserting coercion constraint

The adaptation may coerce only values containing exactly one scalar element.
Empty or multi-element values cause explicit refusal. Silent first-element
selection is prohibited.

### Floating-point tolerance declaration

The compatibility correction shall be assessed at the **input site**: the point
in `vint_dataset.py` where a trajectory's `traj_data` is unpickled and enters
the loader, which is where the correction is applied (patch
`contract_normalisation_call`) and therefore the only site at which the
coercion's own numerical effect is observable in isolation.

This is deliberately *not* the later
`torch.as_tensor(..., dtype=torch.float32)` conversion. Between the input site
and that conversion the loader computes relative positions, orientations and
labels; a difference measured there is the sum of the coercion and all
intervening arithmetic, and would not isolate the quantity this clause bounds.

The values this clause compares are the loader's **inputs**. They are
subsequently transformed by `to_local_coords(...)` and the `yaw[1:] - yaw[0]`
difference, and divided by `metric_waypoint_spacing * waypoint_spacing`, before
tensorisation (`vint_dataset.py`, `_compute_actions`). This clause therefore
bounds the input representation only and makes **no** claim that a 0-ULP input
difference implies a 0-ULP difference after that arithmetic.

The post-arithmetic quantity is bounded separately, and directly, by the B − A
measurement recorded below — which is `bit_identical` at the action labels
themselves, i.e. measured after the arithmetic, not extrapolated through it.
That is the only reason an input-site bound is sufficient here, and it would
not be sufficient without it.

One figure in `comparison.json` must not be read as evidence of amplification:
the recorded `max_rel` of `2.14 × 10^14` on the action labels is an artefact of
division by zero, not a measured sensitivity. As
`gates/G0/measurement/README.md` records, every large relative value occurs
where the true value is exactly `0.0`; among elements with `|true| > 10^-6` the
maximum relative difference is `6.6 × 10^-11`. The associated absolute
difference of `1.7763568394002505 × 10^-15` is itself an **action-label**
difference measured after `_compute_actions`, not an input difference.

For every scalar value in `position` and `yaw`, the value produced by the
corrected normalisation path shall be compared with the corresponding scalar
represented by the released trajectory data, read by an independent route that
shares no code with the correction.

Both values shall be evaluated as IEEE-754 `float32` values at this declared
comparison site.

The permitted numerical difference is:

> **No more than 1 ULP of the corresponding `float32` reference value,
> evaluated separately for every scalar.**

This tolerance is subject to all of the following conditions.

1. **Per-scalar comparison.** The tolerance applies independently to every
   scalar value. An average, maximum aggregate error, trajectory-level average
   or cancellation between positive and negative errors shall not be used to
   make a failing scalar pass. If one scalar exceeds the tolerance, the
   compatibility check fails.
2. **Normal finite values.** For every non-zero finite value, the corrected
   value must have the same sign as the reference value. The ULP distance is
   the number of adjacent representable IEEE-754 `float32` values between the
   reference value and the corrected value. A difference of zero representable
   values is 0 ULP. A difference of one adjacent `float32` value is 1 ULP.
3. **Zero.** Positive zero and negative zero are treated as numerically
   equivalent for `position` and `yaw`. This is permitted because the sign bit
   of zero has no semantic meaning for the trajectory representation used by
   the navigation model. No non-zero value may be converted to zero merely to
   satisfy the tolerance.
4. **Subnormal values.** Subnormal `float32` values are permitted. For
   subnormal values, one ULP is the spacing between adjacent `float32`
   subnormal values, equal to the smallest positive representable `float32`
   increment. Subnormal values must not be flushed to zero by the compatibility
   correction.
5. **NaN and infinity.** `NaN`, positive infinity and negative infinity are not
   valid trajectory values. Their presence shall cause validation to fail
   before training or evaluation. They shall not be replaced, clipped or
   coerced into finite values.
6. **No truncation.** The compatibility correction may unwrap a cell only when
   that cell contains exactly one numerical value. A cell containing zero
   values or more than one value shall be rejected. The correction shall not
   use a truncating operation equivalent to selecting only the first element of
   a multi-valued cell.
7. **Shape invariants.** After normalisation: `position` must have shape
   `[T, 2]`; `yaw` must have shape `[T]`. The value of `T` must remain
   unchanged for the trajectory.
8. **Ordering invariants.** The correction must preserve the original temporal
   ordering of all trajectory samples. No position or yaw value may be
   reordered, inserted, removed, duplicated or interpolated.
9. **Population invariants.** Applying the correction must not change the
   admitted GO Stanford population. The frozen population must remain 3,696
   trajectories. No trajectory may be removed because its representation is
   inconvenient to convert.
10. **Semantic invariants.** The correction changes only the container
    representation required by the released loader. It must not alter the
    recorded physical meaning of: `position`; `yaw`; trajectory length; sample
    order; trajectory identity; dataset membership.
11. **Comparison result.** The compatibility correction passes the numerical
    tolerance requirement only when every eligible scalar satisfies the
    declared `float32` tolerance and every semantic invariant above also holds.
    Passing the numerical tolerance alone is not sufficient.
12. **Trigger-3 failure condition.** Trigger-3 shall reject the correction if
    any of the following occurs: a scalar exceeds 1 ULP; a multi-valued cell is
    truncated; a shape changes; trajectory ordering changes; a trajectory is
    dropped or added; a non-finite value is silently repaired; or any other
    semantic invariant is violated.

### Measured evidence

Recorded as measured evidence, not as part of the tolerance definition:

> The measured compatibility study found no numerical change caused by the
> asserting coercion at a fixed NumPy version. Cell B − Cell A, which isolates
> the representation effect with NumPy held constant, is recorded in
> `gates/G0/measurement/comparison.json` as `bit_identical: true` with
> `max_abs: 0.0` for the action labels: the coercion's measured numerical
> effect is exactly zero, not merely small. The end-to-end Cell C − Cell A
> residual is `1.7763568394002505 × 10^-15`, and is attributable to
> NumPy-version behaviour rather than to the coercion.

Verification of the tolerance clause itself, run over the complete corpus by
`scripts/verify_tolerance.py` and archived verbatim at
`gates/G0/tolerance_verification.txt`: 3,696 of 3,696 trajectories converted,
zero refused, zero dropped; **594,378 scalars compared, maximum ULP distance
0** at the declared `float32` site; sign, zero, shape, ordering and population
invariants holding. The reference side of that comparison is read by a route
sharing no code with the correction; the check was mutation-tested, with the
results archived at `gates/G0/tolerance_mutation_evidence.txt`: an identity
control survives, while a 2-ULP perturbation, a reordering, a column
transposition, a dropped sample and a one-place shift are all caught.

The declared bound is far looser than the achieved result, and this is recorded
rather than presented as headroom. Mutation testing of the tolerance clause
shows it admits a uniform relative perturbation of `3 × 10^-8` at the input
site while catching `6.5 × 10^-8` (archived in the same file), whereas the
measured effect of the correction is bit-identical at `float64` — 0 of 594,378
scalars differ. The bound was therefore set after B − A
bit-identity was already known: it is a conformance limit chosen to be
comfortably satisfiable, not an independent prediction. It grades the
correction, not any hypothesis, and no G0.c result existed when it was written
— but it must not be cited as evidence that the correction is accurate to 1
ULP. The evidence for that is the measured 0.

Three of the twelve conditions hold **vacuously** on this corpus, and are
recorded as such rather than reported as passes: the corpus contains 0
subnormal values (condition 4), 0 multi-valued cells (conditions 6 and 12's
truncation limb), and no non-finite values. Their subjects are absent, so this
run is evidence that the corpus does not exercise them, not evidence that the
correction handles them. The handling is evidenced instead by
`tests/test_trajio_contract.py`, which constructs each absent case directly.
386 exact zeros are present, but the archived run records **0 negative
zeros**, so condition 3's operative content — the `+0 ≡ -0` equivalence — has
no subject either and is a fourth vacuous clause. The negative-zero count is
measured and reported separately for this reason: an earlier draft asserted it
with no instrument behind it, and keyed the annotation on the zero count, which
would have printed identically on a corpus that did contain one. Its other limb, that no non-zero value
may become zero, does have 594,378 subjects and is checked.

These counts are measured per run from the released cells, before conversion,
and vary with the corpus. An earlier draft printed the multi-valued-cell count
from a counter that was never incremented, so its "VACUOUSLY" annotation would
have printed even on a corpus that had just been refused for containing one.

The two figures answer different questions, and neither is a margin against the
other: `1.776 × 10^-15` is the downstream residual between the era path and the
canonical path, measured after the loader's arithmetic, while 0 ULP is the
input-side coercion measured at the site this clause declares. This clause
bounds only the second. No ratio between them is claimed, because the declared
tolerance and the end-to-end residual are not measured at the same site.

### Artefact re-binding

Amendment 2's artefact-binding table is amended in one row only:

| Artefact | Previous binding | This amendment |
|---|---|---|
| Upstream patch identity | `gates/G0/patch.diff` = `e8a8793aaff1db39…` | `gates/G0/patch.diff` = `f77e1a655a12020a0bfdaf38bf344dc40b62bc9b27fd0d354ec0720b25a1ee6f` |

Upstream commit remains `dca79815b704…`. All other bindings — checkpoint
digest, archive digest, split files and digests, scene inventory, grouping and
allocation versions, canonical environment identity, evaluator, table-lineage
schema — are unchanged and remain as bound in Amendment 2.

The freeze audit compares against the **amendment-pinned** value, not current
state, and must never observe the new patch under the old binding. This is
enforced, not merely asserted: `upstream_patch_identity_verified` in
`scripts/protocol_freeze_audit.py` requires three things to agree —

1. the digest **pinned in this file, read from the amendment commit's blob**
   via `git show <amendment-commit>:PREREGISTRATION.md`, with exactly one such
   pin required;
2. the **archived** `gates/G0/patch.diff`, read from that same commit;
3. the **live clone's** actual `git diff` — the code the gate will execute.

All three must equal
`f77e1a655a12020a0bfdaf38bf344dc40b62bc9b27fd0d354ec0720b25a1ee6f`.

Each of those three was added because its absence had already been shown to let
something through, and the reasoning is recorded because the earlier versions of
this paragraph asserted a control that did not exist:

* the audit originally computed the digest and only **printed** it, comparing
  it against nothing;
* the first correction compared the pin against the archived diff but read
  **both from the worktree**, which is a self-consistency check that any single
  coordinated edit satisfies — it was demonstrated passing against a fabricated
  digest;
* neither version inspected the **live clone**. A clone whose patched function
  body had been replaced with a truncating implementation — precisely what
  conditions 6 and 12 forbid — kept its marker count and its archived diff, and
  passed. Marker counting cannot detect this, because markers survive an edit
  to the code beneath them.

Two further corrections belong in this record, because both were claims this
amendment made before they were true:

* The revert path of `scripts/patch_upstream.py` left `vint_dataset.py`
  patched while reporting `0 failed`, and never reverted the `cory_hall`
  config edits at all. Both are fixed; apply-then-revert now returns the clone
  to a bit-identical state, verified by `git status --porcelain` reporting zero
  dirty files. The re-pinned digest above is the first one generated from a
  clone whose patch state is known rather than assumed.
* Re-pinning this digest required a **pristine** clone, and the first attempt
  did not use one. Editing a patch's replacement text makes `--revert` unable
  to match the already-applied region, so the revert failed, the re-apply
  skipped the patch as "already applied", and the regenerated diff carried the
  OLD text under a digest that appeared unchanged. The `new == text` guard
  above reported the failure correctly; it was read past. The digest pinned
  here is generated from `git checkout -- .` followed by a single apply, and
  its apply/revert round trip returns the clone to zero dirty files. Any future
  change to patch text must repeat that sequence rather than patch in place.
* `scripts/verify_tolerance.py` originally read its reference values with the
  same element-selection the correction uses, which made the comparison
  tautological — the two sides were equal by construction and the ULP check
  could not fail. The reference is now read by an independent route
  (NumPy's own object→float conversion for `position`, cell concatenation for
  `yaw`). The 0-ULP result above is from the corrected, falsifiable check.

### Evaluation-population binding

The earlier 44,038-sample compatibility measurement did not match the upstream
evaluator's exact valid-timestep population and is not treated as full
registered-population coverage. G0.c is bound instead to the committed
evaluation-pair manifest produced under the amended loader and frozen before
checkpoint execution.

### Epistemic limits

This amendment does not validate itself. Whether it constitutes fixing rather
than rescuing is a determination for red-team review under trigger 3, recorded
in `gates/redteam/`. It is not claimed here.

## Amendment 4 — 2026-08-07 — clarification of criterion lifetime

**Trigger-3 classification: fixing.** This amendment changes no threshold, no
condition, no decision rule, no population and no classification boundary. It
corrects one factual description in the committed record.

The earlier statement that the criterion "spans the repository's entire
pre-freeze history" is imprecise.

The criterion was introduced at commit `92e3004`. The preregistration freeze
occurred at commit `d4fc321`. The criterion was retired at commit `d6cef79`,
which occurred 8 hours 28 minutes after the freeze.

Therefore the criterion's committed lifetime began before the freeze and
continued after the freeze. It should not be described as being bounded by, or
wholly contained within, the repository's pre-freeze history.

| Event | Commit | Relationship |
|---|---|---|
| Criterion introduced | `92e3004` | Start |
| Preregistration frozen | `d4fc321` | Criterion still active |
| Criterion retired | `d6cef79` | 8 h 28 m after freeze |

The earlier misattribution of the criterion's introduction had already been
corrected at `8cb0e18`, in the paragraph immediately following the mandated
blockquote, under `docs/reviews/2026-07-31-remediation-order.md` §1 and verified
closed in `gates/redteam/trigger3-g0c-amendment-v3-2026-07-31.md`, committed in
that same commit. **This amendment does not perform that correction.** It records
the verified lifetime of the criterion and corrects only the remaining
description of that lifetime.

### Correction to an interval quoted during review

The previously stated 9.5-hour interval was incorrect. Direct verification gives
**8 hours 28 minutes** between `d4fc321` and `d6cef79`
(`d4fc321` = 1785459869, `d6cef79` = 1785490366, via `git show -s --format=%ct`).
The 9.5-hour figure is the `92e3004 → d6cef79` span, a different pair; the two
were conflated.

That figure entered through the trigger-3 review archived at
`gates/redteam/trigger3-amendment4-2026-08-07.md` and was carried into a draft of
this section without being recomputed. It is recorded because it demonstrates a
rule this repository depends on:

> A reviewer's statement is evidence to verify, not a fact to copy without
> recomputation.

## Amendment 5 — 2026-08-07, revised 2026-08-13 — GNM / ViNT / NoMaD reproducibility study

Drafted 2026-08-07; substantially revised through trigger-3 adjudication and
committed 2026-08-13. Both dates are given because the crosswalk's provenance
claims were re-derived during the revision, not at drafting.

**Status: adjudicated under trigger-3.** The round-by-round verdict record,
including every defect found and the correction applied, is
`gates/redteam/trigger3-amendment5-2026-08-13.md`. No checkpoint could be loaded
and no inference run until trigger-3 returned an explicitly `committable`
verdict; a verdict of `Fixing` alone was never sufficient, and several rounds
returned `Fixing` with `committable: FALSE`.

**Trigger-3 classification: fixing.** The determination the standing-instructions
file requires of every amendment, stated here rather than deferred. This
amendment introduces no result-dependent change: it fixes no threshold, alters
no metric, changes no stopping rule and touches no population. It constrains what
may be claimed *before* any checkpoint is loaded — `runs/` does not exist and no
inference has run — declares the paper-reproduction column unclaimable in
advance, assigns `DELTA` or `RERUN` to eight of the twelve crosswalk rows while
confining `REUSE` to the three rows whose evidence is digest identity alone (the
twelfth is `UNDER RECONCILIATION`), and closes R8–R11 together with Success Rate,
Navigation Error and SPL. A rescuing amendment widens what may be claimed after
a result is seen; this one narrows what may be claimed before any result exists.

**Purpose.** Define, before any checkpoint is loaded or inference is run, exactly
what "reproduced" can and cannot mean for the three released VisualNav
Transformer models.

### Three independent claims

| Column | Meaning | Can become PASS from the current public release? |
|---|---|---|
| Released-artifact reproducibility | Released code, checkpoint, loader and inference can be instantiated and executed | Yes |
| Public-data training reproducibility | Released training code can train on the publicly released datasets under a frozen protocol | Yes, subject to execution |
| Exact paper reproduction | Original published result can be recreated from the complete original training/evaluation inputs | **Not claimable** unless unreleased inputs become available |

> These columns are independent. PASS in one column must never be used to infer
> PASS in another.

The third column is not blocked by any deficiency of this project. The official
release states that GNM, ViNT and NoMaD were trained on a mixture of publicly
available and **unreleased** datasets. Absent those inputs and sufficient
evaluation detail, exact paper reproduction is not independently reconstructable,
and this amendment declares that in advance rather than discovering it later.

> A failure to match the paper is still a successful reproducibility experiment
> if we can identify, preserve and demonstrate why the published result cannot
> be independently reconstructed.

### The ladder, frozen per model

```
R0  source frozen        R6  strict checkpoint load
R1  environment frozen   R7  deterministic inference
R2  data verified        R8  training mechanics
R3  preprocessing        R9  public-data training
R4  loader verified      R10 evaluation
R5  checkpoint verified  R11 paper comparison
```

GNM uses this ladder unmodified. ViNT and NoMaD carry preregistered
qualifications, both introduced because a pre-Amendment-5 audit located earlier
evidence that this amendment must not ignore.

> **NoMaD R7 — UNDER RECONCILIATION.** The current `navfm` implementation does
> not contain the diffusion sampling path required for NoMaD inference. However,
> the earlier `FAVL-AI/visualnav-transformer` reproduction lineage contains
> evidence that NoMaD inference executed using the official DDPM scheduler at 10
> steps and produced bitwise-identical outputs across three repeated runs under a
> frozen seed — **on synthetic seeded frames, not on GO Stanford**. The existing
> evidence must be assessed for adoption by reference or delta verification
> before any new implementation or execution is introduced.
>
> That input fact bounds the reconciliation before it starts. The DDPM execution,
> the three-repeat result, the checkpoint identity and the model configuration
> are adoptable by reference. The frozen GO Stanford input-batch digest is not,
> and no reconciliation can produce it, so this rung retains a real execution
> delta irrespective of how the reconciliation concludes.

The earlier wording of this clause declared NoMaD R7 simply BLOCKED, citing
`src/navfm/upstream.py:218`. That was too broad: the missing path is
repository-local to `navfm` and does not establish a model-level blocker.

> **ViNT historical-evidence disposition**
>
> The pre-Amendment-5 audit of the July `FAVL-AI/visualnav-transformer`
> reproduction lineage is complete. ViNT-specific evidence does not support
> inheritance of the family-level reproduction verdict. The following
> dispositions are therefore frozen before new execution:
>
> **ViNT R6 — DELTA.** Historical ViNT checkpoint-verification evidence records
> zero missing and zero unexpected keys, but `scripts/02_verify_checkpoints.py:168`
> performed the load with `strict=False`. Amendment 5 requires an explicitly
> strict state-dict load, so the historical result does not establish R6 under
> the current protocol.
>
> The historical record exists in two forms, and only one is durable. A tracked
> log, `reports/official_reproduction/logs/02_verify_checkpoints.log`, carries
> the result and survives a clean clone — but it enters the fork at **`0afa095`
> (2026-07-30)**, three days *after* `900c418`, and is covered by no
> reproduction tag. The machine-readable artefact
> `experiments/_evidence/checkpoint_verification.json` is **untracked** and does
> not survive a clean clone; its only self-dated provenance is
> `verified_utc 2026-07-30T10:10:16Z`, which likewise postdates `900c418`
> (2026-07-27T11:05:32+01:00). Its state as at `900c418` is unrecoverable by
> anyone, because it was never tracked and was overwritten on 2026-07-30. That
> is a permanent limit on this row, recorded rather than repaired.
>
> The earlier wording of this clause said the evidence "is not durable from a
> clean clone" without qualification. That overstated the case: it is true of
> the untracked JSON and false of the tracked log. Historical evidence shall be
> cited by reference **at the revision where it actually exists**; the missing
> delta is an explicit strict load plus a durable machine-readable record.

Two evidence classes must not be conflated:

```
experiments/_evidence/              IGNORED by git (.gitignore:87 at 900c418;
                                    .gitignore:92 at fork HEAD)
                                    checkpoint-verification evidence
experiments/validation/m1_family/   TRACKED at the audited July revision
                                    gnm_gate.json present
                                    nomad_gate.json present
                                    NO vint_gate.json
```
>
> **ViNT R7 — RERUN.** The machine-readable family gate directory is tracked. It
> contains GNM and NoMaD gate records but no ViNT gate record, and the gate
> implementation restricts supported models to GNM and NoMaD. No deterministic
> ViNT inference record containing a frozen input digest, seed protocol, output
> digest, repeat count and declared tolerance has been located. R7 therefore
> requires a new execution under Amendment 5.
>
> **ViNT R8 — DELTA.** Historical evidence demonstrates execution of the released
> ViNT training entry point on public GO Stanford data. The archived experiment
> was explicitly smoke-scaled: one epoch from random initialization, batch size
> 24 rather than the official batch size 256, with the recorded loss-identity
> comparison approximately `1.4594107256016287e-08`. The historical artefact
> explicitly states that this run is **not a reproduction of any published ViNT
> result**. Amendment 5 adopts that evidence only as proof of prior
> training-mechanics execution. It does not establish public-data training
> reproduction or paper-result reproduction. **No R8 execution is authorised by
> this amendment**, which defines no R8 criterion; see "R8 is NOT opened by this
> amendment" below.
>
> The July family-level reproduction tag shall not be used to transfer GNM or
> NoMaD verification to ViNT. Its own rule that no verdict is inherited between
> models remains controlling. The absence of ViNT R7 evidence is recorded as a
> defect in the historical gate apparatus, not as evidence that ViNT itself is
> non-reproducible and not as a deficiency of `navfm`.

### Frozen crosswalk — provenance-complete

Row provenance is of three kinds, and each row states which applies to it. The
**eight fork-sourced rows** (GNM R6/R7/R8, ViNT R6, ViNT R8, NoMaD R6/R7/R8) were
derived by re-opening the primary artefact in `/home/favl/robotics/FleetSafe-VLA`.
The **three R5 rows** were derived by re-opening `gates/G0/SHA256SUMS` and the
checkpoint files in **`navfm`**, which is where that evidence lives; no such path
has ever existed in the fork. **ViNT R7** rests on a verified absence in the fork
rather than on any artefact. No value is carried over from any summary. Fields
not independently establishable are written `NOT ESTABLISHED` and are never
inferred.

> No cross-repository evidence may affect an Amendment 5 disposition or
> execution-order decision unless the source repository, commit or tag, evidence
> path, checkpoint identity, dataset identity and original claim boundary are
> recorded in the frozen crosswalk. Historical execution is adopted by reference
> and shall never be re-described as execution performed in `navfm`.

Common to every row **whose source is the fork**: `source_repository` =
`FAVL-AI/visualnav-transformer` at `/home/favl/robotics/FleetSafe-VLA`;
`verification_source` = direct `git show <commit>:<path>` against that clone
during this correction pass.

Two classes of row do **not** take those defaults, and stating a blanket default
over them would misattribute a `navfm` artefact to the fork — the inverse of the
re-description this amendment forbids:

* **The three R5 rows.** Their `source_repository` is **`FAVL-AI/navfm`**, and
  their evidence path `gates/G0/SHA256SUMS` is tracked *here*, not in the fork.
  Their `verification_source` is `cd checkpoints && sha256sum -c SHA256SUMS`,
  not `git show`.
* **The ViNT R6 row's second artefact**, `experiments/_evidence/checkpoint_verification.json`.
  It is untracked, so `git show` cannot retrieve it at any commit; it was read
  from the fork's working tree, and that is the whole reason the row records its
  provenance as `NOT ESTABLISHED`.

| Model · Rung | Disposition | source_commit / tag | evidence_path (tracked?) | checkpoint_sha256 | **dataset identity** | **dataset / input digest** | historical claim / boundary | missing Amendment-5 delta |
|---|---|---|---|---|---|---|---|---|
| GNM R5 | REUSE | n/a — digest verified in `navfm` | `gates/G0/SHA256SUMS` (**tracked**, `navfm`); `checkpoints/SHA256SUMS` is an untracked working copy (**ignored**, `.gitignore:22`) with identical checkpoint lines | `4b03e0255f8a547290d4079f4e7d610ff69987122f17e019bd36684c08b3ee95` | n/a — identity only, no dataset read | n/a | identity only | none |
| GNM R6 | DELTA | `900c418` / `gnm-reproduction-v1.0.0` | `experiments/validation/m1_family/gnm_gate.json` (tracked) | as above | n/a — checkpoint load only | n/a | 0 missing / 0 unexpected recorded | strict load asserted; durable record under Amendment 5 |
| GNM R7 | DELTA | `900c418` / `gnm-reproduction-v1.0.0` | same gate file (tracked) | as above | **synthetic seeded frames — NOT GO Stanford.** `np.random.default_rng(SEED+i)`, `SEED = 0`, 480×640×3 `uint8`, through upstream `resize_and_aspect_crop` (`15_reproduction_gate.py:113–125`, called at `:152`,`:155`). The script's own docstring: *"Synthetic, and not benchmark data"* | 6 observation frames, first `1ed344aa3591f729…`; goal frame `987d033e0031b9c5…` | **`repeat_count: 1`** — a single run, **on synthetic input** | frozen **GO Stanford** input batch — **not satisfiable by reference**, because the historical input was synthetic; declared tolerance; **repeats ≥ 2**; input/output digests |
| GNM R8 | DELTA | `900c418` / `gnm-reproduction-v1.0.0` | `m1_family/gnm_entry_point.json` (tracked) | n/a | `go_stanford` (public, official processed format) | fork split registry; corpus digest **NOT ESTABLISHED** | `exit_code 0`, `epochs 1`, `batch_size 24`; boundary: *"execution evidence only … NOT a reproduction of any published GNM result and must never be cited as one"* | official-scale configuration (`batch_size: 400`, `epochs: 30` — GNM's official scale, **not** ViNT's 256/100); **R8 criterion NOT DEFINED in this amendment — R8 requires a further dated amendment** |
| ViNT R5 | REUSE | n/a — digest verified in `navfm` | `gates/G0/SHA256SUMS` (**tracked**, `navfm`); `checkpoints/SHA256SUMS` **ignored** as above | `155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f` | n/a — identity only, no dataset read | n/a | identity only | none |
| ViNT R6 | **DELTA** | **`0afa095`** (2026-07-30) for the tracked log — **not `900c418`**, where the path does not exist; **NOT ESTABLISHED** for the untracked artefact; no tag contains either | `reports/official_reproduction/logs/02_verify_checkpoints.log` (**tracked at `0afa095`; absent at `900c418`**); `experiments/_evidence/checkpoint_verification.json` (**untracked**; only self-dated provenance `verified_utc 2026-07-30T10:10:16Z`) | as above | n/a — checkpoint load only | n/a | 0 missing / 0 unexpected, but `strict=False` at `scripts/02_verify_checkpoints.py:168` | explicit strict load; durable machine-readable record |
| ViNT R7 | **RERUN** | **NOT ESTABLISHED** — no ViNT gate record in any revision | **NOT ESTABLISHED** | as above | **NOT ESTABLISHED** — no inference record exists | **NOT ESTABLISHED** | none located | entire rung |
| ViNT R8 | **DELTA** | **`ce9708e`** / **NOT ESTABLISHED — no tag contains it** | `m1_family/vint_entry_point.json` (tracked at `ce9708e`) | n/a | `go_stanford` (public, official processed format), **scene-entangled split, ≈34.5% padded targets** | split `{train: 2956, test: 740}`; corpus digest **NOT ESTABLISHED** | `exit_code 0`, `epochs 1`, `batch_size 24`, `initialisation "random (from-scratch smoke, not the official checkpoint)"`; boundary quoted below | official-scale configuration (`batch_size: 256`, `epochs: 100`); **R8 criterion NOT DEFINED in this amendment — R8 requires a further dated amendment** |
| NoMaD R5 | REUSE | n/a — digest verified in `navfm` | `gates/G0/SHA256SUMS` (**tracked**, `navfm`); `checkpoints/SHA256SUMS` **ignored** as above | `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333` | n/a — identity only, no dataset read | n/a | identity only | none |
| NoMaD R6 | DELTA | `900c418` / `nomad-reproduction-v1.0.0` for the gate file; **`0afa095`** for the tensor count | `m1_family/nomad_gate.json` (tracked) — records `parameters: 19049675`, `missing_keys: []`, `unexpected_keys: []` and **no tensor-count field**; the 645/645 figure is in `0afa095:reports/official_reproduction/logs/02_verify_checkpoints.log` (tracked) and in the untracked JSON | as above | n/a — checkpoint load only | n/a | 0 missing / 0 unexpected recorded; tensor count sourced separately as above | strict load asserted; durable record |
| NoMaD R7 | **UNDER RECONCILIATION** | `900c418` / `nomad-reproduction-v1.0.0` | `m1_family/nomad_gate.json` (tracked) | as above | **synthetic seeded frames — NOT GO Stanford.** Same `official_frame` path as GNM R7 (`:113–125`, called at `:193`,`:196`) | 4 observation frames, first `1ed344aa3591f729…`; goal frame `987d033e0031b9c5…` | `repeat_count: 3`, DDPM at 10 steps, bitwise identical across repeats — **on synthetic input** | frozen **GO Stanford** input batch — **not satisfiable by reference**, so a real execution delta always remains; tolerance record. **No port by default** |
| NoMaD R8 | DELTA | `900c418` / `nomad-reproduction-v1.0.0` | `m1_family/nomad_entry_point.json` (tracked) | n/a | `go_stanford` (public, official processed format) | fork split registry; corpus digest **NOT ESTABLISHED** | `exit_code 0`, `epochs 1`, `batch_size 16`; boundary: *"execution evidence only … NOT a reproduction of any published NoMaD result and must never be cited as one"* | official-scale configuration (`batch_size: 256`, `epochs: 100`); **R8 criterion NOT DEFINED in this amendment — R8 requires a further dated amendment** |

**ViNT R8 claim boundary, quoted verbatim and not paraphrased**
(`ce9708e:experiments/validation/m1_family/vint_entry_point.json`):

> *"execution evidence only. One smoke-scaled epoch from random init on a
> scene-entangled split with ~34.5% padded targets. NOT a reproduction of any
> published ViNT result, and NOT comparable to GNM's or NoMaD's numbers:
> different optimiser, schedule, capacity and objective scaling."*

Its final clause is binding: this row **may not be used for cross-model
comparison**.

**Four provenance facts that symmetry would have got wrong.** `900c418` carries
`gnm_entry_point.json`, `gnm_gate.json`, `nomad_entry_point.json` and
`nomad_gate.json` — and **no ViNT file of either kind**. `vint_entry_point.json`
is **introduced by** exactly one commit, `ce9708e`, ≈86 minutes after the tagged
commit, and is contained in the tree of no tag. (It persists in 98 commits
through the fork tip; the load-bearing fact is that no tag reaches it, not that
it appears only once. An earlier wording said "exists at exactly one commit",
which is false and is corrected here rather than in place.) **GNM R7 rests
on `repeat_count: 1`**, so it carries no repeatability evidence, unlike
NoMaD's 3.

**And the fourth, which changes the execution order: the historical GNM R7 and
NoMaD R7 inference did not run on GO Stanford at all.** Both drew their input
from `official_frame` (`900c418:scripts/15_reproduction_gate.py:113–125`), which
generates a synthetic frame from `np.random.default_rng(SEED + i)` at `SEED = 0`
and pushes it through upstream's own `resize_and_aspect_crop`. The function's
docstring states the boundary itself: *"Synthetic, and not benchmark data: it
exists to exercise the official contract, and is regenerable from the seed."*

The tag annotations preserve the same distinction, and an earlier reading of
this crosswalk lost it: `gnm-reproduction-v1.0.0` says *"**smoke inference**
through the official forward path returns `dist [1,1]` and `action [1,5,4]`"*
without naming a dataset, and separately that *"official `train.py` executes on
public GO Stanford data"* — which is R8, not R7.

The consequence is not cosmetic. Amendment 5's R7 criterion requires a frozen
**GO Stanford** input-batch digest. No quantity of synthetic-input evidence can
supply it, however many repeats it carries. **NoMaD R7 therefore always retains
a real execution delta and can never be closed by reference alone**, and GNM R7's
gap is not only repeatability but the input population. Both corrections are
carried into the execution order below.

### Historical defect recorded, not repaired

> **Historical ViNT R7 gate defect.** Independent verification of the July
> `FAVL-AI/visualnav-transformer` lineage establishes that no `vint_gate.json`
> exists in the audited revisions and that `scripts/15_reproduction_gate.py`
> restricts the machine-readable reproduction gate to GNM and NoMaD. The
> family-level reproduction claim therefore has no machine-readable ViNT R7 gate
> record in the audited lineage. No claim is made that `TRACEABILITY.md`
> referenced a ViNT gate artefact; it did not. This discrepancy is preserved as a
> limitation of the historical family-level R7 claim and is not retroactively
> repaired.

### R5 evidence, frozen here

Verified by `sha256sum -c`, run from `checkpoints/` because both digest files use
`./`-relative paths and `gates/G0/SHA256SUMS` additionally lists
`./go_stanford.zip`, which does not resolve there:

```
cd checkpoints && sha256sum -c SHA256SUMS
```

`gates/G0/SHA256SUMS` is **tracked** in `navfm` and is the durable record; the
working copy at `checkpoints/SHA256SUMS` carries identical checkpoint lines but
is **ignored** (`.gitignore:22`) and survives no clean clone, so it must not be
cited as the durable record. The three checkpoint digests are:

| Checkpoint | Bytes | SHA-256 | R5 |
|---|---|---|---|
| `gnm.pth` | 104,806,886 | `4b03e0255f8a547290d4079f4e7d610ff69987122f17e019bd36684c08b3ee95` | verified |
| `nomad.pth` | 76,473,631 | `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333` | verified |
| `vint.pth` | 430,167,114 | `155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f` | verified |

**These establish R5, not R6.** A checkpoint whose digest matches has been
identified, not loaded.

### What this amendment authorises loading `vint.pth` for: R6 only

> The previous prohibition
> (`docs/reviews/2026-07-31-g0c-amendment-specification.md:304`) barred loading
> `vint.pth` **for evaluation** until the G0.c protocol was frozen. The G0.c
> population and protocol are frozen at `eee5a66` with freeze audit 16/16.
>
> **G0.c itself has not executed and no G0.c metric exists.** The freeze audit
> concludes "the protocol is frozen and G0.c *may execute*", and two of its own
> sixteen checks — `no_existing_g0c_result_directory` and
> `no_pre_audit_evaluator_output` — pass precisely because no result is present.
> `runs/` does not exist. Committed Amendment 3 states the same evidential state.
>
> The R6 strict load preregistered here is a **different experiment from G0.c
> evaluation**: it loads weights into an architecture and produces no G0.c
> metric, no dataset pass and no classification under the G0.c decision rule.
> Checkpoint loading **for R6** is therefore permitted once this amendment is
> adjudicated and frozen. The prohibition on loading `vint.pth` *for G0.c
> evaluation* is retired by the freeze, and G0.c executes under its own frozen
> protocol, not under this clause.

An earlier wording of this clause read "G0.c is now closed at `eee5a66`". That
was false — `eee5a66` froze G0.c's population and protocol, as its own commit
subject records ("Freeze the G0.c evaluation population"), and closure of a gate
defined by `docs/WORKFLOW.md:82` as *evaluating* the checkpoint requires an
evaluation that has never run. The error is recorded rather than silently
replaced, because it was the sole stated basis for retiring a loading
prohibition, and a gate retired on a false premise is not a gate.

### Evaluation population

```
GO Stanford frozen pair population : 41,872
manifest digest                    : 57a7fbbeba91b92a
```

This population shall not be regenerated or opportunistically changed after
inference outputs have been seen.

### Repeatability criterion, frozen before the first inference

> For **GNM, ViNT and NoMaD**, repeated inference shall use identical model
> checkpoint, model configuration, frozen input batch, device, preprocessing,
> seed and evaluation mode. The primary comparison is element-wise float32 output
> equivalence using `torch.allclose(rtol=1e-5, atol=1e-6)`. Maximum absolute
> difference and maximum relative difference shall also be archived. Any failure
> is reported as a repeatability failure and the tolerance shall not be widened
> after results are observed.

An earlier wording scoped this criterion to GNM and ViNT alone, while step 5
below **mandates** a NoMaD R7 execution and requires it to produce a tolerance
record. That instruction had no referent: the amendment ordered a run and
declared no rule for accepting it, leaving the tolerance to be chosen after the
outputs were seen — which is exactly what the no-rescue clause forbids. NoMaD is
therefore brought under the same declared tolerance as the other two, before its
first inference.

> **NoMaD, additionally.** The historical NoMaD record is *bitwise* identical
> across three repeats under a frozen seed, on synthetic input. Bitwise identity
> is stricter than `allclose` and shall be **reported** for the new GO Stanford
> run if achieved. It is **not** the acceptance threshold: the declared tolerance
> above governs, uniformly across all three models. Adopting the stricter
> historical property as a threshold would set an acceptance rule on hardware and
> an input population the historical run never used.

Held identical across repeats: input digest, preprocessing digest, checkpoint
digest, seed, `model.eval()`, `torch.no_grad()`, device, software environment.

If CUDA deterministic algorithms can be enabled without breaking the upstream
implementation, they shall be enabled and recorded. If upstream execution cannot
satisfy deterministic-algorithm enforcement, **that fact shall be recorded**
rather than the check being silently disabled.

**This tolerance governs repeatability only and must never be applied to
paper-level agreement.** They are different questions: repeatability is same
implementation, same machine, same input; paper reproduction is agreement with
published experimental results. The paper comparison requires its own
metric-specific rule, fixed once the published target metrics and evaluation
protocol have been identified, in a later amendment.

### Cross-repository evidence

> Historical evidence from another repository may satisfy or partially satisfy a
> reproduction rung only when its repository, commit or tag, model checkpoint
> digest, dataset identity, implementation lineage and execution record are
> explicitly cited. Such evidence must be adopted by reference and must not be
> silently copied or re-described as execution performed in `navfm`. Where the
> historical evidence does not satisfy every requirement of the current rung,
> only the missing delta shall be executed.

Corollary, so the rule cannot be read as an invitation to duplicate: existing
evidence shall not be discarded or repeated solely because this protocol was
introduced later.

FleetSafe material is excluded by the standing repository boundary and may not
be adopted under this clause — specifically the fork's `hospital-v1.0.0` corpus,
which counts toward no `navfm` rung.

### No-rescue clause

> No project-collected pilot data, synthetic replacement data, altered split,
> modified metric, changed stopping rule, additional training corpus or
> post-result tolerance adjustment may be introduced to make a failed
> reproduction appear successful. Any such change requires a new dated amendment
> before execution.

### Permitted execution after adjudication

Only the following, in order, and not training:

> **Post-adjudication execution order — derived from the provenance-complete
> crosswalk**
>
> This order may execute only work classified `DELTA`, `RERUN`, or the missing
> delta of an `UNDER RECONCILIATION` row once that reconciliation has identified
> it (NoMaD R7, steps 4-5). `REUSE` evidence is adopted by reference and must not be rerun
> merely for symmetry. `UNDER RECONCILIATION` evidence must be resolved before
> new implementation is introduced.

1. **Close R6 strict-load deltas first.** For each model whose R6 row is
   `DELTA`, instantiate the frozen architecture and perform an explicit strict
   checkpoint load, producing a durable machine-readable record containing
   checkpoint digest, parameter/tensor counts, missing keys and unexpected keys.
   Models whose R6 row is `REUSE` are not rerun.
2. **GNM R7 — execute the two missing deltas, which are input population and
   repeatability.** Historical GNM R7 evidence contains `repeat_count = 1`, so it
   establishes no repeatability. It also ran on **synthetic seeded frames rather
   than GO Stanford**, so it establishes no frozen-input-population evidence
   either. Both gaps are real and neither substitutes for the other: two repeats
   on synthetic input would still leave R7 open. Run the frozen Amendment-5
   **GO Stanford** input through the already-established GNM path for at least two
   repeats under the declared seed/device/preprocessing protocol. Record input
   digest, output digest, output shapes, finite-value checks,
   `torch.allclose(rtol=1e-5, atol=1e-6)`, maximum absolute difference and
   maximum relative difference. Do not repeat unrelated historical GNM gate work.
3. **ViNT R7 — perform the new deterministic-inference run.** This is a
   legitimate `RERUN`/new execution because no qualifying historical
   deterministic-inference record exists. Produce the full Amendment-5
   machine-readable R7 record from the frozen GO Stanford input population. The
   historical prose output shapes may be cited as context only and must not
   satisfy any R7 field.
4. **NoMaD R7 — reconcile historical evidence before executing anything new.**
   Re-read the cited historical DDPM evidence and compare it field-by-field with
   the frozen Amendment-5 R7 criterion. Preserve its historical ten-step DDPM
   execution and three-repeat result by reference. Classify each current
   requirement as already satisfied or missing. Do not port or rebuild the NoMaD
   sampling implementation merely to make `navfm` symmetrical.
5. **NoMaD R7 — execute the demonstrated missing delta, which is known in advance
   to be non-empty.** The historical NoMaD R7 record ran on **synthetic seeded
   frames, not GO Stanford**, so it cannot supply the frozen GO Stanford
   input-batch digest the Amendment-5 R7 criterion requires. **This step
   therefore cannot terminate at zero new inference**, and the reconciliation in
   step 4 must not be read as offering that exit — an earlier wording of this
   step did, and that was the defect. What reconciliation *does* establish is how
   much is already carried by reference: the ten-step DDPM execution, the
   three-repeat bitwise-identical result, the checkpoint identity and the model
   configuration are adopted and must not be re-run to prove them again. The
   delta to execute is the frozen GO Stanford input population, its digest, the
   declared tolerance record and the environment field — **at least two repeats**,
   as for GNM, since the adopted three-repeat result is on synthetic input and
   evidences nothing about this population — and nothing else. Any
   code transfer requires a separate justified change rather than being smuggled
   into this step.
6. **Archive and reconcile the resulting evidence before advancing the ladder.**
   For every executed delta, archive the exact `navfm` commit, checkpoint
   SHA-256, dataset/manifest identity, input/config digest, environment,
   machine-readable result and W&B run/artifact where applicable. Update the
   evidence crosswalk with the new record while preserving the distinction
   between historical cross-repository execution and new `navfm` execution. Do
   not proceed to R8 training mechanics, R9 public-data training, R10 evaluation,
   R11 paper comparison, SR, Navigation Error or SPL under this execution order.

### R8 is NOT opened by this amendment

An earlier draft of the execution order carried three R8 steps while its own
preamble read "and not training". Those steps are withdrawn, and the reason is
recorded rather than the contradiction merely resolved.

Two facts decided it. First, the crosswalk gives every R8 missing delta as
**official-scale configuration**, and official scale is **per model, not
uniform** — a distinction an earlier wording of this section lost by
generalising ViNT's figures across all three:

| Model | Official scale | Historical record | Source |
|---|---|---|---|
| GNM | `batch_size: 400`, `epochs: 30` | batch 24, 1 epoch | `train/config/gnm.yaml:9,11` @ `dca7981` |
| ViNT | `batch_size: 256`, `epochs: 100` | batch 24, 1 epoch | `train/config/vint.yaml:7–8` @ `dca7981` |
| NoMaD | `batch_size: 256`, `epochs: 100` | **batch 16**, 1 epoch | `train/config/nomad.yaml:7–8` @ `dca7981` |

The upstream clone is not tracked in `navfm`, so the pinned commit `dca7981` is
given rather than the path alone. Each model's figures are independently
corroborated by a **tracked** artefact in the fork — one per model, because a
single config corroborates only its own model:

| Model | Tracked corroborator | What it records |
|---|---|---|
| GNM | `900c418:experiments/configs/gnm_gostanford_smoke.yaml:14,16` | `batch_size: 24  # [SMOKE] official: 400`; `epochs: 1  # [SMOKE] official: 30` |
| NoMaD | `900c418:experiments/configs/nomad_gostanford_smoke.yaml:15,17` | `batch_size: 16  # [SMOKE] official: 256`; `epochs: 1  # [SMOKE] official: 100` |
| ViNT | `ce9708e:experiments/configs/vint_gostanford_smoke.yaml:9` | *"Official: batch 256, 100 epochs, 12 workers, 4 warmup epochs."* |

An earlier wording of this passage cited the GNM config alone as corroborating
"the figures", which are six values across three models. It corroborates two.
The other two configs were located and are cited above rather than the claim
being narrowed, because the corroboration genuinely exists.

Every one of those deltas requires a full training run to close — the most costly
and least reversible action in this programme — and that conclusion holds under
each model's own figures, not only under the generalisation that was wrong.

Second, **Amendment 5 does not define an R8 criterion.** The
crosswalk cells and the withdrawn steps both referred to "the frozen R8
criterion"; no such criterion is stated anywhere in this amendment. An execution
step measured against an undefined criterion is not a preregistered experiment.

> R8 training mechanics require a **further dated amendment** that first states
> the R8 criterion — configuration, scale, split identity, seed protocol, record
> fields and claim boundary — and is itself adjudicated under trigger-3. No R8
> execution is authorised until then. The historical R8 evidence in the crosswalk
> remains adopted by reference for what it is: prior training-mechanics
> execution, explicitly not a reproduction of any published result, and in ViNT's
> case explicitly not comparable to GNM's or NoMaD's numbers.

This narrows the amendment. It is recorded here because withdrawing an
authorisation is a protocol change in its own right, and a reader comparing
drafts must be able to see that the change was made deliberately and why.

> The order above is dependency-driven rather than model-symmetric. A model with
> stronger historical evidence may require less new execution than another
> model. Missing evidence must not be manufactured by repeating unrelated work,
> and existing evidence must not be discarded solely because it predates
> Amendment 5.

> GNM's historical `repeat_count = 1` shall not be described as
> deterministic-repeatability evidence. It establishes a historical inference
> execution only; repeatability is an Amendment-5 delta.

```
R5     GNM REUSE · ViNT REUSE · NoMaD REUSE
  |
R6     strict-load DELTAs only
  |
R7     GNM input-population + repeatability DELTA
       ViNT full deterministic RERUN
       NoMaD reconciliation by reference; GO Stanford input delta MANDATORY
  |
archive + provenance reconciliation
  |
STOP        R8 is NOT opened by this execution order (requires a further
            amendment defining the R8 criterion); nor are R9-R11
```

ViNT R7 is a legitimate new run, not a repeat: no prior record exists. The
historical prose statement of ViNT output shapes may be cited as supporting
context but shall not be treated as R7 evidence. The new run must produce the
machine-readable record:

```
checkpoint digest          raw output shapes
model/config digest        finite-output checks
frozen GO Stanford         output digest
  input-batch digest       repeat count
seed                       torch.allclose(rtol=1e-5, atol=1e-6)
device/software env        max absolute difference
model.eval()               max relative difference
strictly defined preprocessing
```

Each checkpoint-loading record shall answer: architecture instantiated? strict
`state_dict` load? missing keys = 0? unexpected keys = 0? all tensors finite?
`model.eval()`? frozen official input accepted? forward pass completed? output
shape correct? repeatability criterion satisfied?

Training mechanics (R8) are not opened by this amendment. They require a
further dated amendment that first states the R8 criterion, adjudicated under
trigger-3, and may in no case begin before R6–R7 are closed.

### SR / NE / SPL remain BLOCKED

Success Rate, Navigation Error and SPL are closed-loop navigation quantities and
shall not be computed from static training trajectories. They remain BLOCKED
until a later frozen evaluation protocol supplies their required inputs: a
defined episode set with start and goal poses, a stopping criterion, final poses
in a verified metric coordinate system, and for SPL the shortest feasible path
length alongside the executed path length.

## Amendment 6 — 2026-09-17 — navigation arm pose, frozen before any pose exists

Pre-results, and deliberately pre-*values*: no candidate joint vector has been
commanded, no candidate camera imagery has been viewed, and the physical arm has
not been moved. What is frozen here is the rule for choosing the pose, not the
pose.

### Why this needs preregistering at all

The ROSMASTER M3 Pro carries its depth camera on the 6-DOF manipulator rather
than on the chassis. The transform from `base_link` to the camera is therefore
not a constant of the apparatus but a function of the arm configuration, and
camera height and pitch are what determine where floor, horizon and obstacles
fall in frame. For image-goal navigation that makes the arm pose part of the
sensing instrument.

A pose chosen after seeing which one produced better navigation would be an
experimental condition selected on the outcome. The protection is ordering:
the pose is fixed from mechanical criteria, and only then is anything rendered
through it.

### Selection hierarchy

**Priority 1.** If the authoritative Yahboom source defines a documented
forward-facing camera or navigation pose appropriate to the installed
configuration, that pose is used and its provenance recorded.

**Priority 2.** Otherwise one fixed pose is selected against these criteria and
no others:

- camera nominally forward;
- central field of view not materially occluded by arm or gripper;
- all joints inside their limits with margin;
- statically stable, no self-collision, no cable strain;
- arm does not materially enlarge the navigation footprint;
- camera elevated enough for usable forward perception, and not dominated by
  floor or ceiling;
- reproducible from reset or home.

### Forbidden selection evidence

GNM, ViNT or NoMaD performance; navigation success or route completion; model
confidence; stopping behaviour; image similarity; any downstream task score; or
choosing whichever camera image looks best. Camera height and pitch may not be
tuned after observing Arm-A behaviour.

### Per-joint tolerance

No numerical tolerance is frozen here, because none has been measured. A guessed
±1° or ±2° would be a threshold invented to be passed.

The tolerance is derived from at least ten independent reset-and-return cycles,
recording all six joint readbacks each time, from which per-joint mean, standard
deviation, min, max and maximum absolute deviation from the reference are
computed. The rule converting that repeatability and the joint-state resolution
into a tolerance is fixed before any navigation episode runs.

### Episode admission

Before any production PRE capture, every joint is compared against the frozen
navigation vector. Any joint outside its frozen tolerance refuses the episode
rather than recording one under unknown camera geometry. Arm motion during
navigation is prohibited; movement beyond tolerance during an episode
invalidates the camera apparatus condition for that episode.

### Camera transform model

`T_base_camera(q) = T_base_arm x FK(q1..q6) x T_mount_camera`

`T_base_arm` and the kinematic chain come from the authoritative description;
`q1..q6` is the frozen navigation pose; `T_mount_camera` is the fixed physical
calibration from the mounting link or bracket to the camera datum. Only the last
of these is a physical measurement, and it is not a chassis-to-camera number.

The camera housing datum, the RGB optical frame identity, and the housing to
optical correction are recorded separately. Where the optical correction is not
supported by a datasheet or calibration it is recorded NOT_MEASURED, never
substituted with zero.

### Status at the time of freezing

    NAVIGATION_ARM_CONFIGURATION = SELECTION_PROTOCOL_FROZEN / VALUES_NOT_ESTABLISHED
    PER_JOINT_TOLERANCE          = PENDING_REPEATABILITY_MEASUREMENT
    PHYSICAL_CAMERA_EXTRINSIC    = NOT_MEASURED
    ARM_MOTION_DURING_NAVIGATION = PROHIBITED
