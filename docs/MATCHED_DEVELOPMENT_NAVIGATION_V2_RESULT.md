# Matched development navigation v2: coverage outcome

Frozen source: 3d9399d8abb7518253c94feb05927b82a8c68f95. The one authorized coverage process coverage-v2-0000 completed all 1200 physics ticks in 10.271399 wall seconds (120-second watchdog). Worker completion is not scientific PASS: the structured tracking gate failed, and the launcher recorded FAIL with “fixed coverage failed; navigation not admitted”. Four navigation IDs remain NOT RUN: dev-v2-release-a, dev-v2-adapted-b, dev-v2-adapted-c and dev-v2-release-d. No checkpoint navigation comparison, retry, replacement or threshold revision occurred.

## Measured gate

Native sensor initialization/readiness completed; 120 startup observations and 1080 subsequent native readings are preserved. The five checks were tracking FAIL, stop distance PASS, residual speed PASS, residual yaw PASS and sensor count PASS. All 16 ordered half-second segments were scored under the frozen final-half and full-hold rules: four passed, twelve failed. Earlier v6 one-second qualification remains unchanged; its result does not establish this shorter/smaller-command coverage.

| Segment | Command v / w | Final-half mean v / w | Full-hold yaw rad | Target yaw rad | Gate |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.1 / 0 | 0.100133 / -0.000012 | 0.000011 | 0.000000 | PASS |
| 1 | 0.025 / 0 | 0.025158 / -0.000034 | -0.000009 | 0.000000 | PASS |
| 2 | 0.05 / 0.005 | 0.049895 / -0.000928 | -0.000383 | 0.002500 | FAIL: rate,sign,integrated_turn,integrated_sign |
| 3 | 0.05 / -0.005 | 0.049902 / 0.000317 | 0.000111 | -0.002500 | FAIL: rate,sign,integrated_turn,integrated_sign |
| 4 | 0.1 / 0.025 | 0.099413 / 0.010192 | 0.003650 | 0.012500 | FAIL: rate,integrated_turn |
| 5 | 0.1 / -0.025 | 0.099048 / -0.001025 | -0.000041 | -0.012500 | FAIL: rate,integrated_turn |
| 6 | 0.025 / 0.05 | 0.023765 / 0.035344 | 0.014701 | 0.025000 | FAIL: rate,integrated_turn |
| 7 | 0.025 / -0.05 | 0.023637 / -0.032994 | -0.012732 | -0.025000 | FAIL: rate,integrated_turn |
| 8 | 0 / 0.005 | -0.000055 / 0.000320 | 0.000234 | 0.002500 | FAIL: rate,integrated_turn |
| 9 | 0 / -0.005 | -0.000104 / 0.001252 | 0.000589 | -0.002500 | FAIL: rate,sign,integrated_turn,integrated_sign |
| 10 | 0.1 / 0.4 | 0.104919 / 0.447492 | 0.207745 | 0.200000 | PASS |
| 11 | 0.1 / -0.4 | 0.103038 / -0.472964 | -0.225626 | -0.200000 | PASS |
| 12 | 0 / 0.4 | 0.042390 / 0.367317 | 0.176044 | 0.200000 | FAIL: translation |
| 13 | 0 / -0.4 | 0.020833 / -0.331244 | -0.151335 | -0.200000 | FAIL: translation |
| 14 | 0.025 / 0.005 | 0.024745 / 0.000837 | 0.000452 | 0.002500 | FAIL: rate,integrated_turn |
| 15 | 0.025 / -0.005 | 0.023906 / -0.001956 | -0.000835 | -0.002500 | FAIL: rate,integrated_turn |

Rate means use only the declared final 30 ticks; signed yaw integrates all 60 ticks. Segments 0, 1, 10 and 11 passed. All six +/- .005 rad/s segments failed, including reversed measured mean/integrated direction at segments 2, 3 and 9. The .025/.05 rad/s moving turns also failed rate/integral criteria. Pure +/- .4 rad/s segments 12/13 passed yaw criteria but failed forward-speed residual bounds, with final-half means .042390/.020833 m/s versus zero commanded forward speed. These are sampled proxy-controller behaviors under the fixed order, not an isolated friction, sensor, PI or actuator cause.

The stopped tail had .000210251 m path (bound .05m). Total sampled path was .397184754 m, with eight commanded-motion seconds across the sixteen holds, plus one startup and one stopped second. All 4748 recorded contacts include the floor; they are retained support/contact-update observations, not 4748 independent collisions or a navigation safety rate. No obstacle-navigation exposure occurred.

