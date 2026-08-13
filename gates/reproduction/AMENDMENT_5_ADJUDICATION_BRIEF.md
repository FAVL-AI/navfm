# Trigger-3 adjudication brief — Amendment 5

**Uncommitted working note.** Not part of the preregistration. This is the
instruction for the adjudicator, to be used at the start of the next session.

## Instruction

> Adjudicate Amendment 5 under Trigger-3 only. Review the complete draft and the
> pre-Amendment-5 evidence audit against the existing preregistration rules. Do
> not load checkpoints, run inference, train models, modify historical evidence,
> or commit anything during the adjudication. Return a precise verdict of
> `Fixing`, `Rescuing`, or `Cannot determine`, with every defect tied to exact
> text/evidence. If the verdict is `Fixing`, apply only the required
> corrections, re-run Trigger-3, and commit Amendment 5 only after it passes.

Artefacts under review:

* `PREREGISTRATION.md`, section `## Amendment 5` to end of file (uncommitted);
* `gates/reproduction/PRE_A5_EXISTING_EVIDENCE_AUDIT.md` (uncommitted);
* the July fork at `/home/favl/robotics/FleetSafe-VLA`, remote
  `FAVL-AI/visualnav-transformer`, evidence around `900c418`, read-only.

## High-risk areas to challenge

1. Whether the three reproducibility columns remain genuinely independent.
2. Whether prior GNM/NoMaD evidence is being adopted by reference rather than
   re-labelled as `navfm` execution.
3. Whether ViNT R7 is correctly classified as a new run because the historical
   gate excluded ViNT.
4. Whether `strict=False` historical ViNT loading is correctly treated as
   insufficient for Amendment 5 R6.
5. Whether the declared repeatability tolerance can be applied without
   post-result adjustment.
6. Whether NoMaD's historical diffusion execution and the current `navfm`
   implementation are reconciled without silently porting code.
7. Whether SR/NE/SPL remain blocked until their required closed-loop inputs
   exist.
8. Whether the execution order permits only DELTA/RERUN work and prevents
   wholesale repetition of July evidence.
9. Whether the historical-family-tag defect is preserved rather than
   retroactively repaired.
10. **Whether every factual claim in Amendment 5 is sourced, and reproduces.**

## Why check 10 exists

Amendment 5 asserts specific numbers that were **not verified by the author who
wrote them into the document**. They were returned by subagents searching a
different repository and relayed into a preregistration:

| Claim | Where it is used |
|---|---|
| 29,662,397 parameters; 799/799 tensors; 0 missing, 0 unexpected | ViNT R6 = DELTA |
| `strict=False` at `scripts/02_verify_checkpoints.py:168` | the reason R6 is DELTA rather than REUSE |
| `scripts/15_reproduction_gate.py:49` restricts `MODELS` to gnm and nomad | **the reason R7 = RERUN** |
| `vint_gate.json` exists in no audited revision | **the reason R7 = RERUN** |
| loss identity confirmed to `1.46e-08` | ViNT R8 = DELTA |
| NoMaD: 645/645 tensors, DDPM at 10 steps, 3 bitwise-identical repeats | NoMaD R7 = UNDER RECONCILIATION |
| GNM: 638/638 tensors, 8,663,797 params, `action [1,5,4]` | GNM dispositions |

This is the exact failure class that caught Amendment 3 on four consecutive
rounds — an unsourced `2.3e-16`, a false claim about what the freeze audit
compared, and a misattributed `2.14e14`. It is also the failure Amendment 4
records against its own author: a 9.5-hour interval copied from a review without
recomputation, and wrong.

The rule Amendment 4 states is controlling here, and applies with more force
because these numbers are being frozen into protocol rather than left in a
review file:

> A reviewer's statement is evidence to verify, not a fact to copy without
> recomputation.

**Minimum for check 10:** independently re-run the two claims the ViNT R7 =
`RERUN` classification rests on — that `vint_gate.json` exists in no revision,
and that the gate script's `MODELS` genuinely excludes ViNT. If either fails to
reproduce, R7's disposition is wrong and the execution order changes with it.

## After a passing adjudication

Begin with the smallest missing delta: **strict-load evidence**, not inference
and not training. It exercises the checkpoint path without requiring a frozen
input batch or a declared tolerance, so a surprise there costs least.

## Contingency: if either decisive claim fails to reproduce

If step 1 or step 2 below does not reproduce, the correct response is **two
actions, not one**.

