"""Enforce the declared float32 tolerance and the semantic invariants.

    python scripts/verify_tolerance.py
    python scripts/verify_tolerance.py \\
        --split gates/G0/splits/test/traj_names.txt --expect-population 760

The amendment declares a per-scalar tolerance at the INPUT SITE: where a
trajectory's `traj_data` is unpickled and enters the loader. That is where the
correction is applied, and the only site at which the coercion's own numerical
effect is observable in isolation. It is deliberately NOT the later
`torch.as_tensor(..., dtype=torch.float32)` conversion -- between the two the
loader runs `to_local_coords` and `yaw[1:] - yaw[0]`, so a difference measured
there is the coercion plus all intervening arithmetic. A declaration nothing
checks is not a control, so this is the check.

Evaluated **per scalar**, at `float32`, at that site:

* **≤ 1 ULP** between the corrected value and the released reference value;
* aggregates, averages and sign cancellation may never rescue a failing scalar;
* sign preserved for every non-zero finite value;
* `+0.0` and `-0.0` treated as equivalent, and no non-zero value may become
  zero to satisfy the tolerance;
* subnormals permitted and never flushed to zero;
* `NaN`/`±inf` are invalid trajectory values and fail rather than being
  repaired.

And the semantic invariants, any one of which failing rejects the correction
regardless of the numbers: shape `[T,2]`/`[T]` with `T` unchanged, temporal
order preserved with nothing reordered/inserted/removed/duplicated/
interpolated, and the admitted population unchanged at its frozen size.
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np

from navfm.trajio import TrajectoryContractError, normalise_traj_data

FROZEN_POPULATION = 3696


def ulp_distance_float32(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Adjacent-representable distance between two float32 arrays.

    Uses the monotone ordering of IEEE-754: reinterpreting the bits as a signed
    magnitude and mapping to a total order makes adjacent representables differ
    by exactly one. Zero-sign is normalised first, so +0.0 and -0.0 are 0 ULP
    apart as the declaration requires.
    """
    a32 = np.asarray(a, dtype=np.float32).copy()
    b32 = np.asarray(b, dtype=np.float32).copy()
    a32[a32 == 0] = np.float32(0.0)  # collapse -0.0 to +0.0
    b32[b32 == 0] = np.float32(0.0)

    ai = a32.view(np.int32).astype(np.int64)
    bi = b32.view(np.int32).astype(np.int64)
    # map the sign-magnitude layout onto a monotone total order
    ai = np.where(ai < 0, np.int64(0x80000000) - ai, ai)
    bi = np.where(bi < 0, np.int64(0x80000000) - bi, bi)
    return np.abs(ai - bi)


def _reference(raw: object, field: str) -> np.ndarray:
    """The released values, read by a route sharing NO code with the correction.

    Deliberately not ``float(np.ravel(v)[0])``: that is exactly what
    ``coerce_scalar`` does, so using it here would make the comparison
    tautological -- ``got`` and ``ref`` identical by construction, and a ULP
    check that cannot fail. A check that cannot fail certifies nothing.

    ``position`` goes through NumPy's own object->float conversion; ``yaw``
    through concatenation of its cells. Neither performs an element select.
    """
    arr = np.asarray(raw, dtype=object)
    if arr.ndim == 1:
        return np.concatenate([np.atleast_1d(np.asarray(v, dtype=float)) for v in arr])
    return np.asarray(arr.tolist(), dtype=float)


class Tally:
    """Observed extremes and invariant subjects, so the report can say what it saw.

    An invariant whose subject never occurs in the corpus holds vacuously.
    Reporting it as "holding" without saying so overstates the evidence, which
    is the failure genus already recorded as F-M2-1 and F-M2-4.
    """

    def __init__(self) -> None:
        self.scalars = 0
        self.max_ulp = 0
        self.zeros = 0
        self.negative_zeros = 0
        self.subnormals = 0
        self.multi_valued_cells = 0
        self.non_finite = 0

    def observe_raw(self, raw: object) -> None:
        """Count the subjects of the vacuity claims, from the RELEASED cells.

        Called before normalisation is attempted, and unconditionally: a
        trajectory containing either subject is refused, so anything counted
        after the refusal return could only ever report zero.
        """
        arr = np.asarray(raw, dtype=object)
        if arr.dtype != object:
            flat = np.asarray(arr, dtype=float).reshape(-1)
            self.non_finite += int(np.count_nonzero(~np.isfinite(flat)))
            return
        for cell in arr.reshape(-1):
            try:
                c = np.asarray(cell)
            except ValueError:  # ragged cell; the correction refuses it and says so
                self.multi_valued_cells += 1
                continue
            if c.size != 1:
                self.multi_valued_cells += 1
                continue
            try:
                value = np.asarray(c, dtype=float).reshape(-1)[0]
            except (TypeError, ValueError):
                # A non-numeric cell. The correction refuses it with a located
                # message; observing must not pre-empt that with a traceback,
                # or the checker turns a reportable refusal into a crash.
                continue
            if not np.isfinite(value):
                self.non_finite += 1

    def report(self) -> str:
        return (
            f"scalars compared     : {self.scalars}\n"
            f"maximum ULP distance : {self.max_ulp}\n"
            f"exact zeros seen     : {self.zeros}\n"
            f"negative zeros seen  : {self.negative_zeros}"
            f"{'' if self.negative_zeros else '  (zero-sign clause holds VACUOUSLY)'}\n"
            f"subnormals seen      : {self.subnormals}"
            f"{'' if self.subnormals else '  (subnormal clause holds VACUOUSLY)'}\n"
            f"multi-valued cells   : {self.multi_valued_cells}"
            f"{'' if self.multi_valued_cells else '  (no-truncation clause holds VACUOUSLY)'}\n"
            f"non-finite values    : {self.non_finite}"
            f"{'' if self.non_finite else '  (non-finite clause holds VACUOUSLY)'}"
        )


