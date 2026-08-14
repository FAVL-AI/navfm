# Render-validity matrix

Three independent contracts, read from three different artefacts. A cell is
`NO EVIDENCE` when its source did not measure it — never blank, never a pass.

```
dependency resolver   "the files exist"
        !=
Isaac runtime         "materials resolve, compile and bind"
        !=
rendered observable   "the scene is visually valid"
```

Collapsing these into one implementation produced FL-018: a repair verified by
the same enumeration that discovered the defect, reporting complete while the
rendered output did not move.

| Metric | control_world | hospital_A_original | hospital_C_321 | warehouse_B_repaired |
|---|---|---|---|---|
| background fraction | 0.3295 | 0.0 | 0.0 | NO EVIDENCE |
| structure fraction | 0.2565 | 0.53 | 0.53 | NO EVIDENCE |
| floor fraction | 0.4139 | 0.47 | 0.47 | NO EVIDENCE |
| median forward depth (m) | 1.647 | 8.99 | 8.99 | NO EVIDENCE |
| dominant hue fraction | NO EVIDENCE | NO EVIDENCE | 0.9628 | NO EVIDENCE |
| distinct colour bins | NO EVIDENCE | NO EVIDENCE | 29 | NO EVIDENCE |
| saturated pixel fraction | NO EVIDENCE | NO EVIDENCE | 1.0 | NO EVIDENCE |
| render verdict | PASS | PASS | FAIL | NO EVIDENCE |
| MDL modules required | NO EVIDENCE | NO EVIDENCE | 69 | 13 |
| MDL modules present | NO EVIDENCE | NO EVIDENCE | 69 | 0 |
| textures required | NO EVIDENCE | NO EVIDENCE | 252 | 73 |
| textures present | NO EVIDENCE | NO EVIDENCE | 252 | 0 |
| dependency closure | NO EVIDENCE | NO EVIDENCE | True | False |
| runtime MDL errors | NO EVIDENCE | NO EVIDENCE | NO EVIDENCE | NO EVIDENCE |
| materials compiled | NO EVIDENCE | NO EVIDENCE | NO EVIDENCE | NO EVIDENCE |
| visible meshes unbound | NO EVIDENCE | NO EVIDENCE | NO EVIDENCE | NO EVIDENCE |
| fallback materials | NO EVIDENCE | NO EVIDENCE | NO EVIDENCE | NO EVIDENCE |
| **render digest (sha256/16)** | `4c5a2886db6b0018` | `2e19baee888b0458` | `a16caf174bdf9211` | `ABSENT` |

## Causal history, preserved

The sequence is recorded as it happened rather than tidied. That STATE A and
STATE B produced materially identical output is first-class evidence, not an
embarrassment to smooth over: an unchanged observable after a repair claimed
causal is evidence against the repair until something else explains it.

| State | Dependency count by the resolver of the day | Closure flag | Observable |
|---|---|---|---|
| A — original mirror | 10 MDL, 20 textures (old walk) | `closure_complete: true` | hue-collapsed |
| B — first repair | 30/30 fetched, same walk | `FULL_RENDER_CLOSURE: true` | **materially identical to A** |
| C — corrected walk | 69 MDL, 252 textures | `FULL_RENDER_CLOSURE: true` | see matrix |

**Evidence gap, stated plainly.** STATE B's rendered image was deleted during a
pre-commit cleanup before this comparison was designed, so its pixel digest is
unrecoverable — the intermediate mirror state no longer exists to re-render from.
Its metrics survive in `camera_view_hospital_v1_repaired.json` and are identical
to STATE A on background, floor, structure and forward depth. The
"unchanged observable" claim therefore rests on metric identity, not pixel
identity. Recorded rather than quietly downgraded.

## Negative controls

Two frames are retained permanently, and the validator must keep rejecting both
**for different reasons** — a validator that rejects them for the same generic
reason has lost the ability to tell the failure classes apart.

| Fixture | Must fail on |
|---|---|
| `views/control_blocks_v1/pov_00.png` | background fraction — unbounded void |
| `views/hospital_v1/pov_00.png` | dominant hue — material collapse |

Author: Frank Asante Van Laarhoven
