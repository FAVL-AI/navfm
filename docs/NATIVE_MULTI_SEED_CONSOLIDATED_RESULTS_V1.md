# All-six native adaptation: development results v1

All six prespecified GNM/NoMaD × seeds 0/11/22 runs completed **PASS**, 4,720 updates each from freeze `e94b6968b1d958a7254ac2ca8da42ba1c4d7a686`; [protocol](NATIVE_MULTI_SEED_ADAPTATION_V1.md). Every run uses fresh release and its frozen native-development selection, not smoke weights or best-seed selection. All original failed precursor attempts remain immutable; these six declared long-run slots have no failures or incomplete endpoints.

## Every selected and final endpoint

| Model | Seed | Endpoint / update | Native dev objective | Distance MAE [steps] | Common ADE [m] | Common FDE [m] |
|---|---:|---|---:|---:|---:|---:|
| gnm | 0 | Released / 0 | 0.557271 | 7.283866 | 0.042461 | 0.074594 |
| gnm | 0 | Selected / 236 | 0.315521 | 7.400471 | 0.020165 | 0.041750 |
| gnm | 0 | Final / 4720 | 0.520861 | 7.663227 | 0.015511 | 0.024863 |
| gnm | 11 | Released / 0 | 0.557271 | 7.283866 | 0.042461 | 0.074594 |
| gnm | 11 | Selected / 1180 | 0.165306 | 5.148582 | 0.013012 | 0.026758 |
| gnm | 11 | Final / 4720 | 0.360925 | 6.752186 | 0.026660 | 0.051939 |
| gnm | 22 | Released / 0 | 0.557271 | 7.283866 | 0.042461 | 0.074594 |
| gnm | 22 | Selected / 2360 | 0.186919 | 5.563858 | 0.009663 | 0.022515 |
| gnm | 22 | Final / 4720 | 0.341897 | 6.654975 | 0.022287 | 0.035380 |
| nomad | 0 | Released / 0 | 0.010168 | 7.221789 | 0.072812 | 0.131571 |
| nomad | 0 | Selected / 236 | 0.006211 | 6.920066 | 0.030627 | 0.066443 |
| nomad | 0 | Final / 4720 | 0.008425 | 7.220176 | 0.020346 | 0.045112 |
| nomad | 11 | Released / 0 | 0.010168 | 7.221789 | 0.072812 | 0.131571 |
| nomad | 11 | Selected / 236 | 0.006105 | 6.931286 | 0.029695 | 0.060538 |
| nomad | 11 | Final / 4720 | 0.006837 | 7.049812 | 0.037907 | 0.075121 |
| nomad | 22 | Released / 0 | 0.010168 | 7.221789 | 0.072812 | 0.131571 |
| nomad | 22 | Selected / 1180 | 0.006646 | 6.948804 | 0.026755 | 0.052653 |
| nomad | 22 | Final / 4720 | 0.007917 | 7.218577 | 0.034332 | 0.071123 |

Native objective magnitudes are model-specific and must not rank GNM against NoMaD. GNM uses raw weights/native five-waypoint action-angle loss; NoMaD uses EMA/native eight-waypoint diffusion loss. Common metrics use the same two action-valid pairs and five physical waypoints at 0.049994826316833496 m spacing. Four total dev pairs/two anchors are repeatedly exposed; these are exploratory selection results, not sealed generalization or navigation evaluation.

## Selected statistics and paired release differences

For each model n=3 training seeds; sample SD uses ddof=1. Range is minimum–maximum. Differences are **selected minus that seed’s released baseline**; negative means lower metric. These descriptive statistics are not confidence intervals or tests and do not make the two dev pairs independent replications.

