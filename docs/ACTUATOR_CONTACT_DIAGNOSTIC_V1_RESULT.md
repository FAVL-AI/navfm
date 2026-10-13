# Grounded versus unloaded actuator/contact result

Source freeze: `159053cfe1c3834cb5a63c3e7497b7a92b2e0ae5`. Both authorized workers completed once, without retry. Diagnostic execution integrity passed; this is not motion qualification. Navigation remains blocked.

Each arm retained 960 ticks, 840 valid native readings and 4800 correctly ordered telemetry phase records. Every requested target exactly matched its accepted target; all four DOF names, finite arrays and pre/post-step clocks were checked. Eleven rigid-link gravity readbacks were false in grounded and true in airborne; original solver settings remained 32/1, TGS, 120 Hz. The initially unapplied gravity schema was recorded before explicit authoring. Grounded and airborne lifecycle spans were 26.394 and 21.890 seconds, within their separate 120-second watchdogs.

Airborne minimum geometric clearance was 0.298721 m. All 960 immediate contact queries completed with no robot contact headers or points. Grounded retained 3788 headers and points (4 found, 3784 persisted); these are floor support observations, not collision-safety outcomes. Raw vector impulses remain N s, not instantaneous force. Both actuation-command and solver-projected DOF effort channels were observed; neither is labelled pure motor-drive torque or a measured effective friction coefficient.

The table uses each complete 60-tick target window. Half-differential is (right-wheel mean minus left-wheel mean)/2; rates are rad/s. Body velocity/yaw are passive evaluation measurements. Per-DOF errors retain [front-left, front-right, rear-left, rear-right] ordering.

| Condition | Target (v,w) | Accepted half-differential | Realized half-differential | Per-DOF mean absolute error | Body v (m/s) | Body yaw (rad/s) |
|---|---|---:|---:|---|---:|---:|
| Grounded | (.05,+.005) | +.020313 | −.008870 | [.028131,.030401,.028531,.030618] | +.049697 | −.000229 |
| Grounded | (0,−.4) | −1.625000 | −1.557281 | [.284782,.024403,.008501,.013293] | +.027457 | −.266847 |
| Grounded | (.05,−.005) | −.020313 | +.010714 | [.034817,.027088,.040387,.026967] | +.049976 | +.000115 |
| Grounded | (0,+.4) | +1.625000 | +1.584188 | [.208815,.017961,.033556,.015475] | −.027763 | +.293454 |
| Airborne | (0,+.4) | +1.625000 | +1.624999 | all approximately .000001 | approximately 0 | approximately 0 |
| Airborne | (.05,−.005) | −.020313 | −.020313 | all approximately .000001 | +.001252 | approximately 0 |
| Airborne | (0,−.4) | −1.625000 | −1.624999 | all approximately .000001 | +.000024 | approximately 0 |
| Airborne | (.05,+.005) | +.020313 | +.020313 | all approximately .000001 | +.001276 | approximately 0 |

Pure-spin per-DOF errors are asymmetric: front-left full-window mean absolute errors are .284782 and .208815 rad/s. Aggregate half-differential agreement therefore does not establish complete wheel tracking.

The fixed final 30 ticks preserve the grounded small-turn reversal: realized differentials −.009087 and +.009278 against accepted +.020313 and −.020313. Grounded pure-spin final-half differentials are −1.526058 and +1.589208, with translation +.032096 and −.026193 m/s. Every airborne final-half per-DOF mean absolute rate error remains below .000001 rad/s. Full and final-half per-DOF RMS/max errors, common-mode rates, signed body integrals and complete pretarget residual states are retained in the external reduction.

Grounded full-window sums of contact impulse magnitudes were 23.058352, 23.058267, 23.058363 and 23.058473 N s in target order; airborne had no observed contact impulse records. These sums are not instantaneous forces. The applied-effort command channel was zero in both arms, which does not mean zero drive torque. Grounded solver-projected joint-effort means were [−.007120,+.016932,−.008297,+.018451], [+.227400,−.230614,+.063667,−.047037], [+.017547,−.008345,+.017470,−.006119], and [−.213196,+.249872,−.071342,+.030659] N m. Airborne corresponding mean magnitudes were below .000577 N m. The measured channels do not separate motor, contact and internal reaction contributions.

Grounded pretarget maximum absolute wheel rates were .011666, .000882, .001339 and .002937 rad/s; airborne values were zero or below 1.6e−11 rad/s. Full pretarget body/root state and full/final-half effort/contact reductions are retained rather than assuming exact rest or identical histories.

These observations reject a universal target-sign inversion or failure to deliver wheel targets as the explanation of these cells. The grounded reversal remains with PI bypassed, so PI feedback or inherited integral alone is insufficient. Unloaded wheels closely realize the fixed targets, while the grounded condition has different wheel/body response. This localizes the discrepancy to the loaded configuration or its interaction with drive/articulation/contact dynamics; it does not uniquely identify friction, solver convergence, drive effort, roller geometry or a corrective parameter.

One fresh initialization occurred per arm. Cells were bounded rest-starts, not identical mechanical resets; pretarget residuals remain recorded. Removing gravity and floor support together, grounded-first process order and reversed cell order are confounded. There is one observation per cell and no significance or isolated contact-effect estimate. Unloaded body motion is not supposed to satisfy grounded navigation criteria. Original failed qualifications and all navigation NOTRUN records are unchanged.

The existing asset is a provisional box/cylinder approximation with no roller joints; the active builder replaces wheel contact with spheres. This mismatch independently motivates a contact-representation candidate, but does not prove that it will repair the observed failure. The [official M3 Pro specification](https://category.yahboom.net/collections/ros-series/products/rosmaster-m3-pro) confirms 80 mm mecanum wheels and rear-wheel pendulum suspension; neither the targeted specification check nor the local asset authenticates roller count/profile, radius/axis placement, rolling resistance or friction. A physically authenticated replacement cannot be instantiated from those missing values. No geometry or friction parameters are invented.

No corrective implementation is selected from this result, and no further runtime was performed. The next engineering decision must specify an independently justified loaded-plant correction or a discriminating measurement; any eventual candidate must pass the unchanged original 16-command qualification before matched ViNT evaluation.

Evidence is external at `/home/favl/navfm-runtime-evidence/actuator-contact-diagnostic-v1-01`; reduction at `/home/favl/navfm-runtime-evidence/actuator-contact-diagnostic-v1-analysis-01`. All consumed ledger artifact hashes were verified, including both lifecycle traces and native/report/process records.

| Evidence | SHA256 |
|---|---|
| Acquisition ledger | `00b5d6dd4a9e089726c1efd7561c255306d876d230b3c566b7ca141277c52ace` |
| Grounded report | `a79e2aa79bc47b95f81c6723a0920af96ed35a4281b2a31d0fdbdc020c64be06` |
| Airborne report | `4a00c2a21f6c0ed31b3bac6d8305a1ec1fc236be6585e575dfe36dfd52eca1b6` |
| Contact/effort/onset reduction | `59aa3d79a1744effb37d0bc9d6e8da175e4c1af69014d88da571df83f8b743e1` |
| Fixed reduction | `4d906924b3ef8e2a2a7ab5397bec079281fd339ba5da97e62cd9d3be3ec41c70` |

Validation: six focused controls, Ruff and source/input freeze preflight passed. The initial ambient ROS plugin invocation failed before test collection; the clean plugin-disabled invocation passed. No raw evidence, weights or generated outputs are committed.
