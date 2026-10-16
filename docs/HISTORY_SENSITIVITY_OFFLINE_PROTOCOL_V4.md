# Offline requested-goal history-sensitivity diagnostic: protocol v4 (FREEZE CANDIDATE)

**Status: candidate. Not frozen. Nothing has executed on a GPU, and GPU execution is not
approved.**
- Supersedes v3. v1, v2 and v3 are retained unchanged.
- The call population, manifest and arms are **unchanged from v3**.
- v4 changes three things:
  1. corrected wording on replay agreement and batch effects;
  2. a concrete runner, with its resource contract;
  3. the runner review's disposition (section at the end).
- Source commit: `1de79941552717e5740be75295567d7c9b6513bb`.

Hashes are listed in the freeze table at the end.

**Paths.** This repository copy is sanitised: paths are symbolic.
- `$NAVFM_EVIDENCE_ROOT` is the runtime-evidence root, holding the four `cmp-*-trunc-20261009-01`
  episodes.
- `$FREEZE` is the persistent external evidence directory
  `$NAVFM_EVIDENCE_ROOT/history-sensitivity-offline-v4-freeze-20261017/`. It holds the raw
  manifests (v1–v3), every earlier builder, protocol, runner and test version, the test logs and
  the review records, bound by sha256 in `gates/history_sensitivity_v4/FREEZE_RECORD.md`.
- `$ISAAC_PY` is the Isaac Sim 5.1 conda environment's interpreter, used without starting Isaac. Everything from v3 not restated here stands: question and claim boundary, definitions, population, arms, H2 matching and reference scales.

## Question (unchanged)
With query image, requested goal, reference rows, batch composition, row order and checkpoint
fixed, does substituting the five preceding history frames change the requested-goal score on
these recorded inputs? The result is descriptive, replay-regime and exposed-development only. It
is **not** an explanation of the stopping failures.

## Corrected wording

### Replay agreement (replaces v3 "Reproduction gap")
- **Gap per query:** gap = H0 repeat-0 replay score minus the logged deployed score. Each gap
  combines JPEG-versus-live input, device, kernel and library differences, and is not attributed
  to any one of them.
- **Reported for all 72 queries, without exception:**
  - every per-query gap;
  - the gap distribution overall and per episode (p10/p25/median/p75/p90, max |gap|);
  - **gate agreement**: whether the replay and logged scores fall on the same side of 7.745,
    with every disagreeing query listed by id.
- **Replay-agreement criterion (prospective, fixed before execution):** median |gap| ≤ 0.085.
  - *Basis.* 0.085 is the smallest per-episode p25 of consecutive in-region changes in the
    logged score (D j0). The criterion requires the replay to differ from the logged output, at
    the median, by less than a quarter of the smallest typical decision-to-decision movement in
    any episode. It is a declared convention, not a derived bound.
  - *Meaning.* Meeting it means only that the replay reproduces the logged outputs to that
    tolerance at the median.
  - **It does not establish equivalence to deployment.** A median can hide large individual
    discrepancies and gate-decision changes. The maximum |gap| and every gate disagreement are
    therefore reported next to the criterion, whatever its outcome.
  - Whatever the outcome, all results are labelled "replay regime". The call population is
    never changed in response to the gaps.

### Batch composition and row order (replaces v3 "batch and order cancel")
- Within every paired comparison, batch composition and row order are **held fixed**. This
  removes them as varying experimental factors.
- It does **not** guarantee that the numerical error of a forward pass is identical for
  different history inputs. Kernel selection and reduction order can interact with the data.
- **N_repeat** (the largest range over the 12 identical-input repeat triples) is the
  identical-input numerical reference reported against each Δ.
- **N_batch** (goal-only minus H0, 12 calls) and **N_order** (reversed reference rows minus H0,
  4 calls) are reported **separately**. They show how much the score moves with composition and
  order at a fixed history. They are not subtracted from Δ and are not used as gates.

## Runner (`history_runner.py`)

