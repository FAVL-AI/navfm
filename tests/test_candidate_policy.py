"""Tests for the contract-owned candidate policy.

Three consumers previously generated their own intervention sets — two, four and
one-to-two directions — while recording results under one contract digest. These
tests guard the properties that make a shared policy meaningful: parity between
consumers, finiteness, role separation, and independence from any observation.
"""

from __future__ import annotations

import pytest

from navfm.candidate_policy import (
    BLOCKER,
    POLICY_VERSION,
    Role,
    generate_candidates,
    policy_digest,
    provenance,
)

MN, MX = (0.0, 0.0, 0.0), (1.0, 2.0, 0.5)


class TestPolicyParity:
    """Two consumers must receive the identical intervention set."""

    def test_blocker_parity_between_callers(self) -> None:
        a = generate_candidates("/W/B", Role.BLOCKER, MN, MX)
        b = generate_candidates("/W/B", Role.BLOCKER, MN, MX)
        assert a.digest == b.digest
        assert [c.candidate_id for c in a.candidates] == [c.candidate_id for c in b.candidates]
        assert [c.origin for c in a.candidates] == [c.origin for c in b.candidates]
        assert [c.direction for c in a.candidates] == [c.direction for c in b.candidates]
        assert [c.max_range for c in a.candidates] == [c.max_range for c in b.candidates]

    def test_support_parity_between_callers(self) -> None:
        a = generate_candidates("/W/F", Role.SUPPORT, MN, MX)
        b = generate_candidates("/W/F", Role.SUPPORT, MN, MX)
        assert a.digest == b.digest

    def test_ordering_is_deterministic(self) -> None:
        """Ordering is part of the set: a reordered set is a different experiment."""
        faces = [c.face for c in generate_candidates("/W/B", Role.BLOCKER, MN, MX).candidates]
        assert faces == ["+X", "-X", "+Y", "-Y"]


class TestRolesAreNotInterchangeable:
    def test_blocker_gets_four_lateral_faces(self) -> None:
        cs = generate_candidates("/W/B", Role.BLOCKER, MN, MX)
        assert len(cs.candidates) == 4
        assert all(c.direction[2] == 0.0 for c in cs.candidates)

    def test_support_is_interrogated_from_above(self) -> None:
        """A floor is met from above; edge-on asks whether its rim obstructs."""
        cs = generate_candidates("/W/F", Role.SUPPORT, MN, MX)
        assert len(cs.candidates) == 1
        c = cs.candidates[0]
        assert c.direction == (0.0, 0.0, -1.0)
        assert c.origin[2] > MX[2]

    def test_the_two_policies_differ(self) -> None:
        b = generate_candidates("/W/X", Role.BLOCKER, MN, MX)
        s = generate_candidates("/W/X", Role.SUPPORT, MN, MX)
        assert b.digest != s.digest


class TestFiniteness:
    def test_blocker_set_is_exactly_four(self) -> None:
        """An intervention set that can grow is a search that stops when the
        answer looks right."""
        assert len(generate_candidates("/W/B", Role.BLOCKER, MN, MX).candidates) == 4

    def test_a_degenerate_axis_yields_an_invalid_candidate_not_a_missing_one(self) -> None:
        """Set size stays fixed so digests remain comparable across targets."""
        cs = generate_candidates("/W/B", Role.BLOCKER, (0.0, 0.0, 0.0), (0.0, 2.0, 0.5))
        assert len(cs.candidates) == 4
        assert len(cs.valid_candidates) == 2
        assert any("degenerate" in c.invalid_reason for c in cs.candidates)

    def test_no_vertical_blocker_faces_without_amendment(self) -> None:
        assert BLOCKER.faces == ("+X", "-X", "+Y", "-Y")


class TestObservationIndependence:
    def test_generation_takes_only_geometry_and_role(self) -> None:
        import inspect

        params = set(inspect.signature(generate_candidates).parameters)
        assert params == {"target_id", "role", "bounds_min", "bounds_max"}

    def test_candidate_carries_no_observation_field(self) -> None:
        from dataclasses import fields

        from navfm.candidate_policy import Candidate

        names = {f.name for f in fields(Candidate)}
        forbidden = {"hit", "actual_hit", "actual_collider", "identity_match", "distance"}
        assert not (names & forbidden)

    def test_identical_geometry_yields_identical_set_regardless_of_context(self) -> None:
        first = generate_candidates("/W/B", Role.BLOCKER, MN, MX).digest
        _ = generate_candidates("/W/OTHER", Role.BLOCKER, (9.0, 9.0, 9.0), (10.0, 10.0, 10.0))
        assert generate_candidates("/W/B", Role.BLOCKER, MN, MX).digest == first


class TestProvenance:
    def test_policy_digest_is_stable(self) -> None:
        assert policy_digest() == policy_digest()
        assert len(policy_digest()) == 16

    def test_changing_the_face_set_changes_the_digest(self) -> None:
        """A policy change must not hide under an unchanged contract label."""
        import navfm.candidate_policy as cp

        before = cp.policy_digest()
        original = cp.BLOCKER
        try:
            cp.BLOCKER = cp.BlockerPolicy(faces=("+X", "-X"))
            assert cp.policy_digest() != before
        finally:
            cp.BLOCKER = original
        assert cp.policy_digest() == before

    def test_provenance_records_both_digests(self) -> None:
        p = provenance("24bf0a8c")
        assert p["candidate_policy_digest"] == policy_digest()
        assert p["effective_contract_digest"] == "24bf0a8c"
        assert p["policy_version"] == POLICY_VERSION
        assert p["blocker_faces"] == ["+X", "-X", "+Y", "-Y"]

    @pytest.mark.parametrize("role", list(Role))
    def test_candidate_set_serialises_its_digest(self, role: Role) -> None:
        j = generate_candidates("/W/T", role, MN, MX).to_json()
        assert j["candidate_set_digest"]
        assert j["policy_version"] == POLICY_VERSION


class TestFourFaceRecovery:
    def test_a_target_blocked_on_x_still_offers_y_faces(self) -> None:
        """The Hospital case: unreachable across one axis, clean across the other.
        A two-face policy reported such targets untargetable."""
        cs = generate_candidates("/W/B", Role.BLOCKER, MN, MX)
        y_faces = [c for c in cs.candidates if c.face in ("+Y", "-Y")]
        assert len(y_faces) == 2
        assert all(c.valid for c in y_faces)
        assert all(c.direction[1] != 0.0 for c in y_faces)
