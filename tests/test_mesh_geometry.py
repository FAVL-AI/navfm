"""Controls for mesh measurement and collider validation.

The validator's whole reason to exist is F-TWIN-1: Isaac's importer squared
every box collider extent, and the check meant to catch it counted colliders
instead of measuring them. So the first control here reproduces that exact
corruption and requires a refusal, and several others make sure the validator
cannot be satisfied by a count, an aggregate bound or a total volume.

Fixtures are synthetic STL written by the test. No vendor mesh is read here, so
the controls run anywhere and prove the rules rather than the robot.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from navfm.isaac.mesh_geometry import (
    ColliderRefused,
    convex_hull_measure,
    hull_backend,
    measure_mesh,
    read_binary_stl,
    transform_bounds,
    validate_collider_set,
)


def write_box_stl(path: Path, extents: tuple[float, float, float],
                  origin: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> Path:
    """A closed axis-aligned box as binary STL, 12 triangles."""
    ex, ey, ez = (e / 2 for e in extents)
    ox, oy, oz = origin
    corner = np.array([[ox + sx * ex, oy + sy * ey, oz + sz * ez]
                       for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
             (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    payload = bytearray(b"\0" * 80 + struct.pack("<I", len(faces)))
    for a, b, c in faces:
        payload += struct.pack("<3f", 0.0, 0.0, 0.0)
        for index in (a, b, c):
            payload += struct.pack("<3f", *corner[index])
        payload += struct.pack("<H", 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(payload))
    return path


def source_entry(path: Path) -> dict[str, object]:
    measured = measure_mesh(path)
    return {"sha256": measured.sha256, "extents": list(measured.extents)}


def collider_from(path: Path, extents: list[float] | None = None,
                  sha: str | None = None) -> dict[str, object]:
    measured = measure_mesh(path)
    return {"source_sha256": sha or measured.sha256,
            "extents": extents if extents is not None else list(measured.extents)}


# -- measurement -----------------------------------------------------------


def test_a_box_mesh_measures_its_own_extents(tmp_path: Path) -> None:
    mesh = write_box_stl(tmp_path / "box.STL", (0.4, 0.2, 0.1))
    measured = measure_mesh(mesh)
    assert measured.mesh_format == "STL_BINARY"
    assert measured.triangle_count == 12
    assert measured.unique_vertex_count == 8
    assert np.allclose(measured.extents, (0.4, 0.2, 0.1))
    assert measured.is_closed_estimate is True
    assert np.isclose(abs(measured.signed_volume), 0.4 * 0.2 * 0.1)


def test_stl_carries_no_unit_declaration(tmp_path: Path) -> None:
    """The format states no unit, so the record must not imply one."""
    mesh = write_box_stl(tmp_path / "box.STL", (1.0, 1.0, 1.0))
    assert measure_mesh(mesh).unit_metadata == "ABSENT"


def test_mesh_values_are_labelled_as_mesh_derived(tmp_path: Path) -> None:
    """A measured value must never read as a vendor-specified one."""
    mesh = write_box_stl(tmp_path / "box.STL", (1.0, 1.0, 1.0))
    assert measure_mesh(mesh).evidence_class == "VENDOR_MESH_DERIVED_VALUE"


def test_a_truncated_file_is_refused(tmp_path: Path) -> None:
    mesh = write_box_stl(tmp_path / "box.STL", (1.0, 1.0, 1.0))
    mesh.write_bytes(mesh.read_bytes()[:-20])
    with pytest.raises(ColliderRefused) as refusal:
        read_binary_stl(mesh)
    assert refusal.value.category == "NON_FINITE_GEOMETRY"


def test_an_absent_mesh_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ColliderRefused) as refusal:
        read_binary_stl(tmp_path / "nothing.STL")
    assert refusal.value.category == "SOURCE_IDENTITY_MISMATCH"


def test_rotating_a_mesh_transforms_its_corners_not_its_box(tmp_path: Path) -> None:
    """A quarter turn about z swaps x and y exactly; boxing first would grow."""
    mesh = write_box_stl(tmp_path / "box.STL", (0.4, 0.2, 0.1))
    turned = transform_bounds(measure_mesh(mesh), rpy=(0.0, 0.0, np.pi / 2))
    assert np.allclose(turned["extents"], (0.2, 0.4, 0.1), atol=1e-6)


# -- the historical defect -------------------------------------------------


def test_f_twin_1_squared_extents_are_refused(tmp_path: Path) -> None:
    """The exact corruption F-TWIN-1 measured: every extent squared.

    At these magnitudes squaring shrinks rather than grows, which is why a
    reviewer looking at plausible small numbers would not notice, and why the
    check has to compare against the source instead of looking reasonable.
    """
    mesh = write_box_stl(tmp_path / "base.STL", (0.4, 0.2, 0.1))
    source = {"base_link": source_entry(mesh)}
    squared = [float(v) ** 2 for v in source["base_link"]["extents"]]  # type: ignore[union-attr]
    report = validate_collider_set(
        source, {"base_link": collider_from(mesh, extents=squared)},
        require_containment=False)
    assert report["ADMITTED"] is False
    assert report["findings"][0]["category"] == "DIMENSION_MISMATCH"


def test_a_correct_collider_is_admitted(tmp_path: Path) -> None:
    """The positive control: the check must be able to pass."""
    mesh = write_box_stl(tmp_path / "base.STL", (0.4, 0.2, 0.1))
    report = validate_collider_set({"base_link": source_entry(mesh)},
                                   {"base_link": collider_from(mesh)})
    assert report["ADMITTED"] is True
    assert report["finding_count"] == 0


# -- unit scale ------------------------------------------------------------


@pytest.mark.parametrize(("factor", "label"), [
    (1000.0, "x1000"), (0.001, "/1000"), (100.0, "x100"), (0.01, "/100")])
def test_unit_scale_corruption_is_refused_and_named(
        tmp_path: Path, factor: float, label: str) -> None:
    mesh = write_box_stl(tmp_path / "base.STL", (0.4, 0.2, 0.1))
    source = {"base_link": source_entry(mesh)}
    scaled = [float(v) * factor for v in source["base_link"]["extents"]]  # type: ignore[union-attr]
    report = validate_collider_set(
        source, {"base_link": collider_from(mesh, extents=scaled)},
        require_containment=False)
    assert report["ADMITTED"] is False
    assert report["findings"][0]["category"] == "UNIT_SCALE_MISMATCH"
    assert label in report["findings"][0]["detail"]


# -- axis and transform ----------------------------------------------------


@pytest.mark.parametrize("permutation", [(1, 0, 2), (2, 1, 0), (0, 2, 1)])
def test_axis_permutation_is_refused_as_orientation_not_size(
        tmp_path: Path, permutation: tuple[int, int, int]) -> None:
    """Same extents on different axes: a permuted collider, not a resized one."""
    mesh = write_box_stl(tmp_path / "base.STL", (0.4, 0.2, 0.1))
    source = {"base_link": source_entry(mesh)}
    extents = list(source["base_link"]["extents"])  # type: ignore[arg-type]
    swapped = [float(extents[i]) for i in permutation]
    report = validate_collider_set(
        source, {"base_link": collider_from(mesh, extents=swapped)},
        require_containment=False)
    assert report["ADMITTED"] is False
    assert report["findings"][0]["category"] == "ORIENTATION_MISMATCH"


def test_a_collider_smaller_than_its_source_violates_containment(
        tmp_path: Path) -> None:
    mesh = write_box_stl(tmp_path / "base.STL", (0.4, 0.2, 0.1))
    source = {"base_link": source_entry(mesh)}
    shrunk = [float(v) * 0.9 for v in source["base_link"]["extents"]]  # type: ignore[union-attr]
    report = validate_collider_set(
        source, {"base_link": collider_from(mesh, extents=shrunk)})
    categories = {f["category"] for f in report["findings"]}
    assert "CONTAINMENT_VIOLATION" in categories


# -- identity and set shape ------------------------------------------------


def test_the_wrong_mesh_of_similar_size_is_refused_on_identity(
        tmp_path: Path) -> None:
    """Binding is to the source hash, not to approximate dimensions."""
    owned = write_box_stl(tmp_path / "lwheel1.STL", (0.08, 0.08, 0.03))
    other = write_box_stl(tmp_path / "rwheel1.STL", (0.08, 0.08, 0.0300001))
    report = validate_collider_set(
        {"lwheel1": source_entry(owned)},
        {"lwheel1": collider_from(other)}, require_containment=False)
    assert report["ADMITTED"] is False
    assert report["findings"][0]["category"] == "SOURCE_IDENTITY_MISMATCH"


def test_a_dropped_collider_is_refused(tmp_path: Path) -> None:
    first = write_box_stl(tmp_path / "a.STL", (0.4, 0.2, 0.1))
    second = write_box_stl(tmp_path / "b.STL", (0.1, 0.1, 0.1))
    report = validate_collider_set(
        {"base_link": source_entry(first), "arm1": source_entry(second)},
        {"base_link": collider_from(first)})
    assert report["ADMITTED"] is False
    assert {f["category"] for f in report["findings"]} == {"MISSING_COLLIDER"}


def test_a_duplicated_collider_with_one_dropped_is_refused(tmp_path: Path) -> None:
    """Equal totals must not pass: the count is right and the set is wrong."""
    first = write_box_stl(tmp_path / "a.STL", (0.4, 0.2, 0.1))
    second = write_box_stl(tmp_path / "b.STL", (0.1, 0.1, 0.1))
    source = {"base_link": source_entry(first), "arm1": source_entry(second)}
    generated = {"base_link": collider_from(first), "arm1": collider_from(first)}
    assert len(generated) == len(source)
    report = validate_collider_set(source, generated, require_containment=False)
    assert report["ADMITTED"] is False
    categories = {f["category"] for f in report["findings"]}
    assert "DUPLICATE_COLLIDER_OWNERSHIP" in categories


def test_an_unexpected_collider_is_refused(tmp_path: Path) -> None:
    mesh = write_box_stl(tmp_path / "a.STL", (0.4, 0.2, 0.1))
    extra = write_box_stl(tmp_path / "ghost.STL", (0.1, 0.1, 0.1))
    report = validate_collider_set(
        {"base_link": source_entry(mesh)},
        {"base_link": collider_from(mesh), "phantom": collider_from(extra)})
    assert report["ADMITTED"] is False
    assert "UNEXPECTED_COLLIDER" in {f["category"] for f in report["findings"]}


def test_equal_aggregate_bounds_do_not_admit_a_wrong_set(tmp_path: Path) -> None:
    """Two links swapping colliders keeps every aggregate identical."""
    first = write_box_stl(tmp_path / "a.STL", (0.4, 0.2, 0.1))
    second = write_box_stl(tmp_path / "b.STL", (0.1, 0.2, 0.4))
    source = {"link_a": source_entry(first), "link_b": source_entry(second)}
    swapped = {"link_a": collider_from(second), "link_b": collider_from(first)}
    report = validate_collider_set(source, swapped, require_containment=False)
    assert report["ADMITTED"] is False
    assert {f["category"] for f in report["findings"]} == {
        "SOURCE_IDENTITY_MISMATCH"}


# -- hull ------------------------------------------------------------------


def test_hull_backend_reports_absence_rather_than_skipping() -> None:
    """Whether hulls can be measured is itself evidence, so it is reported."""
    backend = hull_backend()
    assert "AVAILABLE" in backend
    if not backend["AVAILABLE"]:
        assert "NOT_MEASURED" in backend["consequence"]


def test_a_boxs_hull_equals_the_box_when_a_backend_exists(tmp_path: Path) -> None:
    mesh = write_box_stl(tmp_path / "box.STL", (0.4, 0.2, 0.1))
    result = convex_hull_measure(read_binary_stl(mesh))
    if not result["MEASURED"]:
        assert result["AVAILABLE"] is False
        return
    assert np.allclose(result["hull_extents"], (0.4, 0.2, 0.1), atol=1e-6)
    assert np.isclose(result["hull_volume"], 0.4 * 0.2 * 0.1, rtol=1e-6)
    assert result["hull_vertex_count"] == 8
