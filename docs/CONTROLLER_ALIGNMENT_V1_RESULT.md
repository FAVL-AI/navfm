# Offline controller alignment v1 result

Source freeze: `e0aa83190bbe922591d414b5187a403e1aeb80f5`. One standard-library CPU analysis completed; no simulator, model, training or navigation process ran. The prior coverage admission remains FAIL (4/16 segments passed) and all four checkpoint-navigation episodes remain NOTRUN. No gain, tolerance, command or failure classification changed.

## Fixed join and evidence coverage

The fixed 1e-6-second join matched all 1,080 native records uniquely. Neither side has exact duplicate groups or ambiguous candidates. No native record is unmatched; 120 evaluation rows are unmatched: ticks 0–117 and 1198–1199. All sixteen acquisition-time hold windows have 60 matched records, split into 30 transition and 30 settled records. There are 34 acquisition/consumption segment crossings, including startup/tail boundaries. Acquisition and controller-consumption tick/segment/command and their separate PI outputs are retained in the external analysis; no segment membership is shifted to improve agreement.

The matched recorded-timestamp body-local z residual (native minus matched GT) has signed bias −2.72084089046e-7 rad/s, MAE 0.008954601689 rad/s, RMS 0.028347109359 rad/s and maximum absolute error 0.355847263707 rad/s. The original nonsimultaneous control-versus-later-evaluation residual has MAE 0.008954639710, RMS 0.028347109664 and maximum 0.355847263866 rad/s. Thus this fixed timestamp alignment does not remove the aggregate discrepancy. Matching recorded clocks does not establish physical update-phase simultaneity. These statistics do not isolate native sensor error, evaluation timing semantics, PI state, contact dynamics or actuator response.

## Acquisition-time windows

Rates are rad/s; signed yaw integrals are radians. Each native integral below uses only the matched acquisition-time window, not command-consumption indices. Complete commanded and GT integrals are independently retained. Transition and settled MAEs use the frozen first30 and last30 ticks, never a best window.

| Segment | Command (m/s, rad/s) | Command yaw | Complete GT yaw | Matched native yaw | First30 MAE | Last30 MAE | PI means in consumption-command windows first30 / last30 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | [0.1, 0] | 0.00000000 | 0.00001124 | 0.00002685 | 0.0003829 | 0.0003027 | -0.0000511 / 0.0000015 |
| 1 | [0.025, 0] | 0.00000000 | -0.00000882 | -0.00001607 | 0.0003094 | 0.0002634 | 0.0000036 / 0.0000199 |
| 2 | [0.05, 0.005] | 0.00250000 | -0.00038344 | -0.00037775 | 0.0003976 | 0.0004500 | 0.0134765 / 0.0195194 |
| 3 | [0.05, -0.005] | -0.00250000 | 0.00011098 | 0.00012679 | 0.0002001 | 0.0002968 | -0.0011554 / -0.0066260 |
| 4 | [0.1, 0.025] | 0.01250000 | 0.00365048 | 0.00364576 | 0.0036809 | 0.0021100 | 0.0583819 / 0.0699704 |
| 5 | [0.1, -0.025] | -0.01250000 | -0.00004135 | -0.00007911 | 0.0007570 | 0.0012478 | -0.0280576 / -0.0516286 |
| 6 | [0.025, 0.05] | 0.02500000 | 0.01470126 | 0.01449979 | 0.0059294 | 0.0068398 | 0.0802441 / 0.0876101 |
| 7 | [0.025, -0.05] | -0.02500000 | -0.01273217 | -0.01246852 | 0.0027054 | 0.0037988 | -0.0746810 / -0.0827887 |
| 8 | [0, 0.005] | 0.00250000 | 0.00023420 | 0.00020783 | 0.0002404 | 0.0001342 | -0.0082562 / -0.0047451 |
| 9 | [0, -0.005] | -0.00250000 | 0.00058917 | 0.00108654 | 0.0001015 | 0.0022560 | -0.0263185 / -0.0326484 |
| 10 | [0.1, 0.4] | 0.20000000 | 0.20774473 | 0.20835538 | 0.0198424 | 0.0257137 | 0.4589638 / 0.3312096 |
| 11 | [0.1, -0.4] | -0.20000000 | -0.22562559 | -0.22827652 | 0.0243900 | 0.0129149 | -0.4901830 / -0.3252700 |
| 12 | [0, 0.4] | 0.20000000 | 0.17604402 | 0.17837004 | 0.0378149 | 0.0518402 | 0.5980912 / 0.5685651 |
| 13 | [0, -0.4] | -0.20000000 | -0.15133472 | -0.15202088 | 0.0513604 | 0.0504506 | -0.4920107 / -0.5017334 |
| 14 | [0.025, 0.005] | 0.00250000 | 0.00045174 | 0.00030531 | 0.0012210 | 0.0009241 | -0.0293676 / -0.0362886 |
| 15 | [0.025, -0.005] | -0.00250000 | -0.00083452 | -0.00079872 | 0.0055837 | 0.0073588 | -0.0543712 / -0.0570429 |

