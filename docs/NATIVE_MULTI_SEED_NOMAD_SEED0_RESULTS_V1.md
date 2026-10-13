# Native adaptation v1: NoMaD seed 0

The single authorized NoMaD seed-0 run completed **4,720 updates, PASS**, from freeze `e94b6968b1d958a7254ac2ca8da42ba1c4d7a686`. [Frozen protocol](NATIVE_MULTI_SEED_ADAPTATION_V1.md). No other run was launched in this milestone. GNM seed 0's prior [result](NATIVE_MULTI_SEED_GNM_SEED0_RESULTS_V1.md) is preserved; the four seed-11/22 slots remain NOT RUN.

## Completion and resources

Fresh released NoMaD EMA SHA256 `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333` initialized raw training parameters and initial EMA shadows. No smoke or prior partial weights were used. The authenticated v3 integration adapter and all frozen data/objective/controller exclusions remained unchanged.

There are 4,720 COMPLETE optimizer/scheduler/EMA transactions with finite gradients, raw model states and EMA shadows. Actual optimizer, scheduler and EMA readbacks are 1–4,720; final EMA counter 4,720. All 628 changed parameter tensors are counted against fresh release. Each of the five journal phases occurs 4,720 times. Strict released, complete resume and EMA deployment reloads PASS; all five checkpoint development evaluations and before/after evaluations completed under the model/optimizer/EMA/statistics/RNG fence.

Worker wall time is 592.702771 seconds; occupied launcher wall time 596.677612 seconds (9.945 minutes), below the unchanged 3,600-second reservation. CUDA kernel-active time is unmeasured. The child was reaped and shared pre/post integrity PASS. Both completed seed-0 slots consume 7,200 seconds of worst-case reservations; measured occupied wall sum is 959.240162 seconds. Four remaining slots retain 14,400 seconds of reservations. No retry or extension occurred.

## Frozen development selection

The finite **native development objective** selects update **236**, not the best common waypoint metric or the final update. No tie occurred. Development remains four fixed pairs, only **two action-valid pairs** for common ADE/FDE. All evaluations are goal-conditioned (`goal_masks=[0,0,0,0]`) with fixed RNG909 and native diffusion timestep assignments `[9,5,0,3]`.

| EMA weights / update | Native development objective | Distance MAE [steps] | Common ADE [m] | Common FDE [m] |
|---|---:|---:|---:|---:|
| Released baseline | 0.010168 | 7.221789 | 0.072812 | 0.131571 |
| **236 — selected** | **0.006211** | 6.920066 | 0.030627 | 0.066443 |
| 472 | 0.007927 | 7.417500 | 0.025510 | 0.055309 |
| 1,180 | 0.009837 | 7.351208 | 0.032450 | 0.066307 |
| 2,360 | 0.006813 | 7.061902 | 0.029655 | 0.061542 |
| 4,720 — final | 0.008425 | 7.220176 | 0.020346 | 0.045112 |

The selected EMA lowers these measured development quantities versus release. The final EMA has better ADE/FDE than the selected EMA but a worse native objective and distance MAE; it does not replace the frozen selection. Native eight-waypoint diffusion loss is 0.003978 / 0.000697 / 0.000583 for released / selected / final respectively; distance MSE is 61.901707 / 55.142750 / 78.416847. These native objective components remain separate from common **five** physical waypoints at 0.049994826316833496 m spacing. Native eight-waypoint ADE/FDE was not separately produced by this protocol.

These repeatedly exposed pairs and one seed support an exploratory development result only. They do not establish generalization, model superiority, stopping or navigation efficacy. Native losses cannot be ranked numerically against GNM's different objective.

## Exposure, identities and preserved evidence

Training uses 18,880 sample draws, 1,704 unique catalog pairs, 852 anchors, 1,148 unique RGB endpoints and 9,445 negative-pair draws. Separately, native NoMaD conditioning masks produce 9,486 goal-masked and 9,394 goal-conditioned draws. Negative goal/action-validity labels and conditioning masks are distinct. There are 18,880 recorded per-sample diffusion timestep assignments; their fixed reduction is retained in external `result-integrity.json`. Same sampler pairs/draw counts as GNM do not mean identical history preprocessing, unique RGB exposure or compute.

External root: `/home/favl/navfm-training-evidence/native-multiseed-v1-nomad-seed0-01/`. All 19 ledger-bound artifacts were hash-verified. Pre/post selected dependency object counts are 1,231 / 1,365; generic native file records 2,243 / 3,763; upstream objects 4 / 17. Import-phase counts are not a claim of identical namespace populations.

| Identity / relative artifact | SHA256 |
|---|---|
| Ledger | `3092a0689c18dcf858c737c27f522cb421a229092591dfd45b30d6fe795b48b3` |
| Report | `2dc016b9c573254a93942e8d504a481ec5c7f6331eb0889ae49f81237f85abf8` |
| Selected EMA, `nomad/update_00236/deployment_weights.pth` | `7a6eaa288071a4925f25180385c4cf32430894e068017358d75528d7aaa89ba9` |
| Selected raw/resume + EMA state, `nomad/update_00236/resume.pth` | `5dc75036597b64f9b7d2da0dad192eeccff1c55f326fd9518240a0b9b87317a0` |
| Final EMA, `nomad/deployment_weights.pth` | `f704f5a256a173e538f037c423d49d72aed8cc4fbe65894081803c490d26cffd` |
| Final raw/resume + EMA state, `nomad/resume.pth` | `3976ee8177c7393874936406b600e096fce87f655b2fba8e5873c6e4731eb941` |

Resume containers preserve raw parameters, optimizer, scheduler, EMA, RNG and sampler continuation identity; they are not standalone raw deployment exports. Selected and final EMA identities remain distinct. All weights, per-batch tensor/endpoint hashes, catalog, journal and dense provenance stay external.

Validation: exact frozen source/input/registry/fresh-output preflight; chronological complete transaction/readback audit; frozen selection recomputation; strict reload/development-fence completion; all 19 artifact hashes PASS. The source freeze ran temporarily detached at its canonical paths; the newer GNM report branch was preserved and restored after child reaping. Seven preparation tests and Ruff were not rerun for this result-only document. Old failures/freezes remain immutable.

Next decision: whether to explicitly admit a named remaining seed-11/22 slot under the original reviewed freeze and registry budget. No additional run follows this report.
