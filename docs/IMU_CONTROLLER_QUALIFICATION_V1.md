# Body-IMU controller qualification v1

REVIEWED SINGLE-PROBE SOURCE FREEZE — NOT RUN. The compatibility-only freeze 00238cbbf7293e345156819a85c5576200a0fc30 remains unchanged; use a separate clean worktree at that commit for its four once-only checks. CI-runner cleanup is still unconfirmed, so no runtime is permitted now. This proposed controller contract does not enable the blocked live-development stage.

One fresh simulator process, maximum120 wall seconds and1200 physics steps at120Hz (10 simulated seconds). No model, training or navigation policy is imported. A fixed120-step zero-command settling window precedes seven120-step plateaux: forward0.1m/s with yaw0,+0.1,+0.2,+0.4,-0.1,-0.2,-0.4rad/s, then240steps stopped with PI reset and exact zero wheel targets; tail gyro readings are passive measurements only. No adaptive warmup, retry or extra probe; STOP even on PASS. The PI gains remain unchanged. This is a sampled command/sensor check, not hardware calibration or general navigation qualification.

The sensor is an actual IsaacImuSensor prim under /World/Robot/base_link with identity mount and1/120s period, angular filter size1. Installed physics IMU source is hash-pinned. Actual rigid-body parent, schema, local mount and sensor period are checked and recorded. The raw sensor interface get_sensor_reading(use_latest_data=True) exposes is_valid; cached get_current_frame is deliberately excluded. Every active controller reading must be valid, finite, from the declared source, strictly newer than its previous reading, and no more than one physics tick old (plus1µs numerical allowance); future readings fail. No root/angular-state fallback exists. Callback failures are latched, held command and wheel targets are zeroed immediately, and the main thread propagates the failure outside the native callback. All raw readings, including rejected readings, are retained externally. Invalid startup after the fixed settling window halts rather than extending conditioning.

GT root angular velocity is removed from the controller boundary. Robot pose, articulation velocity and orientation are read only after stepping for evaluation. Evaluation angular velocity is projected into body-local z using the independently measured orientation; world-z velocity is separately retained. Controller commands never depend on these evaluations. The sensor/controller boundary adds gyro feedback to a visually driven policy stack; it does not make the entire deployed system RGB-only in the literal sense. This version declares the permitted low-level gyro separately from RGB-only model perception. Sensor/controller qualification must pass before a versioned live-evaluation launcher can consume it; no additional human-approval condition is introduced.

Tracking uses the final60steps of each plateau. The existing engineering tolerance is retained for speed (absolute0.05m/s), and the existing small-turn sweep criterion for rate (max0.03rad/s or25% of command). Stopping path≤0.05m, last60step residual speed≤0.01m/s and body-local rate≤0.03rad/s. These are predeclared task/actuator margins, not selected from this probe's results. They do not guarantee a future stop classifier or unseen navigation success. Report all windows, errors,1200step path/exposure and all observed robot contacts including floor support separately; this probe does not replace the prior collision positive-control requirement.

The versioned wrapper changes exactly one named controller measurement expression in the preserved collector AST and attaches one sensor. Original source bytes are unchanged. Probe setup reuses the preserved qualification's stage/robot/drive prefix; no original command loop or GT-feedback controller is executed. The named clean source/config commit and pre/post external-input hashes are required. No source edits while running. The ledger records this sole process and preserves any failure. The new wrapper is not connected to an efficacy launcher.

The bounded executable review is complete. After confirmed cleanup, use this exact clean commit as the controller probe freeze:

```bash
/home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/run_imu_controller_v1.py --freeze "$(git rev-parse HEAD)" --out /home/favl/navfm-runtime-evidence/imu-controller-v1-01
```

The launcher reads configs/eval/imu_controller_qualification_v1.json. Raw artifacts stay outside Git. Primary API evidence: [installed-version IMU documentation](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/sensors/isaacsim_sensors_physics_imu.html). Pure tests reject invalid/stale/future/nonfinite/wrong-source readings and changed transformation boundaries without importing the simulator. No runtime outcome exists.

Validation: 15 pure focused tests pass; lint and whitespace checks pass. All 2847 prior population nodes remain, with 15 new nodes (2862 total). The bounded review resolved launcher cwd, exact zero-wheel stopped tail, latched callback failure propagation and finite validation of every evaluation sample. No simulator/model process has run. Inputs/source/config are frozen by this clean commit; runtime outcome remains NOT RUN.

For the separately authorised compatibility checks, preserve the old source identity instead of running them at this controller commit:

```bash
git worktree add --detach /home/favl/projects/navfm-compatibility-freeze 00238cbbf7293e345156819a85c5576200a0fc30
cd /home/favl/projects/navfm-compatibility-freeze
NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-admitted-20261007-02/upstream /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/run_development_qualification_v1.py --freeze 00238cbbf7293e345156819a85c5576200a0fc30 --stage compatibility --out /home/favl/navfm-runtime-evidence/development-qualification-v1-compatibility-01
```

These commands require confirmed cleanup, a new external output and an unused checkout path; they are not evidence of execution. Halt on the first failure and preserve remaining roles as NOT RUN. Compatibility outcomes do not qualify the controller, and controller outcomes do not demonstrate navigation efficacy.
