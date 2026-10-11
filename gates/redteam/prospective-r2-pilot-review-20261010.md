# Prospective R2 pilot results review

Date: 2026-10-10. Disposition: ACCEPTABLE as an INCONCLUSIVE experiment with
expansion HALTED under its frozen integrity rule.

Bounded independent read-only review verified:

- Eight initial/all attempts, no retries, eight PASS recordings, two process
  exits 0, no further-stage launch or passing pilot-gate event.
- All per-attempt checks pass; two paired-image differences exceed the frozen
  grayscale bound 2.5 while paired positions/yaws remain inside their bounds.
- The descriptive primary/secondary categories and contact, time, path and
  rotation totals match the frozen analysis; all 12 listed external evidence
  hashes match current files.
- All failed pairs remain recorded, 24 planned further attempts are explicitly
  NOT RUN, and no efficacy, recovery confirmation or safety improvement is claimed.
- Immutable scorer stage label PILOT_ONLY accompanies integrity_ok=false; it is
  not a positive result. Overall experiment interpretation is INCONCLUSIVE.

The source and targeted recorded provenance support a state/history-carryover
hypothesis, not a cause determination. Reuse of one simulation across routes and
matching root XY/yaw/local-camera transform do not exclude differences in joint
state, root/world-camera height or pitch, simulation/render history. No settling
contacts were recorded. No definite camera-pitch or illumination cause is claimed.

Next justified decision, requiring a separate reviewed version: a small mechanism
diagnostic on already observed pilot starts (one failing and one passing), using
identical scripted conditioning, fresh-process/full-state reset versus current
root teleport, with full root/world-camera pose, joint positions/velocities,
timestamps and stationary image differences. No learned-policy scoring or
unrun prospective-start preview. That diagnostic was NOT RUN. It cannot restore
this failed pilot as a valid efficacy comparison or justify relaxing its bounds.

No additional collection, threshold change or protocol repair is justified within
this version. Final software validation is recorded in the result report: ruff and mypy pass,
full pytest still fails exactly the three documented environment-identity cases.
All evidence remains external and no push is authorised.