| Model | Metric | Selected mean | Sample SD | Range | Paired delta mean | Delta sample SD | Delta range |
|---|---|---:|---:|---|---:|---:|---|
| gnm | loss | 0.222582 | 0.081210 | 0.165306–0.315521 | -0.334689 | 0.081210 | -0.391965–-0.241750 |
| gnm | distance_MAE_steps | 6.037637 | 1.198375 | 5.148582–7.400471 | -1.246229 | 1.198375 | -2.135284–0.116605 |
| gnm | ADE_m | 0.014280 | 0.005365 | 0.009663–0.020165 | -0.028181 | 0.005365 | -0.032798–-0.022296 |
| gnm | FDE_m | 0.030341 | 0.010105 | 0.022515–0.041750 | -0.044253 | 0.010105 | -0.052078–-0.032844 |
| nomad | loss | 0.006321 | 0.000287 | 0.006105–0.006646 | -0.003847 | 0.000287 | -0.004063–-0.003521 |
| nomad | distance_MAE_steps | 6.933385 | 0.014484 | 6.920066–6.948804 | -0.288404 | 0.014484 | -0.301723–-0.272985 |
| nomad | ADE_m | 0.029026 | 0.002021 | 0.026755–0.030627 | -0.043787 | 0.002021 | -0.046057–-0.042185 |
| nomad | FDE_m | 0.059878 | 0.006918 | 0.052653–0.066443 | -0.071692 | 0.006918 | -0.078917–-0.065128 |

All selected native objectives and common ADE/FDE are lower than release on these pairs. Distance MAE is mixed: GNM seed 0 worsens while 11/22 improve; NoMaD selected values improve across all 3. Final weights are not universally better than selected: selections occur earlier and waypoint improvements do not always track the native objective or distance MAE. No checkpoint or seed is replaced after examining these results. The different native objectives cannot identify a pure cross-model effect.

## Compute, exposure and integrity

| Model | Seed | Occupied seconds | Unique RGB | Negative draws | Selected update |
|---|---:|---:|---:|---:|---:|
| gnm | 0 | 362.562550 | 1210 | 9445 | 236 |
| gnm | 11 | 353.558618 | 1210 | 9445 | 1180 |
| gnm | 22 | 355.689952 | 1210 | 9438 | 2360 |
| nomad | 0 | 596.677612 | 1148 | 9445 | 236 |
| nomad | 11 | 601.303644 | 1148 | 9445 | 236 |
| nomad | 22 | 598.174851 | 1148 | 9438 | 1180 |

Total occupied launcher wall: 2867.967226 s (47.799 min), against 21,600 s six worst-case reservations. Includes load/dev/save/reload/cleanup; CUDA kernel-active time/FLOPs unmeasured. Every run has 18,880 sample draws, 1,704 unique catalog pairs and 852 anchors. Equal update/draw counts do not imply equal native preprocessing, unique images, conditioning exposure or compute. NoMaD training goal masks are distinct from negative goal/action-validity labels; all dev masks 0, so no goal-masked dev efficacy claim.

Actual complete optimizer/scheduler counters 1–4,720 each; NoMaD EMA 1–4,720. Finite gradients/states, strict release/resume/deployment reloads, all development fences, child reaping/shared pre/post integrity PASS. GNM duplicated scheduler observations are not extra updates. All 114 ledger artifact hashes (19/run) verified. No source changes during execution.

## Exact identities

Each resume container holds raw training state (including EMA for NoMaD), not standalone deployment weights. Selected/final GNM exports raw, NoMaD exports EMA. Full external roots are `/home/favl/navfm-training-evidence/native-multiseed-v1-MODEL-seedSEED-01/`.

| Model / seed | Selected deployment SHA256 | Final deployment SHA256 |
|---|---|---|
| gnm / 0 | `98a7996e90d5ebce7aca9c247cd7b49a601a84b5347e2877449b0fa294d8f9bc` | `9e638997eee4d6341dfaf2fce0133e69c6896e89530474e7296f951638328368` |
| gnm / 11 | `666b298c23aafeed1ecb79edb4e5e4425ea2c566e4eeebf9c75ea13ac6f18a04` | `e3f9542421a82fe6670600d4a4689a41d42ef664d0f6fe0a494eeb7468063fbc` |
| gnm / 22 | `defa26edab0660135041f282bc0a3a243690ce7e92c510ea48ed5288aea9344e` | `f6db16e7dcb454da05175a7b05664288c89b070f8fa2be515d3407d81a416ea1` |
| nomad / 0 | `7a6eaa288071a4925f25180385c4cf32430894e068017358d75528d7aaa89ba9` | `f704f5a256a173e538f037c423d49d72aed8cc4fbe65894081803c490d26cffd` |
| nomad / 11 | `8bb36d3ca1f206bc93635f28358ef948370e462731d2b67b6e15416d6b7872d7` | `afb053e359fcb0878765924b6a518c0974504591902f6f0b3adac37df3e3fb05` |
| nomad / 22 | `4d5e534ecd8056dde1679399702d20225b710811e6a326b5638fbf436e76c723` | `b0996e20612b46e890d7680a8888340305aa87341f920a859b226de0d5057d69` |

