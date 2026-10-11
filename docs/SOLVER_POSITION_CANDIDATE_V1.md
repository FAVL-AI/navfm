# Single-factor solver-position candidate v1

REVIEWED SOURCE FREEZE, runtime NOTRUN. One prospective numerical-convergence discriminator, not an identified physical repair. Commit exact source/config before one runtime attempt. All old assets, source freezes, failed reports and recovered descriptive scores remain immutable.

The saved telemetry shows exact target delivery, near-exact native/pre-control body-rate association, and opposite small realized wheel differentials even in isolated direct rest-start cells. Inherited integral alone is insufficient; geometry/contact and drive/constraint coupling remain alternatives. No unique corrective factor has been established.

Targeted CPU USD inspection found articulation position iterations 32 and velocity 1, scene TGS, unbounded wheel maximum velocity, enabledSelfCollisions=false and wheel-joint collisionEnabled=false. Base_link origin Z=0.0399999991 m and the runtime base-box bottom Z=0.0399999991 m lie 40 mm above sphere bottoms near 0; base COM world Z=0.0799999991 m. Wheel-centre separations are at least0.155 m versus0.08 m sphere diameter. Wheel/base overlap is within filtered parent-child pairs. No concrete chassis-floor or wheel-wheel overlap defect was found. These are static resolved asset/proxy calculations, not a new physics observation.

Version-matched [Omni Physics 107.3 simulation control](https://docs.omniverse.nvidia.com/kit/docs/omni_physics/107.3/dev_guide/simulation_control/simulation_control.html) describes iterative constraint convergence and recommends about one velocity iteration for TGS. [PhysX 5.3 articulation documentation](https://nvidia-omniverse.github.io/PhysX/physx/5.3.0/docs/Articulations.html) describes implicit end-step joint drives and different units for acceleration/force drive gains. Changing acceleration to force at unchanged numeric damping 1000 is therefore not an unchanged-gain correction. A position-count increase is a bounded convergence intervention;32 already is substantial and no success is presumed.

Only the robot articulation's requested position count changes 32→64 before physics initialization. Velocity1, TGS, 120 Hz timestep, all gains/limits, sphere/contact geometry, material defaults, mapping, native read, reset/readiness procedure, original 16 ordered command tuples, warmup 120, sixteen 60-tick holds and stopped tail 120 remain unchanged. No new sample metadata enters the numeric report. Passive telemetry retains one native read and five ordered phases each tick. Actual scene min/max clamps must admit 64/1; before/after counts, solver and timestep are recorded. Count getters/readback are USD attributes, not independently observed native solver iteration telemetry. The scene/property/API source identities are pinned.

One process, 120-second watchdog,1200 ticks/10 simulated seconds; fresh external `/home/favl/navfm-runtime-evidence/solver-position-candidate-v1-01`. No model, camera policy, navigation or training. Preserve every partial artifact on failure. The exact original `score_command` criteria and stopping/sensor checks apply to all 16 holds. No threshold, best-window or iteration search. FAIL stops this candidate without automatic 128/force/friction/gain alternatives. PASS is sampled qualification on this known engineering fixture, not a unique causal explanation; a fresh reproduction is required before a versioned fair ViNT evaluation can be admitted. Navigation is not launched automatically by this script.

Five focused controls validate one pre-initialize insertion, unchanged 16-command schedule, missing/duplicate boundary rejection, exact single property write and pre-write scene-clamp rejection and actual helper invocation inside the separate preserved setup execution namespace. Lint/diff checks apply to the intended new files. Raw evidence remains external; no robot is accessed.

After accepted review and clean source commit:

```sh
env -u PYTHONPATH /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/run_solver_position_candidate_v1.py --freeze EXACT_COMMITTED_HEAD --out /home/favl/navfm-runtime-evidence/solver-position-candidate-v1-01
```
