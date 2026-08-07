"""The nine cross-dataset contract cases, plus the released-corpus case.

`navfm.trajio` is the single boundary at which a released corpus is made
contract-compliant. Because `scripts/patch_upstream.py` is dataset-agnostic,
this boundary is reached by RECON, SACSoN, SCAND and TartanDrive too — so the
tests must prove it does not narrow inputs that were already valid, as well as
proving it refuses invalid ones.

The standing rule applies in both directions: a check that cannot fail
certifies nothing, and a check that cannot pass gets deleted by whoever is in a
hurry.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pytest

from navfm.trajio import TrajectoryContractError, coerce_scalar, normalise_traj_data

GO_STANFORD = Path.home() / "navfm-data" / "go_stanford" / "go_stanford"


def _plain(n: int = 4) -> dict:
    return {
        "position": np.arange(2 * n, dtype=float).reshape(n, 2),
        "yaw": np.linspace(-1.0, 1.0, n),
    }


def _object_nested(n: int = 4) -> dict:
    """The released GO Stanford shape: object cells holding 1-element arrays."""
    pos = np.empty((n, 2), dtype=object)
    for i in range(n):
        for j in range(2):
            pos[i, j] = np.float64(i * 2 + j)
    yaw = np.empty(n, dtype=object)
    for i in range(n):
        yaw[i] = np.array([float(i) / n])
    return {"position": pos, "yaw": yaw}


class TestValidInputsStillPass:
    """Backward compatibility: the boundary must not narrow valid inputs."""

    def test_plain_numerical_arrays_pass_unchanged(self) -> None:
        source = _plain()
        out = normalise_traj_data(source)
        assert np.array_equal(out["position"], source["position"])
        assert np.array_equal(out["yaw"], source["yaw"])

    def test_released_go_stanford_object_arrays_convert(self) -> None:
        out = normalise_traj_data(_object_nested())
        assert out["position"].shape == (4, 2)
        assert out["yaw"].shape == (4,)
        assert out["position"].dtype == np.float64
        assert np.array_equal(out["position"], np.arange(8, dtype=float).reshape(4, 2))

    def test_additional_metadata_fields_are_preserved(self) -> None:
        """Extra keys pass through: this boundary converts, it does not curate."""
        source = _plain() | {"scene_id": "no2", "timestamps": [1, 2, 3, 4]}
        out = normalise_traj_data(source)
        assert out["scene_id"] == "no2"
        assert out["timestamps"] == [1, 2, 3, 4]

    def test_the_source_mapping_is_not_mutated(self) -> None:
        source = _object_nested()
        normalise_traj_data(source)
        assert source["position"].dtype == object, "the released input was modified in place"

    def test_integer_input_widens_without_complaint(self) -> None:
        """An ordinary unaffected scalar path, per the cross-dataset requirement."""
        out = normalise_traj_data(
            {"position": np.arange(8).reshape(4, 2), "yaw": np.zeros(4, dtype=int)}
        )
        assert out["position"].dtype == np.float64
        assert out["yaw"].shape == (4,)


class TestInvalidInputsAreRefused:
    def test_missing_position_fails_clearly(self) -> None:
        with pytest.raises(TrajectoryContractError, match="missing the required field 'position'"):
            normalise_traj_data({"yaw": np.zeros(4)})

    def test_missing_yaw_fails_clearly(self) -> None:
        with pytest.raises(TrajectoryContractError, match="missing the required field 'yaw'"):
            normalise_traj_data({"position": np.zeros((4, 2))})

    def test_incorrect_position_shape_fails_clearly(self) -> None:
        with pytest.raises(TrajectoryContractError, match=r"requires \[T, 2\]"):
            normalise_traj_data({"position": np.zeros((4, 3)), "yaw": np.zeros(4)})

    def test_incorrect_yaw_shape_fails_clearly(self) -> None:
        with pytest.raises(TrajectoryContractError, match="requires"):
            normalise_traj_data({"position": np.zeros((4, 2)), "yaw": np.zeros((4, 3))})

    def test_ragged_nested_arrays_are_refused_not_truncated(self) -> None:
        """The defect the verdict explicitly did not clear: a multi-element cell
        must refuse, never yield its first element."""
        pos = np.empty((2, 2), dtype=object)
        pos[0, 0] = np.array([1.0, 99.0])  # two values in one cell
        for i, j in ((0, 1), (1, 0), (1, 1)):
            pos[i, j] = np.float64(0.0)
        with pytest.raises(TrajectoryContractError, match="exactly one scalar value"):
            normalise_traj_data({"position": pos, "yaw": np.zeros(2)})

    @pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
    def test_non_finite_values_are_refused(self, bad: float) -> None:
        source = _plain()
        source["yaw"][1] = bad
        with pytest.raises(TrajectoryContractError, match="finite"):
            normalise_traj_data(source)

    def test_empty_trajectory_is_refused(self) -> None:
        with pytest.raises(TrajectoryContractError, match="empty"):
            normalise_traj_data({"position": np.zeros((0, 2)), "yaw": np.zeros(0)})

    def test_length_disagreement_is_refused(self) -> None:
        with pytest.raises(TrajectoryContractError, match="index the same frames"):
            normalise_traj_data({"position": np.zeros((5, 2)), "yaw": np.zeros(4)})

    def test_failure_names_the_trajectory_and_index(self) -> None:
        pos = np.empty((3, 2), dtype=object)
        for i in range(3):
            for j in range(2):
                pos[i, j] = np.float64(0.0)
        pos[2, 1] = np.array([1.0, 2.0])
        with pytest.raises(TrajectoryContractError) as excinfo:
            normalise_traj_data({"position": pos, "yaw": np.zeros(3)}, trajectory="no2vc_101_0")
        assert "no2vc_101_0[2,1]" in str(excinfo.value)


class TestCoerceScalar:
    @pytest.mark.parametrize(
        "value", [1.5, np.float64(1.5), [1.5], np.array([1.5]), np.array([[1.5]])]
    )
    def test_every_single_valued_form_resolves(self, value: object) -> None:
        assert coerce_scalar(value, field="yaw", where="t[0]") == 1.5

    @pytest.mark.parametrize("value", [[], np.array([]), [1.0, 2.0], np.array([1.0, 2.0])])
    def test_empty_and_multi_element_refuse(self, value: object) -> None:
        with pytest.raises(TrajectoryContractError, match="exactly one scalar value"):
            coerce_scalar(value, field="yaw", where="t[0]")

    def test_malformed_nested_value_refuses(self) -> None:
        with pytest.raises(TrajectoryContractError):
            coerce_scalar(np.array(["not-a-number"], dtype=object), field="yaw", where="t[0]")


@pytest.mark.skipif(not GO_STANFORD.is_dir(), reason="GO Stanford corpus not present")
class TestAgainstTheRealCorpus:
    def test_representative_released_records_convert(self) -> None:
        names = sorted(p.name for p in GO_STANFORD.iterdir() if p.is_dir())[:25]
        for name in names:
            with open(GO_STANFORD / name / "traj_data.pkl", "rb") as fh:
                raw = pickle.load(fh)
            out = normalise_traj_data(raw, trajectory=name)
            assert out["position"].ndim == 2 and out["position"].shape[1] == 2
            assert out["yaw"].ndim == 1
            assert out["position"].shape[0] == out["yaw"].shape[0]
            assert np.isfinite(out["position"]).all() and np.isfinite(out["yaw"]).all()

    def test_conversion_preserves_the_measured_values(self) -> None:
        """Bit-identical to the element-wise read the measurement used."""
        name = sorted(p.name for p in GO_STANFORD.iterdir() if p.is_dir())[0]
        with open(GO_STANFORD / name / "traj_data.pkl", "rb") as fh:
            raw = pickle.load(fh)
        expected_yaw = np.array([float(np.ravel(v)[0]) for v in raw["yaw"]], dtype=float)
        out = normalise_traj_data(raw, trajectory=name)
        assert np.array_equal(out["yaw"], expected_yaw)
