# Pre-Amendment-5 reproduction archaeology — read-only audit

**Uncommitted working note.** No checkpoint was loaded, no inference run, no
training started, Amendment 5 unmodified, no prior evidence deleted or rewritten.

## Headline

**The July 2026 GNM/NoMaD reproduction work is real, and it is not in `navfm`.**
It lives in `/home/favl/robotics/FleetSafe-VLA`, whose remote is
`github.com/FAVL-AI/visualnav-transformer` — a fork of the upstream reference,
not this repository.

`navfm`'s first commit is `92e3004`, **2026-07-30T23:59Z**, three days *after*
that work. `navfm` has one branch (`main`), one tag (`m1-freeze`), one worktree
and no unreferenced refs. So no navfm branch or tag hides prior reproduction
evidence — the handoff statement "R6 not executed" is true *of navfm*, and
simultaneously the claim "GNM and NoMaD gates complete" is true *of the fork*.
Both were correct; they describe different repositories.

## What the fork's tags record (all at `900c418`, 2026-07-27T11:05:32+01:00)

| Tag | Recorded evidence |
|---|---|
| `gnm-reproduction-v1.0.0` | checkpoint `4b03e0255f8a5472`, 8,663,797 params, **638/638 tensors, zero missing or unexpected keys**; smoke inference through the official forward path returning `dist [1,1]`, `action [1,5,4]`; official `train.py` executes on public GO Stanford, exit 0 |
| `nomad-reproduction-v1.0.0` | checkpoint `70f79b8262527e20`, 19,049,675 params from a raw `state_dict`, **645/645 tensors**; 96x96 images, context 3, 8 predicted steps, `learn_angle=False`; **a diffusion action head run through the official DDPM scheduler at 10 steps**, outputs `dist [1,1]` and one sampled trajectory `[1,8,2]`; **bitwise identical across three repeats under a frozen seed protocol**; official `train.py` exit 0 |
| `visualnav-family-reproduction-v1.0.0` | all three models independently evidenced; no verdict inherited between them |

**The checkpoint digests match navfm's byte-for-byte** (`4b03e025…`,
`70f79b82…`), so this is the same artefact, not a different release.

## CONFLICT requiring resolution before Amendment 5 is adjudicated

Amendment 5 preregisters **NoMaD R7 as BLOCKED** on the grounds that
`src/navfm/upstream.py:218` raises `NotImplementedError` for the diffusion
sampling path. The July tag records a diffusion action head **executed** through
the official DDPM scheduler at 10 steps, with bitwise-identical repeats.

These are not contradictory once located — navfm's `upstream.py` genuinely does
not implement it, and the fork evidently does — but Amendment 5 must not be
adjudicated while it asserts a blocker that another repository has already
cleared. The reconciliation question is precisely the one to answer:

* was the July NoMaD inference the official deployment entry point, a separate
  implementation in the fork, or a path since removed?
* can that implementation be adopted by reference, ported, or must navfm
  implement its own?

Until answered, **NoMaD R7 = `EXISTING EVIDENCE UNDER RECONCILIATION`**, not
"never executed".

## Crosswalk

| Model | Rung | Existing evidence | Where | Same ckpt? | Same protocol? | Disposition |
|---|---|---|---|---|---|---|
| GNM | R5 | digest verified | navfm `checkpoints/` | Yes | Yes | **REUSE** |
| GNM | R6 | 638/638, 0 missing/unexpected | fork `gnm-reproduction-v1.0.0` | Yes | not navfm's | **DELTA** |
| GNM | R7 | smoke inference, shapes recorded | fork, same tag | Yes | no frozen GO Stanford batch, no declared repeatability tolerance | **DELTA** |
| GNM | R8 | `train.py` exit 0 on public GO Stanford | fork, same tag | Yes | unknown freeze | **DELTA** |
| ViNT | R5 | digest verified | navfm | Yes | Yes | **REUSE** |
| ViNT | R6/R7 | family tag asserts independent evidence; per-model detail not yet read | fork | Yes | unknown | **AUDIT INCOMPLETE** |
| NoMaD | R5 | digest verified | navfm | Yes | Yes | **REUSE** |
| NoMaD | R6 | 645/645 tensors | fork | Yes | not navfm's | **DELTA** |
| NoMaD | R7 | DDPM 10-step sampling, 3 bitwise-identical repeats | fork | Yes | conflicts with navfm blocker | **CONFLICT / RECONCILE** |
| GO Stanford | R2–R4 | G0.c, 41,872 pairs, `57a7fbbeba91b92a` | navfm | — | Yes | **REUSE** |
| Isaac Sim 5.1 | prerequisite | bring-up + pilot + egocentric | navfm | — | Yes | **REUSE** |
| W&B | ledger | pilot project | navfm | — | extend | **REUSE infra** |

