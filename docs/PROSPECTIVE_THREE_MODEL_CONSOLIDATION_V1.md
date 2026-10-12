# Three-model accessed-pilot consolidation v1

All three authorized scorers PASS: GNM128 +NoMaD512 +ViNT128 =**768 returned/valid retained outcomes**, zero missing/invalid. Twelve fixed endpoints (three releases/nine previously selected seeds), not768 independent samples. GNM/NoMaD source `bebf498395c6097b2825679a4c1847bf87f32795`; ViNT `61a5615dab4c841b27d41fe86acba4582818bdc8`. No old run was repeated or checkpoint reselected.

Common population is32 fixed pairs (16positive/16negative), four routes/two **already accessed pilot layouts**, five physical waypoints and common spacing. Native preprocessing differs by model as qualified; temporal-distance labels and artificial negative category20 are not physical-distance estimates. All selected seeds0/11/22 are retained. Routes/pairs/draws are correlated, and seed SD is separate from route variation. No independent benchmark, navigation, architecture winner or state-of-the-art claim.

| Model / fixed role | ADE m | FDE m | Positive temporal MAE steps | Negative category MAE |
|---|---:|---:|---:|---:|
| gnm / release | 0.030442222 | 0.053911264 | 3.183160178 | 16.498497382 |
| gnm / seed 0 | 0.014129813 | 0.023150331 | 1.179048240 | 12.430038452 |
| gnm / seed 11 | 0.017128214 | 0.032057741 | 0.352518886 | 12.721966088 |
| gnm / seed 22 | 0.011849349 | 0.023051070 | 0.638014078 | 14.119692266 |
| nomad / release | 0.059792305 | 0.105892690 | 3.929194510 | 17.024406940 |
| nomad / seed 0 | 0.010253757 | 0.018566488 | 2.894874662 | 9.822191000 |
| nomad / seed 11 | 0.012480807 | 0.023224216 | 2.988469124 | 9.667485356 |
| nomad / seed 22 | 0.007175758 | 0.012866859 | 3.161427766 | 8.857211888 |
| vint / release | 0.079903507 | 0.145230948 | 2.171614781 | 15.068403170 |
| vint / seed 0 | 0.019257628 | 0.034293602 | 3.668477237 | 9.040194780 |
| vint / seed 11 | 0.022018200 | 0.038523723 | 3.860807985 | 8.846467614 |
| vint / seed 22 | 0.019133917 | 0.034113261 | 3.973267287 | 8.816997528 |

| Model / metric | Selected mean | Sample SD ddof1 | Selected min–max | Mean paired Δ vs release | Δ sample SD | Δ min–max |
|---|---:|---:|---|---:|---:|---|
| gnm / ADE_m | 0.014369125 | 0.002647557 | 0.011849349–0.017128214 | -0.016073096 | 0.002647557 | -0.018592873–-0.013314007 |
| gnm / FDE_m | 0.026086381 | 0.005171588 | 0.023051070–0.032057741 | -0.027824883 | 0.005171588 | -0.030860193–-0.021853523 |
| gnm / positive_temporal_MAE_steps | 0.723193735 | 0.419796824 | 0.352518886–1.179048240 | -2.459966443 | 0.419796824 | -2.830641292–-2.004111938 |
| gnm / negative_category_MAE | 13.090565602 | 0.903123305 | 12.430038452–14.119692266 | -3.407931780 | 0.903123305 | -4.068458930–-2.378805116 |
| nomad / ADE_m | 0.009970107 | 0.002663875 | 0.007175758–0.012480807 | -0.049822198 | 0.002663875 | -0.052616547–-0.047311498 |
| nomad / FDE_m | 0.018219188 | 0.005187405 | 0.012866859–0.023224216 | -0.087673502 | 0.005187405 | -0.093025831–-0.082668473 |
| nomad / positive_temporal_MAE_steps | 3.014923851 | 0.135231390 | 2.894874662–3.161427766 | -0.914270659 | 0.135231390 | -1.034319848–-0.767766744 |
| nomad / negative_category_MAE | 9.448962748 | 0.518276248 | 8.857211888–9.822191000 | -7.575444192 | 0.518276248 | -8.167195052–-7.202215940 |
| vint / ADE_m | 0.020136582 | 0.001630703 | 0.019133917–0.022018200 | -0.059766925 | 0.001630703 | -0.060769590–-0.057885306 |
| vint / FDE_m | 0.035643529 | 0.002495951 | 0.034113261–0.038523723 | -0.109587420 | 0.002495951 | -0.111117687–-0.106707225 |
| vint / positive_temporal_MAE_steps | 3.834184170 | 0.154129375 | 3.668477237–3.973267287 | 1.662569389 | 0.154129375 | 1.496862456–1.801652506 |
| vint / negative_category_MAE | 8.901219974 | 0.121254356 | 8.816997528–9.040194780 | -6.167183196 | 0.121254356 | -6.251405641–-6.028208390 |

