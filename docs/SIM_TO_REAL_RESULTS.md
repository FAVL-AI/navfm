# Sim-to-real engineering results and failures

Starting repository commit: `a3a6974`, branch `agent/engineering-recording`.
Hospital and admitted Option 1 dataset02 are preserved. No real robot actuation.
These results establish admitted-data and software/simulator integration. No
navigation superiority, safety guarantee or real-transfer claim is supported.

## Articulated control

All six final sampled cases passed the unchanged absolute gates in
[methods](SIM_TO_REAL_METHODS.md). The qualification applies to an analytic
sphere-wheel collision proxy, acceleration drives and a restricted sampled
command set, not the original cylinder asset or hardware. Pure turns translate
approximately0.12m over3s despite their linear-speed gate passing.

| Case | Requested v / w | Mean v / w | Wheel RMSE rad/s | Stop travel mm | Final residual v / w | Contact reports |
| --- | --- | --- | --- | --- | --- | --- |
| forward | 0.10 / 0.00 | 0.10016 / 0.00005 | 0.0051 | 0.914 | 0.000285 / 0.000821 | 0 |
| left | 0.00 / 0.40 | 0.03285 / 0.37420 | 0.0551 | 0.411 | 0.000114 / 0.001560 | 0 |
| right | 0.00 / -0.40 | 0.03197 / -0.41665 | 0.0673 | 0.419 | 0.000091 / 0.001828 | 0 |
| combined_left | 0.10 / 0.40 | 0.10656 / 0.40185 | 0.2225 | 1.204 | 0.000145 / 0.002164 | 0 |
| combined_right | 0.10 / -0.40 | 0.10324 / -0.45856 | 0.2378 | 1.253 | 0.000132 / 0.002175 | 0 |
| collision_positive | 0.10 / 0.00 | 0.01871 / 0.00015 | 0.0135 | 0.231 | 0.000105 / 0.000663 | 1316 |

Velocity readbacks were independently compared with finite-difference pose motion.
Across free tests mean differences were <=0.0022m/s and0.052rad/s; signed yaw
and forward displacement agree. The final positive control has one deliberate
contact episode with1,316 reports, versus0 reports in five free cases. Report
counts are correlated touch/persist events, not1,316 separate collisions.

## Three matched live pairs

All six completed episodes passed independent strict source/recording verification
and the fixed image screen:1,440frames and480inferences. Starts matched within
0.016mm/0.000016rad. Goal-image hashes, camera/controller/fixture/rates matched
exactly. Batched execution order and variable background load confound performance
interpretation. The 20s timeout is an engineering integration horizon.

| Arm | Route | Termination | Final goal error m | Actual path m | Input-access-to-command p95 ms | Max ms |
| --- | --- | --- | --- | --- | --- | --- |
| pretrained | s_bend_run_0000 | timeout | 1.3536 | 1.9703 | 24.86 | 345.36 |
| pretrained | junction_run_0000 | timeout | 0.6016 | 1.8802 | 22.59 | 27.52 |
| pretrained | junction_run_0001 | timeout | 0.8311 | 1.9098 | 35.57 | 77.30 |
| adapted | s_bend_run_0000 | timeout | 1.3037 | 1.9496 | 22.76 | 389.70 |
| adapted | junction_run_0000 | timeout | 0.6021 | 1.8795 | 23.64 | 33.44 |
| adapted | junction_run_0001 | timeout | 0.8384 | 1.9291 | 27.50 | 34.48 |

| Metric | Pretrained | Six-step adapted | Denominator / definition |
| --- | --- | --- | --- |
| Navigation success |0/3 |0/3 | collision-free latched stop and final settled position within0.5m |
| Arrival any frame |0/3 |0/3 | evaluation pose within0.5m |
| Correct stopping |0/3 |0/3 | stop decision within0.5m |
| Premature stopping |0/3 |0/3 | stop decision outside0.5m |
| Stop events |0 |0 | stopping precision undefined:0/0 |
| Collision episodes |0/3 |0/3 | reported nonfloor fixture contacts; positive control qualified |
| Mean success-weighted path efficiency |0 |0 | success-weighted Euclidean distance to goal region /max(distance,path) |
| Aggregate input-access-to-command p95 |30.14ms |25.46ms |240inferences per arm; cold start retained |
| >250ms policy deadlines |1/240 |1/240 | includes cold-start inference |
| Unusable image frames |0/720 |0/720 | fixed contrast/edge/extreme screen |

