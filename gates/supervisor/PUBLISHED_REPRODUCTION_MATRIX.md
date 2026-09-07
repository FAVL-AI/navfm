# Published-result reproduction matrix — BO-09

Audit date 2026-09-07. **This track is independent of Hospital scene admission**
and of the new-data collection track; it should have been running in parallel
and was not.

Status vocabulary: `REPRODUCED` · `PARTIALLY_REPRODUCED_WITH_AVAILABLE_RELEASE_ASSETS` ·
`BLOCKED_MISSING_EVALUATION_PATH` · `BLOCKED_MISSING_ASSET` · `BLOCKED_ENVIRONMENT` ·
`FAILED_REPRODUCTION` · `NOT_RUN`.

A model is **not** reproduced because a checkpoint loads, a forward pass runs, or
a finite loss appears. Published-result reproduction requires official data,
official preprocessing, the released checkpoint or the prescribed training, the
official metric, a comparable split, and a numerical result.

---

## Assets held

| Asset | State | Digest |
|---|---|---|
| `checkpoints/vint.pth` | present, digest recorded | `155fd72de2e98ae0…` |
| `checkpoints/gnm.pth` | present, digest recorded | `4b03e0255f8a5472…` |
| `checkpoints/nomad.pth` | present, digest recorded | `70f79b8262527e20…` |
| GO Stanford corpus | acquired 2026-07-31 | `1fe1411945abd9cd…` |
| Upstream code | pinned | `dca79815b704e5aa9c6bdc3082351f9e3b2848c2` |

All three released checkpoints and one official corpus are in hand. The blocker
is **not** asset availability for the checkpoints.

---

## Matrix

| Model | Paper | Dataset | Split | Metric | Published | Ours | Δ | Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| **ViNT** | Shah et al. | GO Stanford (reconstructed) | held-out, 760 traj / 15 scenes, 41 872 pairs, batch 400 | `strict/total_loss` | `0.17398` (checkpoint-associated, epoch 29) | **`0.18026808`** | **+3.61 %** | **`PARTIALLY_REPRODUCED_WITH_AVAILABLE_RELEASE_ASSETS`** — recorded verdict *"CLASSIFICATION 2 — RECONSTRUCTED BUT NOT REPRODUCED"* | `gates/G0/g0c/`, `runs/g0c/g0c-vint-r1`, `-r2` |
| **GNM** | Shah et al. | GO Stanford (reconstructed) | test, 41 872 pairs, 105 batches, batch 400 | `strict/total_loss` | `0.1393500482205535` (checkpoint-associated, epoch 29) | **`0.15870234802528657`** | **+13.888 %** | **`PARTIALLY_REPRODUCED_WITH_AVAILABLE_RELEASE_ASSETS`** | `GNM_REPRODUCTION_20260907.json`; `runs/trackA/gnm-r1`, `-r2`, `-control-seed0` |
| **NoMaD** | Sridhar et al. | — | — | — | — | — | — | **`BLOCKED_MISSING_RELEASED_EVALUATION_ENTRYPOINT`** — **executed**, boundary reached at `upstream.py:218` | `NOMAD_BLOCKER_20260907.json` |

---

## Why ViNT is `PARTIALLY_REPRODUCED` and not `REPRODUCED`

The recorded verdict is explicit, and I am not softening it:

> **CLASSIFICATION 2 — RECONSTRUCTED BUT NOT REPRODUCED**

> "The two quantities are NOT equivalent estimands: 0.17398 was computed over an
> unrecoverable five-dataset mixture, this over a reconstructed single-corpus
> scene-grouped holdout of 760 trajectories across 15 held-out scenes. Proximity
> is therefore corroborative of a correct instrument, and is not evidence of
> reproduction. No reproduction claim is made or implied."

**The precise blocker: the published evaluation mixture is unrecoverable.** The
released `avg_total_test_loss = 0.17398` was computed over five datasets whose
exact composition is not recoverable from the release. We hold one of them. So
the comparison is between two different estimands that happen to be close.

This is an **asset/provenance blocker, not an engineering one**. No amount of
work on our side reconstructs a mixture the release does not specify.

What the G0.c run *does* establish, on seven conjunctive conditions:

- procedural validity (16/16 freeze audit, worktree clean, digest re-verified);
- complete instrument execution (454 tests, 33 upstream-marked, none skipped);
- deterministic repeatability (two runs identical but for wall clock);
- control replayability and distinctness (three seeds → three distinct losses);
- metric validity declared pre-execution;
- behavioural sanity ordering — checkpoint `0.180268` vs controls `2.565585`,
  `2.890683`, `2.771972`, **an order of magnitude of separation, no tie**;
- the historical anchor within a sanity band, explicitly *not* a reproduction
  tolerance.

That is strong evidence the instrument is correct. It is not a reproduction of a
published number, and it must not be reported as one.

---

## GNM — executed 2026-09-07

| | |
|---|---|
| Reference (`gnm.pth` `avg_total_test_loss`, epoch 29) | `0.1393500482205535` |
| Reproduced r1 | `0.15870234802528657` |
| Reproduced r2 | `0.15870234802528657` — **bitwise identical** |
| Random-init control | `2.7875974904258642` — **17.56×** the checkpoint |
| Δ absolute / relative | `+0.019352300` / **+13.888 %** |
| Population | 41 872 pairs, 105 batches, none skipped |

