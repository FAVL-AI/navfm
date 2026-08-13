# Trigger-3 adjudication — Amendment 5 (GNM / ViNT / NoMaD reproducibility study)

Date: 2026-08-13
Trigger: 3 (amendment to PREREGISTRATION.md)
Artefact: `PREREGISTRATION.md` `## Amendment 5` to EOF, plus
`gates/reproduction/PRE_A5_EXISTING_EVIDENCE_AUDIT.md`,
`gates/reproduction/AMENDMENT_5_ADJUDICATION_BRIEF.md` and
`gates/failures/F-A5-1.md`
Method: independent reviewer per round, artefacts and git history only, not the
drafting session's reasoning; instructed to refute rather than summarise and to
default to "refuted" when uncertain. Verdict and committability returned as
separate fields, so that `Fixing` could not be read as permission to commit.

## Verdicts

| Round | Verdict | Committable | Blocking |
|---|---|---|---|
| 1 | Fixing | FALSE | 4 — a false traceability claim, a tracked/ignored conflation, a crosswalk without provenance columns, and a ViNT R8 claim boundary summarised away. Filed as `gates/failures/F-A5-1.md`. |
| 2 | Fixing | FALSE | 6 — below. |
| 3 | Fixing | FALSE | 3 — below. All six round-2 corrections verified correct and complete. |
| 4 | Fixing | FALSE | 3 — below. All three round-3 corrections verified correct and complete. |
| 5 | Fixing | FALSE | 2 — below. Both introduced by the round-4 corrections. |
| 6 | Fixing | FALSE | 3 — below. One introduced by round 5; two pre-existing that rounds 1-5 did not reach. |
| 7 | Fixing | FALSE | 1 — a crosswalk preamble asserting fork provenance for all twelve rows; three R5 rows are `navfm`-sourced. |
| 8 | **Fixing** | **TRUE** | **0** — four-lens adversarial panel; the one claim raised was refuted on both limbs and the refutation independently re-confirmed. |

## Round 2 — six defects, all independently re-verified before correction

Every defect was re-derived from primary artefacts by the drafting side before
any text was changed. **A reviewer's statement is evidence to verify, not a fact
to copy without recomputation** — Amendment 4's rule, applied here to a review
that turned out to be right on all six counts. That the review was correct is
the outcome, not the reason: the verification is what licenses acting on it.

| | Defect | Verification command | Result |
|---|---|---|---|
| D1 | Three R5 rows label `checkpoints/SHA256SUMS` "(tracked)" | `git check-ignore -v`; `git ls-files --error-unmatch`; `git log --all --` | **ignored** at `.gitignore:22`; matches no known file; never tracked in any revision. CONFIRMED |
| D2 | ViNT R6 pairs `900c418` with an evidence path absent there | `git ls-tree -r 900c418 \| grep official_reproduction`; `git log --diff-filter=A` | 0 files at `900c418`; log introduced at **`0afa095`** (2026-07-30). `checkpoint_verification.json` untracked, `verified_utc 2026-07-30T10:10:16Z`, postdating `900c418` (2026-07-27T11:05:32+01:00). `nomad_gate.json` carries **no tensor-count field** — only `parameters: 19049675`. CONFIRMED |
| D3 | GNM R7 / NoMaD R7 ran on synthetic input, not GO Stanford | `git show 900c418:scripts/15_reproduction_gate.py` `:113–125`, `:152`, `:155`, `:193`, `:196` | `official_frame` builds each frame from `np.random.default_rng(SEED+i)`, `SEED = 0`, 480×640×3 `uint8`. Docstring: *"Synthetic, and not benchmark data."* Sole input source for both models. CONFIRMED |
| D4 | "`vint_entry_point.json` exists at exactly one commit" | `git cat-file -e` over `git rev-list --all` | contained in **100 commits**; *introduced by* one. CONFIRMED |
| D5 | `.gitignore:92` cited for the audited revision | `git show 900c418:.gitignore` | `experiments/_evidence/` is at **line 87**; line 92 is `# OS`. Line 92 holds only at fork HEAD. CONFIRMED |
| D6 | No Trigger-3 classification stated | `grep -in "fixing\|rescu"` over `:765–1142`; compare Amendments 1 `:153`, 4 `:720` | only a precondition sentence, never a classification. CONFIRMED |

### D3 is the one that changed the execution order

The other five are provenance accuracy. D3 is a decision.

Amendment 5's R7 criterion requires a frozen **GO Stanford** input-batch digest.
Execution step 5 permitted NoMaD R7 to "perform no new NoMaD inference" if every
frozen R7 requirement could be satisfied by referenced evidence. Read against the
crosswalk as it stood — ten-step DDPM, three bitwise-identical repeats, checkpoint
digest, tracked path, **and no dataset column at all** — that exit was reachable.

