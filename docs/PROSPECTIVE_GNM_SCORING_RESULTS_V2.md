# GNM accessed-pilot scoring result v2

Branch `agent/research-three-model-plan`; execution freeze `bebf498395c6097b2825679a4c1847bf87f32795`. The one authorized GNM scoring process **PASS**: release plus three fixed selected checkpoints, 32 pairs per role, **128/128 attempted/returned/valid outcomes**, no missing draws and invalid rate **0/128**. No NoMaD, training, collection, simulator, navigation or robot process ran; no retry, reselection or source change.

The input is the admitted 190-second v2 **already accessed two-layout/four-route kinematic pilot**. Sixteen positive and sixteen negative pairs are fixed by metadata. Positive common-five-waypoint ADE/FDE use metres; positive temporal-distance MAE uses label steps, not elapsed seconds or traversed metres. Cross-route negative category target 20 is artificial and reported separately. Image timestamps describe held kinematic acquisition, not executed robot motion. The pilot is not genuinely uninspected or independently sealed, and routes/frames are not independent layout replicates.

| Frozen role | Positive ADE m | FDE m | Temporal MAE steps | Negative category MAE | Native inference ms |
|---|---:|---:|---:|---:|---:|
| Release | 0.030442222 | 0.053911264 | 3.183160 | 16.498497 | 2.675161 |
| Selected seed 0 | 0.014129813 | 0.023150331 | 1.179048 | 12.430038 | 2.879956 |
| Selected seed 11 | 0.017128214 | 0.032057741 | 0.352519 | 12.721966 | 2.746252 |
| Selected seed 22 | 0.011849349 | 0.023051070 | 0.638014 | 14.119692 | 2.795821 |

Role means use all16 positive or16 negative pairs. All selected roles reduce these aggregate errors relative to release on this pilot; the lowest waypoint, temporal-distance and negative-category errors occur at different selected seeds. No best seed or intrinsic model-quality winner is selected, and these results do not establish broader generalization or navigation efficacy.

| Role / route index | ADE m | FDE m | Temporal MAE steps | Negative category MAE |
|---|---:|---:|---:|---:|
| Release / 0 | 0.030908997 | 0.054668197 | 2.100923 | 16.421617 |
| Release / 1 | 0.031278506 | 0.054972539 | 3.656550 | 17.000937 |
| Release / 2 | 0.030822093 | 0.054708660 | 3.484777 | 16.075080 |
| Release / 3 | 0.028759291 | 0.051295659 | 3.490391 | 16.496356 |
| Seed 0 / 0 | 0.015531334 | 0.025588270 | 1.270653 | 12.025334 |
| Seed 0 / 1 | 0.011899890 | 0.019470562 | 1.067851 | 12.659902 |
| Seed 0 / 2 | 0.014392761 | 0.023596782 | 1.142785 | 12.623598 |
| Seed 0 / 3 | 0.014695265 | 0.023945711 | 1.234904 | 12.411320 |
| Seed 11 / 0 | 0.019164240 | 0.035117788 | 0.569888 | 10.901073 |
| Seed 11 / 1 | 0.015495780 | 0.029608525 | 0.338434 | 13.611535 |
| Seed 11 / 2 | 0.017654676 | 0.033076415 | 0.249543 | 13.731936 |
| Seed 11 / 3 | 0.016198162 | 0.030428236 | 0.252210 | 12.643320 |
| Seed 22 / 0 | 0.011954484 | 0.023390683 | 0.528534 | 13.609622 |
| Seed 22 / 1 | 0.011642042 | 0.022657400 | 0.683082 | 14.602791 |
| Seed 22 / 2 | 0.011311535 | 0.021984830 | 0.646116 | 14.573973 |
| Seed 22 / 3 | 0.012489334 | 0.024171369 | 0.694324 | 13.692383 |

Each route row contains four positive and four negative pairs. Route indices follow the frozen admission order; no private geometry or seed values are disclosed. Seed variation and route variation are separate factors, not 32 or 128 independent trials.