`DELTA` dominates because Amendment 5 adds requirements the July work predates:
a frozen GO Stanford input batch, a declared repeatability tolerance, and the
R0–R11 ladder itself. Prior smoke inference therefore earns DELTA, not automatic
PASS — but it must not be re-run wholesale either.

## The column-3 boundary was already found in July

Both tags state it independently: *"Execution evidence. Not a reproduction of
any published GNM number: upstream ships no offline pathway that produces one"*,
and the family tag adds that *"the published numbers are real-robot trial
results."* That is Amendment 5's third column, reached from the other direction
three days before navfm existed. It corroborates the boundary rather than
duplicating it.

## Also located, not yet examined

* `feat/visualnav-isaaclab-ros2-gazebo-mujoco` exists in
  `/home/favl/robotics/Fleet-Safe-VLA-OS` — the simulator-integration lineage.
  Do not rebuild adapters or simulator harnesses before comparing against it.
* `/home/favl/audit-scratch/visualnav-cross-repo/FleetSafe-VisualNav-Benchmark`
  (112 hits) and `/home/favl/robotics/gnm-vlnverse-baseline` (53 hits, tags
  `v0.1-bo-rui-baseline` … `v0.6-stop-head-train-val-protocol`) — evaluation and
  stop-policy lineage, class D.

## Recommended amendment change before adjudication

Insert the clause the supervisor drafted, which this audit now shows is load-bearing:

> Existing reproduction evidence predating Amendment 5 shall first be audited
> against the frozen rung criteria. Evidence satisfying a rung without
> reinterpretation may be adopted by reference. Where evidence is incomplete,
> only the missing delta shall be executed. Historical evidence shall not be
> discarded or repeated solely because the current protocol was introduced later.

And NoMaD R7 must be restated from BLOCKED to UNDER RECONCILIATION, with the
blocker scoped to `navfm`'s own `upstream.py` rather than to the model.

## ViNT audit — COMPLETE (superseded the partial note below)

Five-angle sweep of the fork (commit messages + all tag annotations; working-tree
files; content at the tip tree of all 12 refs; chronology back to the root commit;
tests and code across all 236 revisions), then independent re-verification of the
decisive checks.

| Rung | Disposition | Basis |
|---|---|---|
| ViNT R6 | **DELTA** | Real per-model load record exists: sha256 `155fd72de2e98ae0…` (exact target match), 430,167,114 B, **29,662,397 params, 799/799 tensors, 0 missing, 0 unexpected, PASS**. Falls short because the load was **`strict=False`** (`scripts/02_verify_checkpoints.py:168`) so strictness is implied by the 0/0 counts but never asserted; the machine-readable artefact `experiments/_evidence/checkpoint_verification.json` is **gitignored** and would not survive a clean clone; environment record is one field. |
| ViNT R7 | **RERUN** | **No ViNT deterministic-inference record exists anywhere, and the gate apparatus excludes ViNT by construction.** `vint_gate.json` has never existed in any revision, and `scripts/15_reproduction_gate.py:49` hard-codes `MODELS` to gnm and nomad with `--model` bound to `choices=sorted(MODELS)`. No inference seed, no input-batch digests, no output digests, no repeat protocol, no declared tolerance. Output shapes `dist_pred [1,1]` / `action_pred [1,5,4]` exist only as **one prose line** at `docs/reproduction/pack/VINT.md:87`. ~~and the repo's own traceability matrix routes that claim to a `gate.json` that does not exist for ViNT~~ — **struck: this clause was FALSE and was caught by trigger-3 round 1.** `grep -rn vint_gate` over the fork returns nothing, and `TRACEABILITY.md`'s gate rows name `m1_family/gnm_gate.json` with subsequent rows inheriting `--model gnm`. No traceability document ever referenced a ViNT gate artefact. Retained struck rather than deleted so the adjudication history is not rewritten; see `gates/failures/F-A5-1.md`. |
| ViNT R8 | **DELTA** | `train.py` (unmodified upstream entry point) exit 0 on public GO Stanford, config and hyperparameters recorded, leakage check PASS, and a loss-identity check confirmed to `1.46e-08`. No produced-artefact digest for the entry-point run. |

### The family tag asserted more than the repository supports

