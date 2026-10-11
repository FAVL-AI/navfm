# G2 Isaac Sim Runtime Gate Brief

**Status: PREREGISTERED / NOT RUN**

**Purpose.** Execute the three frozen PhysX-dependent harnesses on the
designated Isaac Sim 5.1 machine before Sprint 2D certification.

**This file defines the experiment and its claim boundary. It does not record an
executed result.** No count below has been measured. A reader arriving at this
document later must not mistake a protocol for evidence: the harnesses have not
run, and until they do, the numbers here are hypotheses that were written down
in advance so they could not be adjusted afterwards.

Current runtime evidence, in full:

| | |
|---|---|
| causality | **NOT RUN** |
| dense targetability | **NOT RUN** |
| footprint oracle | **NOT RUN** |
| runtime total | **NOT RUN** |
| runtime gate | **NOT RUN** |
| `SAFE_TO_BEGIN_SPRINT_2D` | **NO** |

---

## Which commit to run

**Run at `3ea2106` or later. Do NOT downgrade to `adbb689`.**

`adbb689` is the migration baseline and an older brief named it as the revision
to check out. That instruction was wrong to follow blindly. Verified on the
development host: `adbb689..3ea2106` changes only the governance-configuration
directory, the ignore file, the attribution allowlist, the standing-instructions
file, and one append-only provenance line. Every file this gate depends on is
byte-identical across that range — the policy module, `targetability`,
`population`, all three harnesses, both scene audits, and all three frozen
expected-answer files.

Before running, re-verify that claim against whatever HEAD you actually have.
It is one command per file and it is the difference between running the
instrument you think you are running and one that moved underneath you.

**Record the commit actually executed.** Do not copy a HEAD from this document
into an evidence artefact as though it had already run.

---

## Read first: this repository arms a pre-execution gate

A committed `PreToolUse` hook denies `Bash`, `Edit` and `Write` until
`execution-preflight.md`, in the governance-configuration directory, carries
`status: READY` for the current session. The hook's refusal message names the
exact path. **A fresh clone will refuse your first command. That is expected, not a
broken checkout.**

- Complete the preflight honestly — route `RESEARCH+ENGINEERING` — then set
  `READY`. Do not set it READY merely to get past the gate.
