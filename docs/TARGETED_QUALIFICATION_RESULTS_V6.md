# Targeted qualification results v6

Source freeze: cd580159bdcb373e83d380f74143fa4850e8d44d. Three once-only processes completed: the 60-second CPU import audit, 120-second/1200-tick native IMU controller qualification, and 150-second NoMaD compatibility check. All shared frozen-input preflights passed. No training, live navigation, held-out/illumination evaluation or robot episode ran. Earlier failures remain unchanged.

## Preserved diagnostic history

The initial diagnostic freeze 8b18152 failed shared configuration preflight before any worker because upstream_files was absent; versioned 2b33a88 supplied previously pinned keys without changing inputs. Its CPU import audit timed out at 60 seconds, with no exact blocking phase established. The independent initialization-only probe recorded the selected physics pose [-3,0,.06], USD fallback [0,0,0] after STOP, and restarted X approximately -1.939e-6: finite passed, XY equality failed, yaw equality passed. This was a reset/backend placement mismatch, not physical traversal.

The versioned linear CPU audit f257dee completed: 1266 objects, no import errors, three unclassified backend wrappers. Its legacy ops/classes labels were not code authentication. V6 binds actual class/MRO and method/property attribute slots, descriptor class slots and exact binary getter/setter members to pinned source; exported identity and wrapped-original identity remain required. Two substitution negatives reject an authentic method in an undeclared attribute and an authentic binary function in the wrong descriptor slot. All 11 pure controls passed; Ruff and diff checks passed. An initial test invocation failed before test collection through ambient ROS plugin loading (missing lark); the clean environment invocation passed. Population membership is 2903 nodes, retaining all 2892 prior nodes; this is membership, not full-suite execution evidence.

## Actual v6 results

| Contract | Result | Bounded evidence |
| --- | --- | --- |
| CPU import-only closure | PASS | 1266 selected loaded objects authenticated, zero unclassified, zero import errors; CUDA hidden, no model or simulator construction |
| Native IMU initialization/readiness | PASS | Authored physical-root placement retained; finite/XY/yaw predicates true; native valid, finite, fresh increasing samples at startup ticks 118/119, sensor times 1.0 and 1.0083334446 s |
| Native IMU controller tracking | PASS | All frozen tracking, stop distance, residual velocity/rate and sensor-count checks passed across seven fixed plateaux |
| Released NoMaD compatibility | PASS | Strict checkpoint load on CUDA, finite native distance/actions, 10 diffusion iterations, one sample; pre/post native dependency authentication passed |

IMU metadata was read back from actual IsaacImuSensor schema at /World/Robot/base_link/QualificationIMU: identity mount, body-local frame, period 0.008333333768 s. The probe recorded 1200 ticks and 1080 control/tail sensor readings; the 120 startup observations are separately preserved in the lifecycle trace. Seven seconds of commanded motion produced 0.725078697 m path and 0.001170944 m stopping distance. Plateau mean translation ranged 0.100152–0.106701 m/s against 0.1 m/s commands; mean body-local yaw rates were -0.0000102, 0.085871, 0.204777, 0.414096, -0.098454, -0.214414 and -0.417836 rad/s against 0, 0.1, 0.2, 0.4, -0.1, -0.2 and -0.4. All passed unchanged frozen tolerances. The 4748 contact events are retained floor/wheel support observations, not a navigation collision-rate estimate. Ground-truth pose and velocity were initialization/evaluation data only; controller feedback came from the native IMU.

NoMaD used checkpoint SHA256 70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333, torch 2.7.0+cu128/CUDA 12.8 on RTX 4080 SUPER. Observation shape was [1,12,96,96], goal [1,3,96,96], native actions [1,8,2]. Native check wall time was 1.743344 s. Pre-native authentication recorded 1089 entries and post-native 1277 entries, with fresh attestation caches; the ledger binds provenance. This establishes the released native interface on fixed inputs, not adaptation or navigation performance.

## External evidence

All raw evidence remains outside Git under /home/favl/navfm-runtime-evidence. SHA256 values:

| External relative path | SHA256 |
| --- | --- |
| dependency-import-audit-v6-01/audit.json | 3ebcc5ac3c64a193f9c7c80fc6fec4aae62c5ec90d6930ac80b726df36066465 |
| dependency-import-audit-v6-01/audit-progress.jsonl | ec68abc0c01e2d06263fdba179e58c0a78890e9c41c34f7ba766c1ccc7c4aeda |
| dependency-import-audit-v6-01/ledger.json | 0f834d8c3313fc6d52def43273fd81a3e21f1859d09eaf8807eef5506defd92a |
| imu-controller-v6-01/attempt/imu_qualification.json | 1cdd3e23f19b61f6a28d7d4a1a4ce7252f71a342cdde2c8cfdb1d84896caf536 |
| imu-controller-v6-01/attempt/lifecycle.jsonl | 8de2bd4d27ab67016ed16415eef3c3eb35484ac6fa416e1bc330e5e75d3a88ad |
| imu-controller-v6-01/ledger.json | ba1be81752817af55055bc7fc32d319b24611322f74c4794123cf2d54ea22157 |
| nomad-compatibility-v6-01/nomad.json | 88a30fd312416ea1f7d20cd1dc44d88ef505123d3ec44177aa4c8d4b03a4ccb3 |
| nomad-compatibility-v6-01/import-resolution.json | d8961787b76132c2bf5269d09809e717eafe372c3bbdb32126b316923ff2e33d |
| nomad-compatibility-v6-01/ledger.json | 6dc40bacefa97fde6aae4dd6d185eaaa3fc17735e164468c325966d9e8646711 |

These sampled controller commands and native model interfaces qualify only their declared engineering contracts. They do not establish unseen-layout navigation, correct/wrong stops, collision safety, recovery, or comparative model quality. The development navigation pair remains unexecuted; integrating the qualified controller into a separately versioned matched evaluation contract is the next decision. No further process is authorized by this report.
