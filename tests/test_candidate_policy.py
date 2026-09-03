"""The intervention set is the experiment, so it is tested as one.

Every numeric expectation is read from
``gates/scenes/candidate_policy_expected_semantics.json``, which was written
before this implementation existed. Recomputing an expectation from the module
under test would verify the implementation against itself (FL-018), so the
frozen record is the oracle and this file only compares against it.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from navfm.candidate_policy import (
    BLOCKER,
    DEFAULT_POLICY,
    POLICY_VERSION,
    RETIRED_POLICY_DIGESTS,
    SUPPORT,
    Aabb,
    Candidate,
    CandidateSet,
    Policy,
    PolicyError,
    Role,
    Variant,
    causality_control,
    generate_candidates,
    policy_digest,
    provenance,
    shared_origin_control,
)

EXPECT = json.loads(
    (Path(__file__).resolve().parents[1] / "gates" / "scenes"
     / "candidate_policy_expected_semantics.json").read_text()
)
VALUES: dict[str, Any] = EXPECT["expected_values"]

TARGET = VALUES["target_id"]
BOX = Aabb(tuple(VALUES["box"]["bounds_min"]), tuple(VALUES["box"]["bounds_max"]))  # type: ignore[arg-type]

TOL = 1e-9


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOL


class TestTheFrozenRecordIsUsable:
    """If the oracle is not what it claims, nothing below it means anything."""

    def test_the_record_declares_it_was_written_first(self) -> None:
        assert EXPECT["written_before_execution"] is True

    def test_the_retired_digest_is_named_and_not_in_use(self) -> None:
        assert EXPECT["supersedes"]["policy_digest"] in RETIRED_POLICY_DIGESTS
        assert policy_digest() not in RETIRED_POLICY_DIGESTS


class TestBlockerGeneration:
    def test_four_faces_in_the_frozen_order(self) -> None:
        faces = [c.face for c in generate_candidates(TARGET, Role.BLOCKER, BOX).candidates]
        assert faces == [e["face"] for e in VALUES["BLOCKER_DEFAULT"]]

    def test_origins_directions_and_ranges_match_the_frozen_values(self) -> None:
        got = generate_candidates(TARGET, Role.BLOCKER, BOX).candidates
        for c, e in zip(got, VALUES["BLOCKER_DEFAULT"], strict=True):
            assert all(_close(a, b) for a, b in zip(c.origin, e["origin"], strict=True)), c.face
            assert list(c.direction) == e["direction"], c.face
            assert _close(c.max_range, e["max_range"]), c.face
            assert c.valid is e["valid"]

    def test_ordering_is_deterministic(self) -> None:
        a = generate_candidates(TARGET, Role.BLOCKER, BOX)
        b = generate_candidates(TARGET, Role.BLOCKER, BOX)
        assert [c.candidate_id for c in a.candidates] == [c.candidate_id for c in b.candidates]
        assert [c.origin for c in a.candidates] == [c.origin for c in b.candidates]
        assert a.digest == b.digest

    def test_identity_is_deterministic_and_carries_the_policy(self) -> None:
        cs = generate_candidates(TARGET, Role.BLOCKER, BOX)
        for c in cs.candidates:
            assert c.candidate_id == f"{TARGET}#BLOCKER#{c.face}#{policy_digest()}"

    def test_logical_population_is_fixed_at_four(self) -> None:
        assert len(generate_candidates(TARGET, Role.BLOCKER, BOX).candidates) == 4
        wide = Aabb((0.0, 0.0, 0.0), (50.0, 50.0, 9.0))
        assert len(generate_candidates(TARGET, Role.BLOCKER, wide).candidates) == 4

    def test_no_vertical_blocker_faces(self) -> None:
        cs = generate_candidates(TARGET, Role.BLOCKER, BOX)
        assert all(c.direction[2] == 0.0 for c in cs.candidates)


class TestInvalidGeometryStaysRepresented:
    def test_a_degenerate_axis_yields_invalid_candidates_that_are_retained(self) -> None:
        d = VALUES["DEGENERATE_BOX"]
        cs = generate_candidates(TARGET, Role.BLOCKER,
                                 Aabb(tuple(d["bounds_min"]), tuple(d["bounds_max"])))  # type: ignore[arg-type]
        assert len(cs.candidates) == d["logical_population"]
        assert len(cs.valid_candidates) == d["valid_count"]
        assert [c.face for c in cs.candidates if not c.valid] == d["invalid_faces"]

    def test_an_invalid_candidate_states_why(self) -> None:
        cs = generate_candidates(TARGET, Role.BLOCKER, Aabb((0.0, 0.0, 0.0), (0.0, 2.0, 0.5)))
        assert all("degenerate" in c.invalid_reason for c in cs.candidates if not c.valid)
        assert all(c.invalid_reason == "" for c in cs.candidates if c.valid)


class TestSupportGeneration:
    def test_support_is_interrogated_from_above(self) -> None:
        cs = generate_candidates(TARGET, Role.SUPPORT, BOX)
        e = VALUES["SUPPORT_DEFAULT"][0]
        assert len(cs.candidates) == 1
        c = cs.candidates[0]
        assert c.face == e["face"]
        assert list(c.direction) == e["direction"]
        assert all(_close(a, b) for a, b in zip(c.origin, e["origin"], strict=True))
        assert _close(c.max_range, e["max_range"])

    def test_the_support_origin_is_above_the_surface_it_probes(self) -> None:
        c = generate_candidates(TARGET, Role.SUPPORT, BOX).candidates[0]
        assert c.origin[2] > BOX.maximum[2]

    def test_support_identity_is_deterministic(self) -> None:
        a = generate_candidates(TARGET, Role.SUPPORT, BOX)
        b = generate_candidates(TARGET, Role.SUPPORT, BOX)
        assert a.candidates[0].candidate_id == b.candidates[0].candidate_id
        assert a.digest == b.digest

    def test_support_and_blocker_are_different_experiments(self) -> None:
        s = generate_candidates(TARGET, Role.SUPPORT, BOX)
        b = generate_candidates(TARGET, Role.BLOCKER, BOX)
        assert s.digest != b.digest
        assert s.candidates[0].candidate_id != b.candidates[0].candidate_id
        assert SUPPORT.faces != BLOCKER.faces

    def test_support_range_is_the_value_the_audits_fired(self) -> None:
        """1.50 m, not the robot-pose oracle's 1.00 m that version 2 froze."""
        assert _close(SUPPORT.probe_length_m, EXPECT["roles"]["SUPPORT"]["probe_length_m"])
        assert _close(SUPPORT.probe_length_m, 1.50)