Full/first30/last30 signed translation integrals, residual bias/RMS/maxima and recorded output extrema remain in the external analysis. Recorded PI output is a controller command, not measured wheel velocity or accepted drive-target readback. Actual integral state and wheel targets were not recorded; neither is reconstructed or authenticated here. A small signed residual bias does not imply small instantaneous error: the absolute and RMS statistics remain material, especially in larger-yaw segments.


Selected fixed segments 2/3/9/12/13: acquisition-window endpoints are reported below without searching for extreme samples. Consuming PI output belongs to the later consuming update; its command may cross the acquisition segment boundary.

| Segment / endpoint | Acquisition tick / consumption tick | Native / matched GT (rad/s) | Consuming command | Consuming PI output (rad/s) |
| --- | --- | --- | --- | --- |
| 2 / first | 240 / 242 | -0.00088675 / -0.00087600 | [0.05, 0.005] | 0.01145038 |
| 2 / last | 299 / 301 | -0.00019369 / -0.00137581 | [0.05, -0.005] | 0.00140545 |
| 3 / first | 300 / 302 | -0.00035294 / -0.00019369 | [0.05, -0.005] | 0.00140979 |
| 3 / last | 359 / 361 | 0.00170378 / 0.00064804 | [0.1, 0.025] | 0.05100083 |
| 9 / first | 660 / 662 | 0.00104981 / 0.00090313 | [0, -0.005] | -0.02376989 |
| 9 / last | 719 / 721 | 0.06058766 / 0.00145143 | [0.1, 0.4] | 0.73954774 |
| 12 / first | 840 / 842 | 0.09730725 / -0.18424682 | [0, 0.4] | 0.79260251 |
| 12 / last | 899 / 901 | 0.09487467 / 0.34300551 | [0, -0.4] | -0.78186814 |
| 13 / first | 900 / 902 | -0.13208762 / 0.09487467 | [0, -0.4] | -0.56383627 |
| 13 / last | 959 / 961 | 0.01253509 / -0.34331217 | [0.025, 0.005] | -0.05444505 |

For these same fixed segments, first30 / last30 RMS residuals (rad/s) are: 2: 0.0005070 / 0.0005894; 3: 0.0002666 / 0.0003730; 9: 0.0001499 / 0.0108070; 12: 0.0662277 / 0.0685943; 13: 0.0668234 / 0.0783416.

## Provenance and validation

Eleven focused controls PASS, including duplicate/ambiguous/unmatched retention, fixed-lag rejection, cross-boundary membership, signed units, partial-window statistics, frame and finite-value guards. Ruff and diff checks PASS; population 2,930 retains all 2,919 prior nodes. An initial ambient test invocation failed before collection because a ROS plugin required missing lark; the clean environment passed. No completed broader suite was repeated.

External output: `/home/favl/navfm-runtime-evidence/controller-alignment-v1-01/analysis.json`.

| Evidence | SHA256 |
| --- | --- |
| Preserved input imu_qualification.json | 971cd8af171d8d522b069141539753b59d7d6ba66fea01f0df9fa2942b00a4d6 |
| Frozen analysis script | de71ef1b7e27c3b197fb7c3c6c3e0168831c4e0b6d79adbc6c2795957acbe703 |
| analysis.json | a1b45faf6636b3a721e4177bcfb57215ce6dad6bf373885a07bf1bf62b510c70 |

## Decision

The offline result does not justify navigation admission or gain changes. All attempts and failed gates remain immutable. If a further controller probe is needed, its smallest useful scope would record measured PI integral state, accepted drive targets and realized wheel velocities alongside native/GT timestamps and fixed transitions, under a separately frozen finite protocol. `get_applied_actions().joint_velocities` is a drive-target readback; `get_joint_velocities()` is realized joint velocity. They are different observations. This report launches no probe and makes no checkpoint-quality or safety claim.
