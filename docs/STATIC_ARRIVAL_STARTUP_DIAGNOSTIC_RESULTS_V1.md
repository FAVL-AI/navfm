# Static arrival startup diagnostic v1 results

## Outcome

The single startup-only diagnostic from freeze `6d2972238fb365ff0055f540ac250f87f3f6ebca` started the pinned Isaac application within budget. The child exited with code 0 and was reaped; no timeout or termination request occurred. The measured execution interval was 8.033 seconds and total occupied time, including cleanup, was 8.037 seconds.

The worker recorded `application_start_returned` and `before_close`, but no `close_returned` marker. The terminal status is therefore `STARTUP_PASSED_CLOSE_RETURN_UNOBSERVED`, not a complete start-and-close pass. A zero process exit does not establish that the application close call returned. This diagnostic establishes that the pinned launch recipe starts now; it does not prove that Hub mode alone caused the earlier timeout because the failed invocation's effective environment was not recorded and this recipe also fixes the working directory.

## Frozen scope and evidence

The run used the bound worker interpreter and application bootstrap, repository-root child working directory, and child-only `OMNICLIENT_HUB_MODE=disabled`. It constructed no scene, captured no camera frames, and ran no model inference. The 30-second execution deadline and 10-second cleanup reserve were respected.

Runtime evidence is external and remains at:
`/home/favl/navfm-runtime-evidence/static-arrival-startup-diagnostic-v1/attempt-01/`.
The attempt reservation and original camera qualification failure were preserved. Evidence hashes and detailed event records are in the external attempt capsule; no runtime logs or generated data are included in this repository.

## Decision

Do not treat this result as camera qualification and do not automatically retry shutdown or camera capture. The original camera qualification remains FAIL. Any future camera qualification requires its own explicit authorization and must address the unobserved close-return marker without changing frozen camera criteria.
