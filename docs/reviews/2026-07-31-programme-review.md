Source: external methodological review
Date received: 2026-07-31
Scope: M1 completion and G0.c readiness
Status: reviewed and dispositioned

---

This is a strong M1 completion state. The implementation has crossed from “scaffold” into a reproducible experimental substrate, but it has not yet crossed into scientific evidence. That distinction is being handled correctly.
My assessment is that M1 should be considered **technically complete, methodologically credible, and scientifically non-evidentiary** until G0.c.
The most important achievement is not the increase from 129 to 204 tests. It is that the repository now has executable oracles linking training, evaluation, tables, and gate reproduction to shared reference semantics rather than duplicated logic.
## Executive judgement
| Dimension                   | Assessment                                     |
| --------------------------- | ---------------------------------------------- |
| M1 engineering completeness | Green                                          |
| Reproducibility chain       | Green, subject to fresh-clone confirmation     |
| Upstream fidelity           | Green: pinned and unpatched                    |
| Metric integrity            | Improved materially                            |
| Resume semantics            | Correctly hardened                             |
| Audit maturity              | Strong                                         |
| Scientific-result readiness | Not yet green                                  |
| Immediate decision gate     | G0.c                                           |
| Red-team omission           | Defensible, but must remain explicitly bounded |
The result is suitable to freeze as an M1 milestone provided the archived gate contains exact environment identity, command invocation, source hashes, and expected output signatures.
## What is genuinely strong
### 1. One reproducible chain now exists
The chain appears to be:
```text
training
  ↓
checkpoint/state
  ↓
offline.py evaluator
  ↓
runs/
  ↓
scripts/make_tables.py
  ↓
paper/tables/*.md
  ↓
gates/M1/reproduce.sh
  ↓
archived evidence
```
That is exactly the right architecture for the thesis programme. The paper tables are no longer manually curated outputs. They are terminal artefacts of an executable evidence chain.
The hard failure on missing seeds is particularly important. Missing seeds must never degrade into partial aggregation with silently narrower uncertainty.
### 2. The evaluator is resumable
Resumability matters beyond convenience. It supports:
* recovery from interrupted evaluation;
* explicit identification of completed episode-seed combinations;
* avoidance of duplicate observations;
* traceability of partial runs;
* deterministic continuation.
The implementation should ensure that “resume” means resume against the same experimental identity, not merely append to an existing directory. At minimum, it should reject differences in:
* checkpoint hash;
* dataset or manifest hash;
* configuration;
* evaluator version;
* seed set;
* batch size;
* model architecture;
* metric implementation version.
If those checks already exist, they should be documented as an evaluator invariant.
### 3. The oracle strategy is stronger than a generic red-team review at this stage
Your decision not to conduct red-team review is defensible because the primary risk was semantic duplication, and you removed that risk through executable reference coupling.
The strongest design choice is:
> `train/run.py` calls `train_utils._compute_losses` rather than reimplementing the objective.
That directly prevents training-wrapper drift.
The metric tests comparing against the same reference implementation across:
* four mask rates;
* two alpha values;
are also methodologically appropriate. They test semantic equivalence across variations that could expose masking and weighting errors.
However, this does not permanently eliminate the need for adversarial review. It only justifies postponing it. An oracle can confirm consistency with upstream while upstream itself may still be conceptually wrong. That distinction should remain explicit:
* **conformance oracle:** does the implementation match the reference?
* **validity review:** is the reference computation scientifically meaningful?
M1 primarily establishes the first.
## F12 is a legitimate audit finding
The finding that:
* `action_orien_cos_sim`
* `multi_action_orien_cos_sim`
collapse to the same numerical value under the current representation is meaningful.
The explanation is mathematically sound under the stated conditions.
For timestep heading vectors (p_t) and (y_t), if both are unit norm, then:
[
\frac{\sum_{t=1}^{T} p_t^\top y_t}
{\sqrt{\sum_{t=1}^{T}|p_t|^2}
\sqrt{\sum_{t=1}^{T}|y_t|^2}}
=============================
# \frac{\sum_{t=1}^{T} p_t^\top y_t}{T}
\frac{1}{T}\sum_{t=1}^{T}\cos(p_t,y_t)
]
because:
[
\sum_{t=1}^{T}|p_t|^2=T,\qquad
\sum_{t=1}^{T}|y_t|^2=T.
]
Therefore the flattened cosine similarity and mean per-action cosine similarity are algebraically identical for normalized heading vectors.
Your qualification that this is not necessarily true for the (x,y) displacement pair is important. Displacement vectors need not be independently unit normalized at each timestep, so the denominator does not simplify in the same way.
### How F12 should be classified
F12 should not be presented primarily as a software bug. It is better classified as:
> **Metric redundancy caused by representational invariance.**
Its consequences are:
* two reported metric names may imply distinct evidence while encoding the same statistic;
* tables may overstate the dimensionality of evaluation;
* multiple-metric comparisons may double-count identical evidence;
* readers may infer timestep-level and sequence-level distinctions that do not exist.
A concise formal statement in the paper would be:
> Under the upstream heading representation, both metrics are provably identical because predicted and target heading vectors are unit normalized per action. Consequently, they do not constitute independent evaluation measures.
This finding is stronger because it was discovered through executable comparison and then explained algebraically.
## The scheduler-resume defect is material
The cosine-annealing resume issue is a real experimental-validity defect, not a usability defect.
The observed behaviour:
> increasing `--epochs` on resume retains the old `T_max`, causing a resumed epoch to train at learning rate zero.
This could create several invalid interpretations:
* the user believes training was extended when parameters did not materially update;
* checkpoint names imply a longer training horizon than the optimization actually performed;
* comparative runs may differ in scheduler history rather than intended treatment;
* later epochs may be reported despite having effectively no learning rate.
Refusing the run is the correct default. It is much safer than silently recomputing scheduler state.
The two remedies should be treated as distinct experimental interventions:
1. Resume with the original scheduler horizon.
2. Explicitly restart or redefine the scheduler with a documented new horizon.
The second remedy changes the optimization protocol and must produce a new experiment identity. It should not overwrite or continue the original run lineage as though nothing changed.
## The random-initialization labelling is excellent
The controls around synthetic-noise outputs are exactly right:
* `"random_init": true`;
* visible banner;
* “RANDOM INIT — not a result” table marking;
* explicit statement that G0.c produces the first real number.
This protects against a common repository failure mode where smoke-test numbers are later copied into drafts, presentations, or comparison tables without their provenance.
I would strengthen this further with a machine-readable result class:
```json
{
  "evidence_class": "pipeline_smoke_test",
  "scientific_result": false,
  "model_initialization": "random",
  "data_source": "synthetic_noise"
}
```
Then `make_tables.py` can refuse to place such outputs into any table marked as a scientific results table.
## What still needs verification before freezing M1
There are five remaining checks I would require.
### Fresh-clone reproducibility
Run the M1 reproduction from a new clone or clean worktree with only documented prerequisites.
Acceptance criterion:
* no untracked local source dependency;
* no hidden environment variable;
* no reliance on previously generated runs;
* identical manifest structure;
* numerically identical deterministic outputs where expected;
* documented tolerance where exact equality is not expected.
### Archive completeness
`gates/M1/` should contain or point immutably to:
* repository commit;
* upstream commit `dca7981`;
* Python version;
* dependency lock or resolved package list;
* operating system;
* CPU architecture;
* full commands;
* stdout and stderr;
* exit statuses;
* hashes of generated artefacts;
* test summary;
* mypy and ruff outputs;
* seed manifest.
### Resume identity protection
The evaluator should refuse resumption when the prior-run manifest differs from the requested evaluation identity.
A resumable evaluator without identity checks can produce mixed experimental populations.
### Table lineage
Every table row should retain enough metadata to trace back to:
* individual run directories;
* checkpoint hash;
* seed;
* configuration;
* evaluator version;
* raw metric artefact.
Markdown alone is not sufficient. A machine-readable table source such as JSON, JSONL, Parquet, or CSV should be retained beside the rendered Markdown.
### Random-init contamination barrier
Add a test that confirms production/paper result generation rejects `random_init=true` unless an explicit smoke-test mode is enabled.
## Red-team review: the correct decision boundary
I agree with postponing it for M1, but I would not record the decision as simply “red-team review was unnecessary.”
A more precise record is:
> Red-team review triggers 1–2 were satisfied by constructing executable conformance oracles that directly test the relevant semantic risks. Independent adversarial validity review remains pending and is required before scientific claims are derived from G0.c or later experimental outputs.
That wording avoids conflating semantic conformance with scientific correctness.
Red-team review becomes mandatory at these points:
* before accepting G0.c as a baseline result;
* before freezing the 2×2 protocol;
* before running costly physical episodes;
* before submission;
* whenever a finding depends on the absence of an effect;
* whenever exclusions, failed episodes, or resumed runs affect the sample.
## Recommended status classification
I would record M1 as:
```text
M1 STATUS: TECHNICALLY COMPLETE
Scope established:
- end-to-end CPU execution;
- reference-coupled training loss;
- offline evaluation;
- resumable execution;
- strict seed-complete table generation;
- reproducible gate script;
- upstream fidelity tests;
- audit finding F12;
- scheduler-resume protection.
Not established:
- baseline reproduction;
- scientific performance;
- transfer validity;
- external reproducibility;
- adversarial validity review.
Next evidence gate:
- G0.c.
```
## Immediate next action
The next work should remain narrowly focused on G0.c. Do not expand Paper 3, safety arbitration, dataset collection, or the broader roadmap until the baseline reproduction gate is resolved.
G0.c should answer five questions:
1. What exact checkpoint, dataset split, preprocessing path, and evaluator define the reference baseline?
2. Can the number be reproduced under the pinned upstream state?
3. What tolerance defines reproduction success?
4. Which implementation variables materially affect the number?
5. Does the result remain stable across the pre-registered seed and batch-size protocol?
The gate should return one of three outcomes:
| Outcome                          | Meaning                                                           |
| -------------------------------- | ----------------------------------------------------------------- |
| Reproduced                       | Reference performance falls within pre-registered tolerance       |
| Reconstructed but not reproduced | Pipeline is valid, but reported/reference number is not recovered |
| Not reconstructable              | Missing specification prevents a defensible comparison            |
The third outcome is not an engineering failure. It may become one of the programme’s strongest empirical findings if documented rigorously.
## Final conclusion
M1 appears to have achieved its proper objective:
> establish that the repository can execute, measure, resume, aggregate, and regenerate evidence without silently changing the upstream training semantics.
F12 and the scheduler defect are exactly the type of findings the thesis framing predicts: problems that are invisible when results are treated as table entries but become discoverable when the evidence pipeline is made executable and inspectable.
The decisive next step is G0.c. Until that gate is green—or fails in a scientifically interpretable manner—the repository has a validated instrument, not yet a navigation result.

