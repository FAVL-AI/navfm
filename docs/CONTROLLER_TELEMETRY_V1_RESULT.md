# Controller telemetry v1 result

Source freeze: `e03808dbc22fe485d3a9bbec1a88c16407336e78`. The explicitly authorized single 120-second-capped process completed all 1,200 ticks. Worker exit 0 / ledger COMPLETED is execution status; unchanged coverage remains **FAIL**, with 4/16 passing segments. Native initialization/readiness and count, stop distance and residual-stop checks passed. All four navigation episodes remain NOTRUN. No gains, resets, commands, thresholds or admission rules changed. No second process ran.

## Telemetry integrity

All 6,000 new events are present: exactly five phases per tick, ordered PRE_CONTROL, POST_CONTROL, REQUESTED_TARGET, ACCEPTED_TARGET, POST_PHYSICS. Sequence IDs increase; the first four share the pre-step clock and the fifth advances one 1/120-second physics tick. DOF names/indices consistently bind fl_wheel_joint, fr_wheel_joint, rl_wheel_joint, rr_wheel_joint to indices 0,1,2,3. All joint readbacks have the finite four-DOF schema. Logged body pose, world velocity and WXYZ orientation are finite with expected dimensions.

All 1,080 consumed native records match report raw records, source and controller clocks; reused scalars equal the same record's body-local z rate. There is no extra native poll. Every integral-before equals the prior tick's integral-after. All five ledger artifact hashes verify, including principal lifecycle telemetry and startup evidence. These checks establish complete recorded observations, not physical update-phase simultaneity or navigation qualification.

## Measured state and target delivery

Measured PI integral state spans −0.029821442044 to +0.038567298699. Derived formula evaluations record zero integral-clipping and zero output-clipping events. Integral values are observed program state; unclipped values and flags are explicitly derived. This rules out observed clipping in this fixed run, not controller-state interaction generally.

Requested versus immediately accepted drive-target readback has maximum absolute discrepancy **0 rad/s**. Accepted targets versus post-step realized joint velocities have maximum absolute discrepancy **0.6016884446 rad/s**. Accepted readback is an articulation API target, not measured torque or proof of physical realization. The realized velocity gap alone does not identify drive dynamics, friction, contact effects or a unique controller cause.

| Segment | Command (m/s, rad/s) | Integral before → after | Mean / max wheel target–velocity gap (rad/s) | GT yaw integral (rad) | Coverage |
| --- | --- | --- | --- | --- | --- |
| 0 | [0.1, 0] | 0.00000000 → 0.00000075 | 0.0087459 / 0.0606003 | 0.00001124 | PASS |
| 1 | [0.025, 0] | 0.00000075 → -0.00000190 | 0.0090569 / 0.1131691 | -0.00000882 | PASS |
| 2 | [0.05, 0.005] | -0.00000190 → 0.00287319 | 0.1075541 / 0.1497750 | -0.00038344 | FAIL |
| 3 | [0.05, -0.005] | 0.00287319 → 0.00027908 | 0.0297965 / 0.0636333 | 0.00011098 | FAIL |
| 4 | [0.1, 0.025] | 0.00027908 → 0.00922890 | 0.4015494 / 0.5096824 | 0.00365048 | FAIL |
| 5 | [0.1, -0.025] | 0.00922890 → -0.00338355 | 0.2678113 / 0.4268072 | -0.00004135 | FAIL |
| 6 | [0.025, 0.05] | -0.00338355 → 0.00724832 | 0.4881936 / 0.6016884 | 0.01470126 | FAIL |
| 7 | [0.025, -0.05] | 0.00724832 → -0.00563714 | 0.4864553 / 0.5662011 | -0.01273217 | FAIL |
| 8 | [0, 0.005] | -0.00563714 → -0.00303577 | 0.0530005 / 0.3783607 | 0.00023420 | FAIL |
| 9 | [0, -0.005] | -0.00303577 → -0.00611582 | 0.1960269 / 0.2408184 | 0.00058917 | FAIL |
| 10 | [0.1, 0.4] | -0.00611582 → -0.01022229 | 0.2510892 / 0.5486245 | 0.20774473 | PASS |
| 11 | [0.1, -0.4] | -0.01022229 → 0.00800281 | 0.2741318 / 0.4712861 | -0.22562559 | PASS |
| 12 | [0, 0.4] | 0.00800281 → 0.03856730 | 0.0891790 / 0.5944724 | 0.17604402 | FAIL |
| 13 | [0, -0.4] | 0.03856730 → -0.01581730 | 0.0396303 / 0.1711255 | -0.15133472 | FAIL |
| 14 | [0.025, 0.005] | -0.01581730 → -0.01088593 | 0.2443605 / 0.3299152 | 0.00045174 | FAIL |
| 15 | [0.025, -0.005] | -0.01088593 → -0.01262240 | 0.3806786 / 0.4363969 | -0.00083452 | FAIL |