### Process structure
- `run` (the supervisor):
  - creates the attempt directory, refusing if it already exists, so one directory means one
    attempt;
  - writes `plan.json`;
  - starts exactly one worker in its own session, as `python -I`;
  - enforces the wall clock and the sampled process-memory guard;
  - always writes `supervisor_terminal.json`;
  - **never retries.**
- `_worker`: preflight, then the environment record, then model load, then the calls. It
  arms a hard self-limit (`SIGALRM`, default action: terminate) about 2 s before the supervisor's
  deadline, so it cannot outlive the wall clock even if the supervisor is gone.
- `admit`: accepts or refuses a finished attempt. It repairs and completes nothing.
- `analyse`: the pre-declared reporting, run only on an admitted attempt.

### Preflight (before importing torch; any failure means zero forwards and no model)
1. **Runner identity.** The worker's runner-file sha256 equals the one the supervisor recorded.
2. **Manifest.**
   - Its sha256 equals the pinned v3 digest (production).
   - Structure: `call_id` = position for 0…N−1, six observation frames, goal row last.
   - Per-arm counts are exactly the pinned ones (306 in total, production).
3. **Pairing invariants for every call, against its query's H0 repeat-0 call:**
   - all arms: the query image is identical;
   - H0, H1, H2, H3: the reference batch and goal row are identical;
   - H1: the query repeated ×6;
   - H2 and H3: history actually substituted;
   - goal-only and reversed-rows controls: exactly the derived batches.
4. **Re-derivation from the four episode records (the manifest is not trusted):**
   - logged score and window;
   - reference-row hashes: `topomap.nodes[window]`, plus `fixed_goal_sha256`;
   - every observation hash: `file_sha256` of the owning episode;
   - every arm's history frames, from the episode `inference` frames: H0 k−5…k−1; H3 k−10…k−6;
     H2 the donor's k−5…k−1; H1 the query ×6.
5. **Checkpoint.** All four episodes agree on its path, sha256 and config. The sha256 equals the
   pinned `c7686983…5d7c`, and the file's bytes hash to it.
6. **Inputs.** Every input file (by path, deduplicated) is read and hash-checked, then decoded
   from the same bytes. Each must decode to uint8 RGB, at least 16 px per side.
7. **Source staging.**
   - All 34 files in `influencing_file_digests` are copied from
     `source_snapshot/<digest>` into a package layout under `<attempt>/staged_src/` and made
     read-only.
   - Each file's hash is checked before and after copying.
   - The deployed batch-assembly statements must be present verbatim in the staged
     `RGBTopomapBaseline.step`.

### Source binding (what is bound, and what is not)
**Bound by hash:**
- every `navfm` and `vint_train` module the worker imports. Each one in `sys.modules` must
  resolve to a staged file whose hash equals the episode record, or the run aborts
  (`SOURCE_ORIGIN`). This is checked three times:
  1. after the imports, **before** model construction and checkpoint unpickling;
  2. after model load;
  3. after the last call.

  The installed editable `vint_train` finder comes after `sys.path` in the import order, and
  `-I` removes the script directory and the working directory from the path.
- the deployed preprocessing function `RGBBaseline.tensor`, called as is;
- the deployed `upstream.build_model`, called with the **recorded** `policy.config`;
- the deployed `models.loader.load_checkpoint` and `extract_state_dict`;
- the ViNT, attention and data-utility classes, which come from the staged upstream files.

**Replicated, with checks:**
- The batch assembly from `step()`. Two checks run in preflight:
  - the deployed statements must be present verbatim in the staged `step()`;
  - the runner's **own** model-facing statements (the `obs` and `goals` tensors, the
    `inference_mode` block calling the model, and the `d_all` conversion) must equal the
    deployed ones under AST comparison, with `self.` removed.
- The runner-only statements that bind manifest entries to inputs (`history`, `rows` and
  `images = rows`) are pinned literally.
- A CPU test drives the staged, deployed `RGBTopomapBaseline.step` on a recorded call with an
  **order-sensitive** substitute, which weights every channel and row by its index. It requires
  the result to be bit-identical to the runner's `d_all`.
  - The test also shows that reversing the history frames, or the reference rows, changes the
    output. Its equality therefore covers frame and row order, not only order-invariant content.
  - It does this for one recorded call, on CPU, with a substitute model. It does not exercise
    ViNT or CUDA.
