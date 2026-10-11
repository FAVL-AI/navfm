# F-TWIN-1 — box collider extents are squared in the Yahboom M3 PRO digital twin

**Found** 2026-09-07, during the second Hospital G2 obstacle-map integrity pass.
**Not** found by the builder that produced the asset, which counted colliders
without measuring any of them.

## Observation

`assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd`
(sha256 `0ba6ca5df86d2b8d7d631a25be1eeb57b66c28516e599a02486a14233971cb1b`)
loaded into Isaac Sim 5.1.0.0. World-space AABBs of the eight collision prims,
compared against `yahboom_m3pro.urdf`:

| link | URDF box | loaded AABB | square of URDF value |
|---|---|---|---|
| `base_link` | 0.290 × 0.235 × 0.080 | xy 0.0841000037, h 0.0064000410 | 0.290² = 0.0841, 0.080² = 0.0064 |
| `camera_link` | 0.025 × 0.090 × 0.025 | xy 0.0081000010, h 0.0006250035 | 0.090² = 0.0081, 0.025² = 0.000625 |

Agreement to eight significant figures on four independent quantities.

**Box collider extents are squared. Cylinder colliders are correct.** The four
wheels (r = 0.040 → z-span 0.080), the lidar (`[0.152, 0.192]`) and the top arm
(`[0.120, 0.280]`) all match the URDF exactly. Link *centres* are also correct —
`base_link` at z = 0.080000, `camera_link` at z = 0.280000 — so the transform and
joint chain are sound. Only box half-extent authoring is wrong.

Every box dimension in this URDF is below 1 m, so squaring **shrinks** the
collider. The failure is silent: nothing crashes, no census notices, and the
robot simply has a chassis 84 × 55 × 6.4 mm instead of 290 × 235 × 80 mm.

## Cause

`scripts/build_yahboom_twin.py:83` imports via Isaac's own
`URDFParseAndImportFile` with `distance_scale = 1.0`. The squaring happens
inside that importer, consistent with a size attribute and a scale carrying the
same value and being applied twice. Re-running the builder unchanged reproduces
the defect; this is not repaired by regenerating the asset.

## Why the builder missed it

`build_yahboom_twin.py` records a `physics_census` counting rigid bodies,
colliders, joints, articulation roots and meshes. Its comment says "count what
actually exists, rather than asserting it" — but counting is not measuring. A
collider of the wrong size is still one collider. This is the F-M2-1 genus
again: a check that cannot fail for the defect in front of it.

**Invariant to add:** an asset builder must assert collider *dimensions* against
its source, not merely their count.

## Impact, stated precisely

**On the G2 verdict: none.** G2 was adjudicated with a chassis underside of
0.0768 m instead of the correct 0.040 m. The defect makes the test *more*
permissive in z, so it could only hide a hazard between 0.040 and 0.0768 m.
The complete census contains zero candidates in `(0.0254, 0.10]` — the tallest
planner-invisible mesh in the scene is 0.0254 m. Every chassis underside in
that whole interval yields zero hazards, and the correct 0.040 m lies inside it.
The verdict is invariant to the defect, with a 0.0146 m margin.

**On route feasibility: none.** The defect makes the simulated robot smaller,
never larger, so it cannot cause the planner to accept a route the true robot
could not traverse. The planner inflates by `footprint_radius = 0.24 m` and
enforces `min_clearance_m = 0.35`, against a true circumscribed chassis radius
of 0.1866 m — a margin of +0.0534 m.

**On contact fidelity: real.** Any claim about physical contact, wedging,
brushing past geometry, or chassis strike is not supported by this asset. Those
are not claimed by the G2 result and must not be claimed by later work until the
asset is repaired.

## Status

`OPEN — RECORDED, NOT REPAIRED.` The repair belongs to an asset tranche, not to
a scene-measurement tranche. It does not gate BO-10 route collection for the
reasons above, and it does gate any contact-physics claim.

Physical M3 PRO geometry remains `NOT_MEASURED` and is a separate requirement
for sim-to-real validation. Wheel diameter is not ground clearance.
