# Static-arrival post-close process-exit diagnosis v1

**Status: read-only diagnosis; no runtime launched.** The v1 and v2 camera qualification FAILs, consumed registries, and verified v2 eight-frame capsule remain unchanged. The v2 evidence is preserved externally at `/home/favl/navfm-runtime-evidence/static-arrival-camera-qualification-v2/attempt-01`; its compact result is [here](STATIC_ARRIVAL_CAMERA_QUALIFICATION_RESULTS_V2.md).

## Observed event order

1. The v2 capsule records all eight frame measurements and 16 image/metadata artifact hashes before SDK shutdown.
2. The final capture report records `shutdown_returned=true` and `status=PASS`. In the worker source, those values are set only after `with IsaacApp(...)` exits; its `__exit__` calls `IsaacApp.close()`, which calls `SimulationApp.close()`.
3. The worker's final report write completed and is readable. The child remained alive beyond the 90-second worker allowance. The supervisor marked timeout, terminated the process group with SIGTERM under its cleanup path, observed exit code `-15`, and reaped the child. Occupied time was 90.220 seconds, within the 120-second whole-process cap. No completion marker was written.
4. The Kit log records extension shutdown messages through approximately 41.963 seconds and then an `AttributeError` in the GUI file-menu callback when `omni.usd.get_context()` returned `None`. These are Kit-relative log timestamps; they are not aligned to the parent monotonic clock or to a durable close-return timestamp. The exception is observed, but its relationship to the long-lived child is unknown.

The evidence establishes that the Python worker passed the context manager and wrote its final report, then failed to exit before the parent deadline. It does **not** locate the stall between completion of the final atomic write, return from `main()`, Python interpreter finalization, and native SDK teardown. The parent record has child-start monotonic time, overall elapsed time, timeout, exit status and reap status, but no durable close-return, signal-request, or final-write event timestamps.

## Source inspection

The v2 worker and bootstrap contain no explicit `atexit` handlers, Python thread creation, or executor. The bootstrap `execv`s the worker, so it has no post-worker wrapper cleanup. `IsaacApp.__exit__` calls `close()`; that method stops the timeline, calls the Kit close, and clears `self.app` only if close returns. The pinned `SimulationApp.close(wait_for_replicator=True, skip_cleanup=False)` stops/waits for Replicator when needed, closes the stage, then calls native `shutdown_and_release_framework()`. Its source documents `skip_cleanup=False` as graceful shutdown with full cleanup, but does not document a Python-process-exit or thread-join guarantee. It also has a SIGINT handler; the observed supervisor termination was SIGTERM.

The bound worker interpreter is Python 3.11.15. Its `threading.py` documents that interpreter shutdown calls registered threading-exit hooks before waiting for non-daemon threads. No thread inventory or Python stack was captured in this attempt, so this is a possible stage to inspect, not evidence that a thread caused the stall. Native thread state is not exposed by the inspected Python sources.

Source identities inspected:

- `SimulationApp` source SHA-256: `7cbaa6f00e935a6f14bf1c28ec0db089fd924e931f3b0deee07a822f9b7d0090`
- Bound Python `threading.py` SHA-256: `f8b8d9ebd040e1373d76e73c23c683f7c7c204add96bf9d8d9c21ac751cf5252`

## Conclusion and smallest useful diagnostic

No specific source-supported lifecycle correction is established. Do not switch to forced process exit, treat termination as success, extend the timeout, or remove the child-exit veto. The menu callback exception alone does not justify disabling that extension or changing the renderer.

If further diagnosis is authorized, use one startup-and-close-only attempt with the same bound interpreter, child working directory, child-only Hub setting, `fast_shutdown=False`, and unchanged parent deadlines. Construct no scene and capture no camera frames. First validate the lifecycle logger and timeout/reap path with a harmless child. For the Isaac child, durably record monotonic markers before/after `SimulationApp` construction, close entry/return, final report write entry/return, and the top-level worker entrypoint return. At the close-return boundary, record live thread names, IDs, daemon flags, and bounded Python stacks. On the pinned CPython 3.11.15 runtime, add a diagnostic-only pre-nondaemon-join hook snapshot if its behavior is verified with the harmless child; capture a small, fixed number of additional stack snapshots during the existing 90-second worker window. The parent should record its deadline, SIGTERM/SIGKILL requests, and reap timestamps separately. Keep all traces external and cap their size.

These observations would distinguish a stall before worker return from interpreter thread joining or later native teardown. They still would not prove complete SDK resource cleanup. No camera retry or capture admission follows automatically.
