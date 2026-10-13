# Controller/plant diagnostic v1 result

**Original attempt FAIL; recovered descriptive reduction completed, 0/12 cells pass. Navigation remains NOTRUN. No corrective intervention is selected.**

The single runtime attempt used freeze `81e0af0a5e09fcc7ac379ba3f93678563f519bde`, the fixed 12-cell schedule, unchanged native sensor, gains, wheel mapping, sphere plant and criteria, with a 120-second watchdog. It captured all 3120 ticks, 3000 native readings, 15600 five-phase telemetry records, 12 target onsets and 16 rest-readiness events. Its lifecycle span was 52.342 seconds. Each tick retained ordered pre-control, post-control, requested target, accepted target and post-physics observations. All five ledger-bound artifacts match their recorded hashes. Process exit 0 and ledger COMPLETED describe execution only.

The final report failed with `ValueError: nonfinite or nonnumeric evaluation sample`. Added diagnostic string/null metadata passed through the inherited final numeric-only recursive validator. The original saved rows reproduce that failure; separating only the metadata leaves all 3120 numeric payloads valid. The failed report remains immutable. Offline source `b59ddf80614db0eec4e9fc17079d69029916cade` separately validates exact typed metadata, schedule, artifact bindings, finite clocks, chronology and nested DOF schema, then applies the unchanged frozen scorer to each 60-tick target window. Its output is a derived descriptive reduction, not a retroactive PASS or replacement coverage qualification.

## Fixed target windows

Rates below are means over the final 30 ticks; yaw and distance are signed integrals over all 60 ticks. All 12 cells fail. One observation per cell, sign/mode counterbalance and two-factor direct comparisons do not provide independent replication or significance.

|Cell|Mode|v,w command|Late v m/s|Late yaw rad/s|Full yaw rad|Full distance m|Failed criteria|
|---|---|---|---:|---:|---:|---:|---|
|0|reset|[0.05, 0.005]|0.049828|-0.000684|-0.000988|0.024924|rate, sign, integrated_turn, integrated_sign|
|1|carry|[0.0, -0.4]|0.038976|-0.344369|-0.152174|0.017281|translation|
|2|direct|[0.05, -0.005]|0.049779|0.000250|-0.000039|0.024765|rate, sign, integrated_turn|
|3|reset|[0.0, 0.4]|0.021679|0.342661|0.160051|0.010479|translation|
|4|carry|[0.05, -0.005]|0.049056|-0.003047|-0.000711|0.024621|integrated_turn|
|5|direct|[0.0, 0.4]|0.032247|0.267975|0.124432|0.013810|translation, rate, integrated_turn|
|6|reset|[0.05, -0.005]|0.049670|0.000754|0.000994|0.024945|rate, sign, integrated_turn, integrated_sign|
|7|carry|[0.0, 0.4]|0.040328|0.342788|0.155087|0.017294|translation|
|8|direct|[0.05, 0.005]|0.050007|-0.000218|-0.000055|0.024909|rate, sign, integrated_turn, integrated_sign|
|9|reset|[0.0, -0.4]|0.018733|-0.367683|-0.169928|0.009737|translation|
|10|carry|[0.05, 0.005]|0.049553|0.000812|-0.000327|0.024795|rate, integrated_turn, integrated_sign|
|11|direct|[0.0, -0.4]|-0.020562|-0.318138|-0.149869|-0.012114|translation, integrated_turn|

## Measured onset and wheel response

Integral values are actual program-state readbacks, not reconstructed physical state. Reset removes inherited integral only; new integral accrues during the target. Direct cells hold zero for the conditioning window and use prescribed wheel differentials without PI target output. Rest-readiness passed the declared residual-motion criteria; it is not a full pose/contact-state reset.

|Cell|Integral before / after reset / first update|Accepted R−L mean rad/s|Realized R−L mean rad/s|
|---|---|---:|---:|
|0|0.0074949 / 0.0000000 / 0.0037212|0.344359|-0.013812|
|1|0.0385260 / 0.0385260 / 0.0317622|-4.120544|-4.067738|
|2|0.0000000 / 0.0000000 / 0.0000000|-0.040625|0.016676|
|3|-0.0260211 / 0.0000000 / 0.0063169|5.013236|5.016186|
|4|-0.0073752 / -0.0073752 / -0.0110577|-0.529715|-0.180824|
|5|0.0000000 / 0.0000000 / 0.0000000|3.250000|3.146550|
|6|0.0026476 / 0.0000000 / -0.0035484|-0.334930|-0.001479|
|7|-0.0288916 / -0.0288916 / -0.0223954|4.269502|4.245063|
|8|0.0000000 / 0.0000000 / 0.0000000|0.040625|-0.011235|
|9|0.0273622 / 0.0000000 / -0.0061775|-4.689243|-4.692869|
|10|0.0039832 / 0.0039832 / 0.0077692|0.454300|0.062994|
|11|0.0000000 / 0.0000000 / 0.0000000|-3.250000|-3.198217|