It is false. The historical input was synthetic, so the GO Stanford input digest
is *unsatisfiable by reference* no matter how many repeats the record carries.
NoMaD R7 always retains a real execution delta. GNM R7's gap is likewise not only
repeatability but the input population, which step 2's wording obscured.

The structural cause is recorded rather than only the symptom: the crosswalk had
**no dataset-identity or dataset-digest column**, though round 1's correction 3
required both. A column that does not exist cannot hold a wrong value, and cannot
be checked. Its absence breached the amendment's own gate — that no evidence may
affect an execution-order decision unless its dataset identity is recorded.

## Corrections applied after round 2

| | Correction |
|---|---|
| D1 | R5 rows now cite `gates/G0/SHA256SUMS` (**tracked**) as the durable record, and mark `checkpoints/SHA256SUMS` an ignored working copy with identical checkpoint lines. The R5 evidence section is re-pointed to the tracked file. |
| D2 | ViNT R6 `source_commit` split: **`0afa095`** for the tracked log, **NOT ESTABLISHED** for the untracked artefact, with its self-date recorded and its `900c418` state declared permanently unrecoverable. NoMaD R6 tensor count re-sourced. The over-broad "not durable from a clean clone" sentence scoped to the untracked JSON only, with the earlier wording named as overstated. |
| D3 | Two columns added — **dataset identity** and **dataset / input digest** — and populated for all twelve rows. GNM R7 and NoMaD R7 carry the synthetic-frame identity, the seed protocol and the input digests (`1ed344aa3591f729…`, goal `987d033e0031b9c5…`). Steps 2 and 5 restated: step 5 now states the delta is **known in advance to be non-empty** and cannot terminate at zero new inference. The NoMaD R7 narrative clause carries the same bound. |
| D4 | "exists at" → "is **introduced by**", with the 100-commit fact stated and the load-bearing half (no tag reaches it) preserved. Corrected in the amendment and struck-not-deleted in the source audit. |
| D5 | `.gitignore:87 at 900c418`, with `:92 at fork HEAD` recorded beside it. |
| D6 | Trigger-3 classification stated explicitly: **fixing**, with the reasoning that a rescuing amendment widens what may be claimed after a result is seen, and this one narrows what may be claimed before any result exists. |

## Round 3 — three defects, two of them decision-bearing

All six round-2 corrections were verified correct and complete. Three defects
remained, and their distribution is the finding: **one was a correction that did
not propagate, one was a false premise that had survived every prior round, and
one was introduced by the round-2 corrections themselves.**

| | Defect | Verification | Result |
|---|---|---|---|
| R3-D1 | The ASCII summary ladder still read `NoMaD historical reconciliation -> delta only if required` and `GNM repeatability DELTA` | read the ladder against corrected steps 2 and 5 | The prose was corrected; the summary was not. `"delta only if required"` is a conditional admitting "not required" — the exact zero-execution exit the amendment declares was the defect, restated in the block an executor is most likely to follow. CONFIRMED |
| R3-D2 | *"G0.c is now closed at `eee5a66` with freeze audit 16/16"* | `docs/WORKFLOW.md:82`; `gates/G0/freeze_audit.txt`; `ls -d runs`; committed `PREREGISTRATION.md:451–452`; `git log -1 eee5a66` | G0.c is **defined** as evaluating `vint.pth` at batch 400. The freeze audit concludes "the protocol is frozen and G0.c **may execute**", and two of its sixteen checks pass *because no result exists*. `runs/` absent. `eee5a66`'s own subject is "**Freeze** the G0.c evaluation population". The claim is false. CONFIRMED |
| R3-D3 | "assigns `DELTA` or `RERUN` to eight of **eleven** rungs" | count the crosswalk | **twelve** rows: 7 DELTA, 1 RERUN, 3 REUSE, 1 UNDER RECONCILIATION. Eight of twelve. CONFIRMED |

### R3-D2 is the most serious defect found across all four rounds

Not because it is the largest error — it is one clause — but because of what it
was load-bearing for. It was the **sole stated basis for retiring the prohibition
on loading the released checkpoint**. Every downstream execution in this
amendment begins with that load.

The claim had survived rounds 1, 2 and the entire pre-amendment audit. It is
false in a way that is easy to miss and hard to unsee: `eee5a66` genuinely did
close something, and the freeze audit genuinely did reach 16/16 — but what closed
was the *freeze*, not the *gate*. G0.c is defined by `docs/WORKFLOW.md:82` as the
evaluation itself, and two of the freeze audit's own sixteen checks
(`no_existing_g0c_result_directory`, `no_pre_audit_evaluator_output`) pass
**precisely because that evaluation has not run**. The audit that authorised
execution was read as evidence that execution had happened.

