# Reproduction runbook

Ordered, executable, with the failure you get if you skip a step. Verified
against the current state of the world in July 2026.

Two hard facts to internalise before starting:

* `robodhruv/visualnav-transformer` has had **no commits since 2024-09-14** and
  pins Python 3.8.5 / CUDA 10 / `diffusers==0.11.1`. As shipped, it does not
  install on a 2026 machine.
* **No third-party reproduction of ViNT or NoMaD training has ever been
  published** (searched GitHub issues, web, Hugging Face). You are not
  re-walking a well-trodden path; budget accordingly.

---

## Stage 0 — Environment

Isaac Sim and the training stack want different Pythons (3.12 vs 3.10/3.11).
Keep them in separate virtualenvs. They only ever exchange files.

```bash
# --- training / eval env -------------------------------------------------
python3.11 -m venv .venv-train && source .venv-train/bin/activate
pip install -U pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -e ".[train,dev]"

# The reference package, patched
git clone https://github.com/robodhruv/visualnav-transformer.git third_party/visualnav-transformer
python scripts/patch_upstream.py third_party/visualnav-transformer
pip install -e third_party/visualnav-transformer/train

# NoMaD's U-Net lives in an external repo that is NOT on PyPI, and the
# reference README gives an SSH clone URL that fails without keys.
git clone https://github.com/real-stanford/diffusion_policy.git third_party/diffusion_policy
pip install -e third_party/diffusion_policy
```

### Dependency landmines, all verified

