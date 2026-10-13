# Static-arrival camera qualification v2 result

**Outcome: FAIL; one authorized attempt, no retry.** The bounded review was completed before execution from the prepared continuation at `eac742e5eedf6ea0936709b700146e255b762118`. This resolves the status wording in the protocol: “review required; not executed” describes its state at freeze, not its state at the time of this result. No execution source or frozen configuration was changed for this report.

## Attempt and measurements

The exact clean freeze, source/configuration hashes, eight-frame schedule, fresh `attempt-01` directory and unused v2 registry passed preflight. The approved runner used the child-only Hub setting, repository working directory and `fast_shutdown=False`. The attempt occupied **90.220 seconds**. It did not exceed the **120-second whole-process cap**, but the worker did not exit within its **90-second capture-and-child-exit allowance**.

The worker persisted a complete pre-shutdown measurement capsule. All **8/8** reference/query frames passed the existing capture verifier: saved RGB dimensions and finiteness, image/metadata identity and hashes, same-snapshot rendering metadata, strictly ordered native timestamps, requested and float32-represented pose binding, and actual pose readback checks. The native rendering times increased from 0.875 to 2.625 seconds in seven 0.25-second intervals. All 16 image/metadata artifact hashes in the capsule were rechecked. No evaluator labels were present.

The capture report records that `SimulationApp.close()` returned, and records `shutdown_returned=true`. The subsequent child process did not exit before the worker allowance expired. The supervisor timed it out; the child’s observed exit code was **−15**, and it was reaped. Thus the SDK close-return criterion was observed, but the required successful child exit was not. SDK resource cleanup remains independently unverified.

## Admission and interpretation

Overall qualification remains **FAIL**. The attempt registry is consumed; the parent and registry terminal records show `FAIL`, `timeout=true`, child exit `−15`, `child_reaped=true`, `whole_process_deadline_exceeded=false`, and `dataset_admission=false`. No `qualification_complete.json` marker exists. The complete capsule establishes completed measurements only; it does not override the failed child lifecycle or admit the data.

The worker log shows extension shutdown activity and an `AttributeError` from a menu callback after the stage context became unavailable. This is an observed shutdown-time exception, not proof that it caused the process to remain alive. The preserved evidence does not localize the lingering process to a specific extension, callback, or SDK cleanup operation. Do not retry unchanged, extend the budget, or infer successful cleanup.

The original v1 FAIL and consumed registry remain unchanged. This result qualifies neither a passing camera-qualification transaction nor full-family acquisition feasibility. No family acquisition, encoder inference, fitting, scoring or navigation followed.

## External evidence

Raw evidence remains outside Git at `/home/favl/navfm-runtime-evidence/static-arrival-camera-qualification-v2/attempt-01`; registry records are in its `registry` subdirectory.

| Evidence file | SHA-256 |
|---|---|
| `capture_report.json` | `a88bbfc87cb47bce219e0db24237299564b9725f6cf0b7221368997e3e21139a` |
| `measurement_complete.json` | `1c9a235b2a250668c820424ff631c41f2d4d6692ec40536a3def25e922a7050f` |
| `terminal_record.json` (attempt and registry terminal) | `8e4ca7660e53ad43ba3b6386bd0d8abf235df1cbac871210ff4310ac785ee63c` |
| `worker.stdout` | `593185dc7e06aac6d34963b4a40c1709511e6fbd4804abf1d920ddac39aaa746` |
