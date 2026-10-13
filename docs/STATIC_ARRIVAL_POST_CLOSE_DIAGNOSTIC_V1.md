# Static-arrival post-close lifecycle diagnostic v1

**Status: preparation freeze; no Isaac process has been launched by this revision.** This is a startup-and-close-only diagnostic derived from the preserved post-close failure diagnosis at `8f8417b`. It does not repeat camera capture and does not change either camera qualification result or registry.

## Scope and bound inputs

The worker uses the pinned Python 3.11.15 interpreter and its pinned `threading.py`, the installed Isaac Sim 5.1.0.0 `SimulationApp` source, the repository `IsaacApp` wrapper, and this commit's supervisor/bootstrap/worker source hashes. The child runs from the repository root with `OMNICLIENT_HUB_MODE=disabled` set only in that child environment. It constructs `IsaacApp(SimConfig(headless=True), fast_shutdown=False)`, performs no stage or scene construction, creates no camera, captures no frames, and makes no dataset-admission decision.

All event times use `time.monotonic_ns()` and are flushed with `fsync`. The bootstrap writes a handoff request before `execv`; worker entry records the observed handoff completion. The worker records application-start entry/return, close entry/return, final-report write entry/completion, and worker-main return. CPython's pinned `threading._register_atexit` hook records entry before non-daemon Python-thread joining; a normal `atexit` callback records entry after that threading shutdown hook returns. These markers distinguish Python lifecycle stages when emitted; they do not assert the cause of a missing marker.

Thread snapshots contain bounded thread id/native id, name, daemon/alive flags, and formatted stack frames. Stack formatting omits frame-local values. Snapshots are capped at 128 threads and 32 frames per thread. `SIGUSR1` requests this bounded Python stack/metadata snapshot. Its handler remains registered through interpreter shutdown and creates no diagnostic thread. Parent signal requests and child termination/reap observations are separately timestamped. No environment dump or credentials are recorded.

## Budget and admission

The child deadline is 60 seconds from supervisor start, including application startup and `close()`. At that deadline the supervisor records timeout and requests process-group `SIGTERM`; after at most five seconds it requests `SIGKILL` if still alive, and spends only the remainder of a maximum 10-second reap reserve waiting. Timeout remains a failure even when termination and reap succeed. A zero exit before the deadline is an observation, not a camera qualification PASS and not proof of complete SDK cleanup.

The attempt is one-shot, requires a fresh external evidence directory and an exclusive registry reservation, and always records `dataset_admission=false`. No retry, timeout extension, camera qualification, collection, inference, fitting, or navigation follows automatically.

## Harmless-child validation

Before Isaac execution, run the focused suite:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -m pytest -q tests/test_static_arrival_post_close_diagnostic_v1.py
ruff check scripts/static_arrival_post_close_diagnostic_v1.py scripts/static_arrival_post_close_bootstrap_v1.py scripts/static_arrival_post_close_worker_v1.py tests/test_static_arrival_post_close_diagnostic_v1.py tests/fixtures/static_arrival_post_close_harmless_worker.py
ruff format --check scripts/static_arrival_post_close_diagnostic_v1.py scripts/static_arrival_post_close_bootstrap_v1.py scripts/static_arrival_post_close_worker_v1.py tests/test_static_arrival_post_close_diagnostic_v1.py tests/fixtures/static_arrival_post_close_harmless_worker.py
```

The tests exercise the actual supervisor and `execv` bootstrap with a harmless in-repository child. They cover successful exit and stage records, abnormal exit, bounded timeout/termination/reap, existing output refusal, and attempt-record persistence failure. They are lifecycle tests only; they do not qualify Isaac startup, camera rendering, process teardown or SDK cleanup.

## Single diagnostic command

After the exact clean freeze is committed and pushed, run once:

```bash
/home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/static_arrival_post_close_diagnostic_v1.py \
  --freeze <full-commit-sha> \
  --out /home/favl/navfm-runtime-evidence/static-arrival-post-close-diagnostic-v1/attempt-01 \
  --execute-approved
```

The command checks the full SHA, clean worktree, source/config hashes and bound interpreter before it consumes the one-shot registry. Evidence remains under `/home/favl/navfm-runtime-evidence/static-arrival-post-close-diagnostic-v1`; no raw diagnostic output is committed.

## Interpretation limits

If the child remains alive, the result may localize the hang to an observed Python threading-shutdown hook or to a later interval, with bounded stack snapshots as available. A stack dump is a snapshot, not proof of a unique root cause. If the child exits normally, the original camera-run hang was not reproduced by a startup-and-close-only path; camera/scene initialization remains a possible difference. Neither outcome repairs or retrospectively admits the prior camera captures. SDK cleanup remains unverified unless independently observed.