The correction does not merely restate the basis; it narrows the permission. The
retired prohibition
(`docs/reviews/2026-07-31-g0c-amendment-specification.md:304`) reads *"the
released checkpoint must not be loaded **for evaluation**"*. R6 is a strict
state-dict load that produces no metric, no dataset pass and no classification.
So the clause now retires the restriction **for R6 only**, and G0.c continues to
execute under its own frozen protocol rather than under this amendment.

> A gate retired on a false premise is not a gate. Where a clause authorises the
> single most consequential action in a protocol, the standard is not that it
> sounds right but that its stated basis is independently true — and "the audit
> that permits X passed" is never the same statement as "X has happened".

### R3-D3 was introduced by the round-2 corrections

The wrong count sat inside the Trigger-3 classification paragraph added to
discharge R2-D6. A correction written to satisfy the gate carried a new
unverified number through the gate. That is the third consecutive round in which
the previous round's corrections introduced fresh defects, and it is the reason
the adjudication continues rather than stopping at a `Fixing` verdict.

## Round 4 — three defects, and the amendment narrowed as a result

| | Defect | Verification | Result |
|---|---|---|---|
| R4-1 | The execution-order preamble read *"Only the following, in order, and not training:"* while steps 6–8 of that same list authorised R8 training-mechanics deltas | read the preamble against steps 6–8, the ladder and the closing line | mutually exclusive instructions. An executor following the preamble refuses steps 6–8; an executor following steps 6–8 launches training. CONFIRMED |
| R4-2 | "persists in 100 commits through the fork tip" | tree-containment over `rev-list 219f717`, over `--branches --tags --remotes`, and over `--all` | **98**, 98, 100. The two extra are `refs/stash` entries, reachable from no branch. CONFIRMED |
| R4-3 | Steps 6–8 and three crosswalk cells cited "the frozen Amendment 5 R8 criterion" | grep over the amendment and the repository | **no R8 criterion is defined anywhere.** The amendment defines an R7 criterion, a repeatability criterion and an R6 record checklist — and no R8 criterion. CONFIRMED |

### The resolution narrowed the amendment rather than repairing the sentence

R4-1 admitted two fixes: amend the preamble to permit R8, or withdraw the R8
steps. The second was taken, and R4-3 is why.

Closing R8 means **official-scale configuration** — `batch_size: 256`,
`epochs: 100` (`third_party/visualnav-transformer/train/config/vint.yaml:7–8`)
against a historical record of batch 24 and one epoch. That is a full training
run: the most costly and least reversible action in the programme. And it would
have been authorised by an execution step measured against a criterion the
amendment asserts it has frozen and has not.

> Authorising the most expensive action in a protocol, against an undefined
> criterion, through a list whose own preamble forbids it, is precisely what a
> preregistration exists to prevent. R8 is therefore withdrawn from Amendment 5
> and requires a further dated amendment that first states its criterion.

The historical R8 evidence remains adopted by reference for exactly what it is —
prior training-mechanics execution, not a reproduction of any published result,
and in ViNT's case explicitly not comparable to GNM's or NoMaD's numbers.

### R4-2 is the fourth consecutive round in which a correction shipped an unrecomputed number

The figure `100` entered as a **round-2 correction** to a struck claim, passed
through round 3 untouched, and was wrong. Its cause is worth recording because it
will recur: the count was taken with `git rev-list --all`, which includes
`refs/stash`. The sentence it supported said "through the fork tip" — a
*branch-reachable* claim — so the command did not measure the quantity the
sentence asserted.

> Choosing the wrong enumeration is not a typo; it is measuring a different
> population and reporting it as the one you named. `--all` is not "the
> history" — it is every ref, stashes included. This is the same class as the F13
> subfinding, where a measurement over 44,038 samples was reported for a
> registered population of 41,872.

## Round 5 — two defects, both created by the round-4 correction