| Model / seed | Selected resume SHA256 | Final resume SHA256 | Report SHA256 |
|---|---|---|---|
| gnm / 0 | `82b0ba7cdd455fb42a73c20d1ef359d6d8547c16e02782ead5bf3b8c0c4458db` | `47670ba34315f06fe41637234d709e35715f234705c0e6da3e6aadc534e19f43` | `f4bfe4874f5259b3e09cf86f2179e825890da10c69320f03b1a0bb42fb2d2917` |
| gnm / 11 | `413077d666bc76d2d1d1eda8a7a9b3db12231660eecde9105251ef650614a1da` | `e9d7669a3246c1361d1e61996c5f30cb1e09621d9656f3054b55f941626646dc` | `178712f5f310c30ae0ff4f4e5f92b87acdeef079127418ea6a9a0e9ca6b666b1` |
| gnm / 22 | `9f415ae3e2ffc912adcfa105982c27f36497cc1a26d2588c738d1a9cac4fec00` | `5a7345eb1d128991cefe17df9d3c0e53dc4dd1185f3161cf8cc5a4cb6307ac36` | `8c2c45842b6c9424a9ec9a8659b1adc2ed12091517a723b65ed564afc4b09cc6` |
| nomad / 0 | `5dc75036597b64f9b7d2da0dad192eeccff1c55f326fd9518240a0b9b87317a0` | `3976ee8177c7393874936406b600e096fce87f655b2fba8e5873c6e4731eb941` | `2dc016b9c573254a93942e8d504a481ec5c7f6331eb0889ae49f81237f85abf8` |
| nomad / 11 | `285b4855b34422b3d2e33c62cd3adf8a52f41b93a74b28949f40a8bccc77ae41` | `07b9bc5993452b53409c550cde7a0dde9d9e00f5aeec5c0b203565ae9063d5b0` | `40cf24a6e6b2de73c5c4d5cd1e985bd4f68db0c8398b5cf368de80cf18b7ee92` |
| nomad / 22 | `db4c000d3d947e3f12763371e0358a93ae618bf9602a9b1cbe60073dc24abd7a` | `224a8f672ee8b8426eee32d09eb74775f755221132f749dc417eebb8634ac36e` | `11f0ba8e3f5195cec4d6a9232d46b0def270bc12a1f4a1500f870db8c51704d3` |

Selected paths are `MODEL/update_XXXXX/deployment_weights.pth` and `resume.pth` at the listed selected update; final paths are `MODEL/deployment_weights.pth` and `resume.pth`. Full authenticated compact reduction with ledger hashes, baseline/endpoint values, exposure and mask counts: `/home/favl/navfm-training-evidence/native-multiseed-v1/consolidation-v1/authenticated-summary.json`, SHA256 `660e2d2bc17e510988b716ca390e1e62ff3234a4571b2e48e5bf0f317526c169`. Raw weights/logs/catalogs/dense provenance stay external.

Validation: every report/ledger-bound artifact rehashed; all frozen selections independently recomputed; chronological counters and finite gradient flags audited; arithmetic uses all 3 prespecified seeds with sample SD ddof 1. Preparation tests were not repeated for these result-only documents. No further runtime.

Next decision: independently define an evaluation/physical-plant admission that addresses the tiny exposed development set and still-blocked loaded motion. These offline adaptation results alone do not authorize navigation or robot deployment.
