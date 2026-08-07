# Execution workflow — from empty machine to submitted paper

This is the operational plan. Every phase has an **entry condition**, an
**exit gate**, the exact commands, a realistic time estimate for one person
with one RTX 4080 SUPER and one M3 PRO, and the failure modes I expect you to
hit, in the order you will hit them.

The single rule that governs everything below: **no phase starts until the
previous phase's gate is green, and every gate is a command whose output you
archive.** The audit trail *is* the research product — a reviewer who can
re-run your gates is a reviewer who believes your tables.

```
Phase 0          Phase 1         Phase 2          Phase 3         Phase 4          Phase 5         Phase 6
ENVIRONMENT ──► ROBOT ASSET ──► COLLECTION ────► FINE-TUNE ────► EXPERIMENT ────► REAL ROBOT ───► PAPER
& BASELINE      (URDF→USD)      (Isaac→GNM)      (ViNT, 16GB)    MATRIX (E1-E5)   (E6)            & ARTEFACT
  ~1 week         ~1 week         ~1-2 weeks       ~3 days         ~2 weeks         ~2 weeks        ~3 weeks
  gate G0          gate G1         gate G2          gate G3         gate G4          gate G5         gate G6
```

Total: **10–12 weeks** wall-clock at focused solo pace. The long poles are
scene diversity (Phase 2) and real-robot trials (Phase 5), not GPU time.

---

## Phase 0 — Environment, checkpoints, and the baseline number (~1 week)

**Purpose.** Prove the *reference* stack works before touching anything of
ours. If you cannot evaluate the released `vint.pth` on a public dataset, no
downstream number means anything.

**Entry:** a workstation with the 4080 SUPER, Ubuntu 22.04 (this is forced:
the M3 PRO is ROS 2 Humble, Isaac Sim supports Humble only on 22.04, and
22.04's GLIBC 2.35 is exactly Isaac Sim 6.0.1's floor).

### Steps

```bash
# 0.1 Two virtualenvs. They never share; they exchange only files.
python3.11 -m venv ~/.venv-train
python3.12 -m venv ~/.venv-isaac

# 0.2 Training env + patched reference repo (docs/REPRODUCTION.md Stage 0)
source ~/.venv-train/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -e ".[train,dev]"
git clone https://github.com/robodhruv/visualnav-transformer.git third_party/visualnav-transformer
python scripts/patch_upstream.py third_party/visualnav-transformer   # archive the printed diff
pip install -e third_party/visualnav-transformer/train
git clone https://github.com/real-stanford/diffusion_policy.git third_party/diffusion_policy
pip install -e third_party/diffusion_policy
pip install "diffusers==0.11.1" "huggingface_hub==0.25.2"

# 0.3 Repo self-test, including the compatibility proof
make verify
NAVFM_UPSTREAM=third_party/visualnav-transformer pytest -q

# 0.4 Checkpoints -- Drive folder 1a9yWR2iooXFAqjQHetz263--4_2FFggg
#     vint.pth (410 MB), gnm.pth (100 MB, rename to taste), nomad.pth (73 MB)
sha256sum checkpoints/*.pth | tee checkpoints/SHA256SUMS      # ← goes in the paper appendix

# 0.5 GO Stanford -- the only dataset already in GNM format
#     huggingface.co/datasets/franciszzj/GoStanford2 (781.7 MB)
python -m navfm.validate /data/go_stanford --model vint --workers 8
python -m navfm.splits   /data/go_stanford --name go_stanford \
    --out third_party/visualnav-transformer/train/vint_train/data/data_splits --group-by none

# 0.6 Isaac Sim env (separate terminal, separate venv)
source ~/.venv-isaac/bin/activate
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
pip install "isaacsim[all,extscache]==6.0.1.0" --extra-index-url https://pypi.nvidia.com
# Local Assets Pack (5 parts, checksum each) -- docs/ISAAC_COLLECTION.md
export ISAACSIM_ASSET_ROOT=~/isaacsim_assets/Assets/Isaac/6.0
```

