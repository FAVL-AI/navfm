# The model-ready dataset contract (Option 1) — frozen

This is the on-disk form every corpus must reach before it is admitted to
training or evaluation. It is the official VisualNav Transformer processed
structure, not a navfm invention, and it is frozen here so that "compatible
with the reference" is a checkable property rather than a claim.

## The contract

```text
<dataset_root>/
    <trajectory_name>/
        0.jpg
        1.jpg
        ...
        T.jpg
        traj_data.pkl
```

`traj_data.pkl` is a pickled mapping containing exactly two **required**
fields:

| Field | Type | Shape | Meaning |
|---|---|---|---|
| `position` | numerical NumPy array | `[T, 2]` | planar position per frame, metres |
| `yaw` | numerical NumPy array | `[T]` | heading per frame, radians, **unwrapped** |

"Numerical" is load-bearing and is the whole subject of finding F13: the arrays
must have a real floating dtype. An `object`-dtype array whose *elements* are
arrays satisfies neither the shape contract nor `torch.as_tensor`, which
rejects object dtype unconditionally.

Frame count and trajectory length correspond: image `t.jpg` is the observation
at `position[t]`, `yaw[t]`. The writer enforces this; nothing else may.

## What may NOT go in `traj_data.pkl`

Nothing else. The reference loader reads these two keys, and every extra key is
an invitation for a future reader to assume the reference consumes it.

## Provenance goes in `metadata.json`, beside it

```text
<trajectory_name>/metadata.json
```

Recommended fields, none of which the reference loader reads:

```text
trajectory_id      scene_id           camera_id          robot_id
controller_id      timestamps         source_format      source_digest
conversion_version split
```

This keeps the official training contract byte-for-byte unchanged while letting
this project carry the provenance its gates require — the split identity, the
scene grouping, the digest of the artefact a trajectory was derived from.

## Source formats are evidence, not inputs

RECON HDF5, ROS bags, and Isaac Sim records may be **retained as source
evidence**, hashed and archived. They are never read by training or evaluation.
Conversion into the structure above is a separate, recorded step with its own
`conversion_version`, and the converted corpus is a *derived* artefact.

**The original downloaded files are never modified in place.** A conversion that
overwrote its input would destroy the only thing able to falsify it.

## Consequences already recorded

* **F1** — yaw must be unwrapped on serialisation. The reference preprocessing
  does not unwrap, which is a latent label-corruption channel in the original
  corpora. `navfm.writer` unwraps; `navfm.validate` rejects wrapped
  trajectories. Never bypass the writer.
* **F13** — the released GO Stanford corpus does **not** satisfy this contract:
  all 3,696 trajectories store `position` and `yaw` as object-dtype arrays of
  arrays. That is the defect gate G0.c is currently stopped on, and the reason
  this contract is being written down rather than assumed.

## Status

**Frozen.** Changes to the two required fields, their shapes, or their dtypes
are protocol changes and require a dated pre-registration amendment, because
every downstream label, metric and gate is computed from them.
