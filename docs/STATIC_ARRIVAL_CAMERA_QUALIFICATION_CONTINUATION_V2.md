# Static-arrival camera qualification continuation v2

**Status: prospective amendment; review required; not executed.** The v1 qualification FAIL, its consumed registry, evidence, frame schedule and camera criteria remain unchanged. This continuation uses a separate v2 registry and a new external attempt directory. No Isaac process or camera capture ran during preparation.

## Source finding and decision

The pinned worker distribution is `isaacsim==5.1.0.0`. Its installed `isaacsim/simulation_app/simulation_app.py` source is bound in the v2 configuration by absolute path and SHA-256. The source sets `DEFAULT_LAUNCHER_CONFIG["fast_shutdown"]` to `True`, documents that setting as exiting the process immediately, and forwards the setting as `--/app/fastShutdown=...`. `SimulationApp.close()` defaults to `wait_for_replicator=True, skip_cleanup=False`; its documented shutdown path ends in `shutdown_and_release_framework()`. The project `IsaacApp.start()` passes its extra launch arguments through to `SimulationApp`; its default call did not override `fast_shutdown`. Its `close()` calls `self.app.close()` and clears the handle only after that call returns.

The earlier startup-only run observed `before_close`, no `close_returned`, child exit 0 and successful reap under that default. The installed source makes process termination during that configured shutdown an expected possibility. The source does not prove that the call returned or that all SDK resources were cleaned up.

The v2 worker explicitly passes `fast_shutdown=False`. The pinned API documents this setting as shutting down each extension, and `close(skip_cleanup=False)` as graceful shutdown with full cleanup. This describes the requested shutdown path; it does **not** guarantee that Python returns from `close()` or independently prove SDK cleanup. The setting is the smallest source-supported launch correction, not evidence that the previous process behavior was intended. The prospective amendment retains v1's **normal close-return admission requirement**: if graceful close does not return, the attempt remains FAIL even if its pre-close capsule is complete. Even when it returns, SDK resource cleanup remains `NOT_INDEPENDENTLY_OBSERVED`.

## Frozen continuation contract

The existing three-reference/five-query scene-0 schedule, camera configuration, lighting, warm-up, four-step held poses, all eight image/metadata checks and the 120-second whole-process cap are reused unchanged. The failed v1 attempt and registry are not reused. The child bootstrap sets `OMNICLIENT_HUB_MODE=disabled` only in that child and changes its working directory to the repository root; it does not alter global settings.

After the eighth frame has passed its existing checks, and **before** SDK close, the worker atomically persists a completion capsule containing the ordered frame records, schedule/source/input identities and hashes for the eight images and metadata files. The parent verifies this capsule and re-verifies each artifact. Capsule completion means only that the camera measurements were durably recorded. Overall qualification additionally requires the post-close capture report with `shutdown_returned=true`, child exit code 0, no timeout, successful reaping, unchanged source/input bindings, verified artifacts and a completed parent/registry marker transaction. Abnormal exit, timeout, missing return marker, capsule/write failure or finalization failure is FAIL even if frame measurements were complete. Dataset admission remains false. Parent-observed normal return and process exit do not prove complete SDK cleanup.

The protocol keeps the v1 resource split: up to 90 seconds for worker execution including close, 10 seconds for process cleanup/reaping, and 20 seconds for parent verification/finalization, all inside the 120-second cap. The cap begins at runner-script entry after Python startup, as in v1. No automatic retry or extension is permitted.

The harmless-child tests exercise the actual v2 parent transaction with a fixture worker: successful close-return disposition, complete measurements without a close-return marker, missing measurement capsule, abnormal child exit, child timeout, final marker persistence failure, deadline crossing during final artifact verification, and production capsule persistence failure. The parent checks the whole-process deadline after artifact verification and again after its final marker write; a crossing revokes the completion marker and records a failed terminal transaction. The test-only timeout shortens the child allowance; the executable v2 configuration remains bound to the unchanged 120-second v1 cap. These tests do not qualify Isaac, rendered RGB or shutdown behavior.

The bounded technical review completed on the source/configuration/test delta. It identified the post-verification deadline edge and the missing direct capsule-write failure test; both are addressed and covered by the focused suite. No camera or Isaac runtime was invoked. Review-runtime identity/settings could not be independently verified.

## Review and execution boundary

The bounded review covers only the installed shutdown-option interpretation, the v2 launch delta, pre-close evidence persistence, parent/worker separation and harmless-child lifecycle controls. Reviewer model identity/settings must be recorded as requested versus observed; they do not substitute for empirical camera evidence.

After review and publication, the single prospective command is:

```sh
PYTHONPATH=src /home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/static_arrival_camera_qualification_v2.py --freeze FULL_REVIEWED_COMMIT_SHA --out /home/favl/navfm-runtime-evidence/static-arrival-camera-qualification-v2/attempt-01 --execute-approved
```

This preparation does not authorize that command. It requires the exact clean reviewed commit and the explicit execution approval enforced by the CLI. A pass would qualify only this tested scene-0 camera capture and graceful-close path. It would not qualify the five-family acquisition, visual calibration, navigation, motion or SDK resource cleanup.
