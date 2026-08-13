# Yahboom ROSMASTER M3 Pro digital twin — provenance gate

Run before importing anything, because the question is not "does an asset exist"
but "is this asset a faithful twin". Two artefacts:

* `yahboom_digital_twin_provenance.json` — where the asset came from, what it
  contains, and what may be adopted.
* `yahboom_sim_to_real_calibration_ledger.json` — every physical parameter, and
  whether it is measured, provisional, or in conflict.

## Verdict: the URDF is adoptable. The USD is not.

**The URDF is real and self-contained.** 14,123 bytes, 23 links and joints,
**zero external mesh references** — all geometry is inline boxes and cylinders,
with inertia computed by the box formula and shown in the file. That last point
matters more than it sounds: the asset directory contains **no mesh files at
all** (`asset_report.json`: stl, dae and obj counts are each 0), so an asset that
depended on meshes would be unimportable. This one does not.

**The USD is a placeholder and must not be used.** 3,581 bytes of binary USDC
containing:

```
PhysicsRevoluteJoint  0        Mesh            0
ArticulationRoot      0        RigidBodyAPI    0
                               CollisionAPI    0
```

It cannot articulate, collide, or be driven. And three records in its own
directory agree it was never generated from the URDF:

* `asset_report.json` — `"has_usd": false`, `"generated_usd": null`,
  `"status": "urdf_found"`
* `isaac_import_status.json` — `"status": "already_exists"`

That last string is the one to read carefully. **"Already exists" means the
importer found a file and skipped. It does not mean it converted one.** A
pipeline that reports success on a skip will report success forever.

## The blocking defect: wheel radius

| | |
|---|---|
| URDF | `0.048 m`, commented *"same as X3; verify with calipers"* |
| navfm | 80 mm mecanum wheels → radius `0.040 m` |
| Yahboom X3 URDF | `0.048 m` — identical |
| Discrepancy | **20%** |

The URDF carries the X3 value and says so in its own comment. Nobody smuggled
it in; it was flagged and never resolved.

**Why it blocks recorded trajectories and nothing before them.** Wheel radius is
what converts wheel angular velocity into ground distance. A 20% error scales
every commanded velocity and every odometry-derived displacement by 20% — and
that lands directly in `position`, the label the models learn from. It would not
crash, would not warn, and would corrupt every trajectory identically, so no
internal consistency check would catch it.

It blocks **recording**. It does not block import, articulation, camera
mounting, motion debugging or action-scale work, none of which depend on it.

## Path correction

The requested path
`/home/favl/robotics/FleetSafe-VisualNav-Benchmark/assets/robots/yahboom_m3_pro/`
**does not exist on this workstation.** The asset chain is in
`gnm-vlnverse-baseline`, in two copies. Every internal path inside
`asset_report.json` and `isaac_import_status.json` points at the absent
FleetSafe tree, so none of them resolves — which is consistent with those reports
having been written elsewhere and carried over.

## What this gate does not say

It does not say the twin is wrong. The geometry is plausible, the inertia is
derived rather than guessed, and the structure is importable. It says exactly
one number is known-contaminated, six more have never been measured, and the
mecanum wheels are modelled as plain cylinders — adequate for body-velocity
control, **not** adequate for per-roller slip. That last one deserves attention
before any claim about holonomic execution, because holonomic-versus-differential
execution is the manipulated variable of the project's headline experiment.