class TestControlVariants:
    @pytest.mark.parametrize("case", VALUES["BLOCKER_CAUSALITY_CONTROL_PLUS_X"],
                             ids=lambda c: f"standoff-{c['standoff_m']}")
    def test_causality_control_at_each_measured_standoff(self, case: dict[str, Any]) -> None:
        cs = generate_candidates(TARGET, Role.BLOCKER, BOX,
                                 policy=causality_control(case["standoff_m"]))
        plus_x = cs.candidates[0]
        assert plus_x.face == "+X"
        assert all(_close(a, b) for a, b in zip(plus_x.origin, case["origin"], strict=True))
        assert _close(plus_x.max_range, case["max_range"])

    def test_causality_control_keeps_the_four_face_population(self) -> None:
        cs = generate_candidates(TARGET, Role.BLOCKER, BOX, policy=causality_control(1.0))
        assert [c.face for c in cs.candidates] == list(BLOCKER.faces)

    def test_shared_origin_control_matches_the_retired_construction(self) -> None:
        e = VALUES["BLOCKER_SHARED_ORIGIN_CONTROL"][0]
        cs = generate_candidates(TARGET, Role.BLOCKER, BOX,
                                 policy=shared_origin_control(e["max_range_m"]))
        assert len(cs.candidates) == e["population"]
        c = cs.candidates[0]
        assert all(_close(a, b) for a, b in zip(c.origin, e["origin"], strict=True))
        assert list(c.direction) == e["direction"]
        assert _close(c.max_range, e["max_range"])

    def test_a_control_variant_does_not_mutate_the_production_default(self) -> None:
        before = policy_digest()
        before_faces = tuple(BLOCKER.faces)
        causality_control(1.5)
        shared_origin_control(40.0)
        assert policy_digest() == before
        assert tuple(DEFAULT_POLICY.blocker.faces) == before_faces
        assert _close(DEFAULT_POLICY.blocker.standoff_m, 0.30)
        assert DEFAULT_POLICY.variant is Variant.DEFAULT

    def test_production_default_cannot_reach_a_control_by_accident(self) -> None:
        cs = generate_candidates(TARGET, Role.BLOCKER, BOX)
        assert cs.policy.variant is Variant.DEFAULT
        assert cs.candidates[0].origin != tuple(VALUES["BLOCKER_SHARED_ORIGIN_CONTROL"][0]["origin"])

    def test_controls_are_blocker_only_and_say_so(self) -> None:
        for policy in (causality_control(1.0), shared_origin_control(40.0)):
            with pytest.raises(PolicyError, match="does not define an intervention"):
                generate_candidates(TARGET, Role.SUPPORT, BOX, policy=policy)

    def test_a_control_needs_a_positive_parameter(self) -> None:
        with pytest.raises(PolicyError):
            causality_control(0.0)
        with pytest.raises(PolicyError):
            shared_origin_control(-1.0)