def check_trajectory(path: Path, name: str, tally: Tally | None = None) -> list[str]:
    with open(path / name / "traj_data.pkl", "rb") as fh:
        raw = pickle.load(fh)

    # Observe BEFORE the refusal return. A multi-valued or non-finite cell is
    # exactly what gets a trajectory refused, so counting after the return meant
    # the counters could never be non-zero -- the "VACUOUSLY" annotations would
    # print unconditionally, including on a corpus just refused for containing
    # their subjects. Moving the raw read here was not enough on its own; the
    # placement is the whole fix.
    if tally is not None:
        for field in ("position", "yaw"):
            if field in raw:
                tally.observe_raw(raw[field])

    try:
        out = normalise_traj_data(raw, trajectory=name)
    except TrajectoryContractError as exc:
        return [f"{name}: REFUSED by the correction: {exc}"]

    problems: list[str] = []
    for field in ("position", "yaw"):
        ref = _reference(raw[field], field)
        got = np.asarray(out[field], dtype=float)
        if field == "yaw" and ref.ndim == 2 and ref.shape[1] == 1:
            ref = ref.reshape(-1)

        # 7 / 8: shape and length invariants
        if got.shape != ref.shape:
            problems.append(f"{name}.{field}: shape {got.shape} != reference {ref.shape}")
            continue

        # 5: non-finite must fail, never be repaired
        if not np.all(np.isfinite(got)):
            problems.append(f"{name}.{field}: non-finite value survived normalisation")

        # 1 / 2 / 3 / 4: per-scalar ULP, sign, zero, subnormal
        ulps = ulp_distance_float32(got, ref)
        if tally is not None:
            tally.scalars += int(got.size)
            tally.max_ulp = max(tally.max_ulp, int(ulps.max()) if ulps.size else 0)
        over = int(np.count_nonzero(ulps > 1))
        if over:
            worst = int(ulps.max())
            problems.append(f"{name}.{field}: {over} scalar(s) exceed 1 ULP (max {worst} ULP)")

        ref32, got32 = ref.astype(np.float32), got.astype(np.float32)
        nz = (ref32 != 0) & np.isfinite(ref32)
        if np.any(np.sign(got32[nz]) != np.sign(ref32[nz])):
            problems.append(f"{name}.{field}: sign changed on a non-zero finite value")
        if np.any((ref32 != 0) & (got32 == 0)):
            problems.append(f"{name}.{field}: a non-zero value became zero")
        sub = (np.abs(ref32) > 0) & (np.abs(ref32) < np.finfo(np.float32).tiny)
        if tally is not None:
            tally.zeros += int(np.count_nonzero(ref32 == 0))
            # Condition 3's operative content is the +0 == -0 equivalence, so
            # its subject is the NEGATIVE zero, not the zero. Keying the
            # annotation on `zeros` reported 386 subjects for a clause that has
            # none, and a corpus containing a negative zero would have printed
            # a byte-identical line.
            tally.negative_zeros += int(np.count_nonzero(np.signbit(ref32) & (ref32 == 0)))
            tally.subnormals += int(np.count_nonzero(sub))
        if np.any(sub & (got32 == 0)):
            problems.append(f"{name}.{field}: a subnormal was flushed to zero")

        # 8: ordering -- element i must correspond to element i
        if not np.array_equal(np.argsort(got, axis=0), np.argsort(ref, axis=0)):
            problems.append(f"{name}.{field}: temporal ordering changed")

    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", default=str(Path.home() / "navfm-data/go_stanford/go_stanford"))
    p.add_argument("--split", default=None, help="restrict to a traj_names.txt (default: all)")
    p.add_argument("--expect-population", type=int, default=None)
    args = p.parse_args(argv)

    root = Path(args.data)
    if args.split:
        names = Path(args.split).read_text().split()
    else:
        names = sorted(d.name for d in root.iterdir() if d.is_dir())

    if args.expect_population is not None:
        expected = args.expect_population
    elif args.split is None:
        expected = FROZEN_POPULATION
    else:
        # len(names) here would compare a number with itself: a population check
        # that cannot fail, on the script's own documented invocation.
        print(
            "--split restricts the population, so the frozen-population invariant "
            "cannot be checked from it. Pass --expect-population with the split's "
            "declared size to make clause 9 checkable, or run without --split.",
        )
        return 2
    problems: list[str] = []
    tally = Tally()
    converted = 0
    for name in names:
        found = check_trajectory(root, name, tally)
        problems += found
        if not found:
            converted += 1

    # 9: population invariant
    if converted != len(names):
        problems.append(
            f"POPULATION: {converted} of {len(names)} trajectories converted; the correction "
            f"must not change the admitted population, and no trajectory may be dropped "
            f"because its representation is inconvenient"
        )
    if len(names) != expected:
        problems.append(f"POPULATION: {len(names)} trajectories, expected {expected}")

    print(f"trajectories checked : {len(names)}")
    print(f"converted            : {converted}")
    print(f"population invariant : {'HOLDS' if converted == len(names) else 'VIOLATED'}")
    print(tally.report())
    if problems:
        print(f"\nTOLERANCE / INVARIANT FAILURES: {len(problems)}")
        for line in problems[:20]:
            print(f"  {line}")
        return 1
    print("\nAll scalars within 1 ULP at float32; every semantic invariant holds.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