### Gate G0 — archive all four outputs

| Check | Command | Green means |
|---|---|---|
| G0.a | `make verify` + upstream compat suite | 129 tests pass on your machine, not just mine |
| G0.b | `sha256sum checkpoints/*.pth` | hashes recorded; loads via `navfm.models.loader` with `trust_checkpoint=True` |
| G0.c | **E0.2**: evaluate `vint.pth` on the GO Stanford test split **reconstruction**, batch 400 | a classification under the pre-registered G0.c decision rule. The checkpoint's recorded `avg_total_test_loss = 0.17398` is a provenance anchor, **not** a target: F10 makes the original split unrecoverable, so the reconstruction is not the upstream split and the two quantities are not equivalent. See the G0.c amendment in `PREREGISTRATION.md` |
| G0.d | Isaac Sim opens `simple_room.usd` headless and renders one frame | `isaacsim` CLI runs; assets resolve locally |

**Expected failures, in order:** `HfFolder` import error (pin hub 0.25.2);
torchvision `nms` operator (matched pair); `UnpicklingError` on `vint.pth`
(the patch wasn't applied); LMDB `map_size` failure if `/data` is NFS (move to
local NVMe).

---

## Phase 1 — Robot asset: M3 PRO from CAD to USD (~1 week, mostly not GPU work)

**Purpose.** Replace every PROVISIONAL constant with a measured one, and
produce `assets/m3pro.usd`. This phase is the difference between a sim2real
paper and a simulation essay, and it needs the physical robot on your desk.

### Steps

```
1.1  Pull yahboomcar_description off the robot or the Code-Firmware bundle:
       scp -r <robot>:~/yahboomcar_ws/src/yahboomcar_description assets/src/
     (Pi5/Nano SKUs: it lives inside Docker at /root/yahboomcar_ws/src/)

1.2  Measure, on hardware, in this order of importance:
       a. max_v, max_w  → run Yahboom's own calibrators (~10 min):
            ros2 launch calibration calibrate_linear.launch.py
            ros2 launch calibration calibrate_angular.launch.py
       b. camera transform with the arm in the stowed pose you will lock:
            ros2 run tf2_ros tf2_echo base_link camera_link
       c. wheelbase / track / mass → 3D_Model_File CAD, cross-check with a ruler.
     Record every value with its measurement method in docs/HARDWARE.md —
     that table is going into the paper's appendix verbatim.

1.3  Update the constants and MARK THE COMMIT:
       navfm.control.M3PRO_LIMITS, navfm.isaac.robot.CameraRig, M3PRO
       git commit -m "Replace provisional M3 PRO constants with measured values"

1.4  Fix the URDF inertials against the CAD (vendor URDFs in this segment
     ship placeholders; PhysX will misbehave), then import:
       Isaac Sim → isaacsim.asset.importer.urdf
       Robot Type = Holonomic, Base Type = Mobile, Convex Decomposition colliders
     Save as assets/m3pro.usd. Do NOT model the mecanum rollers — the collector
     drives the articulation root directly (docs/ISAAC_COLLECTION.md explains why).

1.5  Sanity scene: spawn in simple_room, teleport, command 0.2 m/s forward for
     3 s, read pose. Expect 0.6 m ± physics tolerance.
```

### Gate G1

| Check | Green means |
|---|---|
| G1.a | zero PROVISIONAL markers left in `control.py` / `robot.py`; each value has a method note in HARDWARE.md |
| G1.b | `m3pro.usd` spawns, drives, and `SimRobot.pose()` tracks commanded velocity to <5 % over 3 s |
| G1.c | camera frame renders at 640×480 with the measured mount transform; a wall 1 m away subtends the angle the 64° H-FOV predicts (±2°) |

---

## Phase 2 — Data collection at scale (~1–2 weeks)

