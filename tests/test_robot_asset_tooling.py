"""Controls for the robot-asset conversion and admission tooling.

Built and tested against a NON-AUTHORITATIVE local reference description. The
authoritative Yahboom M3 Pro source has not been acquired, so nothing here
establishes anything about the robot. What it establishes is that the machinery
reads geometry from whichever source it is given, measures every collider, and
refuses to admit an asset built from a reference input.

The control that matters most is the F-TWIN-1 reproduction. Isaac's URDF
importer squared every box collider extent -- the chassis loaded as
84 x 55 x 6.4 mm instead of 290 x 235 x 80 mm -- and the builder of the day
missed it because it counted colliders instead of measuring them. These tests
require the validator to catch that exact defect, and to name it.

No geometry constant appears in this file. Expected values are parsed from the
source under test, so swapping the source swaps the expectations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from navfm.isaac.m3pro_asset_builder import (
    AssetBuildRefused,
    ObservedCollider,
    SourceRole,
    emit_provenance,
    reconstruct_colliders,
    request_production_admission,
    validate_colliders,
    write_provenance,
)
from navfm.isaac.urdf_import import (
    UrdfImportRefused,
    parse_source,
    source_closure,
)

REPO = Path(__file__).resolve().parents[1]

#: Parses, and is used to exercise the machinery. REFERENCE_ONLY: this file is
#: not the apparatus and choosing it here is not an apparatus decision.
REFERENCE_URDF = REPO / "assets/robots/yahboom_m3_pro/source/yahboom_m3pro_upstream.urdf"

#: The other local candidate. It is not well-formed XML -- line 20 carries "--"
#: inside a comment, which XML 1.0 section 2.5 forbids -- so it serves as a
#: genuine malformed-source control rather than a synthetic one.
MALFORMED_URDF = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf"


@pytest.fixture(scope="module")
def model() -> Any:
    return parse_source(REFERENCE_URDF)


@pytest.fixture(scope="module")
def specs(model: Any) -> Any:
    return reconstruct_colliders(model)


def _perfect(specs: Any) -> tuple[ObservedCollider, ...]:
    """An asset that matches the source exactly."""
    return tuple(ObservedCollider(s.usd_path, s.link, s.primitive, s.dimensions,
                                  s.translation, s.rotation_rpy) for s in specs)


def _mutate(specs: Any, index: int, **changes: Any) -> tuple[ObservedCollider, ...]:
    observed = list(_perfect(specs))
    base = observed[index]
    observed[index] = ObservedCollider(
        usd_path=changes.get("usd_path", base.usd_path),
        link=changes.get("link", base.link),
        primitive=changes.get("primitive", base.primitive),
        dimensions=changes.get("dimensions", base.dimensions),
        translation=changes.get("translation", base.translation),
        rotation_rpy=changes.get("rotation_rpy", base.rotation_rpy))
    return tuple(observed)


# --- source parsing ----------------------------------------------------------

def test_the_reference_source_parses_and_declares_geometry(model: Any) -> None:
    assert model.links and model.joints and model.collisions
    assert model.sha256


def test_every_collider_carries_dimensions_from_the_source(model: Any) -> None:
    """Nothing is defaulted. A collider with no measurable extent is refused."""
    for element in model.collisions:
        assert element.dimensions
        assert all(d > 0 for d in element.dimensions), element.identity


def test_the_source_closure_is_measured_not_assumed() -> None:
    closure = source_closure(REFERENCE_URDF)
    assert closure["member_count"] >= 1
    assert closure["closure_digest"]
    # The count is whatever resolving the file actually finds.
    assert closure["member_count"] == 1 + closure["external_reference_count"]


def test_the_malformed_local_candidate_is_refused() -> None:
    """A real malformed file, not a synthetic one: '--' inside an XML comment."""
    with pytest.raises(UrdfImportRefused) as excinfo:
        parse_source(MALFORMED_URDF)
    assert excinfo.value.category == "SOURCE_MALFORMED"
    assert excinfo.value.detail.strip()


@pytest.mark.parametrize(("body", "category"), [
    ("<robot name='r'></robot>", "ROBOT_HAS_NO_LINKS"),
    ("<notrobot/>", "SOURCE_MALFORMED"),
    ("<robot name='r'><link name='a'/><link name='a'/></robot>",
     "DUPLICATE_LINK_IDENTITY"),
    ("<robot name='r'><link name='a'><collision><geometry>"
     "<box size='0 1 1'/></geometry></collision></link></robot>",
     "NON_POSITIVE_DIMENSION"),
    ("<robot name='r'><link name='a'><collision><geometry>"
     "<mesh filename='wheel.stl'/></geometry></collision></link></robot>",
     "UNSUPPORTED_COLLISION_PRIMITIVE"),
    ("<robot name='r'><link name='a'><collision><geometry>"
     "<box size='nan 1 1'/></geometry></collision></link></robot>",
     "NON_FINITE_GEOMETRY"),
])
def test_structured_refusal_categories(tmp_path: Path, body: str,
                                       category: str) -> None:
    """Every input fault is named. None of them is a bare assertion."""
    target = tmp_path / "fixture.urdf"
    target.write_text(body)
    with pytest.raises(UrdfImportRefused) as excinfo:
        parse_source(target)
    assert excinfo.value.category == category
    assert excinfo.value.detail.strip()


def test_an_absent_source_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UrdfImportRefused) as excinfo:
        parse_source(tmp_path / "nothing.urdf")
    assert excinfo.value.category == "SOURCE_FILE_ABSENT"


def test_an_unsupported_extension_is_refused(tmp_path: Path) -> None:
    """Xacro must be expanded first, and the expansion recorded as its own source."""
    target = tmp_path / "robot.xacro"
    target.write_text("<robot name='r'><link name='a'/></robot>")
    with pytest.raises(UrdfImportRefused) as excinfo:
        parse_source(target)
    assert excinfo.value.category == "UNSUPPORTED_SOURCE_EXTENSION"


def test_an_unresolvable_package_reference_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "robot.urdf"
    target.write_text("<robot name='r'><link name='a'><visual><geometry>"
                      "<mesh filename='package://x/y.stl'/></geometry>"
                      "</visual></link></robot>")
    with pytest.raises(UrdfImportRefused) as excinfo:
        parse_source(target)
    assert excinfo.value.category == "UNRESOLVED_DEPENDENCY"


# --- reconstruction ----------------------------------------------------------

def test_reconstruction_carries_source_dimensions_unchanged(
    model: Any, specs: Any,
) -> None:
    """Expected values come from the source, never from an import."""
    assert len(specs) == len(model.collisions)
    for element, spec in zip(model.collisions, specs, strict=True):
        assert spec.dimensions == element.dimensions
        assert spec.translation == element.origin_xyz
        assert spec.link == element.link


def test_reconstruction_is_repeatable(model: Any) -> None:
    first = [s.as_dict() for s in reconstruct_colliders(model)]
    second = [s.as_dict() for s in reconstruct_colliders(model)]
    assert first == second


def test_a_source_with_no_colliders_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "bare.urdf"
    target.write_text("<robot name='r'><link name='a'/></robot>")
    with pytest.raises(AssetBuildRefused) as excinfo:
        reconstruct_colliders(parse_source(target))
    assert excinfo.value.category == "NO_COLLISION_GEOMETRY"


# --- the validator, attacked one fault at a time -----------------------------

def test_a_faithful_asset_is_accepted(specs: Any) -> None:
    """The criterion must be able to pass, or the failures below prove nothing."""
    assert validate_colliders(specs, _perfect(specs))["COLLIDER_VALIDATION"] == "PASS"


def test_the_f_twin_1_squared_extent_defect_is_caught(specs: Any) -> None:
    """Mandatory. This is the exact defect that shipped in the admitted asset.

    Box extents squared, cylinders untouched -- the shape F-TWIN-1 measured.
    """
    observed = tuple(
        ObservedCollider(s.usd_path, s.link, s.primitive,
                         tuple(d * d for d in s.dimensions) if s.primitive == "box"
                         else s.dimensions, s.translation, s.rotation_rpy)
        for s in specs)
    result = validate_colliders(specs, observed)
    assert result["COLLIDER_VALIDATION"] == "FAIL"
    assert "COLLIDER_DIMENSION_MISMATCH" in result["failure_categories"]
    squared = [r for r in result["results"]
               if r["VERDICT"] == "FAIL" and "square of the source" in r["detail"]]
    assert squared, "the validator must name the defect, not merely reject it"
    # The cylinders were correct in the real defect and must still pass here.
    assert any(r["VERDICT"] == "PASS" for r in result["results"])


def test_a_scale_fault_is_reported_as_a_scale_fault(specs: Any) -> None:
    """Distinct from a per-value error, so an operator is told which kind."""
    observed = _mutate(specs, 0,
                       dimensions=tuple(d * 100.0 for d in specs[0].dimensions))
    result = validate_colliders(specs, observed)
    assert result["COLLIDER_VALIDATION"] == "FAIL"
    assert "SCALE_OR_DIMENSION_MISMATCH" in result["failure_categories"]


def test_a_transform_fault_is_distinct_from_a_dimension_fault(specs: Any) -> None:
    moved = (specs[0].translation[0] + 0.05, specs[0].translation[1],
             specs[0].translation[2])
    result = validate_colliders(specs, _mutate(specs, 0, translation=moved))
    assert result["COLLIDER_VALIDATION"] == "FAIL"
    assert "COLLIDER_TRANSFORM_MISMATCH" in result["failure_categories"]
    assert "COLLIDER_DIMENSION_MISMATCH" not in result["failure_categories"]


def test_a_rotation_fault_is_caught(specs: Any) -> None:
    turned = (specs[0].rotation_rpy[0] + 0.2, specs[0].rotation_rpy[1],
              specs[0].rotation_rpy[2])
    result = validate_colliders(specs, _mutate(specs, 0, rotation_rpy=turned))
    assert "COLLIDER_TRANSFORM_MISMATCH" in result["failure_categories"]


def test_a_collider_on_the_wrong_link_is_caught(specs: Any) -> None:
    """Geometrically plausible, structurally wrong."""
    result = validate_colliders(specs, _mutate(specs, 0, link="not_this_link"))
    assert "COLLIDER_OWNERSHIP_MISMATCH" in result["failure_categories"]


def test_a_wrong_primitive_type_is_caught(specs: Any) -> None:
    other = "sphere" if specs[0].primitive != "sphere" else "box"
    result = validate_colliders(specs, _mutate(specs, 0, primitive=other))
    assert "COLLIDER_PRIMITIVE_MISMATCH" in result["failure_categories"]


def test_a_missing_collider_is_caught(specs: Any) -> None:
    result = validate_colliders(specs, _perfect(specs)[1:])
    assert "COLLIDER_MISSING" in result["failure_categories"]


def test_an_extra_collider_is_caught(specs: Any) -> None:
    extra = ObservedCollider("/m3pro/ghost/collisions/collision_0", "ghost",
                             "box", (0.1, 0.1, 0.1))
    result = validate_colliders(specs, (*_perfect(specs), extra))
    assert "COLLIDER_UNEXPECTED" in result["failure_categories"]


def test_the_validator_does_not_pass_on_count_alone(specs: Any) -> None:
    """F-TWIN-1's lesson: a collider of the wrong size is still one collider."""
    observed = _mutate(specs, 0,
                       dimensions=tuple(d * 1.5 for d in specs[0].dimensions))
    result = validate_colliders(specs, observed)
    assert result["observed_count"] == result["expected_count"]
    assert result["COLLIDER_VALIDATION"] == "FAIL"


