# Alias-Aware Arrival Component Validation v1

## Scope

The detached candidate computes four-frame ordered similarity features, an
explicit terminal-to-alias margin, an episode-balanced logistic probability
map, and a timestamp-based dwell latch. It is not connected to a navigation
launcher or controller. The calibration implementation uses synthetic rows in
the tests; no recorded or pilot data was accessed or fitted.

`CalibrationRow.group_id` identifies an episode. Equal total weight per
episode is an implementation property and does not make episodes or layouts
statistically independent. The calibrator does not select a probability
threshold, alias-margin floor, terminal reference window, or dwell policy.
Those values remain explicit caller inputs and require a separately frozen
protocol before any research evaluation.

## Validation

Commands ran in the existing `/home/favl/miniforge3/envs/navfm-ci` environment,
with `PYTHONPATH` explicitly bound to this worktree's `src` directory:

```text
PYTHONPATH="$(pwd)/src" /home/favl/miniforge3/envs/navfm-ci/bin/python -m pytest -q tests/test_alias_aware_arrival.py
38 passed

/home/favl/miniforge3/envs/navfm-ci/bin/ruff check src/navfm/collection/alias_aware_arrival.py tests/test_alias_aware_arrival.py
All checks passed

PYTHONPATH="$(pwd)/src" /home/favl/miniforge3/envs/navfm-ci/bin/mypy src/navfm/collection/alias_aware_arrival.py
Success: no issues found in 1 source file
```

The tests cover feature ordering and invalid inputs, alias-window margins,
episode-balanced feature scaling and fit invariance under duplication of one
episode's frames, constant features, degenerate labels, deterministic fitting,
dwell timing/cancellation/reset, timestamp ordering, and explicit decision
settings. These synthetic checks establish software behavior only; they do not
establish calibration quality, novelty, navigation performance, or physical
stopping behavior.
