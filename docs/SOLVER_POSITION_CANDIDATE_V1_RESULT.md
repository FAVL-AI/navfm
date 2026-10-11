# Solver-position candidate v1 result

**Scientific qualification FAIL: 7/16 command holds pass. Execution/evidence integrity passed; reliable motion is not established and navigation remains NOTRUN.**

One prospective candidate at source freeze `0e9fecc0bdcca3c7513e4a702c3e64b44f081133` changed only articulation requested position iterations 32→64. It retained velocity 1, TGS, 120 Hz, native sensor, controller gains/limits, mapping, sphere/contact plant, 16 ordered command holds and every original criterion. The single 120-second-capped process completed 1200 ticks/1080 native samples; lifecycle span 25.329 seconds. No second attempt, escalation or other correction was performed.

The lifecycle records baseline 32/1, candidate 64/1, TGS, physics dt 1/120 and actual scene position clamps 1..255 (velocity clamps 0..255). Authoring and clamp admission are established by USD properties; independent native solver-iteration telemetry is not available. The original asset hash remains `0ba6ca5df86d2b8d7d631a25be1eeb57b66c28516e599a02486a14233971cb1b`. None of the authored physical drive/contact/gain parameters changed.

All 6000 five-phase telemetry events are chronologically bound to 1200 ticks, with source/DOF schema, finite clocks, same-phase clocks, 1/120 post-physics advance and row timestamps checked. All five recorded artifact hashes match, and source/input postflight passed. Requested and immediately accepted drive targets agree exactly; maximum absolute difference 0. Native rate versus the fixed same-tick pre-control body-rate projection has MAE `4.36095e-10` and maximum `1.91999e-7` rad/s across 1080 samples. This is recorded phase association, not a lag search or proof of physical timestamp simultaneity. Process exit 0/ledger COMPLETED do not imply scientific PASS.

## Unchanged command criteria

Late rates are means over the final 30 ticks; signed yaw is integrated over all 60 ticks of each hold. No best-window selection or threshold adjustment was used.

|Hold|v,w command|Late v m/s|Late yaw rad/s|Full yaw rad|Result|Failed criteria|
|---|---|---:|---:|---:|---|---|
|0|[0.1, 0]|0.099789|0.000103|0.000052|PASS||
|1|[0.025, 0]|0.024723|-0.000033|-0.000021|PASS||
|2|[0.05, 0.005]|0.050251|-0.000372|-0.000207|FAIL|rate, sign, integrated_turn, integrated_sign|
|3|[0.05, -0.005]|0.050335|0.000178|0.000036|FAIL|rate, sign, integrated_turn, integrated_sign|
|4|[0.1, 0.025]|0.100607|0.015019|0.006498|FAIL|rate, integrated_turn|
|5|[0.1, -0.025]|0.099898|-0.010799|-0.003696|FAIL|rate, integrated_turn|
|6|[0.025, 0.05]|0.026189|0.039762|0.018992|PASS||
|7|[0.025, -0.05]|0.025249|-0.044214|-0.020646|PASS||
|8|[0, 0.005]|0.000093|-0.000259|-0.000150|FAIL|rate, sign, integrated_turn, integrated_sign|
|9|[0, -0.005]|0.000067|0.000270|0.000108|FAIL|rate, sign, integrated_turn, integrated_sign|
|10|[0.1, 0.4]|0.103820|0.469770|0.216612|PASS||
|11|[0.1, -0.4]|0.103121|-0.492320|-0.231417|PASS||
|12|[0, 0.4]|0.046240|0.389841|0.175860|FAIL|translation|
|13|[0, -0.4]|0.020480|-0.320990|-0.150275|FAIL|translation|
|14|[0.025, 0.005]|0.024681|-0.000334|-0.000709|FAIL|rate, sign, integrated_turn, integrated_sign|
|15|[0.025, -0.005]|0.024735|-0.006154|-0.003124|PASS||

