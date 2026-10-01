# Engineering transition recording v1

An opt-in engineering extension to the existing BO-10 collector. It does not amend
E2, the terminal-approach arms, or historical admission records.

The historical writer embeds metadata and extras in `traj_data.pkl`, despite the
sidecar rule in DATA_CONTRACT.md. Legacy outputs and defaults remain unchanged.
The new `--engineering-step-cap N` path (12..240) uses RecordingTrajectoryWriter:
numbered JPEGs plus **only position/yaw** in the pickle, `metadata.json`, and
`transitions.json` with schema `navfm_transition_recording_v1`.

For result image i, each transition records time and observed pose BEFORE the
command, requested body-frame twist, accepted/clamped twist, and time/pose AFTER
simulation stepping. Image i-1 is the preceding saved observation; the first
command has no preceding saved RGB. No claim of sensor timestamp verification is
made merely from sequential API calls. Commands are provenance, not the waypoint
labels the official loaders derive from observed pose deltas. In kinematic mode,
acceptance means the swept guard admitted a candidate pose and teleport returned;
it does not mean wheel dynamics executed the twist.

The new output root must not exist and must be outside the repository. So must
`--evidence` and the `.milestones` file derived from it: all three are checked by
resolved filesystem ancestry, not by string prefix, so a `..` construction or a
symlinked parent that lands back inside the tree is refused too, while a sibling
directory merely sharing a name prefix is admitted. The check runs before any
directory, evidence file or milestone file is created, so a rejected run leaves
nothing behind. It applies to engineering mode only -- the scientific collector
legitimately writes its evidence inside `gates/`. Recording
termination, motion mode, scope and configuration accompany the images. A separate
supervisor records source hashes, exit/crash evidence and readback. SAVED is not
validation success, training admission or goal completion. Image interpretability,
transition/pose alignment and official loader samples must be checked after capture.

The fixed short cap is an engineering validation limit, not a change to BO-10's
long-horizon adequacy thresholds. Any failed gate stays failed. No scientific
sample counts are incremented. Camera metadata remains nominal unless runtime
attributes substantiate its application; no lens/render setting is changed here.