Your judgments are correct, and the programme is now operating according to its stated epistemic design. I would adopt the proposed session order without changing the substance.
One wording correction is important:
> **G0.c cannot produce an adverse scientific outcome; it can still fail operationally or procedurally.**
That distinction should be explicit. A corrupted dataset, incomplete checkpoint, evaluator crash, post-hoc protocol change, or pre-registration committed after execution would constitute a failed gate execution. By contrast, a validly executed gate must terminate in one of the three evidential classifications:
1. **Reproduced**
2. **Reconstructed but not reproduced**
3. **Not reconstructable**
This protects the project from converting every technical failure into an ostensibly meaningful scientific result.
## The G0.c reference problem
Your rejection of a percentage tolerance against `avg_total_test_loss = 0.17398` is exactly right. That number is not a valid reproduction target for the proposed evaluation because the estimands differ:
| Checkpoint record                        | G0.c evaluation                  |
| ---------------------------------------- | -------------------------------- |
| Full five-dataset mixture                | GO Stanford holdout only         |
| Upstream training/evaluation composition | Locally reconstructed split      |
| Unrecoverable upstream splits            | Explicitly versioned new split   |
| Aggregate total test loss                | Dataset-specific offline metrics |
| Potentially different sample weighting   | Declared batch-400 protocol      |
A numerical tolerance around `0.17398` would create false precision while comparing non-equivalent quantities. It would weaken, rather than strengthen, the pre-registration.
The G0.c amendment should therefore define `0.17398` as a **historical checkpoint-associated reference**, not a reproducible ground-truth target.
A precise formulation would be:
> The checkpoint metadata value `avg_total_test_loss = 0.17398` is retained as a provenance anchor but is not treated as a direct reproduction target because its five-dataset evaluation composition and original split identities cannot be reconstructed. G0.c evaluates a declared GO Stanford holdout and therefore tests internal consistency, behavioural sanity, and the documented relationship between the reconstructed evaluation and the checkpoint-associated aggregate—not numerical equivalence.
## Recommended G0.c decision rule
The gate should separate four layers.
### A. Procedural validity
Required before any scientific classification:
* amendment commit predates every evaluation command;
* repository and upstream commits are recorded;
* worktree state is declared;
* checkpoint hash is recorded;
* dataset manifest and split hash are recorded;
* evaluator configuration is frozen;
* batch size is fixed at 400 where specified;
* random seeds are complete;
* no run identity is resumed under incompatible metadata.
Failure here yields:
> **Gate execution invalid — no evidential classification.**
### B. Instrument consistency
The evaluator must demonstrate:
* deterministic or tolerance-bounded repeatability;
* identical results after interruption and resume;
* seed-complete aggregation;
* stable metrics across supported batch execution;
* finite values within defined mathematical ranges;
* table outputs traceable to raw run records.
### C. Behavioural sanity
The checkpoint should be compared with a clearly labelled random-initialized control.
The pre-registration should avoid assuming that every metric must improve monotonically. Instead, specify which metrics have a justified directional expectation.
Examples:
* trained checkpoint total loss should be lower than random initialization;
* orientation agreement should be better than random initialization;
* predicted temporal distance should show more meaningful association with target distance than random initialization;
* no claim should be made where the metric’s semantics do not establish a directional ordering.
### D. Historical-anchor interpretation
The relationship to `0.17398` should be reported descriptively:
* same order of magnitude or materially different;
* direction of deviation;
* plausible causes;
* whether differences are attributable to dataset composition, split reconstruction, weighting, batching, or implementation findings;
* whether any direct comparison remains scientifically defensible.
It should not be used as a pass/fail threshold.
## Classification semantics
| Classification                       | Required interpretation                                                                                                                                                                         |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Reproduced**                       | A genuinely equivalent reference evaluation was reconstructed and matched within a pre-declared criterion. This may be impossible under F10 unless new evidence recovers the original protocol. |
| **Reconstructed but not reproduced** | A valid, internally consistent evaluation was constructed, but it is not equivalent to or does not recover the upstream reference result.                                                       |
| **Not reconstructable**              | Material missing specification prevents establishment of an evaluation whose relationship to the reported result is scientifically defensible.                                                  |
Under the currently known evidence, **“Reconstructed but not reproduced” should be the declared expected classification**, not because failure is anticipated, but because the available evidence indicates that the target evaluation and original splits are non-equivalent.
## Amendment session content
The amendment should make four targeted changes.
### 1. Oracle-substitution clause
Use the review wording almost exactly:
> Triggers 1–2 were addressed through executable conformance oracles rather than an independent red-team review. These oracles establish consistency with the pinned upstream implementation; they do not establish that the upstream computation is conceptually or scientifically valid. Independent validity review therefore remains pending and is required before scientific claims are accepted.
Then retain the integration-seam requirement separately:
> Conformance to shared reference functions does not eliminate failures at integration boundaries, including serialization, configuration propagation, checkpoint restoration, evaluator orchestration, and table aggregation. Those seams require independent tests.
### 2. F12 taxonomy entry
Recommended classification:
> **F12 — Metric redundancy induced by representation normalization**
Record:
* the two affected metrics;
* the algebraic equivalence conditions;
* code locations;
* executable confirmation;
* why the (xy) case differs;
* reporting implications;
* whether historical results used both values as if independent.
### 3. Review archival
Archive the external review verbatim and add only metadata around it:
```text
Source: external methodological review
Date received: 2026-07-31
Scope: M1 completion and G0.c readiness
Status: reviewed and dispositioned
```
Then maintain a separate disposition document or section showing:
* accepted verbatim;
* accepted with refinement;
* rejected;
* deferred;
* implementation commit.
Do not annotate or alter the source text itself.
### 4. Pre-registration language
The amendment must explicitly state:
* why `0.17398` is not a numerical reproduction target;
* which criteria are internal-consistency criteria;
* which behavioural comparisons are directional;
* which outcomes are possible;
* what invalidates the gate;
* that the protocol commit must precede execution.
## Commit-order control
This is indeed the most important procedural control.
The gate report should record at least:
```text
Pre-registration commit: <SHA>
Pre-registration commit time: <timestamp>
First evaluation command time: <timestamp>
Evaluation code commit: <SHA>
Worktree status at first command: clean / declared modifications
```
A stronger machine-enforced control would make the evaluation command consume the expected pre-registration commit:
```bash
python offline.py \
  --preregistration-commit <SHA> \
  ...
```
The evaluator or gate script can then verify:
1. the commit exists;
2. it is an ancestor of `HEAD`;
3. the relevant protocol file at that commit matches the archived pre-registration;
4. the output directory did not predate that commit;
5. the gate has not previously been initialized under a different protocol hash.
This is preferable to relying only on retrospective `git log` inspection.
## The strongest scientific framing
Your final paragraph captures the programme correctly, but the paper should avoid saying the gate “cannot fail” without the procedural qualification.
The academically defensible framing is:
> G0.c is designed as a classificatory gate rather than a confirmatory test of a preferred result. Once procedural validity is established, every evidential outcome is reportable: successful reproduction, valid reconstruction without reproduction, or demonstrated non-reconstructability.
That makes the pre-registration consequential. It prevents the later interpretation from being selected based on which number appears.
One further caution: the phrase **“most-cited navigation models”** should only enter the manuscript after a documented bibliometric basis exists. For now, use “widely used” or “influential open visual-navigation implementations” unless citation rankings have been independently established.
## Final judgement
Proceed exactly in this order:
1. Amend the methodological record.
2. Archive the external review verbatim.
3. Add F12 and the oracle-substitution clause.
4. Implement the five hardenings.
5. Commit the G0.c decision rule.
6. verify the pre-registration commit and clean execution state;
7. execute G0.c;
8. classify rather than rationalize the result.
The critical achievement is already visible: the infrastructure is producing findings before producing performance claims. F12, the scheduler-resume defect, and the unrecoverable split problem are not peripheral discoveries. They are direct evidence that evaluation trustworthiness is itself a substantive research object.
