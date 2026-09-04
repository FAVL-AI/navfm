# CLAUDE.md — standing instructions for this repository

Read this fully before doing anything. These rules are not preferences; they
are the audit discipline the research depends on.

## What this project is

`navfm` (github.com/FAVL-AI/navfm): reproducible research infrastructure for the GNM / ViNT / NoMaD
visual navigation foundation models — a machine-checked specification of their
on-disk data format, an Isaac Sim collection pipeline for a Yahboom ROSMASTER
M3 PRO (mecanum), single-GPU fine-tuning, and a pre-registered experiment
matrix headed for a CoRL/ICRA/RA-L submission. Read, in order:
`README.md` → `docs/DATA_FORMAT.md` → `docs/WORKFLOW.md` (phases + gates) →
`docs/EXPERIMENTS.md` → `PREREGISTRATION.md`. `docs/METHODOLOGY.md` is the
deep reference; `paper/draft.md` is the paper.

## Canonical identity (frozen 2026-09-04)

| | |
|---|---|
| Repository | `FAVL-AI/navfm` — https://github.com/FAVL-AI/navfm |
| Organisation | `FAVL-AI` |
| Author | Frank (Asante) Van Laarhoven |
| Role | Doctoral Researcher / PhD Candidate |
| Affiliation | Newcastle University |
| Academic email | `F.Van-Laarhoven2@newcastle.ac.uk` — correspondence and papers |
| Git identity | `frankleroyvan@gmail.com` — commits only, see rule 1 below |

The remote is `FAVL-AI/navfm` and never a personal account. Verify before every
push, because the failure is quiet and the repair afterwards is history
rewriting:

    git remote -v                 # git@github.com:FAVL-AI/navfm.git
    gh repo view FAVL-AI/navfm

**The repository is private.** A tool that lacks authorisation for the
organisation reports 404 rather than 403, so "not found" from a third-party
integration is the expected symptom of a missing installation — not evidence
that the repository is absent, misnamed, or has moved. Diagnose the integration
before touching the remote.

**`FAVL-Engineering-OS` is a separate repository.** It holds the machine-level
governance and tooling; it is not NavFM, not a mirror of NavFM, and not a
fallback for it. A push failing there says nothing about this repository, and
neither one is evidence about the other.

Public-facing authorship is Frank (Asante) Van Laarhoven alone. No AI system is
recorded as author, contributor or co-author, in commits, code, docs, metadata,
papers or slides. The tool identifiers this repository's governance layer
requires — the standing-instructions filename, the `.claude/` configuration
directory, the `CLAUDE_PROJECT_DIR` environment variable — are technical
identifiers rather than attribution, which is why `.attribution-allow` lists
exactly where they may appear and why the guard still refuses every credit
construction inside those same paths.

## Execution environments (facts, do not "fix" them)

Three environments, and conflating them is how a tranche gets planned against a
machine that cannot run it. "The repository is configured for Isaac Sim 5.1" is
not "Isaac Sim is installed on this machine", and only the second one lets you
report a physics result.

### 1. Development / build host

The ordinary development host does NOT have Isaac Sim installed. On it:

- static repository inspection is allowed;
- ordinary Python tests may run;
- CI reproduction may run where dependencies exist;
- formatting, linting and type checking may run;
- Isaac Sim / PhysX-dependent harnesses MUST NOT be reported as executed;
- a missing Isaac runtime is NOT evidence of a physics-test failure -- it is
  the absence of a test, and the two must never be recorded the same way;
- physics-dependent results are reported as **NOT RUN**, never as a number.

Two commands settle which host you are on, and they are cheap:

    python -c "import isaacsim"    # must import
    nvidia-smi                     # must reach the driver

Measured 2026-09-04 on host `favl`: **both FAIL**. No `isaacsim` module in
either virtualenv, no `omni` package anywhere on disk, no `python.sh`; the only
thing under `~/.local/share/ov/pkg/` is `hub-2.0.0`, the Omniverse launcher hub
rather than Isaac Sim. `nvidia-smi` cannot reach a driver, so RTX 4080 SUPER
16 GB is the intended GPU and is UNVERIFIED here.