- `upstream.ensure_upstream` is replaced by a function returning the staged path. The deployed
  version locates a full upstream clone, whose other files were never recorded.

**Not bound (recorded only):**
- torch, torchvision, PIL, numpy, `efficientnet_pytorch` (with per-file hashes, marked
  unbound), CUDA and cuDNN.
- The deployment recorded none of these, so equivalence remains INFERRED (see v3, "Execution
  environment").

### Checkpoint loading (restricted)
- The runner calls the deployed `load_checkpoint(path, trust_checkpoint=False,
  expected_sha256=…)`.
- With `trust_checkpoint=False`, that function calls `torch.load(..., weights_only=True)` and
  **raises instead of falling back** to unrestricted unpickling.
- Safe deserialisation is therefore established by the restricted loader actually used, not by
  inspecting the file.
- A static scan of the pickle (its opcodes, only `OrderedDict`, tensor storages and
  `_rebuild_tensor_v2`) only predicts that the restricted load will succeed. If that prediction
  is wrong, the run aborts. It does not fall back.
- Test `test_restricted_checkpoint_loading_refuses_pickled_objects` shows that the staged
  loader, called this way, refuses a checkpoint containing a pickled object.

### Forward accounting
- `ForwardBudget` counts listed calls, and also counts actual module forwards through a
  forward pre-hook. The hook is registered immediately after model construction, before the
  weights load.
- A forward during load, or any forward not matching a listed call, aborts the run
  (`UNLISTED_FORWARD`).
- The cap is the manifest's call count (306), and can never exceed 320.
- **Acceptance requires exactly 306 results and exactly 306 counted forwards, from the pinned
  manifest.** The 320 ceiling bounds a defect; it does not allow exploratory, repeated or warm-up
  calls.
- Module construction is not hooked. It runs only the hash-bound constructors, which perform no
  forward pass.

### Resource contract
| Resource | What is measured | Enforcement | Guarantee |
|---|---|---|---|
| Forwards | Listed calls, and module forwards via the pre-hook | Abort before the 307th forward; acceptance needs exactly 306 | Hard, within the hooked module |
| Wall clock | 600 s from supervisor start, covering worker start, preflight, environment record, model load and all forwards | Three layers: (1) the worker checks its deadline between calls; (2) the worker's `SIGALRM` hard self-limit fires about 2 s before the supervisor's deadline; (3) the supervisor sends SIGKILL to the worker's session at the deadline. The supervisor loop blocks only on 0.1 s sleeps; sampling runs on a separate thread | Hard for execution. Cleanup and finalisation after execution ends are recorded separately (`deadline_s`, `execution_end_s`, `finalised_s`) |
| GPU memory, allocator | Memory reserved and allocated **through PyTorch's caching allocator**, from model load onward (peaks never reset) | `torch.cuda.set_per_process_memory_fraction(4 GiB / device total)`; the allocator raises out-of-memory beyond it. Peaks are also checked after load and after every call | Hard, **only for allocations governed by the PyTorch allocator** |
| GPU memory, process | Per-process `used_memory` from `nvidia-smi`, which includes the CUDA context and allocations outside the PyTorch allocator | A sampling thread queries about every 1 s, and the supervisor kills the worker above 4096 MiB. Only a sample that lists the worker's PID counts as an observation. A hung, failed or unparsable sample counts as failed, never as 0 MiB. Production admission needs at least one observation | **Sampled monitoring only.** A brief excursion between samples can be missed. This is not a hard ceiling |
| Retries | — | None; an existing attempt directory is refused | Hard |

The process figure also covers library-internal allocations and the CUDA context. Whether any
particular library workspace goes through the PyTorch allocator is not asserted.

### Terminal records, natural completion and forced termination
- Every record is written to a temporary file, synced, atomically renamed, and then the
  directory is synced.
- **Execution end** is the moment the supervisor's loop stops. That happens either because the
  worker exited by itself (**natural exit**), or because the supervisor ended it (**forced
  termination**: `TIMEOUT` at the supervisor deadline, `MEMORY_CAP`, `INTERRUPTED` on SIGTERM,
  SIGINT or SIGHUP, or `SUPERVISOR_ERROR` on any supervisor exception).
- `execution_end_s` is recorded in every case, followed by **cleanup and finalisation**:
  1. stop the sampler;
  2. send SIGKILL to the worker's session (created by the supervisor, so owned by it);
  3. reap the direct child;
  4. write `supervisor_terminal.json` with `natural_exit` and `forced_termination`.
- **The cleanup kill is not part of a natural completion.** After a natural exit the session is
  normally empty, so the kill reaches nothing (`session_members_killed_at_cleanup: false`). If
  it does reach a surviving member, that is recorded as `true` and the attempt is inadmissible.
- A worker that ends through its own `SIGALRM` self-limit is classified `TIMEOUT`. That is a
  natural exit by signal, but it is never success.
- A worker that wrote COMPLETE but then exited non-zero is `WORKER_FAILED`.
- **Timeout, memory-cap, interruption and supervisor-error outcomes are never admitted as
  successful production execution.** Admission requires COMPLETE, a natural exit, worker exit
  code 0, and no survivors at cleanup.
- If the supervisor itself is SIGKILLed, no supervisor record is written and `admit` refuses the
  attempt. The worker's self-limit still ends it.
- Results go to `results.jsonl`, opened exclusively, with fsync after every line. Partial
  results are kept as evidence and are never admitted.

### Admission (`admit`) refuses unless all of these hold
- The supervisor and worker statuses are both COMPLETE, and the worker exited with 0.
- Mode and backend agree across the plan, both terminal records and the model-load record.
- Production only:
  - the backend is ViNT on CUDA, as the environment and model-load records show;
  - the manifest digest is the pinned one;
  - the manifest has exactly 306 calls.
- The manifest is unchanged since the attempt.
- The results file matches the worker's recorded digest.
- There are exactly N results, in `call_id` order, and each has:
  - matching arm, query and repeat;
  - matching observation and batch hashes;
  - one finite score per batch row;
  - a score equal to the goal-row value.
- The forward counters equal N.
- The preflight, environment and model-load records all exist.
- The supervisor reports a natural exit with no session survivors.
- **Production only, in addition:**
  - the plan's pins equal the runner's, and the attempt ran this exact runner file;
  - the preflight checkpoint digest is the pinned one;
  - the environment records a CUDA device name;
  - `navfm.models.loader` and `vint_train.models.vint.vint` were loaded from staged source;
  - every result carries CUDA allocator statistics;
  - the memory guard observed the worker at least once.
- TEST attempts are refused unless `--accept-test` is passed.

**Admission checks consistency, not authenticity.** Anyone able to rewrite the attempt
directory can rewrite its records consistently. Authenticity rests on recording the sha256 of
every attempt file (`record_hashes`, also embedded in `analysis.json`) out of band, immediately
after the run. The test suite shows that relabelling a CPU test attempt as production, by editing
five of its records, is refused.

## Execution command (NOT approved; for the freeze record only)
Run from the repository root at the freeze commit:
```
R=scripts/history_sensitivity/history_runner.py   # sha256 add0bd46662dde2d1da6ca784f88c48e5ea5b2186ca01d46e8996582b5a0e022
M=$FREEZE/history_call_manifest_v3.json            # sha256 391c2f02a944cd46f3683f53e4979041b34bad9060f035cf779fd283781ccfa7
A=$NAVFM_EVIDENCE_ROOT/history-sensitivity-offline-v4-attempt-01
RUNNER_SHA=add0bd46662dde2d1da6ca784f88c48e5ea5b2186ca01d46e8996582b5a0e022
sha256sum $R $M                                      # must equal the two digests above
df -B1 $NAVFM_EVIDENCE_ROOT                          # fresh free-space check before launch
$ISAAC_PY $R run --manifest $M \
  --manifest-sha256 391c2f02a944cd46f3683f53e4979041b34bad9060f035cf779fd283781ccfa7 \
  --attempt-dir $A --evidence-root $NAVFM_EVIDENCE_ROOT
$ISAAC_PY $R hashes --attempt-dir $A --out $A.hashes.json   # immediately; record the printed digest out of band
$ISAAC_PY $R admit --attempt-dir $A --expected-runner-sha256 $RUNNER_SHA
$ISAAC_PY $R analyse --attempt-dir $A --out $A.analysis.json --expected-runner-sha256 $RUNNER_SHA
```
- The attempt directory name is consumed by the first launch, whatever its outcome.
- `hashes` refuses an output path inside the attempt directory.
- Production `admit` and `analyse` refuse an attempt if no expected runner digest is given, or if
  the attempt's runner digest differs from it.

## Reporting addition
- Threshold margins are reported both ways:
  - against the H0 replay score, which is what a flip is judged against;
  - against the logged score, the v3 definition.

## Disk requirement
| Item | Size |
|---|---|
| Production attempt: staged source, about 0.27 MB; results, about 0.4 MB; records under 0.1 MB | about 1 MB |
| Test suite: attempt directories, altered manifests, copies of complete attempts; removed by the marker-checked fixture at the end of the session | about 16 MB peak (measured) |
| Temporary files | none beyond the above; the checkpoint is only read |

The **50 GB gate is Frank's standing workstation reserve** (in force since 2026-07-11, after a
disk-exhaustion incident during recording). It does not come from this work's outputs, which
need well under 0.1 GB.

