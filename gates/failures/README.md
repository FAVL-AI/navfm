# Failure records

One file per failure that threatened a claim, in the nine-field convention
defined in `docs/EXPERIMENTS.md`. This directory is the ledger behind the
**claim correction yield** KPI (`ROADMAP.md`): the number and materiality of
conclusions changed, narrowed, or rejected once admissibility and audit
controls are applied. A KPI without a ledger is a slogan.

| Record | Class | Source | Results changed? |
|---|---|---|---|
| [F-M1-1](F-M1-1.md) | specification–execution mismatch | environment | no — caught pre-results |
| [F-M1-2](F-M1-2.md) | unevidenced provenance | protocol | no — caught pre-results |
| [F-M1-3](F-M1-3.md) | unsafe deletion | code | no — never fired |

All three were found during M1 verification, and all three were fixed in
`c82e406`, the commit tagged `m1-freeze`. Before that commit, the claims they
threatened were stated in `gates/M1/README.md` as though already true.

Three entries, none of which moved a number, is the expected early shape of
this ledger and not a sign it is idle: no scientific result existed yet, so
every defect caught was necessarily caught before it could contaminate one.
That is the cheapest possible correction. The ledger will get more interesting
— and the KPI more informative — once there are results for a defect to
threaten, starting at G0.c.

**These are not model defects.** None of the three changes what any navigation
model predicts. They change whether a claim about what it predicts can be
checked, which is the thesis's actual subject.
