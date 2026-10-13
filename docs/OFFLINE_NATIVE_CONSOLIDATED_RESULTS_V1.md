# Both-model expanded offline development results v1

Both authorized processes completed **PASS** from source freeze `69d1a204bbde0a6458dbd38fb4b515d7cf2aa07e`: [GNM](OFFLINE_NATIVE_GNM_RESULTS_V1.md), [NoMaD](OFFLINE_NATIVE_NOMAD_RESULTS_V1.md), [protocol](OFFLINE_NATIVE_EVALUATION_V1.md). Six originally selected adaptation checkpoints and two released baselines remain fixed; no best-seed or checkpoint reselection.

## Fixed completeness and exposed scope

GNM192 + NoMaD768 = **960/960** attempted, returned, finite draws; zero missing/invalid. Eight strict loads/model-state fences PASS; full native-file/selected/upstream pre/post/final provenance and all six ledger artifact hashes verified. Four routes, 48 fixed pairs (24 positive/24 negative), with seven/seven/five/five anchors per route. NoMaD uses four deterministic-coupled ten-step draws per pair; every per-draw error is averaged, no oracle sample. GNM uses one native prediction per pair. Missing draws would yield null fixed-population means; none were missing.

These routes are previously inspected development, including the two retired former test routes; expanded anchors remain correlated and overlap the development used for selection. No fresh-layout or confirmatory claim follows. ViNT remains outside this qualified native evaluation version. Native objectives are different and are not ranked here; this scoring evaluates common physical five-waypoint errors and separately native distance labels.

## Every frozen checkpoint endpoint

Means weight positive/negative pairs equally within class; different route counts are explicit in the individual reports. No aggregate frame-count significance test.

| Model | Role / training seed | Positive ADE [m] | Positive FDE [m] | Positive temporal MAE [steps] | Negative category MAE |
|---|---|---:|---:|---:|---:|
| gnm | release / None | 0.045986 | 0.082460 | 3.665578 | 10.699596 |
| gnm | selected / 0 | 0.021024 | 0.036383 | 2.757941 | 7.646316 |
| gnm | selected / 11 | 0.024201 | 0.041864 | 1.522941 | 10.778081 |
| gnm | selected / 22 | 0.026538 | 0.045230 | 1.517863 | 10.692916 |
| nomad | release / None | 0.075161 | 0.142658 | 3.908380 | 10.472987 |
| nomad | selected / 0 | 0.024118 | 0.043508 | 4.276734 | 5.565226 |
| nomad | selected / 11 | 0.024541 | 0.044362 | 3.762098 | 6.087703 |
| nomad | selected / 22 | 0.021716 | 0.038706 | 4.501001 | 5.079565 |

All selected checkpoints lower overall positive ADE/FDE relative to their own releases on these exposed pairs. Distance outcomes are mixed: GNM positive temporal MAE improves across all three seeds, while NoMaD seeds 0/22 worsen and 11 improves; GNM negative-category error decreases for 0, increases for 11 and is near release for 22, while all NoMaD negative-category errors decrease. Thus waypoint improvement is not a blanket improvement in every output. None identifies a pure architecture effect, intrinsic model quality, stopping or navigation performance.

## Training-seed variation, separate from trajectory variation

The following descriptive selected statistics use all three prespecified training seeds, sample SD ddof 1, and ranges. Paired differences are selected minus that model’s released baseline, evaluated with the same fixed pairs/draw identities. No confidence intervals or significance claims from n=3; per-trajectory outcomes remain in the two reports and are not treated as independent seeds.

