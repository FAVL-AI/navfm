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
| **NoMaD** | Sridhar et al. | — | — | — | — | — | — | **`BLOCKED_MISSING_EVALUATION_PATH`** — model assets exist; the evaluator raises by design; `_compute_losses_nomad` needs a diffusion sampling loop, so it is a separate entrypoint, not a `--model nomad` flag | `src/navfm/upstream.py`; standing instructions |

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

That ordering is expected rather than surprising. `config/gnm.yaml` opens with
`# NOTE: this model uses private datasets`, so GNM's checkpoint-associated
reference was computed over a mixture including corpora we cannot obtain at all.
Our single-corpus GO Stanford reconstruction is therefore a more distant estimand
for GNM than it was for ViNT — the larger delta is evidence about the *reference*,
not about our evaluation path.

Not `FAILED_REPRODUCTION`: nothing failed. The path executed over the full
declared population with exact repeatability and a 17.6× separation from random
initialisation. No preregistered reproduction tolerance existed, and none was
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

**NoMaD → needs an evaluation path, not an asset.** The checkpoint is held and
its digest recorded; what is missing is the diffusion sampling/evaluation
entrypoint (`_compute_losses_nomad`), which is deliberately a separate
entrypoint rather than a flag on the existing evaluator. Classifying this as a
missing *asset* would misstate where the gap is.

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
