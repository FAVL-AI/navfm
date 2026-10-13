# Isaac Sim post-close process-survival issue package v1

**Status: prepared, not submitted.** This package summarizes the bounded signal-free diagnostic from commit `1013457165a06037e703b8fba1a8db5cc5295cee`. It preserves all earlier outcomes and makes no code-fix or root-cause claim.

## Suggested issue title

Standalone Python process remains alive after `SimulationApp.close()` returns with `fast_shutdown=False` (Isaac Sim 5.1.0.0)

## Summary

In a fresh standalone child process using the pinned Isaac Sim Python environment, the project wrapper's `close()` returned, the worker wrote its final report, and worker main returned `0`. The process nevertheless remained alive for roughly 24.18 seconds after worker-main return. A parent supervisor observed it still alive at the 60-second deadline, sent `SIGTERM` only for bounded cleanup, and reaped it with return code `-15` at 60.167 seconds. Natural process exit was not observed.

The worker constructs no task-specific USD scene, robot, camera, or dataset. The SDK's default `create_new_stage=True` does create its default empty stage during startup. Therefore camera construction is not necessary for this observed process-survival symptom. The run does not show whether the original camera-qualification timeout had the same cause. It also does not identify whether interpreter shutdown, a native resource, or another process-lifetime condition kept this process alive.

## Runtime identities recorded during the attempt

| Component | Recorded identity |
|---|---|
| Python | CPython `3.11.15`; `/home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python`; SHA-256 `2cfeb15bca9b4483886e787a5a0f7b86f44e1644ac45b003957e2211ac1c748a` |
| Isaac Sim | Distribution `5.1.0.0`; startup log reports application version `5.1.0` |
| Kit | `107.3.3+production.229672.69cbf6ad.gl`; kernel `206.6+release.9587.07f17b1b.gl` |
| OS/kernel | Ubuntu `22.04.5 LTS` (Jammy); kernel `6.8.0-138-generic` |
| GPU/driver | NVIDIA GeForce RTX 4080 SUPER; driver `580.178.04`; Vulkan |
| CUDA | No CUDA version was recorded for this attempt |

These are the attempt's recorded values, not a claim about current host state.

## Minimal reproduction and launch settings

The bound child used the repository root as its working directory and set `OMNICLIENT_HUB_MODE=disabled` only in the child. It launched headless with `fast_shutdown=False`, created no task-specific scene/camera, called `IsaacApp.start()` followed by `IsaacApp.close()`, and then returned from worker main. The SDK default created an empty stage. The generated Kit command selected `isaacsim.exp.base.python.kit`, passed `--/app/fastShutdown=False`, `--/app/installSignalHandlers=0` and `--no-window`, and used the pinned installation's extension folders.

Source-equivalent core:

```python
from navfm.isaac.app import IsaacApp, SimConfig

if __name__ == "__main__":
    app = IsaacApp(SimConfig(headless=True), fast_shutdown=False)
    app.start()
    app.close()
```

The actual attempt used `scripts/static_arrival_post_close_bootstrap_v1.py` and `scripts/static_arrival_post_close_worker_v2.py`; it emitted fsync-backed monotonic markers around wrapper construction, start, close, final-report persistence, and worker return. The parent passively polled process exit. No diagnostic signal, debugger, or sampling thread was used before the deadline.

## Measured event sequence

Times below are seconds from the first child lifecycle event, using the preserved monotonic records:

| Event | Time |
|---|---:|
| `IsaacApp` wrapper constructor returned | 0.025 |
| `IsaacApp.start()` returned | 5.756 |
| `IsaacApp.close()` entered | 5.761 |
| `IsaacApp.close()` returned | 35.810 |
| Final report persisted | 35.819 |
| Worker main returned `0` | 35.821 |
| Parent child deadline | 59.998 |
| Cleanup `SIGTERM` requested | 60.001 |
| Child reaped, exit `-15` | 60.167 |

**Event-label clarification:** the source event names `simulation_app_constructor_enter` and `simulation_app_constructor_return` refer to the project `IsaacApp.__init__` wrapper, not the SDK `SimulationApp.__init__`. The pinned wrapper's `IsaacApp.start()` invokes the SDK constructor. Its completion occurred before the `start()` return marker at 5.756 seconds, but was not separately bracketed. The external event bytes and their hashes have not been altered.

Sanitized excerpts from the external startup output include:

```text
| Driver Version: 580.178.04 | Graphics API: Vulkan
| 0 | NVIDIA GeForce RTX 4080 SUPER | ...
| OS: 22.04.5 LTS (Jammy Jellyfish) ubuntu, Version: 22.04.5, Kernel: 6.8.0-138-generic
[5.757s] Simulation App Shutting Down
```

The Kit log records `App Version: '5.1.0', Kit Version: '107.3.3+production.229672.69cbf6ad.gl'`. `close()` return, worker return, process exit, and cleanup are separate observations. The attempt ended in timeout and `SIGTERM`; it was not a successful process exit, camera qualification, data admission, or independent proof of SDK cleanup.

