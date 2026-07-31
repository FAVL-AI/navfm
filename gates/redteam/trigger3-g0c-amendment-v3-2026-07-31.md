# Red-team trigger 3 — revised G0.c amendment (draft v3)

**Question adjudicated**, verbatim from §9 of
`docs/reviews/2026-07-31-g0c-amendment-specification.md`:

> Does the revised amendment restore a genuinely falsifiable G0.c
> classification without reintroducing an invalid numerical comparison to
> `0.17398`, and are the checkpoint-arm and random-control repeatability
> criteria correctly separated by their sources of variance?

## VERDICT: Fixing — COMMIT PERMITTED

All eight of the specification's required conclusions hold under independent
verification. Both blocking findings of
`trigger3-g0c-amendment-v2-2026-07-31.md` are genuinely closed, not merely
claimed closed. Four new implementation defects are recorded below; none
reintroduces an invalid comparison, none breaks the variance separation, none
creates a rescue path, and every one is remediable **after** the commit without
re-amending the frozen text — because each rests on values the amendment
already binds.

Not *Rescuing*: no G0.c datum exists (verified below), the amendment *restores*
a falsifiable condition rather than retiring one, and the mandated sixth
mapping row is explicitly anti-rescue.

## Checklist

| # | Requirement | Result |
|---|---|---|
| 1 | corrects identifiable protocol defects | PASS |
| 2 | no released-checkpoint result informed the changes | PASS |
| 3 | seven Classification-2 conditions fully specified | PASS, with a recorded gap |
| 4 | Classification 3 reserved for evidential non-reconstructability | PASS |
| 5 | all partial outcomes have predeclared homes | PASS — sixth row verbatim-verified |
| 6 | 0.17398 change disclosed honestly | PASS — every claim re-verified against git |
| 7 | does not relax the frozen scene-grouping requirement | PASS — split re-derived from scratch |
| 8 | does not certify its own validity | PASS |

### Item 2 — verified, not accepted

`runs/`, `wandb/`, `logs/` do not exist. No `metrics.json` anywhere in the
tree. `git log --diff-filter=D` over all history returns no deleted result
file. The only committed numeric artefacts are the two `gates/M1/` files:
`metrics_randominit_control.json` (`checkpoint: null`, `random_init: true`) and
`metrics_finetuned_roundtrip.json` (`checkpoint_sha256` `89594f27…`, a
`/tmp/navfm-m1` epoch-1 fine-tune). Neither is `155fd72d…`. That digest occurs
only in `PREREGISTRATION.md`, `gates/G0/SHA256SUMS`, `gates/M2/README.md` and
the prior verdict — binding and documentation contexts, never a result.
`vint.pth` has not been scored.

### Item 6 — every corrected claim re-verified

| Claim | Verification |
|---|---|
| criterion entered at `92e3004` in `docs/EXPERIMENTS.md` | `git show 92e3004:docs/EXPERIMENTS.md` line 51: "total test loss within an order of magnitude of the checkpoint's recorded 0.17398" |
| `WORKFLOW.md` did not yet exist | `git ls-tree 92e3004 docs/` lists six files, no `WORKFLOW.md` |
| restated at `d4fc321` in `docs/WORKFLOW.md` | line 82: "a number in the neighbourhood … (same order of magnitude)" |
| both retired at `d6cef79` | `git show d6cef79` replaces both with "a classification under the pre-registered G0.c decision rule" |
| Amendment 1 never carried it | `git show 459c65c:PREREGISTRATION.md \| grep -c 17398` → **0** |

The `-S"0.17398"` log does not list `d6cef79` because that commit retired the
*criterion* while retaining the *number* as a provenance anchor — the
occurrence count is unchanged. The amendment's account is correct and the prior
verdict's method would have missed the retirement.

The amendment reproduces the specification's mandated blockquote **and** flags
its misattribution immediately beneath. That is the correct treatment: the
mandated text is preserved for the record, and the falsehood inside it is
corrected rather than propagated.

### Item 7 — split re-derived independently

From `gates/G0/splits/` alone, re-applying `^(no\d+|sim\d+)` and ranking scenes
by ascending `BLAKE2b(scene_key, digest_size=16)` per naming family to a 20 %
trajectory target:

- 3,696 trajectories, 53 scenes, **0 unparsed** — all as claimed;
- `scene_of.tsv` agrees with the independently derived key on all 3,696 rows;
- 760 held-out trajectories, 15 held-out scenes, **8 `no*` / 7 `sim*`**;
- **scenes appearing in both partitions: none**;
- **test-scene trajectories leaking into train: none** (whole-scene allocation);
- re-derived holdout set equals the committed one, **symmetric difference
  empty**; per-family shares 0.2048 and 0.2077.

