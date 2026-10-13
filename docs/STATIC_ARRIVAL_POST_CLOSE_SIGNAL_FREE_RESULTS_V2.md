# Static-arrival post-close signal-free diagnostic v2 results

**Outcome: timed out; natural process exit was not observed.** The single attempt ran from frozen commit `1013457165a06037e703b8fba1a8db5cc5295cee` under the 60-second child deadline and separate 10-second cleanup reserve. The supervisor reaped the child after deadline `SIGTERM`; this is not a successful exit or camera-data admission.

The reduced startup-and-close path progressed through all worker stages:

| Event | Seconds from first child event |
|---|---:|
| Worker entry | 0.020 |
| `SimulationApp` constructor returned | 0.025 |
| `start()` returned | 5.756 |
| `close()` returned | 35.810 |
| Final report persisted | 35.819 |
| Worker main returned 0 | 35.821 |
| Parent deadline reached | 59.998 |
| Parent requested cleanup `SIGTERM` | 60.001 |
| Child reaped, return code `−15` | 60.167 |

The process therefore remained alive for about 24.18 seconds after worker main returned, until deadline cleanup. No diagnostic signals, debugger, background sampler, scene, or camera were used. The observation reproduces a natural-exit problem in this reduced startup-and-close process, but does not identify whether Python shutdown or native teardown kept it alive. It does not establish why the earlier camera run timed out. The 30.05-second `close()` duration is recorded separately from the post-worker-return interval.

The worker's final report records startup and close returning, no scene/camera/frames, and SDK cleanup as `NOT_INDEPENDENTLY_OBSERVED`. The supervisor terminal record and separate registry terminal record agree: `PROCESS_ALIVE_AT_CHILD_DEADLINE`, `timed_out=true`, `child_reaped=true`, `dataset_admission=false`. The two prior camera qualification FAILs and the signal-interrupted v1 diagnostic remain unchanged. No retry or camera qualification followed.

External evidence directory: `/home/favl/navfm-runtime-evidence/static-arrival-post-close-diagnostic-v2/attempt-01`.

| Evidence file | SHA-256 |
|---|---|
| `lifecycle_events.jsonl` | `666ff87e9140e6a594edc91d3e2fc34f411c6b5c963ac0559e62a0464d25b89f` |
| `supervisor_events.jsonl` | `ec11e39eb36d7f5ba83b9149c54a5e2f49470e5edd30faae2acc4e3f0e0af6f7` |
| `terminal_record.json` | `34194d10ae4190742adcab48f6630d20f20adf0dd0d90ca48b10c91a773c64ce` |
| `worker.stdout` | `91da577e5268fd1d429226ed13a22dd1d51bfb194bc2f50346b3df9769582760` |

No further runtime action is authorized by this result. A separate diagnostic design would be needed to distinguish interpreter shutdown from native teardown; this report makes no causal claim and does not change any existing admission criteria.
