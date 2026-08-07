"""The one loader boundary where a released corpus is made contract-compliant.

`docs/DATA_CONTRACT.md` requires `position` as a numerical `[T, 2]` array and
`yaw` as a numerical `[T]` array. The released GO Stanford corpus satisfies
neither: all 3,696 trajectories store both as **object-dtype arrays whose
elements are themselves arrays**, and `torch.as_tensor` rejects object dtype
unconditionally — under every NumPy version, not merely current ones (F13).

This module is the single boundary at which that representation is converted.
It exists as one function rather than as scattered coercions so that the
conversion has exactly one definition, one test suite, and one digest.

**It asserts; it never repairs.** The measured justification for coercion is
that widening a cell holding exactly one value to `float64` is lossless — bit-
identical at fixed NumPy over 44,038 samples. That argument holds *only* for
single-valued cells. A cell holding two values is not a representation quirk,
it is a corpus this conversion does not understand, and taking `[0]` would
silently discard data while producing a plausible array. So:

* exactly one value per cell, or refuse;
* correct shape after conversion, or refuse;
* finite, or refuse;
* never resize, never pad, never drop a record, never invent a coordinate.

The original file is never written to. The result is a derived value.
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = [
    "CONVERSION_VERSION",
    "TrajectoryContractError",
    "coerce_scalar",
    "normalise_traj_data",
]

#: Bump on any change to the conversion's semantics. Recorded in metadata.json
#: so a converted corpus can name the rule that produced it.
CONVERSION_VERSION = "trajio_v1"


class TrajectoryContractError(ValueError):
    """A trajectory does not satisfy the model-ready contract and was refused."""


def coerce_scalar(value: object, *, field: str, where: str) -> float:
    """One cell to one float, or refuse with the location named.

    ``where`` carries trajectory and index context so a failure in a corpus of
    thousands says which record to look at.
    """
    array = np.asarray(value)

    if array.size != 1:
        raise TrajectoryContractError(
            f"{where}: {field} cell must contain exactly one scalar value; received "
            f"shape={array.shape}, size={array.size}. Refusing rather than selecting "
            f"an element -- silent truncation would produce a plausible array from a "
            f"corpus this conversion does not understand."
        )

    scalar = array.reshape(-1)[0]
    try:
        out = float(scalar)
    except (TypeError, ValueError) as exc:
        raise TrajectoryContractError(
            f"{where}: {field} did not resolve to a real scalar; received "
            f"type={type(scalar).__name__}"
        ) from exc

    if not np.isfinite(out):
        raise TrajectoryContractError(
            f"{where}: {field} is {out!r}; the contract requires finite values, and a "
            f"non-finite label propagates silently into every metric computed from it"
        )
    return out


def _to_float_array(raw: Any, *, field: str, trajectory: str) -> np.ndarray:
    """Convert one field, cell by cell, refusing anything ill-formed."""
    if raw is None:
        raise TrajectoryContractError(f"{trajectory}: {field} is missing")

    arr = np.asarray(raw, dtype=object) if np.asarray(raw).dtype == object else np.asarray(raw)

    if arr.dtype != object:
        out = np.asarray(arr, dtype=float)
        if not np.all(np.isfinite(out)):
            bad = int(np.count_nonzero(~np.isfinite(out)))
            raise TrajectoryContractError(
                f"{trajectory}: {field} contains {bad} non-finite value(s); the contract "
                f"requires finite values"
            )
        return out

    if arr.size == 0:
        raise TrajectoryContractError(f"{trajectory}: {field} is empty")

    if arr.ndim == 1:
        return np.array(
            [coerce_scalar(v, field=field, where=f"{trajectory}[{i}]") for i, v in enumerate(arr)],
            dtype=float,
        )
    if arr.ndim == 2:
        return np.array(
            [
                [
                    coerce_scalar(c, field=field, where=f"{trajectory}[{i},{j}]")
                    for j, c in enumerate(row)
                ]
                for i, row in enumerate(arr)
            ],
            dtype=float,
        )
    raise TrajectoryContractError(
        f"{trajectory}: {field} has {arr.ndim} dimensions; the contract allows 1 or 2"
    )


def normalise_traj_data(traj_data: dict, *, trajectory: str = "<trajectory>") -> dict:
    """Return a contract-compliant copy of ``traj_data``.

    Already-compliant input passes through with its values unchanged (dtype is
    normalised to float, which is a no-op for float input). Non-compliant input
    is either converted losslessly or refused — never partially accepted.

    The input mapping is not mutated, and no file is written.
    """
    if not isinstance(traj_data, dict):
        raise TrajectoryContractError(
            f"{trajectory}: traj_data must be a mapping; received {type(traj_data).__name__}"
        )
    for required in ("position", "yaw"):
        if required not in traj_data:
            raise TrajectoryContractError(
                f"{trajectory}: traj_data is missing the required field {required!r}; "
                f"the contract requires both 'position' and 'yaw'"
            )

    position = _to_float_array(traj_data["position"], field="position", trajectory=trajectory)
    yaw = _to_float_array(traj_data["yaw"], field="yaw", trajectory=trajectory)

    # yaw stored as [T, 1] is the released corpus's shape once cells are
    # unwrapped; flatten it rather than refuse, because no value is discarded.
    if yaw.ndim == 2 and yaw.shape[1] == 1:
        yaw = yaw.reshape(-1)

    if position.ndim != 2 or position.shape[1] != 2:
        raise TrajectoryContractError(
            f"{trajectory}: position has shape {position.shape}; the contract requires [T, 2]"
        )
    if yaw.ndim != 1:
        raise TrajectoryContractError(
            f"{trajectory}: yaw has shape {yaw.shape}; the contract requires [T]"
        )
    if position.shape[0] != yaw.shape[0]:
        raise TrajectoryContractError(
            f"{trajectory}: position has {position.shape[0]} rows but yaw has "
            f"{yaw.shape[0]}; they index the same frames and must agree"
        )
    if position.shape[0] == 0:
        raise TrajectoryContractError(f"{trajectory}: trajectory is empty")

    # Preserve every other key untouched: this boundary converts, it does not curate.
    out = dict(traj_data)
    out["position"] = position
    out["yaw"] = yaw
    return out
