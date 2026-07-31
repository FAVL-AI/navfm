# Pre-registration

This file freezes the experimental protocol *before any result exists*. Its
git commit timestamp is part of the paper's evidence: hypotheses recorded
here predate every number in `runs/`. Amendments are permitted only as new
dated sections below — never edits to this one.

## Frozen protocol (v1)

- **Hypotheses H1–H5** as stated in `docs/EXPERIMENTS.md`, verbatim at the
  commit introducing this file.
- **Primary endpoint:** the E2 interaction term (demonstration × execution
  kinematics) on closed-loop success in held-out simulated scenes, with 95 %
  percentile-bootstrap CI.
- **Pre-registered E2 ordering prediction:**
  (nonholo-demo, holo-exec) > (nonholo, diff) > (holo, holo) > (holo, diff).
- **Cells:** ≥ 30 closed-loop episodes per cell; identical scenario seeds
  across arms within an experiment; 3 training seeds per cell; mean ± CI over
  seeds.
- **Splits:** scene-grouped holdout only. No trajectory-level splits appear
  in any reported table.
- **Offline metrics:** batch size 400, reference (`strict`) reduction, plus
  ADE/FDE converted to metres. Both reduction variants archived.
- **Manipulation check:** E2 proceeds only if the two collected corpora
  separate on lateral-energy ratio at collection gate G2.d; otherwise
  collection parameters are revised and re-collected *before* any training,
  and the revision is logged here as an amendment.
- **Reporting commitment:** all pre-registered cells are reported regardless
  of sign, including a negative E6.
- **Exclusion rules:** episodes excluded only by the collector's automated
  guards (collision/stall/short/degenerate) or by hardware fault noted in the
  trial log at the time of the trial. No post-hoc exclusions.

## Amendments

*(none)*
