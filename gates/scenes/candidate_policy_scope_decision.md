# Scope decision — what `candidate_policy.py` owns, and what it must not

Decision ID: `SD-001`
Date: 2026-09-03
Sprint: 2B.1
Author: Frank Asante Van Laarhoven
Status: FROZEN. Amendments are new dated sections, never edits to this one.

## Decision

`src/navfm/candidate_policy.py` governs **target-directed candidate
interventions only**.

**In scope**

- BLOCKER target interrogation
- SUPPORT target interrogation
- explicit causality-control variants of those target interventions

**Out of scope**

- generic PhysX overlap queries
- robot-footprint occupancy tests
- robot-footprint sweeps
- traversability sweeps
- volumetric collision-oracle operations that do not construct an
  intervention toward a declared target

**No `VolumetricPolicy` is to be added to `candidate_policy.py`.**

## Reason

The two families have different estimands, and that is the whole of it.

A target-directed probe asks:

> Did *this declared object* causally produce the observation?

A footprint overlap or sweep asks:

> Can *this robot volume* occupy or traverse this space?

Both are collision-related. Neither is a special case of the other. A probe
toward a declared target can be wrong by hitting the wrong collider; a
footprint sweep has no declared collider to be wrong about. Folding them into
one abstraction would blur the boundary the last three sprints existed to
make explicit, and would let a consumer satisfy a target-identity contract
with a measurement that never declared a target.

This is a deliberate scope boundary, not a missing implementation. Recording
it as absence-by-design is the point: a later reader finding no volumetric
support in the candidate policy must be able to tell "decided against" from
"not got round to".

## Consequence for `validate_physx_footprint_oracle.py`

Surveyed for a target-directed portion. **There is none.**

| Operation | Query | Declares a target? | Adjudicates collider identity? | Owner |
|---|---|---|---|---|
| `support()` | 5 x `raycast_closest`, -Z | no | no — counts hits and height spread | footprint/oracle contract |
| `overlap()` | `overlap_box` | no | no — counts hits | footprint/oracle contract |
| `sweep()` | `sweep_box_closest` | no | records the collider string, adjudicates distance | footprint/oracle contract |

`check()` compares `support_valid`, `overlap_hits`, `occupiable`,
`traversable`, `sweep_status`, `distance` and
`clear_run_lower_bound_m`. Not one of those is a claim about which declared
object caused an observation. The word `target` does not appear in the
harness.

`support()` uses rays, which is why it can look target-directed at a glance.
It is not: its origins come from a robot pose and its footprint offsets, and
its verdict is about the robot's own support, not about any surface's
identity. A ray is not a target interrogation merely because it is a ray.

Therefore the harness routes **nothing** through `candidate_policy.py`, and
its overlap, sweep and footprint-support semantics stay under the
footprint/oracle contract with its own frozen expected answers in
`gates/scenes/physx_fixture_expected_answers.json`.

If a target-directed ray probe is ever added to this harness -- one that
declares a target prim and adjudicates the returned collider against it --
that probe MUST use `candidate_policy.py`. The rule is the question asked,
not the file it is asked from.

## Consequence for the Sprint 2C representability criterion

A consumer counts as REPRESENTABLE when every **target-directed candidate
intervention it requires** can be represented by `candidate_policy.py`.

It does **not** require generic volumetric operations to be representable
there. A consumer with no target-directed portion is representable
vacuously, and that is a correct result rather than a loophole: there is
nothing for the shared policy to own.

## Open item carried into 2C

`Role.FOOTPRINT_SUPPORT` was added to `candidate_policy.py` in Sprint 2B,
before this boundary was drawn. It takes a robot `Pose`, declares no target
and adjudicates no identity, so by this decision it sits on the out-of-scope
side of the line it is currently inside.

It is recorded here rather than removed silently: deleting it changes the
policy serialization and therefore the policy digest, which is a physics-
provenance event and not a tidy-up. No consumer calls it, so it blocks
nothing. The decision to remove it, and the digest change that follows,
belongs to whoever opens 2C.

## Digest effect

**None.** This decision changes no implementation and no serialized policy
semantics, so `candidate_policy_digest` remains `2cec5cf6bc23edb8`.

Changing the digest to mark a scope decision would be a lie in the exact
grammar the digest exists to speak: it would tell a later reader that the
physical intervention changed when nothing about the experiment moved. A
digest changes when the physics changes. Recording what was always
conceptually out of scope is not a change to the physics.

## Claim boundary

This decision concerns ownership of measurement semantics. It does not
establish that any consumer currently uses the shared policy -- none does --
and it does not validate any scene. Hospital remains NO_EVIDENCE, `wrong_1`
remains UNRESOLVED, Office and Warehouse are untouched, and no canonical
scene is selected.