Everything importing `isaacsim.simulation_app` can be edited and unit-tested on
this host but NOT executed: the three frozen harnesses
(`validate_collision_probe_causality`, `validate_dense_targetability`,
`validate_physx_footprint_oracle`), the scene audits
(`audit_office_collision_coverage`, `diagnose_hospital_isolation`) and all of
`src/navfm/isaac/`. Static reasoning about what they would return is weaker
evidence than a run and must be labelled as such wherever it is recorded.

### 2. GitHub CI

Reproducibility and software gates only: lint, types, the test matrix, the
upstream compatibility proof, population ownership, the corpus owner job. CI
being green says nothing about physics and must never be cited as though it
did.

### 3. Isaac Sim execution machine

A separate machine runs the physics-dependent experiments, on **Isaac Sim
5.1.0**. Do NOT upgrade the NavFM research environment to 6.x without an
explicit compatibility and revalidation tranche. 5.1 is the stable Isaac Lab
pairing (Python 3.11); the codebase supports both namespaces and the 5.x path
is PRIMARY: `isaacsim.core.api.SimulationContext`,
`isaacsim.core.prims.Articulation`, `isaacsim.sensors.camera.Camera`. The 6.0
experimental APIs (`isaacsim.core.experimental.*`,
`isaacsim.sensors.experimental.rtx`) are the fallback branch, not the default.
If you touch `src/navfm/isaac/`, keep both branches working and make the 5.1
branch the tested one.

Only this machine may support a claim requiring real Isaac Sim / PhysX
execution: the three frozen harnesses, scene collision remeasurement, footprint
sweeps, and any other Isaac-dependent runtime evidence.

Before accepting any Isaac-dependent result, record: hostname or
execution-environment identity, repository HEAD, Isaac Sim version, the
interpreter used, the relevant policy and contract digests, and worktree state.
A physics number without that provenance is not admissible, because nothing
distinguishes it from a number produced somewhere else.

- Two virtualenvs, never merged: `~/.venv-train` (Python 3.11, torch cu128,
  this package + patched upstream) and, on the Isaac machine, its 5.1 Python
  environment. They exchange only files on disk.
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
   In commit messages, refer to this file as **the standing-instructions
   file**, never by its filename — the machine-level pre-push attribution
   guard rejects the literal string. That guard lives on this machine, not in
   `.git/hooks/`; do not create an in-repo copy of it.
5. **Gates are sacred.** `docs/WORKFLOW.md` defines gates G0–G6. Archive
   every gate command's output under `gates/G<N>/` (create it; it IS
   committed — text logs only). A phase does not start until the previous
   gate's outputs are archived. Two invariants, each bought with a defect
   recorded in `gates/failures/`:
   - **Gate scripts never infer execution state** — interpreter, environment,
     or paths. Preflight, refuse, and name the missing requirement. Helpfully
     auto-discovering an interpreter weakens reproducibility rather than
     serving it, because it makes the executed environment unknowable from the
     archive (F-M1-1).
   - **Gate scripts delete only paths they created**, verified by a marker
     file. "Delete what the caller asked" is not a deletion rule (F-M1-3).
   - **A verification must fail when its subject is absent.** Run it once
     against a deliberately broken state before trusting it against a good
     one. This genus has appeared four times (F-M2-1, F-M2-4): tests that
     skip silently, a check constructed `passed=True`, a verification command
     whose grep pattern matched nothing pytest prints, and a marker search
     for a string that never existed. A check that cannot fail certifies
     nothing; a check that cannot pass will be deleted by whoever is in a
     hurry. Prove both directions.
   - **The attribution guard false-positives; reword, never bypass.** The
     machine-level pre-push guard matches ordinary English describing how an
     artefact comes into existence -- the two-word pattern "<verb>-by" where
     the verb is the past participle of *to generate*. It fires on legitimate
     prose in files AND on commit messages that quote the blocked phrase while
     explaining the block. Reword to "produced in" / "written by the pass" and
     record the collision. Never disable the guard, never `--no-verify`: a
     false positive costs one rewording, and a disabled attribution guard costs
     the authorship rule the repository is built on.
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

