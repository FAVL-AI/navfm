"""BO-10 is excluded from the E2 population by construction, not by wording.

`gates/BO10/bo10_e2_scope_declaration_20260907.md` freezes the decision. This
suite is the mechanism's proof, and its centre is one mandatory negative
control: offering the BO-10 manifest to an E2 consumer must FAIL.

Both directions are proved, because a guard that cannot pass gets deleted by
whoever is in a hurry, and a guard that cannot fail certifies nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from navfm.collection.scope import (
    BO10_SCOPE_DECLARATION,
    BO10_SCOPE_DECLARATION_SHA256,
    CollectionPurpose,
    CollectionScope,
    E2ScopeViolation,
    ScopeDeclarationError,
    assert_e2_admissible,
    authorise_g2_acknowledgement,
    bo10_scope,
    scope_of,
    select_e2_population,
)

REPO = Path(__file__).resolve().parents[1]

E2_MANIFEST = {
    "purpose": "E2_REGISTERED_CELL",
    "e2_eligible": True,
}


def bo10_manifest() -> dict[str, object]:
    return dict(bo10_scope().to_manifest_fields())


class TestTheMandatoryNegativeControl:
    def test_the_bo10_trajectory_is_rejected_by_an_e2_consumer(self) -> None:
        """BO-10 -> E2 population inclusion attempt -> FAIL. The frozen control."""
        with pytest.raises(E2ScopeViolation) as exc:
            assert_e2_admissible(bo10_manifest(), label="hospital_bo10_run_00000")
        message = str(exc.value)
        assert "excluded from the E2 population by construction" in message
        assert "BO10_FRAMEWORK_COMPATIBILITY" in message
        assert "hospital_bo10_run_00000" in message

    def test_the_same_consumer_admits_a_registered_e2_cell(self) -> None:
        """The other direction: the guard is capable of passing."""
        assert_e2_admissible(E2_MANIFEST, label="e2_cell_a1")

    def test_the_exclusion_reason_travels_with_the_refusal(self) -> None:
        with pytest.raises(E2ScopeViolation, match="outside the preregistered E2 population"):
            assert_e2_admissible(bo10_manifest())


class TestUndeclaredIsRefusedNotAdmitted:
    """Absence of a scope block must never read as eligibility (the FL-019 shape)."""

    def test_a_manifest_with_no_purpose_is_refused(self) -> None:
        with pytest.raises(E2ScopeViolation, match="declares no collection purpose"):
            assert_e2_admissible({"n_episodes": 1})

    def test_a_purpose_without_an_eligibility_field_is_refused(self) -> None:
        with pytest.raises(E2ScopeViolation, match="no e2_eligible field"):
            assert_e2_admissible({"purpose": "E2_REGISTERED_CELL"})

    def test_a_truthy_string_does_not_pass_for_a_bool(self) -> None:
        """'false' is truthy; admitting it would invert the field it reads."""
        with pytest.raises(E2ScopeViolation, match="must be a bool"):
            assert_e2_admissible({"purpose": "E2_REGISTERED_CELL", "e2_eligible": "false"})

    def test_an_unknown_purpose_is_refused(self) -> None:
        with pytest.raises(E2ScopeViolation, match="unknown collection purpose"):
            assert_e2_admissible({"purpose": "SOMETHING_ELSE", "e2_eligible": True})


class TestContradictionsAreRefusedNotResolved:
    def test_bo10_claiming_eligibility_is_refused(self) -> None:
        with pytest.raises(ScopeDeclarationError, match="self-contradictory"):
            CollectionScope(
                purpose=CollectionPurpose.BO10_FRAMEWORK_COMPATIBILITY,
                e2_eligible=True,
            )

    def test_an_e2_cell_claiming_exclusion_is_refused(self) -> None:
        with pytest.raises(ScopeDeclarationError, match="self-contradictory"):
            CollectionScope(
                purpose=CollectionPurpose.E2_REGISTERED_CELL,
                e2_eligible=False,
                e2_exclusion_reason="whatever",
            )

    def test_an_exclusion_must_carry_its_reason(self) -> None:
        with pytest.raises(ScopeDeclarationError, match="must record why it is excluded"):
            CollectionScope(
                purpose=CollectionPurpose.BO10_FRAMEWORK_COMPATIBILITY,
                e2_eligible=False,
                e2_exclusion_reason=None,
            )


class TestPopulationSelectionRecordsWhatItDropped:
    def test_bo10_is_excluded_with_a_reason_and_e2_cells_survive(self) -> None:
        population = select_e2_population(
            [
                ("e2_cell_a1", E2_MANIFEST),
                ("hospital_bo10_run_00000", bo10_manifest()),
                ("e2_cell_b2", E2_MANIFEST),
            ]
        )
        assert population.admitted == ("e2_cell_a1", "e2_cell_b2")
        assert population.n_excluded == 1
        dropped_id, reason = population.excluded[0]
        assert dropped_id == "hospital_bo10_run_00000"
        assert "BO10_FRAMEWORK_COMPATIBILITY" in reason

    def test_an_undeclared_trajectory_is_dropped_rather_than_silently_kept(self) -> None:
        population = select_e2_population([("mystery", {"n_episodes": 3})])
        assert population.admitted == ()
        assert population.n_excluded == 1


class TestTheG2AcknowledgementIsBoundToTheDeclaration:
    def test_the_frozen_declaration_authorises_the_bo10_scope(self) -> None:
        scope = authorise_g2_acknowledgement(REPO / BO10_SCOPE_DECLARATION)
        assert scope.purpose is CollectionPurpose.BO10_FRAMEWORK_COMPATIBILITY
        assert scope.e2_eligible is False
        assert scope.declaration_sha256 == BO10_SCOPE_DECLARATION_SHA256

    def test_an_edited_declaration_is_refused(self, tmp_path: Path) -> None:
        """The negative control for the digest binding."""
        original = json.loads((REPO / BO10_SCOPE_DECLARATION).read_text())
        original["e2_status"]["e2_eligible"] = True
        edited = tmp_path / "edited.json"
        edited.write_text(json.dumps(original, indent=2))
        with pytest.raises(ScopeDeclarationError, match="has digest"):
            authorise_g2_acknowledgement(edited)

    def test_a_missing_declaration_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ScopeDeclarationError, match="no file at"):
            authorise_g2_acknowledgement(tmp_path / "absent.json")

    def test_a_declaration_for_another_purpose_is_refused(self, tmp_path: Path) -> None:
        record = json.loads((REPO / BO10_SCOPE_DECLARATION).read_text())
        record["purpose"]["id"] = "E2_REGISTERED_CELL"
        other = tmp_path / "other.json"
        other.write_text(json.dumps(record, indent=2))
        digest = hashlib.sha256(other.read_bytes()).hexdigest()
        with pytest.raises(ScopeDeclarationError, match="authorised for BO10"):
            authorise_g2_acknowledgement(other, expected_sha256=digest)


class TestTheFrozenDeclarationIsIntact:
    def test_the_declaration_matches_its_pinned_digest(self) -> None:
        """Editing the declaration without re-freezing it fails here, not silently."""
        path = REPO / BO10_SCOPE_DECLARATION
        assert path.is_file(), "the frozen BO-10 scope declaration is missing"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == BO10_SCOPE_DECLARATION_SHA256

    def test_the_declaration_states_the_exclusion_it_exists_to_impose(self) -> None:
        record = json.loads((REPO / BO10_SCOPE_DECLARATION).read_text())
        assert record["e2_status"]["e2_eligible"] is False
        assert record["e2_status"]["status"] == "EXCLUDED"
        assert record["purpose"]["id"] == "BO10_FRAMEWORK_COMPATIBILITY"

    def test_the_declaration_leaves_the_four_deferred_e2_decisions_untouched(self) -> None:
        record = json.loads((REPO / BO10_SCOPE_DECLARATION).read_text())
        untouched = record["e2_deferred_decisions_untouched"]["untouched"]
        for decision in ("E2 estimator", "E2 tolerance", "E2 held-out scene count",
                         "E2 per-cell episode count"):
            assert decision in untouched

    def test_the_markdown_declaration_carries_the_same_digest(self) -> None:
        """The prose and the machine record must not drift apart."""
        md = (REPO / "gates/BO10/bo10_e2_scope_declaration_20260907.md").read_text()
        assert BO10_SCOPE_DECLARATION_SHA256 in md


class TestScopeRoundTrip:
    def test_manifest_fields_reparse_to_the_same_scope(self) -> None:
        scope = bo10_scope(declaration_path="gates/BO10/x.json", declaration_sha256="abc")
        assert scope_of(scope.to_manifest_fields()) == scope