| | Defect | Verification | Result |
|---|---|---|---|
| R5-1 | The GNM R8 cell gave official scale as `batch_size: 256`, `epochs: 100` | `third_party/visualnav-transformer/train/config/gnm.yaml:9,11` @ `dca7981`; corroborated by tracked `900c418:experiments/configs/gnm_gostanford_smoke.yaml:14,16` | GNM's official scale is **`batch_size: 400`, `epochs: 30`**. The smoke config annotates its own values `# [SMOKE] official: 400` and `# [SMOKE] official: 30`. CONFIRMED |
| R5-2 | The R8-withdrawal prose generalised "official scale is 256/100" across all three models, and "against a historical record of batch 24 and one epoch" | the three `*_entry_point.json` records | GNM official 400/30; ViNT and NoMaD 256/100. Historical: GNM 24/1, ViNT 24/1, **NoMaD 16/1**. The summary contradicted the amendment's own NoMaD R8 cell, which correctly says 16. CONFIRMED |

### Both are the same error, and it is the one this amendment is *about*

The GNM figure was not misread from a source. It was **inferred from ViNT by
symmetry** — written into a table the amendment declares provenance-complete,
under its own governing rule that *"fields not independently establishable are
written `NOT ESTABLISHED` and are never inferred"*, two hundred lines below a
section titled **"Four provenance facts that symmetry would have got wrong."**

> The failure mode a document describes is not thereby a failure mode the
> document is immune to. Amendment 5 identified symmetry-inference as its
> principal hazard, catalogued four instances of it in the historical record, and
> then committed a fifth in its own frozen table while correcting something else.

The NoMaD half is the round-3 and round-4 genus again: a summary contradicting
the table it summarises. Three consecutive rounds have now been decided by that
shape, which is itself the finding — **a correction is not complete when the
sentence is fixed; it is complete when every summary, enumeration, preamble and
table cell that restates it has been re-derived.**

### What did *not* fail

The withdrawal of R8 stands. A 24→400 / 1→30 delta cannot close without a full
training run any more than 24→256 / 1→100 can, so round 4's conclusion survives
its own wrong premise. That is worth recording precisely because it is the
tempting reason not to correct: the answer was right. The basis was false, and a
frozen table carrying a false figure is a defect whatever conclusion rests on it.

## Round 6 — three defects: one new, two that six rounds had not reached

| | Defect | Verification | Result |
|---|---|---|---|
| R6-1 | The round-5 corroboration sentence cited one smoke config as corroborating "the figures" — six values across three models | `git show 900c418:experiments/configs/gnm_gostanford_smoke.yaml` | the file is GNM-only (`model_type: gnm`). It corroborates two of six. Tracked corroborators for the other two **do exist** and were located: `900c418:.../nomad_gostanford_smoke.yaml:15,17` and `ce9708e:.../vint_gostanford_smoke.yaml:9`. CONFIRMED |
| R6-2 | *"Common to every row: `source_repository` = `FAVL-AI/visualnav-transformer` ... `verification_source` = direct `git show`"* | `git ls-files --error-unmatch gates/G0/SHA256SUMS`; the amendment's own R5 rows | false for the three R5 rows, whose evidence is tracked in **`navfm`** and verified by `sha256sum -c`; and false for the ViNT R6 row's untracked artefact, which `git show` cannot retrieve at any commit. CONFIRMED |
| R6-3 | The repeatability criterion was scoped *"For GNM and ViNT"* while step 5 **mandates** a NoMaD R7 execution requiring a tolerance record | `grep -i toleran` over the amendment | exactly one tolerance declared, scoped to two models; demanded by the NoMaD R7 crosswalk cell and by step 5. CONFIRMED |

### R6-2 and R6-3 are the same structural failure, and neither was introduced by a correction

Both are **scope errors**: a claim quantified over a range wider than the range
it is true of. R6-2 says "every row" of a table where four rows take different
provenance. R6-3 says "GNM and ViNT" in a criterion that a later mandatory step
requires for a third model.

They matter differently from the earlier rounds' defects. Rounds 1-2 found false
statements about the historical record; rounds 3-5 found corrections that failed
to propagate. These two were in the amendment from the beginning and survived six
independent passes, because **a scope line reads as boilerplate**. "Common to
every row" and "For GNM and ViNT" both look like preamble rather than claim, and
neither carries a figure to recompute.

> Quantifiers are claims. "every", "all three", "only", "never", and a scope list
> naming two of three models are each an assertion over a range, and each must be
> tested against its whole range — not read as framing for the assertions that
> follow.

R6-3 is the more serious of the two because it made an instruction *unexecutable*
rather than merely inaccurate: the amendment ordered a NoMaD run and declared no
rule for accepting its result, which would have left the tolerance to be chosen
after the outputs were seen. That is precisely what the no-rescue clause exists
to forbid, arriving not as a deliberate widening but as a range that was never
checked.

## Round 7 — one defect: the same sentence, ten lines up