Red-team review IS mandatory, before commit, at these six triggers — each is
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
4. Before a result is accepted as a baseline, and before a protocol is
   frozen: immediately before Phase 4 launches, attack the experiment design —
   seed handling, scene leakage between arms, any variable other than the
   manipulated one that differs across cells. The same applies before G0.c is
   accepted as the reference baseline, before the 2×2 protocol is frozen, and
   before the first costly physical episode is run: each is a point after
   which the cost of being wrong stops being a rerun.
5. Phase 6.3, the paper: claim by claim, "which runs/ directory backs this
   sentence?" Anything unbacked is cut or marked as discussion. The same pass
   runs once more before submission.
6. Whenever the evidence itself is of a kind that hides its own weakness:
   any finding that depends on the *absence* of an effect, and any result
   whose sample was shaped by exclusions, failed episodes, or resumed runs.
   Both are cases where a valid-looking table is compatible with an invalid
   population.

Mechanics: spawn an independent subagent with ONLY the artefact under review
plus the relevant upstream files — not this session's reasoning, which is the
thing under test. Instruct it to refute, not to summarise; default to
"refuted" when uncertain. Archive verdicts under gates/redteam/<trigger>-<date>.md.
A finding survives only if the refutation fails against source evidence.

**Oracle substitution, and its limit.** Triggers may be addressed through
executable conformance oracles rather than an independent red-team review.
These oracles establish consistency with the pinned upstream implementation;
they do **not** establish that the upstream computation is conceptually or
scientifically valid. Independent validity review therefore remains pending
and is required before scientific claims are accepted — conformance is not
correctness, and an oracle that agrees with a wrong reference agrees wrongly.

Conformance to shared reference functions also does not eliminate failures at
integration boundaries — serialization, configuration propagation, checkpoint
restoration, evaluator orchestration, table aggregation. Those seams are
exactly where a correct component and a correct reference still combine into a
wrong number, and they require independent adversarial review on their own
account.

Every oracle substitution is archived under `gates/redteam/` with its
justification. "We built an oracle instead" is a reviewable decision, not an
exemption from the trigger.

## Known landmines (all documented in docs/REPRODUCTION.md — check there first)

`diffusers==0.11.1` needs `huggingface_hub==0.25.2` · torch ≥ 2.6 needs
`weights_only=False` for vint/gnm checkpoints (patched) · torchvision must be
the matched pair · eval metrics are batch-size dependent (always batch 400,
always state it) · LMDB cache needs local NVMe, not NFS · stale
`dataset_dist_*.pkl` / `*.lmdb` caches must be deleted when data changes ·
`goals_per_obs` and `negative_mining` are dead upstream keys · yaw must be
unwrapped (the writer does this; never bypass the writer).

## Current state / what remains

Implemented and tested (178 unit + 26 upstream-marked tests): schema, writer,
validator, stats, splits, kinematics, control, planning, checkpoint loader,
metrics, patch/register scripts, and — since milestone M1 — the three
entrypoints that close the path from a dataset to a paper table:
`navfm.upstream` (locates and drives the pinned reference clone),
`navfm.eval.offline`, `navfm.train.run`, `scripts/make_tables.py`. Evidence in
`gates/M1/`; `bash gates/M1/reproduce.sh` re-runs the whole chain on CPU.

Implemented but NEVER EXECUTED (no Isaac Sim on this host — see Environment
above for how to check, rather than assuming either way):
`navfm/isaac/{app,robot,randomize,collect}.py` — expect real API friction on
first 5.1 run; fix in the fallback branch.

Executed only against synthetic noise, never against a real model or corpus:
the M1 entrypoints above. Their loss curves prove gradients flow, nothing more.
The first real number is gate G0.c (Session 2).

Not yet implemented:
- `scripts/smoke_isaac.py` — 5.1 smoke: open simple_room, spawn a cube-proxy
  robot if `assets/m3pro.usd` absent, verify the step/pose/rgb sync contract,
  write 20 episodes, run the validator. Gate G0.d/G2-smoke evidence.
- `src/navfm/isaac/urdf_import.py` — referenced by `robot.py`'s error message.
- NoMaD offline evaluation: `upstream.build_model` raises for it on purpose.
  `_compute_losses_nomad` needs a diffusion sampling loop, so E1.3 is its own
  entrypoint rather than a `--model nomad` flag on `eval.offline`.

@.claude/governance-router.md