**Purpose.** The datasets for every arm of the experiment matrix, plus the
scene diversity that makes the transfer claim defensible.

### Steps

```
2.1  SMOKE TEST FIRST — 20 episodes, one scene:
       python -m navfm.isaac.collect --config configs/collect/m3pro_indoor.yaml \
           --out /data/smoke --robot-usd assets/m3pro.usd --episodes 20
       python -m navfm.validate /data/smoke --model vint --decode-images -v
     Gate on: acceptance rate > 70 %, validator PASS, and OPEN TEN IMAGES WITH
     YOUR EYES. The validator cannot see a black frame from a bad warmup or a
     camera staring at the ceiling. Also check collection_manifest.json's
     per-episode reasons — a wall of "stalled" means the physics import is bad.

2.2  Scene expansion. Four stock scenes is a pipeline demo, not a transfer
     claim. Target ≥ 10 distinct environments:
       - the 8 stock USDs (simple_room, office, hospital, 4× warehouse, digital twin)
       - MobilityGen / Infinigen procedural scenes for the rest
     Record each scene's USD hash in the manifest.

2.3  Main collection runs — one output directory PER ARM, identical seeds:
       A. nonholonomic demonstrator  (the default config)     ~600 episodes
       B. holonomic demonstrator     (demonstrator: holonomic) ~600 episodes
       C. randomization-ablation variants of A (E5 arms: none / lighting /
          lighting+materials / full)                           4 × ~150
     At ~30 s/episode wall-clock, A+B ≈ 10 GPU-hours; the ablations ≈ 5 more.
     Run overnight; the collector is crash-safe (atomic writes) so a resume
     just continues into the same directory with a higher episode offset.

2.4  Derive the constants and register:
       python -m navfm.stats /data/isaac_m3pro_A --name isaac_m3pro --len-traj-pred 5 --context-size 5
       python scripts/register_dataset.py third_party/visualnav-transformer \
           --name isaac_m3pro --spacing <derived> --camera-height <measured> \
           --camera-x-offset <measured> --hfov 64
       python -m navfm.splits /data/isaac_m3pro_A --name isaac_m3pro \
           --out .../data_splits --group-by scene
     KEEP the stats JSON — the clipped-fraction number and lateral-energy
     ratio are Table 2 of the paper.
```

### Gate G2

| Check | Green means |
|---|---|
| G2.a | ≥ 500 accepted episodes per arm, acceptance ≥ 70 %, `navfm.validate --decode-images` PASS on every directory |
| G2.b | scene-grouped split has ≥ 2 held-out scenes; split files committed |
| G2.c | derived `metric_waypoint_spacing` has cross-trajectory sd < 15 % of its mean (a bigger spread means the demonstrator speed is inconsistent and the normalisation is mushy) |
| G2.d | lateral-energy ratio: arm A ≈ ≤ 0.15, arm B substantially higher — this *is* the manipulated variable of H2; if the arms don't separate here, the experiment is dead before training |
| G2.e | eyeball audit: 10 random images per scene, logged as a contact sheet |

### Supervisor-authorised two-trajectory compatibility pilot

Prof. Bo approved a small pilot to collect a couple of trajectories in order to
demonstrate that newly collected data are compatible with the agreed ViNT
processed format.

This pilot is a narrow exception to the normal G2 collection block.

The exception permits collection of no more than two diagnostic trajectories
before G1 and G2 are otherwise complete.

The purpose is only to test data-format compatibility.

A simple Isaac Sim proxy robot may be used because this pilot does not test
robot dynamics, robot geometry or navigation performance.

The pilot does not satisfy G1 or G2.

The collected trajectories are not admitted for model training, validation,
benchmarking or performance claims.

Each trajectory must be converted into the agreed Option 1 format containing
numbered RGB images and a `traj_data.pkl` file with numerical `position` and
`yaw` arrays.

The pilot is successful only if both trajectories pass the project validation
checks and can be read by the unchanged ViNT data path.