All four roles loaded strictly and preserved model state. Native-file attestation passed before/after/final; selected-dependency and upstream attestation passed before/after: selected module records 690→1236, native 2250→2262 with 2262 final, upstream 0 initially loaded→9 after. Added project sources remained authenticated. Before/after dataset transaction checks PASS; all152 input artifact hashes and the completed dataset marker/registry identity verify. The scoring COMPLETE marker binds its PASS output ledger and reservation plus all four output artifacts (report, provenance, binding evidence, process log).

**128 raw per-draw action/distance arrays and content hashes** are retained inside the durable atomic report. Actions have shape [1,5,4], distance [1,1], and returned values are finite; the common waypoint metric uses XY. Raw `.tolist()` arrays preserve nested shape/numeric values but not the original tensor binary dtype. No NPY conversion/export was performed. Missing/invalid draws would retain their attempt identities and null fixed-population metrics; none occurred here.

External launcher spawn-to-return was **10.735103358s**, including interpreter/preflight/finalization; saved ledger **10.327636260s** is pre-final-persistence. The 1800s total was respected. Mean CPU preprocessing was **24.814475ms/pair**, measured once and shared across roles; it includes input/label loading and preprocessing, excludes CUDA transfer. Native inference timing is synchronized batch 1, with two warmups/role; it excludes RNG setup, preprocessing, post-timing host conversion/metric calculation and persistence. Workstation measurements are not end-to-end Orin latency. SDK cleanup of the collection remains independently unobserved.

| Frozen checkpoint | SHA256 |
|---|---|
| Release | `4b03e0255f8a547290d4079f4e7d610ff69987122f17e019bd36684c08b3ee95` |
| Selected seed 0 / update_00236 | `98a7996e90d5ebce7aca9c247cd7b49a601a84b5347e2877449b0fa294d8f9bc` |
| Selected seed 11 / update_01180 | `666b298c23aafeed1ecb79edb4e5e4425ea2c566e4eeebf9c75ea13ac6f18a04` |
| Selected seed 22 / update_02360 | `defa26edab0660135041f282bc0a3a243690ce7e92c510ea48ed5288aea9344e` |

Exact checkpoint paths remain in the frozen config and external report; none were selected using these outcomes. External scoring evidence: `/home/favl/navfm-training-evidence/prospective-scoring-v2-gnm-01`. Observer/arithmetic summary: `/home/favl/navfm-training-evidence/prospective-scoring-v2-gnm-observer-01/validation_summary.json`, SHA256 `a19200afd121e75c3a71e7a3a35db3348dc75ca9b7295395ac60004aab791170`.

| Output identity | SHA256 |
|---|---|
| ledger.json | `197c5afb26113580f1435e7774988bfa320ad40f473c103951dffcc5fdf2e76c` |
| scoring_complete.json | `3d44837fe872030829d05dc1854a1c24a8f9d51957d5184abcbffdada99b09e9` |
| report.json | `8f49ea9adb94cd5489c4f61b1789158c042b3efc7aafe3864f0bb712ce4069bd` |
| provenance.json | `b6e07e80b801d8844e94b90c6ba5462f6ae1adad9321c6451ac99496fec6934c` |
| dataset_binding.json | `0911b11a227bad44b86ff24a4bc8ef4c03adc569269923abde81a5dacbe18c90` |

Validation: exact clean-freeze/source/checkpoint/input/eligibility preflight, immutable opaque seal-chain checks, complete 128 identities and retained raw hashes, fixed-population summary replay, strict-load/state fences, native provenance, final scoring transaction/artifact verification and source/input postflight. No tests rerun; reviewed preparation had 13 focused controls/Ruff PASS. Raw predictions, images, labels, model weights and private values remain external; publication changes only this result document with the required identity.

Next decision: separately authorize NoMaD once from the same reviewed freeze and dataset transaction, retaining four fixed draws and all selected identities. No such launch is performed by this result publication.