# --- provenance and admission ------------------------------------------------

def test_reference_provenance_is_marked_not_admissible(model: Any, specs: Any) -> None:
    provenance = emit_provenance(
        model=model, closure=source_closure(REFERENCE_URDF),
        source_role=SourceRole.REFERENCE_ONLY, specs=specs)
    assert provenance["source_role"] == "REFERENCE_ONLY"
    assert provenance["production_admissible"] is False
    assert provenance["why_not_admissible"]


def test_a_reference_asset_is_refused_production_admission(
    model: Any, specs: Any,
) -> None:
    """Today's test fixture must not become tomorrow's robot model."""
    provenance = emit_provenance(
        model=model, closure=source_closure(REFERENCE_URDF),
        source_role=SourceRole.REFERENCE_ONLY, specs=specs,
        validation=validate_colliders(specs, _perfect(specs)))
    with pytest.raises(AssetBuildRefused) as excinfo:
        request_production_admission(provenance)
    assert excinfo.value.category == "AUTHORITATIVE_SOURCE_NOT_ESTABLISHED"


def test_authoritative_role_still_needs_vendor_provenance(
    model: Any, specs: Any,
) -> None:
    """Claiming the role is not supplying the evidence."""
    provenance = emit_provenance(
        model=model, closure=source_closure(REFERENCE_URDF),
        source_role=SourceRole.AUTHORITATIVE, specs=specs,
        validation=validate_colliders(specs, _perfect(specs)))
    with pytest.raises(AssetBuildRefused) as excinfo:
        request_production_admission(provenance)
    assert excinfo.value.category == "VENDOR_PROVENANCE_INCOMPLETE"


