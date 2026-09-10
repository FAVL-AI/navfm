# Validation-harness defects — four ways an instrument can lie about an instrument

**Append-only.** Recorded 2026-09-10, during the F-G5 obstacle-map repair. None
of these were defects in the probe under test. All four were defects in the
apparatus built to judge it, and each would have produced a wrong verdict — two
toward false failure, two toward false confidence.

The original failing artefacts are **not overwritten**. They are the evidence
that these happened.

## The methodological lesson

> Expected occupied cells must be defined by **actual geometric intersection**,
> never by AABB membership.

Two of the four defects below are the same violation of that sentence, made
twice — once on a synthetic rotated box and once on a real reception desk. That
it recurred after being fixed is itself the finding: the AABB is available,
convenient, and wrong, so it will be reached for again unless the rule is
written down.

---

## `H-FIXTURE-1` — fixtures silently became tangency tests

**Toward false failure.**

Each fixture derived its grid origin as `bx - 0.25`, where `bx` was the box's
minimum. That places the box minimum exactly 2.5 cells from the origin — that
is, exactly on a cell boundary. Every fixture therefore tested boundary
tangency in addition to whatever it was meant to test, and disagreement between
the strict and touch conventions contaminated all of them at once.

Observed: 5 of 12 fixtures failed with large false-positive counts that were
entirely convention artefacts. `C_wall_on_cell_boundary` reported 8 expected
against 20 measured.

**Repair.** Fixtures are offset by a third of a cell. `C` deliberately keeps the
boundary-aligned origin, because tangency is its subject rather than its
contaminant.

**Why it was hard to see.** The fixtures were individually reasonable and the
origin rule was written once, far from them.

---

## `H-AABB-1` — AABB coverage treated as occupied truth (rotated box)

**Toward false failure.**

The rotated-obstacle fixture was judged on "no false negatives against the
measured world AABB". A world AABB strictly **over-covers** a rotated box, so
cells inside the AABB but outside the shape contain no geometry and must be
free. The rule therefore demanded that the probe mark empty cells, and scored a
correct answer as 5 false negatives.

**Repair.** Rotated geometry is judged on containment — every measured cell must
lie inside the AABB expectation, and the object must be found at all.

---

## `H-AABB-2` — the same error, repeated on a real object

**Toward false failure, and the most dangerous of the four.**

The identical mistake was then applied to real Hospital objects. The reception
desk was judged against its bounding box and reported **540 false negatives at
0.28 recall**, which read as a serious probe failure.

It was not. An independent dense sub-sample — 5×5 points per cell at three
heights, using small spheres rather than the cell-sized box — showed **all 540
unmarked cells genuinely empty**. The desk occupies 28% of its bounding box,
which is what an L-shaped desk does. The supply cart's 5 unmarked cells were
likewise all empty.

**Why this one mattered most.** The obvious response to "the desk fails" is to
increase the query epsilon until it passes. That would have manufactured false
positives to satisfy a broken yardstick, corrupting the instrument while making
the report look better — and the corruption would have been invisible, because
the fixtures that were genuinely exact would have stayed exact.

**Repair.** Real-object adjudication re-tests every unmarked in-AABB cell with an
independent query, and only independently-occupied cells count as false
negatives.

---

## `H-INSTANCE-1` — the instancing control put a collider at the world origin

**Toward false failure, from self-contamination.**

The instancing prototype `/W/Proto/Box` carried a real `CollisionAPI` and had no
translate op, so it sat spanning ±0.05 about the world origin — exactly where
fixture `A_box_inside_one_cell` was measured. Fixture A reported 3 false
positives from geometry the harness had placed there itself.

**Repair.** The prototype is translated to (500, 500, 0), clear of every fixture.

**Why it was hard to see.** The prototype is required to carry a collider, since
the instance's collider is what the control exists to detect. Its own placement
was never considered because it was thought of as a template rather than as a
prim in the scene.

---

## What none of these were

None was a defect in the cell-volume probe. After all four repairs the probe
passes 13 of 13 analytic fixtures with exact set agreement and 5 of 5 known
Hospital objects with zero genuine false negatives, at epsilon = 0 and with no
per-object tuning.
