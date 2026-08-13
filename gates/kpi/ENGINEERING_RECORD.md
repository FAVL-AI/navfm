# NavFM engineering record — issues, decisions, mitigations, iterations, KPIs

Session of 2026-08-13. Every row traces to a commit or an evidence file.

---

## 1. The surpassment claim, stated precisely

**Claimed:** navfm's reproduction evidence for GNM, ViNT and NoMaD is *strictly
stronger than the evidence that exists for the released artefacts themselves*.

**Not claimed:** that navfm navigates better than those models. The D5
eligibility audit ruled that ineligible and no table was produced — only ViNT has
an evaluation metric, so a three-model performance comparison would have to
invent two of its three rows. A second reason applies specifically to our data:
the pilots are ViNT-driven, and motion the model under test produced itself cannot
be evidence of beating that model.

**8 of 10 reproducibility KPIs surpassed.**

| KPI | Released-artefact evidence | navfm | |
|---|---|---|---|
| Strict checkpoint load | `strict=False` at `02_verify_checkpoints.py:168` and `15_reproduction_gate.py:319` — counts *reported*, the call cannot fail | `strict=True` × 3, PyTorch raises on mismatch, none raised | **✓** |
| Models with a deterministic-inference record | **2 of 3.** `vint_gate.json` exists in **no revision of 236**; the gate binds `--model` to choices excluding ViNT | **3 of 3** | **✓** |
| Inference input population | **synthetic seeded frames** — `np.random.default_rng(SEED+i)`, 480×640×3; the script's own docstring: *"Synthetic, and not benchmark data"* | frozen GO Stanford, **41,872 pairs**, manifest `57a7fbbeba91b92a`, in draw order | **✓** |
| Repeats evidencing repeatability | GNM **1** (none), NoMaD 3, ViNT **none** | **2 per model**, on the frozen population | **✓** |
| Declared tolerance before first inference | none | `allclose(rtol=1e-5, atol=1e-6)`, frozen in the committed protocol; the harness *refuses to run* without it | **✓** |
| Max abs / rel difference archived | not recorded | **0.0 / 0.0** all three; bitwise identical, reported, never adopted as threshold | **✓** |
| Adversarial adjudication | none | **8 rounds, 22 defects**; round 8 a four-lens panel, two skeptics per claim | **✓** |
| Per-row provenance | tags assert "independently evidenced"; ViNT R7 had no record behind it | 12-row crosswalk with repository, commit, tag, path, tracked status, digests, dataset identity, claim boundary, missing delta | **✓** |
| Exact paper reproduction | not claimable — upstream used unreleased datasets | not claimable, **declared so in advance** | — |
| Navigation performance | published numbers are real-robot trials | **NOT ELIGIBLE** | — |

The novelty is not any single row. It is that all three released models now have
a strict-load *and* deterministic-inference *and* frozen-benchmark-population
record, with a declared tolerance, under one protocol — which none of them had
before, and ViNT had none of.

---

## 2. Silent failures caught

Each would have produced convincing, worthless evidence. None is visible in a
well-formed output file.

| # | Failure | What it would have produced | Why nothing downstream catches it | How it was caught | Fix |
|---|---|---|---|---|---|
| 1 | Wheel joints imported with **zero stiffness and zero damping** | 40 perfectly-formed frames — right dtypes, contiguous images, aligned poses, unwrapped yaw — of a robot that moved **0.001 m** while its log said 0.45 m/s | The file passes every Option 1 check and loads in all three models | Comparing **commanded velocity against achieved displacement** | `kp=0, kd=1e4` on wheel DOFs; ratio now in every record |
| 2 | PyTorch CUDA context beside Isaac's RTX renderer | Nothing — SIGSEGV at first inference, reproducibly, identically in both pilots | n/a, hard crash | Identical failure point across runs | ViNT on CPU |
| 3 | **Missing waypoint un-normalisation** | Every command ~8× too fast; plausible trajectory, wrong everywhere | **The 0.45 m/s saturation clamp returns the SAME value for correct and wrong** — the safety limiter erases the evidence | A named, tested conversion function | `unnormalise_waypoint`, 22 tests |
| 4 | Camera parented to a prim *named* `top_arm_mount` at chassis height | Every trajectory from the wrong visual domain | The old check asked whether a camera was *mounted*, not *where* | Height assertion, measured from the transform | Resolve by traversal; derive from measured height |
| 5 | Placeholder USD passing an earlier acceptance run | A "digital twin" with 0 joints, 0 colliders, 0 rigid bodies | The importer reported `already_exists` on a file it had merely *found* | Counting physics content instead of trusting the report | URDF re-import; census in the record |
| 6 | Stale pilots reported as fresh | Old chassis-camera data presented as the corrected viewpoint | Numbers were identical to 3 d.p. — because they were the same files | `camera_prim` field read `base_link`; mtimes 30 min old | Verify the camera contract *first*, before any other field |
| 7 | Wheel radius **0.048 m**, X3-derived | 20% error in every commanded velocity and every odometry displacement, landing in `position` | Corrupts every trajectory *identically*, so no consistency check fires | Cross-repo audit + the URDF's own comment *"same as X3"* | 0.040 m, `PROVISIONAL_SIMULATION_VALUE`, in the ledger |

