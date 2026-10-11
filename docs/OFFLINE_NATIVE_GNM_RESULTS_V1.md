# Expanded offline development: GNM v1

The single authorized GNM process completed **PASS** from freeze `69d1a204bbde0a6458dbd38fb4b515d7cf2aa07e`; [protocol](OFFLINE_NATIVE_EVALUATION_V1.md). Released plus three frozen selected raw checkpoints were evaluated on 48fixed pairs across four already exposed routes. No checkpoints/seeds were reselected; NoMaD remains NOT RUN. No training/simulator/navigation/robot process.

## Completeness and fixed denominators

All 192expected role×pair×draw identities were attempted, returned and finite, with zero missing/invalid draws (0/192). All four strict checkpoint loads and model-state fences PASS; no optimizer or EMA update. Each role has 24positive/action-valid pairs and24negative/action-invalidpairs. Fullnative file closure, selected dependencies and upstream origins pass before/after/final attestation; source/input postflight PASS, child reaped. Occupied launcher time 8.514714s against 1800s reserved.

Positive ADE/FDE uses only the 24action-valid pairs, common first five XY waypoints at 0.049994826316833496m spacing; native GNM RGB 85×64/context 5 remains unchanged. Positive distance error is temporal-step label error (goal six steps later); negative error is against artificial native max category 20, not physical goal distance. All summaries keep these labels separate.

## Per-role overall descriptive means

Means below weight fixed pairs equally (routes have 7/7/5/5positivepairs). They do not select a seed and do not replace the per-route results.

| Raw checkpoint | Positive ADE [m] | Positive FDE [m] | Positive distance MAE [steps] | Negative category MAE | Invalid / attempted |
|---|---:|---:|---:|---:|---|
| Released | 0.045986 | 0.082460 | 3.665578 | 10.699596 | 0 / 48 |
| Selected seed 0 | 0.021024 | 0.036383 | 2.757941 | 7.646316 | 0 / 48 |
| Selected seed 11 | 0.024201 | 0.041864 | 1.522941 | 10.778081 | 0 / 48 |
| Selected seed 22 | 0.026538 | 0.045230 | 1.517863 | 10.692916 | 0 / 48 |

## Trajectory versus training-seed outcomes

Each row is one fixed trajectory/checkpoint aggregate; neighbouring anchors/histories are correlated. These four trajectories are not new uninspected layouts. No pooling of frame counts as independent replications.

| Role / training seed | Trajectory | Positive pairs | ADE [m] | FDE [m] | Positive distance MAE [steps] | Negative category MAE |
|---|---|---:|---:|---:|---:|---:|
| release | s_bend_run_0000 | 7 | 0.048596 | 0.080663 | 3.856023 | 11.630470 |
| release | s_bend_run_0001 | 7 | 0.045293 | 0.080721 | 4.699944 | 10.371376 |
| release | junction_run_0000 | 5 | 0.041540 | 0.080453 | 3.169315 | 14.060557 |
| release | junction_run_0001 | 5 | 0.047747 | 0.089415 | 2.447103 | 6.494918 |
| selected / 0 | s_bend_run_0000 | 7 | 0.021959 | 0.038897 | 3.062231 | 8.973444 |
| selected / 0 | s_bend_run_0001 | 7 | 0.025907 | 0.042291 | 3.124470 | 5.462430 |
| selected / 0 | junction_run_0000 | 5 | 0.010969 | 0.021268 | 2.311650 | 11.185647 |
| selected / 0 | junction_run_0001 | 5 | 0.022936 | 0.039706 | 2.265088 | 5.306447 |
| selected / 11 | s_bend_run_0000 | 7 | 0.022955 | 0.038885 | 0.915213 | 14.219564 |
| selected / 11 | s_bend_run_0001 | 7 | 0.027072 | 0.047079 | 0.829214 | 9.255922 |
| selected / 11 | junction_run_0000 | 5 | 0.019962 | 0.034352 | 2.280232 | 10.331386 |
| selected / 11 | junction_run_0001 | 5 | 0.026164 | 0.046247 | 2.587686 | 8.537721 |
| selected / 22 | s_bend_run_0000 | 7 | 0.022698 | 0.039053 | 1.186321 | 14.788224 |
| selected / 22 | s_bend_run_0001 | 7 | 0.027662 | 0.046589 | 1.995086 | 9.361756 |
| selected / 22 | junction_run_0000 | 5 | 0.021836 | 0.036111 | 1.409641 | 11.400699 |
| selected / 22 | junction_run_0001 | 5 | 0.035043 | 0.061094 | 1.422132 | 6.115324 |

