# isaac-navfm

Reproducible research infrastructure for the GNM / ViNT / NoMaD visual
navigation foundation models, with Isaac Sim data collection for a Yahboom
ROSMASTER M3 PRO and single-GPU fine-tuning.

Three things this repo does that were not previously possible:

1. **Specifies the GNM on-disk format** — which has never been written down,
   only implemented — as machine-checkable constraints, and **proves**
   compatibility by loading generated data through the actual reference
   `ViNT_Dataset` (`tests/test_upstream_compat.py`).
2. **Collects new data in Isaac Sim** with a documented synchronisation
   contract, so every `t.jpg` provably corresponds to `position[t]` and
   `yaw[t]` at the same simulated instant.
3. **Derives the normalisation constants** (`metric_waypoint_spacing`,
   `action_stats`) that the reference repo hard-codes with no published
   derivation and three unanswered questions about.

Primary model: **ViNT**. Rationale in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) §4.

---

## Quick start

```bash
pip install -e ".[dev]"
pytest -q                                     # 51 tests, no GPU, no Isaac Sim needed

# with the reference repo available, the compatibility proof runs too:
git clone https://github.com/robodhruv/visualnav-transformer.git third_party/visualnav-transformer
NAVFM_UPSTREAM=third_party/visualnav-transformer pytest -q
```

Then, in order:

```bash
# 1. collect in Isaac Sim (separate venv -- see docs/ISAAC_COLLECTION.md)
python -m navfm.isaac.collect --config configs/collect/m3pro_indoor.yaml \
    --out /data/isaac_m3pro --robot-usd assets/m3pro.usd --episodes 600

# 2. prove it will load, and derive the constants
python -m navfm.validate /data/isaac_m3pro --model vint --decode-images --workers 8
python -m navfm.stats    /data/isaac_m3pro --name isaac_m3pro --len-traj-pred 5 --context-size 5

# 3. register and split (deterministic, scene-grouped)
python scripts/register_dataset.py third_party/visualnav-transformer \
    --name isaac_m3pro --spacing <derived> --camera-height 0.28 --camera-x-offset 0.16 --hfov 64
python -m navfm.splits /data/isaac_m3pro --name isaac_m3pro \
    --out third_party/visualnav-transformer/train/vint_train/data/data_splits --group-by scene

# 4. fine-tune ViNT on one 16 GB GPU
python -m navfm.train.run --config configs/train/vint_finetune_4080s.yaml
```

---

## Documentation

| Document | What it answers |
|---|---|
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | How each of the three papers works, step by step, with every paper↔code discrepancy marked; why ViNT is the right primary model; what is novel here |
| [`docs/DATA_FORMAT.md`](docs/DATA_FORMAT.md) | The written specification of the GNM on-disk format |
| [`docs/REPRODUCTION.md`](docs/REPRODUCTION.md) | Executable runbook: environment, checkpoints, datasets, the 2026 dependency landmines, the known-issue index |
| [`docs/ISAAC_COLLECTION.md`](docs/ISAAC_COLLECTION.md) | Isaac Sim setup, the synchronisation contract, demonstrator design, scene choices |
| [`docs/HARDWARE.md`](docs/HARDWARE.md) | M3 PRO: what Yahboom publishes, what it does not, and how to measure the rest |
| [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md) | Hypotheses, the run matrix, metrics, threats to validity, venue framing |

---

## Package map

| Module | Role |
|---|---|
| `navfm.schema` | the format, as checkable constraints |
| `navfm.writer` | atomic, crash-safe, streaming trajectory writer |
| `navfm.validate` | strict dataset validator (`python -m navfm.validate`) |
| `navfm.stats` | derive `metric_waypoint_spacing` and `action_stats` from data |
| `navfm.splits` | deterministic, scene-grouped train/test splits |
| `navfm.kinematics` | SE(2) helpers that bit-match the reference action pipeline |
| `navfm.control` | demonstrator and waypoint tracking, differential and holonomic |
| `navfm.planning` | occupancy grid, A*, string-pulling, episode sampling |
| `navfm.isaac` | Isaac Sim collection (Isaac imported lazily) |
| `navfm.models` | checkpoint loading for the three released models |
| `navfm.train` | single-GPU fine-tuning |
| `navfm.eval` | reference-exact offline metrics, closed-loop metrics, bootstrap CIs |