The timer includes RGB access/history copying, preprocessing, synchronized inference,
controller and first joint-target submission. Actual acquisition/exposure-to-access
queue age, hardware command transport/response, and measured safety-clearance duration
are missing observations. These numbers do not establish complete camera-to-motor
latency. Future instrumentation also records observed-frame-ready-to-command residence.
No latency improvement or learned navigation improvement is claimed.

Checkpoint identities:

- Released: `/home/favl/projects/navfm/checkpoints/vint.pth`, SHA256
  `155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f`.
- Six-step adapted: `/home/favl/navfm-training-evidence/option1-vint-20261007-04/smoke_weights.pth`, SHA256
  `d0f412e66ebe312d115503a46ed170193e92b91486a7f1eda5031dbafe57f01d`.
- Original dataset digest:
  `c8121cb2a56e5a99f1fde3978f6a6a6e75200492f8132f5d60ad13ef8436dc88`;
  admission file SHA256
  `549ec6ab1fcdf04fb7decf52e86e8db1b9c1c9b9c82156460fcbe056bdbd52a7`.

## Retained failures and limitations

| Attempt | Observed failure | Action / evidence boundary |
| --- | --- | --- |
| Articulated control01 |0.026m/s forward at0.2 request; turning near zero; wheel tracking failures; wall not reached | retained all6cases; does not validate collision reporting |
| Control02 | analytic cylinder replacement still fails | all6cases retained; collision-shape change alone insufficient |
| Control03 | acceleration drive alone still fails | all6cases retained; drive-only explanation unsupported |
| Control04 | sphere proxy restores forward and contact, but3turn cases fail | all6cases retained; not qualified full motion |
| Control05 | yaw calibration at0.2m/s combined motion fails both signs | all8cases retained; no acceptance relaxation |
| Control06 | reduced0.1m/s sampled set passes | simplified proxy qualified only sampled commands; pure-turn drift remains |
| Expansion01 | source edited during execution | interrupted; provenance-invalid, excluded, all partial evidence retained |
| Expansion02 layout8_behavior1 | sensor194.98611692215007 vs capture195.00000581145287 | failed closed; no timestamp tolerance change; separately recollected03 |
| Live startup01 / adapter01 | missing RGBBaseline max_v parameter | zero completed episodes; exact startup failure saved; repaired |
| Live matched6episodes | all timeout, no arrivals or stops | preserve every episode; native learned stopping authority remains unavailable |
| Training subset6 flags | development-only still evaluated adapted engineering test | frozen source/outputs retained; corrected subsequent implementation; test not claimed untouched |
| Initial pytest |3UpstreamNotFound loader failures due omitted NAVFM_UPSTREAM | explicit existing pinned checkout repaired test invocation; no install/download |
| Live annotation | legacy sidecar says demonstration; R8substeps intent label stale | disclose; actual source/RGB policy manifests/rate readbacks establish execution; preserve records |

## Software-only deployment

Adapted saved-RGB replay passed20frames, exact official preprocessing tensor equality,
finite bounded commands and stale-frame rejection/zero sink. The command sink is a
local list. Pretrained replay and dry-run pulse are separately retained. ROS wrapper
syntax compiled. The unmeasured profile is rejected before ROS imports/publication.
ROS subscription/QoS/topic wiring and real camera, wheel mapping, watchdog, stopping
and timing remain unqualified. See [manual qualification commands](YAHBOOM_QUALIFICATION.md).

## Evidence and commands

External roots: `articulated-control-20261007-01` through`-06`,
`option1-live-pretrained-20261007-02`, `option1-live-adapted-20261007-01`,
`option1-live-matched-20261007-01.json`, `option1-live-rgb-review-20261007-01.png`,
`option1-expansion-20261007-01` through`-03`, beneath
`/home/favl/navfm-runtime-evidence`. Exact collector/trainer source snapshots are
under `/home/favl/navfm-execution-snapshots/sim2real-20261007`. Git contains code,
protocols and curated results only, no generated image/log/weight/corpus artifacts.