All three selected checkpoints have lower overall positive ADE/FDE and positive temporal-step MAE than release on this expanded exposed-development pair set. Negative-category error is mixed: seed 0 decreases, seed 11 increases, seed 22 is close to release. Per-route/seed variation remains visible; no best-seed choice, model ranking, confidence interval or generalization claim. This is expanded development evidence after selection on a smaller overlapping subset, not a confirmatory test. Physical-plant motion remains unqualified.

## Workstation timing and identities

Batch1, two unscored warmups per checkpoint; seeds reset before timing, CUDA synchronized immediately before/after native forward. Latency excludes RNG setup/load/preprocessing/CPU metric transfer. Preprocessing and image/trajectory hash validation were measured separately once per pair and reused identically across checkpoints; mean 20.498648ms. These RTX workstation measurements do not establish Orin/ROS/robot end-to-end latency.

| Role / training seed | Native mean [ms] | Median [ms] | Range [ms] | Timed draws |
|---|---:|---:|---|---:|
| release | 3.098111 | 2.804807 | 2.651416–6.212762 | 48 |
| selected / 0 | 3.097501 | 2.837159 | 2.608220–4.583293 | 48 |
| selected / 11 | 2.871466 | 2.820645 | 2.630967–3.792386 | 48 |
| selected / 22 | 2.978807 | 2.950942 | 2.813648–3.756816 | 48 |

External root: `/home/favl/navfm-training-evidence/offline-native-evaluation-v1-gnm-01/`. Every row preserves role/pair/draw, batch endpoint/tensor identities, finite/invalid disposition and timing. No source changes/retries; all three ledger-bound artifacts rehashed.

| Artifact | SHA256 |
|---|---|
| ledger.json | `2ea96811eda24bd8785cb8495a87dce8050082c7c8a8e372d02a27bce3ae8cfa` |
| report.json | `c6147727ea89e10e6860e5dfe8a6d805cc79aa9b7964703519542b9a4def9ff4` |
| provenance.json | `6bb99bae477e578bdd676c380419e818be380ed947c2060ad6bc4c4df5f1fbe3` |

| Loaded raw checkpoint | SHA256 |
|---|---|
| release / None | `4b03e0255f8a547290d4079f4e7d610ff69987122f17e019bd36684c08b3ee95` |
| selected / 0 | `98a7996e90d5ebce7aca9c247cd7b49a601a84b5347e2877449b0fa294d8f9bc` |
| selected / 11 | `666b298c23aafeed1ecb79edb4e5e4425ea2c566e4eeebf9c75ea13ac6f18a04` |
| selected / 22 | `defa26edab0660135041f282bc0a3a243690ce7e92c510ea48ed5288aea9344e` |

Validation: exact frozen source/input/metadata/registry/fresh-output preflight;192 expected identity audit; strict load/state fences; full pre/post dependency/source integrity; three artifact hashes PASS. Summary recomputation is byte-value-equivalent under the exact worker interpreter. A host-Python read-only recomputation initially differed by one ULP in a floating sum; using the frozen worker interpreter reproduced all saved summaries without source/threshold changes. Preparation tests/Ruff were not rerun for this result-only report. Data/tensors/logs/dense provenance remain external.

Next decision: explicit admission of NoMaD under the same prepared evaluation freeze and remaining 1800-second reservation. No NoMaD process is launched by this report.
