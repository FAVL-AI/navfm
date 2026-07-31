Source: external methodological review
Date received: 2026-07-31
Scope: operative specification for revision and red-team adjudication of the G0.c amendment
Status: reviewed and dispositioned

---

# External Methodological Review — G0.c Amendment Specification

**Source:** External methodological review
**Purpose:** Operative specification for revision and red-team adjudication of the G0.c amendment
**Status:** Pre-execution review; no released checkpoint has been evaluated

## 1. Historical disclosure concerning `0.17398`

The amendment must include the following disclosure without changing its substantive meaning:

> Amendment 1 preregistered an order-of-magnitude relationship to the checkpoint-associated value `avg_total_test_loss = 0.17398`. Before any released checkpoint was evaluated, that criterion was retired because the reference value was computed over an unrecoverable five-dataset mixture, whereas G0.c evaluates a reconstructed GO Stanford scene-grouped holdout. No new empirical result motivated the retirement. The change is disclosed because it removed a previously committed falsifiable condition, even though that condition compared non-equivalent estimands.

The amendment must identify the commits at which the criterion was introduced and retired.

The amendment must not describe the criterion as an open degree of freedom. It was a committed criterion and was subsequently withdrawn before evaluation for methodological reasons.

The amendment may reinstate an order-of-magnitude relationship only as a limited historical-anchor condition within Classification 2. It must not represent `0.17398` as an equivalent reproduction target or as the primary endpoint.

## 2. Classification 2 — Reconstructed but not reproduced

Classification 2 must be falsifiable and must require all seven predeclared conditions below.

### Condition 1 — Procedurally valid execution

All pre-execution controls must pass, including:

* the G0.c amendment exists at the declared amendment commit;
* the amendment commit is recorded and is an ancestor of the execution commit;
* all pinned artefacts resolve in the amendment commit's tree;
* the worktree state is clean or explicitly declared;
* no prior G0.c result directory exists;
* the checkpoint digest matches the preregistered digest at runtime;
* the canonical environment identity matches the preregistered identity;
* the split and dataset digests match the preregistered values.

Failure of this condition yields:

> Gate execution invalid — no evidential classification. This is not a result.

### Condition 2 — Complete instrument execution

The complete declared evaluator and test population must execute.

This requires:

* no required test is absent, skipped, deselected or uncollected;
* the upstream-marked population equals the count pinned to the upstream commit and manifest hash;
* all required evaluation outputs are produced;
* all required seeds or deterministic repetitions are complete;
* all lineage records and manifests are present;
* no contamination-barrier override is used for a scientific table.

Failure of this condition yields no Classification 2 result.

### Condition 3 — Deterministic checkpoint-arm repeatability

The released checkpoint arm must be executed twice under identical declared conditions.

The following must be identical between the two runs:

* raw implemented metric values;
* checkpoint digest;
* dataset and split digests;
* evaluator commit;
* environment identity;
* configuration identity;
* evidence class;
* seed declarations;
* table-lineage inputs.

The amendment must define whether identity means bit-identical serialized output or exact equality of the parsed numerical and lineage records. It must not substitute a coefficient-of-variation threshold for deterministic repeatability.

Failure of this condition is a Layer-B instrument failure and yields no evidential classification.

### Condition 4 — Random-control replayability and distinctness

The random-initialized control must use three predeclared `model_seed` values.

For each seed:

* Python, NumPy, PyTorch and CUDA random states must be seeded before model construction;
* replaying that seed must recreate identical model parameters and identical evaluation outputs under identical conditions;
* `random_init` must be `true`;
* `checkpoint` must be `null`;
* the evidence class must be ineligible for scientific performance tables.

Across different declared model seeds:

* at least one model parameter must differ;
* the three controls must represent distinct initializations rather than three dataloader permutations of one model.

Failure of exact replay is a Layer-B instrument failure and yields no evidential classification.

### Condition 5 — Metric validity and completeness

Every classificatory metric must:

* be implemented before execution;
* have a declared manifest key;
* have a declared table or adjudication role;
* be finite;
* fall within its mathematically valid range;
* be traceable through the lineage record to raw run outputs;
* not duplicate another classificatory metric algebraically or deterministically.

