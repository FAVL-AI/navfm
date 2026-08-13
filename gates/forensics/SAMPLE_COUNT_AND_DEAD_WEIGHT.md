# Two numbers that were left unexplained, now explained

Evidence: `gates/forensics/train_path_compatibility.json`
Harness: `scripts/verify_train_path_compatibility.py`
Date: 2026-08-13 · Author: Frank Asante Van Laarhoven

Both items below came out of the same run. Neither is a defect. Both were
numbers a reader could have accepted without understanding, which is the
condition under which a real defect eventually hides.

---

## 1. Why GNM 30, ViNT 30, NoMaD 29

Earlier the three-model loader result was recorded as "GNM 30, ViNT 30, NoMaD
29 samples". That is now derived rather than observed.

The reference indexer (`ViNT_Dataset._build_index`) admits a sample only where a
full context window exists behind the observation and a full prediction horizon
exists ahead of it:

```
begin = context_size  * waypoint_spacing
end   = traj_len - end_slack - len_traj_pred * waypoint_spacing
n     = max(0, end - begin)
```

Our trajectory is 40 frames, `waypoint_spacing = 1`, `end_slack = 0`.

| Model | Context behind | Horizon ahead | n | Check |
|---|---|---|---|---|
| GNM | 5 | 5 | 40 − 0 − 5 − 5 = **30** | actual 30 ✓ |
| ViNT | 5 | 5 | 40 − 0 − 5 − 5 = **30** | actual 30 ✓ |
| NoMaD | 3 | 8 | 40 − 0 − 8 − 3 = **29** | actual 29 ✓ |

**Classification: DESIGN / MODEL-SEMANTIC. Not a defect, not an off-by-one.**

The loop at `_build_index` L221 has **no rejection branch** — every value in
`range(begin_time, end_time)` is appended unconditionally. So there is no filter
that could be dropping a sample; the count is fixed entirely by where the range
starts and stops. This was verified rather than assumed: the accepted index set
from each constructed dataset was compared against the rule's range and matched
exactly for all three models.

**It is not simply a loss.** NoMaD *gains* two candidates at the front and
*loses* three at the back:

| | GNM / ViNT | NoMaD | |
|---|---|---|---|
| admissible range | `[5, 35)` | `[3, 32)` | |
| gains | — | **3, 4** | needs only 3 context frames, not 5 |
| loses | — | **32, 33, 34** | predicts 8 steps ahead, not 5 |
| net | — | **−1** | |

Population conservation holds for all three, so nothing disappears silently:

| Model | Candidates | Accepted | Rejected | Conserved |
|---|---|---|---|---|
| GNM | 40 | 30 | 10 | ✓ |
| ViNT | 40 | 30 | 10 | ✓ |
| NoMaD | 40 | 29 | 11 | ✓ |

**We preserve 29 rather than forcing 30.** Patching upstream to equalise the
counts would fabricate a sample outside NoMaD's admissible range — it would make
the table symmetrical and the comparison less valid. Scientific comparability
means the same evidence standard, not identical internal implementation.

Per-candidate evidence is in `gates/forensics/nomad_sample_index_trace.csv`
(120 rows: 40 candidates × 3 models, each with context indices, action indices,
validity and rejection reason cited to `vint_dataset.py:219-221`), and the
population arithmetic in `gates/compatibility/<model>_sample_population.json`.

The harness computes the predicted count from each config and asserts it against
`len(dataset)`. If a future config change alters a horizon, the count changes
with it and the assertion says so, rather than a reader having to notice that a
familiar number moved.

---

## 2. About 19% of the released ViNT checkpoint is never executed

While checking that an optimizer step actually moves the model, 16 parameters in
ViNT and the same 16 in NoMaD did not move. They received no gradient at all.
That is not noise, and it is the same 16 in both models because both inherit the
same two upstream constructions.

| Model | Dead tensors | Dead elements | Share of checkpoint | fp32 |
|---|---|---|---|---|
| ViNT | 16 | 5,714,384 | **19.21%** | 22.9 MB |
| NoMaD | 16 | 3,351,760 | **17.59%** | 13.4 MB |
| GNM | 0 | 0 | 0% | — |

Two independent causes, both verified against upstream source, not inferred:

**(a) The EfficientNet classifier heads — 4 tensors.**
`vint.py:41` and `:46` touch `self.obs_encoder._fc.in_features` and
`self.goal_encoder._fc.in_features`. That is a *shape lookup*. The forward pass
calls `extract_features` (`vint.py:82, 85, 105`), which stops before the
classifier. So `_fc.weight` and `_fc.bias` of both encoders are carried in the
checkpoint, restored by `strict=True`, and never called. They are ImageNet
classifier weights reachable only by their shape.

**(b) The transformer layer prototype — 12 tensors.**
`self_attention.py:31-32`:

```python
self.sa_layer   = nn.TransformerEncoderLayer(...)
self.sa_decoder = nn.TransformerEncoder(self.sa_layer, num_layers=num_layers)
```

`nn.TransformerEncoder` **deep-copies** the layer it is given. Verified directly:
`enc.layers[0] is l` → `False`, and the two do not share storage. So
`sa_decoder.layers.0 … .7` are the real, trained layers — all of which did move —
while `self.sa_layer` survives as a registered submodule holding an orphaned
copy. It is serialised into every released checkpoint and executed never.

### Why this matters, stated at its actual size

It does **not** invalidate anything. Strict load still passes 3/3 — the keys are
present on both sides, which is exactly why nothing complained. Inference is
unaffected. The released models are not wrong.

What it changes is arithmetic that gets published:

- A parameter count read off the checkpoint overstates ViNT's *trainable* model
  by 19.21%. "29.7M parameters" is 24.0M executed.
- A fine-tuning budget computed from checkpoint size over-provisions by the same
  fraction, and an optimizer built over `net.parameters()` allocates AdamW
  moments for 5.7M tensors that will never receive a gradient.
- Any claim of the form "we updated the whole network" is false for these 16.

### Why nothing caught it before

Every existing check is satisfied by this state. Strict load compares key sets,
and the keys match. Inference compares outputs, and the outputs are correct
because the dead tensors are not in the graph. A loss curve descends normally.
The only check that could see it is the one that asks *which specific parameters
an optimizer step moved* — and that check only exists because a train-path proof
needed a way to distinguish "the backward pass ran" from "the backward pass did
something", and the honest way to do that is per-tensor.

### Claim boundary

This is a property of the **released upstream artefacts** (`vint.pth`,
`nomad.pth`) under the pinned reference architecture at commit `dca7981`, on a
`strict=True` load. It is not a claim that the models were trained incorrectly —
the dead prototype layer never participated in training either, so the released
weights are exactly what the published training procedure produced. It is a
claim about what the distributed files contain.