## Remaining limitations
- Two routes, one checkpoint, exposed development episodes. Replay regime only.
- The library and backend environment is not bindable to deployment. Replay agreement is a
  median criterion, reported with the full gap distribution and gate agreement.
- Reference scales are circular yardsticks. H3 mixes content with frame spacing; H2 mixes
  near-duplicate history with variant behaviour.
- Within-process repeats cannot bound noise across processes or kernel selections.
- The allocator cap and the CUDA-side behaviour of timeout and memory handling **cannot be
  exercised by the CPU tests**. They are verified by reading the code only, until the approved
  run.
- The process-memory guard is sampled, not a ceiling. A sampler stuck in uninterruptible sleep is
  counted as failed and not re-launched while it is alive. It cannot affect the deadline.
- If `write_json` fails inside the supervisor's cleanup (for example, a full disk), no supervisor
  record is written. The worker has already been killed, and `admit` refuses the attempt.
- If the supervisor is SIGKILLed, there is no terminal record; the attempt is refused but not
  self-described.

## Review disposition (runner review, three rounds)
The full review record is in `gates/redteam/trigger4-20261017-history-sensitivity-runner.md`.

- **Round 1** reviewed runner `0768c1ed…`. It found **0 blocking, 6 should-fix and 5 minor**
  issues, and confirmed:
  - the restricted checkpoint loading;
  - the allocator-only memory claim;
  - child reaping;
  - closure of the staged source;
  - the analysis computations;
  - F1–F7 and F9.
