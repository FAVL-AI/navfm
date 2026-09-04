"""Do the tools actually execute the shared policy, or merely agree with it?

Sprint 2A's finding was not that the consumers disagreed on paper. Two of them
computed numerically identical candidates from separately written arithmetic --
they agreed by coincidence, and coincidence is not a contract. So these tests
assert structure, not just numbers: a migrated consumer must *call*
``navfm.candidate_policy``, and must no longer carry the arithmetic it used to
build candidates with.

The physics cannot be executed here. Isaac Sim is absent from this machine, so
every PhysX-dependent harness is migrated and checked statically; re-running the
frozen fixture suites is a separate obligation on the Isaac machine and is
recorded as PENDING rather than assumed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from navfm.candidate_policy import (
    Aabb,
    Role,
    causality_control,
    generate_candidates,
    policy_digest,
    shared_origin_control,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

#: Consumers whose target-directed candidate construction has been migrated.
#: Grows one entry per migration commit; a name arrives here only with evidence.
MIGRATED = ("diagnose_hospital_isolation.py",)

#: SD-001: this harness has no target-directed portion at all. Its rays come from
#: a robot pose, declare no target and adjudicate no collider identity, so it must
#: never route through the candidate policy. Listed so the boundary is enforced
#: by a test rather than remembered by a reader.
VOLUMETRIC_ONLY = ("validate_physx_footprint_oracle.py",)

#: Arithmetic that means a script is still building its own candidates. These are
#: the exact spellings the retired local generators used.
LOCAL_GENERATOR_MARKERS = (
    "LOCAL_STANDOFF",
    "LOCAL_MARGIN",
    'for label, axis, sign in',
    "for ox, sgn in",
)


def source(name: str) -> str:
    return (SCRIPTS / name).read_text()


class TestMigratedConsumersCallTheSharedPolicy:
    @pytest.mark.parametrize("name", MIGRATED)
    def test_the_consumer_imports_the_policy(self, name: str) -> None:
        tree = ast.parse(source(name))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "navfm.candidate_policy" in imported

    @pytest.mark.parametrize("name", MIGRATED)
    def test_the_consumer_calls_generate_candidates(self, name: str) -> None:
        tree = ast.parse(source(name))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "generate_candidates" in called

    @pytest.mark.parametrize("name", MIGRATED)
    def test_no_local_candidate_arithmetic_survives(self, name: str) -> None:
        """Deleting the duplicate is the point; leaving it is how drift returns."""
        src = source(name)
        found = [m for m in LOCAL_GENERATOR_MARKERS if m in src]
        assert found == [], f"{name} still carries local candidate construction: {found}"

    @pytest.mark.parametrize("name", MIGRATED)
    def test_the_consumer_records_the_policy_that_produced_its_candidates(
        self, name: str
    ) -> None:
        """A result without its policy digest is unattributable to an experiment."""
        assert "candidate_policy_digest" in source(name)


class TestTheVolumetricBoundaryHolds:
    """SD-001, enforced. A future contributor must trip over this."""

    @pytest.mark.parametrize("name", VOLUMETRIC_ONLY)
    def test_the_oracle_does_not_import_the_candidate_policy(self, name: str) -> None:
        assert "candidate_policy" not in source(name), (
            f"{name} asks a volumetric question -- can this robot volume occupy this "
            "space -- and declares no target. Routing it through the candidate policy "
            "would let a volumetric measurement satisfy a target-identity contract."
        )

    @pytest.mark.parametrize("name", VOLUMETRIC_ONLY)
    def test_the_oracle_still_declares_no_target(self, name: str) -> None:
        """The property that put it outside the boundary is still true."""
        src = source(name)
        assert "declared_target" not in src
        assert "expected_target_prim" not in src

    def test_the_oracle_keeps_its_own_volumetric_operations(self) -> None:
        src = source(VOLUMETRIC_ONLY[0])
        assert "overlap_box" in src and "sweep_box_closest" in src

    def test_this_boundary_test_can_fail(self) -> None:
        """Both directions: the check must be capable of firing.

        A boundary assertion that cannot fail certifies nothing, and this one is
        an absence check, which is the kind most easily written vacuous.
        """
        assert "candidate_policy" in source(MIGRATED[0])


class TestCrossConsumerBlockerParity:
    """One target, one policy, one candidate set -- whoever asks.

    Every migrated BLOCKER consumer now obtains candidates from the same
    function, so parity is structural rather than coincidental. What remains
    worth asserting is that the shared function is stable under the things that
    used to differ between consumers.
    """

    BOX = Aabb((0.0, 0.0, 0.0), (1.0, 2.0, 0.5))

    def test_the_same_target_yields_one_candidate_set_digest(self) -> None:
        a = generate_candidates("/W/T", Role.BLOCKER, self.BOX)
        b = generate_candidates("/W/T", Role.BLOCKER, self.BOX)
        assert a.digest == b.digest
        assert [c.candidate_id for c in a.candidates] == [c.candidate_id for c in b.candidates]

    def test_all_four_faces_are_present_for_every_consumer(self) -> None:
        faces = [c.face for c in generate_candidates("/W/T", Role.BLOCKER, self.BOX).candidates]
        assert faces == ["+X", "-X", "+Y", "-Y"]

    def test_a_control_variant_is_a_different_experiment(self) -> None:
        prod = generate_candidates("/W/T", Role.BLOCKER, self.BOX)
        ctrl = generate_candidates("/W/T", Role.BLOCKER, self.BOX,
                                   policy=causality_control(0.5))
        assert prod.digest != ctrl.digest
        assert prod.policy.digest() != ctrl.policy.digest()

    def test_the_retired_construction_is_reachable_only_by_name(self) -> None:
        retired = generate_candidates("/W/T", Role.BLOCKER, self.BOX,
                                      policy=shared_origin_control(40.0))
        assert len(retired.candidates) == 1
        assert retired.candidates[0].origin[0] == 0.0
        assert generate_candidates("/W/T", Role.BLOCKER, self.BOX).candidates[0].origin[0] != 0.0


class TestCandidatesDoNotDependOnObservations:
    """Cross-consumer observation independence.

    The generator takes geometry, role and policy. There is no argument through
    which a hit, a collider, a distance or a prior verdict could reach it, and
    that is asserted here rather than left to the signature being read.
    """

    BOX = Aabb((0.0, 0.0, 0.0), (1.0, 2.0, 0.5))

    def test_the_set_is_identical_before_and_after_unrelated_queries(self) -> None:
        first = generate_candidates("/W/T", Role.BLOCKER, self.BOX)
        for _ in range(3):
            generate_candidates("/W/OTHER", Role.BLOCKER, Aabb((9.0,) * 3, (10.0,) * 3))
            generate_candidates("/W/T", Role.SUPPORT, self.BOX)
        again = generate_candidates("/W/T", Role.BLOCKER, self.BOX)
        assert again.digest == first.digest
        assert [c.to_json() for c in again.candidates] == [c.to_json() for c in first.candidates]

    def test_the_policy_digest_is_stable_across_the_session(self) -> None:
        assert policy_digest() == policy_digest()
