# BO-10 / E2 scope separation — frozen 2026-09-07

**Status:** FROZEN, append-only. Superseded only by a later dated declaration in
this directory; never edited in place.

**Machine-readable form:** `bo10_e2_scope_declaration_20260907.json`
**SHA-256:** `7bc18794bf6242b2652acc597f37ae680f126242bfeb5907d94592bc055e47ec`

Frozen at git head `6ce98933c116d81b32cbddbf08259ed72cc7c09a`, **before** any
change to the collection code it governs. The ordering is the point: a scope
declaration written after the collector was modified would be a description of
what happened, not a constraint on it.

## Purpose

One new Hospital trajectory, collected through the production collector
(`src/navfm/isaac/collect.py`), used **only** to prove:

- simulator collection execution
- data-format correctness
- GNM compatibility
- ViNT compatibility
- NoMaD compatibility

## E2 status: EXCLUDED

    e2_eligible = false

The BO-10 trajectory must NOT be used for:

- E2 2×2 experimental cells
- E2 estimator computation
- E2 confidence / tolerance decisions
- E2 held-out evaluation
- E2 per-cell episode counts
- E2 optional-stopping decisions
- thesis effect-size claims based on E2

The exclusion is by **construction**, not by wording. The manifest carries
`purpose`, `e2_eligible` and `e2_exclusion_reason`; `navfm.collection.scope`
refuses such a trajectory at the E2 admission boundary; and a negative control
proves the refusal fires.

### Why wording alone was not enough

The failure this guards against is not misconduct, it is a future script. A
selection step that globs `runs/` for trajectories and computes an estimator
would pick this one up, and nothing in the number it produced would record that
a compatibility trajectory had entered a statistical population. That is the
FL-019 shape — a value that carries no record of the population it came from —
and the defence has to sit in the admission path, not in a document.

An undeclared manifest is therefore **refused**, not admitted. Absence of a
scope block is not evidence of eligibility.

## The four deferred E2 decisions are untouched

This declaration makes none of them and changes no E2 expectation:

- E2 estimator
- E2 tolerance
- E2 held-out scene count
- E2 per-cell episode count
- E2 stopping rules
- E2 expectations

Their status remains what `PREREGISTRATION.md` Amendment 1 and
`gates/g2_decisions.json` say it is: **DEFERRED**, and still blocking E2
collection.

## `--acknowledge-g2-block`

Authorised **only** for this BO-10 compatibility scope, and only when bound to
this declaration by path and SHA-256 digest. It is not converted into a general
bypass:

- passing the flag without the declaration is refused;
- passing it with a declaration whose digest does not match is refused;
- passing it with a declaration whose purpose is not
  `BO10_FRAMEWORK_COMPATIBILITY` is refused;
- using it stamps `e2_eligible = false` into the manifest, so the resulting
  trajectory can never be admitted to the E2 population.

An acknowledgement flag that can be passed on its own is a bypass with a comment
attached. Requiring the digest means the only way to use the flag is to name the
scope it was granted under — and the scope carries the exclusion.

## What this declaration does not do

- It admits no route.
- It does not authorise the production Hospital collection.
- It makes no physical-hardware claim.
- It does not open E2, and does not weaken the G2 block for any other purpose.
- It does not repair, reinterpret or replace the scene-wide traversability
  verdict. Hospital remains **NOT ADMISSIBLE** scene-wide, and
  `COLLECTION_ROUTE_ADMISSION_V1` still governs whether any route may be
  collected at all.