Any failure must be reported as Blocked with the reason recorded. The data must
not be modified merely to make the compatibility test pass.

No additional collection may begin until the two examples have been reviewed and
the next step has been agreed.

**Scope boundary, stated explicitly so the record cannot be misread later.** The
cube proxy is acceptable only for this pilot. It does not satisfy G1, does not
validate the M3 PRO model, does not open general data collection, and the
resulting trajectories are not admitted for training or evaluation.

---

## Phase 3 — Fine-tuning bring-up (~3 days)

**Purpose.** One trustworthy training run before the matrix. Not results —
*calibration*: wall-clock per epoch, VRAM headroom, loss-curve shape.

```
3.1  python -m navfm.train.run --config configs/train/vint_finetune_4080s.yaml
     (the driver exists as of milestone M1 and has been exercised end-to-end on
      CPU against synthetic data — see gates/M1/. It has never seen a GPU, a
      released checkpoint or a real corpus, so treat the first launch as
      bring-up: --overfit-n first, then one full run.)

3.2  Watch epoch 1 like a hawk:
       - val loss RISING in epoch 1 → BatchNorm drift → confirm freeze_bn took
       - loss flat at a high floor → action labels wrong → STOP, re-run the
         upstream-compat test against the actual collected data
       - NaN → check for un-unwrapped yaw that slipped past (it can't, but check)

3.3  Confirm the memory model: micro-batch 64 should sit ≈ 3-4 GB of
     activations + ~1 GB fixed. If you have > 8 GB headroom, raise
     micro_batch_size to 128 and halve accumulation — same maths, faster.

3.4  Overfit check: train on 10 trajectories only; the model must drive train
     loss near zero. If it can't, the pipeline (not the model) is broken.
```

### Gate G3

| Check | Green means |
|---|---|
| G3.a | 20-epoch run completes; monotone-ish val loss; checkpoint + `config.json` + git SHA archived under `runs/` |
| G3.b | offline eval of the fine-tuned model beats zero-shot `vint.pth` on the held-out Isaac scenes on ADE (in metres) and multi-action cosine |
| G3.c | the 10-trajectory overfit run reaches near-zero train loss |

---

## Phase 4 — The experiment matrix (~2 weeks, mostly unattended GPU time)

Run `docs/EXPERIMENTS.md` E1–E5 exactly as pre-registered. Discipline items:

```
4.1  Freeze the protocol FIRST: commit a PREREGISTRATION.md that fixes N per
     cell, seeds (3 per cell), scenes, metrics, and the H2 prediction ordering
     BEFORE looking at any closed-loop number. This is what "audited" means —
     the commit timestamp proves the hypotheses predate the results.

4.2  E1 zero-shot baselines + oracle + random-waypoint floor.  (~1 day)
4.3  E2 the 2×2 (demonstrator × execution).                    (~4 fine-tunes + eval)
4.4  E3 data-efficiency curve {0, .25, 1, 4, 16} h × {pretrained, scratch}
        × {replay, no-replay}.                                 (~20 runs, the bulk)
4.5  E4 normalisation-constants ablation.                      (~3 runs)
4.6  E5 randomisation ablation (evaluate in sim now; the real-robot column
        lands in Phase 5).
4.7  Every closed-loop cell: ≥ 30 episodes, bootstrap CIs, identical
     scenario seeds across arms. Every offline number: batch 400, stated.
```

At 1–2 h per fine-tune, the ~30 runs of E2–E5 are ≈ 40–60 GPU-hours —
comfortably two weeks of nights on one card.

### Gate G4

