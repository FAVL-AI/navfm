"""Every target-identity consumer must mean the same thing by identity.

The repair to the identity predicate landed in ``navfm.probe_adjudication`` while
four harnesses each carried their own inline copy of the old three-way prefix
test. For one commit the repository held two definitions of what it means for a
returned collider to be the declared target -- which is FL-007, the ledger's
dominant protocol defect: a correction that did not propagate.

Two of those copies were introduced by the diagnostics written during this
investigation, so the defect reproduced itself while it was being studied. That
is the argument for asserting the property structurally rather than trusting a
convention.

These tests assert from source that no consumer keeps a local relation, and
assert behaviourally that the shared predicate answers identically for every
consumer, because a shared import that is then wrapped in a local adjustment
would pass the first check and fail the second.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from navfm.probe_adjudication import identity_matches

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

#: Every script that adjudicates whether a returned collider is a declared
#: target. A name arrives here when such a consumer is written.
IDENTITY_CONSUMERS = (
    "validate_collision_probe_causality.py",
    "validate_dense_targetability.py",
    "audit_office_collision_coverage.py",
    "diagnose_support_invariance.py",
    "diagnose_support_causal_controls.py",
)

#: The shape of the retired relation, in any of the spellings it appeared in.
STALE_RELATION = re.compile(
    r"startswith\(\s*(target|path|declared_target|inp\.declared_target|o)\s*\)")


class TestNoConsumerKeepsALocalRelation:
    @pytest.mark.parametrize("name", IDENTITY_CONSUMERS)
    def test_the_stale_prefix_relation_is_absent(self, name: str) -> None:
        src = (SCRIPTS / name).read_text()
        found = STALE_RELATION.findall(src)
        assert not found, (
            f"{name} still computes target identity locally ({found}). One predicate, "
            "one meaning -- a second implementation is how a repair fails to propagate."
        )

    @pytest.mark.parametrize("name", IDENTITY_CONSUMERS)
    def test_it_reaches_the_canonical_predicate(self, name: str) -> None:
        src = (SCRIPTS / name).read_text()
        assert "probe_adjudication" in src, (
            f"{name} adjudicates identity but never imports the canonical module"
        )


class TestTheSharedPredicateIsUnambiguous:
    """One declared/observed pair, one verdict -- whoever asks."""

    #: Declared, observed, expected. Includes the pair that motivated the repair.
    PAIRS = (
        ("/World/Wall", "/World/Wall", True),
        ("/World/Wall", "/World/Wall/Section0", True),
        ("/World/Wall/Section0", "/World/Wall", True),
        ("/World/Wall", "/World/WallLamp", False),
        ("/World/Wall", "/World/Wall2", False),
        ("/World/Wall", "/World/Neighbour", False),
        ("/World/B", "/World/B_hidden", False),
        ("/World/Scene/Geo_M3_DoorWall", "/World/Scene/Geo_M3_DoorWallLamp", False),
    )

    @pytest.mark.parametrize(("declared", "observed", "expected"), PAIRS)
    def test_the_verdict_is_the_same_for_every_consumer(
        self, declared: str, observed: str, expected: bool
    ) -> None:
        assert identity_matches(observed, declared, ()) is expected

    def test_owners_are_matched_by_the_same_relation(self) -> None:
        """The frozen PHYSICAL_OWNER_IDENTITY shape, and its negative."""
        assert identity_matches("/World/Group", "/World/Group/Leaf", ("/World/Group",))
        assert not identity_matches("/World/GroupOther", "/World/Leaf", ("/World/Group",))


class TestHistoricalDecisionsAreUnchanged:
    def test_the_causality_identities_still_hold(self) -> None:
        """Every declared/observed pair the frozen 9/9 experiment recorded."""
        for declared, observed in (("/World/B", "/World/B"),
                                   ("/World/B_open", "/World/B_open"),
                                   ("/World/Group/Leaf", "/World/Group/Leaf"),
                                   ("/World/T_NEAR", "/World/T_NEAR"),
                                   ("/World/T_MID", "/World/T_MID"),
                                   ("/World/T_FAR", "/World/T_FAR")):
            assert identity_matches(observed, declared, ())

    def test_the_wrong_cause_control_is_still_rejected(self) -> None:
        assert not identity_matches("/World/A", "/World/B", ())

    def test_the_historical_shared_collider_defect_is_still_rejected(self) -> None:
        wall = "/World/Scene/SM_Wall_6m24_269/SM_Wall_6m/SM_Wall_6m"
        for door in ("/World/Scene/BP_DoorEntrance_2651/SM_DoorEntrance",
                     "/World/Scene/BP_DoorC_Security_350/SM_DoorB"):
            assert not identity_matches(wall, door, ())
