# Prospective ViNT scoring v1 result

**PASS, one attempt, no retry or reselection.** Execution freeze `61a5615dab4c841b27d41fe86acba4582818bdc8`. All four fixed identities (release and prior epoch20 seeds0/11/22) loaded strictly; only release permits the qualified legacy-object fallback. Qualified native preprocessing/context/action units and the actual completed qualification, admitted dataset and old model transactions were verified before/after scoring.

128 expected/attempted/returned/valid outcomes, zero missing, invalid0/128.32 pairs contain16positive/16negative from four routes/two previously accessed layouts. There is one deterministic prediction per role/pair; no checkpoint choice or best-seed selection. All raw action/distance JSON arrays and content hashes are retained externally: actions `[1,5,4]`, distances `[1,1]`; all four action components pass finite/heading checks. Metrics use the first five native cumulative XY waypoints and spacing once. Binary tensor dtype is not separately preserved.

| Fixed role | ADE m | FDE m | Positive MAE steps | Negative category MAE | Forward + fence ms | CPU preprocessing ms |
|---|---:|---:|---:|---:|---:|---:|
| release | 0.079903507 | 0.145230948 | 2.171614781 | 15.068403170 | 151.836332836 | 22.925804820 |
| seed 0 | 0.019257628 | 0.034293602 | 3.668477237 | 9.040194780 | 147.623089317 | 22.925804820 |
| seed 11 | 0.022018200 | 0.038523723 | 3.860807985 | 8.846467614 | 147.511680771 | 22.925804820 |
| seed 22 | 0.019133917 | 0.034113261 | 3.973267287 | 8.816997528 | 147.417790009 | 22.925804820 |

Adapted waypoint and negative-category errors improve on the same-model release here, while **positive temporal-distance error worsens for all three seeds**. This is a mixed pilot outcome, not generalization. Positive step labels and artificial negative category20 are separate. No navigation/Orin claim follows.

| Fixed role / route index | ADE m | FDE m | Positive temporal MAE steps | Negative category MAE |
|---|---:|---:|---:|---:|
| release / 0 | 0.089097238 | 0.161382297 | 2.015560746 | 15.261681318 |
| release / 1 | 0.072661576 | 0.131901762 | 2.402845144 | 15.700309455 |
| release / 2 | 0.075648440 | 0.139260890 | 1.998879135 | 14.523947477 |
| release / 3 | 0.082206772 | 0.148378845 | 2.269174099 | 14.787674427 |
| seed 0 / 0 | 0.023670184 | 0.041429986 | 2.872827411 | 10.259445548 |
| seed 0 / 1 | 0.016872421 | 0.030642572 | 3.433344245 | 9.277075052 |
| seed 0 / 2 | 0.016169693 | 0.029487448 | 3.752857685 | 7.914390326 |
| seed 0 / 3 | 0.020318215 | 0.035614401 | 4.614879608 | 8.709868193 |
| seed 11 / 0 | 0.026750445 | 0.045442802 | 3.229933858 | 9.823902845 |
| seed 11 / 1 | 0.019290256 | 0.034373478 | 3.518065691 | 9.192818403 |
| seed 11 / 2 | 0.018677936 | 0.033641195 | 3.905739784 | 7.739397287 |
| seed 11 / 3 | 0.023354165 | 0.040637416 | 4.789492607 | 8.629751921 |
| seed 22 / 0 | 0.023828198 | 0.041575103 | 3.155833125 | 10.020001411 |
| seed 22 / 1 | 0.016632543 | 0.030400363 | 3.720036507 | 8.993843079 |
| seed 22 / 2 | 0.016727947 | 0.030587851 | 4.083215475 | 7.770792723 |
| seed 22 / 3 | 0.019346979 | 0.033889727 | 4.933984041 | 8.483352900 |

Each route cell has four positive/four negative pairs. Routes share layouts and pairs share frames; these are not independent128 samples. State fences are recorded for all roles, and the qualified isolated forward enforces per-call RNG/module-mode restoration and model-state immutability checks. Installed provenance counts690→1236, native2249→2261/final2261; upstream post-attestation completed. All raw content hashes, fixed identity population and complete marker/registry/ledger/four-artifact bindings were independently verified. Parent ledger records reaped=true; source admission requires normal child completion. Separate child-code/timeout fields are not serialized in this scorer ledger; the observed launcher returned0.

1800-second reservation includes finalization. External launcher span **29.361757427s**, including preflight/final persistence; saved pre-final28.573767666s is not end-to-end. CUDA-active time was not measured. Synchronized batch1/two warmups per role; ViNT inference timing includes its isolated state/RNG fence, unlike prior wrapper scopes. CPU preprocessing is separate, native post-timing list conversion excluded. No kernel/Orin or architecture-speed comparison is justified.

External root `/home/favl/navfm-training-evidence/prospective-vint-scoring-v1-01`; raw/evidence stays outside Git.

| Artifact | SHA256 |
|---|---|
| ledger.json | `6575daa96d7e91259383885bb6a41728a1094ff24be7878d4c031cf48af940b5` |
| scoring_complete.json | `64c4a3787ce0a302c41201ee8eab2ba3f992029ce6dab98abe518202ff4c9818` |
| report.json | `1d4f4604c0af3a848f6fde3b4c38cebbdcf29c0627d4d08f7da9dd57df7c041a` |
| provenance.json | `8e2e8eb1bc50bd1cef8a309a382cd0084766631ff5d6319143907f1304eee574` |
| dataset_binding.json | `0911b11a227bad44b86ff24a4bc8ef4c03adc569269923abde81a5dacbe18c90` |
| observer.json | `69c00de1abd94a8f4a48f3045206567067c0a350d831ecccb887728352f9a133` |

Exact checkpoint identities and arithmetic rows are retained in [the external consolidation packet](PROSPECTIVE_THREE_MODEL_CONSOLIDATION_V1.md) and [the qualification protocol](VINT_INTERFACE_QUALIFICATION_V1.md). Source/interface/data criteria and original FAILs remain unchanged; no new collection, training, simulator or robot action. Next: publish the bounded three-model descriptive consolidation, with adaptation/workload differences explicit.
