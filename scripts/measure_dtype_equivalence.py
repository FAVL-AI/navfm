"""Three-cell measurement: does coercion restore era behaviour, or make a third one?

    <era-python>       scripts/measure_dtype_equivalence.py --cell A --out A.npz
    <era-python>       scripts/measure_dtype_equivalence.py --cell B --out B.npz
    <canonical-python> scripts/measure_dtype_equivalence.py --cell C --out C.npz
    <canonical-python> scripts/measure_dtype_equivalence.py --compare A.npz B.npz C.npz

Label computation only. **No checkpoint, no model, no G0.c metric** — schema
reconnaissance under the acquisition ruling.

The cells decompose two confounded factors:

* **A** — era numpy (1.23.5), object-dtype path, as the reference ran it.
* **B** — era numpy, float64-coerced path (the proposed patch).
* **C** — canonical numpy (2.x), float64-coerced path — the cell that would
  actually produce G0.c's numbers.

``B minus A`` isolates the **representation** effect at fixed numpy.
``C minus B`` isolates the **numpy-version** effect at fixed representation.
``C minus A`` is the claim under test: *canonical-coerced equals era-reference*.

`_compute_actions` is reproduced verbatim from
`vint_dataset.py`, including the `metric_waypoint_spacing` normalisation, so
the quantities measured are the ones the amendment binds: actions, goal_pos,
and the distance label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import warnings
from pathlib import Path

import numpy as np

DATA = Path.home() / "navfm-data" / "go_stanford" / "go_stanford"
LEN_TRAJ_PRED = 5
WAYPOINT_SPACING = 1
METRIC_WAYPOINT_SPACING = 0.12
LEARN_ANGLE = True


def yaw_rotmat(yaw):  # verbatim, data_utils.py:28
    return np.array(
        [
            [np.cos(yaw), -np.sin(yaw), 0.0],
            [np.sin(yaw), np.cos(yaw), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )


def to_local_coords(positions, curr_pos, curr_yaw):  # verbatim, data_utils.py:45
    rotmat = yaw_rotmat(curr_yaw)
    if positions.shape[-1] == 2:
        rotmat = rotmat[:2, :2]
    elif positions.shape[-1] != 3:
        raise ValueError
    return (positions - curr_pos).dot(rotmat)


def compute_actions(traj, curr_time, goal_time):  # verbatim _compute_actions
    start, end = curr_time, curr_time + LEN_TRAJ_PRED * WAYPOINT_SPACING + 1
    yaw = traj["yaw"][start:end:WAYPOINT_SPACING]
    positions = traj["position"][start:end:WAYPOINT_SPACING]
    goal_pos = traj["position"][min(goal_time, len(traj["position"]) - 1)]

    if len(yaw.shape) == 2:
        yaw = yaw.squeeze(1)
    if yaw.shape != (LEN_TRAJ_PRED + 1,):
        const_len = LEN_TRAJ_PRED + 1 - yaw.shape[0]
        yaw = np.concatenate([yaw, np.repeat(yaw[-1], const_len)])
        positions = np.concatenate(
            [positions, np.repeat(positions[-1][None], const_len, axis=0)], axis=0
        )

    waypoints = to_local_coords(positions, positions[0], yaw[0])
    goal_pos = to_local_coords(goal_pos, positions[0], yaw[0])
    if LEARN_ANGLE:
        yaw = yaw[1:] - yaw[0]
        actions = np.concatenate([waypoints[1:], yaw[:, None]], axis=-1)
    else:
        actions = waypoints[1:]
    actions = np.asarray(actions, dtype=float)
    goal_pos = np.asarray(goal_pos, dtype=float)
    actions[:, :2] /= METRIC_WAYPOINT_SPACING * WAYPOINT_SPACING
    goal_pos /= METRIC_WAYPOINT_SPACING * WAYPOINT_SPACING
    return actions, goal_pos


def load(name: str, *, coerce: bool):
    with open(DATA / name / "traj_data.pkl", "rb") as fh:
        d = pickle.load(fh)
    if not coerce:
        return d
    pos = np.array([[float(np.ravel(c)[0]) for c in row] for row in d["position"]], dtype=float)
    yaw = np.array([float(np.ravel(v)[0]) for v in d["yaw"]], dtype=float)
    return {"position": pos, "yaw": yaw}


def run_cell(coerce: bool, names: list[str]) -> dict:
    acts, goals, dists, keys, failures = [], [], [], [], []
    warn_count = 0
    for name in names:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                traj = load(name, coerce=coerce)
                n = len(traj["position"])
                for t in range(0, max(0, n - LEN_TRAJ_PRED - 1)):
                    goal_t = min(t + LEN_TRAJ_PRED, n - 1)
                    a, g = compute_actions(traj, t, goal_t)
                    acts.append(a)
                    goals.append(g)
                    dists.append(goal_t - t)
                    keys.append(f"{name}:{t}")
            except Exception as exc:
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
            warn_count += sum(1 for x in w if "Deprecation" in x.category.__name__)
    return {
        "actions": np.asarray(acts, dtype=float),
        "goal_pos": np.asarray(goals, dtype=float),
        "dist": np.asarray(dists, dtype=float),
        "keys": np.asarray(keys),
        "warnings": warn_count,
        "failures": failures,
    }


def compare(a: dict, b: dict, label: str) -> dict:
    out: dict = {"pair": label}
    if list(a["keys"]) != list(b["keys"]):
        out["key_mismatch"] = True
        return out
    out["key_mismatch"] = False
    out["n_samples"] = int(len(a["keys"]))
    for q in ("actions", "goal_pos", "dist"):
        x, y = a[q], b[q]
        bit = bool(np.array_equal(x, y)) and x.dtype == y.dtype
        diff = np.abs(x - y)
        denom = np.maximum(np.abs(x), 1e-30)
        out[q] = {
            "bit_identical": bit,
            "max_abs": float(diff.max()) if diff.size else 0.0,
            "max_rel": float((diff / denom).max()) if diff.size else 0.0,
            "n_differing": int((diff > 0).sum()),
        }
        if diff.size and diff.max() > 0:
            idx = int(np.unravel_index(diff.argmax(), diff.shape)[0])
            out[q]["worst_sample"] = str(a["keys"][idx])
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cell", choices=["A", "B", "C"])
    p.add_argument("--out")
    p.add_argument("--names", default="gates/G0/splits/test/traj_names.txt")
    p.add_argument("--compare", nargs=3, metavar=("A", "B", "C"))
    args = p.parse_args(argv)

    if args.compare:
        cells = {}
        for tag, path in zip("ABC", args.compare, strict=True):
            z = np.load(path, allow_pickle=True)
            cells[tag] = {k: z[k] for k in z.files}
        report = {
            "n_samples": int(len(cells["A"]["keys"])),
            "warnings": {t: int(cells[t]["warnings"]) for t in "ABC"},
            "B_minus_A_representation": compare(cells["A"], cells["B"], "B-A"),
            "C_minus_B_numpy_version": compare(cells["B"], cells["C"], "C-B"),
            "C_minus_A_claim_under_test": compare(cells["A"], cells["C"], "C-A"),
        }
        print(json.dumps(report, indent=2))
        return 0

    names = Path(args.names).read_text().split()
    print(f"cell {args.cell}: {len(names)} trajectories, numpy {np.__version__}")
    result = run_cell(coerce=args.cell in ("B", "C"), names=names)
    print(
        f"  samples {len(result['keys'])}  warnings {result['warnings']}  failures {len(result['failures'])}"
    )
    if result["failures"]:
        print("  first failures:", result["failures"][:3])
    np.savez_compressed(args.out, **result)
    digest = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(f"  wrote {args.out}  sha256 {digest[:16]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