def test_physical_measurements_are_recorded_as_not_measured(
    model: Any, specs: Any,
) -> None:
    provenance = emit_provenance(
        model=model, closure=source_closure(REFERENCE_URDF),
        source_role=SourceRole.REFERENCE_ONLY, specs=specs)
    for value in provenance["physical_measurements"].values():
        assert value == "NOT_MEASURED"
    for value in provenance["vendor_acquisition"].values():
        assert value == "PENDING"


def test_provenance_writes_and_reads_back(model: Any, specs: Any,
                                          tmp_path: Path) -> None:
    provenance = emit_provenance(
        model=model, closure=source_closure(REFERENCE_URDF),
        source_role=SourceRole.REFERENCE_ONLY, specs=specs)
    sha = write_provenance(tmp_path / "m3pro.asset.json", provenance)
    assert sha
    back = json.loads((tmp_path / "m3pro.asset.json").read_text())
    assert back["production_admissible"] is False


def test_an_unknown_source_role_is_refused(model: Any, specs: Any) -> None:
    with pytest.raises(AssetBuildRefused) as excinfo:
        emit_provenance(model=model, closure=source_closure(REFERENCE_URDF),
                        source_role="CANONICAL", specs=specs)
    assert excinfo.value.category == "UNKNOWN_SOURCE_ROLE"