| Item | Status July 2026 | Action |
|---|---|---|
| `diffusers==0.11.1` | still on PyPI, but declares `huggingface-hub>=0.10.0` with **no upper bound**, so a fresh install pulls hub 1.x and dies with `ImportError: cannot import name 'HfFolder'` | pin `huggingface_hub==0.25.2` (verified working) |
| `torch >= 2.6` | `torch.load` defaults to `weights_only=True`; `vint.pth` and `gnm.pth` contain pickled model objects → `UnpicklingError` | `scripts/patch_upstream.py`, or use `navfm.models.loader` |
| `torch` unpinned | resolves to 2.13.0; upstream issue #27 reports 2.4.0 breaking training, 2.3.1 working | pin explicitly and record the pin |
| torch/torchvision skew | `RuntimeError: operator torchvision::nms does not exist` | always install the matched pair from the pytorch index |
| `EMAModel` | `diffusers > 0.12` changed the signature to `EMAModel(parameters, …)` and dropped `averaged_model` (upstream issue #36) | stay on 0.11.1, or patch |
| `opencv-python==4.6.0.66` | no wheels for Python ≥ 3.11; PyQt5 conflict causes `Aborted (core dumped)` (issues #27, #43) | `opencv-python-headless`, `MPLBACKEND=Agg` |
| `roslz4` | **no wheel newer than cp38** on the rospypi index | only needed for rosbag conversion; needs `liblz4-dev` + a compiler, or use `rosbags` (pure Python) |
| ROS 1 Noetic | **EOL 2025-05-31** | for deployment use [RobotecAI/visualnav-transformer-ros2](https://github.com/RobotecAI/visualnav-transformer-ros2) (ROS 2 Jazzy/Humble, `uv.lock`, Docker) |
| `python 3.8.5` | EOL 2024-10-07 | use 3.10/3.11 |

---

## Stage 1 — Checkpoints

All three live in one Google Drive folder, `1a9yWR2iooXFAqjQHetz263--4_2FFggg`,
linked from the reference README. All three resolve and download (verified
2026-07-30).

| File | Size | Format | Note |
|---|---|---|---|
| `vint.pth` | 430 167 114 B (410 MB) | full training dict; `["model"]` is a live `ViNT` object | `epoch=29`, `avg_total_test_loss=0.17398` → this is the paper's 30-epoch run |
| `gnm.pth` | 104 806 886 B (100 MB) | full training dict, `GNM` object | `epoch=29`, `obs_encoding_size=1024` |
| `nomad.pth` | 76 473 631 B (73 MB) | **bare `OrderedDict`**, 645 keys | these are the **EMA** weights |

Two `models.yaml` entries are wrong:

* it expects `gnm_large.pth`; the released file is `gnm.pth`. The original
  `drive-any-robot` folder that hosted `gnm_large.pth` now returns **404**.
  Rename or edit the config.
* it expects `vint_late_fusion.pth`, which **was never released**. Delete the
  entry.

There is **no official Hugging Face mirror** of any of the three.

```bash
python -c "
from navfm.models.loader import load_checkpoint, extract_state_dict, CHECKPOINTS
obj = load_checkpoint('checkpoints/vint.pth', trust_checkpoint=True)
print({k: type(v).__name__ for k, v in obj.items()})
print(len(extract_state_dict(obj)), 'tensors')
"
```

Loading `vint.pth`/`gnm.pth` **executes pickled code**. `navfm.models.loader`
requires an explicit `trust_checkpoint=True` and supports SHA-256 pinning; record
the hash you used in your paper's artefact appendix.

---

## Stage 2 — Datasets

### The fast path

Start with **GO Stanford**, and only GO Stanford, until the whole pipeline runs
end to end. It is the only public dataset **already in GNM format** —
verified by reading the ZIP central directory:
`go_stanford/<traj>/N.jpg`.

* [huggingface.co/datasets/franciszzj/GoStanford2](https://huggingface.co/datasets/franciszzj/GoStanford2) — 781.7 MB, single `go_stanford.zip`
* Mirror of the Drive file `1BVGA46WbvOZFyuzkzV2n_yZqcQsdIJy7` (745 MB)
* License: inherits GO Stanford's CC BY-NC-SA 3.0 — **non-commercial**

### The rest

| Dataset | Where | Size | Format | License |
|---|---|---|---|---|
| RECON | `rail.eecs.berkeley.edu/datasets/recon-navigation/recon_dataset.tar.gz` | **53.2 GB** (exact: 53 235 196 027 B) | HDF5 → `process_recon.py` | MIT |
| SACSoN / HuRoN | `rail.eecs.berkeley.edu/datasets/huron/` | ~40 GB, 576 `.bag` files across 26 sessions | ROS 1 bags → `process_bags.py -d sacson` | MIT |
| SCAND | TDR `doi:10.18738/T8/0PRYRH` | ~400 GB | ROS 1 bags | **CC0** |
| TartanDrive | `github.com/castacks/tartan_drive` (or the three `franciszzj/TartanDrive_*` HF mirrors, 2.70 TB total) | ~2.3 TB | ROS 1 bags | MIT |
| CoryHall | only via Open X-Embodiment: `lerobot/berkeley_gnm_cory_hall` | 0.09–1.5 GB | LeRobot parquet, **7 331 episodes / 156 012 frames @ 5 fps, images 64×86** | Apache-2.0 |

Corrections to the shipped configs, both verified:

* **`scand` is marked "private" in the configs and is actually public CC0.** The
  comment is stale.
* **`cory_hall` is *active* (uncommented) in all three training configs** but
  has no public link in the README, so `python train.py -c config/vint.yaml`
  dies on a missing directory. `scripts/patch_upstream.py` comments it out.
* Every config uses `/home/<username>/…` placeholder paths.

`konpat/huron-sacson-hdf5` on HF (1.0 GB, 2 955 trajectories, 224×224 JPEG in
HDF5) ships `data_splits/*/traj_names.txt` and a `data_config.yaml`, i.e. it was
produced by a completed GNM preprocessing run. Not drop-in, but it saves the
entire SACSoN rosbag extraction. No license stated — **UNVERIFIED**, check
before publishing on it.

Preprocessed GNM-format RECON, SCAND, TartanDrive or CoryHall **do not exist**
anywhere I could find. Budget the preprocessing.

---

## Stage 3 — Reproduce the published evaluation (offline)

Full closed-loop reproduction needs the physical robots. Offline reproduction of
the *training metrics* is what you can actually do, and it is what validates
your pipeline.

```bash
# 1. Splits (deterministic, unlike upstream's unseeded random.shuffle)
python -m navfm.splits /data/go_stanford --name go_stanford \
    --out third_party/visualnav-transformer/train/vint_train/data/data_splits \
    --split 0.8 --group-by none

# 2. Evaluate the released checkpoint on the held-out split
python -m navfm.eval.offline --model vint --checkpoint checkpoints/vint.pth \
    --dataset go_stanford --split test --batch-size 400
```

**Use `--batch-size 400`, not 1.** Upstream issue #51 reports action cosine
similarity dropping 0.96 → 0.5 when the eval batch goes from 400 to 1. The
metrics are batch-size dependent (BatchNorm/GroupNorm statistics, plus
`action_reduce`'s `mask.mean()` term). Any number you report must state its
batch size.

The seven metrics upstream logs, and which our `navfm.eval.metrics` mirrors:
`uc_action_loss`, `uc_action_waypts_cos_sim`, `uc_multi_action_waypts_cos_sim`,
`gc_dist_loss`, `gc_action_loss`, `gc_action_waypts_cos_sim`,
`gc_multi_action_waypts_cos_sim` (`uc` = goal-masked, `gc` = goal-conditioned;
NoMaD only). ViNT/GNM log `dist_loss`, `action_loss`,
`action_waypts_cos_sim`, `multi_action_waypts_cos_sim`,
`action_orien_cos_sim`, `multi_action_orien_cos_sim`.

**Acceptance criterion for "the pipeline is correct":** the released `vint.pth`
evaluated on a GO Stanford test split should reproduce a total test loss in the
neighbourhood of the checkpoint's own recorded `avg_total_test_loss = 0.17398`
— that value was computed over the full training mixture, so it will not match
exactly on a single dataset, but an order-of-magnitude disagreement means
something is wrong with your normalisation constants.

---

## Stage 4 — Collect in Isaac Sim

See `docs/ISAAC_COLLECTION.md`. Summary:

```bash
source .venv-isaac/bin/activate
python -m navfm.isaac.collect --config configs/collect/m3pro_indoor.yaml \
    --out /data/isaac_m3pro --robot-usd assets/m3pro.usd --episodes 600
```

---

## Stage 5 — Validate before you train

Non-negotiable. This step costs 30 seconds and has saved multi-day runs.

```bash
source .venv-train/bin/activate

python -m navfm.validate /data/isaac_m3pro --model vint --decode-images --workers 8 -v
# -> PASS, plus the metric_waypoint_spacing estimate

python -m navfm.stats /data/isaac_m3pro --name isaac_m3pro --len-traj-pred 5 --context-size 5
# -> metric_waypoint_spacing, empirical action_stats, and the fraction of
#    deltas that the published action_stats would clip

python scripts/register_dataset.py third_party/visualnav-transformer \
    --name isaac_m3pro --spacing <value from above> \
    --camera-height 0.28 --camera-x-offset 0.16 --hfov 64
# -> prints the dataset_index renumbering this causes

python -m navfm.splits /data/isaac_m3pro --name isaac_m3pro \
    --out third_party/visualnav-transformer/train/vint_train/data/data_splits \
    --split 0.8 --group-by scene
```

`--group-by scene` holds out **whole environments**. A random split over
trajectories from the same four USD scenes measures memorisation of those
scenes, not generalisation, and a reviewer will say so.

---

## Stage 6 — Fine-tune

```bash
python -m navfm.train.run --config configs/train/vint_finetune_4080s.yaml
```

Recipe rationale is in `docs/METHODOLOGY.md` §2.6 and §6. The short version:
LR 1e-4, AdamW, no warmup, **full** fine-tuning (frozen-encoder ViNT collapses
0.82 → 0.32 in the paper's own Table 8), effective batch 256 via 64 × 4
accumulation, BatchNorm frozen, bf16.

Watch for: validation loss *rising* during epoch 1 is the BatchNorm-drift
signature — confirm `freeze_bn: true` took effect.

---

## Stage 7 — Evaluate

Offline (`navfm.eval.metrics`) and closed-loop in held-out Isaac scenes.
Report both, with bootstrap CIs (`navfm.eval.metrics.bootstrap_ci`) — the
original papers report point estimates with no trial counts, so a bare point
estimate is not comparable to anything.

---

## Known-issue index

Consolidated from the reference repo's 52 issues, with the resolution:

| Issue | Symptom | Resolution |
|---|---|---|
| #36 | `EMAModel.__init__() missing 'parameters'`; `no attribute averaged_model`; `cannot import cached_download` | pin `diffusers==0.11.1` + `huggingface_hub==0.25.2` |
| #27 | torch 2.4.0 breaks training; `Aborted (core dumped)` | torch 2.3.1, or ≥2.6 with the weights_only patch; `opencv-python-headless`; delete stale `*.lmdb` |
| #43 | training stops with a Qt error | `MPLBACKEND=Agg`, `image_log_freq: 0` |
| #30 | `Failed to load image` on RECON | `data_folder` must be the post-`process_recon.py` directory |
| #54 | `No module named vint_train.models.gnm.gnm` | you skipped `pip install -e train/` |
| #55 | `No module named diffusion_policy` | clone `real-stanford/diffusion_policy` via **HTTPS** (README's SSH URL fails) |
| #47 | `conda env create` fails | the `cudatoolkit=10` + `python=3.8.5` + rospypi combination is unsatisfiable; use the venv recipe above |
| #10 | NoMaD weights cannot be loaded to resume training | `nomad.pth` is a bare state_dict; use `load_state_dict(..., strict=False)` and skip the optimizer path. The maintainer's promised fine-tuning config was never shipped |
| #51 | eval cosine similarity 0.96 → 0.5 at batch size 1 | evaluate at batch 400; report the batch size |
| #45, #64, #67 | how were `action_stats` derived? | never answered; use `navfm.stats` |

Undocumented pitfalls found by reading the code:

* `vint_dataset.py:158` opens LMDB with `map_size=2**40` (1 TiB) — fails on
  filesystems without sparse allocation.
* The cached sampling index filename does **not** include a dataset content
  hash, so adding or removing trajectories silently reuses a stale index. Delete
  `dataset_dist_*.pkl` and `dataset_*.lmdb` whenever the data changes.
* `train/train.py:299` calls `latest_checkpoint["optimizer"].state_dict()`,
  expecting a pickled optimizer *object*. Resume works only from checkpoints
  this repo wrote — and, on torch ≥ 2.6, only with the weights_only patch.
* `data_config.yaml` defines `carla_intvns` twice (last wins).
