# Two-trajectory compatibility pilot — status and evidence

## Status: PASS

| | |
|---|---|
| Isaac Sim runtime | **available** — 5.1.0.0 at `~/miniforge3/envs/isaac`, bring-up verified |
| Pilot collection | **COMPLETE** — two trajectories collected, both PASS |
| Harness validation | **executable, and executed** |
| GO Stanford source dataset | **reference only** |

**Nothing in this directory is pilot evidence.** No trajectory has been
collected. The two trajectories Prof. Bo asked for do not exist, and neither
report here counts as one of them.

> **Correction.** This directory was created while the pilot was believed
> blocked on a missing Isaac Sim runtime. That belief was wrong: Isaac Sim
> 5.1.0.0 is installed at `~/miniforge3/envs/isaac` and its headless bring-up is
> verified. See `gates/failures/F-PILOT-1.md`, where the original finding is
> retained and refuted. The harness work below is unaffected and stands on its
> own; only the stated reason for doing it when it was done has changed.

## What was done, and why

The evidence machinery
that will judge the two pilot trajectories does not depend on how the frames are
produced, so it was built and validated against the existing, verified GO
Stanford corpus before collection was attempted. The pilot therefore tests the
*data*, rather than debugging the evidence system and the data at the same
time.

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


---

# Pilot result — two trajectories collected and accepted

**Success criterion, as set:** *two trajectories collected by our own pipeline
are accepted by the unchanged ViNT data path in the agreed Option 1 format.*
**Met.** Both trajectories pass all twelve required checks.

| | `pilot_0001` | `pilot_0002` |
|---|---|---|
| Motion | mostly forward | one clear turn |
| Frames | 60 | 60 |
| Total yaw change | **+14.1°** | **+85.9°** |
| End position (m) | (1.731, 0.221) | (0.999, 0.958) |
| Arc length (m) | 1.721 | 1.721 |
| `position` | `float64` `(60, 2)` | `float64` `(60, 2)` |
| `yaw` | `float64` `(60,)` | `float64` `(60,)` |
| Project validator | PASS | PASS |
| **Unchanged ViNT data path** | **PASS — 50 samples** | **PASS — 50 samples** |
| **Overall** | **PASS** | **PASS** |

Reports: `pilot_0001_report.txt`, `pilot_0002_report.txt`. Digests and derived
quantities for reproduction: `pilot_digests.json`.

## Things checked that the twelve checks do not cover

Twelve PASSes on two trajectories would look identical if the same trajectory
had been written twice, so that was checked separately:

* positions differ by up to **0.736 m**; `yaw` arrays are not equal; frame 59
  digests differ (`4d563efd…` vs `76df7c11…`);
* equal arc length (1.721 m) is **correct by construction** — constant 0.35 m/s
  for 60 frames at 12 Hz. The turn changes direction, not distance travelled;
* `yaw` is unwrapped in both (`np.array_equal(yaw, np.unwrap(yaw))`), so
  finding F1 does not apply. It is integrated from the commanded rate rather
  than recovered from a quaternion, so it cannot wrap;
* frames are genuine renders, not black: mean 120–149, std 21–57, first and last
  frames differ.

## How the data was collected

`scripts/pilot_collect.py`, run under `~/miniforge3/envs/isaac/bin/python`.
Cube proxy in `simple_room`, driven **kinematically** along a scripted path. No
controller, no planner, no physics: the pilot tests the file contract, and those
would add failure modes unrelated to the question. Each frame is captured after
`IsaacApp.step()` returns, which blocks until the renderer finishes, so image
and pose refer to the same instant.

The collected data lives at `~/navfm-data/pilot/` and is **not committed** —
images and datasets never enter this repository. `pilot_digests.json` pins what
was measured.

## What this does NOT establish

* It does not validate the M3 PRO model. The robot is a cube.
* It does not satisfy G1 or G2, and does not open general collection.
* The trajectories are not admitted for training, validation, benchmarking or
  any performance claim.
* No model was loaded and no metric was computed. `vint.pth` remains unloaded.
