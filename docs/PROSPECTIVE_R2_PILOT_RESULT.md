# Prospective R2 pilot result

Decision: **INCONCLUSIVE. Expansion halted under the frozen integrity rule.**

Freeze: `54bfc239b3f8d4e5443212822582711b78925bbd`, branch
`agent/engineering-recording`. The independently reviewed development protocol
planned 16 paired starts (32 initial arm attempts). Only the declared first four
pairs ran: eight recordings, all collection status PASS, both collection processes
exit 0. PASS means valid recording, not successful recovery. No retries occurred.
The remaining 12 pairs (24 arm attempts) were NOT RUN. No rear-facing/hard-subgroup
start ran. No protocol, source, threshold or scoring rule changed after launch.

## Integrity failure

The frozen 2.5 mean-absolute-grayscale initial-image bound failed on two pairs.
All per-attempt source/config/checkpoint/goal/state/history checks passed; every
individual six-image history contains copies of its own live initial image.
Physical poses and headings matched within the frozen 0.02 m/2 degree bounds.
The images entering the two arms therefore differ beyond the accepted bound
despite closely matched recorded pose and initialized counters. This invalidates
the experimental comparison; a valid per-arm recording cannot repair unmatched
initial image histories. The frozen scorer returned
`continue_fixed_remaining=false` and `integrity_ok=false`. Its unchanged literal
`decision=PILOT_ONLY` identifies the scoring stage; it is not an affirmative
experimental result. The overall experiment is INCONCLUSIVE. No further
collection was launched.

| Route | Paired position error (m) | Paired yaw error (deg) | Initial grayscale MAD | Pair integrity |
|---|---:|---:|---:|---|
| s_bend_run_0000 | 0.00000000 | 0.000000 | 0.292799 | PASS |
| s_bend_run_0001 | 0.00004482 | 0.003847 | 8.242943 | FAIL |
| junction_run_0000 | 0.00003963 | 0.034796 | 1.129232 | PASS |
| junction_run_0001 | 0.00004707 | 0.039597 | 4.724297 | FAIL |

All eight attempts are retained, including the failed pairs. Removing failed
pairs to create a smaller favourable sample is not allowed. These were completed
PASS recordings, so the infrastructure-only retry rule does not permit retries.
The image-matching threshold remains 2.5; it was not relaxed after observations.

## Descriptive outcomes, not an efficacy comparison

The frozen categories below preserve every launched attempt. Experiment-wide
integrity failed; these counts cannot support comparative recovery or safety
claims. No threshold decision is evaluated on this incomplete sample.
Exact at first declaration with ten preterminal no-reentry decisions is primary;
+/-1 node is secondary. Missing/common-horizon failures remain failures.

| Arm | Primary correct confident | Primary wrong confident | Abstention | Failure | Secondary correct confident | Secondary wrong confident | Secondary abstention | Secondary failure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| R2_recover | 0 | 1 | 2 | 1 | 0 | 0 | 2 | 2 |
| B1x_exit | 1 | 2 | 0 | 1 | 1 | 2 | 0 | 1 |

| Attempt | Primary category | Frozen reason |
|---|---|---|
| R2_recover/s_bend_run_0000 | wrong_confident | wrong node |
| R2_recover/s_bend_run_0001 | failure | lost reentry |
| R2_recover/junction_run_0000 | abstention | no relocation in common horizon |
| R2_recover/junction_run_0001 | abstention | no relocation in common horizon |
| B1x_exit/s_bend_run_0000 | correct_confident | exact at declaration; complete no-reentry follow-up |
| B1x_exit/s_bend_run_0001 | failure | no relocation in common horizon |
| B1x_exit/junction_run_0000 | wrong_confident | wrong node |
| B1x_exit/junction_run_0001 | wrong_confident | wrong node |

The exact-node R2 exit on s_bend0001 re-entered lost within the required follow-up.
Its s_bend0000 exit was one node wrong and also re-entered. Both junction R2
attempts abstained without first-entry relocation within 36 decisions. B1x had
one primary correct first declaration, two wrong first declarations and one
common-horizon failure. These observations do not establish a mechanism effect
because two initial-image pairs failed the matching contract.

## Contacts and measured exposure

The gate window includes the first commanded interval through first terminal+24
capture frames (or all timeout frames). Extra recorded tail and eight settling
steps are reported separately. Contacts are contact-bearing episodes; physics
contact records are not distinct collision events. Motion time uses the frozen
per-frame displacement threshold 1e-4 m and therefore includes scan creep/noise.