class TestDigestSensitivity:
    """Any change to the physics must change the digest, or provenance is a label."""

    def test_changing_the_standoff_changes_the_digest(self) -> None:
        assert causality_control(0.5).digest() != policy_digest()
        assert causality_control(0.5).digest() != causality_control(1.0).digest()

    def test_changing_a_range_changes_the_digest(self) -> None:
        moved = dataclasses.replace(
            DEFAULT_POLICY,
            support=dataclasses.replace(DEFAULT_POLICY.support, probe_length_m=1.0))
        assert moved.digest() != policy_digest()

    def test_changing_the_face_set_changes_the_digest(self) -> None:
        two_face = dataclasses.replace(
            DEFAULT_POLICY,
            blocker=dataclasses.replace(DEFAULT_POLICY.blocker, faces=("+X", "-X")))
        assert two_face.digest() != policy_digest()

    def test_changing_the_variant_changes_the_digest(self) -> None:
        assert shared_origin_control(40.0).digest() != policy_digest()

    def test_role_changes_evidence_identity_even_at_one_policy(self) -> None:
        b = generate_candidates(TARGET, Role.BLOCKER, BOX)
        s = generate_candidates(TARGET, Role.SUPPORT, BOX)
        assert b.digest != s.digest
        assert {c.candidate_id for c in b.candidates}.isdisjoint(
            {c.candidate_id for c in s.candidates})

    def test_the_digest_is_stable_and_short(self) -> None:
        assert policy_digest() == policy_digest() == DEFAULT_POLICY.digest()
        assert len(policy_digest()) == 16


class TestObservationIndependence:
    """The generator defines the experiment; it does not interpret the outcome."""

    def test_the_signature_admits_no_observation(self) -> None:
        params = set(inspect.signature(generate_candidates).parameters)
        assert params == {"target_id", "role", "subject", "policy"}

    def test_no_candidate_field_can_hold_an_observation(self) -> None:
        forbidden = {"hit", "collider", "distance", "actual", "result", "normal",
                     "identity_match", "verdict", "pass", "fail", "outcome", "hit_point"}
        for cls in (Candidate, CandidateSet, Policy):
            names = {f.name for f in dataclasses.fields(cls)}
            assert not (names & forbidden), cls.__name__

    def test_no_policy_dataclass_can_hold_an_observation(self) -> None:
        forbidden = {"hit", "collider", "distance", "actual", "result", "verdict"}
        for field in dataclasses.fields(Policy):
            value = getattr(DEFAULT_POLICY, field.name)
            if dataclasses.is_dataclass(value):
                assert not ({f.name for f in dataclasses.fields(value)} & forbidden)

    def test_generation_is_unaffected_by_anything_that_happened_before(self) -> None:
        first = generate_candidates(TARGET, Role.BLOCKER, BOX).digest
        generate_candidates("/W/OTHER", Role.BLOCKER, Aabb((9.0, 9.0, 9.0), (10.0, 10.0, 10.0)))
        generate_candidates(TARGET, Role.BLOCKER, BOX, policy=causality_control(1.5))
        assert generate_candidates(TARGET, Role.BLOCKER, BOX).digest == first


class TestFiniteness:
    def test_the_candidate_tuple_cannot_grow(self) -> None:
        cs = generate_candidates(TARGET, Role.BLOCKER, BOX)
        assert isinstance(cs.candidates, tuple)
        with pytest.raises(AttributeError):
            cs.candidates.append(cs.candidates[0])  # type: ignore[attr-defined]

    def test_the_set_cannot_be_rebound(self) -> None:
        cs = generate_candidates(TARGET, Role.BLOCKER, BOX)
        with pytest.raises(dataclasses.FrozenInstanceError):
            cs.candidates = ()  # type: ignore[misc]

    def test_a_candidate_cannot_be_edited_after_generation(self) -> None:
        c = generate_candidates(TARGET, Role.SUPPORT, BOX).candidates[0]
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.max_range = 99.0  # type: ignore[misc]

    def test_every_role_has_the_frozen_logical_population(self) -> None:
        assert len(generate_candidates(TARGET, Role.BLOCKER, BOX).candidates) == \
            EXPECT["roles"]["BLOCKER"]["logical_population"]
        assert len(generate_candidates(TARGET, Role.SUPPORT, BOX).candidates) == \
            EXPECT["roles"]["SUPPORT"]["logical_population"]


