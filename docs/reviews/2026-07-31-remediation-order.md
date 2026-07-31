Source: external methodological review
Date received: 2026-07-31
Scope: remediation order for the G0.c amendment following the "Cannot determine" adjudication — RNG stream separation, seed predeclaration, audit-integrity fix, and the final supersessions
Status: reviewed; execution outstanding

---

# Remediation order — G0.c amendment, post-adjudication

Issued after `gates/redteam/trigger3-g0c-amendment-v2-2026-07-31.md` returned
**Cannot determine** on the §9 question. Two findings blocked a *Fixing*
verdict; both lay in the specification's own text. The remaining findings are
implementation-side.

## Corrected items (blocking findings)

**1. Historical disclosure — misattribution.** The mandated blockquote read
"Amendment 1 preregistered an order-of-magnitude relationship to 0.17398".
Amendment 1 (`459c65c`) is the E2 analysis plan and contains no reference to
`0.17398` (grep count 0). Corrected disclosure must name **`92e3004`** as the
introduction commit — the repository's first commit — and **`d6cef79`** as the
retirement, must not attribute the condition to Amendment 1, and must note that
the condition's committed life spans the repository's entire pre-freeze history.
The misattribution had flattered the retirement by shortening it.

*Programme addition, verified at execution time:* the condition entered
`docs/EXPERIMENTS.md` (E0.2) at `92e3004` and was restated in
`docs/WORKFLOW.md` (G0.c) at `d4fc321` when the gated-execution documentation
was created. Both were retired at `d6cef79`. The earlier draft named `d4fc321`
for both documents, which is right for one and wrong for the other.

**2. Outcome mapping — the decisive missing cell.** No row covered Layers A, B
and C all passing while Condition 7 alone fails. Row 2 voids itself via
"subject also to Conditions 1–5 and 7"; rows 3–4 require partial or failed
Layer C; row 5 is foreclosed by Condition 7's own sentence. The cell is reached
precisely when the reinstated anchor comparison fails — where §5 forbids
narrative discretion. The missing cell turns out to *be* the tripwire case.

### Sixth mapping row — final text, verbatim

> Valid instrument execution with failed historical-anchor sanity. This is a
> diagnostic outcome. It blocks Classification 2, is not Classification 3, does
> not populate the preregistered scientific result table, and mandates
> investigation of scale, normalisation, evaluator configuration, dataset
> identity, checkpoint identity, or other pipeline factors before any
> subsequent execution. Any execution following that investigation constitutes
> a new experimental run, receives a new run identity, and records an explicit
> lineage link to the originating diagnostic run. The original diagnostic run
> remains immutable and is not reclassified retrospectively.

This supersedes the earlier sanctioned wording.

## §9 ruling

The reinstatement is **legitimate**: all five sanctioned constraints are
honoured, and a factor-of-100 band is a plausibility check on scale, not an
estimand tolerance. The defect was the unlabelled consequence, which the sixth
row supplies.

## Implementation remediation

**1. RNG stream separation — the deepest finding.** `seed_model_rng` reseeds
the global NumPy stream that upstream's `_sample_goal` draws from
(`vint_dataset.py:301,195,207`), so changing `--model-seed` changes *which
(observation, goal) pairs are scored*. Decouple: model initialisation consumes
its seed at build time; then, before any dataloader iteration, the global
data-sampling RNG is re-seeded to a single **predeclared population seed**,
identical in every arm — both checkpoint runs and all three controls score the
identical population.

Preferred verification object: an **evaluation-pair manifest**, generated in a
pre-execution pass under the declared `evaluation_seed`, digest pinned, with
every arm verifying its realised pairs against it at runtime.

Acceptance — two causal-contract invariants, above the five lower-level RNG
assertions, which remain:

- (a) fixed `evaluation_seed`, `model_seed` A vs B → **identical sampled pairs,
  different weights**;
- (b) fixed `model_seed`, `evaluation_seed` A vs B → **identical weights,
  different pairs**.

Full success criterion: identical evaluation population across arms; different
parameters across model seeds; identical checkpoint-arm population across
repeats; population reproducible from the declared seed alone.

Any `_sample_goal` refactor goes through `scripts/patch_upstream.py` with an
archived diff.

**2. Predeclare the checkpoint arm's population seed** in the amendment's seed
declarations. Condition 3's run-twice identity criterion is only meaningful
under a declared population seed; this closes "`L` depends on an undeclared
parameter".

**3. `environment_identity_recorded`.** Replace the constructed `passed=True`
with a real hash comparison against the preregistered identity, exposing
expected and observed digests and the mismatching fields; mismatch is FAIL and
the gate is invalid. Four negative tests — perturbed `PYTHONPATH`, perturbed
resolved module path, perturbed executable identity, one perturbed canonical
field — each making the audit exit non-zero.

File the always-pass stub as a failure record, classified as an **audit
integrity defect**, same family as F-M2-1: *the mechanism purported to verify a
property while being incapable of falsifying it*. Authorship acknowledged,
because the audit framework is subject to the same evidential standards it
imposes.

## Order of execution

Steps 1–3 as infrastructure; fold the corrected disclosure and the sixth row
into the draft; full suite, typecheck and lint; a freeze audit whose only
failing check is `amendment_committed`; then submit the revised draft **plus
the prior Cannot-determine disposition** to a fresh red-team adjudication on the
§9 question against the eight Fixing requirements. Commit only on *Fixing*.

On *Fixing*: commit; freeze audit against the exact amendment SHA with all
checks passing and archived; verify no prior G0.c results; hash `vint.pth`
immediately before scoring; execute only the preregistered commands; classify
from the frozen rule; produce `gates/G0/G0c_report.md`.
