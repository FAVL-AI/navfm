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

## Two candidate rules, both refuted by measurement

Recorded because each looked correct and each is wrong, and a later reader
reaching for either should find the measurement rather than repeat it.

### Refuted: bound by collidable geometry

The robot must stand on something, so bounding by colliders should exclude a
non-collidable backdrop. Enumerated with `Usd.TraverseInstanceProxies()` — plain
`stage.Traverse()` finds zero colliders in these instanced scenes, which was the
first attempt's error:

| | colliders | collider bounds | stage bounds |
|---|---|---|---|
| Hospital | 2,160 | 766 × 418 cells | 766 × 420 cells |
| Office | 3,645 | **identical to stage bounds** | 10635 × 6771 cells |

It reproduces Hospital exactly, and does nothing at all for Office: the skyline
buildings **carry colliders**. Refuted.

### Refuted: bound by where the robot can stand

The support test G3 and G4 already use — raycast down, accept a hit within
`SUPPORT_FLOOR_TOL_M` of `floor_z` — applied as a 1 m coarse scan. Cheap, at
353,000 rays/second: 2.2 s for Office's 723,135 cells.

| | coarse cells | cells reporting ground | ground extent |
|---|---|---|---|
| Hospital | 3,354 | **3,354 (100%)** | 77 × 42 m |
| Office | 723,135 | **723,135 (100%)** | **1064 × 678 m** |

Every cell in Office reports ground at `floor_z = 0`. The city backdrop is not
floating scenery; it stands on a ground plane spanning the entire stage. So by
pure geometry the robot could stand almost anywhere, and the support criterion —
correct as a gate — does not bound a collection region. Refuted.

### What the refutations establish

**Office has no intrinsic geometric boundary.** It is not an enclosed interior
with a bounded floor; it is an office placed on a large ground plane in a city.
Any bounded collection region for such a scene must be **declared**, and the
declaration must be principled and frozen before candidates are enumerated.

### Surviving candidate: a window justified by the frozen route length

`CollectConfig.max_path_m = 40.0` is already frozen. Euclidean displacement
cannot exceed path length, so every point of every admissible route lies within
40 m of its start. A square window of half-width `max_path_m` plus a footprint
margin, centred on a declared region centre, therefore cannot exclude any route
the contract would admit — and at 0.10 m it is roughly 820 × 820 = 672,400
cells, about twice Hospital's and entirely tractable.

The one declared input is the region centre, which must be stated and justified
before any Office candidate is enumerated, and recorded in provenance.

**This must be opt-in, and Hospital's default must not change.** A window applied
to Hospital would produce a different grid from the 420 × 768 that produced the
frozen result, and a different grid means different sampling. Hospital's result
is frozen; it is not re-derived under a new bounds rule.

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