class TestCanonicalRecord:
    def test_the_same_input_serialises_byte_identically(self) -> None:
        a = generate_candidates(TARGET, Role.BLOCKER, BOX).to_json()
        b = generate_candidates(TARGET, Role.BLOCKER, BOX).to_json()
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_the_record_names_the_policy_that_produced_it(self) -> None:
        j = generate_candidates(TARGET, Role.SUPPORT, BOX, policy=DEFAULT_POLICY).to_json()
        assert j["candidate_policy_digest"] == policy_digest()
        assert j["variant"] == "DEFAULT"
        assert j["policy_version"] == POLICY_VERSION == 4

    def test_a_control_record_is_distinguishable_from_a_production_one(self) -> None:
        prod = generate_candidates(TARGET, Role.BLOCKER, BOX).to_json()
        ctrl = generate_candidates(TARGET, Role.BLOCKER, BOX,
                                   policy=causality_control(1.5)).to_json()
        assert ctrl["variant"] == "CAUSALITY_CONTROL" != prod["variant"]
        assert ctrl["candidate_policy_digest"] != prod["candidate_policy_digest"]
        assert ctrl["candidate_set_digest"] != prod["candidate_set_digest"]

    def test_provenance_records_the_policy_and_the_retired_digest(self) -> None:
        p = provenance("24bf0a8c")
        assert p["candidate_policy_digest"] == policy_digest()
        assert p["effective_contract_digest"] == "24bf0a8c"
        assert p["policy_version"] == POLICY_VERSION
        assert p["blocker_faces"] == ["+X", "-X", "+Y", "-Y"]
        assert "7136993d04151369" in p["retired_policy_digests"]

    def test_provenance_follows_the_policy_it_is_given(self) -> None:
        p = provenance("24bf0a8c", causality_control(0.5))
        assert p["variant"] == "CAUSALITY_CONTROL"
        assert p["candidate_policy_digest"] == causality_control(0.5).digest()


# ------------------------------------------- SD-001 scope correction (Sprint 2C)

AMENDMENT = json.loads(
    (Path(__file__).resolve().parents[1] / "gates" / "scenes"
     / "candidate_policy_expected_semantics_amendments.jsonl").read_text().splitlines()[0]
)


class TestFootprintRoleIsGone:
    """SD-001 applied: the volumetric question is not this module's to ask.

    These assert an ABSENCE, which is the hardest kind of expectation to keep
    honest -- a later reader must be able to tell "decided against" from "not got
    round to", and a future contributor must trip over this rather than quietly
    re-adding a Pose-shaped role.
    """

    def test_the_public_role_set_is_target_directed_only(self) -> None:
        assert {r.value for r in Role} == {"BLOCKER", "SUPPORT"}
        assert not hasattr(Role, "FOOTPRINT_SUPPORT")

    def test_no_pose_subject_type_remains(self) -> None:
        import navfm.candidate_policy as cp
        assert not hasattr(cp, "Pose")
        assert not hasattr(cp, "FootprintPolicy")
        assert not hasattr(cp, "FOOTPRINT")

    def test_no_policy_field_describes_a_robot_volume(self) -> None:
        names = {f.name for f in dataclasses.fields(Policy)}
        assert "footprint" not in names
        assert names == {"variant", "blocker", "support", "shared_origin"}

    def test_the_serialized_record_carries_no_volumetric_block(self) -> None:
        assert "footprint" not in DEFAULT_POLICY.to_json()

    def test_a_robot_pose_shaped_subject_is_refused_rather_than_guessed(self) -> None:
        """The boundary is enforced, not merely documented."""
        with pytest.raises(PolicyError, match="out of scope"):
            generate_candidates(TARGET, Role.BLOCKER, (2.0, 0.0, 0.5))  # type: ignore[arg-type]


