# Native GNM / NoMaD multi-seed adaptation v1

Status: reviewed preparation freeze, all six training runs NOT RUN. This executable freeze is independent of the blocked physical plant. Publishing it does not launch or select an initial run. No sealed evaluation, navigation, robot, simulator, illumination or new collection is permitted.

## Frozen schedule and budgets

| Declared slot | Model | Seed |
|---|---|---|
| 1 | GNM | 0 |
| 2 | NoMaD | 0 |
| 3 | GNM | 11 |
| 4 | NoMaD | 11 |
| 5 | GNM | 22 |
| 6 | NoMaD | 22 |

Each fresh process starts from its released checkpoint, never smoke weights or the previous failed partial state. Batch 4, at most 4,720 updates, development checkpoints 236/472/1180/2360/4720. Whole-process GPU reservation is at most 3,600 seconds, including model loading, development evaluations and checkpoint work. The launcher subtracts elapsed setup and a five-second reaping allowance from the child timeout. Six worst-case reservations total 21,600 seconds (six hours), independent of whether a prior slot finishes early. No overlapping worker is admitted by the shared lock. A consumed identity cannot be retried; timeout/exception consumes its full reservation. No extension to reach the update ceiling.

The CLI launches exactly one declared model/seed, not the entire manifest. The registry blocks remaining slots if prior source/runtime integrity is failed or unknown, including a killed worker without complete post-attestation. A normally reaped model-specific failure with shared integrity PASS does not silently cancel independent declared slots. Every actual launch still requires the explicitly authorized staged instruction. Time-limited endpoints remain incomplete; do not label differing update counts equal training exposure. Report occupied wall time; CUDA kernel-active time is not independently measured, and equal reservations are not equal FLOPs.

## Data and native objectives

The hash-pinned admitted split is training only (31 trajectories); four exposed development trajectories are evaluation only. The original four fixed development pairs/two anchors are retained. Before any training trajectory metadata read, compare the declared training list with admission and reject train/development overlap. Authenticate trajectory pickle bytes and every loaded RGB endpoint. No mutable corpus cache is constructed.

A shared deterministic catalog contains one positive goal exactly six chronological steps ahead and one negative goal from the next training trajectory per eligible anchor. Anchors have at least five history steps and eight future labels, so both models draw from the same conservative eligible population. Negative goals are bounded to that trajectory's final admitted image. Catalog order follows the frozen admission list and ascending anchors, positive then negative. Every history/goal/label endpoint remains confined to its partition. Each model/seed uses the same shuffled catalog draws without replacement within an epoch, with local shuffle seed `seed + 1000003*epoch`; this does not consume native training RNG. The next draw is determined by completed update count and catalog hash. This is a declared sampling contract, not a claim that default upstream negative mining is unchanged.

GNM keeps native 85×64 RGB, five history plus current, five action waypoints/angle supervision, native distance/action loss alpha .5 and its qualified Adam configuration. NoMaD keeps native 96×96 RGB, three history plus current, eight actions, native diffusion/noise and distance objective, alpha1e-4, goal masking .5, AdamW and authenticated EMA integration v3. The released bare NoMaD EMA initializes both raw training parameters and initial shadows; it supplies no historical optimizer state. Both use the qualified constant learning-rate scheduler for this bounded adaptation; no claim of upstream epoch-based cosine/warmup equivalence. Native delta/action-statistics normalization and inverse cumulative conversion are unchanged. GT supplies admitted training labels and offline metrics only.

Persist catalog, per-batch indices/endpoint/tensor identities and chronological phase journal. Report complete optimizer/scheduler transactions (and EMA for NoMaD), finite states/gradients, changed parameter count, sample draws, unique pairs/anchors/RGB endpoints, negative draws, native sampled goal masks and diffusion timesteps. A 4,720-update endpoint has 18,880 optimizer-sample draws, not 18,880 unique images or equal effective exposure across objectives.

## Evaluation and selection

Released baseline and every declared checkpoint use evaluation RNG909 under the qualified no_grad state/RNG fence; development never changes raw model, EMA, optimizer, running statistics or training RNG. One frozen native evaluation draw per checkpoint is used; no best-of-draw selection. GNM evaluates raw parameters; NoMaD evaluates the EMA copy. Select the finite **native development objective** minimum among complete declared checkpoints, latest exact tie (deterministic and avoids incidental traversal order). Training loss never selects. Incomplete or nonfinite checkpoints cannot become selected; nonfinite evaluation is a failed run. Baseline is reported separately, not secretly eligible as an adapted checkpoint. Selection on this tiny repeatedly exposed development set is exploratory and may overfit it.

Save raw/resume and deployment separately at each declared checkpoint. The completed optimizer/scheduler/EMA transaction is fsynced before checkpoint evaluation begins; a kill during evaluation cannot erase that completed update. Resume reload follows the qualified CUDA path (RNG tensors are restored on CPU); each EMA shadow must share its model parameter device before continuation. A checkpoint is complete only after fenced development evaluation, strict resume restoration and strict deployment reload; record their hashes and selected relative deployment path. A partial run may report its best complete earlier checkpoint but is not a completed 4,720-update comparison. Final weights and the selected earlier weights have separate identities.

Common ADE/FDE uses the unchanged shared two action-valid development pairs, five physical waypoints at 0.049994826316833496 m spacing. Native GNM five / NoMaD eight-horizon metrics and losses stay separate; temporal distance remains steps. Goal-masked training exposure is separate from goal-conditioned development. Cross-stack differences are system differences, not identifiable pure model effects.

## Invocation and evidence boundary

Configuration: `configs/train/native_multiseed_adaptation_v1.json`. Qualified source/runtime references are the v2 GNM and v3 NoMaD smokes; the earlier failures and all v1–v3 bytes remain immutable. External dependency snapshot/registry root: `/home/favl/navfm-training-evidence/native-multiseed-v1/`. Outputs, catalogs, journals, weights and dense provenance never enter Git.

After accepted committed freeze, the per-slot command template is:

```sh
PYTHONPATH=src NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01/upstream /home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/run_native_multiseed_v1.py --freeze FULL_COMMIT --model MODEL --seed SEED --out /home/favl/navfm-training-evidence/native-multiseed-v1-MODEL-seedSEED-01
```

Prepared validation: seven focused budget/catalog/sampling/selection controls and Ruff PASS. No model construction, optimizer update or GPU training was used to validate this preparation. Runtime behavior under the longer schedule is not yet measured. Next decision is explicit admission of named initial staged runs after source/budget/selection review and freeze, not automatic six-run execution.
