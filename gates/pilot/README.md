# Two-trajectory compatibility pilot — status and evidence

## Status: BLOCKED

| | |
|---|---|
| Isaac Sim runtime | **unavailable** — see `gates/failures/F-PILOT-1.md` |
| Pilot collection | **BLOCKED** |
| Harness validation | **executable, and executed** |
| GO Stanford source dataset | **reference only** |

**Nothing in this directory is pilot evidence.** No trajectory has been
collected. The two trajectories Prof. Bo asked for do not exist, and neither
report here counts as one of them.

## What was done, and why

Collection is blocked on a missing Isaac Sim runtime. The evidence machinery
that will judge the two pilot trajectories does not depend on how the frames are
produced, so it was built and validated against the existing, verified GO
Stanford corpus while collection is unavailable. When Isaac Sim becomes
available the pilot then tests the *data*, rather than debugging the evidence
system and the data at the same time.

## The harness

`src/navfm/compat.py` — twelve required checks over one trajectory directory.
Every check is required: one failure makes the overall result `BLOCKED`. There
is no "green if most passed", because a partially compatible trajectory is not
compatible.

The last two checks are not reimplementations of the contract. Check 11 runs
`navfm.validate`; check 12 builds the reference `ViNT_Dataset` over a split
containing only that trajectory and draws a sample through it. The first ten are
diagnostic, so that a failure at 11 or 12 arrives with a located cause rather
than a traceback.

No checkpoint is loaded. `vint.pth` is not touched: whether the data path
accepts the data is a question about the data.

## Both directions, on real data

| Report | Result | Why that is the correct result |
|---|---|---|
| `harness_validation_as_released.txt` | **BLOCKED** | The released GO Stanford corpus stores `position` and `yaw` as object-dtype arrays and does **not** satisfy the Option 1 contract (F13, `docs/DATA_CONTRACT.md`). A harness that passed this would be measuring nothing. |
| `harness_validation_converted.txt` | **PASS** | The same trajectory after the approved `navfm.trajio` boundary. Exercises `navfm.validate` and the unchanged ViNT data path end-to-end. |

The harness is validated only because it does both. A harness that passes
everything and a harness that fails everything are equally uninformative.

`harness_tests.txt` records the unit suite: a compliant fixture passing every
check, and eight broken fixtures each failing the one check that should catch
it — missing `traj_data.pkl`, missing image, bad numbering, wrong `position`
shape, wrong `yaw` shape, non-finite values, a multi-valued scalar cell, and an
unreadable image.

## Reproducing this

```
python scripts/harness_validation.py --data-folder ~/navfm-data/go_stanford/go_stanford
```

| | |
|---|---|
| Trajectory | `no10vcF_10_0` (first directory, sorted) |
| Corpus digest | `1fe1411945abd9cd0f335e845fe40d3477aac641aeb5669c961ec9debc4fb8a4` (`go_stanford.zip`, `gates/G0/SHA256SUMS`) |
| Conversion | `navfm.trajio` `trajio_v1` |
| Frames | 68 |

The original corpus is never modified. The converted trajectory is a derived
artefact written to scratch and deliberately **not** committed — what is
committed is the report about it, so that no directory in this repository can
later be mistaken for collected data.

## What happens when Isaac Sim is available

The deliverable becomes small, which is the point of doing this now:

```
collect trajectory 1 -> run this harness -> PASS / BLOCKED
collect trajectory 2 -> run this harness -> PASS / BLOCKED
```

Reports for real pilot trajectories will carry `collected_by_project: true` and
`pilot_evidence: true`. Every report in this directory carries both as `false`.
