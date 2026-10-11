# Targeted qualification result v3

Both independently authorised once-only contracts failed before their measurement boundaries. IMU initialization integrity failed before native readings; NoMaD authenticated dependency provenance failed before native model construction. No training, navigation, illumination, held-out or robot experiment ran. Every previous source freeze and failed attempt remains unchanged; there were no retries.

Both once-only attempts used clean source freeze 77a1912d2239617b61e4e64b80a216ea5a9f848f and the commands in TARGETED_QUALIFICATION_REPAIRS_V3.md. CI setup paths were absent; source/configuration remained unchanged during execution. IMU retained its 120-second watchdog/1200-tick maximum and NoMaD its separate 150-second child watchdog.

## IMU initialization outcome

FAIL: `ValueError: initial pose changed across sensor restart`. Fifteen fsynced lifecycle records establish Isaac import, application/stage startup and initial placement at simulation time 0.01666666753590107. STOP reset the simulation clock to 0.0; the Python sensor initializer returned at 0.0 and enabled readback was true, with native attachment explicitly NOT_YET_PROVEN. The last successful marker was BEFORE_RESTART_PLAY, followed by the pose-preservation guard failure.

Zero evaluation rows and zero raw IMU readings were produced. Sensor validity, readiness and tracking are NOT ASSESSED; no active tracking command was evaluated. The failed guard rejects nonfinite poses or disagreement beyond 1e-6 m/rad. Its exception does not distinguish those branches, and before/after poses were not saved on this failure path. Therefore displacement cannot be quantified and the exact cause remains UNKNOWN. The combined initialization integrity requirement failed qualification; this is not evidence about sensor performance. A STOP/PLAY hard reset or reset-state restoration is a static hypothesis, not a demonstrated cause. The next minimal evidence correction would record tagged-safe before/after poses and each finite/XY/yaw predicate before the guard, without changing its thresholds. No sensor fallback, threshold change, additional warmup or retry occurred. The live wrapper remains unqualified.

## NoMaD provenance outcome

FAIL: `ImportError: unverifiable loaded dependency origin: torch._VF`. Both pre-native and finally provenance checks record this rejection. The exact autograd_compiler/compiled_autograd alias no longer appears as the first error, but full authenticated dependency resolution is still NOT ESTABLISHED. Pinned torch/_VF.py lines20–31 deliberately replace sys.modules with a VFModule instance storing vf=torch._C._VariableFunctions without an independent __file__. This explains a legitimate object shape the guard does not handle; the actual rejected object was not authenticated by this attempt. The next minimal evidence correction would record its class/code origin and binary-member identity before rejection. This error does not establish a foreign dependency or checkpoint incompatibility. No native nomad.json was produced: strict checkpoint loading, CUDA model execution and finite native outputs remain NOT ESTABLISHED. No dependency upgrade, ambient path admission or retry occurred.

## External evidence identity

All artifacts remain under /home/favl/navfm-runtime-evidence/imu-controller-v3-01 and /home/favl/navfm-runtime-evidence/nomad-compatibility-v3-01. The current identity inventory is /home/favl/navfm-runtime-evidence/pr2-resource-contract-20261010/operator-setup/research-qualification-result-evidence-v3.json, SHA256 1ea2f5a0130441d44e1f91d0422cb8d28a6b3e3cb0ec58ca42afd86b94fc0a4d. It lists 8 preserved files; this is current evidence identity, not historical independent attestation.

| Artifact | SHA256 |
|---|---|
| IMU imu_qualification.json | 8f64219992a2c1b155eb5e4784f6236ec633c4df5ac0b9727da638345f068083 |
| IMU lifecycle.jsonl | 38e9a7bafa5206987c8e1357f01536093a7591beac2b057f3ec1aa21a7cdef23 |
| IMU ledger.json | ab755c206e40c3e615f240ac43eef1da8367622bdcc1cfcb4b45ec3b37578362 |
| NoMaD import-resolution.json | 8d0a430f70d26ad4a1b61294a32b50ec073f60a1ea18afaa247c7f67325eb4d5 |
| NoMaD ledger.json | d068bf947d7c88383e0e07529d10932d61f54a99b64435250c344b211cec0b26 |

## Validation and next boundary

Twelve pure focused tests, lint and whitespace checks passed before freeze. The declared population 2883 retains all 2871 predecessors. Result-only documentation does not repeat completed tests. Any later sensor initialization revision must first preserve the required pose/readiness evidence and be separately versioned/reviewed; no retry or live evaluation is authorised by this report. All raw artifacts remain external.
