# Red-team trigger 3 — revised G0.c amendment (draft v2)

**Question adjudicated**, verbatim from §9 of
`docs/reviews/2026-07-31-g0c-amendment-specification.md`:

> Does the revised amendment restore a genuinely falsifiable G0.c
> classification without reintroducing an invalid numerical comparison to
> `0.17398`, and are the checkpoint-arm and random-control repeatability
> criteria correctly separated by their sources of variance?

## VERDICT: Cannot determine — NOT COMMITTED

Not *Rescuing*: no G0.c datum exists (verified — no `runs/`, no `metrics.json`
carrying `155fd72d…`, nothing has scored `vint.pth`), and the amendment
*restores* a falsifiable condition rather than retiring one. Not *Fixing*: two
of the specification's eight required conclusions fail. Under §9 the amendment
may not be committed.

## Checklist

| # | Requirement | Result |
|---|---|---|
| 1 | corrects identifiable protocol defects | PASS — seven of the prior adjudication's eight requirements met |
| 2 | no released-checkpoint result informed the changes | PASS — verified by filesystem sweep and `git log --diff-filter=D` |
| 3 | seven Classification-2 conditions fully specified | PASS, with flagged ambiguities |
| 4 | Classification 3 reserved for evidential non-reconstructability | PASS |
| 5 | all partial outcomes have predeclared homes | **FAIL** |
| 6 | 0.17398 change disclosed honestly | **FAIL** |
| 7 | does not relax the frozen scene-grouping requirement | PASS — split re-derived independently from the committed files |
| 8 | does not certify its own validity | PASS |

## The two failures, re-verified against git

**Item 6 — two factual errors in the section whose only job is accurate
historical accounting.** Both confirmed:

* `git log -S"0.17398" -- docs/EXPERIMENTS.md` → **`92e3004`**, the repository's
  first commit. `git show --stat d4fc321` touches `PREREGISTRATION.md`,
  `docs/WORKFLOW.md` and `paper/draft.md` — **never `docs/EXPERIMENTS.md`**. The
  draft names `d4fc321` as the introduction commit for both documents. The error
  shortens the criterion's committed life by the entire pre-freeze history,
  which is mildly flattering to the retirement.
* `git show 459c65c:PREREGISTRATION.md | grep -c 17398` → **0**. The
  specification's mandated blockquote says "Amendment 1 preregistered an
  order-of-magnitude relationship to 0.17398". Amendment 1 is the E2 analysis
  plan and contains no such criterion. Reproducing mandated text is defensible;
  reproducing it without flagging the misattribution is not.

**Item 5 — the outcome mapping has no row for the case that matters most.**
Layer A passes, Layer B passes, Layer C passes completely, Conditions 1–5 pass,
**Condition 7 fails**. Row 2 matches on (B, C) but is voided by its own
"subject also to Conditions 1–5 and 7" clause and names no replacement; rows 3–4
require Layer C partial or failed; row 5 is foreclosed by Condition 7's own
sentence and by Classification 3's exclusion of "an inconvenient or unexpected
metric value". No outcome is declared — and the undeclared cell is reached
*precisely when the reinstated 0.17398 comparison fails*, which is exactly where
§5 forbids narrative discretion. The draft nonetheless asserts "Every partial
case has an explicit home."

## Answer to the §9 question

**Half one.** Falsifiability is substantially restored — seven conjunctive
conditions, a machine-checkable Layer A, a deterministic Layer B, a directional
Layer C where ties fail and descriptive cosines cannot rescue a failed loss
ordering. The reinstatement is **not** an invalid reproduction comparison: all
five sanctioned constraints are honoured, and a factor-of-100 band is a
plausibility check on scale and normalisation, not a tolerance on an estimand.
What is illegitimate is not the comparison but its unlabelled consequence.

**Half two.** The separation made is right; the separation claimed is
incomplete. The checkpoint arm is genuinely deterministic and excluding CV is
correct; the control arm is genuinely three initialisations. But
`seed_model_rng` reseeds the **global NumPy stream** that upstream's
`_sample_goal` draws from (`vint_dataset.py:301,195,207`), so changing
`--model-seed` also changes *which (observation, goal) pairs are scored*. The
three controls differ in evaluation draw as well as initialisation, and the
checkpoint arm's own seeds are never predeclared — leaving `L`, and therefore
Condition 7, dependent on an undeclared parameter.

## Six further defects recorded

Overstated Layer A enforcement (`environment_identity_recorded` is constructed
`passed=True` unconditionally and never compares against the preregistered
identity; the dataset digest is never re-hashed); split digests pinned under a
non-standard convention (`sha256` of joined names, not of the file) without
stating it; no commit-order disclosure though `d6cef79` already calls the rule
"pre-registered"; a primary/secondary ordering distinction the inherited outcome
table cannot index; `L` not bound to `strict/` where the threshold is applied;
and a vacuous `no_pre_audit_evaluator_output` check that globs inside a
directory check 13 already requires to be absent.

## Disposition

Closing the two blocking failures is mechanical, not structural. The draft is
preserved outside the repository. `PREREGISTRATION.md` is unchanged and still
ends at Amendment 1.
