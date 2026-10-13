# Static-arrival camera qualification results v1

**Outcome: FAIL — execution allowance timeout before the first camera frame.** This report is bound to the approved preparation freeze `51a33902d21223e3b8ff1d71896de688e25c6f00`. The single approved `attempt-01` was executed once. Its one-shot registry slot remains consumed; no retry or budget extension was made.

## Attempt and lifecycle

The frozen whole-process cap was 120 seconds, with a 90-second child execution allowance, a 10-second cleanup reserve, and a 20-second verification/finalization reserve. The parent recorded 90.032455 seconds occupied when the child execution timeout was handled. The child was terminated with return code `-15` and was reaped. The parent and registry terminal records agree and both say `FAIL`, `timeout=true`, `finalization_complete=false`, and `dataset_admission=false`. No `qualification_complete.json` marker exists.

## Camera evidence

The child `capture_report.json` remains `STARTED`, has zero frame rows, and records `shutdown_returned=false`. Therefore no native capture intervals, pose readbacks, saved images, image hashes, or per-frame camera checks were produced. The camera criteria were not evaluated; this is a startup/worker-timeout failure, not a measured RGB or pose-check failure. SDK-context return and complete SDK cleanup are unobserved.

The external worker log shows Isaac Kit extension startup followed by repeated OmniHub reconnect warnings while waiting for a per-user Hub config file. This is a correlated startup observation only; the attempt does not isolate or prove OmniHub as the cause of the timeout.

## Evidence preservation

Raw attempt evidence remains outside Git at `/home/favl/navfm-runtime-evidence/static-arrival-camera-qualification-v1/attempt-01`; the matching registry terminal record remains in the sibling `registry` directory. No images or frame metadata were created. Selected hashes:

| External file | SHA-256 |
|---|---|
| `attempt-01/attempt_start.json` | `3359653d1bb95e41462363354937fbbf9481cc891d80c9bff7b79919045c879f` |
| `attempt-01/qualification_input.json` | `ffc9d266dde489edb49be7ae8fc626bf361ac017e4d58a16e4dd3601f4d591c9` |
| `attempt-01/capture_report.json` | `dfe9b4a4c2d4b8301eacff96ed2a26d4ed17818c935dcbc12c84fa3990c9e875` |
| `attempt-01/terminal_record.json` and registry terminal | `d80fa9cf00b605d2aec7fbbdaa4e53bad39f88dd2bd7e6be8dfeec67c17970c6` |
| `attempt-01/worker.stdout` | `ad99643fecdb8527fee9aa3c5577a21887f29c09066c842f04a26a05fa414efb` |

The five-family acquisition proposal remains unapproved. This failure provides no camera-path qualification, calibration result, or arrival-performance evidence.