# --- the future swap ---------------------------------------------------------

def test_the_tooling_is_source_driven_not_hard_coded(tmp_path: Path) -> None:
    """Two sources, same machinery, different expectations and different hashes.

    This is what makes the vendor archive a source substitution rather than
    another development tranche.
    """
    a = tmp_path / "a.urdf"
    b = tmp_path / "b.urdf"
    a.write_text("<robot name='a'><link name='base'><collision><geometry>"
                 "<box size='0.1 0.2 0.3'/></geometry></collision></link></robot>")
    b.write_text("<robot name='b'><link name='base'><collision><geometry>"
                 "<box size='0.4 0.5 0.6'/></geometry></collision></link></robot>")

    model_a, model_b = parse_source(a), parse_source(b)
    specs_a, specs_b = reconstruct_colliders(model_a), reconstruct_colliders(model_b)

    assert model_a.sha256 != model_b.sha256
    assert specs_a[0].dimensions != specs_b[0].dimensions
    # Each source validates against itself and not against the other.
    assert validate_colliders(specs_a, _perfect(specs_a))["COLLIDER_VALIDATION"] == "PASS"
    assert validate_colliders(specs_a, _perfect(specs_b))["COLLIDER_VALIDATION"] == "FAIL"


def test_no_geometry_constant_is_hard_coded_in_the_tooling() -> None:
    """The disputed values must not appear in the builder or the importer."""
    for module in ("src/navfm/isaac/urdf_import.py",
                   "src/navfm/isaac/m3pro_asset_builder.py"):
        text = (REPO / module).read_text()
        for literal in ("0.048", "0.040", "0.280", "0.100", "0.290", "0.235"):
            assert literal not in text, f"{module} hard-codes {literal}"
