# Native adaptation v1: GNM seed 0

The single authorized GNM seed-0 run completed **4,720 updates, PASS**. Freeze: `e94b6968b1d958a7254ac2ca8da42ba1c4d7a686`; [frozen protocol](NATIVE_MULTI_SEED_ADAPTATION_V1.md). No other slot ran. This is one exploratory adaptation run, not multi-seed evidence, generalization or navigation qualification.

## Completion and budget

- Fresh released GNM initialization SHA256 `4b03e0255f8a547290d4079f4e7d610ff69987122f17e019bd36684c08b3ee95`; no smoke weights used.
- 4,720 complete optimizer/scheduler transactions, finite gradients and updated model states; actual optimizer/scheduler readbacks 1–4,720. All 326 changed parameter tensors are counted against fresh release. EMA is not used by GNM.
- Strict released, resume and raw deployment reloads passed. All five checkpoint evaluations completed under the development model/optimizer/statistics/RNG fence. Four fixed development pairs contain only **two action-valid pairs** for common five-waypoint metrics.
- Worker wall time 359.261511 seconds; occupied launcher wall time 362.562550 seconds (6.043 minutes), under the unchanged 3,600-second reservation. CUDA kernel-active time was not independently measured. Child reaped and shared pre/post integrity PASS.
- All 19 ledger-bound artifact hashes verified. The registry consumes exactly GNM seed 0's 3,600-second reservation; five slots remain NOT RUN, with 18,000 seconds of worst-case reservations remaining. No retry, extension or other process was launched.

## Development selection and measured curve

The frozen rule selects **update 236** by the lowest finite native development objective. It does not select the best ADE/FDE or the final update after observing outcomes. Latest exact tie was not needed. Selected and final raw weights are distinct.

| Weights / update | Native development loss | Distance MAE [steps] | Common ADE [m] | Common FDE [m] |
|---|---:|---:|---:|---:|
| Released baseline | 0.557271 | 7.283866 | 0.042461 | 0.074594 |
| **236 — selected** | **0.315521** | 7.400471 | 0.020165 | 0.041750 |
| 472 | 0.350012 | 7.290827 | 0.025986 | 0.055849 |
| 1,180 | 0.316322 | 6.553899 | 0.022255 | 0.041900 |
| 2,360 | 0.329218 | 7.296216 | 0.014757 | 0.016746 |
| 4,720 — final | 0.520861 | 7.663227 | 0.015511 | 0.024863 |

The selected checkpoint improves the measured native objective and two-pair ADE/FDE over release, while distance MAE worsens. Final weights have better ADE/FDE than the selected weights, but worse native objective and distance MAE; the selection rule remains unchanged. Every evaluation uses the same exposed development pairs, RNG909 and five physical waypoints at 0.049994826316833496 m spacing. Repeated evaluation of two eligible pairs is not independent replication or evidence on unseen layouts. No physical-plant, stopping, collision or navigation result follows these offline metrics.

## Exposure and integrity

Measured training exposure: 18,880 optimizer-sample draws, 1,704 unique catalog pairs, 852 unique anchors, 1,210 unique RGB endpoints and 9,445 negative-pair draws. Repeated draws and overlapping histories do not become independent examples. Catalog identity is `6ea55dc8f11d6cbcec9377287714e5f7850a9717a93eb4d2644f6573f415dc21`. Only the admitted training split supplied optimizer data; the frozen development pairs supplied evaluation only.

The journal contains 4,720 BACKWARD_FINITE, 4,720 OPTIMIZER_APPLIED, 9,440 SCHEDULER_APPLIED and 4,720 COMPLETE records. The GNM no-EMA branch records the same scheduler phase twice; these are two observations of each single scheduler application, not 9,440 scheduler updates. Chronological COMPLETE records and actual counters attest exactly 4,720 updates. Selected dependency objects were 1,231 before / 1,356 after; generic native file records 2,241 / 3,749; upstream objects 4 / 16. These counts describe different import phases, not a constant namespace population.

External evidence root: `/home/favl/navfm-training-evidence/native-multiseed-v1-gnm-seed0-01/`. Catalog, per-batch endpoint/tensor hashes, transaction journal, checkpoint curves, raw/resume weights, process log and provenance remain external. `result-integrity.json` records the final hash/accounting audit.

| Artifact | SHA256 |
|---|---|
| Ledger | `cd986e12954a9ba3a31ef31174d34b530de263f15fb6776c07bf9e940f2363d5` |
| Report | `f4bfe4874f5259b3e09cf86f2179e825890da10c69320f03b1a0bb42fb2d2917` |
| Selected raw weights, `gnm/update_00236/deployment_weights.pth` | `98a7996e90d5ebce7aca9c247cd7b49a601a84b5347e2877449b0fa294d8f9bc` |
| Final raw weights, `gnm/deployment_weights.pth` | `9e638997eee4d6341dfaf2fce0133e69c6896e89530474e7296f951638328368` |

Validation: exact frozen source/input/sampler/budget and fresh-output preflight PASS; actual complete-transaction ordering/counters, selection recomputation, strict reload/fence completion and 19 artifact hashes PASS. The preparation's seven focused tests and Ruff were not rerun for this result-only document. All old freezes/failures remain immutable.

Next decision: whether to explicitly admit the next named slot, NoMaD seed 0, using the reviewed original source freeze and remaining registry budget. No further training is started by this report.