The two reset small-turn cells still have wrong-sign integrated yaw after measured integral reset to zero. Thus inherited integral alone is insufficient to explain failure; this does not establish that all PI state is irrelevant. Both isolated direct small-turn cells also fail, with realized mean wheel differential opposite the accepted target differential. This supports a downstream actuator/contact response gap under these states; it does not distinguish solver contact, drive response, geometry or another plant mechanism. All six pure-spin cells violate translation criteria, including both isolated direct cells. Direct versus conditioned cells differ in both antecedent and controller mode, so their contrast cannot uniquely identify a PI effect.

Direct target-onset linear-speed norms for cells 2/5/8/11 were respectively 0.00007595 / 0.00009019 / 0.00009482 / 0.00014858 m/s; angular-speed norms were 0.0007370 / 0.0001489 / 0.0005728 / 0.0006276 rad/s. Maximum absolute realized joint speeds were 0.001653 / 0.000478 / 0.008278 / 0.004267 rad/s. Thus “rest-start” means bounded residual motion, not exactly zero wheel/body motion or a reset contact configuration.

Requested versus accepted target maximum absolute difference is zero in all target cells. Full-window accepted and realized means retain order `[fl, fr, rl, rr]`:

|Direct cell|Accepted wheel means rad/s|Realized wheel means rad/s|
|---|---|---|
|2|1.270313, 1.229687, 1.270313, 1.229687|1.242328, 1.259355, 1.236818, 1.253143|
|5|-1.625000, 1.625000, -1.625000, 1.625000|-1.706862, 1.353927, -1.598368, 1.633943|
|8|1.229687, 1.270313, 1.229687, 1.270313|1.257778, 1.242660, 1.253425, 1.246073|
|11|1.625000, -1.625000, 1.625000, -1.625000|1.633508, -1.472992, 1.640489, -1.649443|

For all 3000 reused native readings, the fixed same-tick pre-control body-frame comparison has mean absolute residual `4.7168e-11` rad/s and maximum `4.0034e-9` rad/s. This is a recorded update-phase association, not a lag search or proof of physical clock simultaneity. There is no evidence here selecting an IMU timing repair. Final tail path is 0.000200004 m. The failed footer did not publish its contact aggregate; no collision, floor-force or safety claim is made.

## Authenticated plant and deployment scope

The authentic robot asset remains SHA256 `0ba6ca5df86d2b8d7d631a25be1eeb57b66c28516e599a02486a14233971cb1b`. The runtime stage records four active radius-0.04 m sphere wheel colliders, +Y wheel-joint axes, acceleration drives with stiffness 0 and damping 1000, and max force `3.402823466e38`. No resolved material binding was observed; effective solver friction is UNKNOWN, not zero. Original roller-style asset contact subtrees are disabled by the unchanged proxy builder. Matching wheel ordering/mapping between qualifier and deployment and these observed signs do not establish a universal mapping inversion or a unique repair.

The user-declared deployment target is Yahboom ROSMASTER M3Pro with Jetson Orin NX 16 GB; the RTX 4080 SUPER workstation performs simulation/training. Front RGB is the learned-policy input; IMU and wheel feedback are explicit low-level controller sensors. Connected hardware identity, JetPack/software versions, wheel configuration/calibration, sensor frames and measured latency remain unverified prerequisites for deployment. This task accessed no robot and performed no navigation, training, heldout or illumination evaluation.

## Evidence and validation

External acquisition: `/home/favl/navfm-runtime-evidence/controller-plant-diagnostic-v1-01`. External derived output: `/home/favl/navfm-runtime-evidence/controller-plant-offline-reduction-v1-01/derived.json`, SHA256 `3d826666f14716e78f3b562259e990d38335ee141b0abe0b9440c632c7b98ca9`.

|Acquisition artifact|SHA256|
|---|---|
|attempt/lifecycle.jsonl|4959bf515c2fd3de8be981957e508c539177a14ea4d9e439fbfd8838b4bfd197|
|worker-entry.jsonl|223342f4243bdb453fcff6d4d402bdb782e45451c14358f8f5c4d7cd1897c6b6|
|attempt/imu_qualification.json|cf7602633de7a59c74a23a0a5fbd0a58d2cc88e87be03370b3a4622837a7d4db|
|attempt/imu_readings.jsonl|08cc013f7cf482671f12667275ad52358a6a5700cd9a3b5a074f4fd94b83b8a2|
|process.log|706337d213e51be5867d202adeb0eeda3aaee71a96065314e06a66524e11f005|

Four original diagnostic focused tests and nine offline-reducer focused tests pass; Ruff and diff checks pass. The reducer includes a synthetic full 3120-row nested-schema path and rejection controls; these are not additional physical observations. An initial formatter invocation failed because the worktree lacks `.venv/bin/ruff`; the established external environment then completed formatting/validation. Test population retains all 2939 prior nodes and adds nine reducer nodes (2948 total).

The next decision is to identify a supported downstream plant mechanism using declared physical/contact assumptions and measured drive/wheel response, before proposing one factor intervention. Current evidence selects none. No gain, friction, geometry, sensor, mapping or threshold change is selected; no second runtime attempt was performed. Original coverage admission remains failed and all four navigation episodes remain NOTRUN.