| Model | Metric | Selected mean | Sample SD | Range | Mean paired delta |
|---|---|---:|---:|---|---:|
| gnm | ADE_m | 0.023921 | 0.002768 | 0.021024–0.026538 | -0.022065 |
| gnm | FDE_m | 0.041159 | 0.004466 | 0.036383–0.045230 | -0.041301 |
| gnm | positive_distance_MAE_steps | 1.932915 | 0.714498 | 1.517863–2.757941 | -1.732663 |
| gnm | negative_category_MAE | 9.705771 | 1.784048 | 7.646316–10.778081 | -0.993825 |
| nomad | ADE_m | 0.023458 | 0.001524 | 0.021716–0.024541 | -0.051703 |
| nomad | FDE_m | 0.042192 | 0.003049 | 0.038706–0.044362 | -0.100466 |
| nomad | positive_distance_MAE_steps | 4.179944 | 0.378841 | 3.762098–4.501001 | 0.271564 |
| nomad | negative_category_MAE | 5.577498 | 0.504181 | 5.079565–6.087703 | -4.895489 |

## Workstation latency, budget and identities

Total occupied launcher wall **59.801649 seconds** (GNM 8.514714 + NoMaD 51.286935), against two consumed 1800-second reservations; no overlap/retry/extension. This includes loading, preprocessing, validation and report work. CUDA kernel-active time/FLOPs were not measured.

Native timed inference is batch 1 after two warmups per checkpoint; CUDA-synchronized, RNG outside timer. GNM means 2.87–3.10ms; NoMaD means 24.36–25.57ms for one full ten-step draw, including native get_action CPU inverse/decode transfers. NoMaD evaluation uses four draws per pair, not one identical computational workload. Separately measured preprocessing means 20.498648 ms GNM / 16.843212 ms NoMaD; native image/context sizes differ. Timings do not estimate Orin/ROS end-to-end deployment latency or prove a hardware speed claim.

| Model | Role / seed | Exact deployment SHA256 |
|---|---|---|
| gnm | release / None | `4b03e0255f8a547290d4079f4e7d610ff69987122f17e019bd36684c08b3ee95` |
| gnm | selected / 0 | `98a7996e90d5ebce7aca9c247cd7b49a601a84b5347e2877449b0fa294d8f9bc` |
| gnm | selected / 11 | `666b298c23aafeed1ecb79edb4e5e4425ea2c566e4eeebf9c75ea13ac6f18a04` |
| gnm | selected / 22 | `defa26edab0660135041f282bc0a3a243690ce7e92c510ea48ed5288aea9344e` |
| nomad | release / None | `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333` |
| nomad | selected / 0 | `7a6eaa288071a4925f25180385c4cf32430894e068017358d75528d7aaa89ba9` |
| nomad | selected / 11 | `8bb36d3ca1f206bc93635f28358ef948370e462731d2b67b6e15416d6b7872d7` |
| nomad | selected / 22 | `4d5e534ecd8056dde1679399702d20225b710811e6a326b5638fbf436e76c723` |

Raw GNM versus EMA NoMaD roles remain distinct. Full paths and individual ledger/report/provenance hashes are in the per-model reports and source configuration. Authenticated compact reduction: `/home/favl/navfm-training-evidence/offline-native-evaluation-v1/consolidation-v1/authenticated-summary.json`, SHA256 `5cad3fa3912b6f7e1d8679d08998b05db01c6dc441e9f53455ade7d988f7e5c1`. It rehashes all six ledger artifacts, recomputes summaries under the exact worker interpreter and preserves all route/role/seed denominators. Recorded metrics/data/logs and dense provenance remain external; raw predicted waypoint arrays were not persisted by the frozen worker, limiting later output-level reanalysis.

Validation: fixed expected identity populations, finite outputs, strict loads/state fences, full provenance and bound artifact hashes PASS. No source/threshold changes. The prior GNM host-Python one-ULP floating-reduction difference is documented; exact-worker arithmetic reproduces both reports without a gate change or rerun. Preparation tests were not repeated for these result-only documents.

Next decision: an independently specified evaluation/physical-plant admission, respecting exposed-development selection and the still-blocked loaded motion. This report does not launch further training, navigation, simulator or robot work.
