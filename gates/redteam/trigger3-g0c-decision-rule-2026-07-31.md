# Red-team trigger 3 — the G0.c decision rule (Amendment 2 draft)

**Trigger.** Standing-instructions adversarial review policy, trigger 3: any
amendment to `PREREGISTRATION.md` — is it fixing the protocol, or rescuing a
hypothesis?

**Artefact.** A drafted "Amendment 2 — G0.c decision rule". Reviewed
*uncommitted*, which is the point of doing this before the commit rather than
after.

**Outcome: REFUSED. The amendment was NOT committed.** The draft is preserved
outside the repository; the pre-registration is unchanged and still ends at
Amendment 1.

**Trigger-3 classification: cannot determine.** Not *rescuing* — the reviewer
verified exhaustively that no G0.c datum exists, so nothing could have shaped
it. Not *fixing* either, on the record it presented: three of its factual
predicates are false, and its central self-description is inaccurate.

## What the refutation established, all re-verified against source

| Finding | Verification |
|---|---|
| The Reference definition cites **three artefacts that do not exist**: `gates/G0/SHA256SUMS`, a "recorded" GO Stanford zip hash, and "split files committed" | `gates/G0/` absent; the zip hash exists only in `gates/M2/README.md`; `git ls-files \| grep traj_names` empty. A pre-registration pinning a run to non-existent artefacts pins nothing |
| **It contradicts the frozen section.** Frozen: "Splits: scene-grouped holdout only. No trajectory-level splits appear in any reported table." The draft declares an *ungrouped* 0.8 split | `splits.py:75` defines ungrouped as per-trajectory; `make_tables.py:77` maps `e0` to **Table 3**, so E0.2 is a reported table by construction. The draft's closing line — "Nothing in the frozen section is edited, relaxed, redirected, or reinterpreted" — is false |
| A **directional expectation on a metric that does not exist**: rank correlation between predicted and target temporal distance | No implementation in `src/`, no key in `REFERENCE_KEYS`, no column in `OFFLINE_COLUMNS` |
| The **stability criterion contradicts the committed table generator**. Draft: "3 evaluation seeds", "CV < 5 % on total loss" | `make_tables.py:231`: "E0 is a single deterministic evaluation; everything else needs n seeds", and the run-name grammar has no seed slot for E0. Either CV ≡ 0 and the criterion is vacuous, or the committed generator is wrong |
| The **random-init control is unreproducible**, so Layer B is unsatisfiable for that arm | `offline.py:562` seeds only the DataLoader generator; the model RNG is never seeded, and `build_model` runs before it. Every Layer C directional claim rests on one unrepeatable draw |
| The **classification is not exhaustive**. Layer A passes, Layer B passes, Layer C *partially* fails → no classification applies, yet exactly one is required. Layer B failure has no home either | The draft states what happens when an unlisted metric moves, and is silent on a listed expectation being violated — the one case Layer C exists to detect |

Two further findings I accept as fair and did not re-verify in depth: the draft
reproduces the committed programme review's Layers A–D, classification names,
historical-anchor paragraph and expected-classification sentence substantially
verbatim without attribution, while framing them as its own analytic acts; and
the commit-order defect already filed as `F-AMEND-1` recurs — `d6cef79`
committed docs calling the rule "pre-registered" while it was still uncommitted
— with no disclosure section, where Amendment 1 had one.

## The finding that decides it

The draft claims to close the degree of freedom "whether 0.17398 is a target or
an anchor". **That degree of freedom was not open.** It was closed in the
opposite direction by the commit that froze the pre-registration:
`d4fc321:docs/EXPERIMENTS.md` set E0.2's criterion as "total test loss within
an order of magnitude of the checkpoint's recorded 0.17398", and
`d4fc321:docs/WORKFLOW.md` said the same. That was falsifiable. It was retired
at `d6cef79`, one commit before this draft, and replaced by a rule under which
the anchor comparison is "descriptive only… not a pass/fail threshold".

The justification for retiring it — F10, and the five-dataset composition — was
**fully available at `d4fc321`**: F10 is in `paper/draft.md` at that commit, and
the `0.17398` metadata string has been in `models/loader.py` since the first
commit. Nothing was learned in between.

There is a genuine methodological defence for dropping the criterion —
comparing non-equivalent estimands *is* bad science, and the external review
argues it well. But an amendment that retires a committed falsifiable test,
introduces no comparably risky one, and describes itself as closing an open
degree of freedom rather than reversing a closed one, has not made that defence.
That is why this is refused rather than merely corrected.

## Required before a G0.c amendment can be committed

1. Delete or correct the three false artefact references.
2. **Resolve the split contradiction explicitly** — either use a grouped split,
   or declare the ungrouped split as a scoped deviation from the frozen bullet,
   with its justification and why it does not apply to E1–E6. This is a
   protocol decision, not an editorial one.
3. Drop the rank-correlation expectation, or implement the metric first.
4. Replace or rescope the CV criterion so it measures a declared estimand, and
   reconcile it with `make_tables.py`'s deterministic-E0 contract.
5. Seed the model RNG in `offline.py` and record the seed, so the random-init
   control is reproducible and Layer B is satisfiable.
6. Give the Layer-B-failure and Layer-C-partial-failure cases a home.
7. Attribute the programme review, and add a "Commit order, for the record"
   section as Amendment 1 has.
8. State plainly that E0.2's prior order-of-magnitude criterion is being
   retired, on whose argument, and that no equally risky test replaces it.

## Why this is the review working

Trigger 3 exists because an amendment is where a protocol can be quietly bent,
and because the person writing it is the person it benefits. It caught a draft
that would have committed three false statements of fact and a silent conflict
with a frozen commitment into the one file whose whole value is that it can be
trusted without checking.

The draft was refused *before* the commit. That is the difference between this
and `F-AMEND-1`.
