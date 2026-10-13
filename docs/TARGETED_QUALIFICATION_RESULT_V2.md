# Targeted qualification result v2

Both independently authorised once-only attempts failed at their frozen eligibility boundaries. IMU startup completed and the Python sensor initializer returned, but its first native reading was invalid; sensor validity is NOT QUALIFIED and tracking is NOT ASSESSED. NoMaD failed the authenticated embedded-module origin guard before native model construction or checkpoint loading; compatibility remains NOT ESTABLISHED. No training, navigation, illumination, held-out or robot experiment ran. Neither failure was retried or reclassified.

## Source and sequence

Both attempts used clean freeze 85c047cf7a52bf5348cb000de7b84b021bb0d32d and the commands in TARGETED_QUALIFICATION_REPAIRS_V2.md. The three CI-runner cleanup paths were absent. IMU ran first with its unchanged 120-second watchdog and 1200-tick maximum; the separately admitted NoMaD process retained its 150-second watchdog. Original 00238cbb compatibility and 9358263 controller outcomes remain immutable. No source changed during either attempt.

## IMU outcome

The worker-entry, Isaac import, application creation, stage creation and Python sensor initializer markers were saved with fsync. The Python sensor initializer returned at simulation time 0.01666666753590107. At simulation time 1.0166667196899652, the first reading guard raised `ValueError: invalid IMU source/reading`. The preserved record has the exact declared source /World/Robot/base_link/QualificationIMU, valid=false, sensor time 0.0, controller time 1.0166667196899652 and angular velocity [0,0,0]. Thus the recorded rejection is an invalid native reading, not an observed source-name mismatch. The zero-valued invalid fields are not stationary-motion measurements. No successful first-sample marker exists.

The report preserves 120 evaluation rows and the observed IsaacImuSensor schema, identity mount and period 0.008333333767950535. These startup observations do not qualify gyro validity or tracking: no valid control sample reached the tracking plateaux and no active tracking command was assessed. A returned Python initializer does not establish native sensor activation. The process exited with a FAIL report before the wall watchdog. The changed Hub environment coincided with startup completion in this attempt; the different prior launch and instrumentation prevent a sole-cause claim. The cause of the invalid native reading remains UNKNOWN. Static inspection identifies sensor creation after PLAY and native attachment/enable/update readiness as hypotheses for a future versioned diagnosis; none is established by this attempt. The live-navigation wrapper remains unqualified and disabled.

## NoMaD outcome

Pinned dependency-file preflight completed and the worker reached the import boundary. Both its pre-native and finally provenance checks rejected `embedded dependency identity mismatch: torch._C._dynamo.autograd_compiler`. The parent recorded FAIL and hash-bound import-resolution.json. No native nomad.json was produced; checkpoint loading, finite native outputs and CUDA model compatibility remain NOT ESTABLISHED.

This is an authenticated-origin eligibility failure. Static inspection suggests that PyTorch registers embedded modules by their __name__, which may differ from their attribute path (compiled_autograd versus autograd_compiler); an overstrict object-path guard is a hypothesis, not a verified cause. The saved error does not isolate whether binary identity or nested-object identity caused the rejection; it does not demonstrate a foreign dependency, checkpoint incompatibility or completed dependency-resolution validation. No package was installed or upgraded, no dependency path was broadened, and no further worker was launched.

## Evidence and validation

All nine artifacts remain external under /home/favl/navfm-runtime-evidence/imu-controller-v2-01 and /home/favl/navfm-runtime-evidence/nomad-compatibility-v2-01. The identity inventory is /home/favl/navfm-runtime-evidence/pr2-resource-contract-20261010/operator-setup/research-qualification-result-evidence-v2.json, SHA256 9e2bc114f547e6ed82f3aa14c2042ec6daef4c1985f7b18da752a6901ae7814c. This is a current evidence identity record, not historical independent attestation.

| Artifact | SHA256 |
|---|---|
| IMU ledger.json | b3b2f5bf054595a4a65921526fb0ed025022827228666b84bea77984c9df044b |
| IMU imu_qualification.json | 4cfe5adb39fd215a0760fdbbd0ae3cb5422ea13f16ea65518e23d5ddf51f97b0 |
| IMU imu_readings.jsonl | 862300f0e38ac8f1925689a58520e89345f004a8f7f5b53728fba60885842089 |
| IMU lifecycle.jsonl | 499dd71a5356d8e3810408307d707dc99dcbb88d4c1693dde72cec57ae7ba235 |
| NoMaD ledger.json | 7d0ce32d9da7691f8fa0c66807b2db0f7000459ec905983828ae5712bf3e8e59 |
| NoMaD import-resolution.json | eb3ba8c5fedef6d1c1cbe377452a3596933dd8f5f238813b2e9a2b8ab335c469 |

Nine pure focused tests and lint/whitespace checks passed before the source freeze; 2871 declared population nodes retain all 2862 predecessors. No completed test suite was repeated for result-only documentation. Next decisions require separate versioned, evidence-based fixes for native sensor acquisition and embedded-module provenance, with review before any revised attempt. This report authorises no retry or live evaluation. Raw outputs, logs and weights remain outside Git.
