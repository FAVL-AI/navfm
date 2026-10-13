# Targeted qualification repairs v3

REVIEWED SOURCE FREEZE, NOT RUN. Twelve pure focused tests passed; bounded static review corrections are resolved. Preserve all v1/v2 source bytes, failed attempts and original limits. Two independent once-only contracts: IMU first, 120 seconds/1200 physics ticks; NoMaD alone, 150 seconds after independent continuation if IMU fails. No navigation, training, installation, upgrades or robot experiment.

## Native IMU lifecycle

Installed Isaac 5.1 test_orientation_imu creates the sensor before PLAY. Official documentation states that sensors are created on PLAY and moving a sensor during simulation invalidates it: https://docs.isaacsim.omniverse.nvidia.com/5.1.0/sensors/isaacsim_sensors_physics_imu.html . The v2 worker created its sensor after PLAY, then teleported the robot. These are plausible lifecycle causes, not demonstrated causes of the saved invalid reading.

The v3 wrapper preserves the initial stage/articulation setup, places the robot while no sensor exists, records the pose/clock, STOPs, constructs and enables the sensor, then restarts PLAY and reinitializes the articulation. Pose equality across restart is required (1e-6 m/rad); this is initialization/evaluation ground truth, never controller feedback. Sensor enabled/schema/rigid-parent/identity mount/period readbacks are required; returned Python initialization does not itself prove native attachment. The existing 120 zero-command startup ticks are the only warmup. Every startup native reading is preserved separately, with NaN/Inf encoded as explicit numeric tags for evidence only while original values reach strict validation; the last two (ticks118/119) must pass independent finite/valid/fresh/increasing-time guards before any active command. Invalid early warmup records are never fed to controller or substituted. No extra adaptive steps, cached read fallback or ground-truth gyro is admitted. Tracking commands, gains, thresholds and zero-wheel stop remain unchanged.

## Confirmed embedded module alias

A single authorised torch-only object inspection found that the module named torch._C._dynamo.autograd_compiler is the exact object stored under torch._C._dynamo.compiled_autograd. The authenticated binary was /home/favl/miniforge3/envs/isaac/lib/python3.11/site-packages/torch/_C.cpython-311-x86_64-linux-gnu.so, SHA256 8a272d68cbbf6206a63a587844803bf46ad87c0407d206368af2c4cf63135f57. V3 admits only that explicit alias; exact nested identity and frozen parent binary path/hash remain mandatory. Other source/namespace/version/native checks remain unchanged. Foreign binary, altered binary and wrong alias object are rejected. No model was constructed by the diagnostic.

Static evidence is external at /home/favl/navfm-runtime-evidence/pr2-resource-contract-20261010/operator-setup/v3-static-repair-evidence.json. Configuration pins its current digest and the relevant installed native API/test source identities. This records current observations, not a historical independent attestation.

## Execution after review and named freeze

Use /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python with scripts/run_imu_controller_v3.py --freeze EXACT_COMMIT --out /home/favl/navfm-runtime-evidence/imu-controller-v3-01. Only after separate continuation, use the same interpreter with scripts/run_nomad_compatibility_v3.py --freeze EXACT_COMMIT --out /home/favl/navfm-runtime-evidence/nomad-compatibility-v3-01. Guarded CI setup paths must remain absent. All raw records remain external; failed attempts halt their contract with no retry. A compatibility PASS is not navigation evidence; a controller PASS only qualifies this fixed probe.
