# Trigger 4: held-out layout freeze (heldout_layouts_v1), 2026-10-09

Independent reviewers received only the artefacts (spec, generator, scene
geometry, collector guard, tests), never this session's reasoning, and were
instructed to refute. Verdicts are recorded as returned, condensed.

## Pass 1: DO-NOT-FREEZE

First design: 3 groups x 2 routes, routes 3.3-4.3 m from x=0.5.

1. BLOCKING. Endpoints within groups A and C nearly coincided: teacher stops
   0.40 m (A) and 0.05 m (C) apart, inside a 0.5 m arrival radius, so the goal
   image was never needed.
2. MAJOR. Step budget not frozen; the default 240 steps (20 s) made the teacher
   time out on hc_route_0/1 (243 and 266 steps needed).
3. MAJOR. Routes were longer and started elsewhere than training, so novelty of
   scene and route were confounded; the "route shapes absent from training" claim
   was false.
4. MAJOR. Weak goal views: ha_route_0 51% blank wall; group B horizontal bands
   carried no lateral cue.
5. MAJOR. Seal advisory only: a `sealed:false` copy passed; routes extracted to
   `--route-spec` were accepted (index 40 renders as legacy scene 0); no single
   use; no scoring gate.
6. MAJOR. n = 3 groups too small; no analysis plan.
7. MINOR. Policy clearance not modelled.
8. MINOR. Disjointness test checked only scene index and floor colour.

## Pass 2 (after redesign to 6 groups, training-matched starts and lengths): DO-NOT-FREEZE

Resolved: 1. Partial: 3 (new wording "route shapes NOT novel" also false: no
training route ends laterally offset facing +x), 4 (checked at teacher rollout
pose, not the goal-photo pose), 5, 6, 7, 8. Unresolved: 2 (collector never read
the protocol). New findings:

- N1 HIGH. `--limit` default 10 silently dropped two of twelve sealed routes.
- N2 HIGH. Training admission, teacher replay and live summary scripts ungated.
- N3 MED-HIGH. Seal bypassed by renaming, re-indexing and a 1 mm waypoint shift;
  scene appearance not sealed.
- N4 MED. Single-use ledger incompatible with a multi-run protocol; scoring flag
  not tied to any ledger.
- N5 MED. Straight-line null wrong; goal-blind always-left/right nulls score
  about 6/12; need goal-swap control and completion as primary endpoint.
- N6 MED. Paired goals differed only by panel colour.
- N7 MED. Six groups contradicted frozen split v1 (A-C).
- N8 LOW ray-cast limits; N9 LOW reserved indices; N10 LOW speed not bound.

## Amendments made before pass 3

- Collector binds a sealed run to the protocol: every route, `--max-steps` 360
  teacher / 600 policy, `--policy-max-v` 0.1, no perturbation, the sealed bytes
  only, and one pre-declared slot (`unseal_slots`) in an external ledger
  directory. `--limit` no longer truncates layout specs.
- Seal matches route id, reserved scene index, route geometry (Hausdorff
  < 0.1 m) and scene appearance (half of a sealed scene's boxes reproduced in
  colour and size); admission, replay, summary, decompose and audit scripts
  refuse sealed data; scoring requires the collection to be in the ledger.
  `split_routes` rejects split "heldout".
- Verification runs at the goal-photo pose; paired landmarks differ in shape
  (solid block vs three bars) and colour; colours at least 0.15 from every
  training colour; wording corrected (final approach pose is new to the policy).
- Analysis plan: completion primary, route denominators, Wilson intervals,
  goal-blind nulls, goal-swap control, post-render pair-distance check.
- `arrival_split_v2.json` amends v1 (held-out A-F) before any held-out data exists.

## Pass 3: FREEZE-WITH-AMENDMENTS

Resolved: 2, N1, N2, N4, N6, N7, N9, N10; 3 still carried a false claim (training
also ends near (2.8, 0.25) heading 0 and (2.8, 0.2-0.28) heading -12 deg); 4
resolved in code but the unseal text contradicted the goal semantics; 5/N5 partial.
New findings:

1. HIGH. Slot limit renewable by choosing a new ledger directory.
2. MED. Roles not bound to checkpoint presence; no checkpoint sha recorded or
   pre-declared, leaving room for checkpoint selection on held-out.
3. MED. No retry rule for runs that crash before an episode.
4. MED. "Completion must exceed 6/12" had no number.
5. LOW, accepted if documented. Seal residuals: >= 0.1 m route shift, uniform
   colour tint, copying under half a scene, reusing only the final approach pose.
6. LOW. Spec untracked until committed.

Amendments made (spec regenerated before commit):

- Text: design claim corrected; group E is the only route pair below 0.46 m
  teacher clearance (0.348 m); goals are the teacher run's final recorded frames
  and are now verified at that pose as well as the endpoint pose (dominant
  landmark is the route's own at both); decision rule completion >= 10/12
  (exact binomial vs p = 0.5, P = 0.019); goal-swap criterion >= 10/12 nearer the
  partner goal and <= 2/12 own-goal completion; retry rule; accepted residuals.
- Code: ledger pinned to `~/navfm-runtime-evidence/heldout_layouts_v1-ledger`
  for collection and scoring; roles bound to checkpoint presence; checkpoint
  sha256 recorded and required to be declared in
  `configs/splits/heldout_layouts_v1_checkpoints.json` (absent, so no policy run
  can unseal yet); goal sources must lie in the single teacher run (partner route
  for goal-swap); one retry per role for runs that attempted no episode; refusal
  tests for admission, replay and summary scripts.

Remaining documented gaps: goal-swap goal-root construction tooling and its
"nearer the partner goal" scoring are not built; they must exist and be tested
before the goal_swap_control slots are used.
