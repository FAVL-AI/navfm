# CLAUDE.md — standing instructions for this repository

Read this fully before doing anything. These rules are not preferences; they
are the audit discipline the research depends on.

## What this project is

`isaac-navfm`: reproducible research infrastructure for the GNM / ViNT / NoMaD
visual navigation foundation models — a machine-checked specification of their
on-disk data format, an Isaac Sim collection pipeline for a Yahboom ROSMASTER
M3 PRO (mecanum), single-GPU fine-tuning, and a pre-registered experiment
matrix headed for a CoRL/ICRA/RA-L submission. Read, in order:
`README.md` → `docs/DATA_FORMAT.md` → `docs/WORKFLOW.md` (phases + gates) →
`docs/EXPERIMENTS.md` → `PREREGISTRATION.md`. `docs/METHODOLOGY.md` is the
deep reference; `paper/draft.md` is the paper.

## Environment on this machine (facts, do not "fix" them)

- Ubuntu 22.04, RTX 4080 SUPER 16 GB, ROS 2 Humble.
- **Isaac Sim 5.1.0 is installed. Do NOT upgrade to 6.x.** 5.1 is the stable
  Isaac Lab pairing (Python 3.11). The codebase supports both namespaces; on
  this machine the 5.x path is PRIMARY: `isaacsim.core.api.SimulationContext`,
  `isaacsim.core.prims.Articulation`, `isaacsim.sensors.camera.Camera`.
  The 6.0 experimental APIs (`isaacsim.core.experimental.*`,
  `isaacsim.sensors.experimental.rtx`) are the fallback branch here, not the
  default. If you touch `src/navfm/isaac/`, keep both branches working and
  make the 5.1 branch the tested one.
- Two virtualenvs, never merged: `~/.venv-train` (Python 3.11, torch cu128,
  this package + patched upstream) and the Isaac Sim 5.1 Python environment.
  They exchange only files on disk.
- Upstream reference: `third_party/visualnav-transformer` pinned at commit
  `dca7981`, patched via `scripts/patch_upstream.py` (idempotent, reversible).
  Never edit upstream files directly; extend the patch script instead.

## Non-negotiable rules

1. **Authorship.** Git identity is Frank Asante Van Laarhoven
   <frankleroyvan@gmail.com> only. Never add Co-Authored-By, "Generated
   with", AI/assistant/tool attribution, or any such branding to commits,
   code, docs, or metadata. No exceptions.
2. **The format modules are load-bearing.** Any change under `src/navfm/`
   that touches `schema.py`, `writer.py`, `kinematics.py`, or `validate.py`
   MUST be followed by the full suite INCLUDING the upstream proof:
   `NAVFM_UPSTREAM=third_party/visualnav-transformer python -m pytest -q`.
   A change that breaks `test_upstream_compat.py` is wrong by definition,
   even if it looks like an improvement — the reference loader's behaviour is
   the specification.
3. **Verify before commit, every time:** `make verify` (ruff + mypy + pytest)
   plus the upstream suite when applicable. Inspect `git status` and the
   staged diff. Never stage: weights (*.pth), datasets, images, LMDB, runs/,
   logs, wandb/, third_party/, USD assets, or anything in `.gitignore`.
4. **Small commits, evidence in the message:** what changed, why, and the
   test/gate output that proves it. Plan first for anything non-trivial.
5. **Gates are sacred.** `docs/WORKFLOW.md` defines gates G0–G6. Archive
   every gate command's output under `gates/G<N>/` (create it; it IS
   committed — text logs only). A phase does not start until the previous
   gate's outputs are archived.
6. **Pre-registration.** Never edit the frozen section of
   `PREREGISTRATION.md`; amendments are new dated sections. No hand-typed
   numbers in `paper/draft.md` — result tables come only from
   `scripts/make_tables.py` reading `runs/`.
7. **Honesty markers.** Anything unmeasured stays marked PROVISIONAL /
   UNVERIFIED. Removing such a marker requires a measurement, with its method
   recorded in `docs/HARDWARE.md`.
