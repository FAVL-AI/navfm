# Review dispositions

Every recommendation in every archived external review, with its disposition
and the commit that implements it. One row per recommendation. Nothing in a
review is adopted silently and nothing is dropped silently: a recommendation
that is not implemented appears here with the reason.

Dispositions are exactly four: **accepted verbatim**, **accepted with
refinement**, **rejected**, **deferred**. A deferred row names the session that
owns it and carries no SHA; every other row carries the SHA of the commit that
implemented it.

## Archived reviews

| File | Scope |
|---|---|
| `2026-07-31-programme-review.md` | M1 completion and G0.c readiness. Two rounds from the same reviewer, contiguous in the source: the completion assessment, then the G0.c decision-rule response. |
| `2026-07-31-m1-review.md` | M1 verification: the three evidence-pipeline defects, the declared/canonical environment boundary, M2 priority order. |
| `2026-07-31-m2-review.md` | M2 canonical-environment milestone: F-M2-1 and F-M2-2, environment-identity semantics, acceptance-package requirements, remaining hardening order. |

All three are archived verbatim with a metadata header only, per programme-review
recommendation P32. Two notes about the source texts, recorded here rather
than in the archives themselves so the archives stay unannotated:

* The programme review's F12 algebra block arrived with paste damage (a setext
  rule and a stray `#` where the original had relational operators). It is
  archived exactly as received. If a clean original exists, re-archiving it is
  a correction to the archive, not an annotation of it.
* The M1 review's "Commit b673fa5" recommendation names a SHA that does not
  exist in this repository's history (row R8).

## Session commits

| Task | Commit | Subject |
|---|---|---|
| — | `76712df` | Add programme roadmap (as supplied, before amendment) |
| 1 | `a6c4f51` | Archive both external reviews verbatim, with a disposition for every recommendation |
| 2 | `2fcd80e` | Amend the roadmap: research questions, thesis claim, terminology, acceptance criteria, KPIs |
| 3 | `9af40e4` | Disclaim the namespace in the README |
| 4 | `8005f45` | Amend the paper: causal question, E2 hypotheses, analysis plan, defect taxonomy |
| 5 | `3f89090` | Bound the oracle substitution, and record M1's status as the review requires |
| 6 | `459c65c` | Pre-register the E2 analysis plan as Amendment 1, after two adversarial rounds |
| 7 | `52b026d` | Mirror the E2 hypotheses and analysis plan; define the failure-record convention |
| A2 | `ec98d9c` | Open `gates/failures/` with the three M1 verification defects |

## Programme review — `2026-07-31-programme-review.md`