```
1. Recompute whether vint_gate.json exists in any revision.
2. Recompute whether scripts/15_reproduction_gate.py excludes ViNT from MODELS.
3. Only if both claims hold, retain ViNT R7 = RERUN.
```

**First**, correct the disposition and the execution order before any checkpoint
is touched. ViNT R7 = `RERUN` is the only disposition that changes the execution
order, so a failure there invalidates the plan, not merely a table row.

**Second — and this is the part easily skipped — file the miss under
`gates/failures/`.** A failure here is not only a fact about ViNT. Five search
agents and a synthesiser reported those claims with high confidence, after being
instructed to verify at least two findings independently and to state their
coverage gaps. If that apparatus still produced a wrong claim that reached a
preregistration draft, the finding is about **how much weight a fan-out summary
can carry into frozen protocol**, and it belongs beside F-M2-1, F-M2-4 and
F-PILOT-1 rather than being quietly corrected in place.

Record, at minimum: which claim failed, which agent angle produced it, what the
correct value is, how far it propagated (audit report, amendment text,
disposition, execution order), and what would have caught it earlier. The
generalisation to test against is whether "verify two findings yourself" is a
sufficient bar when the output is destined for a preregistration rather than a
review file.

If both claims reproduce, record nothing — a check that passed is not a defect,
and this section does not apply.

---

# Round 1 result and required corrections

**Verdict: `Fixing` · committable: FALSE · 4 blocking defects.**
Full verdict: `/tmp/.../tasks/wx6bcfuuq.output` (re-run the workflow if expired).

**Check 10 passed.** Every numeric claim reproduced — three checkpoint digests
and byte counts, `MODELS` at `:49`, `choices=sorted(MODELS)` at `:260`,
`strict=False` at `02_verify_checkpoints.py:168`, 29,662,397 params,
`1.4594107256016287e-08`, NoMaD `repeat_count 3`, the 41,872-pair manifest.

## The four corrections, in order. Do 3 before touching the execution order.

**1. Remove the false ViNT traceability claim.** Delete every statement that the
traceability matrix referenced a nonexistent `vint_gate.json`. Replace with:

> The audited repository contains no `vint_gate.json`, and
> `scripts/15_reproduction_gate.py` restricts the gate to GNM and NoMaD. The
> family-level reproduction claim therefore has no machine-readable ViNT R7 gate
> record in the audited lineage. No claim is made that the traceability matrix
> itself referenced a ViNT gate artefact.

Frame the historical defect as an **unsupported family-level R7 assertion**, not
a traceability link that never existed.

**2. Separate the two artefact classes.**

```
experiments/_evidence/                 IGNORED (.gitignore:92) - checkpoint verification
experiments/validation/m1_family/      TRACKED - gnm_gate.json, nomad_gate.json,
                                       and NO vint_gate.json
```

ViNT R6 DELTA reason becomes: *historical checkpoint verification used
`strict=False`; 0 missing and 0 unexpected recorded, but strict loading was never
asserted. The checkpoint-verification record resides in an ignored evidence area
and is not durable from a clean clone.*

**ViNT R7 must not mention gitignore at all.** Its evidence is stronger without
it: *the gate directory is tracked, GNM and NoMaD gate artefacts are present,
ViNT is excluded by the gate script, and no ViNT gate artefact exists in the
audited revisions.* This removes the internal contradiction.

**3. Rebuild the crosswalk with provenance columns** — the largest correction.
Per adopted rung: source repository · commit SHA · tag · evidence path · model ·
checkpoint digest · dataset identity · dataset/manifest digest · execution record
· historical claim boundary preserved · current disposition · missing delta.

**Derive each row by re-reading the source artefacts. Do NOT populate from the
earlier fan-out summary** — that is what produced defects 1 and 2. Then:

> No historical rung may affect the execution order unless its repository,
> commit/tag, evidence path, checkpoint identity and dataset identity are
> explicitly recorded in the crosswalk.

**4. Restore ViNT R8's claim boundary.** `vint_entry_point.json` cannot be
summarised as "training succeeded". Retain: one smoke-scaled epoch, random
initialisation, batch 24 against official 256, public GO Stanford, `train.py`
completed, loss identity checked, and explicitly not a reproduction of a
published ViNT result. R8 establishes **prior training-mechanics execution
only**, never public-data training reproduction — otherwise a smoke test turns
the second column green.

## Re-check before re-adjudicating

Amendments 1–4 byte-identical · frozen section == `d4fc321` · no stale
traceability sentence · no statement that gate artefacts are gitignored · every
adopted rung has concrete provenance · ViNT R8 retains its claim boundary · no
checkpoint loaded · no inference · no training.

