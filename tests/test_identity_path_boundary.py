"""A lexical prefix is not a hierarchy, and must not read as one.

Identity accepted a returned collider whose path merely *began* with the declared
target's path. With a declared ``/World/Scene/Geo_M3_DoorWall``, a prim named
``/World/Scene/Geo_M3_DoorWallLamp`` matched, and the probe was recorded
probative. The lamp was accepted as the wall.

The defect was latent while declared targets were long, specific mesh paths. It
becomes dangerous the moment a declared target is a shorter owner path, because
every prim whose name extends that owner's name starts to collide -- which is
exactly the direction the physical-ownership question was about to move in. It is
repaired first, on its own, so that decision cannot be taken on top of it.

Three relations must stay distinct:

    /Wall              the target
    /Wall/Section0     a path-segment descendant  -- accept
    /WallLamp          a lexical prefix only      -- reject

Both the descendant and the ancestor direction are intended and in use: USD often
reports the collider as a child mesh of the declared prim, and the frozen
PHYSICAL_OWNER_IDENTITY fixture declares a leaf owned by an ancestor Xform. The
repair narrows neither; it only requires the separator that makes the relation a
hierarchy rather than a spelling.
"""

from __future__ import annotations

import pytest

from navfm.probe_adjudication import Reason, adjudicate

WALL = "/World/Scene/Geo_M3_DoorWall"


def _identity(hit: str | None, declared: str = WALL, owners: tuple[str, ...] = ()) -> bool:
    return adjudicate(hit=hit is not None, returned_collider=hit, declared_target=declared,
                      observed_distance_m=0.30, expected_distance_m=0.30,
                      preregistered_owners=owners).identity_ok


class TestTheDefectIsGone:
    def test_the_reported_case_is_rejected(self) -> None:
        """The exact pair that was accepted before the repair."""
        assert not _identity("/World/Scene/Geo_M3_DoorWallLamp")

    @pytest.mark.parametrize("hit", [
        "/World/Scene/Geo_M3_DoorWallLamp",
        "/World/Scene/Geo_M3_DoorWall2",
        "/World/Scene/Geo_M3_DoorWallpaper",
        "/World/Scene/Geo_M3_DoorWall_386",
    ])
    def test_lexical_prefixes_are_rejected(self, hit: str) -> None:
        assert not _identity(hit)

    def test_a_prefix_collision_cannot_become_probative(self) -> None:
        """Geometry can be perfect and the probe must still fail on identity."""
        v = adjudicate(hit=True, returned_collider="/World/Scene/Geo_M3_DoorWallLamp",
                       declared_target=WALL, observed_distance_m=0.30,
                       expected_distance_m=0.30)
        assert v.geometry_ok, "residual is exactly zero here, by construction"
        assert not v.probative and v.reason is Reason.WRONG_IDENTITY


class TestIntendedRelationsSurvive:
    def test_exact_target_matches(self) -> None:
        assert _identity(WALL)

    def test_a_path_segment_descendant_matches(self) -> None:
        assert _identity(WALL + "/Section0")

    def test_a_deep_descendant_matches(self) -> None:
        assert _identity(WALL + "/Section0/Mesh")

    def test_an_ancestor_matches(self) -> None:
        """The PHYSICAL_OWNER_IDENTITY shape: a leaf answered by its owner."""
        assert _identity("/World/Group", declared="/World/Group/Leaf")

    def test_a_declared_owner_matches(self) -> None:
        assert _identity("/World/Group", declared="/World/Group/Leaf",
                         owners=("/World/Group",))

    def test_a_descendant_of_a_declared_owner_matches(self) -> None:
        assert _identity("/World/Group/Other", declared="/World/Group/Leaf",
                         owners=("/World/Group",))


class TestIdentityDidNotBroaden:
    def test_an_unrelated_sibling_is_rejected(self) -> None:
        assert not _identity("/World/Scene/Neighbour")

    def test_an_undeclared_owner_is_rejected(self) -> None:
        assert not _identity("/World/Owner", declared="/World/Leaf")

    def test_a_miss_has_no_identity(self) -> None:
        assert not _identity(None)

    def test_the_historical_shared_collider_defect_is_still_rejected(self) -> None:
        """12x5.9: twelve distinct declared doors answered by one wall."""
        wall = "/World/Scene/SM_Wall_6m24_269/SM_Wall_6m/SM_Wall_6m"
        for door in ("/World/Scene/BP_DoorEntrance_2651/SM_DoorEntrance",
                     "/World/Scene/BP_DoorEntrance_2651/SM_DoorEntrance_door_R",
                     "/World/Scene/BP_DoorC_Security_350/SM_DoorB"):
            assert not _identity(wall, declared=door)

    def test_a_generic_hit_never_becomes_probative_by_spelling(self) -> None:
        assert not _identity("/World/Scene/Geo_M3_DoorWall_OTHER_THING")


class TestTheSeparatorIsWhatDoesTheWork:
    """Directly, so the mechanism is pinned and not merely its consequences."""

    @pytest.mark.parametrize(("declared", "hit", "expected"), [
        ("/A", "/A", True),
        ("/A", "/A/B", True),
        ("/A/B", "/A", True),
        ("/A", "/AB", False),
        ("/AB", "/A", False),
        ("/A/B", "/A/BC", False),
    ])
    def test_relation_table(self, declared: str, hit: str, expected: bool) -> None:
        assert _identity(hit, declared=declared) is expected
