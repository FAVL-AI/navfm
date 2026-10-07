# Yahboom camera/controller and sim-to-real qualification

This is a measurement checklist, not a completed hardware qualification.
No robot commands were sent and no real test recordings were touched.

| Interface | Measurement and evidence | Admission decision |
| --- | --- | --- |
| Camera | Actual device/mode, image size, color order, exposure/gain/white-balance controls; timestamp source and monotonicity | Freeze mode and processing; report unavailable controls explicitly |
| Intrinsics | Repeated checkerboard calibration,fx/fy/cx/cy,distortion and held-out reprojection residuals | Store observed estimates and uncertainty; do not equate requestedFOV with calibration |
| Mount | Measure x/y/z, pitch/roll/yaw and mounting stability | Match simulator mount prospectively; inspect hood/occlusion and motion blur |
| Image pipeline | Apply identical aspect crop, resize and ImageNet normalization to saved simulator and realRGB | Golden-image tensor equality; preserve raw acquisition images |
| History | Six chronological4Hz frames with declared startup handling; acquisition gaps and queue age | Reject/recover dropped or stale input explicitly |
| Commands | Verify motor sign/order, wheel radius/track, ROS units and maxv/maxw | Do not infer turning response from nominal kinematics |
| Motion response | Both forward/reverse and CW/CCW tests at multiple speeds, starts/stops; measure realized displacement/yaw and latency | Simulator wheel and body-velocity angular responses currently unqualified; kinematic teacher is not controller evidence; identify friction/torque/mapping cause |
| Action scaling | Register normalized waypoint unit, selected waypoint, PD gains,4Hz cadence | Same frozen mapping in pretrained/adapted comparison |
| Termination | Native policy stop absent; operator stop/watchdog and experiment termination separately recorded | Correct stopping unavailable until documented stop interface is validated |
| Contacts/safety evaluation | Deliberate low-speed contact/noncontact detector checks in simulation; independent real evaluation observations | Monitor sensitivity, misses and missing data; never feed privileged measurements to deployedRGBpolicy |
| Full-loop timing | Camera timestamp and RGB availability through preprocessing, inference, controller, command submission and robot response | Report p50/p95/max, cold start, dropped deadlines and device clocks separately |

Real development/adaptation collection must be separate from untouched real test
routes. Freeze image goals, starts, obstacles, operator rules, timeout and paired
order before comparing released and adapted checkpoints. Ground truth from
external tracking or simulator state is evaluation/supervision only. The deployed
method receives RGB history and goal RGB; any action-history input added later
must be explicitly included in the claim and ablated.

Start real evaluation only after camera/controller/termination qualification,
with bounded commands and an operator-controlled stop. Retain collisions,
timeouts, interventions, acquisition failures and missing observations. Do not
interpret simulation waypoint error or a six-step training smoke as transfer.
