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

## Deployment software and supervised commands

`src/navfm/deployment/yahboom.py` receives RGB, an acquisition timestamp and goal
RGB. It supplies six 4 Hz observations to ViNT and sends bounded differential
Twist commands to an injected sink. No pose, velocity, collision report, map or
action history is a model input. A 0.2 s acquisition-age limit, nonmonotonic/future
stamp rejection and 0.375 s history-gap limit issue zero commands. The ROS wrapper
adds a 50 ms watchdog timer. These software limits need measured camera/clock
qualification; they are not a formal stopping guarantee. CPU stalls, network loss,
and process failure still require an independently qualified hardware watchdog.

The software-only saved-image check executed with the adapted checkpoint:

```bash
NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-admitted-20261007-02/upstream \
.venv/bin/python scripts/check_yahboom_adapter.py \
  --checkpoint /home/favl/navfm-training-evidence/option1-vint-20261007-04/smoke_weights.pth \
  --images /home/favl/navfm-runtime-evidence/option1-20261007-05/junction_run_0000/trajectory \
  --goal /home/favl/navfm-runtime-evidence/option1-20261007-05/junction_run_0000/goal.png \
  --out /home/favl/navfm-runtime-evidence/yahboom-software-next
```

It strictly loaded the checkpoint, checked 20 replay frames, exact official
preprocessing tensor equality, finite bounded predictions and stale-frame
rejection/zero submission. Its sink was a local list. No ROS transport opened.
The initial missing `max_v` constructor argument failed before model execution;
that attempt and the repaired PASS are retained separately.

Copy `configs/deployment/yahboom_measured_profile.template.json` outside Git and
fill observed calibration/mount/mode/clock/mapping values. Unknown fields remain
null. Record repeated calibration estimates, held-out reprojection residuals,
exposure settings, raw color encoding, monotonic acquisition stamps, camera queue
age, command/response timestamps, wheel signs/order/radius, steady linear/angular
tracking, stopping travel, residual motion and hardware watchdog response. Calibrate
using development routes; preserve untouched real test routes. The current pipeline
uses raw distorted images with official aspect cropping; it does not silently
undistort camera frames. Match this prospectively or introduce and validate the
same transformation in training and deployment.

On the robot, an operator must first verify the command topic, clear the test area,
check the emergency stop and external watchdog, and arrange independent tracking.
**The following are manual supervised commands, not executed in this milestone.**
Replace the topic with the observed hardware interface; SI forward/left conventions
must be measured, not inferred from the topic name.

```bash
# Dry run opens no ROS transport.
python scripts/yahboom_supervised_pulse.py --topic /cmd_vel \
  --v 0.05 --w 0 --seconds 2 --out /tmp/yahboom-forward-dry
# Operator executes after checking the independent stop/watchdog.
python scripts/yahboom_supervised_pulse.py --topic /cmd_vel \
  --v 0.05 --w 0 --seconds 2 --execute-supervised --out /tmp/yahboom-forward-01
python scripts/yahboom_supervised_pulse.py --topic /cmd_vel \
  --v 0 --w 0.2 --seconds 2 --execute-supervised --out /tmp/yahboom-left-01
python scripts/yahboom_supervised_pulse.py --topic /cmd_vel \
  --v 0 --w -0.2 --seconds 2 --execute-supervised --out /tmp/yahboom-right-01
python scripts/yahboom_supervised_pulse.py --topic /cmd_vel \
  --v 0.05 --w 0.2 --seconds 2 --execute-supervised --out /tmp/yahboom-combined-01
```

Each pulse sends explicit zeros on normal completion/failure while its process is
alive. A logged submission is not measured motion; populate the pending external
measurements before qualification. Never count a manually interrupted or missing
trace as PASS. Initially use the simulator absolute tolerances only as an engineering
reference: 0.05 m/s linear and 0.15 rad/s angular tracking error, 0.05 m stopping
travel, residual speed <0.01 m/s and yaw rate <0.03 rad/s after settling. Those are
wide relative to small hardware pulses: predeclare tighter hardware tolerances
using tracking uncertainty and available clearance before calling hardware qualified.

After measured camera/controller and independent watchdog qualification, the operator
may start the RGB wrapper in the ROS environment:

```bash
NAVFM_UPSTREAM=/path/to/pinned/training/snapshot python scripts/run_yahboom_rgb.py \
  --checkpoint /path/to/verified/weights.pth --goal /path/to/real-development-goal.png \
  --calibration /path/to/measured-profile.json --camera-topic /observed/rgb/topic \
  --command-topic /observed/qualified/twist/topic --execute-supervised
```

This command was not run. ROS subscriptions, QoS compatibility, command-topic wiring
and hardware response remain untested; compilation and the RGB adapter replay do not
qualify them. The experimental RGB stopping rule also remains uncalibrated. Do not
use the real test set to choose its thresholds.