8. **Don't chase upstream.** The reference repo is unmaintained; treat its
   quirks (documented as findings F1–F11 in `paper/draft.md` §3) as fixed
   facts to reproduce or consciously patch — each patch recorded.

## Adversarial review policy (when to red-team, and when not to)

Do NOT run adversarial review on routine work — the oracles are stronger:
format/label questions are settled by the upstream compatibility proof, sync
questions by the smoke test's physical assertions, result integrity by gates
and script-generated tables. Arguing where an oracle exists is wasted budget.

Red-team review IS mandatory, before commit, at these five triggers — each is
a place where no oracle exists and the failure mode is a plausible
misreading that our own tests would co-sign:

1. Any semantic change to `schema.py`, `kinematics.py`, `writer.py`, or
   `eval/metrics.py`. Reviewer instruction: refute the change against the
   UPSTREAM SOURCE at `third_party/visualnav-transformer` (or the pinned-line
   references in docs/METHODOLOGY.md), never against this repo's tests.
2. The training-loss implementation in `train/run.py` (first commit and any
   later change). A wrong objective trains beautifully. Verify the exact
   weighting `alpha*1e-2*dist + (1-alpha)*action_reduce(mse)`, the mask
   semantics, and BN-freeze taking effect, line-by-line against
   `train_utils._compute_losses`.
3. Any amendment to PREREGISTRATION.md: is it fixing the protocol, or
   rescuing a hypothesis? State the answer in the amendment.
4. Once, immediately before Phase 4 launches: attack the experiment design —
   seed handling, scene leakage between arms, any variable other than the
   manipulated one that differs across cells.
5. Phase 6.3, the paper: claim by claim, "which runs/ directory backs this
   sentence?" Anything unbacked is cut or marked as discussion.

Mechanics: spawn an independent subagent with ONLY the artefact under review
plus the relevant upstream files — not this session's reasoning, which is the
thing under test. Instruct it to refute, not to summarise; default to
"refuted" when uncertain. Archive verdicts under gates/redteam/<trigger>-<date>.md.
A finding survives only if the refutation fails against source evidence.

## Known landmines (all documented in docs/REPRODUCTION.md — check there first)

`diffusers==0.11.1` needs `huggingface_hub==0.25.2` · torch ≥ 2.6 needs
`weights_only=False` for vint/gnm checkpoints (patched) · torchvision must be
the matched pair · eval metrics are batch-size dependent (always batch 400,
always state it) · LMDB cache needs local NVMe, not NFS · stale
`dataset_dist_*.pkl` / `*.lmdb` caches must be deleted when data changes ·
`goals_per_obs` and `negative_mining` are dead upstream keys · yaw must be
unwrapped (the writer does this; never bypass the writer).

## Current state / what remains

Implemented and tested (125 unit + 4 upstream-compat tests): schema, writer,
validator, stats, splits, kinematics, control, planning, checkpoint loader,
metrics, patch/register scripts. Implemented but NEVER EXECUTED (no Isaac Sim
in the build environment): `navfm/isaac/{app,robot,randomize,collect}.py` —
expect real API friction on first 5.1 run; fix in the fallback branch.

Not yet implemented (the immediate work):
- `src/navfm/train/run.py` — the fine-tune driver (`python -m navfm.train.run
  --config …`). All components exist in `train/finetune.py`; the driver is the
  loop: build ViNT from upstream classes, load `vint.pth` via
  `navfm.models.loader`, apply freeze/BN policy, accumulation loop with bf16
  autocast, per-epoch eval, checkpoint + config.json + git SHA into `runs/`.
- `src/navfm/eval/offline.py` — `python -m navfm.eval.offline --model vint
  --checkpoint … --dataset … --split test --batch-size 400`: reference-exact
  metrics (both strict and plain reductions) + ADE/FDE in metres, JSON output
  into `runs/`.
- `scripts/make_tables.py` — regenerate paper tables from `runs/` logs.
- `scripts/smoke_isaac.py` — 5.1 smoke: open simple_room, spawn a cube-proxy
  robot if `assets/m3pro.usd` absent, verify the step/pose/rgb sync contract,
  write 20 episodes, run the validator. Gate G0.d/G2-smoke evidence.
