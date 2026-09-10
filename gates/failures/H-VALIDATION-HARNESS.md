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

---

## `H-SAMPLING-1` — a footprint sampler that never reached the object's far edge

**Toward false failure.** Found 2026-09-10 during the Office generalisation.

The helper that asked "how many of this object's cells does the map mark?"
stepped world points from the AABB minimum in strides of the resolution, taking
`int(span / res) + 1` samples. That covers `int(span / res) * res`, which is less
than the object whenever the span is not an exact multiple of the resolution.

`SM_InformationDesk_A_232` spans y from −11.7972 to −11.4548 on a grid with
origin y = −27.14. Its geometry sits in row 157. The sampler's last sample landed
at −11.4972, which is row **156**, so it examined rows 153–156 and reported the
desk **planner-invisible** — one genuine-looking false negative, enough to block
`OBSTACLE_MAP_FULL_ACCEPTANCE`.

The map was correct. Reading the production grid directly shows cells
(157, 407) through (157, 410) marked occupied, and `overlap_box` at that cell
centre returns a hit.

**Direction of error, and why it did not corrupt G2 V2.** Under-sampling can only
*miss* marked cells; it can never invent them. So it manufactures false
"invisible" reports and can never manufacture a false "visible" one. G2 V2's
result — 1,089 colliders checked, zero planner-invisible — was computed with the
same flawed helper and is therefore conservative: a correct helper can only
confirm it, never overturn it.

**Repair.** `cells_spanning_aabb` enumerates cell INDEX ranges from the corner
cells, so the far edge is included by construction. Pinned by a test using the
measured values above.

**The pattern.** This is the fifth harness defect in this tranche and the fourth
that produced a false failure. Every one of them lived in the apparatus, not in
the instrument under test. The recurring shape is an expectation computed by a
convenient proxy — an AABB, a stepped sample, a default transform — rather than
by the thing it claims to measure.

---

## Permanent rule for NavFM validation

All five defects in this ledger are instances of one mistake, and it is now
stated as a standing rule rather than left as five stories:

> **Validation expectations must be generated from an independent representation
> of the underlying geometry. They must not reuse an approximation taken from
> the instrument under test, nor a convenient proxy for it.**

The proxies that failed here, each of which was available and plausible:

| proxy used | what it stood in for | how it failed |
|---|---|---|
| world AABB | an object's true footprint | over-covers; produced false negatives twice (`H-AABB-1`, `H-AABB-2`) |
| stepped world samples | a cell index range | under-covers the far edge (`H-SAMPLING-1`) |
| a default transform | a deliberate placement | put a collider at the world origin (`H-INSTANCE-1`) |
| an origin derived from the object | an independent grid | forced boundary tangency (`H-FIXTURE-1`) |

Four of the five manufactured a **false failure**, which is the direction that
wastes effort and invites the worst possible repair: tuning the instrument until
the broken yardstick is satisfied. `H-AABB-2` came closest — raising the query
epsilon until the reception desk "passed" would have manufactured false
positives invisibly, because the fixtures that were genuinely exact would have
stayed exact.

The one direction that would have been far more dangerous — a proxy that
manufactured **false confidence** — did not occur here, and that is luck rather
than method. The rule above is what removes the luck.


---

## `H-ORDER-1` — the robot contaminated its own occupancy map

**Toward a wrong route.** Found 2026-09-10 in the BO-10 collection script.

The collection script spawned the robot and *then* built the occupancy map. The
robot carries colliders, so a robot standing in the scene is rasterised as an
obstacle: its cells leave the free set, and `sample_episode_pair` draws start and
goal poses from a different population than route admission did.

Replaying the admitted candidate 050 produced start (−25.099, 36.082) against the
admitted (−39.903, 23.121) — a different route entirely. The guard refused to
collect rather than silently driving a route the gates had never evaluated.

**Repair.** The map is built before the robot is spawned, matching route
admission, which builds its map with no robot present. Reproduction then matches
the admitted route exactly.

**Same genus as `H-INSTANCE-1`**, where the instancing prototype's collider sat
at the world origin inside a fixture. Both are a test or production fixture
placing collidable geometry into the scene it is measuring.

## `H-REPLAN-1` — re-planning from stored poses is not reproduction

**Toward a wrong route.** Same session.

The first collection attempt rebuilt the admitted route by running A* from the
stored start and goal poses. `sample_free_pose` returns a *continuous* pose,
which can round back into a different cell than the one it was sampled from: the
stored start (−39.903, 23.121) maps to cell (279, 97), which A* reports as
occupied, and the attempt failed with `PlannerError`.

**Repair.** The route is reproduced by replaying the seeded generator to the
selected candidate index, which regenerates the identical candidate including
the path the gates actually evaluated, and the result is checked against the
stored poses before anything is driven.


---

## Attribution-guard collision, recorded not bypassed

The machine-level pre-push attribution guard blocked a commit for the phrase
*"generated by a seeded sampler"* in `scripts/evaluate_g10_v2_plan.py`. It
matches the two-word `<verb>-by` construction where the verb is the past
participle of *to generate*, which is ordinary English here describing how a
candidate population comes about.

Reworded to *"comes from a seeded sampler run against"*. The guard was not
disabled and `--no-verify` was not used: a false positive costs one rewording,
and a disabled attribution guard costs the authorship rule the repository is
built on. This is the second such collision recorded in this programme.

---

## `H-LMDB-1` — one open LMDB environment produced two false incompatibilities

**Toward false failure.** Found 2026-09-10 during the loader-compatibility proof.

GNM, ViNT and NoMaD were built in one process from one split folder. The
reference loader writes an LMDB cache *inside* the split folder keyed by dataset
name, so the second and third builds hit:

```
Error: The environment '/tmp/_bo10_splits/recon/train/dataset_recon.lmdb'
is already open in this process.
```

Reported verbatim, that reads as **ViNT and NoMaD reject the trajectory** — a
false negative against upstream, on the exact question the tranche existed to
answer. GNM passed only because it happened to run first.

**Repair.** Each model gets its own split folder, so each gets its own LMDB
environment. All three then pass: 1190, 1190 and 1189 samples.

This is the LMDB-cache landmine the repository already documents, in a form it
had not taken before — not a stale cache across runs, but a live collision within
one process.

## `H-EVIDENCE-KEY-1` — the evidence guard failed closed, correctly

**Not a false failure. A guard working.** Same session.

The turning-population artefact contained a failure-combination dictionary keyed
by tuples, which JSON cannot serialise. `emit_evidence` raised

```
EvidenceNotPersisted: record is not serialisable, so nothing was written
```

after the full 96-candidate evaluation had already been computed.

It wrote nothing rather than a partial artefact, which is exactly the contract:
returning normally must imply valid evidence exists on disk. The alternative --
writing what serialised and dropping what did not -- would have produced an
artefact that parsed, looked complete, and silently lacked the failure
distribution.

Recorded here because the ledger should not contain only defects. This is the
FL-019 defence catching a real fault in the direction it was built for.
