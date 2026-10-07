# Executed Option 1 engineering results

Repository `/home/favl/projects/navfm-engineering-recording`, branch
`agent/engineering-recording`, starting at `9a28d761`. Hospital milestone
`e7633fe` is preserved. These are kinematic dataset and training engineering
checks, not publication evidence of navigation improvement or sim-to-real transfer.

## Dataset admission

**10 admitted / 13 attempted = 76.923%** in collection batches05–07.
Earlier controller/image qualification and startup failures are retained separately;
they are not silently folded into that denominator.

1,221 raw frames at12Hz simulation time and320x240;404 processed frames at4Hz.
Exactly aligned float64 `position[N,2]` and unwrapped `yaw[N]` map to source
JPEG indices2,5,8,... . Every admitted raw recording passed independent source,
image, pose, transition and timestamp verification. An independent processed
readback passed exact image/position/yaw/time mapping with unchanged1e-8 tolerance.

Both patched and pristine official ViNT loaders accepted10/10 admitted trajectories
and304/304 finite sample tuples each. Frozen scene/route-disjoint splits:

| Split | Trajectories | Processed frames | Frozen pairs | Action-valid pairs |
| --- | ---: | ---: | ---: | ---: |
| train | 6 | 220 | 160 | 104 |
| dev | 2 | 103 | 83 | 57 |
| test | 2 | 81 | 61 | 41 |

Normalization unit: **0.049994826316833496m**, median nonstationary processed
step distance from TRAIN only. This measured unit is stored in the isolated dataset
registry; action scaling must match it at inference. Acquisition and model image
resolution are distinct:320x240 records,85x64 official model input.

## Admitted trajectory coverage

| Route | Source batch | Raw frames | Processed frames | Travel (m) | Yaw range (deg) |
| --- | --- | ---: | ---: | ---: | ---: |
| straight_run_0000 | 05 | 108 | 36 | 1.666 | 0.0 |
| straight_run_0001 | 05 | 108 | 36 | 1.668 | 0.0 |
| left_run_0000 | 05 | 115 | 38 | 1.628 | 96.4 |
| s_bend_run_0000 | 05 | 161 | 53 | 2.296 | 82.9 |
| s_bend_run_0001 | 05 | 151 | 50 | 2.302 | 86.7 |
| junction_run_0000 | 05 | 127 | 42 | 1.961 | 42.4 |
| junction_run_0001 | 05 | 118 | 39 | 1.961 | 43.2 |
| right_run_0000 | 06 | 115 | 38 | 1.628 | 96.4 |
| right_run_0001 | 06 | 109 | 36 | 1.641 | 98.7 |
| left_run_0001 | 07 | 109 | 36 | 1.641 | 98.8 |

Five corridor variants cover straight, left/right turns, S-bends and branching
polylines; the junction label does not imply a modeled architectural junction.
Camera/mount are fixed, there is one static box per scene, and appearance is
primitive. This dataset lacks real imagery, dynamic obstacles, long routes,
U-turns and broad architectural diversity. No learning curves were run yet.

## Retained failure table

| Attempt | Observed failure / rejection | Repair |
| --- | --- | --- |
| Collection01 | Wheel turn request0.7rad/s;~0.27rad total yaw, timeout | Preserve/reject; control mapping not qualified |
| Collection02 | Body-velocity turn request0.7rad/s;~0.03rad total yaw, timeout | Use explicitly kinematic teacher for data engineering |
| Collection03 |11 plain-wall endpoint frames fail edge screen | Prospective USD wall/floor landmarks |
| Collection04 |Invalid SdfPath `Stripe-1_0`; no episodes ran | LegalL/R identifiers; durable setup-error record |
| Collection05 left_run_0001 | reported obstacle contact | Recollect with prospective lighting or obstacle repair |
| Collection05 right_run_0000 | 8 unusable images | Recollect with prospective lighting or obstacle repair |
| Collection05 right_run_0001 | 7 unusable images | Recollect with prospective lighting or obstacle repair |
| Training01 |MissingLMDB in simulator interpreter; environment probe imported another checkout | Select/guard source before probe; existing training environment |
| Training02 |`save_weights` arguments reversed; failure at checkpoint saving | Correct call; persist optimization metrics before saving |

