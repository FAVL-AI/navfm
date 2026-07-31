# Route-3 investigation: the released corpus, the released loader, and numpy's era

**Status: investigation only.** No patch applied, no classification made, no
population drawn. Conducted under the acquisition ruling: read-only pickle
inspection, upstream source reading, and the reference loader run against
`traj_data` alone. **No checkpoint was loaded. No model was constructed. No
metric was produced.** `vint.pth` remains unloaded at `155fd72de2e98ae0…`.

## Trigger

The pre-execution pass failed at `_compute_actions` → `to_local_coords` →
`yaw_rotmat`, before any population could be drawn.

## 1. The artefact's exact shape — uniform, not a subset

All **3,696** trajectories inspected, none unreadable.

| `(position.dtype, yaw.dtype)` | count | share |
|---|---|---|
| `('object', 'object')` | 3,696 | **100.0 %** |

By naming family: `no*` 2,656/2,656; `sim*` 1,040/1,040. **No subset, no family
correlation**, so the "selective exclusion" branch of the decision mapping is
excluded on the evidence — as it had to be, population integrity being frozen.

Concretely, elements are themselves arrays:

```
yaw[0]      = array([-2.16882408])
position[0] = array([-7.5279…, 3.1194…], dtype=object)
```

## 2. The exact failure site

`train/vint_train/data/data_utils.py:28`:

```python
def yaw_rotmat(yaw: float) -> np.ndarray:
    return np.array([[np.cos(yaw), -np.sin(yaw), 0.0],
                     [np.sin(yaw),  np.cos(yaw), 0.0],
                     [0.0, 0.0, 1.0]])
```

The signature declares `yaw: float`. Given a 1-element array, `np.cos(yaw)`
returns a 1-element array, so rows become `[array([x]), array([y]), 0.0]` — a
**ragged nested sequence**. The operation is `np.array()` construction over
inhomogeneous input, and the numpy behaviour it assumes is *implicit ragged
object-array creation*.

Called from `to_local_coords` (`data_utils.py:51`), reached from
`ViNT_Dataset._compute_actions` (`vint_dataset.py:278`).

## 3. Era dependency — **YES, and it inverts the situation**

Throwaway environment, numpy **1.23.5** (upstream's pinned era; clearly
labelled, not canonical, discarded after the test):

| Call | numpy 1.23.5 | numpy 2.x (canonical) |
|---|---|---|
| `yaw_rotmat(yaw[0])` | **constructs**, shape `(3,3)`, dtype `object`, `VisibleDeprecationWarning` | `ValueError: inhomogeneous shape` |
| `to_local_coords(pos, pos[0], yaw[0])` | **completes**, shape `(42,2)`, dtype `object`, first row `[array([0.]) array([0.])]` | raises |
| scalar-yaw control | shape `(3,3)`, dtype `float64` | same |

The values are correct — the first waypoint relative to itself is zero — but
they arrive **wrapped in 1-element arrays**, and the whole computation runs in
object dtype rather than `float64`.

So the corpus **is** readable under the reference implementation's
contemporaneous dependency semantics. Our failure is an **environment-fidelity
gap**, not an artefact defect. numpy 1.24 turned ragged array creation from a
`VisibleDeprecationWarning` into a `ValueError`; the reference was written
before that line moved.

## 4. Upstream's own emission path

`train/vint_train/process_data/process_data_utils.py:92`:

```python
return {"position": np.array(xys), "yaw": np.array(yaws)}
```

An unguarded `np.array()` over accumulated per-timestep values. If the source
yields 1-element sequences per timestep — as `process_recon.py:35`'s
`h5_f["jackal"]["yaw"][()]` may, depending on stored shape — this construction
emits exactly the observed structure under era-appropriate numpy, silently.

So the structure is **consistent with upstream's own pipeline**, not evidence
of foreign tooling. This does not establish that GO Stanford passed through
*this* pipeline — its lineage runs through Hirose et al. and `F-M2-3` records
that the corpus composition is undocumented — but it removes "no upstream code
could have produced this" from the table.

## Where the decision mapping lands

The declared mapping says: **(3) = YES → Route 1, reframed as era-fidelity
restoration.** A dtype coercion *restores* the reference's contemporaneous
behaviour rather than altering reference semantics.

Two qualifications the mapping did not anticipate, both material and neither
mine to resolve:

1. **Era-appropriate numpy does not produce clean floats.** It produces
   object-dtype arrays of 1-element arrays. A coercion patch would therefore
   not reproduce era behaviour exactly — it would produce `float64` where the
   era produced `object`. Whether downstream metrics are numerically identical
   across those two representations is **untested**, and it bears on what
   "restoration" means.
2. **The era path emits a `VisibleDeprecationWarning` on every trajectory.**
   The reference implementation was, on its own corpus, warning continuously
   that its behaviour was deprecated. That is a finding in itself.

Under the mapping this is Route 1 with an era-fidelity rationale, and it still
requires red-team adjudication under trigger 1 — a semantic change to a
load-bearing path — before any re-run. It is not self-cleared, and this
document does not clear it.