| Check | Green means |
|---|---|
| G4.a | every cell has 3 seeds, CIs, and a `runs/<cell>/` directory containing config, git SHA, dataset hash, and raw episode logs |
| G4.b | oracle ≫ best model ≫ random floor (if the oracle isn't near-perfect, the eval harness is broken, not the models) |
| G4.c | results tables auto-generated from the logs by script, not hand-typed |

---

## Phase 5 — Real-robot transfer, E6 (~2 weeks)

The gate on publishability. Everything before this is simulation talking to
itself.

```
5.1  Deployment stack: RobotecAI/visualnav-transformer-ros2 (Humble profile)
     on the robot's SBC; model export to the format its loader expects.
     Verify the 4 Hz policy loop holds on the Orin/Pi — if inference is slow,
     drop to 2 Hz on BOTH the baseline and fine-tuned arms (never just one).
5.2  Camera bring-up at 640×480@15, 4:3 mode, arm locked in the stowed pose
     measured in Phase 1. Confirm with tf2_echo that the transform matches.
5.3  Three environments NOT resembling the Isaac scenes. ≥ 20 episodes each,
     per arm: zero-shot ViNT vs best E2/E3 arm. Use the dual T-mini LiDARs to
     log ground truth for collision counting and SPL (this is what they're for).
5.4  Intervention protocol written BEFORE trials: what counts as a collision,
     when the human takes over, how displacement-before-intervention is read.
     One page, committed, followed.
5.5  Film everything. Reviewers of robot papers watch the video first.
```

### Gate G5

| Check | Green means |
|---|---|
| G5.a | ≥ 120 physical episodes logged with rosbags archived |
| G5.b | the E6 table exists with CIs, whatever it says — a negative transfer result with this audit trail is still a publishable finding |
| G5.c | supplementary video cut |

---

## Phase 6 — Paper and artefact (~3 weeks)

```
6.1  paper/draft.md is already structured with every result slot tied to a
     matrix cell — filling it is transcription, not writing.
6.2  Artefact release: repo (public), dataset (HF, with the GO Stanford
     CC BY-NC-SA caveat respected — your OWN data can be permissive),
     checkpoint hashes, upstream patch set, scene USDs or their generators.
6.3  Internal red-team pass: re-run every gate command from a fresh clone on a
     second machine. What fails goes in the reproducibility appendix as a
     known caveat, not a surprise for reviewers.
6.4  Target: CoRL (deadline typically ~June) or ICRA (~September). RA-L any
     time as the fallback with the same material.
```

### Gate G6 — submission checklist

Every number traces to a `runs/` directory · every gate output archived ·
PREREGISTRATION.md timestamp predates all E-results · artefact tested from
fresh clone · limitations section contains the rolling-shutter, locked-arm,
scene-count, and ground-truth-odometry caveats *before* a reviewer finds them.

---

## Risk register (ordered by expected pain)

| # | Risk | Likelihood | Mitigation already in place | Residual action |
|---|---|---|---|---|
| R1 | Isaac→real appearance gap swamps everything; fine-tuned model no better on hardware | Med | domain randomisation (E5 measures it); DCW2-matched intrinsics; 4:3 discipline | if E6 is negative, the paper pivots to *quantifying* the gap — the audit trail makes that publishable |
| R2 | M3 PRO constants wrong → sim dynamics wrong | High until Phase 1 | everything marked PROVISIONAL; Phase 1 exists solely to kill this | do not skip 1.2 |
| R3 | Occupancy-map extension API drift in Isaac 6.0.x | Med | collector raises loudly, `--occupancy-npz` manual path exists | budget a day in Phase 2 |
| R4 | Upstream repo changes/vanishes | Low (dead 22 months) | pinned commit `dca7981`, patch script asserts anchors | vendor a tarball in the artefact |
| R5 | 4 Hz loop doesn't hold on the robot SBC | Med | Orin SKU is fine; Pi 5 marginal | equal-rate fallback rule (5.1) protects the comparison |
| R6 | Scene diversity too thin for reviewers | High if ignored | Phase 2.2 targets ≥ 10; MobilityGen path documented | this is where spare weeks go |
| R7 | H2 arms don't separate in the data (G2.d) | Low | lateral-energy gate before any training | raise holonomic cruise/lookahead to force separation, re-collect |