- **Round 2** was a closure check of runner `e569af13…`. It found 8 closed, 4 partial, none open
  and 1 new minor issue.
- **Round 3** checked only the final fixes, against runner `add0bd46…`. Every code item was
  closed and the lint rewrites showed no behaviour change. One documentation defect (D1) was
  found and is fixed in this copy: the command block pinned a superseded runner digest and lacked
  `--evidence-root`.

| ID | Severity | Disposition |
|---|---|---|
| A2/A18 | minor | Fixed. Module-origin check before construction and unpickling, after load, and after the calls |
| A4 | should-fix | Fixed. Supervisor wrapped in try/except/finally; bad samples count as failed; worker always killed |
| A5 | should-fix | Fixed. Sampling on its own thread; worker `SIGALRM` self-limit; no stacked sampler while one is alive |
| A6 | should-fix | Fixed. Only samples listing the worker's PID count; production needs at least one |
| A8 | minor | Fixed. `execution_end_s` always set; natural vs forced exit recorded; COMPLETE-then-nonzero is a failure |
| A10 | should-fix | Fixed. Production consistency checks; `--expected-runner-sha256`; `hashes` step right after `run`; "consistency, not authenticity" stated |
| A12 | minor | Fixed. Origins re-checked after the last call |
| A13 | should-fix | Fixed. Runner assembly AST-bound to the deployed one; input-binding assignments pinned; order-sensitive equivalence test with failure cases |
| A16 | minor | Fixed. Both margin definitions reported |
| A19 | should-fix | Fixed. AST test of the restricted-load call site; synthetic analysis test covering per-episode and per-route summaries |
| A20 | minor | Fixed. Marker-checked cleanup of test outputs |
| N1 | minor | Fixed. Corrupt results line is refused, not raised |
| E1 | change | Evidence root is a required argument, recorded in the plan; no default anywhere. Round 3: closed |
| L1–L5 | change | Lint rewrites for the repository's ruff configuration. Round 3: no behaviour change |
| D1 | should-fix (doc) | Fixed in this copy |
| A13 residual | minor, accepted | The binding check covers assignments only. An in-place reorder written as a bare expression (e.g. `history.reverse()`) would not be caught by it. The current runner contains no such statement (round 3), and the order-sensitive equivalence test would expose any reorder of the arrays the model receives on call 0 |
| X1 | disclosure | The substitutes file round 2 saw (`17c5749a…`) was not preserved before `OrderSensitive` was appended. The current file adds one class and changes no existing class; that is confirmed only by the round-3 reading, not by a diff |

