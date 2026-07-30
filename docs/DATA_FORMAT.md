# The GNM / ViNT / NoMaD on-disk format — a written specification

There is no upstream specification of this format. It exists only as the
behaviour of `train/vint_train/data/vint_dataset.py`. This document is that
behaviour, written down. `navfm.schema` encodes it as executable constraints and
`navfm.validate` checks them.

## Layout

```
<dataset_root>/
  <trajectory_name>/
    0.jpg
    1.jpg
    ...
    <T-1>.jpg
    traj_data.pkl
```

and, separately,

```
<data_splits>/<dataset_name>/train/traj_names.txt
<data_splits>/<dataset_name>/test/traj_names.txt
```

`traj_names.txt` is one trajectory directory name per line. The loader also
writes its sampling index and an LMDB image cache **into the split directory**,
so the split directory must be writable and per-configuration.

## `traj_data.pkl`

A pickled `dict` with exactly two required keys.

| Key | Type | Shape | Units | Frame |
|---|---|---|---|---|
| `position` | float ndarray | `(T, 2)` | metres | fixed world/odometry frame, `(x, y)` |
| `yaw` | float ndarray | `(T,)`, or `(T, 1)` (squeezed by the loader) | radians | same frame, CCW from `+x` |

Extra keys are ignored by the loader. `navfm.writer` adds a `metadata` dict
(sim config, seed, episode index, robot config, randomisation draw) so any
trajectory can be regenerated.

## Constraints

| # | Constraint | Where it bites | Failure |
|---|---|---|---|
| 1 | `len(position) == number of .jpg files` | `_load_image` | `FileNotFoundError` inside a dataloader worker, mid-epoch |
| 2 | image stems are **unpadded** integers `0..T-1`, extension `.jpg` | `get_data_path` builds `f"{time}.jpg"` | silent miss; `007.jpg` and `0.png` are both invisible |
| 3 | `position` is `(T, 2)` float; `yaw` is `(T,)` or `(T,1)` float | `_build_index`, `_compute_actions` | `IndexError` / broadcasting nonsense |
| 4 | all values finite | training | NaN loss |
| 5 | **`yaw` must be unwrapped** | `_compute_actions` computes `yaw[1:] - yaw[0]` with no angle wrapping | a `2π` jump in the orientation labels at every branch-cut crossing |
| 6 | `T > context_size·s + len_traj_pred·s + end_slack` | `_build_index` | trajectory contributes zero samples and is dropped **silently** |
| 7 | dataset name registered in `data_config.yaml` | `__init__` assertion | `AssertionError`, or (worse, if registered with a wrong `metric_waypoint_spacing`) a silently wrong action scale |
| 8 | images are 4:3, or you accept the centre crop | `resize_and_aspect_crop` | ~25 % of a 16:9 frame discarded; sim and real see different FOVs |

Constraint 5 is the important one. The reference preprocessing scripts
(`process_bags.py`, `process_recon.py`) do **not** unwrap, so this is a latent
bug in the original datasets as well, not merely a trap for new ones.
`TrajectoryWriter` unwraps on close; `navfm.validate` reports it.

Minimum lengths for the shipped configs (`waypoint_spacing=1`, `end_slack=0`):

| Model | context | horizon | min `T` |
|---|---|---|---|
| GNM | 5 | 5 | 11 |
| ViNT | 5 | 5 | 11 |
| NoMaD | 3 | 8 | 12 |

## `data_config.yaml`

```yaml
action_stats:            # global; used ONLY by the NoMaD diffusion path
  min: [-2.5, -4]
  max: [5, 4]

<dataset_name>:
  metric_waypoint_spacing: 0.088    # metres per recorded frame
  camera_metrics:                   # optional, visualisation only
    camera_height: 0.28
    camera_x_offset: 0.16
    camera_matrix: {fx: ..., fy: ..., cx: ..., cy: ...}
    dist_coeffs:   {k1: ..., k2: ..., p1: ..., p2: ..., k3: ...}
```

