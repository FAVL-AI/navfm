# How history reaches the requested-goal score: source inspection note (v1)

**Scope.** A read-only reading of the source code that produced the requested-goal score in the
v4 and v5 history diagnostics. No model was loaded and nothing was executed. This note describes
the computation graph. It does **not** establish how strongly the checkpoint uses any input, and
it does **not** explain the closed-loop navigation failures.

## Source inspected
- **Upstream:** `visualnav-transformer` (`https://github.com/robodhruv/visualnav-transformer`),
  commit `dca79815b704e5aa9c6bdc3082351f9e3b2848c2`. Files:
  - `train/vint_train/models/vint/vint.py` (sha256 `1af3afb275f6f52d643df792cf39d8bb77e0fe00f06d7ceb9c152a408554ad37`);
  - `train/vint_train/models/vint/self_attention.py` (sha256 `e28c8eb0c5017d8690b1328a7ec75c30c7fa30416f232b05b9bb406670ce57a6`).
- **The copy the v5 run loaded.** The staged snapshot in
  `$NAVFM_EVIDENCE_ROOT/history-stress-test-v5-attempt-01/staged_src/upstream_train/` is
  byte-identical to both files at that commit. The local clone has no changes under
  `train/vint_train/models`.
- **Model configuration.** Read from the episodes' `runtime_manifest.json`
  (`policy.config`): `context_size` 5, `late_fusion` False, `obs_encoder` efficientnet-b0,
  `obs_encoding_size` 512, 4 attention heads, 4 layers, feed-forward factor 4, `image_size`
  [85, 64].
- **Call path.** `scripts/history_sensitivity/history_runner.py` at runner sha256
  `288b6cf71814e6057cb9ce4a05d05960ffe38c241cd523e91ff5187346c20f74`, lines 598–602 (batch assembly, copied from the deployed `step()`) and line 617
  (the score is `d_all[goal_row_index]`).

## Computation (VERIFIED from source)
1. **Batch assembly** (`history_runner.py:598–600`). The six frames (five history frames and the
   current frame) are stacked into one observation tensor and repeated once per goal row. Every
   goal row in a call therefore sees the same history.
2. **Goal token** (`vint.py:45`, `vint.py:84–95`). With `late_fusion` False, the goal encoder is
   an EfficientNet-b0 with 6 input channels. Its input is the **current frame** (the last three
   observation channels) concatenated with the **goal image**. It yields one 512-d token.
   **History frames do not enter this encoder.**
3. **Observation tokens** (`vint.py:40`, `vint.py:99–119`). A separate EfficientNet-b0 encodes
   each of the six frames independently, yielding six 512-d tokens.
4. **Mixing** (`vint.py:122–123`; `self_attention.py:24`, `:31–32`, `:39–40`). The seven tokens
   (six observation, one goal) get a sinusoidal positional encoding and pass through a 4-layer,
   4-head pre-norm Transformer encoder. There is no attention mask, so every token can attend to
   every other.
5. **Distance head** (`self_attention.py:33–36`, `:42–45`; `vint.py:68–70`, `vint.py:126`). The
   seven output tokens are flattened into one 3584-d vector, which passes through
   Linear(3584→512), then 256, 128, 64 and 32, each followed by ReLU, then Linear(32→1). The
   output is the distance score.

## What this shows
- **History has a computational path to the distance head.** It enters through its own five
  token positions in the flattened vector, and through attention into the current-frame and goal
  tokens. Nothing in the architecture blocks it.
- **The current-versus-goal comparison is formed in a pathway that sees no history** (the 6-channel
  goal encoder, step 2).

## What this does not establish
- **How strongly the trained checkpoint uses history.** That is set by learned weights and
  activations, which this note does not examine. Parameter magnitudes alone would not establish
  functional dependence either.
- **Why the measured sensitivity to the tested substitutions was low** (v4; v5 at `28c9deb`).
  The structure is consistent with that result but does not demonstrate its cause.
- **Any explanation of the closed-loop navigation or stopping failures.**
