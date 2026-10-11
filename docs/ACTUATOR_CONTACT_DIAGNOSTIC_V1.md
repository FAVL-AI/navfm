# Actuator/contact diagnostic v1

Status: REVIEWED SOURCE FREEZE, runtime NOTRUN. This two-worker unloaded-condition contrast tests accepted versus realized wheel response, not motion qualification or a deployment repair. The original robot asset, failed qualifications and 64-iteration candidate remain immutable.

Grounded runs first with original gravity and 32 position / 1 velocity iterations, TGS and 120 Hz physics. Pinned links initially have no PhysxRigidBodyAPI and return unknown disableGravity attributes; the documented schema default is false. Both arms explicitly apply the schema, preserve before-state evidence and author false for grounded or true for airborne. Airborne runs second with every robot rigid link's gravity disabled before initialization, floating base and initial root Z 0.30 m. Geometry, drive type/damping, target mapping and sensor lifecycle are unchanged. This removes gravity and floor support together; it does not isolate friction. No fixed-base restraint or target-time state reset is used.

Each fresh worker has a 120-second wall watchdog and exactly 960 physics ticks (8 seconds). After 120 startup ticks, four cells each have 120 zero-wheel rest ticks and 60 direct target ticks; 120 zero-wheel tail ticks follow. Grounded order is (v,w) = (.05,+.005), (0,-.4), (.05,-.005), (0,+.4), in m/s and rad/s. Airborne reverses this order. One initialization occurs per arm, not per cell. Rest-starts and recorded residual motion do not establish identical mechanical resets. Condition, process order and history are confounded; each cell has one observation.

Targets bypass PI update; the native IMU is still read once and validated, but does not affect the direct target. No gains, friction, geometry, thresholds or mapping are fitted. Requested and accepted drive targets, actual joint positions/velocities and passive body state retain the existing five-phase telemetry. Pretarget residuals are preserved at the final rest tick. Optional effort channels are separately labelled actuation-command and solver-projected joint effort; they are not pure motor-drive torque. Missing values are UNKNOWN, never zero.

Every post-step immediate contact query copies robot contact headers/data before the next step. Impulse is a vector in N s, not instantaneous force. The query completion is recorded even when empty. Airborne integrity requires all-link gravity flags, clearance above 0.10 m throughout and no robot contacts with a functioning observer. Grounded observation must demonstrate robot contacts. Contact positions, normals and impulses are copied with tick/phase provenance. Effective friction and floor force remain unmeasured. Floor/wheel support is not a collision-safety result.

Analysis is fixed before outcomes: retain all eight cells, full 60-tick and final 30-tick per-DOF accepted versus realized rate bias, MAE, RMS and maxima; signed left/right differential and common-mode means; body translation/yaw and onset residuals. Existing ground motion criteria are descriptive only; airborne body yaw is not expected to meet ground-motion criteria. Tracking failure does not halt the second arm, but integrity failure or watchdog does. No replacement, unchanged retry, automatic correction, navigation or training follows.

Run only after reviewed committed source/config freeze:

```bash
PYTHONPATH=scripts /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/run_actuator_contact_diagnostic_v1.py --freeze FULL_COMMIT --out /home/favl/navfm-runtime-evidence/actuator-contact-diagnostic-v1-01
```

All runtime evidence remains external, including partial reports, native readings, lifecycle and process logs hash-bound in the ledger after child reaping. Native reports preserve numeric rows; condition/contact metadata stays in lifecycle records.

Six focused controls pass, including execution in the preserved setup namespace and the unapplied gravity-schema case. Ruff and diff checks pass. An initial ambient ROS pytest plugin failure occurred before collection; the clean plugin-disabled invocation passed.
