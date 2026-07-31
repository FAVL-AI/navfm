# GNM, ViNT and NoMaD: derivation, mechanism, and exactly how to reproduce them

This document reconstructs the three models from their papers *and* from the
released source, and marks every place the two disagree. It is written to be
used, not admired: each section ends with the concrete quantity you must
reproduce and the file that computes it.

Source of truth for code claims: `robodhruv/visualnav-transformer` at commit
`dca79815b704e5aa9c6bdc3082351f9e3b2848c2` (2024-09-14, the current HEAD — the
repo has had no commits in ~22 months). Papers: [GNM
arXiv:2210.03370](https://arxiv.org/abs/2210.03370), [ViNT
arXiv:2306.14846](https://arxiv.org/abs/2306.14846) (CoRL 2023), [NoMaD
arXiv:2310.07896](https://arxiv.org/abs/2310.07896) (ICRA 2024).

Anything I could not verify is marked **UNVERIFIED** rather than smoothed over.

---

## 0. The one idea all three share

All three models solve the same problem in the same coordinates, and everything
else is a variation on it.

**Problem.** Given a short history of forward-facing RGB observations
`o_{t-P..t}` and a goal specification `g`, output (a) a temporal distance
`d(o_t, g)` — how many timesteps away the goal is — and (b) a sequence of
`H` future waypoints in the robot's body frame.

**Why this factorisation.** The distance head makes the model usable as an edge
cost in a topological graph: you can localise against a set of previously-seen
images by asking which is closest in *time*, and you can plan over the graph
with those costs. The waypoint head makes it a controller. One network, two
roles — a topological SLAM front-end and a local policy — which is what lets a
single 16 M-parameter model do kilometre-scale navigation.

**Why waypoints rather than velocities.** GNM's Table V settles this
empirically: on the LoCoBot, raw velocities score 0.73/0.54 (easy/moderate), raw
waypoints 0.42/0.26, and *normalised* waypoints 1.0/0.95. Velocities are
robot-specific (a Warthog's 5 m/s and a TurtleBot's 0.5 m/s are different
actions with the same number). Un-normalised waypoints are dimensionally shared
but scale-mismatched. Normalised waypoints — divided by a per-robot constant —
are the only action space in which "go forward one step" means the same thing
on every platform. This is the single most important design decision in the
whole line of work, and it is the one your new dataset must get right.

**The normalisation constant.** In the paper it is `α`, "a robot-specific factor
corresponding to the top speed of the robot". In the code it is
`metric_waypoint_spacing × waypoint_spacing`, the mean metres travelled between
recorded frames (`vint_dataset.py:268-270`). These are the same quantity under
a fixed frame rate: `metres/frame = top_speed / frame_rate`. The code's version
is the operational one, and `navfm.stats` derives it from data.

> **Reproduce this:** `navfm.kinematics.compute_actions` is a line-by-line
> reimplementation of `ViNT_Dataset._compute_actions`.
> `tests/test_upstream_compat.py::test_our_action_labels_match_the_reference_dataset`
> asserts agreement to `1e-10` against the actual upstream class.

---

## 1. GNM — *A General Navigation Model to Drive Any Robot*

### 1.1 What the paper set out to show

That a single policy trained on heterogeneous data from many robots
outperforms a policy trained on any one of them, *including on that one's own
platform*, and transfers zero-shot to robots absent from training. It is a
scaling claim about embodiment diversity, made before "foundation model" was
the framing.

### 1.2 Method, step by step

**Step 1 — Aggregate.** Six-to-nine datasets (the paper's Table I lists nine
rows summing to 70 h; the abstract says "60 hours from 6 distinct robots" —
these do not reconcile, and the GNM-Large mix is therefore **UNVERIFIED**).
Platforms: TurtleBot2, Jackal, RC car, Spot, Warthog, ATV. Speeds 0.5–10 m/s.

**Step 2 — Convert everything to one format.** Folder per trajectory,
`{t}.jpg` + `traj_data.pkl` containing `position (T,2)` and `yaw (T,)`. This
format is the actual unit of interoperability in the whole line of work, and it
is what §5 of this document specifies for your Isaac Sim data.

**Step 3 — Normalise the action space.** Waypoints in the body frame at time
`t`, divided by the platform's metres-per-frame. Yaw is kept as a raw radian
delta and is **not** normalised — a discrepancy with the paper's claim that
"the temporal distance `d̃` is also estimated in this normalized scale", which
the code does not do either (distance labels are raw integer timesteps).

**Step 4 — Infer embodiment from observations, not from a spec sheet.** The
paper's key trick: rather than conditioning on hand-written robot parameters,
condition on the last `k = 5` frames. Motion parallax across those frames
encodes camera height, speed and turning radius implicitly. In code this is
literally just channel-stacking the context —
`MobileNetEncoder(num_images=1+context_size)` with an 18-channel stem
(`gnm.py:29`). There is **no separate embodiment vector anywhere in the code.**

**Step 5 — Train two heads jointly.** Distance regression + waypoint
regression, both ℓ2.

### 1.3 Architecture (from code, which is more specific than the paper)

```
obs (6 frames, 85x64)  --channel-stack-->  18ch  --MobileNetV2--> 1280 --Linear--> 1024
obs+goal               --channel-stack-->  21ch  --MobileNetV2--> 1280 --MLP-->    1024
                                     concat 2048 --> 256 --> 32
                                                    /            \
                                          dist: Linear(32,1)   action: Linear(32, 5*4)
```

MobileNetV2 is the torchvision architecture with a widened stem
(`modified_mobilenetv2.py`), `width_mult=1.0`, Kaiming init — **not** ImageNet
pretrained, and it cannot be, because the stem takes 18 or 21 channels.

`action_pred[:,:,:2] = cumsum(deltas)`; `action_pred[:,:,2:] = normalize(...)`
so the `(cos ψ, sin ψ)` pair is unit-norm.

### 1.4 Loss

The paper gives no equation ("we train the two heads jointly using an ℓ2
regression loss"). The code is authoritative (`train_utils._compute_losses`):

```
L = α · 1e-2 · MSE(d̂, d) + (1 − α) · action_reduce( MSE(â, a) )
```

with `α = 0.5`, so effective weights `0.005 · L_dist + 0.5 · L_action`, i.e. a
distance:action ratio of `0.01` — which is exactly ViNT's published `λ = 0.01`.

`action_reduce` is **not** a mean:

```python
while loss.dim() > 1: loss = loss.mean(dim=-1)
return (loss * action_mask).mean() / (action_mask.mean() + 1e-2)
```

The `+1e-2` is a divide-by-zero guard that also scales every reported value by
`p/(p+0.01)`. Reproduced in `navfm.eval.metrics.action_reduce`, with
`strict=False` to turn it off.

When `learn_angle` is set, `_compute_losses` additionally logs
`action_orien_cos_sim` and `multi_action_orien_cos_sim`. **These are the same
number** (finding F12). Both architectures L2-normalise the predicted heading
columns before returning (`vint.py:135–137`, `gnm.py:85–87`) and the labels are
unit-norm from `calculate_sin_cos`; for unit vectors, the mean per-waypoint
cosine `(1/T)Σₖ pₖ·lₖ` equals the flattened cosine `(Σₖ pₖ·lₖ)/(√T·√T)`. The
`xy` pair is not redundant — those columns are cumulative sums. Both are stored
in `metrics.json`; report one.

### 1.5 Training

| | Paper | `train/config/gnm.yaml` |
|---|---|---|
| Batch | 400–1200 (multi-GPU) | 400 |
| LR | 5e-4 | **7e-4** |
| Optimizer | Adam | Adam, betas (0.9, 0.98) |
| Epochs | not stated | 30 |
| Context | 5 | 5 |
| Horizon | 5 | 5 |
| Action dist range | — | 2 → 10 |

### 1.6 Headline results (exact)

Table II, one policy across four robots (mean progress toward goal): GNM-Mid
scores 0.96 / 0.99 / 0.93 / 0.94 on LoCoBot / Tello quadrotor / Vizbot / Jackal,
versus 0.26 / 0.21 / 0.51 / 0.31 for a GoStanford-only policy.

Table V design-space ablation on LoCoBot (easy / moderate): action space —
velocities 0.73/0.54, waypoints 0.42/0.26, **normalised waypoints 1.0/0.95**;
context — none 1.0/0.79, static 1.0/0.86, **temporal 1.0/0.92**.

Trial counts are not reported. Any comparison against these numbers needs its
own confidence intervals; `navfm.eval.metrics.bootstrap_ci` provides them.

---

## 2. ViNT — *A Foundation Model for Visual Navigation*

### 2.1 What changed relative to GNM

Three things, in order of impact:

1. **The goal becomes a single replaceable token.** GNM fuses the goal into the
   observation encoder by channel-stacking, so goal information is smeared
   through the whole network and cannot be swapped out. ViNT gives the goal its
   own encoder producing exactly one token in a transformer sequence. Swap that
   token's producer and you have a GPS-conditioned or command-conditioned
   policy, with everything else frozen. This is the mechanism behind the paper's
   "adaptation to new modalities".
2. **Transformer over per-frame tokens instead of channel-stacking.** Each of
   the `P+1 = 6` observations is encoded independently, so the model sees
   *frames*, not a 18-channel tensor, and attention over them replaces
   convolution across them.
3. **Scale.** 80 h actually used out of 160 h collected (Table 7), 8+
   platforms.

Table 5 states the justification for (1) directly: late fusion gives good
adaptation but poor performance; early fusion the reverse; FiLM/RT-1-style
conditioning poor performance, good adaptation; ViNT's separate-encoder-single-
token design gets both.

### 2.2 Architecture, precisely

```
obs_img [B, 18, 64, 85]                       # 6 frames x 3ch, oldest first
  split(3,dim=1) -> cat(dim=0) -> [(6B),3,64,85]
  EfficientNet-B0 (in_channels=3)  ->  [(6B),1280]  -> Linear(1280,512)
  reshape -> [B, 6, 512]

goal fusion:  cat([obs_img[:, 15:18], goal_img], dim=1)  # ONLY o_t, not the context
  EfficientNet-B0 (in_channels=6)  ->  [B,1280] -> Linear(1280,512) -> [B,1,512]

tokens = cat(obs_tokens, goal_token, dim=1)   # [B, 7, 512], goal LAST
  + fixed sinusoidal positional encoding (max_seq_len = P+2 = 7)

nn.TransformerEncoder(
    nn.TransformerEncoderLayer(d_model=512, nhead=4, dim_feedforward=2048,
                               activation="gelu", batch_first=True, norm_first=True),
    num_layers=4)                              # self-attention only, despite the
                                               # class being named MultiLayerDecoder

flatten [B, 3584] -> 512 -> 256 -> 128 -> 64 -> 32   (ReLU after every layer)
  dist:   Linear(32, 1)
  action: Linear(32, 20) -> [B, 5, 4]
```

31 M parameters (paper Table 6).

Two code facts that contradict the configs:

* `vint.yaml` comments `obs_encoder: "efficientnet-b0" # by default, this is
  imagenet pretrained`. It is not. `vint.py` calls
  `EfficientNet.from_name(...)`, which is random init;
  `from_pretrained` would be the pretrained path.
* Paper Table 4 lists the encoder output as `[1, 1000]` (the classifier width);
  the code uses `1280` (the pre-classifier feature width). Trust the code.

### 2.3 Loss

Paper Eq. (1):

```
L = E[ log p(â | f(ψ(o)_{t:t−P}, φ(o_t, o_s))) + λ log p(d | f(·)) ],   λ = 0.01
```

The code's Gaussian-NLL ⇒ MSE realisation is byte-identical to GNM's
(`α = 0.5` giving effective `λ = 0.01`). Same `action_reduce`, same `1e-2`
distance scaling.

### 2.4 Training hyperparameters — the paper and the repo disagree

| | Paper Table 6 | `train/config/vint.yaml` |
|---|---|---|
| Batch | **300** | **256** |
| Epochs | **30** | **100** |
| LR | 5e-4 | 5e-4 |
| Optimizer | AdamW | AdamW (default wd 0.01, not the paper's 0.001) |
| Warmup | 4 epochs | 4 epochs |
| Scheduler | cosine, "period 10" | `CosineAnnealingLR(T_max=epochs=100)` — the period-10 setting is ignored |
| Context P | 5 | 5 |
| Horizon H | 5 | 5 |
| Image | 85 × 64 | 85 × 64 |
| Compute | 8 × V100, 30 h | single GPU |

Reproducing "ViNT" therefore requires choosing which ViNT. The released
`vint.pth` is `epoch=29` (`avg_total_test_loss=0.17398`), i.e. it matches the
**paper's** 30 epochs, not the config's 100. Reproduce the paper.

### 2.5 The exploration system (this is not in the repo)

ViNT's undirected exploration uses an **image**-diffusion subgoal generator: a
318 M-parameter, 128×128 conditional diffusion model `g(o_s | o_t)` trained on
future observations 5–20 steps ahead, sampled with DDIM (η = 0, 200 steps,
guidance 1.0). At inference it proposes `K` candidate subgoal *images*; ViNT
scores each by `f(s) = d_M(o_t, s⁻) + d_pred(s⁻, s) + h(s, G, C)` where `h` is
`0` for coverage, `‖s − G‖` for GPS, or a learned CNN for satellite guidance.

**None of this is in `robodhruv/visualnav-transformer`.** `deployment/src/explore.py`
implements NoMaD (action-space diffusion), not ViNT's image diffusion. If your
work needs ViNT's exploration behaviour you must reimplement the subgoal
generator; if it needs *an* exploration behaviour, NoMaD is the released one and
is 15× smaller.

### 2.6 Downstream adaptation — the part your project is actually doing

The paper's own fine-tuning recipe, verbatim in effect:

* **Full fine-tuning**, all weights, **LR 1e-4, 5 epochs, AdamW, no warmup, no
  scheduler**, no replay of pretraining data.
* Data: 181 trajectories (~4 h) in CARLA Town 01, 52 (~1 h) in Town 02.
* Result: zero-shot 0.40 → **0.82** success with <1 h of target data, beating a
  specialist trained on 5× more data.
* **Frozen encoder is not viable**: ViNT-FE scores 0.32 vs full ViNT 0.82 on
  image goals (Table 8). Fine-tune the encoder.

Modality swap (GPS, turn-by-turn): replace `φ(o_t, o_s)` with a small MLP
`φ̃` producing the same 512-d token; keep `ψ` and the transformer. GPS variant
uses a learned 3000-element tensor concatenated with ego-centric goal
coordinates through a 2-layer MLP, goals sampled 1.25–1.75 s ahead, LR 1e-4,
cosine with 4 warmup epochs.

`configs/train/vint_finetune_4080s.yaml` implements this recipe at 16 GB.

### 2.7 Headline results (exact)

Zero-shot cross-embodiment, maximum displacement (m) without intervention:

| | LoCoBot | Go 1 | Vizbot | Jackal |
|---|---|---|---|---|
| Single-robot | 40 | 12 | 40 | 184 |
| GNM | 60 | 8 | 20 | 427 |
| **ViNT** | **120** | **45** | **110** | **438** |

Exploration success: ViNT 0.94 indoor / 1.00 outdoor, vs BC 0.72/0.44, RECON
0.19/0.23. Kilometre-scale goal-directed with GPS heuristic: 0.95 success, 0.84
SPL, 1270 m, vs ViKiNG 0.64/0.42/720 m.

CARLA adaptation (images / positions / routing success): ViNT
0.82 / 0.89 / 0.72; scratch 0.45 / 0.79 / 0.43; GNM 0.49 / 0.45 / 0.49;
VC-1 0.19 / 0.49 / 0.38.

---

## 3. NoMaD — *Goal Masked Diffusion Policies*

### 3.1 The problem it solves

ViNT needs two systems: a goal-conditioned policy, and a separate 318 M-parameter
image-diffusion model to invent subgoals when there is no goal. NoMaD collapses
both into one 19 M-parameter network by making "no goal" a *masking* operation
and modelling the resulting multimodal action distribution with a diffusion head
rather than a point estimate.

The reason a point estimate fails without a goal is worth stating: at a
corridor junction with no goal, the set of good actions is bimodal (left or
right). An ℓ2 regressor trained on both modes predicts their mean — straight
into the wall. Table III's "Masked ViNT" row (50 % success, 1.0 collisions) is
that failure measured.

### 3.2 Method, step by step

**Step 1 — Goal masking.** Same ViNT encoder stack, but with a per-sample binary
mask `m ~ Bernoulli(0.5)` implemented as a `src_key_padding_mask` over the
`P+2 = 5` token sequence. `m = 1` excludes the goal token from attention →
undirected behaviour. `m = 0` → goal-conditioned. One set of weights, two modes.

The pooling renormalisation is the fiddly part
(`nomad_vint.py:64-69, 113-128`): tokens are *mean*-pooled to a single 256-d
`c_t`, so masking one of five slots requires scaling the remaining four by
`5/4` to keep the mean correct.

**Step 2 — Diffusion action head.** `ConditionalUnet1D` from
`real-stanford/diffusion_policy` (`input_dim=2`, `global_cond_dim=256`,
`down_dims=[64,128,256]`, `cond_predict_scale=False` → **bias-only FiLM**, not
scale+shift). DDPM, `num_train_timesteps=10`, `beta_schedule='squaredcos_cap_v2'`,
`prediction_type='epsilon'`, `clip_sample=True`.

Ten denoising steps is unusually few, and it is what makes the whole thing run
inside a 250 ms control period on a Jetson.

**Step 3 — Predict deltas, not waypoints.** `get_delta` first-differences the
normalised waypoints; the U-Net models per-step displacement. This keeps the
target distribution stationary along the horizon and bounded, which is required
because `clip_sample=True` clamps to `[-1, 1]` at every step. Absolute waypoints
would grow linearly with horizon index and be clipped away.

**Step 4 — Normalise to `[-1, 1]` with fixed global constants.**
`action_stats: min [-2.5, -4], max [5, 4]` in units of
`metric_waypoint_spacing`. The asymmetry in `dx` (`-2.5` to `5`) encodes that
reversing is rare. These constants are dataset-mixture-specific and *nobody has
ever published their derivation* — three open upstream issues (#45, #64, #67)
ask and none was answered. `navfm.stats.estimate_action_stats` derives them
from your data and reports what fraction the published range would clip.

### 3.3 Loss

Paper Eq. (2):

```
L = MSE(ε^k, ε_θ(c_t, a^0 + ε^k, k)) + λ · MSE(d(o_t, o_g), f_d(c_t)),  λ = 1e-4
```

Code uses convex weights `α·L_dist + (1−α)·L_diff` with `α = 1e-4`, i.e.
`λ_eff = α/(1−α) = 1.0001e-4`. Numerically irrelevant, but it is not literally
Eq. (2).

**A bug you must reproduce to match the checkpoint.** The per-sample goal-mask
gating of `dist_loss` is a no-op: `F.mse_loss(..., reduction='mean')` already
returns a **scalar**, so multiplying it by the `(B,)` vector `(1 − m)` and
taking `.mean()` yields `scalar × mean(1−m)`, then dividing by
`1e-2 + mean(1−m)` gives `≈ 0.98 × scalar` at `p_m = 0.5`. The distance head is
therefore trained on goal-masked samples too. Documented in
`navfm.eval.metrics`.

### 3.4 Training

| | Paper | `train/config/nomad.yaml` |
|---|---|---|
| Batch | 256 | 256 |
| LR | 1e-4 | 1e-4 |
| **Epochs** | **30** (baselines 20) | **100** |
| Context | — | 3 |
| Horizon | 8 | 8 |
| Image | — | 96 × 96 |
| Encoding | 256 | 256 |
| Diffusion steps | 10 | 10 |
| `learn_angle` | — | False (action dim 2) |

**EMA is the deployed model.** `EMAModel(model=model, power=0.75)`
(`train_eval_loop.py:197`), stepped every optimizer step, with decay
`1 − (1 + s)^(−0.75)` saturating at 0.9999 — there is no fixed decay constant.
All evaluation, visualisation and the released `nomad.pth` use
`ema_model.averaged_model`.

**A second bug:** `lr_scheduler.step()` is called twice per epoch in
`train_eval_loop_nomad` (lines 217 and 268), so `CosineAnnealingLR(T_max=100)`
completes its cosine at epoch 50 and then climbs back up.
`scripts/patch_upstream.py` removes the duplicate; decide deliberately whether
you want the fixed or the original schedule, and say which in your paper.

### 3.5 Deployment

`explore.py`: `mask = ones` (goal ignored), a *random* goal image is fed and
never used, 8 action samples drawn in parallel, 10 DDPM steps, waypoint index 2
of 8 taken, scaled by `max_v / rate = 0.2 / 4 = 0.05`.

**Critical gap:** candidate selection is literally `naction = naction[0]` with
the comment `# change this based on heuristic`. The paper's frontier-based
high-level planner is **not in the repo**. Any reproduction of NoMaD's
exploration numbers must supply this.

`navigate.py`: topological localisation over a `±radius = 4` node window using
the distance head, subgoal advance when `dist < close_threshold = 3`.

### 3.6 Headline results (exact)

Table I — exploration in unseen environments, navigation in known ones:

| Method | Params | Explore success | Collisions | Navigate success |
|---|---|---|---|---|
| Masked ViNT | 15 M | 50 % | 1.0 | 30 % |
| VIB | 6 M | 30 % | 4.0 | 15 % |
| Autoregressive | 19 M | 90 % | 2.0 | 60 % |
| Random Subgoals | 30 M | 70 % | 2.7 | 90 % |
| Subgoal Diffusion (ViNT) | 335 M | 77 % | 1.7 | 90 % |
| **NoMaD** | **19 M** | **98 %** | **0.2** | **90 %** |

Table III — encoder ablation (success / collisions): late-fusion CNN 52 %/3.2,
early-fusion CNN 68 %/1.5, ViT 32 %/2.5, **NoMaD 98 %/0.2**.

The paper reports **no latency measurements** — the efficiency claim is
parameter count plus a 4 Hz control loop, not a timing table. Do not cite a
NoMaD inference time; measure your own.

---

## 4. Choosing ViNT as the primary model — the argument

You asked to lean towards ViNT. That is the right call, and here is the defence
you can put in a paper:

1. **It is the only one of the three with a published, tested fine-tuning
   recipe and a quantified adaptation result** (CARLA, <1 h of data,
   0.40 → 0.82). GNM's paper has no fine-tuning experiment; NoMaD's released
   checkpoint is a bare state_dict that upstream's own resume path cannot load
   (upstream issue #10, unresolved, maintainer's promised "tested fine-tuning
   config" never shipped).
2. **Its failure modes are legible.** A regression head's error decomposes into
   ADE/FDE and cosine similarity per waypoint. A diffusion head's error requires
   sampling and gives you a distribution to characterise — more informative
   eventually, far more expensive to debug during a first sim2real study.
3. **Its adaptation interface is architectural, not incidental.** The
   single-goal-token design means a sim2real study can hold `ψ` and the
   transformer fixed and vary only the goal pathway, which is a clean
   experimental axis.
4. **Compute.** 31 M parameters, 85×64 inputs. A full fine-tune fits on a 16 GB
   card with room to spare (see §6). NoMaD adds a diffusion loop to every
   evaluation step, which roughly triples evaluation wall-clock.

NoMaD is still worth including as a second arm, for one specific reason: it is
the only released model that handles the *undirected* case, and undirected
behaviour is where simulation data has the largest comparative advantage (you
can generate unlimited novel environments). Treat it as the secondary
experiment, not the primary.

---

## 5. What "compatible with their pipeline" means, operationally

A dataset is compatible if and only if all of the following hold. Each is
checked by `python -m navfm.validate`.

| # | Constraint | Failure mode if violated |
|---|---|---|
| 1 | `<root>/<traj>/{0.jpg … T-1.jpg, traj_data.pkl}` | loader finds no trajectories |
| 2 | `traj_data.pkl` is a pickled dict with `position (T,2)` float and `yaw (T,)` float | `KeyError` in `_build_index` |
| 3 | `len(position) == number of jpgs` | `FileNotFoundError` inside a dataloader worker |
| 4 | image stems are unpadded integers `0..T-1` | `_load_image` builds `f"{time}.jpg"` and misses |
| 5 | `yaw` is **unwrapped** | `_compute_actions` does `yaw[1:] - yaw[0]` with no wrapping → spurious 2π in the labels |
| 6 | `T > context_size·s + len_traj_pred·s + end_slack` | trajectory silently contributes zero samples |
| 7 | dataset name registered in `data_config.yaml` with a correct `metric_waypoint_spacing` | assertion at construction; or silently wrong action scale |
| 8 | split files at `data_splits/<name>/{train,test}/traj_names.txt` | empty dataset |
| 9 | images are 4:3 (or accept the centre crop) | ~25 % of a 16:9 frame is discarded, so sim and real see different FOVs |

Constraint 5 is the one nobody catches. The reference preprocessing scripts do
**not** unwrap, so it is a latent bug in the original datasets too;
`navfm.writer.TrajectoryWriter` unwraps on close, and `navfm.validate` flags it.

Two config keys are **dead code** in the released dataset class and will not do
what their names suggest:

* `goals_per_obs` — assigned at `vint_dataset.py:99` and never read again.
  `go_stanford`'s `goals_per_obs: 2 # increase dataset size` has no effect;
  GO Stanford is *not* double-weighted in any released run.
* `negative_mining` — only used to append `-1` to a list that is never read
  afterwards. Negative sampling happens unconditionally, at rate
  `1/(max_goal_dist + 1) ≈ 1/21`.

If you report a dataset mixture, report it as the code actually samples it.

---

## 6. Reproducing on one RTX 4080 SUPER (16 GB)

**Feasible:** ViNT fine-tuning, ViNT evaluation, NoMaD fine-tuning, all offline
metrics, all Isaac Sim collection.

**Not feasible as published:** ViNT pretraining from scratch (8 × V100 for 30 h
≈ 240 V100-hours; a 4080 SUPER is roughly V100-class for this workload at bf16,
so ~10 days wall-clock single-GPU — possible but not a sensible use of the
card), and ViNT's 318 M-parameter subgoal diffusion model (trained on a v4-8 TPU
for 30 h).

**Memory arithmetic.** The dominant term is the EfficientNet-B0 tower applied to
`(P+1) × B` images. `navfm.train.finetune.estimate_activation_memory_gb` makes
this checkable before you launch:

| micro-batch | activations (bf16) | fits in 16 GB with ~0.5 GB fixed? |
|---|---|---|
| 32 | ~1.3 GB | yes, comfortably |
| 64 | ~2.6 GB | yes |
| 128 | ~5.3 GB | yes |
| 256 | ~10.5 GB | tight; fragmentation risk |

So the published batch of 256 is reachable directly, but 64 × 4 accumulation is
the safer configuration and — crucially — lets you freeze BatchNorm, which
small-batch fine-tuning needs anyway.

**Time.** With ~80 k samples from 600 Isaac episodes, 20 epochs at effective
batch 256 is ~6 250 optimizer steps. Empirically this class of model runs at
roughly 2–4 optimizer steps/s at micro-batch 64 on Ada-class hardware, so
**order 1–2 hours per fine-tuning run**. That is what makes a proper ablation
matrix (§ `docs/EXPERIMENTS.md`) affordable.

---

## 7. What is actually novel here, and how to defend it

Reproduction alone is not a publication. The defensible contributions of this
project are:

**C1 — A validated, open sim→GNM-format data pipeline.** The reference format
has never been specified in writing; it exists only as the behaviour of one
loader. This repo encodes it as machine-checkable constraints and proves
compatibility by loading generated data through the actual upstream class
(`tests/test_upstream_compat.py`). That is a reusable artefact, and the
"constraint 5" yaw bug is a genuine finding about the original datasets.

**C2 — Holonomic execution of a nonholonomically-trained navigation prior.**
Every platform in the GNM/ViNT/NoMaD training mix is differential-drive or
Ackermann. The M3 PRO is mecanum. The action space `(dx, dy, cos ψ, sin ψ)`
*admits* lateral motion but the training distribution has almost no mass there.
This gives a clean, previously-unasked question with a two-arm answer:
does the gain from executing waypoints holonomically outweigh the loss from
collecting demonstrations off the prior's support? `DemonstratorMode` and
`BaseKinematics` are separate knobs precisely so this is a 2×2, not a confound.

**C3 — Derived rather than inherited normalisation constants.** `action_stats`
and `metric_waypoint_spacing` are hard-coded in the reference repo with no
published derivation and three unanswered questions about them.
`navfm.stats` derives both and quantifies the clipping the published constants
impose on a new platform. This is a small but real methodological contribution
and it changes results measurably when the new platform's speed profile differs.

**C4 — Sim2real transfer curves at controlled data volumes.** ViNT's own
adaptation result is a single point (<1 h of CARLA data). A curve over
{0, 0.25, 1, 4, 16} hours of Isaac data, with and without pretraining-data
replay, on a real robot, is the experiment the original paper gestures at and
does not run.

Positioning: this is an *empirical systems and transfer* paper, not an
architecture paper. Venues that reward that framing: CoRL, ICRA, IROS, RA-L,
and the CoRL/NeurIPS datasets-and-benchmarks tracks. Do not claim a new model.

---

## 8. Open questions and honest limitations

* **The M3 PRO's mechanical parameters are unpublished.** Yahboom does not
  release wheelbase, track width, chassis dimensions, mass, or maximum
  velocities. Every such number in this repo is marked PROVISIONAL and must be
  replaced by measurement (`docs/HARDWARE.md` says how). A sim2real claim built
  on guessed dynamics is not a claim.
* **The camera is on the arm, not the chassis.** The physical DaBai DCW2 mounts
  to the DOFBOT-PRO, so its extrinsics depend on six joint angles. We lock the
  arm; that is a deviation from stock configuration and must be stated.
* **Nobody has publicly reproduced ViNT or NoMaD training from scratch.** I
  searched GitHub issues, the web, and Hugging Face and found no matching-metrics
  reproduction report. Treat published training curves as unvalidated.
* **`explore.py`'s missing planner** means NoMaD's 98 % exploration number is
  not reproducible from the released code alone.
* **Rolling shutter.** The real RGB sensor is rolling-shutter at 15 fps; Isaac
  Sim's RTX camera is effectively global-shutter. Under fast yaw this is a real,
  unmodelled appearance gap.