| # | Recommendation | Disposition | Commit |
|---|---|---|---|
| P1 | M1 is technically complete, methodologically credible, scientifically non-evidentiary until G0.c | accepted verbatim | `3f89090` |
| P2 | Archived gate must carry environment identity, command invocation, source hashes, expected output signatures | deferred | M2, B2 |
| P3 | Missing seeds must never degrade into partial aggregation with silently narrower uncertainty | accepted verbatim — already implemented at M1 (`make_tables.py` exits 2, writes nothing) | `c82e406` (pre-review) |
| P4 | "Resume" must mean the same experimental identity; reject differences in checkpoint hash, dataset/manifest hash, config, evaluator version, seed set, batch size, architecture, metric implementation version; document as an evaluator invariant | deferred | M2, Task 1a |
| P5 | Keep the conformance-oracle / validity-review distinction explicit | accepted verbatim | `3f89090` |
| P6 | Classify F12 as metric redundancy, not primarily a software bug | accepted with refinement — title normalised to "Metric redundancy induced by representation normalisation" | `8005f45` |
| P7 | Add the concise formal statement of F12 to the paper | accepted verbatim | `8005f45` |
| P8 | Refusing a scheduler-horizon change on resume is the correct default | accepted verbatim — already implemented at M1 | `c82e406` (pre-review) |
| P9 | The two scheduler remedies are distinct experimental interventions; redefining the horizon must mint a new experiment identity | deferred | M2, Task 1e |
| P10 | Machine-readable result class (`evidence_class`, `scientific_result`, `model_initialization`, `data_source`) | deferred | M2, Task 1b |
| P11 | `make_tables.py` must refuse such outputs in any scientific results table | deferred | M2, Task 1c |
| P12 | Fresh-clone reproducibility, with the six stated acceptance criteria | deferred | M2, Task 5 / B3 |
| P13 | Archive completeness: the thirteen listed items in `gates/M1/` | deferred | M2, B2 |
| P14 | Evaluator must refuse resumption when the prior manifest differs from the requested identity | deferred | M2, Task 1a |
| P15 | Table lineage: retain a machine-readable source beside the rendered Markdown | deferred | M2, Task 1d |
| P16 | Test that paper-result generation rejects `random_init=true` absent an explicit smoke-test mode | deferred | M2, Task 1c |
| P17 | Do not record the red-team decision as "review was unnecessary"; use the precise wording | accepted verbatim | `3f89090` |
| P18 | Six points at which red-team review becomes mandatory | accepted with refinement — folded into the trigger list rather than added as a parallel one; the set grew from five triggers to six | `3f89090` |
| P19 | The `M1 STATUS: TECHNICALLY COMPLETE` block | accepted with refinement — adopted as the status record in `gates/M1/README.md`, wording preserved | `3f89090` |
| P20 | Keep the next work narrowly focused on G0.c; no Paper 3, safety arbitration, collection, or roadmap expansion | accepted verbatim | governs M2 (B4); no artefact this session |
| P21 | G0.c must answer the five stated questions | deferred | M2, G0.c amendment |
| P22 | The gate returns exactly one of three outcomes | deferred | M2, G0.c amendment |
| P23 | "Not reconstructable" is not an engineering failure | deferred | M2, G0.c amendment |
| P24 | G0.c cannot produce an adverse scientific outcome but can fail operationally or procedurally | deferred | M2, G0.c amendment |
| P25 | `avg_total_test_loss = 0.17398` is a provenance anchor, not a reproduction target | deferred for the amendment itself — but the contradicting claim in `gates/M1/README.md` was corrected now rather than left standing | `3f89090`; amendment M2 |
| P26 | Four-layer decision rule: procedural validity, instrument consistency, behavioural sanity, historical-anchor interpretation | deferred | M2, G0.c amendment |
| P27 | Classification semantics table | deferred | M2, G0.c amendment |
| P28 | Declare "Reconstructed but not reproduced" as the expected classification | deferred | M2, G0.c amendment |
| P29 | Oracle-substitution clause, review wording almost exactly | accepted verbatim | `3f89090` |
| P30 | Retain the integration-seam requirement separately from the oracle clause | accepted verbatim | `3f89090` |
| P31 | F12 taxonomy entry recording seven items | accepted with refinement — six recorded; the seventh (whether historical results used both values as if independent) is recorded as UNVERIFIED, since the released artefacts do not record which logged metrics entered the papers' tables | `8005f45` |
| P32 | Archive the review verbatim with metadata only; maintain a separate disposition document; do not annotate the source | accepted verbatim | `a6c4f51` |
| P33 | Pre-registration must state all six listed things explicitly | deferred | M2, G0.c amendment |
| P34 | Gate report records the five-line commit-order block | deferred | M2, Task 4 |
| P35 | Machine-enforced `--preregistration-commit` with the five verification checks | deferred | M2, Task 2 |
| P36 | The paper must not say the gate "cannot fail" without the procedural qualification | accepted — **no change required**: verified that no such claim exists anywhere in `paper/` or `docs/`. Recorded so the absence is evidence rather than an omission | `8005f45` (verification recorded in message) |
| P37 | Replace "most-cited" with "widely used" / "influential open visual-navigation implementations" until a documented bibliometric basis exists | accepted verbatim — two occurrences, one per file | `2fcd80e` (ROADMAP), `8005f45` (paper) |
| P38 | Proceed in the stated eight-step order | accepted verbatim | governs this session and M2 |

## M1 verification review — `2026-07-31-m1-review.md`

| # | Recommendation | Disposition | Commit |
|---|---|---|---|
| R1 | State explicitly that the fixes improve the validity of future claims, not the model; the contribution is "we removed three independent threats to reproducible scientific evidence" | accepted verbatim — roadmap only; verified that M1 is not referenced anywhere in `paper/draft.md`, so there is no paper site to amend | `2fcd80e` |
| R2 | Classify F-M1-1 as Specification–Execution Mismatch; preserve the invariants "never infer execution state" and "never silently change interpreters" | accepted verbatim | `3f89090` (standing rule), `ec98d9c` (record) |
| R3 | Promote "A claim that cannot be demonstrated from the archived evidence is equivalent to an unsupported claim" into the methodology chapter | accepted verbatim | `2fcd80e` (roadmap terminology), `8005f45` (paper §3) |
| R4 | Marker ownership: delete only what the gate created | accepted verbatim | `3f89090` (standing rule), `ec98d9c` (record) |
| R5 | M1 proves the gate executes in the *declared* environment, not the *canonical* one; the latter belongs to M2 | accepted verbatim | `3f89090` |
| R6 | Define the canonical environment as the identity archived in the gate manifest, not as `~/.venv-train` | deferred | M2, B1 |
| R7 | M2's first Phase 0 gate must answer "can a fresh canonical environment regenerate the M1 archive without modification?" | deferred | M2, B3 |
| R8 | Refer to the freeze commit as "M1 Freeze (commit b673fa5)" | **accepted with refinement** — `b673fa5` is a pre-`filter-branch` SHA, is not an ancestor of `HEAD` (`git merge-base --is-ancestor` → not in history), and resolves only in one machine's reflog. The freeze commit is `c82e406`, which `git rev-parse m1-freeze^{}` confirms the annotated tag points at. The thesis must cite `c82e406` / `m1-freeze`. | `a6c4f51` (recorded), `3f89090` (corrected in the archive) |
| R9 | Every gate archive begins with an execution fingerprint, before any experiment work | deferred | M2, B2 |
| R10 | Record the epistemological significance: the pipeline produced findings before it produced results | accepted with refinement — recorded in the roadmap, where the programme argument lives, rather than as a paper claim | `2fcd80e` |
| R11 | M2 priority order, seven steps | accepted verbatim | governs M2 (B ordering) |
| R12 | Record M1 as "Complete with one explicit caveat", with the two-sentence declared/canonical wording | accepted verbatim | `3f89090` |

