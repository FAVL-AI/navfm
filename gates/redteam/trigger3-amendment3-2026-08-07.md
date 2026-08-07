# Trigger-3 adjudication — Amendment 3 (compatibility correction + patch re-binding)

Date: 2026-08-07
Trigger: 3 (amendment to PREREGISTRATION.md — "fixing the protocol, or rescuing
a hypothesis?")
Artefact: PREREGISTRATION.md `## Amendment 3`, src/navfm/trajio.py,
scripts/{verify_tolerance,patch_upstream,protocol_freeze_audit}.py, and their tests.
Method: four independent reviewers, each given only the artefacts plus the pinned
upstream source, instructed to refute and to default to "refuted" when uncertain.
No reviewer saw this session's reasoning, which is the thing under test.

## Verdicts

| Round | Verdict | Blocking defects |
|---|---|---|
| 1 | Cannot determine | 3 (unsourced figure; false comparison-site claim; false claim that the freeze audit compared a digest) |
| 2 | Fixing — not committable | 4 (`torch.as_tensor unmodified` false; audit read both sides from the worktree; audit never inspected the live clone; max-ULP figure unarchived) |
| 3 | Fixing — not committable | 3 (`2.14e14` misattributed to cancellation; vacuity counter never incremented; non-object branch silently discarded imaginary parts) |
| 4 | Fixing — one blocking | 1 (negative-zero claim with no instrument measuring it) |

Final verdict: **Fixing**. Every blocking defect above was corrected and the
correction proved by execution, in both directions where a counter or check was
involved (it fires on a corpus containing the subject; it stays silent on one
that does not).

## Why "Fixing" rather than "Rescuing"

Recorded from the reviewers' own evidence, not asserted:

- No hypothesis exists to rescue. `runs/` absent, no `metrics.json` anywhere,
  `vint.pth` unloaded, freeze audit reports "gate execution invalid".
- `PREREGISTRATION.md` is strictly append-only: `git diff --numstat` shows
  insertions only, 0 deletions. Frozen section and Amendments 1–2 byte-identical.
- The correction has no admission latitude: upstream can load NO released
  trajectory, so 3,696/3,696 cannot be a selection. It refuses rather than
  repairs, and every clause added can only make more things fail.
- The amendment argues against its own strength — it retires the 44,038-sample
  measurement as coverage, discloses that the 1-ULP bound was set after B − A
  bit-identity was known, and states that the bound must not be cited as
  evidence of accuracy.

## Findings that survive, recorded not resolved

- `6.6 × 10^-11` (and its `|true| > 10^-6` filter) exists only as prose in
  `gates/G0/measurement/README.md`. The per-element cell outputs are not
  archived and cell A needs the discarded numpy 1.23.5 environment, so it is
  not recomputable. It is non-load-bearing: it only defuses the `max_rel`
  division-by-zero artefact, which `max_abs = 1.776e-15` bounds independently.
- The three-cell measurement as a whole is unre-runnable for the same reason,
  and its population is "neither a subset nor a superset" of upstream's.
- Two freeze-audit tests assert on `inspect.getsource` substrings rather than
  behaviour. The behaviour was proved by reviewers tampering with a live clone;
  the in-repo test is textual.
- Typed-branch soft spots unreachable from GO Stanford: `int64 > 2^53` widens
  with precision loss, `Decimal` and `datetime64` cells are accepted.

## Lesson recorded

Two consecutive rounds found a blocking defect in code written to fix the
previous round's blocking defect — a counter that counted the right thing but
was called after the early return that made it unreachable, then a vacuity
claim whose subject nothing measured. Both passed isolated unit probes. The
generalisation, added to the standing habits: when a check is fixed, exercise it
through its real call path against a corpus containing the subject, not through
its helper in isolation.