## Timing and controller evidence

The controller consumed each native measurement before its corresponding physics step; the independent body-local GT rate was recorded after that step. Across all 1080 paired raw/evaluation entries, native age at control was .008332863–.008333810 seconds (mean .008333333), and evaluation followed control by .008333334 seconds. Evaluation therefore followed the native acquisition by .016666196–.016667143 seconds. The paired absolute gyro-minus-later-GT difference had mean .008954640 rad/s and maximum .355847264 rad/s. These are time-offset differences, not simultaneous sensor accuracy measurements, and do not isolate the failure mechanism. Original raw timestamps and values remain available externally.

Recorded PI outputs ranged -1.306867052 to +1.310361035 rad/s against the unchanged +/-1.5 output limit; no recorded output reached that limit. Integrator state and actual wheel-target readbacks were not recorded, so integral saturation/sign and realized actuator targets cannot be authenticated from this attempt. The fixed source's wheel-target formula is provenance, not measured target readback. Opposite-sign corrective PI effort during command transitions is not itself proof of a defect.

| Segment | Mean PI output | Min / max PI output |
| --- | --- | --- |
| 0 | -0.000025 | -0.000977 / 0.001943 |
| 1 | 0.000012 | -0.000524 / 0.000763 |
| 2 | 0.016498 | 0.010545 / 0.023113 |
| 3 | -0.003891 | -0.009238 / 0.002748 |
| 4 | 0.064176 | 0.051001 / 0.077187 |
| 5 | -0.039843 | -0.059107 / -0.015588 |
| 6 | 0.083927 | 0.050783 / 0.100034 |
| 7 | -0.078735 | -0.108016 / -0.046991 |
| 8 | -0.006501 | -0.015088 / 0.028861 |
| 9 | -0.029483 | -0.036180 / -0.022679 |
| 10 | 0.395087 | 0.315033 / 0.787370 |
| 11 | -0.407727 | -1.306867 / -0.310687 |
| 12 | 0.583328 | 0.491724 / 1.310361 |
| 13 | -0.496872 | -1.013503 / -0.387212 |
| 14 | -0.032828 | -0.054445 / 0.301653 |
| 15 | -0.055707 | -0.063104 / -0.048762 |

## Validation and external evidence

The source freeze followed one bounded protocol/source review and corrective readback. Sixteen focused controls passed; Ruff/diff and Frank-only staged attribution/credential checks passed. The clean frozen-input, installed IMU/XFormPrim source, finite-manifest and cleanup preflights passed before runtime. Population membership retains all 2903 prior nodes and adds 16 (2919); no full-suite claim is made. All older source freezes and failed evidence remain unchanged. No raw records, images, weights or generated runtime artifacts were committed.

Evidence root: /home/favl/navfm-runtime-evidence/matched-development-v2-01. SHA256:

| Relative file | SHA256 |
| --- | --- |
| ledger.json | 54067a9db859910ff1137267438e002ca819459f7df58f6c425a5ea9b33de959 |
| coverage-v2-0000/attempt/imu_qualification.json | 971cd8af171d8d522b069141539753b59d7d6ba66fea01f0df9fa2942b00a4d6 |
| coverage-v2-0000/attempt/lifecycle.jsonl | d7d3b7bc50a7745dd7f18f2ceb4bc06ec8f534a9af1ff93a3fda897dd2b1928a |
| coverage-v2-0000/attempt/imu_readings.jsonl | 7859b0ecd348bf7c8e05eec7fee270456f40ccd9b1e5c1d3d1c98d8e47fbd562 |
| coverage-v2-0000/process.log | fb411915b5c62c3a9de2c56f3ea9197b066b2d4a2bd8c10412d9bfae75b44420 |

The decision is HALT before the four checkpoint episodes. The smallest next decision is an offline alignment of saved native sample timestamps with same-time ground-truth evaluation rows, retaining unmatched samples and inspecting commands, matched gyro/evaluation rates and recorded PI outputs across failed small-turn transitions. Any reconstructed state must be labelled derived rather than measured; unrecorded controller targets and integral state cannot be authenticated. No additional diagnostic was performed for this report, and this recommendation implies no new runtime, gain or threshold change. The evidence does not compare released versus adapted ViNT navigation quality.
