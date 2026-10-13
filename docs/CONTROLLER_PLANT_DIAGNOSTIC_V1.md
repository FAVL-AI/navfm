# Controller/plant diagnosis v1 — reviewed source freeze, NOTRUN

Branch: agent/research-three-model-plan. Goal: distinguish inherited integral contribution, prescribed differential delivery and realized wheel/body response under a bounded diagnostic. Existing source freezes, authentic robot asset and all failure records remain immutable; no navigation admission follows this diagnostic. Only authored source/config/protocol/tests/population are committed; all runtime records stay external.

## Static evidence

The authentic robot asset SHA256 remains 0ba6ca5df86d2b8d7d631a25be1eeb57b66c28516e599a02486a14233971cb1b. CPU-only USD inspection used the installed pinned runtime's USD extension and required library paths; it did not create SimulationApp. An initial import lacked pxr, followed by missing USD/Python libraries; explicit installed paths enabled read-only decoding, without package installation.

All four wheel joints have +Y axes, identity local joint rotations and wheel orientations, body0 base/body1 wheel, and names fl/fr/rl/rr consistent with recorded indices 0/1/2/3. Wheel centres are x=±0.0775, y=±0.085 m. Base mass is approximately 1.8 kg with authored inertia (0.009,0.014,0.021); each wheel is approximately 0.15 kg with authored inertia (0.000094,0.000173,0.000094). The wheel centre-of-mass attribute has the schema's unset sentinel, not a measured invalid mass. Native computed inertia is not inferred from authored values.

The runtime builder disables original collision subtrees and creates four radius-0.04 m spheres. It does not instantiate mecanum rollers. The mapping's 0.1625 lever equals 0.0775+0.085, but this does not authenticate no-slip yaw for sphere contacts. Asset drives (stiffness625/damping≈0.1) are overridden to stiffness0/damping1000 and acceleration type; max force remains the large authored bound. Friction=-1 installs no explicit material; effective solver friction is UNKNOWN, not zero. The probe records actual stage drive and material-binding attributes; unbound/default contact coefficients stay explicitly unknown. These findings support neither a universal sign inversion nor a unique correction.

Saved telemetry establishes exact requested/accepted API targets, no observed clipping, and small-turn cases with opposite realized differential/body yaw. An almost-zero inherited integral in segment2 already argues against inherited integral as the sole explanation. Recorded gyro content agrees with pre-control body-rate evaluation despite its older sensor timestamp. No IMU, gain or timestamp change is selected.

## Finite process and modes

ONE fresh process, 120-second wall watchdog, 3120 physics ticks (26 simulation seconds): startup120, twelve cells of rest120+conditioning-or-zero-hold60+target60, tail120. The earlier 1200-tick telemetry worker entry-to-last-phase interval was 23.854590 seconds; the new cap is plausible, not guaranteed, and will not be increased after a timeout. Partial artifacts are preserved and hashed.

The eight reset/carry cells use the SAME closed-loop PI prescription during opposite-sign ±0.4 rad/s conditioning with target forward speed; only their integral state branches at target onset. The four direct cells replace the 60 conditioning ticks with additional zero-wheel holding to provide rest-start downstream plant baselines. Their fixed final rest tick (offset179) is checked/logged with the same residual limits before target onset. Thus direct versus conditioned cells changes antecedent AND controller mode and is not a clean PI-effect contrast. No full physical-pose reset or identical contact history is claimed.

Target modes:

- reset: reset integral only immediately before target, then unchanged PI updates;
- carry: unchanged PI including inherited integral;
- direct: prescribed w_out=w_command during target only; native reading still validated once, but PI output/derived clipping is NOT APPLICABLE. This is a downstream diagnostic and never a deployment repair.

Targets: moving (0.05,±0.005) and pure spin (0,±0.4), each once per mode. Exact balanced order is the config's twelve IDs and the source TRIALS array: reset moving+, carry spin−, direct moving−, reset spin+, carry moving−, direct spin+, reset moving−, carry spin+, direct moving+, reset spin−, carry moving+, direct spin−. No substitutions or repeats.

The zero-wheel rest necessarily changes mechanical/contact history as well as resetting PI; nominal scripted conditioning for reset/carry does not guarantee identical mechanical antecedents across sequential cells. At the final fixed rest tick, existing residual limits |v|≤0.01 m/s and |w|≤0.03 rad/s plus integral=0 are checked for technical readiness. Joint residuals are recorded, not forced to match. No teleport, geometry/friction/gain change or extra native poll occurs between cells. Target onset records integral before/after explicit reset, pretarget body/joint state and clocks; first and subsequent post-update integral values follow in telemetry.

All old telemetry is retained: ordered pre-control/post-control/requested/immediate-accepted/post-physics events with DOF bindings, native clocks and evaluation-only body quantities. New stage readbacks and every contact record remain external. Invalid source/schema/nonfinite/readiness or watchdog failure halts remaining cells. Intact scientific tracking failures do not halt the declared twelve cells.

Each target is scored using the unchanged full60 and last30 coverage criteria, without best windows. A target-onset reset that still fails shows inherited integral alone is insufficient; it does not show PI state is irrelevant, because new integral accumulates during target. Direct mode's response separates prescribed targets from PI requests but does not isolate friction/torque/contact parameters. One observation per cell is not an efficacy or significance study. This diagnostic cannot replace the original short-hold qualification or unlock navigation. No intervention is selected before results.

Prepared command after reviewed clean source freeze:

```
env -u PYTHONPATH /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/run_controller_plant_diagnostic_v1.py --freeze <exact-commit> --out /home/favl/navfm-runtime-evidence/controller-plant-diagnostic-v1-01
```

## Declared deployment contract

The user's deployment target is a Yahboom ROSMASTER M3Pro with Jetson Orin NX 16GB; RTX 4080 SUPER is the simulation/collection/training workstation. Front RGB supplies learned-policy observations; IMU and wheel feedback are explicit low-level controller sensors. This is user-declared hardware identity, not a verified connected robot. JetPack/software versions, wheel configuration/calibration, sensor mounts, units/signs and measured deployment latency remain UNKNOWN and require validation before sim-to-real deployment. No robot access or actuation is authorized or performed here. Hardware specifications are not an explanation for this simulation failure.

Validation: four focused controls PASS, Ruff and diff checks PASS; all prior population nodes retained. The reviewed packet preserves every older source and asset byte. Results remain unavailable before the one launch.