`scene_key_v1` is genuinely group-level. The diff is **234 insertions, zero
deletions** — the frozen section is untouched.

## Answer to the §9 question

**Half one — yes.** Falsifiability is restored and the comparison is not
invalid. Seven conjunctive conditions; Condition 3's identity semantics defined
as exact equality of parsed numerical and lineage records with coefficient of
variation explicitly excluded; Layer C directional with ties failing and
descriptive cosines barred from rescuing a failed loss ordering; Condition 7
given an exact definition, `0.1 ≤ L / 0.17398 ≤ 10`, with `L` bound to
`strict/total_loss`. All five sanctioned constraints on the reinstatement are
honoured verbatim. Independently: a factor-of-100 band is a plausibility check
on scale, not a tolerance on an estimand — it is discriminating (a random-init
model at `strict/total_loss` ≈ 2.53 in `gates/M1/` would fail it) yet nowhere
near equivalence. Its failure now has a declared home whose anti-rescue clause
is explicit: the diagnostic run is immutable, any follow-up is a new run
identity with a lineage link.

**Half two — yes, correctly separated, and verified at source.** The coupling
the prior verdict identified is genuinely broken.
`third_party/visualnav-transformer/train/vint_train/data/vint_dataset.py` now
holds a dedicated `_NAVFM_SAMPLING_RNG = np.random.RandomState()` seeded only by
`navfm_seed_sampling()`; both `_sample_goal`'s `goal_offset` (line 216) and
`_sample_negative` (line 228) draw from it; **no global `np.random` call remains
in the sampler**. The patch is live in the clone (4 markers), its archived diff
digests to `e8a8793aaff1db39…` as bound, and `upstream_patch_identity_verified`
PASSes at runtime. The checkpoint arm is deterministic (`model_seed` 0,
`evaluation_seed` 0, twice); the controls are three initialisations
(`model_seed` 0/1/2) on **one** population, enforced at runtime by
`navfm.evalpairs.verify`, which compares realised pairs in draw order against
the pinned digest and aborts as gate-invalid on mismatch. Both causal-contract
invariants demanded by the remediation order exist as tests and pass
(`tests/test_rng_domains.py:64,76`). Full suite: 368 passed, upstream proof
intact.

## Prior-defect closure

| Prior finding | Status | Evidence |
|---|---|---|
| **Blocking 5** — no home for Condition-7-alone failure | **closed** | sixth row present and **verbatim-identical** to the remediation order's mandated text (programmatic comparison, exact match) |
| **Blocking 6** — two factual errors in the disclosure | **closed** | all five corrected claims re-verified against git; misattribution explicitly flagged |
| (1) overstated Layer A: `environment_identity_recorded` always-pass | **closed** | now a real digest comparison naming differing fields; four negative tests in `tests/test_freeze_audit_negatives.py:77,85,116,132`; audit correctly FAILed in a ROS-contaminated shell and PASSed under clean `PYTHONPATH` |
| (2) dataset digest never re-hashed | **closed** | `sha256sums_recorded` + `checkpoint_digest_reverified` |
| (3) `L` not bound to `strict/` | **closed** | Condition 7 binds `L` to `strict/total_loss` |
| (4) `model_seed` / NumPy goal-sampling coupling | **closed** | dedicated `RandomState`; see half two |
| (5) undeclared checkpoint-arm seeds | **closed** | `gates/G0/evaluation_declaration.json` pins `model_seed` 0, `evaluation_seed` 0, `repeats` 2 |
| (6) no commit-order disclosure | **NOT closed** | `d6cef79` calls the rule "pre-registered" and forward-references "the G0.c amendment in `PREREGISTRATION.md`" ~9 h before it existed; the amendment does not disclose this, though Amendment 1 set the in-repo precedent ("an audit trail that omits its own awkward orderings is not an audit trail"). No result preceded the amendment, so the epistemic harm is nil — but the standard is the repo's own |
| (7) split digest convention unstated | **partially** | still unstated in prose; but implemented consistently in generator (`scripts/make_go_stanford_split.py:248`) and audit (`scripts/protocol_freeze_audit.py:228`), and the check genuinely falsifies |
| (8) vacuous `no_pre_audit_evaluator_output` | **NOT closed** | `scripts/protocol_freeze_audit.py:419` still globs inside a `run_dir` that check 12 already requires absent; harmless duplicate, not a false pass |
| primary/secondary ordering not indexable | **partially** | row 3 plus the post-table sentence give incomplete satisfaction a home; the boundary between "primary fails" (row 4) and "secondary fails" (row 3) is still not stated |

## New defects