Wheel-gap mean is the mean across the hold of each tick's maximum absolute four-DOF gap. Integral carryover between nonzero turn commands is directly observed; existing zero/straight reset behavior remains unchanged. Segments 2 and 3 retain GT body yaw opposite to their requested small-turn direction despite accepted API targets. Existing body/native clocks, commands and PI outputs remain preserved for timestamp-aware interpretation. No intrinsic checkpoint-quality, navigation or safety conclusion follows.


## Recorded clocks versus content phase

A fixed chronological comparison projects each PRE_CONTROL world angular velocity using that event's WXYZ body-z axis, then compares the same tick's reused native scalar. All 1,080 records are retained; there is no lag search or shifted-window optimization. Native minus pre-control body rate has MAE **3.49849994e-10**, RMS **6.01963299e-9** and maximum absolute residual **1.45165044e-7 rad/s**. Native minus POST_PHYSICS body rate remains MAE **0.008954639710**, RMS **0.028347109664** and maximum **0.355847263866 rad/s**. The recorded sensor clock trails pre-control by **0.008332862519–0.008333809674 seconds**.

This strongly supports recorded clock/update-phase semantics as the explanation for the earlier gyro/evaluation discrepancy: content agrees with the pre-control observation despite the older sensor timestamp. It does not establish hardware-level simultaneity or identify the controller/plant tracking cause. No feedback, timestamp, gain or reset repair is selected.

## Signed wheel response

Fixed full60-tick means separate common mode (four-DOF mean) from right-minus-left differential (mean of right pair minus left pair). These are joint-coordinate reductions, not a no-slip body-motion model. Full signed per-DOF means for every segment remain external. Selected fixed segments show:

| Segment | Accepted / realized common mode (rad/s) | Accepted / realized right-minus-left (rad/s) |
| --- | --- | --- |
| 2 | 1.2500000 / 1.2480552 | 0.1340456 / -0.0590183 |
| 3 | 1.2500000 / 1.2485624 | -0.0316121 / 0.0148783 |
| 9 | 0.0000000 / 0.0014062 | -0.2395527 / 0.1464326 |
| 12 | 0.0000000 / -0.0179085 | 4.7395415 / 4.7187883 |
| 13 | 0.0000000 / -0.0041532 | -4.0370854 / -4.0375366 |

Exact API target delivery and the absence of observed clipping are established in this run. Signed wheel response and body response remain distinct; a joint-coordinate differential alone cannot authenticate contact forces or no-slip kinematics.

## Validation and evidence

Exact clean source, pinned robot/API inputs and telemetry hashes passed the CPU-only preflight; the fresh output directory was absent. Five focused preparation controls passed; no completed suite was rerun for execution. Earlier offline analysis controls passed eleven tests in the clean environment after an ambient ROS plugin invocation failed before collection for missing lark. All earlier source freezes and failed attempts remain immutable.

External root: `/home/favl/navfm-runtime-evidence/controller-telemetry-v1-01`. The summary is a descriptive reduction of recorded evidence, not a newly measured artifact.

| Artifact | SHA256 |
| --- | --- |
| ledger.json | 6f20c140e78f52381d09eb6dcfca4ec2e04b9bb9899312c1172b68ad66fd60a0 |
| attempt/lifecycle.jsonl | 8b5399feea2651524fcb308c67ccf76f1348a0fdd079c7114059700ba1026756 |
| worker-entry.jsonl | 2387562e2746f56ed5905919a78940a796550b6a224a9841a65cc24b0716f8e9 |
| attempt/imu_qualification.json | 971cd8af171d8d522b069141539753b59d7d6ba66fea01f0df9fa2942b00a4d6 |
| attempt/imu_readings.jsonl | 7859b0ecd348bf7c8e05eec7fee270456f40ccd9b1e5c1d3d1c98d8e47fbd562 |
| process.log | c5aa6c47e516766444e55a573bccf12a2d6e4a7a3085824db66b7cbb41b0407d |
| telemetry-summary.json | 88e37622a9eb0121d091febf3d21d4cae4db182615e2f8aac449da037e02b748 |
| reduce-fixed-phases.py | 087bfcc8ebf1ca3725e84c28111b0b95821cf3a84e6e1ebaca7a2746e7501dfb |
| fixed-phase-reduction.json | 787cc4c7e51ae530296787d462d95024220efc69265ae0ddb84a492571b57bbf |
| reduce-signed-wheels.py | dbe867b4f950555d3f3cc63d6b574fccfac837b73b42df9715af9b8e822d90cc |
| signed-wheel-reduction.json | bdc14be2d9d697b5cae30fa2b6cc93e9e629a1ac916ea8c039bc4b8f0134bf7d |

## Decision

HALT remains in force for navigation. Complete observations establish PI state, API target delivery and realized wheel response, but not a unique cause of the body tracking gap. The narrow next decision is whether the observed signed differential/common-mode and body response warrant a versioned controller/plant intervention; the mechanism remains unresolved and no repair is selected. Any justified repair must be separately reviewed and frozen with fresh qualification under unchanged criteria. Only saved-evidence reductions were performed after the one probe; no further simulator process ran.