Orientation cosine metrics affected by F12 may be retained descriptively but must not be counted as independent classificatory evidence.

Rank correlation of temporal distance is not part of G0.c unless it is separately implemented and preregistered before execution.

Failure of a required metric's validity or completeness prevents Classification 2.

### Condition 6 — Predeclared behavioural sanity ordering

The released checkpoint must satisfy every preregistered Layer-C ordering that is defined over implemented loss terms.

At minimum, the amendment must identify:

* the exact primary implemented loss or loss aggregate;
* the exact direction of the expected checkpoint-versus-random relationship;
* whether the comparison is against each random initialization individually or against a declared aggregate;
* how ties are treated;
* how incomplete satisfaction is classified.

The checkpoint must outperform the random-initialized control according to the complete predeclared ordering rule.

Descriptive cosine measures must not rescue a failed implemented-loss ordering.

If Layer B passes but only part of Layer C passes, the outcome must be reported as:

> Valid instrument execution with insufficient behavioural evidence for Classification 2.

That outcome is a diagnostic result and must not populate the preregistered scientific result table as "Reconstructed but not reproduced."

### Condition 7 — Limited historical-anchor relationship

The GO Stanford-only reconstructed evaluation must not be claimed numerically equivalent to the five-dataset value `0.17398`.

For Classification 2, the amendment may require only the following limited relationship:

* the checkpoint's declared total-loss quantity is within one order of magnitude of `0.17398`;
* the comparison is reported as a historical-anchor sanity condition, not a reproduction tolerance;
* any deviation is interpreted in light of the non-equivalent dataset population, reconstructed split and unrecoverable upstream mixture;
* satisfying this condition does not establish reproduction;
* failing this condition prevents Classification 2 but does not by itself establish non-reconstructability.

The amendment must state the exact mathematical definition of "within one order of magnitude."

All seven conditions are conjunctive. Classification 2 is available only if Conditions 1–7 all pass.

## 3. Classification 3 — Not reconstructable

Classification 3 is reserved for cases where the relationship between the released artefacts, available code, available data and the reported upstream evaluation cannot be reconstructed to a scientifically defensible minimum.

Classification 3 must not be used for:

* a high loss;
* failure to outperform the random control;
* failure of deterministic replay;
* a corrupted download;
* an environment mismatch;
* missing seeds;
* incomplete execution;
* a failed test;
* an implementation defect;
* an inconvenient or unexpected metric value.

Those are respectively behavioural findings or invalid gate executions.

Classification 3 may be assigned only where all applicable acquisition and procedural controls have been completed, but a load-bearing element of the evaluation remains unavailable or irrecoverably ambiguous. Examples include:

* the released checkpoint cannot be associated with a defensible evaluation configuration;
* the required evaluation population cannot be identified or reconstructed;
* the reported metric cannot be computed from the released code or artefacts;
* the original dataset mixture or weighting is indispensable to the claim and cannot be recovered;
* the relationship between the reconstructed evaluation and the reported upstream result cannot be stated without unsupported assumptions;
* artefact incompatibility prevents a scientifically meaningful evaluation despite verified, intact files and a valid environment.

The report must identify the exact missing or ambiguous element and explain why no narrower reconstruction is scientifically defensible.

Classification 3 is therefore an evidential finding about the limits of the released record. It is not a synonym for gate failure.

## 4. Classification 1 — Reproduced

Classification 1 is available only if an evaluation materially equivalent to the reported upstream evaluation is reconstructed and satisfies a preregistered numerical equivalence criterion.

Given the currently established F10 finding, unrecoverable original splits and the five-dataset composition behind `0.17398`, Classification 1 is not expected unless new documentary or artefactual evidence recovers the missing protocol.

The amendment must not weaken the meaning of reproduction merely to make Classification 1 attainable.

## 5. Layer-B and Layer-C outcome mapping

The amendment must map outcomes before execution as follows:

| Layer B | Layer C                                                                                          | Outcome                                                                                |
| ------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| Fails   | Not adjudicated                                                                                  | Gate execution invalid — no evidential classification                                  |
| Passes  | All preregistered conditions pass                                                                | Classification 2, subject also to Conditions 1–5 and 7                                 |
| Passes  | Partial behavioural conditions pass                                                              | Valid instrument execution with insufficient behavioural evidence for Classification 2 |
| Passes  | Behavioural sanity ordering fails                                                                | Valid negative behavioural finding; not Classification 2 and not Classification 3      |
| Passes  | Upstream relationship remains scientifically indefensible because of irrecoverable specification | Classification 3, if the reserved-scope requirements are met                           |

The amendment must give every partial case an explicit home. No outcome may be assigned retrospectively by narrative discretion.

## 6. Scene-grouped reconstruction

The amendment must bind G0.c to the committed reconstructed scene grouping and allocation artefacts.

It must record:

* `scene_key_v1 = ^(no\d+|sim\d+)`;
* 3,696 trajectories;
* 53 reconstructed scenes;
* zero unparsed trajectories;
* whole-scene allocation;
* `scene_order_v1`;
* ascending BLAKE2b ordering;
* approximately 20% holdout by trajectory share within each naming family;
* 760 held-out trajectories;
* 15 held-out reconstructed scenes;
* 8 `no*` scenes and 7 `sim*` scenes in the holdout;
* no reconstructed scene appearing in both partitions;
* committed split files and their digests.

The grouping must be described as reconstructed because `traj_data.pkl` contains no native scene identifier.

Both `no*` and `sim*` naming families must be retained. Their composition must be reported. The amendment must not claim that `sim*` means simulated data or that the two families differ in acquisition modality.

## 7. Artefact binding

Every artefact named by the amendment must exist in the amendment commit's tree or be an externally acquired binary pinned by a committed digest record.

The freeze audit must verify artefact existence against the amendment commit using the commit tree, not the later worktree.

At minimum, the amendment must bind to:

* `gates/G0/SHA256SUMS`;
* the released ViNT checkpoint digest;
* the GO Stanford archive digest;
* the committed split files;
* the split manifest;
* the reconstructed scene inventory;
* the grouping and allocation implementation versions;
* the canonical environment identity;
* the evaluator and table-lineage schema versions.

## 8. Attribution and epistemic limits

The review must be attributed as an external methodological review through the recorded review channel.

The amendment must not claim that:

* it validates itself;
* the freeze audit proves scientific validity;
* conformance to upstream establishes conceptual correctness;
* a green gate guarantees a correct scientific conclusion;
* G0.c cannot fail.

The freeze audit establishes declared procedural properties. Conformance oracles establish consistency with the pinned implementation. Neither establishes that the upstream metric or conceptual design is valid.

## 9. Required red-team adjudication

The red-team must answer the following question:

> Does the revised amendment restore a genuinely falsifiable G0.c classification without reintroducing an invalid numerical comparison to `0.17398`, and are the checkpoint-arm and random-control repeatability criteria correctly separated by their sources of variance?

The verdict must be one of:

* **Fixing**
* **Rescuing**
* **Cannot determine**

The amendment may be committed only if the verdict is **Fixing**.

A **Fixing** verdict requires the reviewer to conclude that:

* the amendment corrects identifiable protocol defects;
* no released-checkpoint result informed the changes;
* the seven Classification-2 conditions are fully specified;
* Classification 3 remains reserved for evidential non-reconstructability;
* all partial outcomes have predeclared homes;
* the historical `0.17398` change is disclosed honestly;
* the amendment does not relax the frozen scene-grouping requirement;
* the amendment does not certify its own validity.

## 10. Execution boundary

After a Fixing verdict and amendment commit:

1. Run the freeze audit using the exact amendment commit SHA, not `HEAD`.
2. Require all freeze-audit checks to pass.
3. Archive the complete audit output.
4. Verify that no prior G0.c result directory exists.
5. Verify the checkpoint digest immediately before scoring.
6. Execute only the preregistered commands.
7. Apply the frozen classification rule without amendment, rescue or reinterpretation.

Until these steps are complete, the released checkpoint must not be loaded for evaluation and no G0.c metric may be produced.

This supplies the seven Classification-2 conditions, the reserved scope of Classification 3, and the exact disclosure language needed to complete the held draft and run the red-team.