---

## Things you will otherwise learn the hard way

Verified against the reference repo at commit `dca7981` (2024-09-14 — the
current HEAD; the repo has been unmaintained for ~22 months).

* **`yaw` must be unwrapped.** `_compute_actions` does `yaw[1:] - yaw[0]` with
  no angle wrapping, so a `±π` crossing injects `2π` into the orientation
  labels. The reference preprocessing scripts do not unwrap — this is a latent
  bug in the original datasets too.
* **`goals_per_obs` and `negative_mining` are dead config keys.** GO Stanford is
  *not* double-weighted despite what `vint.yaml` says.
* **`models.yaml` names two checkpoints that do not exist.** The released GNM
  file is `gnm.pth`, not `gnm_large.pth` (whose original Drive folder now 404s),
  and `vint_late_fusion.pth` was never published.
* **`nomad.pth` is a bare state_dict** with no optimizer or epoch, so upstream's
  own resume path cannot load it (issue #10, never fixed).
* **`cory_hall` is an *active* dataset in all three training configs** with no
  public download link, so training as shipped dies on a missing directory.
  `scand` is marked private and is in fact public CC0.
* **`torch >= 2.6` cannot load `vint.pth` or `gnm.pth`** without
  `weights_only=False` — they contain pickled model objects.
* **`diffusers==0.11.1` no longer installs cleanly**: it declares
  `huggingface-hub>=0.10.0` with no upper bound, and hub 1.x removed `HfFolder`.
  Pin `huggingface_hub==0.25.2`.
* **Evaluation metrics are batch-size dependent** — cosine similarity drops
  0.96 → 0.5 between batch 400 and batch 1 (issue #51). Always state the batch
  size.
* **`action_reduce` is not a mean.** The `+1e-2` guard scales every reported
  value by `p/(p+0.01)`. Reproduced in `navfm.eval.metrics`.
* **NoMaD's `dist_loss` goal-masking is a no-op** (scalar × vector), so the
  distance head trains on masked samples too. You must reproduce this to match
  the released checkpoint.
* **`lr_scheduler.step()` is called twice per epoch** in the NoMaD loop, so
  `CosineAnnealingLR(T_max=100)` finishes at epoch 50 and climbs back up.

`scripts/patch_upstream.py` fixes the mechanical ones, reversibly, with a diff.

---

## Status

Implemented and tested: format schema, writer, validator, statistics, splits,
kinematics, control, planning, checkpoint loading, evaluation metrics, and the
upstream compatibility proof.

Implemented against the documented Isaac Sim 6.0.1 / 5.x APIs but **not
executed** in this repository (no Isaac Sim in CI): the collector, robot rig and
domain randomisation. First run on a machine with Isaac Sim should be a 20-episode
smoke test through `navfm.validate` before scaling up.

Not implemented: ViNT's 318 M-parameter image-diffusion subgoal generator (it is
not in the reference repo either), and NoMaD's frontier-based exploration
planner (`explore.py` ships `naction = naction[0]` with the comment
`# change this based on heuristic`).

## License

MIT. See `LICENSE`.

The reference implementation (`robodhruv/visualnav-transformer`) is MIT.
Datasets carry their own licenses: RECON MIT, SACSoN/HuRoN MIT, SCAND CC0,
TartanDrive MIT, CoryHall (via Open X-Embodiment) Apache-2.0, **GO Stanford
CC BY-NC-SA 3.0 — non-commercial**.
