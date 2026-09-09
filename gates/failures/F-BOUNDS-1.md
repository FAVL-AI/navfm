# `F-BOUNDS-1` — the occupancy map is built over the whole stage, including scenery the robot can never reach

**Status: OPEN.** Raised 2026-09-09 while attempting the Office BO-10 route
admission. Blocks Office measurement; does not affect any Hospital result.

## What was observed

The Office route-admission run could not be completed. Three attempts were
stopped — the first under host memory pressure, the second pre-emptively, the
third after diagnosis. Measured cause, by stage, on host `favl`:

| stage | RSS | elapsed |
|---|---|---|
| SimulationApp started | 4.47 GB | — |
| Office scene referenced | 4.55 GB | — |
| physics stepped | 5.20 GB | — |
| **occupancy built** | **7.36 GB** | **49.0 s** |
| clearance transform | 7.36 GB | +63.8 s |
| inflation | 7.36 GB | +1.0 s |
| 40,000 raycasts | 7.36 GB | 0.2 s |

Two things are settled by that table. Memory is **stable, not leaking** — it
plateaus at the occupancy build and never moves again, through two batches of
raycasts. And **raycasting is not the cost**: 353,000 rays/second.

The cost is the grid itself:

| | Hospital | Office |
|---|---|---|
| occupancy grid | 420 × 768 | **6770 × 10635** |
| cells | 322,560 | **71,998,950** |
| implied extent at 0.10 m | ~42 × 77 m | **~677 × 1064 m** |

## Root cause

`Collector._stage_bounds()` computes the world bound of the stage pseudo-root
and `build_occupancy` maps that whole rectangle. Office contains

    /World/Scene/SM_Buildings

a city-skyline backdrop spanning 1063.55 × 677.15 m — the exterior scenery
visible through the office windows. Stage bounds are
`[-528.08, -294.67] .. [535.48, 382.47]`.

The traversable office is nowhere near that size. The next largest spans are the
GroundPlane collision mesh at 50.0 m and interior prims at 58.0, 49.6 and
31.3 m. So roughly 99.5% of the mapped area is exterior backdrop the robot can
never occupy, and the grid is 223× larger than Hospital's for a comparable
interior.

Hospital was unaffected only because it has no backdrop, not because the rule is
sound. Any scene with distant scenery has the same defect.

## Why this was not caught earlier

Nothing fails. The map builds, the planner plans, and the numbers look ordinary
— they are simply computed over a rectangle that is mostly unreachable exterior.
On Hospital the rule and a correct rule agree, so the Hospital results are not
in question. The defect only becomes visible as cost, and cost reads as "this
scene is big" rather than as "this bound is wrong".

## What must NOT be done

- **Do not exclude prims by name.** `SM_Buildings` is one scene's spelling of a
  general problem; a name filter would pass Office and fail the next scene
  silently.
- **Do not shrink the bounds until Office yields a passing route.** Bounds chosen
  after seeing route outcomes are a parameter tuned to an outcome. Whatever rule
  replaces the current one must be declared and frozen before Office candidates
  are enumerated.
- **Do not treat this as a memory problem.** It was diagnosed as one twice —
  first as an unbounded cache in the harness, which the measurements above
  refute — and both diagnoses were wrong. The caches were bounded anyway on their
  own merits, and that change is not claimed to have fixed this.

## Candidate rule, not yet validated

The occupancy map only needs to cover where the robot can be, and the robot must
be on collidable ground. Bounding by collidable geometry would exclude a
non-collidable backdrop generally rather than by name.

That rule is **not yet demonstrated**. A first attempt enumerated
`UsdPhysics.CollisionAPI` over `stage.Traverse()` and found **zero** collider
prims in Office, while the Hospital route pass demonstrably raycast against
prims such as `/World/Scene/Geo_W_TrimStrateBase5/...`. These environments are
heavily instanced and plain traversal does not descend into instance proxies, so
the enumeration was wrong rather than the scene being collider-free. Any
implementation must traverse with `Usd.TraverseInstanceProxies()` and must be
validated against a scene whose answer is already known — Hospital, where the
current bounds are known to be reasonable and a correct rule must reproduce
them.

## Effect on results

- **Hospital: none.** `HOSPITAL_BO10_FROZEN_ROUTESET = NO_ADMISSIBLE_ROUTE`
  stands. Its grid was 420 × 768, no backdrop inflated it, and no threshold or
  candidate depends on this.
- **Office: NOT MEASURED.** No Office candidate was enumerated, so there is no
  Office route-admission result of any kind — not a pass, not a failure, and not
  an inconclusive verdict about routes.
- **BO-10: still BLOCKED**, now behind scene-bounds derivation rather than behind
  Hospital admission.

## Resolution requires

1. A declared, scene-independent bounds rule, frozen before Office candidates are
   enumerated, recorded in provenance with the derived bounds.
2. Validation against Hospital first: the rule must reproduce bounds consistent
   with the 420 × 768 grid that produced the frozen result. A rule that changes
   Hospital's grid would put that result in question and must be adjudicated
   before use.
3. Only then, Office route admission under the unchanged frozen contract.
