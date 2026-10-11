# Native adaptation v1: GNM seed 22

The single authorized GNM seed-22 run completed **4,720 updates, PASS** from unchanged freeze `e94b6968b1d958a7254ac2ca8da42ba1c4d7a686`; [protocol](NATIVE_MULTI_SEED_ADAPTATION_V1.md). Only this slot ran in this milestone; NoMaD22 remains NOT RUN. No aggregate or best-seed selection is made.

## Completion and frozen selection

Fresh released GNM SHA256 `4b03e0255f8a547290d4079f4e7d610ff69987122f17e019bd36684c08b3ee95` supplied initialization, never smoke or prior adapted weights. All 4,720 optimizer/scheduler transactions completed with finite gradients and updated states; actual counters are 1–4,720. There are 326 changed parameter tensors versus release; GNM uses no EMA. Strict released, resume and raw deployment reloads PASS; all five checkpoint and before/after development evaluations completed under the model/optimizer/statistics/RNG fence.

Worker wall time 352.426034 seconds; occupied launcher time 355.689952 seconds, below the 3,600-second reservation. CUDA kernel-active time is unmeasured. Child reaped and shared pre/post integrity PASS. Five consumed slots reserve 18,000 seconds; the unlaunched NoMaD22 slot retains 3,600 seconds. No retry, extension or other worker.

The lowest finite native development objective selects **update2,360**; neither final weights nor an observed best seed replaces the frozen rule. Four fixed exposed pairs contain only two action-valid pairs for common five-waypoint metrics at spacing 0.049994826316833496 m, evaluation RNG909.

| Weights / update | Native development loss | Distance MAE [steps] | Common ADE [m] | Common FDE [m] |
|---|---:|---:|---:|---:|
| Released | 0.557271 | 7.283866 | 0.042461 | 0.074594 |
| 236 | 0.290997 | 6.923385 | 0.015735 | 0.033805 |
| 472 | 0.318729 | 7.005713 | 0.020901 | 0.047155 |
| 1180 | 0.255470 | 6.234461 | 0.020029 | 0.044960 |
| 2360 — selected | 0.186919 | 5.563858 | 0.009663 | 0.022515 |
| 4720 — final | 0.341897 | 6.654975 | 0.022287 | 0.035380 |

Selected and final quantities improve over release on these repeatedly exposed pairs; selected values are lower than final values. This is exploratory development evidence only, not generalization, unseen-layout results, model superiority or navigation qualification. No multi-seed conclusion is selected in this per-slot report.

## Exposure and artifact identities

18,880 optimizer-sample draws covered 1,704 unique catalog pairs, 852 anchors, 1,210 unique RGB endpoints and 9,438 negative draws. Repeated draws and overlapping histories are not independent examples. Only the admitted training split supplied optimizer data; development supplied evaluation only.

Journal counts: 4,720 BACKWARD_FINITE, 4,720 OPTIMIZER_APPLIED, 9,440 SCHEDULER_APPLIED and 4,720 COMPLETE. Duplicate no-EMA scheduler observations do not denote additional applications; actual scheduler counters attest 4,720.

External root: `/home/favl/navfm-training-evidence/native-multiseed-v1-gnm-seed22-01/`. All 19 ledger artifact hashes verified; `result-integrity.json` preserves accounting. Raw deployment weights are distinct from resume containers with raw model/optimizer/scheduler/RNG/sampler continuation. Logs, checkpoints, catalogs, tensor hashes and dense provenance remain external.

| Artifact | SHA256 |
|---|---|
| Ledger | `47c90b86b07dc10128d755735e4a68b9ef91119907eb3455527aee16418d4031` |
| Report | `8c2c45842b6c9424a9ec9a8659b1adc2ed12091517a723b65ed564afc4b09cc6` |
| Selected raw `gnm/update_02360/deployment_weights.pth` | `defa26edab0660135041f282bc0a3a243690ce7e92c510ea48ed5288aea9344e` |
| Selected resume `gnm/update_02360/resume.pth` | `9f415ae3e2ffc912adcfa105982c27f36497cc1a26d2588c738d1a9cac4fec00` |
| Final raw `gnm/deployment_weights.pth` | `f6db16e7dcb454da05175a7b05664288c89b070f8fa2be515d3407d81a416ea1` |
| Final resume `gnm/resume.pth` | `aa37d3c68fade632a8754b292ede88818836e5ddae6025b9f487aa89e58e355f` |

Validation: exact frozen source/input/dependency/sampler/budget/registry/fresh-output preflight; chronological complete transaction and counter audit; selection recomputation; strict reload/development fence completion; all 19 artifact hashes PASS. The canonical source ran detached at the original freeze; newer report branch was restored after reaping. Preparation tests/Ruff were not rerun for this result-only document. All original freezes/failures remain immutable.

Next decision: explicit admission of NoMaD seed22 under the unchanged freeze and remaining reservation. No additional run follows this report.
