# Alias-aware feature/target resolution v1

**Decision: retain the legacy feature and latch unchanged; add a detached,
synthetically tested goal-region feature candidate.** This is an engineering
method decision, not evidence of visual discrimination, calibration quality,
arrival accuracy, navigation improvement, or novelty. No real data, images,
encoder, fitting, threshold search, simulator, collection, or navigation was
used.

## What the current rule actually does

The legacy feature computes ordered history scores `S(j)`, then
`terminal_score = S(J)` and `alias_margin = S(J) - max(S(j))` over nodes
outside the explicit terminal window. The logistic map has an unconstrained
margin coefficient, so it can learn a negative association or ignore margin.
Thus a negative margin alone does **not** force a low probability.

The separate legacy dwell rule is stricter: it requires both calibrated
probability above its threshold and `alias_margin >= alias_margin_floor`.
That explicit floor vetoes a high-probability prediction whenever the margin
falls below the chosen floor. The floor is caller-selected and unvalidated;
the synthetic counterexample does not show every possible floor or calibration
must fail. It does show that this extra hard gate can conflict with the
geometric label.

## Synthetic counterexamples and alternative

The frozen label is positive when query XY lies within 0.5 m of the requested
goal image's capture pose. A valid positive can match a different reference
inside that same region more strongly than the final goal image. For the
reviewed score vector `S=(.125,.125,.125,.2,.9,.1,.1,.6)`, terminal index 7,
and valid-region references `{4,7}`, the legacy terminal margin is `-.3`.
The region-aware alternative instead gives goal-region support `.9` and
out-of-region contrast `.7`.

The additive candidate in
[`alias_aware_arrival.py`](../src/navfm/collection/alias_aware_arrival.py)
accepts explicitly bound reference identities and computes:

```text
G = references whose authenticated capture poses are within 0.5 m of the
    requested goal image's capture pose, including that goal reference
goal_region_score = max(S(j) for j in G)
outside_score = max(S(j) for j not in G)
region_margin = goal_region_score - outside_score
```

The function requires the requested goal to be the final ordered reference,
its identity to belong to `G`, at least one outside competitor, and unique
nonempty reference IDs. It refuses absent/unknown region members. It receives
no query pose or query label. The only eventual static prediction rule under
consideration is a calibrated probability of geometric proximity compared
with a separately justified probability threshold; `region_margin` is a
calibration feature, not an independent hard veto. This component does not
emit STOP and does not implement dwell for the new candidate.

### Residual limits tested

- **Multiple valid references:** max pooling allows the best-scoring valid
  reference to support the region instead of treating it as a distractor.
- **Distant lookalike:** a high-scoring out-of-region node can still dominate.
  If positive and negative queries have identical similarity inputs and
  identical reference annotations, every deterministic score function returns
  identical features. The method cannot separate them from these inputs alone.
- **Ordering:** pooling `(score, identity, membership)` tuples is invariant to
  permutation, but `S(j)` uses ordered `j-k` history alignment. Reordering the
  reference chain can change `S` and the resulting features.
- **Density:** duplicating an already-scored value does not change max pooling.
  Adding/removing nodes changes upstream index alignment and can change `S`;
  score maxima can also depend on which distinct views are added. No density or
  cadence invariance is claimed.
- **Calibration:** a synthetic logistic fit can assign a negative coefficient
  to margin and rank a lower-margin positive above a higher-margin negative.
  This shows the feature is learnable in a fixture; it does not establish
  that real data can estimate that relation or that an arbitrary hard floor is
  safe.

## Required input and eligibility boundaries

To construct `G`, the reference bank must carry authenticated per-reference
capture poses and the requested goal reference's capture pose in one common
coordinate frame, bound to their RGB identities and the frozen 0.5 m radius.
Those are prior-reference metadata; live query pose is not an input. This is
additional deployment information compared with the current RGB/history-only
feature API. It must be disclosed and supplied consistently to every
comparator if used in a comparison.

The admitted training records contain per-frame pose and identity within each
trajectory, so membership is derivable for references from that same recorded
trajectory. That does not establish that deployment reference banks retain
the metadata or share a coordinate frame. The available data's single-pass
query/reference relationship is not established as deployment matched. The
new feature is therefore **not deployment-qualified**, and the old static
calibration contract's source hash remains bound to its earlier code version;
that contract must not be treated as binding this additive feature.

Development fitting and independent assessment are distinct:

- Prior encoder exposure does not automatically prohibit explicitly labelled
  development fitting. The current training records may support the geometric
  label within authenticated trajectory frames, but fitting still requires
  permitted deployment-matched query/reference inputs and the authenticated
  feature source.
- Encoder exposure limits claims of independent generalisation. A clean
  layout grouping can prevent additional partition leakage; it cannot undo
  prior encoder training exposure. Independent layout assessment requires
  appropriately unexposed groups.
- Existing development, retired-test, and accessed pilot outcomes remain
  exposed and excluded from independent assessment; future held-out groups
  remain forbidden for fitting. No new split is invented here.

## Bounded review and validation

One bounded method review was requested from **Astra at ultra reasoning**.
Requested model/settings are recorded; runtime identity and reasoning
configuration could not be independently verified. The review confirmed the
separate logistic-vs-hard-gate behavior, recommended the additive annotated
region support/contrast feature, and cautioned that reference ordering and
density remain consequential. It also highlighted the identical-input
positive/negative limit and the need to retain legacy behavior until reference
metadata is authenticated. This critique is advisory, not empirical evidence
or human approval.

Focused synthetic validation used the declared `navfm-ci` environment and
this worktree's `src` binding:

```text
PYTHONPATH="$(pwd)/src" /home/favl/miniforge3/envs/navfm-ci/bin/python -m pytest -q tests/test_alias_aware_arrival.py
50 passed

/home/favl/miniforge3/envs/navfm-ci/bin/ruff check src/navfm/collection/alias_aware_arrival.py tests/test_alias_aware_arrival.py
All checks passed

/home/favl/miniforge3/envs/navfm-ci/bin/ruff format --check src/navfm/collection/alias_aware_arrival.py tests/test_alias_aware_arrival.py
Already formatted

PYTHONPATH="$(pwd)/src" /home/favl/miniforge3/envs/navfm-ci/bin/mypy src/navfm/collection/alias_aware_arrival.py
Success: no issues found in 1 source file
```

Tests cover the near-goal/nonterminal counterexample, multiple region
references, a distant-lookalike non-identifiability counterexample, identity
pooling, ordering and density behavior, rejection of missing/ambiguous region
metadata, a fitted negative margin association, and the legacy hard-floor
veto. Synthetic evidence proves only these API and arithmetic properties.

The `rio-research` and `enterprise-execution` skills informed the evidence
and implementation boundaries. Skill-retrieval search tools were unavailable.
No benchmark, calibration or research conclusion follows from this change.