```bash
OMNICLIENT_HUB_MODE=disabled /home/favl/miniforge3/envs/isaac/bin/python  scripts/qualify_articulated_control.py --bounded-policy-envelope  --analytic-colliders --sphere-wheels --acceleration-drive  --yaw-gain 1.5 --mixed-yaw-gain 0.8  --robot /home/favl/projects/navfm/assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd  --out /home/favl/navfm-runtime-evidence/articulated-control-next

.venv/bin/python scripts/summarize_option1_live.py  --pretrained /home/favl/navfm-runtime-evidence/option1-live-pretrained-20261007-02  --adapted /home/favl/navfm-runtime-evidence/option1-live-adapted-20261007-01  --out /home/favl/navfm-runtime-evidence/option1-live-matched-next.json
```

## Expanded admitted corpus and two-point learning curve

The original corpus remains unchanged. A new admitted corpus contains35trajectories:
31training and the original2development/2test trajectories. It has4,341raw frames,
1,439processed frames at4Hz and1,089pairs accepted by both official loader variants
(945train,83development,61test). There are25new training trajectories in5new partition
layouts. The normalized waypoint unit remains0.049994826316833496m.

Admission is35/39candidates(89.74%) across the completed lineage collections:
three original rejected attempts and one new stale-frame failure are retained.
The expansion itself is25/26(96.15%), counting the repaired recollection. The separate
provenance-invalid batch01 had2completed episodes and an interrupted next episode;
it is excluded as an entire invalid batch and is not hidden in that denominator.
Original development/test image, label, processing, name-list, pair-ID and goal-flag
hashes match exactly. The new35trajectory corpus independently passed exact raw-to-
processed position/yaw/image/timestamp mapping.

Expanded corpus digest:
`7e2b3738c3026e9e170d1a635d3172e92767428ec577bdb85a9b64501f02cbc3`.
Admission SHA256:
`e7938615e2f9fc40f7f5f664b834c7c92127dc78005a129f850ddcef52e487f3`.
Path: `/home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01`.

All six training runs completed exactly20optimizer steps, finite losses/gradients,
292changed parameter tensors, strict saved-weight reload and exact reload predictions.
Each starts from the same released checkpoint with batch4/AdamW lr1e-5 and frozenBN.
The6trajectory subset is the original training data. The25subset includes those6plus
19new routes in4partition layouts; the remaining6training trajectories are admitted
but not used at that curve point. Development evaluation uses the same57valid action
pairs out of83. The engineering test is not claimed untouched; no real test data used.

| Training trajectories | Seed | Development ADE cm | FDE cm | Checkpoint SHA256 |
| --- | --- | --- | --- | --- |
| 6 | 0 | 4.6063 | 8.9022 | `324cde93793bd38a4b35c9eca7d9f34129eb550db0208fcdf7752059bf0a9b2f` |
| 6 | 11 | 4.5904 | 8.8993 | `6e515a734d061498158b8c71180124e1ff916a5a2f56fc4f53ad42c30ec96e00` |
| 6 | 22 | 4.5476 | 8.7540 | `10be6c2bcddc5db3a511ab76005b514f2ea896aafa2daf7d01c679baf593bcb4` |
| 25 | 0 | 4.5605 | 8.8157 | `1ee4c20ab42ee4f0d98a8c4912fcfa83f832269d0e4c28b3fe46beb16f837ec3` |
| 25 | 11 | 4.5423 | 8.7470 | `e648d04360f5c13bbc9b819e2cb2a95c876fe7e2c34b1bbba42636bc2cc7e201` |
| 25 | 22 | 4.5567 | 8.7809 | `6cd01970db378033e1fa4ebee12c8a0671e3747163784e35103a1fbbf9bbb95f` |

Mean/sampleSD development ADE:6trajectories4.5814/0.0304cm;
25trajectories4.5532/0.0096cm. Released ADE is4.8445cm on the same fixed development
pairs. These are tiny-budget offline feasibility measurements, not evidence that
more data causes navigation improvement. Size and layout diversity change together;
trajectory-correlated pairs and3seeds do not establish independent scene-level effects.
50/100/200trajectory curves and a substantial training budget have NOT RUN.

Measure further curves with declared update budgets, enough exposure to each corpus,
multiple seeds, and fixed development criteria before increasing scale mechanically.
Add new architectural classes (turns with genuine occlusion, rooms, branches),
calibrated camera/controller diversity and independent confirmatory scenes. Existing
partition corridors remain a narrow synthetic family. Real transfer is NOT RUN.

