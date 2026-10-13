# Expanded offline development: NoMaD v1

The single authorized NoMaD process completed **PASS** from freeze `69d1a204bbde0a6458dbd38fb4b515d7cf2aa07e`; [protocol](OFFLINE_NATIVE_EVALUATION_V1.md). Released plus three frozen selected EMA checkpoints were evaluated on 48 fixed pairs across four exposed routes, exactly four goal-conditioned DDPM draws per pair. No retries, checkpoint reselection, training, simulator, navigation or robot process.

## Completeness and metric scope

All **768 expected draws** were attempted, returned and finite; missing/invalid 0/768. All four strict loads and model-state fences PASS, with full native-file, selected-dependency and upstream pre/post/final provenance. Source/input postflight PASS; child reaped. Occupied launcher time **51.286935 seconds**, against 1,800 seconds reserved.

Every role uses 24 positive/action-valid and 24 negative/action-invalid pairs. Common ADE/FDE is expected per-draw error across all four fixed draws, then equal-pair mean over the 24 eligible positives; no oracle minimum, error of averaged trajectory or survivor-only mean. Positive distance MAE uses temporal-step labels; negative category MAE uses native artificial max category 20, not physical distance. Native NoMaD 96×96/context 3, eight-waypoint DDPM output and ACTION_STATS inverse/cumulative conversion remain unchanged; common errors use only the first five XY waypoints at 0.049994826316833496 m spacing. No native eight-waypoint ADE/FDE or masked-goal efficacy claim.

| EMA role / training seed | Positive ADE [m] | Positive FDE [m] | Positive distance MAE [steps] | Negative category MAE | Invalid / attempted |
|---|---:|---:|---:|---:|---|
| release / None | 0.075161 | 0.142658 | 3.908380 | 10.472987 | 0 / 192 |
| selected / 0 | 0.024118 | 0.043508 | 4.276734 | 5.565226 | 0 / 192 |
| selected / 11 | 0.024541 | 0.044362 | 3.762098 | 6.087703 | 0 / 192 |
| selected / 22 | 0.021716 | 0.038706 | 4.501001 | 5.079565 | 0 / 192 |

All selected EMAs lower overall waypoint errors and negative-category error relative to release on this exposed-development set. Positive temporal-step error is mixed: seeds 0 and 22 worsen; seed 11 improves. No best seed or post-evaluation checkpoint choice is made.

## Fixed per-trajectory outcomes

Each row averages four fixed draws per positive pair; routes contain 7/7/5/5 positives and the same number of negatives. Correlated anchors are not independent replications, and trajectory variation is distinct from training-seed variation.

| EMA role / training seed | Trajectory | Positive pairs | ADE [m] | FDE [m] | Positive distance MAE [steps] | Negative category MAE |
|---|---|---:|---:|---:|---:|---:|
| release / None | s_bend_run_0000 | 7 | 0.069483 | 0.132947 | 3.824131 | 11.749223 |
| release / None | s_bend_run_0001 | 7 | 0.076019 | 0.135128 | 3.964866 | 9.534395 |
| release / None | junction_run_0000 | 5 | 0.089270 | 0.172143 | 3.793415 | 13.220268 |
| release / None | junction_run_0001 | 5 | 0.067801 | 0.137311 | 4.062216 | 7.253004 |
| selected / 0 | s_bend_run_0000 | 7 | 0.025766 | 0.044925 | 4.115662 | 6.727294 |
| selected / 0 | s_bend_run_0001 | 7 | 0.029727 | 0.053353 | 5.139031 | 4.083505 |
| selected / 0 | junction_run_0000 | 5 | 0.015147 | 0.030263 | 3.852780 | 7.134512 |
| selected / 0 | junction_run_0001 | 5 | 0.022929 | 0.040987 | 3.718973 | 4.443453 |
| selected / 11 | s_bend_run_0000 | 7 | 0.025357 | 0.042720 | 4.723000 | 7.533624 |
| selected / 11 | s_bend_run_0001 | 7 | 0.028629 | 0.051683 | 5.003093 | 4.299112 |
| selected / 11 | junction_run_0000 | 5 | 0.018315 | 0.036219 | 2.624641 | 8.842400 |
| selected / 11 | junction_run_0001 | 5 | 0.023903 | 0.044556 | 1.816899 | 3.812745 |
| selected / 22 | s_bend_run_0000 | 7 | 0.026550 | 0.044884 | 4.263493 | 6.762520 |
| selected / 22 | s_bend_run_0001 | 7 | 0.021542 | 0.038413 | 4.923343 | 5.326567 |
| selected / 22 | junction_run_0000 | 5 | 0.013194 | 0.027037 | 4.676107 | 4.882374 |
| selected / 22 | junction_run_0001 | 5 | 0.023713 | 0.042138 | 4.067125 | 2.574814 |