`metric_waypoint_spacing` is the mean Euclidean distance between consecutive
frames. `_compute_actions` divides local-frame waypoints by
`metric_waypoint_spacing × waypoint_spacing`, so a normalised displacement of
1.0 means "one nominal inter-frame step for this platform". It is the code's
realisation of the GNM paper's per-robot factor `α`. Derive it with
`python -m navfm.stats`; never guess it.

`dataset_index`, returned in every batch, is the position of the dataset name in
the **sorted** key list. Adding a key renumbers every alphabetically later
dataset. `scripts/register_dataset.py` prints the renumbering.

Published values, for calibration: `cory_hall` 0.06, `go_stanford` 0.12,
`recon` 0.25, `sacson` 0.255, `seattle` 0.35, `scand`/`racer` 0.38,
`tartan_drive` 0.72, `carla_cil` 1.27, `carla_intvns` 1.39, `carla` 1.59.

## What a training sample looks like

`ViNT_Dataset.__getitem__` returns a **7-tuple** (the class docstring is stale
and describes 5 elements with wrong shapes). Shapes for ViNT
(`context_size=5`, `len_traj_pred=5`, `learn_angle=True`, `image_size=[85,64]`):

| # | Name | dtype | Shape |
|---|---|---|---|
| 0 | `obs_image` | float32 | `(18, 64, 85)` — `3·(context+1)` channels, oldest first |
| 1 | `goal_image` | float32 | `(3, 64, 85)` |
| 2 | `actions` | float32 | `(5, 4)` — `dx, dy, cos Δψ, sin Δψ` |
| 3 | `distance` | **int64** | scalar |
| 4 | `goal_pos` | float32 | `(2,)` |
| 5 | `dataset_index` | int64 | scalar |
| 6 | `action_mask` | float32 | scalar |

Note `image_size` in the configs is `(width, height)`, but the tensor is
`(C, H, W)`. Images are ImageNet-normalised in the training loop; **no data
augmentation of any kind is applied.**

## Dead config keys

Two keys do nothing in the released dataset class. Report your mixture as the
code actually samples it, not as the config implies.

* **`goals_per_obs`** — assigned at `vint_dataset.py:99`, never read again.
  `go_stanford`'s `goals_per_obs: 2 # increase dataset size` is inert; GO
  Stanford is not double-weighted in any released run.
* **`negative_mining`** — only appends `-1` to `distance_categories`, which is
  never read after `min_dist_cat`/`max_dist_cat` are taken. Negative goal
  sampling happens **unconditionally** at rate `1/(max_goal_dist + 1) ≈ 1/21`.

A negative sample sets `distance = max_dist_cat` (a saturated target the
distance head still regresses) and `action_mask = 0` (action loss fully masked).

## Writing the format

```python
from navfm.writer import TrajectoryWriter

with TrajectoryWriter(root / "office_a_run_00007", metadata={"scene": "office_a"}) as w:
    for frame in episode:
        w.append(frame.rgb, frame.position_xy, frame.yaw, sim_time=frame.t)
```

Crash-safe (staging directory + fsync + atomic rename, so an interrupted
collector never leaves a half-written trajectory that `data_split.py` would
index), streaming (no need to hold an episode in RAM), and format-exact (4:3
centre crop at write time, unpadded stems, yaw unwrapped on close).

## Checking the format

```bash
python -m navfm.validate /data/isaac_m3pro --model vint --decode-images --workers 8 -v
python -m navfm.stats    /data/isaac_m3pro --name isaac_m3pro --len-traj-pred 5 --context-size 5
python -m navfm.splits   /data/isaac_m3pro --name isaac_m3pro --out <data_splits> --group-by scene
```

The compatibility claim is not asserted, it is tested:
`tests/test_upstream_compat.py` writes a dataset with `TrajectoryWriter`, loads
it through the **actual** upstream `ViNT_Dataset`, and asserts that our
`compute_actions` matches its `_compute_actions` to `1e-10`.