- Before READY, only named read-only commands pass.
- Composition is denied: `;` `&` `&&` `|` `>` `` ` `` `$()`. A `cd <dir> && <cmd>`
  prefix is refused; issue two separate calls.
- `gh api` is deliberately not allowlisted. `gh run view|list` and
  `gh pr view|checks` are.

To disable for one machine only, remove the `research-governance.enabled`
marker from that same directory. The gate enforces nothing where the marker is
absent, so other repositories on the machine are unaffected either way.

---

## Before running anything

1. Enter the NavFM repository. `git remote -v` must be
   `git@github.com:FAVL-AI/navfm.git`.
2. `gh repo view FAVL-AI/navfm`. The repository is **private**, so a caller
   without organisation access receives 404 rather than 403. "Not found" from a
   third-party integration means missing access, not a missing repository.
3. `git rev-parse HEAD` and `git status --short`.
4. **STOP** if any scientific-code file is unexpectedly modified.
5. Confirm Isaac is genuinely on *this* machine:

       python -c "import isaacsim"    # must import
       nvidia-smi                     # must reach the driver

   On the development host both FAIL. That is why this gate has not run, and it
   is the check that should have been made before the gate was ever scheduled.

6. Record hostname, interpreter, Isaac Sim version, GPU and driver.

---

## Expected digests

| Policy | Digest |
|---|---|
| production (policy version 4) | `c6534203825fa13d` |
| `causality_control(0.50)` | `f262ab4c40adaf08` |
| `causality_control(1.00)` | `7670a01604dd7314` |
| `causality_control(1.50)` | `b303977ded31507c` |
| `shared_origin_control(40.0)` | `c0a05923595b72bb` |

Superseded, never to be reused: `2cec5cf6bc23edb8` (v3), `7136993d04151369` (v2).

Verify the executing code reports the production digest before running physics.
A result carrying the wrong digest measures a different experiment.

---

## Run only these three

    <isaac-sim>/python.sh scripts/validate_collision_probe_causality.py   expect 9/9
    <isaac-sim>/python.sh scripts/validate_dense_targetability.py         expect 5/5
    <isaac-sim>/python.sh scripts/validate_physx_footprint_oracle.py      expect 9/9

All three import `isaacsim.simulation_app` and require the Isaac Sim 5.1 Python
interpreter. The repository documents no wrapper command.

**Known gap, recorded and NOT to be repaired in this tranche.** None of the three
preflights its interpreter. A missing `isaacsim` raises an uncaught
`ModuleNotFoundError` rather than refusing by name, which is the F-M1-1
invariant — gate scripts never infer execution state; they preflight, refuse,
and name the missing requirement. A traceback on the wrong interpreter is that
gap, not a physics failure, and must not be recorded as one.

---

## The three runtime questions

**1. Causality — the default blocker standoff moved 0.50 m to 0.30 m** for five
fixtures when they migrated onto the shared policy. `DISTANCE_DIVERSITY` passes
preregistered explicit standoffs and should be unaffected. `OCCLUDED_TARGET` and
`WRONG_CAUSE_BAD_PROBE` use `from_origin`, which maps onto
`shared_origin_control(40.0)` exactly. The remaining fixtures pin verdicts and
colliders rather than absolute distances. Static tracing says the verdicts hold;
only execution can confirm it.

**2. Dense targetability — two faces became four**: `+X`, `-X`, `+Y`, `-Y`.
`f_nonisolatable` already shells all four lateral faces at ±0.6 m, and every
four-face origin lands inside its own shell, so `TARGET_NOT_ISOLATABLE` should be
preserved — the fixture was written for a four-face policy before one existed.
Confirm it rather than assume it.

**3. Footprint oracle — confirm the target-directed migration did not disturb
generic overlap and sweep.** These operations are `OUT_OF_SCOPE_VOLUMETRIC` under
SD-001 and route through no candidate policy. A censored sweep must still report
a **bound**, never a completed measurement at the cap.

---

## The frozen-expectation rule

**9/9, 5/5 and 9/9 are hypotheses under test, not targets to optimise toward.**

If any case fails: preserve the failure. Capture the fixture, the candidate
origin, direction, range and standoff, the hit or miss, and the returned
collider. Classify the supported cause. Then **STOP**.

Do **not**: edit an expected answer · modify `candidate_policy.py` · change the
standoff · reduce four faces to two · rerun until something passes · repair
before reporting.

A failure here is a result. Tuning the intervention until the test agrees would
destroy the only evidence the tranche exists to produce, and would reproduce in
one afternoon the exact defect — an instrument shaped to its answer — that
Sprints 2A through 2C were spent removing.

---

## Claim boundary

Do **not** run the Hospital, Office or Warehouse production audits.

| | |
|---|---|
| Hospital | `NO_EVIDENCE / PENDING` |
| `wrong_1` | `UNRESOLVED` |
| Office | not remeasured |
| Warehouse | not remeasured |
| canonical scene | `NONE` |
| Yahboom trajectory collection | not authorised |
| data admission | not authorised |

`gates/scenes/hospital_collision_coverage_audit.json` is **known stale**. Do not
edit, stage, clean, restore or reinterpret it. It is the only expected dirty
file in the worktree, and it records an impossible `probative_population` of
`-1` produced by superseded probe semantics.

---

## Provenance required before any result is accepted

Record, alongside the numbers:

- hostname or execution-environment identity;
- exact Git HEAD actually executed;
- branch;
- worktree status;
- Isaac Sim version;
- Isaac interpreter path;
- GPU, where relevant;
- candidate-policy digest.

A physics number without that provenance is not admissible, because nothing
distinguishes it from a number produced somewhere else, on other code.

---

## PASS gate

All of the following, or the gate fails:

- causality **9/9 actually executed**;
- dense targetability **5/5 actually executed**;
- footprint oracle **9/9 actually executed**;
- no skipped frozen case;
- no rewritten expectation;
- executing policy digest is `c6534203825fa13d`;
- no negative population in any accounting;
- complete runtime provenance as listed above.

If all three execute and pass: `SAFE_TO_BEGIN_SPRINT_2D = YES`.

**Then STOP and report. Do not start Sprint 2D automatically.** Sprint 2D
certifies cross-consumer intervention-policy equivalence and prepares the
append-only behavioural-contract amendment; it is a separate tranche with its
own approval.

---

## Report format

**A** machine / environment · **B** HEAD and worktree · **C** Isaac version and
interpreter · **D** policy digest · **E** causality x/9 · **F** dense
targetability x/5 · **G** footprint oracle x/9 · **H** total x/23 · **I** failed
fixtures with supported cause · **J** negative controls executed? · **K**
accounting valid? · **L** runtime evidence path · **M** runtime gate PASS/FAIL ·
**N** safe for Sprint 2D YES/NO.
