# Static-arrival startup-only diagnostic v1

**Scope:** one startup and close attempt with the pinned Isaac Sim 5.1.0.0
worker interpreter. No stage, scene, camera, capture, encoder, fitting,
collection, or navigation work is performed. This protocol does not repeat
or alter camera qualification.

## Frozen launch contract

The child runs from the repository root using the interpreter and Isaac
distribution bound in `configs/eval/static_arrival_startup_diagnostic_v1.json`.
The supervisor copies the parent environment and overrides only
`OMNICLIENT_HUB_MODE=disabled` in the child. It does not modify the parent
environment. Headless mode, the RayTracedLighting renderer, 320×240 launch
dimensions, and the existing IsaacApp bootstrap remain fixed. No application
experience or extension list is added or removed.

The child records only allowlisted settings: interpreter path, working
directory, Isaac distribution version, Hub mode, application arguments and
the frozen SimConfig values. It does not serialize the full process
environment. Timestamped, fsynced child events bracket Python/import startup,
`SimulationApp` construction, completion of `IsaacApp.start()`, and entry and
return from `IsaacApp.close()`. Missing return markers remain unobserved.

The child execution deadline is 30 seconds from immediately before spawn and
includes normal close and process exit. The separate cleanup reserve is at
most 10 seconds and covers TERM/KILL requests, reap, evidence verification,
and terminal recording. No retry or deadline extension is allowed. A unique
external output directory and exclusive one-shot registry record prevent
overwriting or repeating the attempt.

## Admission and interpretation

The parent records actual child exit code, timeout state, each termination
request, reap status, elapsed execution and cleanup time, event-journal
validity, and hashes for external logs. A `PASS_STARTUP_AND_CLOSE_RETURNED`
requires the post-constructor, application-start-returned, before-close and
close-returned markers, child exit 0, successful reap, no timeout, and budget
compliance. Exit 0 without a close-returned marker is reported as
`STARTUP_PASSED_CLOSE_RETURN_UNOBSERVED`, never as a complete close PASS.

The prepared worker source is hash-bound in the config; the launcher,
supervisor tests and protocol are bound by the clean full Git commit used for
the one-shot command. The IsaacApp source hash is also bound. The harmless
supervisor test exercises normal child exit, timeout termination/reaping,
output-directory refusal, and child-only environment override without
starting Isaac.

This diagnostic can establish that the pinned recipe starts and closes now.
Because the failed qualification did not preserve its effective environment
or working directory, a pass cannot identify which setting caused the
original timeout. The original camera qualification remains FAIL, and no
camera readiness follows automatically.

## Reproducibility

After the source/config/tests are committed, run once from the exact clean
commit:

```bash
python scripts/run_static_arrival_startup_diagnostic_v1.py \
  --freeze FULL_COMMIT_SHA \
  --execute-approved
```

The runner verifies the exact clean commit, bound source/interpreter hashes
and installed Isaac distribution before consuming the one-shot slot.
Runtime evidence is stored under the external root specified by the config.