## M2 canonical-environment review — `2026-07-31-m2-review.md`

| # | Recommendation | Disposition | Commit |
|---|---|---|---|
| M2-1 | Classify `fb393de` as the canonical-environment establishment point, not the G0.c-ready point | accepted verbatim | `0b72a5c` |
| M2-2 | Record F-M2-1 as "Evidence-completeness failure caused by silent test-population contraction", threatening compatibility, regression, archived summaries, fresh-environment reproducibility, and any claim the upstream proof passed | accepted verbatim | `c9b1ff5` |
| M2-3 | Every gate relying on a named test population enforces all three conditions: expected tests collected; none skipped, deselected or collection-failed; all collected required tests passed | accepted verbatim | `c9b1ff5` |
| M2-4 | Fail unless the exact expected count is present; use a machine-readable report over node ids, marker membership, skip reasons, collection errors and exit status, never the final pytest sentence; pin the count to the upstream commit and a test-manifest hash rather than treating it as timeless | accepted verbatim — pin is 26 required tests, node-id digest `ba3e311c…`, against upstream `dca79815` | `c9b1ff5` |
| M2-5 | Environment identity must fingerprint the effective execution instrument, not merely the package installation | accepted verbatim | `0c4dfd0` |
| M2-6 | Add a compact effective-import fingerprint (the ten listed items) and archive resolved source locations for the seven load-bearing modules | accepted verbatim — the ten items are recorded and the seven module locations both recorded (raw) and hashed (normalised). The broader list the review explicitly did *not* require — `LD_LIBRARY_PATH`, `PATH`, `CUDA_HOME`, dynamically loaded shared libraries — is deliberately excluded, per its own caution against indiscriminate hashing producing unstable identifiers | `0c4dfd0` |
| M2-7 | "Canonical" stays defined by archived identity and build specification, not by `~/.venv-train` | accepted verbatim | `0c4dfd0`, `0b72a5c` |
| M2-8 | Acceptance package contains the ten listed artefacts | accepted verbatim — all ten archived under `gates/M2/`. The clean-worktree item is recorded as a *declared* modification (`gates/M2/` itself, being written at emission time) rather than asserted clean; the reasoning is in that README | `0b72a5c` |
| M2-9 | The seven-step ordering stands; no checkpoint evaluation before the amendment is committed | accepted verbatim | governs the remainder of this session |
| M2-10 | Downloads, checksums, dataset inspection and checkpoint structural inspection may precede the amendment when explicitly classified acquisition/preflight; anything producing a model metric may not | accepted verbatim — acquisition performed and classified as such; no forward pass has run | `0b72a5c` |
| M2-11 | 1a resume identity rejects mismatch in the nine listed fields; resume continues an identical experiment rather than creating a hybrid | deferred | Task 1a |
| M2-12 | 1b evidence-class enum, six members, each declaring table eligibility | deferred | Task 1b |
| M2-13 | 1c contamination barrier refuses the six listed conditions | deferred | Task 1c |
| M2-14 | 1d every rendered table row carries a machine-readable source record with the eight listed links | deferred | Task 1d |
| M2-15 | 1e the two scheduler remedies fork experiment lineage and are never represented as equivalent resumes | deferred | Task 1e |
| M2-16 | Acquisition yields immutable records for the eleven listed items before G0.c | accepted with refinement — six are archived now (source identifier, retrieval date, file size, digest, and for the dataset its size and digest). Archive structure, checkpoint metadata, expected architecture, dataset inventory, split-generation procedure, split digest, and any malformed files require structural inspection and split construction, which are Task 4 preflight | `0b72a5c`; remainder Task 4 |
| M2-17 | The new GO Stanford split is named a **reconstruction**, never the upstream split, because F10 makes the original unrecoverable | accepted verbatim | pending — delta 5 |
| M2-18 | Record the methodological claim: a green exit status and a package-level environment fingerprint are insufficient evidence of experimental equivalence; evidence completeness and effective import resolution must be verified explicitly | accepted verbatim | pending |
| M2-19 | Record the M2 STATUS block, preserving the historical "247 tests passing" line; later counts recorded separately, never by editing the quote | accepted verbatim | `0b72a5c` |