`visualnav-family-reproduction-v1.0.0` states *"GNM, ViNT and NoMaD independently
evidenced"* and *"Each model holds its own reproduction evidence."* For R6 and R8
that is defensible. **For R7 it is not:** ViNT was structurally excluded from the
gate script that produced GNM's and NoMaD's inference records. This is a defect in
the July gate, recorded here as a finding about that gate — not a deficiency of
`navfm`, and not something `navfm` should quietly absorb into a delta plan.

Residual gaps, neither plausibly holding a ViNT gate record: the pinned upstream
submodule's own history (unmodified reference, wrong place for it), and a
blob-level sweep of all 236 commits for a file added and deleted mid-history whose
content never matched the greps.

### Superseded partial note

**There is no standalone `vint-reproduction-v1.0.0` tag.** The fork carries
`gnm-reproduction-v1.0.0` and `nomad-reproduction-v1.0.0` as per-model gates,
but ViNT appears only inside `visualnav-family-reproduction-v1.0.0`, which
asserts that *"each model holds its own reproduction evidence"* without
restating ViNT's numbers the way the GNM and NoMaD tags restate theirs.

Two readings, and they must not be conflated:

1. ViNT's per-model evidence exists in commits or evidence files rather than in
   a tag annotation — plausible, since ViNT was the pre-existing model and GNM
   and NoMaD were described in that tag as "the two newcomers";
2. ViNT's evidence was assumed from the family and never separately recorded.

The family tag's own rule decides which matters: *"No verdict is inherited:
shared upstream code and dataset format reduce duplication but do not transfer
verification."* If reading 2 holds, the family tag would violate its own rule.

**Next session's first action:** locate ViNT's parameter count, tensor count,
strict-load result, missing/unexpected keys, inference entry point and output
shapes in the fork's commits and evidence files. If they exist, ViNT joins GNM
and NoMaD at DELTA. If they do not, ViNT is **RERUN** at R6–R7, and that is a
finding about the July gate rather than about navfm.

Until then ViNT R6–R8 remains **AUDIT INCOMPLETE**. It must not be recorded as
DELTA by symmetry with the other two — that is exactly the inheritance the
family tag forbids.

## Incidental cross-repository observation

Fork commit `26166cb`, *"fix(scene): parse git status independently of leading-
column stripping"*, is the same defect class navfm hit and pinned as a
regression: porcelain output stripped, truncating the first filename. The same
bug was found and fixed independently in both repositories. Worth noting when
deciding what else may be shared lineage rather than coincidence.

## Out of scope, recorded to prevent mis-adoption

`hospital-v1.0.0` in the fork certifies a hospital corpus — *"unmodified official
ViNT_Dataset indexes 11,877 samples"*, corpus `3344c7eb5fce9c8e`. This is
**FleetSafe material (class E)** and, per the standing repository boundary, must
not be imported into navfm or counted toward any navfm rung.

## Check 10 — decisive ViNT claims independently recomputed

Both claims underpinning ViNT R7 = `RERUN` were re-run directly, not accepted
from the workflow summary. **Both reproduce.**

**Claim 1 — `vint_gate.json` exists in no revision. REPRODUCES.**
`git log --all --name-only -- '*gate*.json'` lists six gate artefacts. Two sit
in `experiments/validation/m1_family/`: `gnm_gate.json` and `nomad_gate.json`.
There is no `vint_gate.json`, in history or the working tree.

The control matters more than the claim: had no model's gate file existed, the
absence of ViNT's would have proved nothing. GNM's and NoMaD's exist **in the
same directory**, so this is a per-model asymmetry, not an absent mechanism.

**Claim 2 — `scripts/15_reproduction_gate.py` excludes ViNT. REPRODUCES.**

```
:49   MODELS = {"gnm": ("gnm.yaml", "gnm.pth"), "nomad": ("nomad.yaml", "nomad.pth")}
:260  ap.add_argument("--model", choices=sorted(MODELS), required=True)
```

`--model vint` is rejected by argparse. Across all history there is exactly one
distinct `MODELS =` line — it never included ViNT.

**Corroboration found while checking a possible confound.** The script contains
11 `vint` matches; ten are `vint_train`, the upstream *package* shared by all
three models, so they do not indicate ViNT support. The eleventh is the script's
own docstring at line 5: *"then ran one training job with model type `vint`.
That leaves GNM and NoMaD with…"*. The exclusion was deliberate and the author
stated why — ViNT was covered by a training job (R8), not by an inference gate
(R7). That is exactly the shape the dispositions record: ViNT R8 DELTA, R7 RERUN.

