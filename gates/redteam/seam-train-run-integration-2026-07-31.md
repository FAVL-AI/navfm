# Integration-seam review — `train/run.py` against the pinned reference

**Trigger.** Standing-instructions adversarial review policy: the
oracle-substitution clause states that conformance to shared reference
functions does not eliminate failures at integration boundaries —
serialization, configuration propagation, checkpoint restoration, evaluator
orchestration, table aggregation — and that those seams require independent
adversarial review on their own account. M1 substituted conformance oracles
for red-team triggers 1–2; this is the seam review that substitution left
owing.

**Artefact.** `src/navfm/train/run.py` and `src/navfm/train/finetune.py`,
refuted against upstream `train_utils.py`, `train.py`, `vint_dataset.py` at
`dca7981`.

**Mechanics.** Independent subagent, given the repository files and the
upstream source, explicitly barred from treating this repository's tests as
evidence — they are co-authored with the code under review and may encode the
same misreading. Nothing was executed; every claim is from source reading.

**VERDICT: REFUTED.** Eleven findings. The five attack lines the policy names
resolved as follows.

| Attack line | Outcome |
|---|---|
| 1. Tensor preparation entering `_compute_losses` | **Attack fails** on order, shape, dtype and the cumulative-waypoint convention — identical to upstream. Autocast is a disclosed divergence. |
| 2. Accumulation loss-scaling vs effective LR | **Attack fails** on the hypothesised N× LR error — the loss *is* divided by `accum` (`run.py:214`). A different, real defect found instead (F4). |
| 3. Scheduler step count per epoch | **Attack fails.** One step per epoch, identical to upstream's ViNT/GNM loop. F8's double-step is NoMaD-only and unreachable here. Two real defects found nearby (F1, F2). |
| 4. `freeze_bn` surviving mode toggling | **Attack succeeds as a latent defect** (F7): the invariant is broken and survives only by accident of ordering. |
| 5. Replay mixing vs per-dataset `metric_waypoint_spacing` | **Attack fails.** Per-dataset normalisation is preserved end to end. A separate hard defect found in the mixing path (F6). |

## Findings, severity-ordered

Verification status is mine, added after the review: **[VERIFIED]** means I
re-checked it against source myself before recording it here.

| # | Finding | Class | Status |
|---|---|---|---|
| F9 | `load_into` result is recorded and never inspected, so a checkpoint that loads zero tensors trains from random init while `config.json` names a checkpoint and its SHA | changes a number | **[VERIFIED]** `run.py:409`, `:523–524`. **Fixed this session** — threatens G0.c directly |
| F1 | `warmup_epochs` is a config field, written into `config.json`, and read by no code | changes a trained model, when set | **[VERIFIED]** `finetune.py:67`; no reader anywhere in `src/navfm/`. Default is 0, so the default path is honest; a non-zero value produces a run record that claims a warmup that did not happen |
| F3 | The training-curve eval runs under autocast; the gate/table eval runs fp32. `offline.py`'s docstring claims the same code path guarantees they are never computed two different ways | changes a number | **[VERIFIED]** `offline.py:171,188`. The *code path* is the same; the *numerics* are not. G0.c is unaffected — the gate path takes no `amp` and runs fp32, which the gate report states explicitly |
| F2 | `scheduler: plateau` with `eval_every != 1` feeds `0.0` on non-eval epochs, so `ReduceLROnPlateau` fixes `best = 0.0` and decays on a fabricated baseline | changes a trained model | not re-verified; deferred |
| F4 | Accumulation is not equivalent to the effective batch: `action_reduce`'s `/(mask.mean() + 1e-2)` is computed per micro-batch, and mean-of-quotients ≠ quotient-of-means | changes a trained model, second order | not re-verified; deferred |
| F5 | `grad_clip: 1.0` by default has no upstream counterpart (upstream ViNT sets `clipping: False`, and its enabled form is element-wise clamp, a different operator); `amp_dtype: fp16` is accepted with no `GradScaler` | changes a trained model | not re-verified; deferred |
| F6 | An empty replay loader makes `_cycle` spin without yielding, hanging the trainer with no output; the target loader has a guard, the replay loader has none | availability | not re-verified; deferred |
| F7 | `offline.evaluate`'s `model.train(was_training)` un-freezes every BatchNorm's mode; nothing re-applies the freeze until the next epoch. Benign only because no forward pass exists in that window | latent | not re-verified; deferred |
| F8 | Every run's `config.json` carries a note advertising a deliberate deviation from upstream's double-stepping — but upstream's ViNT/GNM loop steps once, exactly as this driver does, so the record claims a change that was never made | cosmetic, but in the run record | not re-verified; deferred |
| F10 | `set_seed`'s stated justification for `PYTHONHASHSEED` is factually wrong: `dataset_index` comes from a sorted list, not a set iteration order | cosmetic | not re-verified; deferred |
| F11 | The eval loader reshuffles every epoch, so successive validation points measure slightly different batch compositions. Upstream-faithful, but it undercuts reading the curve as a per-epoch comparison | changes a number, small | not re-verified; deferred |

## What was done about them in this session

**F9 is fixed**, because it threatens the gate this session executes. G0.c
loads the released `vint.pth`; a silent zero-tensor load would produce a
number from a randomly initialised model carrying a checkpoint SHA in its own
provenance record — precisely the contamination the `random_init` stamping was
built to prevent, arriving through a door that stamping does not watch.

**F3 changes what the gate report must say** rather than what the gate does.
The G0.c evaluation runs fp32 (no `amp` on the gate path), and the report
states the precision explicitly instead of leaving it inferable.

**Everything else is deferred**, under the session's scope guard: this session
ends at the evidential classification of G0.c and does not extend beyond it.
None of the deferred findings lies on the G0.c evaluation path —
F1/F2/F4/F5/F6/F7/F8/F10/F11 are all in the *training* driver, which G0.c does
not invoke. They are recorded as an audit finding set with owners, not as
resolved items, and `docs/reviews/DISPOSITIONS.md` carries them forward.

## The methodological point

The review found nothing wrong with the objective, the label convention, the
scheduler count, or the per-dataset normalisation — the four things a
conformance oracle already covers. Every finding it did return lives at a seam
the oracle does not reach: a config field nothing reads, a result nothing
inspects, a precision mismatch between two callers of one function, a mode
toggle undone by the evaluator, a note describing a deviation that was never
made.

That is the oracle-substitution clause's claim, demonstrated rather than
asserted. Conformance to a shared reference function was necessary and was not
sufficient, and the sufficient part had to be bought with an independent
adversarial pass.
