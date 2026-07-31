# F-AMEND-1 — Protocol deviation: the amendment-session push preceded the wording correction

| Field | Record |
|---|---|
| **1. What failed** | The amendment session was pushed at `b5cf0c8` while `paper/draft.md` still carried a prospective reference introduced at `8005f45`: "This plan is fixed in `PREREGISTRATION.md` Amendment 1", written one commit before Amendment 1 existed. The push made that wording public before the correction was written, so for the duration of one push cycle the published draft asserted a pre-registration state that had not yet been reached at the commit asserting it. |
| **2. How detected** | Operator, self-reported. Not caught by a test, a gate, or a review — the ordering was disclosed inside Amendment 1 at the time it was written, and the push sequencing was reported afterwards by the operator. No automated control covers push ordering. |
| **3. Claim threatened** | The ordering claim on which the pre-registration's authority rests: that the registered protocol predates the text depending on it. Narrowly — the paper's assertion about *what* the pre-registration fixed, not the pre-registration itself. |
| **4. Source** | protocol — specifically operator sequencing between commit and push. |
| **5. Correction** | Additive commits `f8aa982` ("Correct prospective wording introduced at 8005f45") and `9bef511`, delivered in the following push. The sentence now reads "This plan is governed by PREREGISTRATION.md, including Amendment 1 adopted before the first registered evaluation run", which is true at every commit in which it has ever appeared. History was not rewritten: the prospective sentence remains in the archive at `8005f45`, where an auditor of the ordering will find it. |
| **6. Pre-registered?** | Amendment 1 itself was pre-registered, at `459c65c`, before any evaluation. The defect was in the paper's description of it, not in the protocol. |
| **7. Results changed?** | None. No evaluation and no data collection occurred during the interval — `runs/` did not exist at any point in it, and G0.c had not been executed. Nothing could have been, or was, affected. |
| **8. Residual uncertainty** | The intermediate push state is not independently verifiable from a clone: a remote's push history is not carried in the repository, and `origin/main` now points at `9bef511`, after the correction. This record therefore rests on operator self-report for the *timing* of the push, and on git history alone for everything else. Recorded so that a later reader does not mistake the self-reported part for a verified one. |
| **9. Gate blocked or reopened** | None. No G-gate had opened. |

## Why this is filed at all

Nothing was contaminated and no number moved, so the temptation is to treat it
as bookkeeping. It is filed because the protocol-deviation rate is one of the
programme's five KPIs, and a deviation ledger that records only the deviations
that caused damage measures damage, not deviations. A control that is only
exercised when it fails expensively has not been shown to work.

It also marks the boundary of what the current controls cover. Commit ordering
between the pre-registration and the evaluator is machine-enforced from M2
onward via `--preregistration-commit`. Ordering between a *commit* and a
*push* is not enforced by anything, and this record is the evidence for that
gap rather than a claim that the gap has been closed.

Related: [F-M1-1](F-M1-1.md), [F-M1-2](F-M1-2.md), [F-M1-3](F-M1-3.md).