Then Trigger-3 again. **Do not commit merely because the verdict says `Fixing`** —
require committability: adjudication complete, no blocking defects remaining.
First execution remains strict checkpoint loading: no frozen batch, no tolerance,
no training loop.

---

# Round 2 brief — START HERE after /clear

All four round-1 corrections are applied. Amendment 5 is corrected,
provenance-complete, and **uncommitted** at 379 insertions / 0 deletions.

> Adjudicate the corrected Amendment 5 under Trigger-3. Treat the
> provenance-complete crosswalk as the controlling historical-evidence map.
> Independently verify its load-bearing provenance cells from primary artefacts
> rather than accepting the audit summary. In particular, re-derive:
>
> * ViNT R8 evidence at commit `ce9708e`;
> * that ViNT R8 `source_tag = NOT ESTABLISHED`;
> * GNM R7 `repeat_count = 1`;
> * the corresponding checkpoint, dataset, evidence-path and claim-boundary
>   fields;
> * that each execution-order step is justified by a specific crosswalk row
>   rather than by model symmetry.
>
> Recheck all ten high-risk areas above. Do not execute any reproduction rung
> during adjudication. Return the verdict and explicit `committable` status
> separately. If defects remain, identify the minimum correction and its exact
> evidence basis. Amendment 5 may be committed only when Trigger-3 explicitly
> determines it is committable.

## Two areas needing extra scrutiny in round 2

**1. Crosswalk provenance integrity.** Every `REUSE` / `DELTA` / `RERUN` /
`UNDER RECONCILIATION` cell must trace to an exact repository, commit, path,
checkpoint and dataset, with the original claim boundary preserved.
**`NOT ESTABLISHED` must remain `NOT ESTABLISHED`** — it must not become an
inferred tag for tidiness. ViNT R8's absent tag is the specific case: symmetry
with GNM and NoMaD invites writing `900c418`, and that would be false.

**2. Execution-order derivation.** Each step must follow from a crosswalk row,
not from a model's position in a list:

```
R5      REUSE -> no rerun
R6      strict-load deltas only
GNM R7  repeatability delta, because historical repeat_count = 1
ViNT R7 genuinely new deterministic execution
NoMaD R7 reconciliation first; execution only for a demonstrated missing delta
R8      model-specific deltas only
R9-R11, SR, NE, SPL  remain closed
```

## After round 2 there are exactly two branches

```
committable = FALSE -> correct only demonstrated defects -> re-adjudicate

committable = TRUE  -> commit Amendment 5
                    -> verify clean/pushed state
                    -> begin the smallest execution delta:
                       strict checkpoint-load evidence
```

## Handoff state at /clear

```
HEAD = d0e2492
PREREGISTRATION.md   Amendment 5, 379 insertions / 0 deletions, UNCOMMITTED

Uncommitted:
  PREREGISTRATION.md
  gates/reproduction/PRE_A5_EXISTING_EVIDENCE_AUDIT.md
  gates/reproduction/AMENDMENT_5_ADJUDICATION_BRIEF.md
  gates/failures/F-A5-1.md
  docs/drafts/IMAGENAV_EPISODE_CONTRACT.md

Integrity: Amendments 1-4 byte-unchanged · frozen section == d4fc321
Execution: checkpoint load NOT RUN · inference NOT RUN · training NOT RUN
           runs/ absent · commit NONE
```

---

# Staleness notice — appended 2026-08-13, not a rewrite

This brief is a working note recording the instructions given at rounds 1 and 2.
It is **superseded in several particulars** by rounds 3, 4 and 5, and is retained
unedited above so the adjudication history is not rewritten. Where it and
`PREREGISTRATION.md` disagree, the amendment governs.

Known stale statements above, and what is now true:

| Stale | Current |
|---|---|
| "379 insertions / 0 deletions" | the diff has grown through five adjudication rounds; see `git diff --numstat` |
| "`R8   model-specific deltas only`" in the round-2 execution sketch | **R8 is withdrawn from Amendment 5** and requires a further dated amendment defining the R8 criterion (round 4) |
| "After a passing adjudication … begin with the smallest missing delta: strict-load evidence" | still correct, and now the *first* step of a six-step order rather than a nine-step one |
| The re-check list at "Re-check before re-adjudicating" | incomplete: it omits the Trigger-3 classification, whose absence was defect R2-D6. The checklist itself had a hole. |

The authoritative round-by-round record is
`gates/redteam/trigger3-amendment5-2026-08-13.md`.
