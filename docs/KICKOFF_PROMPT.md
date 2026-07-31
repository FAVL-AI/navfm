# Kickoff prompt for Claude Code

Paste the block below into Claude Code, started in the repo root, on the
workstation. It assumes `CLAUDE.md` is present (Claude Code reads it
automatically — the standing rules live there so this prompt stays short and
re-usable). Run milestones one session each; don't ask for all four at once.

---

## Session 1 — M1: close the runs-to-tables path

```
Read CLAUDE.md, then docs/WORKFLOW.md Phase 0 and docs/REPRODUCTION.md.

Milestone M1 — implement the three missing entrypoints so the pipeline is
closed from training to paper tables. Plan first, then implement in small
commits.

1. src/navfm/eval/offline.py
   CLI: python -m navfm.eval.offline --model {vint,gnm} --checkpoint PATH
        --dataset NAME --split {train,test} --batch-size 400 [--limit-batches N]
   - Build the model from the upstream classes (vint_train.models.*) using the
     shipped config geometry; load weights via navfm.models.loader.load_into
     (trust_checkpoint gated, mismatch summary printed).
   - Iterate the upstream ViNT_Dataset over the named split; compute the
     reference metrics via navfm.eval.metrics in BOTH strict and plain
     reductions, plus ADE/FDE converted to metres via the dataset's
     metric_waypoint_spacing.
   - Write runs/eval_<model>_<dataset>_<split>_<timestamp>/{metrics.json,
     config.json, git_sha.txt}. Print a one-screen summary.
   - Unit-test the metric plumbing with a synthetic dataset (no GPU needed);
     mark GPU-path tests with @pytest.mark.torch.

2. src/navfm/train/run.py
   CLI: python -m navfm.train.run --config configs/train/vint_finetune_4080s.yaml
   - Use FinetuneConfig + set_seed + apply_freeze + freeze_batchnorm +
     build_optimizer + build_scheduler + amp_context from navfm.train.finetune.
   - Gradient accumulation to effective_batch_size; loss identical to the
     reference: alpha*1e-2*dist_loss + (1-alpha)*action_reduce(action_mse)
     with alpha=0.5 (see docs/METHODOLOGY.md §1.4/§2.3 — do not invent a
     different weighting).
   - Replay mixing: sample replay_ratio of each batch from replay_datasets.
   - Per-epoch: eval via the same code path as offline.py; save
     runs/<run_name>/{epoch_N.pth,latest.pth,config.json,git_sha.txt,
     metrics_epoch_N.json}. Resumable from latest.pth.
   - Include a --overfit-n N flag (train on N trajectories) for gate G3.c.

3. scripts/make_tables.py
   Read every runs/*/metrics*.json, group by experiment cell (cell id comes
   from the run_name convention e2_<demo>_<exec>_seed<k> etc. — define and
   document the convention in the script docstring), emit markdown tables
   with bootstrap CIs via navfm.eval.metrics.bootstrap_ci into
   paper/tables/*.md. Fail loudly on missing seeds rather than averaging
   what's there.

Definition of done: make verify green; the upstream-compat suite green;
offline.py runs end-to-end on a synthetic GNM-format dataset on CPU;
train/run.py completes 2 epochs on that synthetic set on CPU (tiny batch);
all committed under the authorship rule with gate-style evidence in the
commit messages.
```

## Session 2 — M2: Phase 0 gates on this machine

```
Read docs/WORKFLOW.md Phase 0. Execute it: build ~/.venv-train, clone and
patch upstream (archive the patch diff to gates/G0/patch.diff), download the
three checkpoints and record SHA-256 to gates/G0/SHA256SUMS, fetch GO Stanford
from huggingface.co/datasets/franciszzj/GoStanford2, validate and split it,
then run:

  python -m navfm.eval.offline --model vint --checkpoint checkpoints/vint.pth \
      --dataset go_stanford --split test --batch-size 400

Archive stdout to gates/G0/e02_reproduction.txt. This number is gate G0.c and
goes into paper/draft.md Table 3 via make_tables only. If anything in the
dependency stack fails, consult docs/REPRODUCTION.md's known-issue index
before improvising, and record any new failure + fix as an addendum there.
```

## Session 3 — M3: Isaac Sim 5.1 smoke (the code's first real contact)

```
Read CLAUDE.md (environment facts: Isaac Sim 5.1.0 — the 5.x branch is
primary) and docs/ISAAC_COLLECTION.md.

Write scripts/smoke_isaac.py and make the 5.1 code path actually work:

1. Boot IsaacApp headless at 12 Hz against 5.1: verify the fallback branch in
   navfm/isaac/app.py (_configure_rates → SimulationContext) really holds
   physics_dt == rendering_dt on 5.1, and that step() blocks until the frame
   is rendered. Expect API friction — fix it in the 5.x branch, never by
   upgrading Isaac Sim.
2. Open Simple_Room from the 5.1 asset root; spawn a placeholder robot
   (Jetbot USD or a kinematic cube with a Camera child) since assets/m3pro.usd
   does not exist yet; attach a 640x480 camera (isaacsim.sensors.camera).
3. SYNC CONTRACT TEST, the point of the exercise: teleport the robot to a
   known pose, step once, read rgb+pose; command a fixed velocity for 24
   steps (2 s), assert the pose track matches the commanded integral to <5%,
   and assert the image actually changes frame-to-frame (catch the
   frames-in-flight staleness bug). Save 5 frames to gates/G0/smoke_frames/
   for eyeball audit.
4. Run 20 collector episodes into /data/smoke with the placeholder robot,
   then: python -m navfm.validate /data/smoke --model vint --decode-images -v
   Archive validator output + collection_manifest.json to gates/G2-smoke/.

Anything you must change in navfm/isaac/ to make 5.1 work: keep the 6.0
branch intact, add/adjust tests where testable without Isaac, document the
5.1-specific behaviour in docs/ISAAC_COLLECTION.md, commit with evidence.
```

## Session 4 — M4: robot asset (needs the physical robot + downloads)

```
Read docs/WORKFLOW.md Phase 1 and docs/HARDWARE.md. Inputs I will provide in
this session: the yahboomcar_description package (pulled off the robot or the
Code-Firmware bundle) and my measured values for max_v, max_w, camera
transform, wheelbase/track/mass with their measurement methods.

1. Replace every PROVISIONAL constant in navfm/control.py and
   navfm/isaac/robot.py with the measured values; update the HARDWARE.md
   table with value + instrument + method; single commit titled
   "Replace provisional M3 PRO constants with measured values".
2. Write src/navfm/isaac/urdf_import.py (referenced in robot.py's error
   message but not yet implemented): headless URDF→USD via the 5.1 importer
   (isaacsim.asset.importer.urdf), holonomic/mobile config, convex
   decomposition, and a post-import inertia sanity report comparing URDF
   inertials against uniform-density estimates from the collision geometry —
   flag ratios >10x as the placeholder-inertia signature.
3. Import to assets/m3pro.usd (not committed; record its sha256 in
   gates/G1/). Re-run the smoke script against the real asset; archive gate
   G1 evidence: velocity-tracking <5% over 3 s, camera FOV check (wall at
   1 m subtends what 64° H-FOV predicts ±2°).
```

After M4, Phase 2 (main collection) runs from the existing config:
`python -m navfm.isaac.collect --config configs/collect/m3pro_indoor.yaml
--out /data/isaac_m3pro_A --robot-usd assets/m3pro.usd --episodes 600` —
and the workflow document takes over.