One of13 candidate episodes reported obstacle contacts (37 headers, first type0
between `/World/Robot/base_link` and `/World/Fixture/Scene1/Obstacle`). Admitted
episodes reported0/10 contacts. These are teacher observations and a selection
criterion, not learned-policy collision performance. Detector sensitivity and
kinematic collision fidelity remain unqualified.

## Training and matched offline measurements

Successful runs03 and04 each executed six micro-batches/optimizer steps, batch4,
lr1e-5, full fine-tuning with frozen BatchNorm, bf16, seed17 and upstream objective.
Mean training total loss: **0.280078101**.
All individual objectives and gradients were finite;292 parameter tensors changed.
Weights were saved and strictly reloaded, with every tensor equal and exact
prediction equality after reload. The fresh-process repeat produced a byte-identical
checkpoint, not an independent training-seed replicate.

Pretrained SHA256:
`155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f`.
Adapted SHA256:
`d0f412e66ebe312d115503a46ed170193e92b91486a7f1eda5031dbafe57f01d`.

Training used project `.venv`,Torch2.11.0+cu128. The byte-identical run03 weights
also strictly loaded and produced finite RGB-only predictions in the simulator
interpreter,Torch2.7.0+cu128. Its reload record is retained under run03. No model
download or checkpoint substitution occurred; active loader/model source locations
point to the admitted private source snapshot.

| Population | ADE pretrained→adapted (m) | FDE pretrained→adapted (m) | Valid pairs / all pairs |
| --- | --- | --- | --- |
| dev | 0.048445→0.047733 | 0.092841→0.091466 | 57/83 |
| test | 0.059287→0.057956 | 0.115466→0.112753 | 41/61 |

Waypoints are evaluated at five future4Hz steps in the observation-local frame,
masked exactly as upstream; ADE is mean Euclidean error per valid pair in metres,
FDE is final-horizon error. Both arms use identical frozen RGB/goal pairs and
negative flags, and realised pairs match their manifest digests. Observations
within two trajectories per held-out split are correlated, not independent trials.

Test offline-loop p95 in run04: pretrained14.138ms;
adapted14.041ms (61 calls each). Bounds include
LMDB/label loading, preprocessing, inference, CPU metrics and CUDA synchronization.
This is not camera-to-motor full-loop latency; no latency improvement is inferred.

**Adapted-policy navigation success, correct/premature stopping, collision episodes
and real full-loop latency: NOT RUN.** Native stopping is absent. Small offline
error changes after six steps do not establish navigation improvement, transfer,
superiority to another framework, or formal safety.

## Artifacts, validation and next command

Admitted dataset: `/home/favl/navfm-runtime-evidence/option1-admitted-20261007-02`.
Canonical smoke: `/home/favl/navfm-training-evidence/option1-vint-20261007-04`; weights `smoke_weights.pth` and `training_report.json`.
Raw batches01–07, rejected attempts, partial recordings and source snapshots are
external. Review images `rgb_review_1.png`, `rgb_review_2.png` and measured
`trajectory_coverage.png` are in the admitted artifact directory and were inspected.
No generated data, caches, logs or weights are staged. Real test data is untouched.

Validation:144 targeted tests passed; Ruff and independent raw/processed checks
passed. Raw12Hz and processed4Hz tolerances were not relaxed. Matched live protocol
and camera/controller qualification checklist are prepared, but live comparisons
require turning-response and stopping qualification.

Next executable check from the repository:

```bash
.venv/bin/python scripts/verify_option1_dataset.py --dataset \
  /home/favl/navfm-runtime-evidence/option1-admitted-20261007-02
```

Collection expansion and nested25/50/100/200 trajectory learning-curve proposal
are in `OPTION1_TRAINING.md`. The proposed200 training demonstrations are a coverage
target, not a justified sufficient dataset size; scale must be revised using real
learning curves and matched navigation failures. New confirmatory and real test
routes remain separate from this engineering corpus.

The subsequent articulated-control,31training-trajectory expansion, three-seed6/25
learning curves, matched live checkpoint failures and deployment software checks are
reported in [sim-to-real results](SIM_TO_REAL_RESULTS.md). Original artifacts remain
unchanged; new evidence is separate.