| Arm | Contact-bearing episodes | Contact records | Path(m) | Exposure(s) | Contacts/m | Contacts/s | Translating(s) | Absolute rotation(rad) | Correct/wrong arrival stops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| R2_recover | 0 | 0 | 4.839081 | 114.333339 | 0.000000 | 0.000000 | 106.916672 | 37.836849 | 0/0 |
| B1x_exit | 1 | 5099 | 6.998034 | 102.750005 | 0.142897 | 0.009732 | 95.500005 | 9.618493 | 3/0 |

All recorded extra-tail exposure and contacts were zero, and no settling contacts
were recorded. R2 exposure was longer in time and shorter in path than B1x;
these contact counts cannot establish safer driving. The single B1x contact-bearing
episode is on a pair that failed image matching.

## External evidence identity

All evidence stays under `/home/favl/navfm-runtime-evidence/`; none is committed.
The two collection IDs are `v2-prospective_r2_a-R2_recover-20261010-01` and
`v2-prospective_r2_a-B1x_exit-20261010-01`. Each contains the four route IDs in the
table below. This lists all eight launched attempt identities and manifest hashes.

| Relative external evidence path | SHA256 |
|---|---|
| prospective-r2-v1-pilot-analysis-20261010-01.json | `bf0822fb866270d8fc64b5abb0868a5eed3912c2e313dbbad0dd34cd7748367c` |
| prospective-r2-v1-launch-ledger.jsonl | `ec08c8710c27b3fbd975da888782eb8ef66b61d309a123637f36442416f9e606` |
| v2-prospective_r2_a-R2_recover-20261010-01/frozen_routes.json | `176ad8e2e3a876eef0a190ecfa006a1b3f5071467e68b5f9d8dc8ea44069c59e` |
| v2-prospective_r2_a-R2_recover-20261010-01/s_bend_run_0000/runtime_manifest.json | `2d05970fcac74d1dd68b1408b5cdd1b7ee0e70151225b1aeb7025775919ba8af` |
| v2-prospective_r2_a-R2_recover-20261010-01/s_bend_run_0001/runtime_manifest.json | `9808e00699d78d4b330ef33f2f456764022bb0373ff0c31abc0646b7f6621244` |
| v2-prospective_r2_a-R2_recover-20261010-01/junction_run_0000/runtime_manifest.json | `59abf59c8181880cd84d48e70ed517d6b6a65749058b98ea45fae8b7ed2f5f25` |
| v2-prospective_r2_a-R2_recover-20261010-01/junction_run_0001/runtime_manifest.json | `cc5e6be4107743b52b9f43dcabe8f162d58adbf60dcb7c2fdfefb55c52606980` |
| v2-prospective_r2_a-B1x_exit-20261010-01/frozen_routes.json | `176ad8e2e3a876eef0a190ecfa006a1b3f5071467e68b5f9d8dc8ea44069c59e` |
| v2-prospective_r2_a-B1x_exit-20261010-01/s_bend_run_0000/runtime_manifest.json | `8f9d20119f486055f5303f18a1f2ae02beabbab89c274ebc6b0addd8f369b22d` |
| v2-prospective_r2_a-B1x_exit-20261010-01/s_bend_run_0001/runtime_manifest.json | `9f24de1257852af0cb3ee8ab6d5977ef66d31520fd92f6fe800944c415746e15` |
| v2-prospective_r2_a-B1x_exit-20261010-01/junction_run_0000/runtime_manifest.json | `3613ee8db494fc2b3d0f8108692963a76f31b50aa4b292ac84201167b6974889` |
| v2-prospective_r2_a-B1x_exit-20261010-01/junction_run_0001/runtime_manifest.json | `22b7b4eb9e3eb3f8e78410491223a149f11da26616f12a0ea4065cf64f950223` |

Robot, checkpoint, chain, goal and effective source digests remain pinned in the
external launch/runtime records and the frozen config. Both launches used one
identical robot digest; all per-attempt provenance checks passed.

## Validation and next decision

Repository ruff and mypy passed, and 40 focused recovery/legacy-analysis tests
passed before launch; 12 prospective boundary/negative tests also passed in the
independent read-only review. The baseline full verification failed exactly the
three documented environment-identity tests; those are failures, not passes.
Post-experiment `make verify` with the admitted `NAVFM_UPSTREAM` finished:
ruff and mypy pass; pytest fails exactly those same three named tests, with no
additional failures. The command exits 2 and remains failed. Its log is external
at `/tmp/navfm-prospective-final-verify-20261010.log`.

The cause of the initial-image discrepancy is UNKNOWN. Physical-state carryover and renderer/sensor history
are candidate explanations, not an established cause; no mechanism diagnostic
or illumination experiment ran. Next decision: separately review a small
initialization/history diagnostic and repair, with a fresh prospective protocol
and new uninspected starts if another recovery comparison is justified. Do not
reuse this failed pilot as confirmatory evidence or alter its frozen bounds.
Held-out layouts remain sealed, illumination paused, and no push or real robot
actuation occurred.