Δ=selected−same-model release on identical pairs/rules; negative means lower error. Sample SD uses all three preselected seeds(n=3), not frames/routes. ViNT has improved waypoint/category error but worse positive temporal-distance error for every adapted seed. GNM/NoMaD aggregate selected errors improve on their own release on this pilot, while within-model metric minima differ. Route-specific16 cells/model are retained in the per-model reports and all48 cells in the packet; they are not pooled into seed SD.

**Adaptation/workload limits:** ViNT uses the prior historical20epoch/4720-update procedure and its recorded dataset exposure/selection; GNM/NoMaD use the separate frozen4720-update shared sample catalog/native objectives. Equal nominal updates do not equal image/label/compute exposure. Pilot capture holds four updates at nominal12Hz (about1/3s between teacher poses), whereas prior training used4Hz; temporal/context cadence mismatch is an additional domain confound, not corrected or tuned here. Step-label MAE is not a calibrated duration estimate. Deployment is raw ViNT/GNM versus selected NoMaD EMA. ViNT/GNM use one draw; NoMaD averages four fixed coupled draws per pair, never oracle-best. These systems and adaptation procedures are not an isolated architecture comparison.

**Compute:** three1800-second reservations=5400s. Observed launcher spans10.735103358+37.548457670+29.361757427=**77.645318455s**. Saved pre-final spans total76.034163349s, not end-to-end; CUDA-active time unknown. Batch1/two warmups per role. ViNT timed forward includes state/RNG fencing; GNM native forward excludes host conversion; NoMaD includes native CPU decode/transfers. CPU preprocessing remains separately reported. Timing scopes cannot rank architecture speed or predict Orin latency.

**Integrity/retention:** strict loads/model-state gates and completed scoring/dataset transactions verify. All768 per-draw raw JSON arrays/content hashes retained externally; GNM/ViNT actions `[1,5,4]`, NoMaD `[1,8,2]`, distances `[1,1]`. Original tensor dtype is not preserved. Each completed scorer binds four artifacts plus marker/ledger; dataset binds152 artifacts. Private seal, original failed stages and independently unobserved collection SDK cleanup remain unchanged.

Per-model route/results: [GNM](PROSPECTIVE_GNM_SCORING_RESULTS_V2.md), [NoMaD](PROSPECTIVE_NOMAD_SCORING_RESULTS_V2.md), [ViNT](PROSPECTIVE_VINT_SCORING_RESULTS_V1.md). Authenticated compact packet `/home/favl/navfm-training-evidence/prospective-three-model-consolidation-v1-01/summary.json`, SHA256 `bb3f3263a29e301b41c8df86ee1d704d3e45bc037586085eb50ab944382b9938`, includes all12 checkpoint hashes/endpoints,48 route cells,12 statistic rows, source/evidence identities and compute. Ordinary arithmetic reductions may differ by one floating-point ULP from older displayed reductions; no admission threshold changed.

Next decision is a separately specified independent evaluation or authenticated plant work; these accessed-pilot outcomes do not authorize further training, collection, scoring or navigation. Raw predictions/images/geometry/seed values/weights remain external; only these two compact reports enter Git.
