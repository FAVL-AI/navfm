# Static-arrival post-close lifecycle diagnostic v1: result

**Outcome: instrumentation-limited; no camera qualification or admission.** The single attempt used the frozen commit `7bf2fa905054e1553a5ca0277ea23b1d98f8434d` and the external evidence directory `/home/favl/navfm-runtime-evidence/static-arrival-post-close-diagnostic-v1/attempt-01`. The one-shot registry is consumed. The original camera qualification FAILs and their registries remain unchanged.

## Observed stages

The child entered `SimulationApp` startup at 0.051 s after parent launch; startup returned at 5.868 s. `close()` entered at 5.877 s and returned at 36.833 s (about 30.956 s inside the call). The worker wrote its final report at 36.844 s, returned from `main()` at 36.847 s, entered the pinned CPython threading-shutdown hook at 36.849 s, and entered ordinary `atexit` at 36.854 s.

Thread snapshots showed nine Python threads after application startup: the main thread, five `ThreadPoolExecutor` workers, one `asyncio_0` worker, and two daemon `Dummy` threads. During close, snapshots showed that the executor workers had exited; the `asyncio_0` worker remained in the 30-second snapshot. At and after close return, only the main thread and two daemon `Dummy` threads were present. The threading-shutdown hook ran, and ordinary `atexit` was reached with no live non-daemon worker thread. This reduced path therefore did not stall in the observed CPython non-daemon-thread join stage.

## Exit and instrumentation limitation

The child did **not** reach a naturally observed process exit. It remained alive after the ordinary `atexit` marker. At 40.048 s, the supervisor sent the fourth scheduled `SIGUSR1` trace request. The child exited at 40.251 s with return code `-10` (signal 10), was reaped, and the 60-second deadline was not reached. No thread snapshot followed that request. The result record is `PROCESS_EXITED_NONZERO_BEFORE_DEADLINE`, `timed_out=false`, `child_reaped=true`; this is not a PASS.

The frozen protocol intended its Python `SIGUSR1` handler to remain useful during interpreter shutdown. The observed final request did not produce a handler snapshot and was followed by termination with signal 10. The evidence supports that the tracing mechanism itself ended the observation; it does not establish why the handler was no longer servicing that signal. Consequently, this run cannot determine whether the child would have exited naturally before 60 seconds, nor can it provide a post-`atexit` stack. It also cannot distinguish remaining native teardown from other process-lifetime behavior.

## Conclusion

This startup-and-close-only run reached close return, worker return, the threading-shutdown hook, and ordinary `atexit`. The call to `close()` itself took about 31 seconds. Because the diagnostic signal terminated the child about 3.4 seconds after the `atexit` marker, this run neither establishes a natural exit nor determines whether the process would have remained alive through the 60-second deadline. Camera/scene initialization remains a material difference from the failed camera run. The original cause is unresolved; no repair or camera-path qualification is established. Do not repeat this diagnostic automatically.

## Evidence integrity

Compact external evidence hashes (SHA-256):

| External record | SHA-256 |
|---|---|
| Parent terminal record | `b2aa7dca31a576f2dcdcb605d6be4e0854b052b4e6a5616c1c3c1155a6de4fb4` |
| Worker lifecycle events | `af9489c171e13e7a23e0ab38279d19b073fbdffb24b8cf1f9f16fab36264f50a` |
| Thread snapshots | `f1d28a18400d85417c91b84eafdfb9a357d51f2dcb67753f55fd3e2408230b22` |
| Worker final report | `a5cc024710c9dbea0ff7c7974b3a8c8a92c5b346650a8843f2d1ad4c6a0e75dc` |
| Parent supervisor events | `d0dada94a34a295c5cad5d8b829fc45aff8a1adb9071f09b9fad19cf6b1ae376` |
| Child stdout/stderr | `d49b1c58883de1eddae09516b81fa434f2634a94d0c5122a39adf06d97b30042` |
| Consumed one-shot reservation | `c93ac105903993be76fe6c640ebaeef21004bca382e760f7ae8318049bb6d45a` |

Raw logs, stack snapshots and process evidence remain external and were not added to Git. No scene, camera, frame capture, model, dataset, fitting or navigation was used.
