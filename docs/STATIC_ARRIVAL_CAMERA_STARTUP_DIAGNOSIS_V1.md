# Static-arrival camera startup diagnosis v1

**Outcome: startup configuration mismatch identified as a plausible, testable
cause; root cause remains unproven.** No simulator was launched and no camera
criteria, registry record, or prior result was changed.

## Failed attempt

The single attempt bound to freeze
`51a33902d21223e3b8ff1d71896de688e25c6f00` remains **FAIL**. Its terminal record
reports a 90.032-second worker allowance, timeout, child exit `-15`, successful
reap, incomplete finalization, and no dataset admission. The capture report is
still `STARTED`, with zero frames and `shutdown_returned=false`; no completion
marker exists.

The last explicit startup marker is `omni.client-1.3.0 startup` at 0.111 s.
OmniHub reconnect warnings begin at 5.229 s while waiting for a per-user Hub
configuration file. The log contains no `app ready` or `Simulation App Startup
Complete` marker. Therefore the last demonstrated stage is Omni Client
extension startup; return from `SimulationApp(launch)` is the first
unconfirmed boundary. Deferred imports, stage creation, camera setup and frame
capture were not demonstrated. The warnings are correlated evidence, not proof
that Hub alone blocked startup.

The external worker log SHA-256 is
`ad99643fecdb8527fee9aa3c5577a21887f29c09066c842f04a26a05fa414efb`.
Attempt evidence remains at
`/home/favl/navfm-runtime-evidence/static-arrival-camera-qualification-v1/attempt-01/`.

## Comparison with the most recent successful camera launch

The successful known-fixture camera run is preserved at
`/home/favl/navfm-training-evidence/prospective-offline-v2-qualify-01/`.
Its ledger reports PASS, child exit 0, no timeout, child reaped, and 23.291 s
occupied. Its process log records `app ready` at 3.741 s and `Simulation App
Startup Complete` at 5.452 s. The process-log SHA-256 is
`d6ae856673554d7f534f519eacf6db71513bd58fd4b966fd9b3c268c16b1c1fa`.

The bound Isaac worker interpreter path is the same in both launch contracts:
`/home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python`.
The failed freeze binds its SHA-256 as
`2cfeb15bca9b4483886e787a5a0f7b86f44e1644ac45b003957e2211ac1c748a`; the
successful run's versioned config names the same path. The failed config
records Isaac Sim 5.1.0.0; the successful log shows Kit 5.1 and its base
Python experience extension at 5.1.0. The `src/navfm/isaac/app.py` bootstrap
is byte-identical between the two source freezes. Both use headless 320×240 camera capture and
the `RayTracedLighting` default. Their simulation rates differ (16 Hz failed,
12 Hz successful), but rate configuration occurs after `SimulationApp`
returns, so it does not explain the unconfirmed constructor boundary.

There is one relevant launcher-contract difference. The successful frozen
launcher explicitly set `OMNICLIENT_HUB_MODE=disabled` for its child and set
the child working directory to the repository root. The failed launch's
supervisor copies the parent environment and adds only its private nonce; it
does not pin that Hub variable and does not pass a child `cwd`. The failed log's
Hub reconnects are consistent with an effective mode that permits Hub use,
but the exact failed child value and working directory were not persisted.
Thus this is a concrete configuration mismatch between the launch recipes,
not a proven causal diagnosis.

Both app sources omit an explicit Kit experience path; the failed run's
selected experience is not recorded. The successful log shows the base
Python experience extension starting, but the exact selected experience is
likewise not bound in its ledger. Do not claim an exact experience match.

## Runtime records versus current workstation state

For the failed run, the frozen config records the worker interpreter and hash,
Isaac distribution version, renderer/camera settings, and compatibility
branch. The supervisor source shows that the child inherited the then-current
parent environment. No run-time allowlisted environment snapshot or explicit
child working directory was recorded. These missing historical values cannot
be recovered from the current shell.

At diagnosis time, this shell had `OMNICLIENT_HUB_MODE` unset and was in
`/home/favl/projects/navfm-research-planning`. Those are current-session
observations only; they do not establish the failed launch's values. No
credentials or full environment dump were read or published.

## Narrow proposed diagnostic; not executed

If a separately authorized startup-only diagnostic is approved, use the exact
bound worker interpreter and source with the repository root as `cwd`, and set
only the child variable `OMNICLIENT_HUB_MODE=disabled`. Give this separate
diagnostic a 30-second end-to-end child deadline, including normal close; this
is a diagnostic cap, not an extension of the failed qualification budget.
Keep the renderer, `omni.client`, RTX, Replicator and camera dependencies
enabled. Record the
effective child variable, `sys.executable`, working directory, Isaac/Kit
version and explicit launch arguments from a strict non-secret allowlist.
Write durable markers immediately before and after `SimulationApp(launch)`
and after `IsaacApp.start()`. Perform normal close, with no stage, camera,
capture or dataset work. A startup pass would show that this pinned startup
recipe can complete; it would not retrospectively change
the original FAIL or by itself prove Hub was the original cause.

NVIDIA documents `OMNICLIENT_HUB_MODE=disabled` as the mode that does not use
Hub ([Omniverse Client Library documentation](https://docs.omniverse.nvidia.com/kit/docs/client_library/latest/index.html)).
The project also has a prior frozen Isaac runner using this child-only setting.
This proposal leaves the Omni Client extension and rendering/camera stack
enabled; it disables Hub use only for the diagnostic child. No environment,
cache, service, extension, or network setting was modified during diagnosis.

## Scope and decision

This read-only comparison used the frozen launcher/configuration sources,
published reports, and the two preserved process logs. Skill-retrieval tools
were unavailable; technical interpretation was checked against the frozen
project precedent and NVIDIA's primary documentation. No tests were run
because no source code changed. The consumed registry and all earlier
qualification outcomes remain untouched. Camera readiness remains
unestablished.

Next decision: separately authorize the proposed bounded startup-only
diagnostic. Do not retry camera qualification or extend its budget on the
basis of this report.
