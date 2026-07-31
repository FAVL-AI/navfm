# Red-team trigger 3 — PREREGISTRATION.md Amendment 1

**Trigger.** Standing-instructions adversarial review policy, trigger 3: *any
amendment to `PREREGISTRATION.md` — is it fixing the protocol, or rescuing a
hypothesis?*

**Artefact.** The `## Amendment 1 — 2026-07-31` section of
`PREREGISTRATION.md` (statistical analysis plan for E2).

**Mechanics.** Independent subagent, given the artefact plus
`paper/draft.md` §5, `docs/EXPERIMENTS.md`, and read access to the repository
and its history for fact-checking. Instructed to refute rather than summarise,
to default to REFUTED under uncertainty, and explicitly barred from treating
any commit message or in-repo justification as evidence *for* the amendment —
those being the thing under test. Two rounds were run: the second reviewed the
revision the first had forced.

## Determination

| | Round 1 (first draft) | Round 2 (revision) |
|---|---|---|
| Verdict on the draft reviewed | REFUTED | REFUTED |
| **Trigger-3 classification** | **fixing** | **fixing** |

The trigger-3 question survived both rounds: the amendment is *fixing* the
protocol, not rescuing a hypothesis. Both rounds nonetheless refuted the draft
they were given, on separate grounds. Every finding below that changed the
amendment was independently verified against source before it was acted on;
the two places where the reviewer's reading was itself wrong are recorded as
such.

## Round 1 — findings that survived, and what they changed

1. **Frozen interval procedure silently downgraded.** The draft reported the
   primary endpoint "with a 95 % CI" while routing bootstrap machinery to the
   continuous metrics alone. Frozen v1 line 14 fixes a **95 %
   percentile-bootstrap CI**. Verified against `git show d4fc321` — the draft
   would have *reopened* a degree of freedom the frozen section had closed,
   the exact inverse of an amendment's purpose. **Most serious finding of
   either round.** Corrected: the frozen procedure is restored verbatim and
   the escape route named and shut.
2. **"The analysis model was absent from v1" was inaccurate.** Frozen v1 fixes
   both an interval procedure and an aggregation level ("mean ± CI over
   seeds"). Verified. The real gap is narrower — v1 never said how the
   interaction term is estimated from episode-level outcomes. Corrected, and
   the amendment's own scope narrowed with it.
3. **"No E-cell has run" was false as written.** `gates/M1/e2e.txt:61–151`
   contains cells named `e2_nonholo_diff_seed{0,1,2}` and a "Table 4 — E2 …"
   heading with bootstrap CIs. Verified. Those are random-init models on
   synthetic noise and contain no observation of success, scene, or start–goal
   configuration — substantively harmless, textually indefensible. Corrected
   to a precise evidential statement that discloses the artefact by name.
4. Round 1 also confirmed the frozen section was untouched (byte-identical to
   `d4fc321`) and that the H1–H5 / E2-H1–H4 disambiguation resolves cleanly.

## Round 2 — findings that survived, and what they changed

1. **"Trajectory efficiency" was algebraically SPL.** As defined, it is the
   per-episode term SPL already computes
   (`src/navfm/eval/metrics.py:294–298`, `optimal / max(executed, optimal)`).
   Verified directly. Two deterministically related quantities would have
   entered one multiplicity correction. Additionally, conditioning it on
   success stratifies on a post-treatment outcome the manipulation is
   hypothesised to move. **Removed as a secondary metric**, with the reason
   recorded so the omission is a commitment rather than an oversight.
2. **Displacement before intervention is not an E2 metric.** No intervener
   exists in simulation. *The reviewer's stated mechanism was wrong* — it
   claimed `metrics.py:317` skips episodes with a `None` field; the code in
   fact substitutes `executed_length_m`. That makes the objection stronger,
   not weaker: the metric would have silently reported path length under a
   name promising something else. **Removed from E2**; it remains an E6 metric.
3. **Training seed as a random intercept is not identifiable** from three
   levels, while the primary interval resampled scenes only and so carried no
   seed variability at all. Removed from the episode-level model; seed
   variation stays where frozen v1 already carried it.
4. **Non-collapsibility of the logistic interaction.** A log-odds interaction
   can be non-zero while the probability-scale cell ordering holds, and near
   zero while it is violated — and frozen v1 states its prediction as a cell
   *ordering*. The draft never reconciled the two scales. Both are now
   reported from the same fit, with disagreement reported as the result rather
   than resolved after the fact.
5. Also adopted: nesting rather than crossing for start–goal configuration;
   fit-failure defined to include boundary/singular estimates; the fallback
   rung selected once from the full-data fit and held across all refits.

## Findings deferred rather than closed

Round 2's remaining findings — estimation software and tolerance, the held-out
scene count, the exact per-cell episode count, and the estimator
implementation — all depend on E2 design constants that do not yet exist.
Closing them now would be precision without a basis. They are deferred **by
name** in the amendment under a blocking gate condition: all four must be
fixed in a further dated amendment, with the estimator's measured type-I error
rate on simulated null data, before the first E2 episode is collected.

## Residual, accepted

- The paper (`paper/draft.md:558`, commit `8005f45`) asserts "This plan is
  fixed in `PREREGISTRATION.md` Amendment 1" one commit before the amendment
  existed. Disclosed in the amendment. The binding requirement is that the
  pre-registration predate every number in `runs/`, which holds: `runs/` does
  not exist.
- The amendment narrates its own review history, which is unusual in a
  pre-registration. Retained deliberately: the corrections are the evidence
  that the trigger-3 determination was tested rather than asserted.
- E2-H2 (`paper/draft.md:524–526`) predicts effects across collision and
  stopping metrics; the analysis plan estimates success and two secondaries.
  The pinned hypotheses outrun the pinned analysis. Recorded for the
  pre-collection amendment.
- Two intervals of different width appear in the E2 table (model-based
  primary, and the frozen seed-level summary over three seeds). Estimands
  differ and the primary is unambiguous, but a reviewer will ask which the
  abstract quotes.

## Outcome

Trigger 3 discharged: **fixing**. The amendment is committed with the round-1
and round-2 corrections applied and the deferred items gated.