**N1 — `scripts/protocol_freeze_audit.py:352-358`. The pair-manifest check
cannot falsify.** Check 15 reads `sha256` and `pair_count` *out of the manifest
it is checking* and tests only truthiness (`ok = bool(digest) and bool(count)`).
It never compares an observed digest against a preregistered expected value.
Any file containing two non-empty keys passes. The remediation order's addendum
§1 required "a check **comparing expected against observed** manifest digest".
This is the same audit-integrity family as F-M2-1 / F-M2-4 — *the mechanism
purports to verify a property while being incapable of falsifying it* — and it
is the very defect just remediated for `environment_identity_recorded`.
Mitigated by `navfm.evalpairs.verify`, which does perform a real comparison at
runtime in every arm, so cross-arm population identity **is** enforced; what is
unenforced is that the manifest is the one the protocol intended.
**Fixable post-commit without amending:** recompute `manifest_digest` and check
`population_seed`, `dataset_digest`, `split_digest` against the already-bound
`gates/G0/evaluation_declaration.json` and split manifest.

**N2 — `PREREGISTRATION.md:245`, artefact-binding preamble, false for its own
row.** "Every artefact exists in this amendment's commit tree or is an
externally acquired binary pinned by a committed digest record" is untrue of
`gates/G0/evaluation_pairs.json`: absent from the worktree, untracked, and the
audit reports "no pinned pair manifest". The row is transparent ("produced by
the pre-execution pass") and the audit docstring reasons correctly that a
manifest committed in advance "would pin a population nobody had drawn" — but
the blanket sentence overstates, and the row's claim that the digest is
"verified by the freeze audit" is, per N1, not what the audit does. Self-
resolving at the execution boundary once the manifest is generated; the
overstatement is not.

**N3 — `src/navfm/eval/offline.py:277-293`. Exact-equality criterion without
declared determinism controls.** `seed_model_rng` seeds `random`, `numpy`,
`torch`, `torch.cuda` but never sets `torch.backends.cudnn.deterministic=True` /
`benchmark=False`, and neither the evaluator nor
`gates/G0/evaluation_declaration.json` declares any CUDA determinism control —
while Condition 3 demands *exact equality of raw implemented metric values*
across two runs. The sibling training path sets exactly these flags
(`src/navfm/train/finetune.py:133-137`). The declaration reasons carefully about
`num_workers=0` worker seeding, a far smaller risk. Fails safe: nondeterminism
produces a spurious Layer-B failure ("gate execution invalid"), never a false
Classification 2.

**N4 — the declaration is documentary, not enforced.** Commit `86636ce` is
titled "Predeclare the G0.c execution parameters, **and enforce them in the
evaluator**", but `src/navfm/eval/offline.py` never reads
`gates/G0/evaluation_declaration.json`; its only occurrence is an argparse help
string (line 379). Nothing checks that `--batch-size`, `--seed`,
`--population-seed`, `--model-seed`, `--num-workers` match the declared values,
and no Classification-2 condition requires realised execution parameters to
equal declared ones. Combined with N1: five arms run at an undeclared
`--population-seed`, against a manifest generated at that same seed, would agree
with each other, pass check 15, and produce a green gate. The deviation remains
*detectable* — run records carry `population_seed` and the declaration is
committed and bound — but it is caught by a reader, not by the gate.

## Residual weaknesses

- Conditions 2 and 5 are conjunctive but unindexed by the outcome table, which
  keys on Layer B × Layer C only. Their failures route to "invalid gate
  executions" through the Classification-3 exclusion list's trailing
  "respectively", which does not cleanly distribute over ten items and two
  categories. Inherited from the specification, which indexes its own table the
  same way.
- N4's converse: the amendment adds a declaration the specification never
  required, then wires no condition to it.
- Check 14 verifies four paths at the amendment commit; the binding table names
  fourteen rows. `evaluation_declaration.json` and `patch.diff` are bound but
  not commit-verified (both are tracked, so nothing is actually missing —
  Condition 1's "all pinned artefacts resolve" is only partially machine-checked).
- The canonical environment identity `4408691c…` is reachable only with a clean
  `PYTHONPATH`; a sourced ROS 2 Humble tree yields `6b4aafb6…`. Documented as
  F-M2-2, and the audit now names the differing fields — but the execution
  boundary should state the shell precondition explicitly.

## Disposition

Commit permitted. **Before the execution boundary is crossed**, N1 and N4 must
be closed, because §10 requires "all freeze-audit checks to pass" and check 15
as implemented cannot meaningfully pass. N3 should be closed in the same pass;
prior defects (6) and (8) and the primary/secondary boundary are
documentation-level and may follow.