## Source and evidence identities

| Item | SHA-256 |
|---|---|
| Installed `isaacsim.simulation_app` source | `7cbaa6f00e935a6f14bf1c28ec0db089fd924e931f3b0deee07a822f9b7d0090` |
| Project `src/navfm/isaac/app.py` wrapper | `27a94026c4b6a370971a34f5e7d7ee8674aebcf4aa97e2c96299d62df6694b87` |
| Signal-free worker v2 | `c45a3f6776c2083c722c9b09a563becb340f37a7a804e3ea5d65ca14c80a0281` |
| Signal-free supervisor v2 | `3b820bf0739b831b2b140aef895997d19794b6c32d0fdc7a3fc34ef1c2abed6a` |
| Bootstrap v1 | `7a6c0cd80a45edfc4baa7bf397525779af34be28e7f509228c395daf112f8bf4` |
| Frozen v2 config | `33869a56df6a59ae19b09f1d0e9223720d5c36b34de596a91d1dcf8976981d8d` |
| External Kit log | `afb75043df5229f8cd241208e2f2427be33156e45f5f16ff8d1d900311d6c9f9` |
| External lifecycle events | `666ff87e9140e6a594edc91d3e2fc34f411c6b5c963ac0559e62a0464d25b89f` |
| External supervisor events | `ec11e39eb36d7f5ba83b9149c54a5e2f49470e5edd30faae2acc4e3f0e0af6f7` |
| External terminal record | `34194d10ae4190742adcab48f6630d20f20adf0dd0d90ca48b10c91a773c64ce` |
| External worker stdout | `91da577e5268fd1d429226ed13a22dd1d51bfb194bc2f50346b3df9769582760` |

Raw logs and runtime evidence remain external at `/home/favl/navfm-runtime-evidence/static-arrival-post-close-diagnostic-v2/attempt-01`; the issue package contains only sanitized excerpts and hashes.

## Pinned shutdown implementation inspected

In the pinned project wrapper, `IsaacApp.start()` creates the SDK `SimulationApp`, then performs its post-launch setup. `IsaacApp.close()` stops the timeline, calls the SDK app's `close()`, and clears the wrapper reference only after that call returns.

The pinned SDK `SimulationApp.close()` source stops/waits for Replicator as applicable, disables capture-on-play, closes the current stage when possible, shuts down the Tracy profiler if loaded, disables logging, then calls `shutdown_and_release_framework()`. The `fast_shutdown` value is passed as a Kit setting. NVIDIA's 5.1 API documentation describes `fast_shutdown=True` as immediate process exit and `False` as shutting down each extension; `close()` documents `skip_cleanup=False` as graceful cleanup. The observed run used `fast_shutdown=False`, and its wrapper `close()` returned. Source inspection alone does not identify the later process-lifetime blocker.

## Public NVIDIA records checked

- NVIDIA's Isaac Sim 5.1 release notes identify Kit SDK `107.3.3` and list generic fixes for a shutdown hang and a hang on exit. They do not give a reproducer or symptom signature matching this post-worker-return process survival. This is related release context, not confirmation of this issue: [Isaac Sim 5.1 release notes](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/overview/release_notes.html).
- The [5.1 `SimulationApp` API documentation](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/py/source/extensions/isaacsim.simulation_app/docs/index.html) documents the `fast_shutdown` and `close()` behavior described above.
- Official [Isaac Sim issue #586](https://github.com/isaac-sim/IsaacSim/issues/586) reports an application crash/segmentation fault in a container on Ubuntu 24.04 with an RTX 4090 and driver 595.58.03. That is not this observed alive-after-worker-return timeout.
- The NVIDIA forum topic [“How to keep a standalone script running after calling SimulationApp.close()”](https://forums.developer.nvidia.com/t/how-to-keep-a-standalone-script-running-after-calling-simulationapp-close/331754) concerns Isaac Sim 4.0–4.5 and the inverse behavior: `close()` terminates a session the author wanted to keep open. It is not a match.

No exact matching public NVIDIA issue/support record was located in this bounded search. The release-note entries are too general to infer that the installed source should or should not exhibit this result.

## Suggested questions for NVIDIA

1. Is natural process exit expected after `SimulationApp.close()` returns when `fast_shutdown=False` in a standalone Python child using this 5.1.0.0 / Kit build?
2. Is there a supported cleanup or shutdown sequence after `shutdown_and_release_framework()` for a child whose Python main has returned but whose process remains alive?
3. Which additional runtime artifact would best distinguish Python interpreter shutdown from a native Kit/framework teardown or remaining native thread/resource?

No workaround is proposed. In particular, this package does not recommend forced exit, killing as success, a larger timeout, cache deletion, package upgrade, extension removal, or relaxing any admission rule.
