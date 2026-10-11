# Controller/plant offline reduction v1

Preparation for a CPU-only descriptive reduction of the preserved diagnostic at source freeze `81e0af0a5e09fcc7ac379ba3f93678563f519bde`. No simulator, model, controller replay or new physical observation is permitted. Commit this reducer before executing it once to a fresh external directory.

The original report remains **FAIL**: its inherited final numeric validator recursively encounters the newly added `diagnostic` strings and null metadata. All 3120 numeric sample payloads pass that same validator when only this metadata field is separated. This establishes a final scoring/schema defect; it does not retroactively make the original report successful.

The reducer authenticates every ledger-bound artifact, checks 3120 ordered rows and exact schedule metadata/commands, validates every remaining numeric value with the original validator, and checks all five telemetry phases, sequence, clock and DOF bindings. It preserves original status/error and input hashes in a new derived output. Target windows remain exactly the twelve frozen 60-tick windows starting at `300 + 240*k`. The unchanged `score_command` supplies the frozen full-hold and final-half criteria. No thresholds, command order, gains, plant, sensor or state are changed. Scores are descriptive recovered reductions, not a replacement qualification or permission to run navigation.

For each cell, report original target/mode, measured integral before/after onset reset and after the first update, full-hold control-output mean, four accepted and realized wheel means, signed right-minus-left wheel differential, body signed yaw/distance integrals, and the frozen criterion results. Direct rest-start versus conditioned PI cells differ in antecedent and controller mode. Neither improvement nor failure uniquely identifies a plant or PI cause. Effective solver friction/floor forces remain unmeasured; stage readbacks are reported only as observed properties.

Validation: nine focused tests pass, covering separate metadata validation, retained numeric nonfinite rejection and metadata/command tamper rejection, actual nested `[1,4]` DOF schema through a complete synthetic reduction, bool/integer metadata confusion, nonfinite clocks, chronological phase drift, wrong freeze and missing artifact binding. An initial formatter command failed because this worktree has no `.venv/bin/ruff`; the established external development environment then formatted the two files and ran the initial three tests successfully; after the bounded readback corrections all nine focused tests pass. This tooling failure is not a product test failure.

Execution after source commit:

```sh
env -u PYTHONPATH /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/reduce_controller_plant_diagnostic_v1.py --input /home/favl/navfm-runtime-evidence/controller-plant-diagnostic-v1-01 --out /home/favl/navfm-runtime-evidence/controller-plant-offline-reduction-v1-01
```

Raw acquisition artifacts and new reduction output remain external and must never be committed. The original failed attempt, old source freezes and authentic robot asset remain unchanged. No intervention or further runtime is authorized by this reduction.