Stopping path 0.000712653 m passes the original 0.05 m limit. Final residual translation/yaw and exact 1080 sensor count also pass. Tracking is the failing admission check. Five small-yaw holds have wrong-sign full-hold yaw; both pure ±0.4 rad/s holds fail translation. The candidate therefore does not establish reliable small turns or pure rotation.

The historical 32-position coverage had 4/16 passes; this candidate has 7/16. That is a descriptive cross-attempt comparison, not an independently replicated estimate of an iteration effect, proof of solver convergence, or unique physical cause. Numerical trajectories can differ, and the control/plant still fails the fixed task criteria. No fresh reproduction or ViNT episode is admitted following this FAIL.

## Contact and mechanism limits

4748 reported contacts comprise four wheel/Floor pairs with 1187 records each. These are support contact reports, not 4748 collisions. No base/Floor or wall pair appears in this report. Contact forces, effective solver friction and lateral roller mechanics remain unmeasured; absence of a reported pair is not a safety guarantee. The active plant remains a four-sphere proxy with acceleration drives, not an authenticated mecanum roller-contact model.

Exact target delivery and native update-phase association do not establish realized wheel tracking or a unique downstream mechanism. Increasing position iterations alone was insufficient. The next concrete engineering decision is localization within the already saved wheel/body response, not a new launch or arbitrary tuning. Fixed reductions cover all 16 full-60 and last-30 windows. In order `[fl, fr, rl, rr]`, differential is `(fr + rr - fl - rl)/2` and common mode is `(fl + fr + rl + rr)/4`, in rad/s; body columns retain the independent body-frame evaluations. Requested and accepted rates are identical, so accepted is shown once. These are derived window means, not drive-effort/contact measurements or a calibrated no-slip model.

|Hold|Window|Accepted differential|Realized differential|Accepted common|Realized common|Body v m/s|Body yaw rad/s|
|---|---|---:|---:|---:|---:|---:|---:|
|0|full60|-0.000887|0.001227|2.500000|2.501986|0.098615|0.000105|
|0|last30|-0.000919|0.000540|2.500000|2.499502|0.099789|0.000103|
|1|full60|0.000375|0.000578|0.625000|0.625687|0.024991|-0.000043|
|1|last30|0.000235|0.000034|0.625000|0.625368|0.024723|-0.000033|
|2|full60|0.128842|-0.061463|1.250000|1.252264|0.050286|-0.000414|
|2|last30|0.150689|-0.068987|1.250000|1.254338|0.050251|-0.000372|
|3|full60|-0.035275|0.014606|1.250000|1.250030|0.050329|0.000072|
|3|last30|-0.056512|0.026822|1.250000|1.248399|0.050335|0.000178|
|4|full60|0.423097|0.291617|2.500000|2.482959|0.100080|0.012995|
|4|last30|0.449289|0.318561|2.500000|2.474949|0.100607|0.015019|
|5|full60|-0.314612|-0.177132|2.500000|2.500262|0.099861|-0.007393|
|5|last30|-0.358026|-0.224327|2.500000|2.496591|0.099898|-0.010799|
|6|full60|0.547797|0.476603|0.625000|0.600859|0.026530|0.037984|
|6|last30|0.568389|0.513533|0.625000|0.601693|0.026189|0.039762|
|7|full60|-0.479778|-0.355711|0.625000|0.612214|0.025369|-0.041292|
|7|last30|-0.481240|-0.361829|0.625000|0.610667|0.025249|-0.044214|
|8|full60|0.102545|-0.054710|0.000000|0.000242|0.000221|-0.000300|
|8|last30|0.116852|-0.073878|0.000000|0.001426|0.000093|-0.000259|
|9|full60|-0.071423|0.046360|0.000000|-0.000016|0.000059|0.000217|
|9|last30|-0.093066|0.059878|0.000000|-0.000359|0.000067|0.000270|
|10|full60|3.122815|3.100079|2.500000|2.506129|0.088669|0.433224|
|10|last30|2.472123|2.428777|2.500000|2.507373|0.103820|0.469770|
|11|full60|-3.302138|-3.269313|2.500000|2.506399|0.097091|-0.462834|
|11|last30|-2.495052|-2.440371|2.500000|2.506003|0.103121|-0.492320|
|12|full60|4.938949|4.945291|0.000000|-0.003071|0.045850|0.351720|
|12|last30|4.641063|4.643033|0.000000|-0.004514|0.046240|0.389841|
|13|full60|-3.978792|-3.985561|0.000000|0.001242|0.017445|-0.300549|
|13|last30|-4.058678|-4.062668|0.000000|0.000644|0.020480|-0.320990|
|14|full60|-0.181452|0.015522|0.625000|0.623112|0.024622|-0.001419|
|14|last30|-0.211302|0.021830|0.625000|0.618486|0.024681|-0.000334|
|15|full60|-0.298093|-0.171905|0.625000|0.624069|0.024716|-0.006248|
|15|last30|-0.293265|-0.172834|0.625000|0.624160|0.024735|-0.006154|

