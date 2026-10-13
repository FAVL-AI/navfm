# Two-model accessed-pilot scoring consolidation v2

Execution freeze `bebf498395c6097b2825679a4c1847bf87f32795`; both named processes PASS without retry. [GNM](PROSPECTIVE_GNM_SCORING_RESULTS_V2.md) has 128 and [NoMaD](PROSPECTIVE_NOMAD_SCORING_RESULTS_V2.md) has 512 valid returned/retained outcomes: **640 total**, no missing outcomes, invalid 0/640. Eight fixed role endpoints, not 640 independent samples. GNM uses one draw and NoMaD averages four coupled draws, never best-of-four. Six selected identities and two releases are unchanged; all strict loads/state fences and dataset/scoring transactions verify.

Scope is the **already accessed two-layout/four-route kinematic pilot**, 32 fixed pairs (16 positive/16 negative), common first five physical waypoints and model-specific native preprocessing. Positive temporal-distance label steps and artificial negative category 20 remain separate. Routes share layouts, pairs share frames and stochastic draws share pair identities. Seed variation is across three preselected training seeds, not route replication; no architecture/native-objective ranking, best seed, independent-heldout, Orin or navigation claim.

| Model / role | ADE m | FDE m | Positive temporal MAE steps | Negative category MAE |
|---|---:|---:|---:|---:|
| gnm / release | 0.030442222 | 0.053911264 | 3.183160 | 16.498497 |
| gnm / seed 0 | 0.014129813 | 0.023150331 | 1.179048 | 12.430038 |
| gnm / seed 11 | 0.017128214 | 0.032057741 | 0.352519 | 12.721966 |
| gnm / seed 22 | 0.011849349 | 0.023051070 | 0.638014 | 14.119692 |
| nomad / release | 0.059792305 | 0.105892690 | 3.929195 | 17.024407 |
| nomad / seed 0 | 0.010253757 | 0.018566488 | 2.894875 | 9.822191 |
| nomad / seed 11 | 0.012480807 | 0.023224216 | 2.988469 | 9.667485 |
| nomad / seed 22 | 0.007175758 | 0.012866859 | 3.161428 | 8.857212 |

| Model / metric | Selected mean | Sample SD (ddof1) | Selected range | Mean paired Δ vs release | SD of paired Δ | Paired Δ range |
|---|---:|---:|---|---:|---:|---|
| gnm / ADE_m | 0.014369125 | 0.002647557 | [0.011849349, 0.017128214] | -0.016073096 | 0.002647557 | [-0.018592873, -0.013314007] |
| gnm / FDE_m | 0.026086381 | 0.005171588 | [0.023051070, 0.032057741] | -0.027824883 | 0.005171588 | [-0.030860193, -0.021853523] |
| gnm / positive_temporal_MAE_steps | 0.723193735 | 0.419796824 | [0.352518886, 1.179048240] | -2.459966443 | 0.419796824 | [-2.830641292, -2.004111938] |
| gnm / negative_category_MAE | 13.090565602 | 0.903123305 | [12.430038452, 14.119692266] | -3.407931780 | 0.903123305 | [-4.068458930, -2.378805116] |
| nomad / ADE_m | 0.009970107 | 0.002663875 | [0.007175758, 0.012480807] | -0.049822198 | 0.002663875 | [-0.052616547, -0.047311498] |
| nomad / FDE_m | 0.018219188 | 0.005187405 | [0.012866859, 0.023224216] | -0.087673502 | 0.005187405 | [-0.093025831, -0.082668473] |
| nomad / positive_temporal_MAE_steps | 3.014923851 | 0.135231390 | [2.894874662, 3.161427766] | -0.914270659 | 0.135231390 | [-1.034319848, -0.767766744] |
| nomad / negative_category_MAE | 9.448962748 | 0.518276248 | [8.857211888, 9.822191000] | -7.575444192 | 0.518276248 | [-8.167195052, -7.202215940] |

Statistics include all selected seeds 0/11/22 (n=3); Δ is selected−same-model release on the same fixed pairs/draw rule, so negative means lower error. No seed was chosen from these outcomes. Route-specific cells are reported separately in each model document; their variation is not pooled into seed SD. All selected aggregate errors improve on their own release here, but metric trade-offs remain: NoMaD seed 22 improves waypoints most while temporal-distance error is largest among its selected seeds; GNM waypoint/distance/category minima likewise differ. Common metrics describe these native systems on this pilot, not isolated architecture quality or incomparable native training objectives.

**Compute/accounting:** two 1800s reservations (3600s total). Separate external observed launcher spans 10.735103358+37.548457670 = **48.283561028s**. Saved pre-final-persistence spans total 47.460395683s, explicitly not full process elapsed. CUDA-active kernel time was not measured. Native timing is synchronized batch 1 with two warmups/role; GNM excludes post-timing host conversion, while NoMaD includes its native CPU decode/transfers, so wrapper scopes differ. CPU preprocessing is separate; no Orin estimate follows.

**Retention/integrity:** all 640 raw per-draw action/distance JSON arrays and content hashes are retained; GNM actions [1,5,4], NoMaD [1,8,2], distances [1,1]. Binary tensor dtype is not preserved. Each model final marker binds output ledger/registry and four artifacts; actual dataset marker/152 input artifacts verify before/after. Original collection/timing failures and private seal remain unchanged. Collection SDK cleanup remains independently unobserved.

Authenticated fixed arithmetic packet `/home/favl/navfm-training-evidence/prospective-scoring-v2-consolidation-01/summary.json`, SHA256 `864c768a3e47504ceff5bb4859d163f60e472ef454df4463a08c1235ce44a944`, binds all eight role identities, 32 route cells, eight selected-statistic rows and model report/provenance/marker/observer hashes. Full checkpoint/artifact hashes appear in the per-model result documents and packet. No raw RGB, private geometry/seed values, weights or predictions are committed.

Both scoring slots are consumed; no further training, scoring, collection, simulator or robot process is launched. Next decision is scientific interpretation/design using the complete mixed metric record, preserving accessed-pilot and unqualified-plant limits rather than post-hoc checkpoint selection.