---

## 3. Protocol defects — 8 adjudication rounds, 22 defects

| Round | Verdict | Committable | Defects | The one that mattered |
|---|---|---|---|---|
| 1 | Fixing | FALSE | 4 | A false traceability claim; filed as `F-A5-1` |
| 2 | Fixing | FALSE | 6 | **GNM/NoMaD R7 ran on synthetic input, not GO Stanford** — an execution step permitted NoMaD's rung to close with zero work |
| 3 | Fixing | FALSE | 3 | **"G0.c is now closed" was FALSE** — the sole basis for retiring the checkpoint-loading prohibition |
| 4 | Fixing | FALSE | 3 | Preamble forbade training while three steps authorised it, against a criterion never defined → **R8 withdrawn** |
| 5 | Fixing | FALSE | 2 | GNM's official scale **inferred from ViNT by symmetry** (400/30, not 256/100) |
| 6 | Fixing | FALSE | 3 | Tolerance scoped to two of three models while a third was mandated → **unexecutable instruction** |
| 7 | Fixing | FALSE | 1 | The same provenance claim, **ten lines above** the sentence corrected in round 6 |
| 8 | **Fixing** | **TRUE** | **0** | Four-lens panel, two skeptics per claim; zero survived |

**Iteration signature: 4 → 6 → 3 → 3 → 2 → 3 → 1 → 0.** Rounds 3–6 were each
decided by a *correction that did not propagate* — prose fixed, summary left
stale. That is the finding, not the individual defects.

---

## 4. Decisions and their reasons

| Decision | Alternative rejected | Why |
|---|---|---|
| Withdraw R8 from Amendment 5 | Amend the preamble to permit training | Closing R8 needs official-scale training (400/30 GNM, 256/100 ViNT/NoMaD) against a criterion the amendment never defined |
| Wheel radius 0.040 m as provisional | Block on calipers | Open-by-default: documented, plausible, sourced, not claimed as measured, in the ledger |
| Represent the top-arm mast now | Collect first, correct later | **Empirically vindicated** — same start/goal/seed/policy/physics, camera the only change, `pilot_0002` yaw went **+8.8° → +37.9°** |
| Own mecanum IK, not `HolonomicController` | Use the shipped controller | It writes `self.max_wheel_speed = (max_wheel_speed,)` — a 1-tuple compared against a float |
| ViNT on CPU inside Isaac | GPU | CUDA context beside RTX renderer segfaults reproducibly |
| Stage `einops` outside the environment | `pip install` | Would change `pip_freeze_digest` → environment identity → **break the G0.c freeze audit before G0.c ran** |
| Keep low-camera pilots as a different camera-domain experiment | Delete them | They are evidence of the domain effect, not merely superseded data |
| Panel owns no state | UI holds state | A UI that owns state cannot be tested |

---

## 5. KPIs

| KPI | Value |
|---|---|
| Tests | **437 → 454 → 476 → 501** |
| Lint / types | ruff + mypy clean, **33 source files** |
| Commits pushed | 16, all Frank Asante Van Laarhoven, zero AI trailers |
| Adjudication rounds / defects | 8 / 22 |
| R6 strict load | **3/3** — 638, 799, 645 tensors; 0 missing, 0 unexpected |
| R7 repeatability | **3/3** — max abs 0.0, max rel 0.0, bitwise |
| G0.c | **Classification 2**, 7/7 conjunctive conditions, `strict/total_loss` 0.18026807678384063 |
| G0.c anchor ratio | 1.036143 — inside [0.1, 10], *not* a reproduction tolerance |
| Behavioural ordering | 0.180 vs controls 2.566 / 2.891 / 2.772 — beaten individually |
| Frozen population | 41,872 pairs, digest `57a7fbbeba91b92a` |
| Environment identity | `4408691cfeb89860…`, unchanged across the session |
| Digital twin | 11 rigid bodies, 10 joints, 8 colliders, 1 articulation root |
| Camera | **0.2800 m** ground, 0.2400 m above `base_link`, measured |
| Pilots | 2 × 40 frames, 4.867 m and 4.968 m |
| Commanded → achieved | 0.450 → 0.491 / 0.505 m/s (ratios 1.09 / 1.12) |
| Option 1 | 3/3 validators |
| Three-model loaders | **3/3** — GNM 30, ViNT 30, NoMaD 29 samples |

---

## 6. Open, and whose call it is

**Yours and Rui's:** the four E2 design decisions — plus **a fifth the tracking
file does not record**: the gate condition requires the four *"together with the
estimator's type-I error rate measured on simulated null data and its
tolerance"*, and `gates/g2_decisions.json` holds four entries. Fixing four and
calling it done would step over the fifth silently.

Also yours: whether ViNT-driven pilots may ever be admitted as training data.
Every trajectory carries `admission_status: NOT_ADMITTED` until you say
otherwise.

**Engineering:** GNM and NoMaD offline evaluation (the only route to a legitimate
performance comparison — NoMaD additionally needs an evaluation path that does
not exist); G1 physical measurements; the panel's windowed demo.

**Not blocking anything:** `gh` cannot see the repo because `FAVL-AI` is a
separate account, not an organisation. SSH pushes fine.
