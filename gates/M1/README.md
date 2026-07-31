# M1 — the runs-to-tables path, closed

Milestone M1 (docs/KICKOFF_PROMPT.md Session 1) implemented the three missing
entrypoints so the pipeline runs unbroken from a dataset directory to a
markdown table in `paper/tables/`:

| | Entrypoint | What it now does |
|---|---|---|
| 1 | `python -m navfm.eval.offline` | reference-exact offline metrics, strict + plain, ADE/FDE in metres |
| 2 | `python -m navfm.train.run` | single-GPU fine-tune against the reference objective, resumable |
| 3 | `python scripts/make_tables.py` | `runs/` → `paper/tables/*.md`, or a loud failure |

**This is not a gate in the G0–G6 sense.** No phase of `docs/WORKFLOW.md` was
executed. These are milestone artefacts: evidence that the code paths run, not
evidence about any model. Gate G0 is Session 2's work and its evidence goes in
`gates/G0/`.

## Files

| File | What it is |
|---|---|
| `reproduce.sh` | regenerates everything below from a clean checkout, CPU only |
| `e2e.txt` | its output: corpus → split → validate → eval → 3-seed fine-tune → round trip → stamping assertions → tables |
| `verify.txt` | `ruff` + `mypy` + full suite + the upstream-marked suite |
| `metrics_randominit_control.json` | the uncheckpointed eval's own record — `"random_init": true` |
| `metrics_finetuned_roundtrip.json` | the checkpointed eval's — `"random_init": false`, with the SHA-256 of the bytes scored |

```bash
PYTHON=~/.venv-train/bin/python bash gates/M1/reproduce.sh
```

The script does **not** guess an interpreter. Picking the wrong environment
silently would produce numbers from the wrong torch, so it refuses to start
unless `$PYTHON` can import `navfm` and resolve the reference clone, and names
the fix in each case. It also refuses to delete a workdir it did not create —
it `rm -rf`s that path, and a mistyped argument must not be how you lose a
directory. `verify.txt` records the interpreter and torch version actually
used; `e2e.txt` opens with the same line.

## What the evidence shows

* **204 tests pass** (was 129 at the start of M1), of which **26 are
  `upstream`-marked** and run against the pinned reference clone `dca7981`.
  `ruff` and `mypy` clean across 24 source files.
* The validator PASSes on a corpus written through `navfm.writer`, recovering
  `metric_waypoint_spacing ≈ 0.2499 m` (sd 0.0000) from data generated at
  0.25 m — the writer/validator/stats loop agrees with itself.
* Offline evaluation runs end to end on CPU and reports both reductions. The
  strict/plain ratio is the `p/(p+0.01)` scaling that finding F6 predicts.
* Three seeds of one matrix cell fine-tune for 2 epochs each, with per-epoch
  eval through the *same* evaluator, and land in `runs/` with `config.json`,
  `git_sha.txt` and per-epoch metrics.
* A fine-tuned `epoch_N.pth` loads back into the evaluator with **799 tensors,
  0 missing, 0 unexpected, and no `--trust-checkpoint`** — finding F5 describes
  the released checkpoints, and our own must not inherit it.
* `make_tables.py` refuses a cell with a missing seed (exit 2, nothing
  written), and produces bootstrap CIs when the cell is complete.

## What the numbers in `e2e.txt` are NOT

Every model in that log is randomly initialised or trained from scratch on
**synthetic noise images**. The losses show that gradients flow and that the
plumbing is connected. They say nothing about ViNT, about navigation, or about
this project's hypotheses.

The artefacts say so themselves, and step 7 of `reproduce.sh` *asserts* it
rather than leaving it to this file to claim: the evaluator prints a two-line
`RANDOM INITIALISATION — not a result` banner, `metrics.json` carries
`"random_init": true` with a null checkpoint (archived here as
`metrics_randominit_control.json`), a checkpointed run carries
`"random_init": false` and the SHA-256 of the bytes it scored (archived as
`metrics_finetuned_roundtrip.json`), and `make_tables.py` stamps
`RANDOM INIT — not a result` on any cell built from such a run. If any of that
regresses, the gate script fails rather than the README going quietly stale.

The first real number is **gate G0.c**: released `vint.pth` on a GO Stanford
test split at batch 400. It does not exist yet.

The checkpoint's own recorded `avg_total_test_loss = 0.17398` is **not** the
target that number is measured against. Per the accepted programme review
(`docs/reviews/`), it is a provenance anchor only: it was produced over a
five-dataset mixture whose evaluation composition and original split
identities cannot be reconstructed (F10), so a tolerance around it would put
false precision on non-equivalent quantities. The decision rule that replaces
it — four layers, three possible classifications — is pre-registered before
G0.c executes, in the M2 session.

## Finding recorded during M1

**F12 — two of the reference's logged metrics are the same number.**
`action_orien_cos_sim` and `multi_action_orien_cos_sim` are provably identical
for both released architectures. Written up in `paper/draft.md` §3 and
Appendix C, `docs/METHODOLOGY.md` §1.4, and pinned by
`tests/test_upstream_losses.py::test_the_two_orientation_metrics_are_the_same_number`,
which asserts it against `train_utils._compute_losses` rather than against our
port. Visible in `e2e.txt` as two identical rows.

## Status

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

M1 is **complete with one explicit caveat**: M1 validates the reproducibility
infrastructure within a *declared* execution environment. M2 extends that
validation to the *canonical* execution environment before any scientific
claims are generated. Those are two different propositions, and only the first
is closed here.

The freeze commit is **`c82e406`**, annotated tag `m1-freeze`. (The accepted
M1 review names `b673fa5`; that SHA predates this repository's `filter-branch`
rewrite, is not an ancestor of `HEAD`, and resolves only in one machine's
reflog. Cite `c82e406`.)

## Adversarial-review note

The standing-instructions file mandates red-team review at two triggers M1
touches: semantic changes to `eval/metrics.py` (trigger 1) and the
training-loss implementation in `train/run.py` (trigger 2). Both exist because
*no oracle exists* there. M1 built the oracles instead:

* `train/run.py` does not implement the objective. It calls
  `train_utils._compute_losses`, the reference function itself, so there is no
  reading of the weighting to refute.
* the metric additions are asserted equal to that same reference function
  across four mask rates and two `alpha` values, keys included, in
  `tests/test_upstream_losses.py`.

The correct record of that decision is **not** "red-team review was
unnecessary". It is:

> Red-team review triggers 1–2 were satisfied by constructing executable
> conformance oracles that directly test the relevant semantic risks.
> Independent adversarial validity review remains pending and is required
> before scientific claims are derived from G0.c or later experimental
> outputs.

The distinction is load-bearing. A conformance oracle answers *does the
implementation match the reference?* It does not answer *is the reference
computation scientifically meaningful?* M1 establishes the first only, and an
oracle that agrees with a wrong reference agrees wrongly. Conformance also
does not cover the integration seams — serialization, configuration
propagation, checkpoint restoration, evaluator orchestration, table
aggregation — where a correct component and a correct reference still combine
into a wrong number.

Remaining triggers (pre-registration amendments, the Phase 4 design attack,
the paper claim-by-claim pass, and the evidence-shape trigger added with this
review) are untouched by M1 and still stand.