## Timing and provenance

Batch 1 latency uses two unscored warmups per checkpoint and CUDA synchronization before/after each full ten-step DDPM sample. RNG setup is outside timing. Native wrapper latency **includes get_action inverse/decode CPU roundtrip and its transfers**; excludes model loading, disk/preprocessing, warmups and later metric CPU transfer. Separate preprocessing/hash-validated batch construction mean 16.843212 ms. All timed draws retained. Workstation timing is neither pure GPU kernel time nor Orin/ROS deployed latency.

| EMA role / training seed | Mean [ms] | Median [ms] | Range [ms] | Timed draws |
|---|---:|---:|---|---:|
| release / None | 24.364689 | 24.198361 | 23.327935–30.370189 | 192 |
| selected / 0 | 24.986021 | 24.871876 | 24.076633–26.422403 | 192 |
| selected / 11 | 25.395017 | 25.156004 | 24.397366–39.021486 | 192 |
| selected / 22 | 25.569572 | 25.355945 | 24.653679–43.479352 | 192 |

External root: `/home/favl/navfm-training-evidence/offline-native-evaluation-v1-nomad-01/`. Recorded per-draw metrics, pair/draw/role identities, batch hashes, logs and dense provenance remain external. The frozen worker did not persist raw predicted waypoint arrays; no later raw-trajectory inspection is claimed. All three ledger-bound artifacts rehashed.

| Artifact | SHA256 |
|---|---|
| Ledger | `ca8ea41e776c7ab5ad576d87508c4cbd4cfc089ad7583f184b4e2dba7d819fd5` |
| process.log | `d9cb391f575473dcb11f1b8137f5b9eacea14b46d956d1f5d73798f5f32256f7` |
| provenance.json | `2bc853ef485c3ac50aca93a9ce1a38fb9fb427a7e32dcf2c048dc0ebe3787906` |
| report.json | `e1d73f837ad6da92407f22964fbd0ed4a9a78ded61a83f34dbac3214fe25b770` |

| Loaded EMA role / seed | SHA256 |
|---|---|
| release / None | `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333` |
| selected / 0 | `7a6eaa288071a4925f25180385c4cf32430894e068017358d75528d7aaa89ba9` |
| selected / 11 | `8bb36d3ca1f206bc93635f28358ef948370e462731d2b67b6e15416d6b7872d7` |
| selected / 22 | `4d5e534ecd8056dde1679399702d20225b710811e6a326b5638fbf436e76c723` |

Validation: exact source/input/metadata/registry/fresh-output preflight; all 768 fixed identities and finite outputs; strict loads/state fences; full provenance/source postflight; three artifact hashes and exact-worker summary recomputation PASS. Newer GNM report branch was preserved and restored after reaping. Preparation tests were not rerun for this report-only publication. No source edits, retry or additional process.

Next decision: [bounded both-model consolidation](OFFLINE_NATIVE_CONSOLIDATED_RESULTS_V1.md). These already exposed routes do not establish generalization, stopping or navigation efficacy.