Holds 2/3/8/9 continue to show realized differential opposing the accepted differential in both fixed windows. Hold 14 also has a differential realization gap, while body yaw and realized differential need not share a simple no-slip sign relation. Pure-spin holds 12/13 show close differential and near-zero common-mode wheel tracking yet substantial body translation; thus close aggregate wheel-rate means do not establish faithful body response; these means do not exclude per-wheel or within-window tracking discrepancies. Hold 15 passes its body criteria despite a differential-rate gap. These two observed response paths justify separating actuator/constraint target realization from wheel/contact-to-body motion before a physical correction. They do not identify friction, motor effort, roller mechanics or another unique cause. No factor change, automatic 128-iteration trial or navigation is performed.


## Evidence and validation

External attempt: `/home/favl/navfm-runtime-evidence/solver-position-candidate-v1-01`. Read-only compact integrity reduction: `/home/favl/navfm-runtime-evidence/solver-position-candidate-v1-analysis-01/integrity_summary.json`, SHA256 `d1e538e71786327510c0de96ce715c76f61005c42bbcb7f9f7502f04e28f83d6`.

|Artifact|SHA256|
|---|---|
|attempt/lifecycle.jsonl|e7a7d626e2d133919de4d27028045a9de7fc66e5d0b033a0d42b750f051893b3|
|worker-entry.jsonl|5af2784181580a0fa54fdff1e493dd819c024fa5724dac68d69fe6ee5fa26eeb|
|attempt/imu_qualification.json|e148e2202dcde7c012932ebffff6eafec0b2833b8566711ee1565beaf18c6b51|
|attempt/imu_readings.jsonl|9665ad32a26c3f253fe5d735fdc81847a5b48e854efe6ca3892977d2ca702809|
|process.log|0cf891f5f592c4926f29ef211f69b0aaac72b7549c016d4d60f110f87c345e7e|

Five focused source/namespace/clamp controls pass; Ruff, diff checks and actual clean source/input preflight pass. Population retains 2948 prior nodes and adds five (2953 total). The namespace control executes the inserted helper in the actual separate setup pattern, addressing the review-discovered pre-launch defect. Only this source fix preceded runtime; no runtime failure was retried. All generated evidence remains external, all prior freezes/failed attempts remain immutable, and no robot, training, illumination or heldout evaluation occurred.

All-16 fixed-wheel reduction: `/home/favl/navfm-runtime-evidence/solver-position-candidate-v1-analysis-01/all16_wheel_body_windows.json`, SHA256 `491d4fe457c52fbeca839c0c834c12d1d1783287c7e6b80fb4d2f2a143abbd54`. The earlier eight-hold requested subset is preserved separately; the published table covers every declared hold.
