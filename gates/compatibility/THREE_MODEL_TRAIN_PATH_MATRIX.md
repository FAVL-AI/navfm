# Three-model train-path compatibility matrix

Every cell is derived from the evidence file named in its row. No cell is
hand-entered, and a row with no backing artefact renders `NO EVIDENCE` rather
than blank — a blank reads as a pass to a hurried reader.

- NavFM commit `3270785` · upstream `dca7981`
- Python 3.11.15 · PyTorch 2.11.0+cu128 · NumPy 2.4.4 · device cpu
- Trajectory `pilot_0002` · Option 1 payload digest `c897464fb3d5344f`
- Stage SIMULATION_DEVELOPMENT · admission `NOT_ADMITTED` · formal training allowed: False

| Contract | GNM | ViNT | NoMaD | Evidence |
|---|---|---|---|---|
| Option 1 loader accepts | PASS | PASS | PASS | `<model>_sample_population.json` |
| sample population explained | PASS | PASS | PASS | `<model>_sample_population.json` |
| population conserved (cand = acc + rej) | PASS | PASS | PASS | `<model>_sample_population.json` |
| sample index trace | PASS | PASS | PASS | `forensics/nomad_sample_index_trace.csv` |
| batch construction (official collate) | PASS | PASS | PASS | `<model>_single_batch_forward.json` |
| forward in train mode | PASS | PASS | PASS | `<model>_single_batch_forward.json` |
| all required targets present | PASS | PASS | PASS | `<model>_single_batch_forward.json` |
| loss construction (upstream source) | PASS | PASS | PASS | `<model>_loss_smoke.json` |
| finite total loss | PASS | PASS | PASS | `<model>_loss_smoke.json` |
| total loss is a scalar | PASS | PASS | PASS | `<model>_loss_smoke.json` |
| backward executes | PASS | PASS | PASS | `<model>_backward_optimizer_smoke.json` |
| finite gradients (no NaN/Inf) | PASS | PASS | PASS | `<model>_backward_optimizer_smoke.json` |
| non-zero gradients on expected path | PASS | PASS | PASS | `<model>_backward_optimizer_smoke.json` |
| optimizer step executes | PASS | PASS | PASS | `<model>_backward_optimizer_smoke.json` |
| a named parameter measurably changed | PASS | PASS | PASS | `<model>_backward_optimizer_smoke.json` |
| released checkpoint unchanged | PASS | PASS | PASS | `<model>_backward_optimizer_smoke.json` |
| repeatable smoke (2 runs, frozen seed) | PASS | PASS | PASS | `train_path_compatibility.json` |
| invalid fixture rejected | PASS | PASS | PASS | `train_path_compatibility.json` |

## Where the models legitimately differ

These are model-semantic differences, preserved rather than standardised away.
Forcing them into symmetry would make the table look tidier and the science worse.

| Property | GNM | ViNT | NoMaD |
|---|---|---|---|
| context size | 5 | 5 | 3 |
| action horizon | 5 | 5 | 8 |
| admissible index range | [5,35) | [5,35) | [3,32) |
| samples from 40 frames | 30 | 30 | 29 |
| loss components | dist_loss, action_loss, action_waypts_cos_sim, multi_action_waypts_cos_sim, action_orien_cos_sim, multi_action_orien_cos_sim, total_loss | dist_loss, action_loss, action_waypts_cos_sim, multi_action_waypts_cos_sim, action_orien_cos_sim, multi_action_orien_cos_sim, total_loss | dist_loss, diffusion_loss, total_loss |
| alpha | 0.5 | 0.5 | 0.0001 |
| total-loss formula | alpha * 1e-2 * dist_loss + (1 - alpha) * action_loss | alpha * 1e-2 * dist_loss + (1 - alpha) * action_loss | alpha * dist_loss + (1 - alpha) * diffusion_loss |
| stochastic training state | none | none | DDPM noise + timestep + goal mask |
| trainable tensors | 326 | 504 | 644 |
| tensors receiving no gradient | 0 | 16 | 16 |
| unexecuted share of checkpoint | 0.00% | 19.21% | 17.59% |

## Measured values

| | GNM | ViNT | NoMaD |
|---|---|---|---|
| total loss | 0.104939 | 0.084481 | 0.036361 |
| gradient global norm | 2.4080e+00 | 2.1664e+00 | 2.8813e+00 |
| non-zero gradients | 324/326 | 486/504 | 628/644 |
| parameters changed by one step | 326/326 | 488/504 | 628/644 |
| repeat run max abs difference | 0.00e+00 | 0.00e+00 | 0.00e+00 |
| invalid fixture rejected by | AssertionError | AssertionError | RuntimeError |

## Claim boundary

> The fresh Yahboom Isaac Sim Option 1 trajectories have been verified through the
> complete data-to-training-step path for GNM, ViNT and NoMaD. For each model, the
> official dataset path constructs a valid batch, the model executes in training
> mode, the model-specific loss is finite, backpropagation produces valid gradients,
> and one optimizer step updates the in-memory model without modifying the released
> checkpoint.

**Not claimed:** model trained · model improved · fine-tuning succeeded ·
convergence · generalisation · performance improvement · training dataset admitted ·
ViNT-generated pilots are valid expert demonstrations.

Author: Frank Asante Van Laarhoven
