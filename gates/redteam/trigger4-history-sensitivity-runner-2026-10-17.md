# Trigger 4: offline history-sensitivity protocol and runner, 2026-10-16/17

Protocol reviews (v1, v2) and runner reviews (rounds 1–3). Each was an independent read-only
subagent instructed to refute, defaulting to "refuted" when uncertain. None executed tests, the
runner, torch or the GPU. Full reports are in
`$NAVFM_EVIDENCE_ROOT/history-sensitivity-offline-v4-freeze-20261017/reviews/`, bound by hash
in `gates/history_sensitivity_v4/FREEZE_RECORD.md`.

## Protocol review 1 (v1): DO-NOT-FREEZE
- **Blocking.** F1 H2 was a near-duplicate history mislabelled as an intervention; F2 had no
  practical scale.
- **Should-fix.**
  - F3: image pose taken from `captures[f]` instead of `captures[f-1]`.
  - F4: the matching rule took the nearest candidate, then gated it.
  - F5: unit of analysis.
  - F6: determinism.
  - F7: controls.
  - F9: variant confound.
- **Minor.** F8, F10, F11.
- All addressed in v2; see the v2 protocol disposition.

## Protocol review 2 (v2): DO-NOT-FREEZE
- **Blocking.**
  - F1: the declared scale was not recorded in any artefact.
  - F2: the 1.18 scale was circular as a gate.
  - F6: the replay environment is not bindable.
- **v3 response.**
  - The scale is now an exploratory reference: per episode, computed in the builder, never a gate.
  - F6 was partly rebutted. Model source is hash-bound through `influencing_file_digests` and
    `source_snapshot`. The library environment is declared INFERRED.
- **Other fixes.**
  - F3: H3 is a temporal splice with a 3 s gap.
  - F4: pair rule 16 mutual / 18 one-direction.
  - F5: N_repeat is the only identical-input reference.
  - F7: two-route caveat.
  - F9: 1/12 s.

## Runner round 1 (runner 0768c1ed…): 0 blocking, 6 should-fix, 5 minor
**Confirmed:**
- restricted checkpoint loading (`trust_checkpoint=False`, so no unrestricted fallback);
- the memory claim limited to the PyTorch allocator;
- reaping;
- staged-source closure;
- image path and frame offsets;
- analysis computations;
- v3 F1–F7 and F9.

**Found and fixed:**
- A2/A18: origin check after unpickling → now before construction and loading.
- A4: a sampler parse error could kill the supervisor → try/finally, failed samples counted.
- A5: an inline sampler could block the deadline → sampling thread, worker `SIGALRM`.
- A6: a guard that never saw the PID still passed → presence required.
- A8: record wording.
- A10: admission could be fooled by relabelling → production consistency checks.
- A12: late imports → origins re-checked after the calls.
- A13: the runner's assembly was not bound → AST-bound.
- A16: margin definition → both margins reported.
- A19: test gaps.
- A20: test cleanup.

## Runner round 2 (runner e569af13…, closure check): 8 closed, 4 partial, 0 open, 1 new minor
**Partial items, then fixed:**
- A10b: no post-run hash step → `hashes` subcommand and `--expected-runner-sha256`.
- A13: the equivalence test could not see order → order-sensitive substitute and pinned input
  binding.
- A19: routes untested.
- N1: a corrupt line made `admit` raise.
- A5 residual: stacked samplers.

## Runner round 3 (runner add0bd46…, final fixes only): code CLOSED; 1 doc defect
- **CLOSED:**
  - A13, A10b, A19, N1 and the A5 residual;
  - E1: evidence root is a required argument with no default;
  - L1–L5: the lint rewrites (merged conditions, read helpers, `contextlib.suppress`,
    unpacking, import order) change no behaviour.
- **D1** (doc, should-fix): the command block pinned the superseded digest `a3801351…` and
  lacked `--evidence-root`. Fixed in `docs/HISTORY_SENSITIVITY_OFFLINE_PROTOCOL_V4.md`.
- **Accepted residual (minor).** The input-binding check covers assignments only, so an
  in-place reorder written as a bare expression is not detected by it. None exists.
- **X1 (disclosure).** The round-2 substitutes file was not preserved, so it could not be
  diffed. Round 3 read the current file.

## Tests on the final sources
- Run 5, against runner `add0bd46…`, tests `ff0de11b…`, substitutes `fa56cdd5…`.
- **42 tests, 0 failures, 0 errors, 0 skipped** (JUnit XML), with CUDA hidden.
- Earlier runs:
  - run 1: 37 passed and 2 failed (an `admit` defect and a fixture error, both fixed);
  - runs 2–4: 39, 41 and 42 passed.

## Verdict
**FREEZE CANDIDATE.**
- No open blocking or should-fix finding.
- The ViNT/CUDA path, the allocator cap and CUDA-side timing are untested by design. They are
  verified by reading the code only.
- GPU execution is not approved by this record.