class TestTheScopeCorrectionIsAProvenanceEvent:
    def test_the_digest_changed(self) -> None:
        assert policy_digest() == AMENDMENT["new_policy_digest"]
        assert policy_digest() != AMENDMENT["old_policy_digest"]

    def test_every_superseded_digest_is_retired_and_none_reused(self) -> None:
        assert set(RETIRED_POLICY_DIGESTS) == set(AMENDMENT["retired_digests_after_this_amendment"])
        assert policy_digest() not in RETIRED_POLICY_DIGESTS

    def test_the_version_moved_with_the_semantics(self) -> None:
        assert POLICY_VERSION == AMENDMENT["policy_version_after"] == 4

    def test_the_digest_change_is_attributable_to_the_removal_alone(self) -> None:
        """The whole diff, not a sample of it.

        Reconstructs the v3 record from the v4 one plus the amendment's declared
        delta. If anything else moved, this fails -- which is the point: a scope
        correction that also perturbed an unrelated parameter would otherwise be
        indistinguishable from a clean one.
        """
        delta = AMENDMENT["serialization_delta"]
        assert delta["removed_keys"] == ["footprint"]
        assert delta["added_keys"] == []
        assert delta["changed_values"] == {"policy_version": [3, 4]}
        new = DEFAULT_POLICY.to_json()
        assert set(new) == {"policy_name", "policy_version", "variant",
                            "blocker", "support", "shared_origin"}

    def test_the_amendment_names_the_scope_decision_not_a_refactor(self) -> None:
        assert AMENDMENT["kind"] == "SCOPE_CORRECTION"
        assert "SD-001" in AMENDMENT["decision"]
        assert "SD-001" in AMENDMENT["reason"] or "outside candidate_policy.py" in AMENDMENT["reason"]


class TestRemainingSemanticsSurvivedTheRemoval:
    """Nothing that stayed may have moved. Checked against the frozen record."""

    def test_blocker_population_is_untouched(self) -> None:
        got = generate_candidates(TARGET, Role.BLOCKER, BOX).candidates
        assert len(got) == 4
        for c, e in zip(got, VALUES["BLOCKER_DEFAULT"], strict=True):
            assert c.face == e["face"]
            assert all(_close(a, b) for a, b in zip(c.origin, e["origin"], strict=True))
            assert list(c.direction) == e["direction"]
            assert _close(c.max_range, e["max_range"])

    def test_support_population_is_untouched(self) -> None:
        c = generate_candidates(TARGET, Role.SUPPORT, BOX).candidates[0]
        e = VALUES["SUPPORT_DEFAULT"][0]
        assert all(_close(a, b) for a, b in zip(c.origin, e["origin"], strict=True))
        assert list(c.direction) == e["direction"]
        assert _close(c.max_range, e["max_range"])

    @pytest.mark.parametrize("case", VALUES["BLOCKER_CAUSALITY_CONTROL_PLUS_X"],
                             ids=lambda c: f"standoff-{c['standoff_m']}")
    def test_causality_controls_are_untouched(self, case: dict[str, Any]) -> None:
        c = generate_candidates(TARGET, Role.BLOCKER, BOX,
                                policy=causality_control(case["standoff_m"])).candidates[0]
        assert all(_close(a, b) for a, b in zip(c.origin, case["origin"], strict=True))
        assert _close(c.max_range, case["max_range"])

    def test_shared_origin_control_is_untouched(self) -> None:
        e = VALUES["BLOCKER_SHARED_ORIGIN_CONTROL"][0]
        c = generate_candidates(TARGET, Role.BLOCKER, BOX,
                                policy=shared_origin_control(e["max_range_m"])).candidates[0]
        assert all(_close(a, b) for a, b in zip(c.origin, e["origin"], strict=True))
        assert _close(c.max_range, e["max_range"])

    def test_invalid_geometry_semantics_are_untouched(self) -> None:
        d = VALUES["DEGENERATE_BOX"]
        cs = generate_candidates(TARGET, Role.BLOCKER,
                                 Aabb(tuple(d["bounds_min"]), tuple(d["bounds_max"])))  # type: ignore[arg-type]
        assert len(cs.candidates) == d["logical_population"]
        assert len(cs.valid_candidates) == d["valid_count"]

    def test_no_consumer_physics_changed_because_no_consumer_calls_this_yet(self) -> None:
        """Guards the claim boundary of this tranche, not the code.

        If a consumer starts calling the policy in the same commit as the scope
        correction, a later digest change becomes ambiguous between the two.
        """
        root = Path(__file__).resolve().parents[1] / "scripts"
        callers = [p.name for p in root.glob("*.py") if "candidate_policy" in p.read_text()]
        assert callers == [], f"consumer migration must not ride along with the scope correction: {callers}"
