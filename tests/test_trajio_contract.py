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

    @pytest.mark.parametrize(
        ("dtype", "values"),
        [
            (complex, [[1 + 2j, 2 + 0j], [3 + 0j, 4 + 0j]]),
            ("U8", [["1.5", "2.5"], ["3.5", "4.5"]]),
            (bool, [[True, False], [False, True]]),
            ("S8", [[b"1.5", b"2.5"], [b"3.5", b"4.5"]]),
        ],
    )
    def test_typed_non_numeric_position_refuses_at_the_non_object_branch(
        self, dtype: object, values: list
    ) -> None:
        """The hardening must cover BOTH branches of `_to_float_array`.

        `coerce_scalar` is reached only for object-dtype input. A typed complex
        array takes the other branch, where a bare `np.asarray(..., dtype=float)`
        silently dropped the imaginary part -- the truncation conditions 6 and 12
        forbid, reachable by any dataset whose arrays are typed rather than
        boxed. These go through `normalise_traj_data`, not `coerce_scalar`,
        because routing through the latter is what hid the defect.
        """
        with pytest.raises(TrajectoryContractError, match="not measurements"):
            normalise_traj_data({"position": np.array(values, dtype=dtype), "yaw": np.zeros(2)})

    def test_typed_complex_yaw_refuses(self) -> None:
        with pytest.raises(TrajectoryContractError, match="not measurements"):
            normalise_traj_data({"position": np.zeros((2, 2)), "yaw": np.array([1 + 1j, 2 + 0j])})

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

    def test_complex_cell_refuses_rather_than_dropping_the_imaginary_part(self) -> None:
        """A complex cell holds two reals; float() would keep one and discard one.

        It passes the size gate (size == 1), so only an explicit dtype check
        catches it. This is the truncation conditions 6 and 12 forbid, arriving
        through a dtype instead of a shape.
        """
        with pytest.raises(TrajectoryContractError, match="complex"):
            coerce_scalar(np.complex128(1 + 2j), field="yaw", where="t[0]")

    @pytest.mark.parametrize("value", ["1.5", np.str_("1.5"), True, np.bool_(False)])
    def test_non_numeric_that_parses_as_a_number_refuses(self, value: object) -> None:
        """float("1.5") succeeds. A string that parses is still not a measurement."""
        with pytest.raises(TrajectoryContractError, match="non-numeric"):
            coerce_scalar(np.array([value], dtype=object), field="yaw", where="t[0]")

    def test_ragged_sequence_refuses_with_the_contract_error_type(self) -> None:
        """Not numpy's bare ValueError: the caller must be able to tell a refusal
        from a crash."""
        with pytest.raises(TrajectoryContractError, match="ragged"):
            coerce_scalar([[1.0, 2.0], [3.0]], field="yaw", where="t[0]")

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


class TestToleranceCounterIsReachable:
    """The vacuity counters must be reachable for their own subjects.

    A multi-valued or non-finite cell is exactly what gets a trajectory refused,
    so a counter read after the refusal return could never be non-zero and its
    "VACUOUSLY" annotation would print unconditionally -- including on a corpus
    just refused for containing both. Counting the right thing is not enough;
    the placement is the fix, so the placement is what this pins.
    """

    def _corpus(self, tmp_path: Path, yaw_cells: list) -> Path:
        pos = np.empty((len(yaw_cells), 2), dtype=object)
        for i in range(len(yaw_cells)):
            for j in range(2):
                pos[i, j] = np.float64(i + j)
        yaw = np.empty(len(yaw_cells), dtype=object)
        for i, cell in enumerate(yaw_cells):
            yaw[i] = cell
        (tmp_path / "t0").mkdir(parents=True)
        with open(tmp_path / "t0" / "traj_data.pkl", "wb") as fh:
            pickle.dump({"position": pos, "yaw": yaw}, fh)
        return tmp_path

    def _tally(self, root: Path):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "vt", Path(__file__).resolve().parents[1] / "scripts" / "verify_tolerance.py"
        )
        assert spec and spec.loader
        vt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vt)
        tally = vt.Tally()
        vt.check_trajectory(root, "t0", tally)
        return tally

    def test_multi_valued_cell_is_counted_even_though_it_is_refused(self, tmp_path: Path) -> None:
        root = self._corpus(tmp_path, [np.array([1.0, 2.0]), np.array([1.0])])
        assert self._tally(root).multi_valued_cells == 1

    def test_non_finite_cell_is_counted_even_though_it_is_refused(self, tmp_path: Path) -> None:
        root = self._corpus(tmp_path, [np.array([np.nan]), np.array([1.0])])
        assert self._tally(root).non_finite == 1

    def test_a_clean_corpus_counts_zero_of_both(self, tmp_path: Path) -> None:
        """The control: the counters must not simply always report a subject."""
        root = self._corpus(tmp_path, [np.array([0.5]), np.array([1.0])])
        tally = self._tally(root)
        assert tally.multi_valued_cells == 0 and tally.non_finite == 0

    def test_negative_zero_is_counted_so_the_clause_has_a_measured_subject(
        self, tmp_path: Path
    ) -> None:
        """Condition 3's subject is the NEGATIVE zero, not the zero.

        Keying the vacuity annotation on the zero count reported 386 subjects
        for a clause that has none, and a corpus containing a negative zero
        would have printed a byte-identical line.
        """
        pos = np.empty((2, 2), dtype=object)
        for i in range(2):
            for j in range(2):
                pos[i, j] = np.float64(-0.0 if (i, j) == (0, 0) else i + j)
        yaw = np.empty(2, dtype=object)
        for i in range(2):
            yaw[i] = np.array([float(i)])
        (tmp_path / "t0").mkdir(parents=True)
        with open(tmp_path / "t0" / "traj_data.pkl", "wb") as fh:
            pickle.dump({"position": pos, "yaw": yaw}, fh)
        assert self._tally(tmp_path).negative_zeros == 1

    def test_a_refusable_cell_is_reported_not_raised(self, tmp_path: Path) -> None:
        """Observing runs before normalisation, so it must not pre-empt a
        located refusal with a bare numpy traceback."""
        root = self._corpus(tmp_path, [np.str_("not-a-number"), np.array([1.0])])
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "vt", Path(__file__).resolve().parents[1] / "scripts" / "verify_tolerance.py"
        )
        assert spec and spec.loader
        vt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vt)
        problems = vt.check_trajectory(root, "t0", vt.Tally())
        assert problems and "REFUSED by the correction" in problems[0]
