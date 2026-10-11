# Prepared controller telemetry v1 — NOTRUN

One proposed, unexecuted replay of the unchanged coverage: 1200 physics ticks, 120-second wall watchdog, the same 120 startup / sixteen ordered 60-tick commands / 120 zero-wheel tail. All native sensor setup, gains, clamps, resets, command order and coverage thresholds remain unchanged. The failed coverage and four NOTRUN navigation episodes remain immutable. No automatic launch follows offline analysis.

The passive transform records ordered tick/phase events before control, after control, requested joint targets, immediately read-back accepted targets, and post-physics realized joint velocities. It reuses the consumed native sample without another sensor poll. Actual program integral values before/after update are measured; unclipped formula values and clipping flags are labelled derived. Requested targets are bound to the preserved DOF names and wheel indices. `get_applied_actions().joint_velocities` returns drive targets; `get_joint_velocities()` returns realized joint velocities. Installed isaacsim.core.prims/impl/articulation.py methods 1715 and 1541 establish these distinct APIs. Body velocities/poses are evaluation-only and never feed the controller. Logged sample/controller/evaluation clocks preserve update ordering without claiming physical-phase simultaneity.

Every readback is recorded before finite/schema validation; invalid telemetry halts without fallback. Existing lifecycle records persist ordinary failures. No gain tuning, extra native polls, runtime retry, navigation, model import or best-window selection is permitted. Instrumentation can change execution timing; this limits causal comparisons. A future execution must use the committed exact source and all pinned inputs, with a fresh external output path; one attempt only.

Prepared command (not executed):

```
env -u PYTHONPATH /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/run_controller_telemetry_v1.py --freeze <committed-source-head> --out /home/favl/navfm-runtime-evidence/controller-telemetry-v1-01
```

Config: configs/eval/controller_telemetry_v1.json, with the robot and actual installed IMU/XForm/articulation API pins plus telemetry source digests; upstream_files is empty because this controller probe needs no model closure. Source guards reject changed instrumentation boundaries; focused checks cover read-once and chronology, schema/nonfinite rejection and derived clipping without state mutation. This is preparation only, not evidence of target delivery, wheel response or improved tracking.

The final ledger hashes all available lifecycle telemetry, startup marker, report, native-reading and process-log files after child reaping on success or failure/timeout. Five focused controls PASS, including partial-failure artifact binding. This prepared probe remains NOTRUN.