**Consequence.** ViNT R7 = `RERUN` stands. The execution order is unchanged. Per
the brief's contingency, **no `gates/failures/` record is warranted** — both
checks passed, and a check that passed is not a defect.

## Correction-pass re-verification from PRIMARY artefacts (not the fan-out summary)

Re-derived directly, per correction 3's rule. Four controls confirm; **two new
findings emerged that the fan-out summary did not report.**

| Control | Command | Result |
|---|---|---|
| `MODELS` excludes vint at the audited revision | `git show 900c418:scripts/15_reproduction_gate.py` `:49`,`:260` | CONFIRMED — `{"gnm":…,"nomad":…}`, `--model` bound by `choices=sorted(MODELS)` |
| `vint_gate.json` in any revision | `git rev-list --all` × `git ls-tree -r` | CONFIRMED absent from **every** commit |
| `experiments/_evidence/` ignored | `git check-ignore -v` | CONFIRMED — `.gitignore:92` |
| `experiments/validation/m1_family/` ignored | `git check-ignore -v` | CONFIRMED **not** ignored (exit 1) |

### NEW FINDING A — the tag does not carry ViNT entry-point evidence

`git ls-tree -r 900c418 experiments/validation/m1_family/` returns exactly:
`M1_FAMILY_manifest.sha256`, `gnm_entry_point.json`, `gnm_gate.json`,
`nomad_entry_point.json`, `nomad_gate.json`. **There is no
`vint_entry_point.json` at the tag** — ViNT has neither a gate record nor an
entry-point record there.

~~`vint_entry_point.json` exists at exactly one commit,~~ — **struck: FALSE, and
caught by trigger-3 round 2.** The file is contained in **98 commits** (branch-reachable; `git rev-list --all` inflates this to 100 by including two `refs/stash` entries), from its
introduction through the fork tip `219f717`. Corrected statement:
`vint_entry_point.json` is **introduced by** exactly one commit, **`ce9708e`
(2026-07-27T12:32:04+01:00)** — ≈86 minutes after `900c418` (11:05:32) — and is
contained in the tree of no tag. The load-bearing fact was never the count of
commits but the absence of any tag reaching it, and that fact survives
refutation (`git tag --contains ce9708e` → empty; `merge-base --is-ancestor`
false for all six tags). Retained struck rather than deleted so the adjudication
history is not rewritten. The ViNT R8 evidence therefore **postdates every
reproduction tag and is covered by none of them.**

**Round-2 finding, not present in this audit's original sweep: the historical
GNM R7 and NoMaD R7 inference ran on synthetic input, not GO Stanford.**
`900c418:scripts/15_reproduction_gate.py:113–125` defines `official_frame`,
which builds each frame from `np.random.default_rng(SEED + i)` at `SEED = 0` and
is the sole input source for both `run_gnm` (`:152`,`:155`) and `run_nomad`
(`:193`,`:196`). Its docstring says so: *"Synthetic, and not benchmark data."*
The crosswalk in this audit carried no dataset-identity column and so could not
record it, which is why the omission survived into Amendment 5 and had to be
caught at adjudication. This is the same genus as [[F-A5-1]]: a mechanistic fact
about what an artefact actually did, assumed rather than read.

Consequence for correction 3: ViNT R8's `source_commit` is `ce9708e`, and its
`source_tag` is **NOT ESTABLISHED** — no tag contains it. Recording `900c418`
there, as symmetry with GNM and NoMaD would suggest, would be false provenance.

### NEW FINDING B — the claim boundary is stronger than previously relayed

Verbatim from `ce9708e:experiments/validation/m1_family/vint_entry_point.json`:

> `"claim_boundary": "execution evidence only. One smoke-scaled epoch from
> random init on a scene-entangled split with ~34.5% padded targets. NOT a
> reproduction of any published ViNT result, and NOT comparable to GNM's or
> NoMaD's numbers: different optimiser, schedule, capacity and objective
> scaling."`

Two qualifiers were absent from the earlier summary and must survive into
Amendment 5: the split was **scene-entangled** with **~34.5% padded targets**,
and the run is **not comparable to GNM's or NoMaD's numbers**. The second
matters structurally — it forbids using this row for cross-model comparison,
which the eventual three-model protocol would otherwise invite.

Verified fields: `epochs 1`, `batch_size 24`, `initialisation "random
(from-scratch smoke, not the official checkpoint)"`, `exit_code 0`,
`dataset "go_stanford (public, official processed format)"`.
