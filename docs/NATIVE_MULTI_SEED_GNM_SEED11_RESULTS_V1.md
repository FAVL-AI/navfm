# Native adaptation v1: GNM seed 11

The single authorized GNM seed-11 run completed **4,720 updates, PASS** from unchanged freeze `e94b6968b1d958a7254ac2ca8da42ba1c4d7a686`; [protocol](NATIVE_MULTI_SEED_ADAPTATION_V1.md). Fresh released initialization, never smoke or previous adapted weights. Only this slot ran in this milestone.

## Completion and selection

All 4,720 optimizer/scheduler transactions completed with finite gradients and updated states; actual optimizer/scheduler counters are 1–4,720. There are 326 changed parameter tensors versus release; GNM uses no EMA. Strict released, resume and raw deployment reloads passed, with development model/optimizer/statistics/RNG fences at all five checkpoints. Child reaped and shared pre/post integrity PASS.

Worker wall time was 350.283950 seconds; occupied launcher time 353.558618 seconds, below the 3,600-second reservation. CUDA kernel-active time was not independently measured. Registry now contains three completed slots; NoMaD11, GNM22 and NoMaD22 remain NOT RUN, with 10,800 seconds of worst-case reservations remaining.

The frozen native development objective selects **update 1,180**, independently of final weights or best ADE/FDE. Four repeatedly exposed development pairs include only two action-valid pairs for common five-waypoint metrics; spacing is 0.049994826316833496 m and evaluation RNG909.

| Weights / update | Native dev loss | Distance MAE [steps] | Common ADE [m] | Common FDE [m] |
|---|---:|---:|---:|---:|
| Released | 0.557271 | 7.283866 | 0.042461 | 0.074594 |
| 236 | 0.360639 | 6.938435 | 0.037567 | 0.075837 |
| 472 | 0.253963 | 6.698555 | 0.018329 | 0.032126 |
| 1180 — selected | 0.165306 | 5.148582 | 0.013012 | 0.026758 |
| 2360 | 0.278329 | 5.750371 | 0.015924 | 0.023670 |
| 4720 — final | 0.360925 | 6.752186 | 0.026660 | 0.051939 |

Selected and final metrics improve over released values on this tiny exposed development set. The selected checkpoint has lower native objective, distance MAE and ADE/FDE than final weights; no selection rule changed. This is exploratory offline adaptation, not generalization, unseen-layout evidence or navigation qualification.

## Exposure and artifact identities

18,880 optimizer-sample draws covered 1,704 unique catalog pairs, 852 anchors, 1,210 RGB endpoints and 9,445 negative draws. Overlapping histories and repeated draws are not independent examples. Optimizer data was confined to the admitted training split; development supplied evaluation only.

The journal has 4,720 BACKWARD_FINITE, 4,720 OPTIMIZER_APPLIED, 9,440 SCHEDULER_APPLIED and 4,720 COMPLETE records. The no-EMA branch emits two observations of each scheduler application; actual scheduler counters attest 4,720 updates.

External evidence root: `/home/favl/navfm-training-evidence/native-multiseed-v1-gnm-seed11-01/`. All 19 ledger-bound artifact hashes verified; weights, resume state, logs, catalogs and dense provenance stay external. `result-integrity.json` records accounting checks. Resume containers include raw model/optimizer/scheduler/RNG continuation; deployment files contain raw GNM weights.

| Artifact | SHA256 |
|---|---|
| Ledger | `ee747966dcc047e6807da7af447124725a85c65967dbbe41ff9a3abe7276dde0` |
| Report | `178712f5f310c30ae0ff4f4e5f92b87acdeef079127418ea6a9a0e9ca6b666b1` |
| Selected raw `gnm/update_01180/deployment_weights.pth` | `666b298c23aafeed1ecb79edb4e5e4425ea2c566e4eeebf9c75ea13ac6f18a04` |
| Selected resume `gnm/update_01180/resume.pth` | `413077d666bc76d2d1d1eda8a7a9b3db12231660eecde9105251ef650614a1da` |
| Final raw `gnm/deployment_weights.pth` | `e3f9542421a82fe6670600d4a4689a41d42ef664d0f6fe0a494eeb7468063fbc` |
| Final resume `gnm/resume.pth` | `c8ef9618c06948ad3bc05f1f20365484df5a63ee86655d4b941bed06c9564ae3` |

Validation: exact frozen source/input/dependency/sampler/budget/fresh-output preflight PASS; transaction sequence, actual counters, finite gradients, selection recomputation, strict reload/fence completion and all 19 artifact hashes PASS. An initial accounting command used the nonexistent journal key `update`; correcting it to the saved schema key `step` completed the read-only audit, without another worker. Source preparation tests were not repeated for this result-only document. Original freezes/failures remain immutable.

Next decision: explicit admission of a remaining named slot under the unchanged freeze and registry budget. No retry, extension or additional training is launched by this report.
