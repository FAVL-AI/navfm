# Admitted training geometry audit v1

**Result: geometry audit passed within scope; calibration sufficiency is not established.** The audit used only the 31 training records admitted by the dataset bound to `da14a76ac0e33b7f364dcf7c18e818f7b14f73ee`. It did not read image contents, inspect development/pilot/evaluation records, or run an encoder, model, fit, or threshold selection.

## Frozen audit definition

For every admitted training trajectory, the population contains **all ordered pairs of distinct frame indices** `(query, goal)` from that same trajectory. Self-pairs and cross-trajectory pairs are excluded. For each pair, the external table retains trajectory, route, and scene identity; both frame indices and XY poses; continuous Euclidean distance in metres; and signed query-minus-goal heading difference wrapped to `[-pi, pi]` radians. No arrival radius or success label is assigned.

The runner verifies each training `traj_data.pkl` against its admission-manifest SHA-256 before restricted NumPy-only unpickling, requires exactly `position` and `yaw`, checks finite aligned arrays and contiguous image-index filenames without reading image bytes, then writes a CSV and compact JSON outside Git. Per-trajectory source hashes, admission hash, tool hash, and output hashes are retained with the external evidence.

## Measured coverage

| Quantity | Result |
|---|---:|
| Training trajectories / route IDs | 31 / 31 |
| Scene groups | 8 |
| Indexed frames | 1,255 |
| Ordered distinct within-trajectory pairs | 50,632 |
| Pair distance, min / p10 / median / p90 / max | 0.0000076 / 0.1015 / 0.5476 / 1.1846 / 1.7613 m |
| Wrapped heading difference, min / p10 / median / p90 / max | -1.7236 / -1.0109 / 0 / 1.0109 / 1.7236 rad |
| Output rows finite and tied to all 31 training identities | 50,632 / 50,632 |

All 31 per-trajectory distributions and all eight scene-level distributions are in the external JSON report. The five `partition_layout_5` through `_9` groups each contain five trajectories and 8,556 pairs; their median distances are approximately 0.551–0.555 m. The `left` and `right` groups each contain two trajectories and 2,666 pairs; `straight` contains two trajectories and 2,520 pairs. Pair counts are dependent observations, not independent samples. The close minima and lower-tail values show geometric proximity coverage in the records, but do not by themselves establish a sufficient number of independent near-goal examples for a future calibration protocol.

## Interpretation and boundary

The training partition supports constructing continuous **within-trajectory geometric proximity targets** after a goal-frame sampling rule is frozen. It does not establish successful arrival: these records do not supply timestamps, settling, collision-free completion, or physical STOP outcomes. It also cannot establish perceptual aliasing or visually confusing negative coverage; no images or descriptors were examined. No common coordinate alignment is assumed between trajectories.

Therefore, the result supports **further geometry-only calibration preparation**, but not calibration fitting or a sufficiency claim. A static proximity calibration would still need pinned visual features and a prospectively defined target rule. A temporal dwell latch needs authentic timing; successful stopping needs independent endpoint evidence. Do not substitute assumed frame rate or geometric proximity for either.

## Provenance and reproduction

Implementation and tests were committed at `66e9b0a`; the tool SHA-256 is `7b6e71cb8510fd618af5130cb26258d35db8b997f669ccbb273e91cf645869ef`. The dataset-content digest is `7e2b3738c3026e9e170d1a635d3172e92767428ec577bdb85a9b64501f02cbc3`; admission JSON SHA-256 is `e7938615e2f9fc40f7f5f664b834c7c92127dc78005a129f850ddcef52e487f3`.

```bash
PYTHONPATH=src python scripts/audit_arrival_training_geometry_v1.py \
  --admission /home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01/admission.json \
  --dataset-root /home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01/data/option1_m3pro \
  --out /home/favl/navfm-training-evidence/arrival-training-geometry-v1-rerun-01
```

The measured external output is `/home/favl/navfm-training-evidence/arrival-training-geometry-v1-01`: `training_geometry_pairs.csv` SHA-256 `f2c589a29f7c96535923db39440103ba490b11ed1f53d6b9fa444eebc40bc52c`; `report.json` SHA-256 `d410c603117f25c8bd091d453ea2237dcb1988b21e1876643e55130912a2c09c`. Neither derived table nor raw evidence is committed.

Focused synthetic validation: 8 tests passed, covering known distances, ordered identity preservation, angle wrapping, malformed shapes, and nonfinite rejection. Ruff lint and format checks passed. No collection, simulation, navigation, or actuation was run.
