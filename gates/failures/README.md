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
| [F-AMEND-1](F-AMEND-1.md) | protocol deviation (push ordering) | protocol | no — no evaluation existed in the interval |
| [F-M2-1](F-M2-1.md) | documented prerequisites disable the upstream proof | environment | no — found before G0.c ran |
| [F-M2-2](F-M2-2.md) | sourced ROS overrides the canonical interpreter's imports | environment | no — found before G0.c ran |
| [F-M2-3](F-M2-3.md) | **external corpus limitation, not a pipeline defect** — undocumented second scene-naming family | data (reference corpus) | no — open question, recorded before the split committed |

The three `F-M1-*` records were found during M1 verification and fixed in
`c82e406`, the commit tagged `m1-freeze`. Before that commit, the claims they
threatened were stated in `gates/M1/README.md` as though already true.
`F-AMEND-1` is a deviation rather than a defect: it records sequencing between
a commit and a push, and it is the first entry detected by operator
self-report rather than by a control.

Seven entries, none of which moved a number, is the expected early shape of
this ledger and not a sign it is idle: no scientific result existed yet, so
every defect caught was necessarily caught before it could contaminate one.
That is the cheapest possible correction. The ledger will get more interesting
— and the KPI more informative — once there are results for a defect to
threaten, starting at G0.c.

**F-M2-3 is counted separately.** It is an external reference-corpus limitation
discovered by the pipeline, not a defect in this project's evidence pipeline, and
grouping it with the others would inflate this project's defect count with
someone else's corpus.

Two of the five programme KPIs read from this directory: **claim correction
yield** (field 7 across all records) and **protocol deviation rate** (records
whose source is `protocol`, each classified and justified). Both are
measurements of the controls, not of the researcher, and both are weakened by
a record that is omitted because it caused no damage.

**These are not model defects.** None of the three changes what any navigation
model predicts. They change whether a claim about what it predicts can be
checked, which is the thesis's actual subject.
