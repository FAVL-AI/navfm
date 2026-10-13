# Native adaptation v1: NoMaD seed 11

The single authorized NoMaD seed-11 run completed **4,720 updates, PASS** from unchanged freeze `e94b6968b1d958a7254ac2ca8da42ba1c4d7a686`; [frozen protocol](NATIVE_MULTI_SEED_ADAPTATION_V1.md). Only this slot ran in this milestone. Earlier results and failures remain immutable.

## Completion and budget

Fresh released EMA SHA256 `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333` initialized raw parameters and shadows; no smoke or prior adapted state was used. Qualified EMA integration remained unchanged. All 4,720 complete optimizer/scheduler/EMA transactions have finite gradients, raw states and EMA shadows. Actual optimizer/scheduler/EMA readbacks are 1–4,720; final EMA counter 4,720. There are 628 changed parameter tensors versus release. Each of the five transaction phases occurs exactly 4,720 times.

Strict released, complete resume and EMA deployment reloads PASS; all five checkpoint and before/after development evaluations completed under the model/optimizer/EMA/statistics/RNG fence. Child reaped and shared pre/post integrity PASS. Worker wall time 597.329270 seconds; occupied launcher time 601.303644 seconds, below the 3,600-second reservation. CUDA kernel-active time is unmeasured. Four completed slots consume 14,400 seconds of worst-case reservations; GNM22 and NoMaD22 remain NOT RUN with 7,200 seconds remaining.

## Frozen development selection

The native development objective selects **update 236**, not final weights or best common ADE/FDE. Four fixed exposed pairs include only two action-valid pairs for common five-waypoint metrics at spacing 0.049994826316833496 m. Evaluation RNG909, goal masks `[0,0,0,0]` and native diffusion timesteps `[9,5,0,3]` remain fixed; no goal-masked development evaluation is claimed.

| EMA / update | Native development objective | Distance MAE [steps] | Common ADE [m] | Common FDE [m] |
|---|---:|---:|---:|---:|
| Released | 0.010168 | 7.221789 | 0.072812 | 0.131571 |
| 236 — selected | 0.006105 | 6.931286 | 0.029695 | 0.060538 |
| 472 | 0.006321 | 6.814610 | 0.031708 | 0.064724 |
| 1180 | 0.007069 | 6.656377 | 0.028131 | 0.059130 |
| 2360 | 0.006663 | 6.979745 | 0.041408 | 0.082223 |
| 4720 — final | 0.006837 | 7.049812 | 0.037907 | 0.075121 |

Selected and final quantities improve over release on these exposed pairs. Selected EMA has lower native objective, distance MAE and common ADE/FDE than final EMA; update1,180 has lower common ADE/FDE than selected but does not replace the frozen objective-based selection. Native eight-waypoint diffusion losses for release/selected/final are 0.003978/0.000775/0.001090; distance MSE is 61.901707/53.299595/57.471935. Native eight-waypoint ADE/FDE was not separately produced. This is exploratory development evidence only: no best-seed selection, aggregate multi-seed conclusion, generalization, model superiority or navigation qualification.

## Exposure and identities

Training exposure: 18,880 optimizer-sample draws, 1,704 unique catalog pairs, 852 anchors, 1,148 RGB endpoints and 9,445 negative-pair draws. Separately, native conditioning produced 9,544 goal-masked and 9,336 goal-conditioned draws; these masks differ from negative goal/action-validity labels. All 18,880 per-sample diffusion timestep assignments are reduced in external `result-integrity.json`. Repeated draws/history overlap are not independent examples.

External root: `/home/favl/navfm-training-evidence/native-multiseed-v1-nomad-seed11-01/`. All 19 ledger artifact hashes verified. Raw parameters/optimizer/scheduler/EMA/RNG/sampler continuation are in resume containers; deployment exports contain EMA weights, not raw parameters. All weights, logs, catalogs, tensor hashes and dense provenance remain external.

| Artifact | SHA256 |
|---|---|
| Ledger | `a40852261e3815513bb88447459b90a3746bd92fe8dbcb67202eaa1f44677a9b` |
| Report | `40cf24a6e6b2de73c5c4d5cd1e985bd4f68db0c8398b5cf368de80cf18b7ee92` |
| Selected EMA `nomad/update_00236/deployment_weights.pth` | `8bb36d3ca1f206bc93635f28358ef948370e462731d2b67b6e15416d6b7872d7` |
| Selected raw/resume + EMA state `nomad/update_00236/resume.pth` | `285b4855b34422b3d2e33c62cd3adf8a52f41b93a74b28949f40a8bccc77ae41` |
| Final EMA `nomad/deployment_weights.pth` | `afb053e359fcb0878765924b6a518c0974504591902f6f0b3adac37df3e3fb05` |
| Final raw/resume + EMA state `nomad/resume.pth` | `8043aba90b83983641ba861727aa06d07c60ce0ddd8aa2723359a175fdea5019` |

Validation: exact freeze/source/input/dependency/registry/fresh-output preflight; actual chronological COMPLETE counter/phase audit; frozen selection recomputation; strict reload and development fence completion; all 19 artifact hashes PASS. Canonical source ran detached at the original freeze; newer report branch was restored after reaping. Preparation tests/Ruff were not repeated for this result-only document. No source change, retry, extension or other worker.

Next decision: explicit admission of a remaining named seed22 slot under the unchanged freeze and registry budget. No additional run follows this report.