**Test-run history:**
| Run | Result | Notes |
|---|---|---|
| 1 | 37 passed, 2 failed | `admit` raised on an unreadable manifest (fixed); one test-fixture error (fixed) |
| 2 | 39 passed | |
| 3 | 41 passed | |
| 4 | 42 PASSED lines, exit 0 | Final sources, run from the repository; pytest's count line was suppressed by `-qq` |
| 5 | **42 tests, 0 failures, 0 errors, 0 skipped** (JUnit XML), 218.8 s | Final sources; the authoritative record |

## Freeze table (candidate; not frozen)
| File | sha256 |
|---|---|
| `scripts/history_sensitivity/history_runner.py` | `add0bd46662dde2d1da6ca784f88c48e5ea5b2186ca01d46e8996582b5a0e022` |
| `scripts/history_sensitivity/test_history_runner.py` | `ff0de11bf82d6ceb2ca5bb8909cabe86d894ee825aba6d89b94cadb008bbbfa6` |
| `scripts/history_sensitivity/history_substitutes.py` (test only) | `fa56cdd57aab5b47851670703ce19e412211a817f5265de51b5703f52d09aa21` |
| `gates/history_sensitivity_v4/build_history_manifest_v3.py` (verbatim) | `a4fdb50df200e4cd5a865e4058c42ab9bd16c025fe44e865e926b4814ad78317` |
| `$FREEZE/history_call_manifest_v3.json` (external) | `391c2f02a944cd46f3683f53e4979041b34bad9060f035cf779fd283781ccfa7` |

**Test command (run 5),** run from `scripts/history_sensitivity/`:

```
CUDA_VISIBLE_DEVICES= NAVFM_EVIDENCE_ROOT=$NAVFM_EVIDENCE_ROOT \
  HSR_MANIFEST=$FREEZE/history_call_manifest_v3.json HSR_TEST_OUTPUT_ROOT=<scratch dir> \
  $ISAAC_PY -B -m pytest -p no:cacheprovider -rA --junitxml=<out>.xml test_history_runner.py
```

Run 5's environment: Python 3.11.15, torch 2.7.0+cu128 (CUDA hidden), torchvision 0.22.0+cu128,
PIL 11.3.0, numpy 1.26.0, pytest 9.0.3. Both the log and the JUnit XML are bound by hash in the
freeze record.

**Untested by design:** the ViNT/CUDA path, the allocator cap and CUDA-side timing. They are
verified by reading the code only.

The committed builder still contains its original absolute evidence path. It is kept verbatim
because its digest is what the manifest record binds.