| | Defect | Verification | Result |
|---|---|---|---|
| R7-1 | *"Every row derived by re-opening the primary artefact in `/home/favl/robotics/FleetSafe-VLA`."* | `git log --all -- gates/G0/SHA256SUMS` in the fork → **empty**; `git ls-files` in `navfm` → tracked; the three R5 cells read *"n/a — digest verified in `navfm`"* | false for three of twelve rows. CONFIRMED |

Round 6 scoped the *"Common to every row"* sentence and added an explicit
exception naming these same three R5 rows. It did not scope the identical claim
**ten lines above it**, in the same section. The correction and the surviving
defect sat on the same page.

> A defect and its fix can be neighbours. Propagating a correction means
> re-reading the passage, not the sentence — and a second statement of the same
> claim is the most likely place for the old version to survive, precisely
> because it was written to say the same thing.

The correction replaced the blanket claim with an explicit three-kind partition:
eight fork-sourced rows, three `navfm`-sourced R5 rows, and ViNT R7 resting on a
verified absence rather than on any artefact. Twelve rows, each assigned to
exactly one kind.

## Round 8 — committable

**Verdict: `Fixing` · committable: TRUE · 0 blocking defects.**

Round 8 was run as an adversarial panel rather than a single reviewer, because
rounds 6 and 7 were each decided by a claim a prior single reviewer had passed.

* **Four independent reviewers**, distinct lenses: quantifier/scope; internal
  consistency; executability; and a fresh full adjudication from first
  principles. All four returned `fixing`.
* **One blocking defect claimed** across the four — the scope of "each
  checkpoint-loading record".
* **Two independent skeptics per claim**, one testing the fact against primary
  artefacts and one testing whether it met the blocking bar. **Both refuted it**,
  and the synthesiser re-derived both refutations rather than accepting them.
* **Zero defects survived.**

The synthesiser additionally re-verified, from primary artefacts, the claims
whose falsity would have been blocking: the ViNT R7 negative existential by
exhaustive sweep of all 236 fork revisions (`vint_gate` absent everywhere, exit
1); the provenance facts at `900c418` and `ce9708e`; the R5 digests and byte
counts; the G0.c freeze; the disposition arithmetic (7 DELTA + 1 RERUN + 3 REUSE
+ 1 UNDER RECONCILIATION = 12); and the ViNT R8 loss residual, recomputed to
`1.4594107256016287e-08` and matching.

## The generalisation this round adds

Round 1 established that mechanistic **prose** needs the same verification as
numbers (`F-A5-1`). Round 2 sharpens it:

> A provenance column that does not exist cannot be audited. Round 1 required
> dataset identity in the crosswalk; the correction added every other column and
> omitted that one, and the omission is what let a synthetic-input run be read
> for four rounds as GO Stanford evidence. **The absence of a field is not a
> neutral gap — it is an unfalsifiable claim**, and it survived precisely because
> there was nothing there to check.

The corollary for the crosswalk's own design: every column whose absence would
change a disposition must be present and explicitly populated, `NOT ESTABLISHED`
where the value cannot be derived. `NOT ESTABLISHED` is auditable; a missing
column is not.

Round 3 adds two more.

> **A correction must be propagated to every place the defect appears, and
> summaries are where it hides.** R3-D1 was not a missed defect; it was a
> *corrected* defect that survived in the ASCII ladder summarising the steps
> that had just been fixed. Prose and its own summary are two artefacts, and
> fixing one does not fix the other. Whoever executes the protocol will read the
> ladder.

> **"The check that authorises X passed" is not "X happened."** R3-D2 read a
> 16/16 freeze audit — an audit whose own passing conditions include *the result
> not existing yet* — as evidence that the gate it authorises had closed. This is
> a distinct failure from an unverified claim: every component fact was true, and
> the conclusion drawn from them was false. It is also the failure with the
> highest blast radius found so far, because that clause is what permits the
> first checkpoint load.

The `gates/failures/` genus this extends is F-M2-4, "checks that cannot fail".
R3-D2 is its inverse and deserves naming: **a check that passed being read as the
event it was gating**. The freeze audit could fail, did discriminate, and was
correct in every line — and was still misread, because "may execute" and "has
executed" are one word apart.

## Integrity, verified at each round

```
Amendments 1-4 byte-identical to HEAD          PASS (lines 1-763, cmp)
Frozen protocol section == d4fc321             PASS (sha256 94fde1f8da9c88bf...)
Diff is append-only                            PASS (single hunk @@ -763,0 +764 @@, 0 deletions)
Checkpoint loaded                              NO
Inference run                                  NO
Training run                                   NO
runs/ present                                  NO
```

The frozen-section check was run once against a deliberately mutated copy and
rejected it, so the check is known to discriminate rather than assumed to.
