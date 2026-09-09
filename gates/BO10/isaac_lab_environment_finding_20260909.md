# Isaac Lab is already installed inside the frozen Isaac Sim 5.1.0 environment

**Recorded 2026-09-09.** Raised while planning an isolated Isaac Lab
installation. Changes the premise of that plan; does not invalidate any BO-10
result.

## What was found

Isaac Lab is **already installed, editable**, into
`~/miniforge3/envs/isaac` — the environment producing the BO-10 evidence:

| distribution | version |
|---|---|
| `isaacsim` | 5.1.0.0 |
| `isaaclab` | 0.54.3 |
| `isaaclab_tasks` | 0.11.16 |
| `isaaclab_rl` | 0.5.1 |
| `isaaclab_assets` | 0.2.4 |

The editable install points at a clone at `/home/favl/ai-lab/IsaacLab`
(270 MB), on branch **`main`**, at commit `3e73d6dd7`, which carries **no exact
tag** — `git describe` gives `training-checkpoints-develop-4-g3e73d6dd7`. The
worktree is clean.

So the intended plan — install Isaac Lab separately and pin it, explicitly *not*
tracking `main` — describes a state that has already been departed from, in the
opposite direction, before this session.

## Why it does not invalidate BO-10

`navfm` imports nothing from Isaac Lab. Checked across `src/`, `scripts/` and
`tests/`: zero references outside the provenance module written today. The
harnesses import `isaacsim.*` and `omni.*` only. Isaac Lab shares the
environment; it is not on the code path that produced Hospital's or Office's
frozen route-set results.

That is a real limit on the risk, and it is not the same as no risk.

## The actual risk

An **editable install tracking `main`** means the environment can change without
anything in this repository changing. `git pull` in that clone silently alters
the environment that produced the frozen evidence. Today nothing imports it, so
nothing changes; the day a harness does, the environment is a moving target and
no artefact records which version it moved to.

The provenance layer did not previously capture this. It captured the
interpreter path, which identifies the environment but not its contents.

## A second gap found in the same pass

`scripts/validate_route_admission.py` recorded the interpreter but **not the
Isaac Sim version** — a regression against the older Hospital harness, which did
record it, and against the standing rule that an Isaac-dependent result must
carry the simulator version. It is repaired: provenance now carries
`isaac_sim_version`, the expected-version match, torch, CUDA, GPU and the full
Isaac Lab block.

`gates/BO10/office_route_admission_20260909.json` was produced before the repair
and therefore lacks these fields. It is **not re-run** — the verdict does not
depend on them, and re-running to improve a provenance block would replace a
measured result with a newer one for no scientific reason. The missing identity
is supplied instead by `gates/BO10/simulator_identity_20260909.json`, captured
from the same interpreter on the same host and day:

```
isaac_sim_version   5.1.0.0        (matches expected 5.1.0)
python              3.11.15
torch               2.7.0+cu128    CUDA 12.8
interpreter         ~/miniforge3/envs/isaac/bin/python
isaac_lab           0.54.3 @ 3e73d6dd79080fd7632488c061052a6edd52e230 (untagged, main)
GPU                 RTX 4080 SUPER, driver 580.173.02, 16376 MiB
```

That is weaker than in-artefact provenance and is labelled as such: it
establishes the environment on the day, not per-run binding.

## Decisions this now requires — none of them taken here

1. **Whether to pin the existing clone to a release tag.** `v2.3.2`
   (2026-02-02) is the terminal patch of the 2.3 line and pins
   `isaacsim[all,extscache]==5.1.0` in its own installation docs. `v3.0.0-beta2`
   exists and targets the 6.0 line, which the standing instructions forbid
   without a compatibility tranche. Checking out a tag in that clone **changes
   the frozen environment**, which is exactly the action the isolation plan
   exists to avoid, so it is not done unilaterally.
2. **Whether to move Isaac Lab out of the frozen environment entirely.** This is
   the cleaner outcome and it costs disk — see below.
3. **Neither is urgent** while nothing imports Isaac Lab, and both become urgent
   the moment something does.

## Installation is blocked on disk regardless

| | |
|---|---|
| free space | **13 GB** |
| existing `isaac` env | 25 GB |
| an isolated Isaac Lab env (own `isaacsim==5.1.0` + clone + torch/RL libs) | **~30–35 GB** |
| standing rule before a build | 50 GB |

`/var/log/syslog` is 353 GB, growing at 7.7 GB/hour from a desktop
application's repeating GPU-process launch failure, logged without rate
limiting, and fills the disk in under two hours. Truncating it
reclaims the space and makes the installation feasible; nothing else here does.

## Verified against primary sources

From the Isaac Lab repository at tag `v2.3.2`, not from the `develop` docs:

- `docs/source/setup/installation/pip_installation.rst`:
  `pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com`
- `docs/source/setup/installation/index.rst`: "Isaac Sim 5.1.0 release…";
  "For Isaac Sim 5.X, the required Python version is 3.11"; **RAM: 32 GB or
  more**; **GPU VRAM: 16 GB or more**.

A caveat on the last two: this host has **31 GB RAM** against a stated 32 GB
baseline, and **16376 MiB VRAM** against a 16 GB baseline with no headroom.
Isaac Sim alone already reached 7.4 GB resident on the Office scene. The
vectorised-parallel-environments workload the plan is built around is the one
most likely to exceed both. That is a caveat on the premise, not an objection to
the plan.

---

*Note on wording:* an earlier draft named the desktop application responsible for
the syslog growth. The machine-level pre-push attribution guard matches vendor
names in tracked files, so the sentence is reworded to describe the mechanism
instead. The guard's behaviour is correct here and the collision is recorded
rather than bypassed. The operational detail a reader needs — a repeating
GPU-process launch failure logged without rate limiting — is unchanged.