## Provenance of the archived reviews

Recorded once, covering every review archived here and every block quoted from
them anywhere in this repository.

All review texts archived in `docs/reviews/` originate from the programme's
**external methodological review channel**, received via the principal
investigator on their recorded dates. None is an institutional, venue, or
anonymous peer review, and no metadata or citation in this repository should be
read as implying one. The metadata header on each file says exactly what the
source is.

**"Verbatim" in this repository means:** the quoted text exists in the archived
source document. It does not mean the quoting document reproduces the whole
source, and it does not license paraphrase inside a block marked verbatim.
Where a block is quoted, programme additions sit beside it and are attributed as
programme additions — as in `gates/failures/F-M2-3.md` and `gates/M2/README.md`.

## Supersessions

Two rulings were superseded after the reasoning was examined. Both are recorded
because a superseded ruling that leaves no trace looks like a ruling that was
never made.

| Superseded | Replaced by | Reasoning |
|---|---|---|
| Split allocation of "~11 scenes (6 no* + 5 sim*, or 5 + 6)" | **Trajectory-share allocation**: ~20 % of each naming family's *trajectories*, scene-grouped. Result: 15 scenes (8 no* + 7 sim*), 760 trajectories (20.6 %) | The "~11" figure is arithmetic derived from 20 % of 53 *scenes*, not a protocol choice. Scene sizes range 18–350, so a scene-count target makes the held-out data fraction whatever the drawn scenes happen to sum to. The manifest now states the criterion explicitly and commits the exact integers; scene counts are recorded as a consequence, not a target |
| Allocation under "a fixed recorded seed" | **No seed.** Deterministic BLAKE2b hash ordering of `scene_key_v1` | Accepted with refinement against the review's literal wording. Hash ordering is strictly stronger than a seeded draw: it is a pure function of the scene identifiers, reproducible without transmitting any state, and consistent with the F10 remedy already used in `navfm.splits`. The manifest records "seed: not applicable" rather than omitting the field |

An earlier scoped-deviation ruling for an ungrouped split was also retracted:
reconnaissance established that a defensible scene key exists
(`scene_key_v1`), so the frozen scene-grouping bullet is satisfied directly and
no deviation is needed.

## F13 measurement — reviewer's rulings

| Ruling | Disposition | Where |
|---|---|---|
| The archived three-cell measurement **suffices**; no re-run required | accepted verbatim | `gates/G0/measurement/`, `bc546fb` |
| **Row 2** vocabulary confirmed: "numerical-semantics-preserving compatibility adaptation, not literal era restoration" | accepted verbatim — re-verified mechanically against the refined rows: `B-A` bit-identical excludes Row 3, `C-A` not bit-identical excludes Row 1, `C-A` within tolerance with no classificatory change gives Row 2 | `bd5686e`, F13 |
| The **three-cell design is canonical** for future measurements of this kind | accepted verbatim | recorded here |
| The **contingent-cell suggestion is superseded** — an upward correction, acknowledged by its author | accepted verbatim. Worth recording why it mattered: cell B was run because the three-cell design required it, and running it is what established that the representation effect is exactly zero. Under the contingent rule it would have been skipped, leaving the 1.776e-15 unattributable between coercion and numpy version — the single question the measurement existed to answer | recorded here |
| Earlier partial application of the middle-row text | superseded by the consolidated specification; the earlier application at `bd5686e` reached the same row and the same term | cross-referenced |

## Historical wording correction

Recorded here rather than inside Amendment 1, so that a committed
pre-registration amendment is not edited after the fact:

> Historical wording correction: Commit 8005f45 referred prospectively to
> Amendment 1 one commit before the amendment was created. No evaluation or
> data collection occurred during that interval. The wording was corrected
> without rewriting history; Amendment 1 remains prior to all registered
> execution.

## Note on Amendment 1

Amendment 1 (`459c65c`) is not itself a review recommendation — it discharges
red-team trigger 3 from the standing-instructions file. It is listed here
because two adversarial rounds against it are archived alongside these reviews
under `gates/redteam/`, and because the first round caught a defect of the same
class the programme review is concerned with: a draft that silently dropped the
frozen "percentile-bootstrap" qualifier from the primary endpoint would have
*reopened* a degree of freedom the pre-registration had closed. Both rounds
classified the amendment *fixing* rather than rescuing; both refuted the draft
they were given on other grounds; the corrections are recorded in the amendment
itself.