```bash
# Actual expanded admission command; use a new output to repeat.
NAVFM_UPSTREAM=/home/favl/projects/navfm/third_party/visualnav-transformer .venv/bin/python scripts/admit_option1.py \
 --collection /home/favl/navfm-runtime-evidence/option1-20261007-05 \
 --collection /home/favl/navfm-runtime-evidence/option1-20261007-06 \
 --collection /home/favl/navfm-runtime-evidence/option1-20261007-07 \
 --collection /home/favl/navfm-runtime-evidence/option1-expansion-20261007-02 \
 --collection /home/favl/navfm-runtime-evidence/option1-expansion-20261007-03 \
 --expected-trajectories 35 --spacing 0.049994826316833496 \
 --out /home/favl/navfm-runtime-evidence/option1-expanded-admitted-next

PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python scripts/train_option1_smoke.py \
 --steps 20 --seed 0 --development-only \
 --dataset /home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01 \
 --train-names /home/favl/navfm-training-evidence/option1-curve-subsets-20261007/n25.txt \
 --out /home/favl/navfm-training-evidence/option1-curve-n25-seed0-next

.venv/bin/python scripts/verify_option1_dataset.py --expected-trajectories 35 \
 --dataset /home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01
```

## Final instrumented matched repeat

The final repeat uses corrected live-policy sidecars, explicit consumed-field
annotations, eager preprocessing imports and a source guard that accepts new
imports but rejects modifications or disappearance of previously frozen sources.
Independent strict recording/source verification and all pair matching gates passed.
It retains observed-frame-ready-to-command timing, including intervening recording
and evaluation bookkeeping/residence. Earlier exposure/acquisition before that
observation and physical motor response are still outside the timing boundary.
Fixed goal PNGs are verified against raw collection05 and their original observed
capture times/source-manifest hashes and separate clock epoch are included in the
independent report. R3's unused local-capture time is disclosed, not rewritten.

| Arm | Route | Final error m | Path m | Frame-ready-to-command p95 ms | Max ms |
| --- | --- | --- | --- | --- | --- |
| pretrained | s_bend_run_0000 | 1.3189 | 1.9512 | 45.35 | 222.89 |
| pretrained | junction_run_0000 | 0.5469 | 1.8161 | 42.16 | 51.03 |
| pretrained | junction_run_0001 | 0.8022 | 1.9179 | 29.49 | 45.84 |
| adapted | s_bend_run_0000 | 1.3150 | 1.9492 | 45.71 | 222.67 |
| adapted | junction_run_0000 | 0.5545 | 1.8640 | 44.07 | 48.71 |
| adapted | junction_run_0001 | 0.8270 | 1.9052 | 37.25 | 46.28 |

Final aggregate frame-ready-to-command p95:41.28ms pretrained /43.80ms adapted,
240samples each. Both arms:0/3success,0/3arrival,0/3correct stopping,0/3premature
stopping,0stop events (precision undefined),0/3reported collision episodes,
0mean success-weighted efficiency,0/720unusable images and0/240missed250ms deadlines.
All6episodes time out. These are repeat engineering measurements on the same three
conditions, not additional independent test scenes or evidence of superiority.

Final roots: `option1-live-pretrained-20261007-04` and
`option1-live-adapted-20261007-03`. Report:
`/home/favl/navfm-runtime-evidence/option1-live-matched-20261007-02.json`.

Across comparative invocations,18episodes were attempted:14completed and4failed
closed on the source-list guard. The failed repeat loaded data_utils lazily after
its first episode, so the guard incorrectly treated a new dependency as changed
source. Both source lists and failed attempts are retained; preprocessing is now
loaded before attestation, and unit negative controls verify genuine changes still
fail. That initial episode omitted the crop module from its runtime list; the module
was already frozen in the admitted upstream source snapshot, and the limitation is
not hidden. The final list includes it.

There is also one completed12frame annotation/timing check, bringing total completed
live episodes to15(14comparison+1instrumentation). One separate startup failure
completed zero episodes. Metrics for the four aborted episodes are unavailable;
do not count them as collision-free successes. Failed recording attempts remain
in external directories and collection ledgers. The earlier6complete comparison
episodes and this final6complete repeat form6engineering pairs across only3unique
route/seed conditions. The guard-failed pairs are not valid comparisons.

The final targeted suite passed173tests, including loader, strict recording,
attestation default compatibility/consumed-field overrides, policy-sidecar retention,
source mutation/disappearance rejection, adapter timing failure controls and
kinematics. Ruff checks passed. No outputs, weights, logs or images are committed.
Real transfer, the original cylinder asset's tracking, ROS wiring, calibrated RGB
stopping and50/100/200data/training points remain unresolved or NOT RUN.
