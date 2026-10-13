# Static-arrival post-close signal-free diagnostic v2

**Status: preparation freeze.** This is one startup-and-close observation, authorized after the v1 diagnostic's periodic trace signals interrupted observation. It preserves the prior camera qualification failures and does not consume their registries.

## Scope and bound inputs

The worker uses the bound Python 3.11.15 interpreter, Isaac Sim 5.1.0.0, the pinned `SimulationApp` source and this revision's worker, supervisor, bootstrap, and `IsaacApp` wrapper. The bootstrap sets the child working directory to the repository root and disables OmniHub only in the child environment. The worker constructs `IsaacApp(SimConfig(headless=True), fast_shutdown=False)`, then calls `start()` and `close()`. It does not create a stage, scene, camera, or dataset.

The child writes flushed monotonic lifecycle events at worker entry, before and after application construction, start and close, final-report persistence, and worker-main return. The parent records child start, passively polls for process exit, records the observed return code, and records termination/reaping only if the deadline requires cleanup. There are no diagnostic signals, debugger attachments, stack samplers, or background diagnostic threads before the deadline. `SIGTERM` and, if required, `SIGKILL` are cleanup actions after timeout only; they never count as successful exit.

## Budget and interpretation

The child deadline is 60 seconds from supervisor start and includes startup, close, report writing, and natural process exit. A separate cleanup reserve is at most 10 seconds. Deadline expiry is a failure even when cleanup reaps the child. A normal zero exit before the deadline means only that this reduced startup-and-close path exited naturally; it does not explain the earlier camera-run timeout or establish camera qualification, dataset admission, or complete SDK cleanup.

The attempt uses a separate one-shot registry and a fresh external evidence directory at `/home/favl/navfm-runtime-evidence/static-arrival-post-close-diagnostic-v2/attempt-01`. It cannot admit data and has no automatic follow-up.

## Harmless-child validation

Run the focused suite before the Isaac invocation:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python -m pytest -q tests/test_static_arrival_post_close_signal_free_v2.py
ruff check scripts/static_arrival_post_close_signal_free_v2.py scripts/static_arrival_post_close_worker_v2.py tests/test_static_arrival_post_close_signal_free_v2.py tests/fixtures/static_arrival_post_close_signal_free_harmless_worker.py
ruff format --check scripts/static_arrival_post_close_signal_free_v2.py scripts/static_arrival_post_close_worker_v2.py tests/test_static_arrival_post_close_signal_free_v2.py tests/fixtures/static_arrival_post_close_signal_free_harmless_worker.py
```

The harmless subprocess tests exercise the actual supervisor and `execv` bootstrap. They verify passive observation of a child that remains alive briefly after its final marker and exits naturally, bounded timeout cleanup, abnormal exit, and refusal to reuse an existing attempt directory. They do not qualify Isaac, camera rendering, SDK cleanup, or physical behavior.

## Single execution command

After committing and pushing the exact clean freeze, run once:

```bash
/home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/static_arrival_post_close_signal_free_v2.py \
  --freeze <full-commit-sha> \
  --out /home/favl/navfm-runtime-evidence/static-arrival-post-close-diagnostic-v2/attempt-01 \
  --execute-approved
```

The launcher checks the exact commit, clean worktree, bound source/configuration and interpreter before consuming its registry. Preserve all resulting process records externally. Do not retry or extend the budget if the attempt fails.