Same evaluator, objective, split and population as the ViNT arm, so the two are
directly comparable. **ViNT deviated +3.61 %; GNM deviates +13.89 %, roughly four
times further.**

`config/gnm.yaml` opens with `# NOTE: this model uses private datasets`, so the
checkpoint-associated reference was computed over a mixture including corpora
that cannot be obtained. **The reference is therefore not reconstructable from
released assets, so the numerical delta is descriptive rather than a valid
reproduction error.** It does not measure how far our evaluation path is from the
published one, and it does not by itself prove the private-data explanation
either — the comparison is simply not between the same estimand.

The larger GNM delta is consistent with a more distant reference population, but
consistency is not evidence, and this ordering is recorded as an observation
rather than an inference.

Not `FAILED_REPRODUCTION`: nothing failed. The path executed over the **full
declared obtainable evaluation population** — which is *not* the population used
for the checkpoint-associated reference — with exact repeatability and a 17.6×
separation from random initialisation. Repeatability and control separation are
instrument checks; neither is published-reproduction proof. No preregistered reproduction tolerance existed, and none was
invented after seeing the result; the delta is reported descriptively.

Run under `runs/trackA/`, **not** `runs/g0c/`. G0.c was preregistered for ViNT;
recording GNM as a G0.c arm would claim a preregistration it never had.

## What would move each row

**ViNT → `REPRODUCED`.** Requires either (a) the five-dataset evaluation mixture,
which has not been reconstructed from the obtainable release assets, or (b) a
published number computed on a corpus we can obtain in full. Until one exists the
status is `PARTIALLY_REPRODUCED_WITH_AVAILABLE_RELEASE_ASSETS`.

This is a statement about **currently available assets, not a permanent ceiling**:
a later corpus release or an equivalent official artefact could lift it.

**GNM → executed.** Ceiling is the same as ViNT's and for a stronger reason: the
reference mixture includes private datasets. `REPRODUCED` is not reachable from
obtainable assets.

**NoMaD → executed blocker, not an inference.** See below.

---

## Honest summary for the supervisor

> On the published results: we hold all three released checkpoints and one
> official corpus. ViNT has been evaluated against its released checkpoint on a
> reconstructed GO Stanford holdout and lands within 3.6 % of the
> checkpoint-associated value, with random-initialisation controls an order of
> magnitude worse. We are recording this as *reconstructed, not reproduced*,
> because the published figure was computed over a five-dataset mixture that has
> not been reconstructed from the obtainable release assets — the two numbers are
> close but are not the same estimand. That is a limitation of the assets
> currently available to us, not a permanent one. GNM can be evaluated with assets
> already in hand. NoMaD holds its checkpoint but lacks the diffusion
> sampling/evaluation entrypoint the reproduction run needs.


---

## NoMaD — executed blocker, 2026-09-07

The earlier classification came from reading the repository. It has now been
**executed**, and the first attempt was not sufficient evidence.

| Attempt | Outcome | Sufficient? |
|---|---|---|
| CLI `--model nomad` | exit 2 — *"invalid choice: 'nomad' (choose from 'vint', 'gnm')"* | **No.** An argparse rejection is earlier than the evaluation boundary; it proves only that the CLI does not expose the model |
| API `upstream.build_model("nomad", …)` | `NotImplementedError` at **`src/navfm/upstream.py:218`** | **Yes.** Reaches the point at which the released model cannot be constructed for evaluation |

Inspecting the release at that boundary:

- `train_utils._compute_losses_nomad` **is present** upstream (line 447);
- the only evaluation-shaped module is `vint_train/training/train_eval_loop.py`;
- its only driver is `train.py`.

**The release computes NoMaD's diffusion losses inside the training loop and
ships no standalone evaluation entrypoint.** There is therefore no official
evaluation path to execute in the way ViNT and GNM were evaluated.

Classification: **`BLOCKED_MISSING_RELEASED_EVALUATION_ENTRYPOINT`**.

Not `BLOCKED_MISSING_ASSET` — the checkpoint and config are held and
digest-verified. Not `BLOCKED_MISSING_SAMPLING_IMPLEMENTATION` — upstream does
implement the sampling loss. What is absent is a standalone entrypoint invoking
it outside training.

No evaluator was written to make the row runnable. Building one would be new
work, not reproduction of a released path.

Also noted: NoMaD's config uses `context_size: 3` against GNM/ViNT's `5`, so it
would additionally require its own sample population rather than reusing the
41 872-pair set.

---

## BO-09 closure

| Model | Executed | `published_result_reproduction_status` |
|---|---|---|
| ViNT | ✅ result | `NOT_RECONSTRUCTABLE_FROM_RELEASED_ASSETS` |
| GNM | ✅ result | `NOT_RECONSTRUCTABLE_FROM_RELEASED_ASSETS` |
| NoMaD | ✅ blocker | `NOT_ATTEMPTABLE_FROM_RELEASED_EVALUATION_PATH` |

**BO-09 = `COMPLETE_WITH_EVIDENCED_LIMITATIONS`.** All three rows carry executed
evidence and a precise, evidenced ceiling.

This explicitly does **not** mean any published number was reproduced. Not one
was. What is complete is the *investigation*: for each model we can now say what
runs, what does not, and exactly why — and each remaining limitation is inherent
to what the release provides rather than to our engineering.
