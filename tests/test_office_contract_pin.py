"""Does the Office audit's contract pin follow the frozen effective contract?

The Office audit refuses to adjudicate a scene unless the behavioural contract it
was written against is still the one on disk. That check is only worth having if
it can fail, so these tests prove both directions: the current canonical contract
is accepted, and a superseded or perturbed one is not.

The pin is read out of the script with ``ast`` rather than by importing it. The
module builds a ``SimulationApp`` inside ``main()``, and a test that needed Isaac
Sim to verify a string would be a test nobody could run on a build host.

No production scene is launched here. Nothing in this file measures Hospital,
Office or Warehouse, and passing it is not evidence that any scene is suitable.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "scripts" / "audit_office_collision_coverage.py"
AMENDMENTS = REPO / "gates" / "scenes" / "collision_probe_contract_amendments.jsonl"

#: The digest field is excluded from its own hash; that is the whole construction.
DIGEST_FIELD = "effective_contract_digest"

#: Amendment 1. Retired as the effective contract by amendment 2, and kept here
#: as the negative control: if the pin ever matches this again, the Office audit
#: has been rebound to a superseded contract identity.
SUPERSEDED_DIGEST = "24bf0a8c09ab96d6d961b823c8f69c16"


def _pin() -> str:
    """The frozen literal, read without executing the module."""
    tree = ast.parse(AUDIT.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "REQUIRED_CONTRACT_DIGEST":
                    assert isinstance(node.value, ast.Constant)
                    pin = node.value.value
                    assert isinstance(pin, str), "the pin must be a string literal"
                    return pin
    raise AssertionError("REQUIRED_CONTRACT_DIGEST not found in the Office audit")


def _amendments() -> list[dict]:
    return [json.loads(line) for line in AMENDMENTS.read_text().strip().splitlines()]


def _amendment(amendment_id: int) -> dict:
    """Select by id, never by position.

    An earlier version of the two tests below reached for ``[-1]``. That happened
    to be amendment 2 when they were written, and broke the moment amendment 3
    was appended -- not because the assertions were wrong but because the locator
    was. Facts about a specific amendment must be addressed by its id; only the
    *contract identity* is a property of the last line.
    """
    for record in _amendments():
        if record["amendment_id"] == amendment_id:
            return record
    raise AssertionError(f"amendment {amendment_id} not found")


def canonical_digest(record: dict) -> str:
    """The repository's self-digest rule, recomputed rather than trusted.

    sha256 over the record with the digest field removed and keys sorted. No
    module in the repository produces this value, so a test that merely read it
    back out of the file would be checking the file against itself.
    """
    body = {k: v for k, v in record.items() if k != DIGEST_FIELD}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


class TestTheCanonicalRuleHolds:
    def test_every_amendment_carries_its_own_self_digest(self) -> None:
        for record in _amendments():
            assert canonical_digest(record) == record[DIGEST_FIELD], (
                f"amendment {record['amendment_id']} does not satisfy the self-digest rule"
            )

    def test_the_rule_also_derives_the_base_contract_digest(self) -> None:
        """Same construction, different artefact -- so the rule is not a coincidence."""
        contract = json.loads((REPO / "gates/scenes/collision_probe_contract.json").read_text())
        body = {k: v for k, v in contract.items() if k != "probe_contract_digest"}
        recomputed = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        assert recomputed == contract["probe_contract_digest"]


class TestThePinFollowsTheEffectiveContract:
    def test_the_pin_accepts_the_current_effective_contract(self) -> None:
        effective = _amendments()[-1][DIGEST_FIELD]
        assert _pin() == effective[:32]

    def test_the_pin_is_the_last_line_not_merely_some_line(self) -> None:
        """The audit reads the LAST line; a pin matching an earlier one is stale."""
        records = _amendments()
        assert _pin() == canonical_digest(records[-1])[:32]
        if len(records) > 1:
            assert _pin() != canonical_digest(records[0])[:32]


class TestThePinCanStillRefuse:
    """A check that cannot fail certifies nothing. These make it fail."""

    def test_the_superseded_contract_is_rejected(self) -> None:
        assert _pin() != SUPERSEDED_DIGEST

    def test_a_perturbed_amendment_does_not_satisfy_the_pin(self) -> None:
        perturbed = dict(_amendments()[-1])
        perturbed["claim_boundary"] = perturbed["claim_boundary"] + " (perturbed)"
        assert canonical_digest(perturbed)[:32] != _pin()

    @pytest.mark.parametrize("field", ["candidate_policy", "accounting", "targetability"])
    def test_touching_a_contract_clause_moves_the_digest(self, field: str) -> None:
        """Semantics cannot drift while the identity stays still."""
        perturbed = dict(_amendments()[-1])
        perturbed[field] = {"mutated": True}
        assert canonical_digest(perturbed)[:32] != _pin()


class TestTheRebindChangedIdentityOnly:
    """Amendment 2 is an identity freeze, not a behavioural change.

    Asserted against the live policy rather than against the amendment's own
    prose, so a record that drifted from the code would fail here.
    """

    def test_the_frozen_intervention_semantics_match_the_live_policy(self) -> None:
        from navfm.candidate_policy import (
            DEFAULT_POLICY,
            POLICY_VERSION,
            Role,
            policy_digest,
        )

        frozen = _amendment(2)["candidate_policy"]
        assert frozen["production_digest"] == policy_digest()
        assert frozen["policy_version"] == POLICY_VERSION
        assert frozen["public_roles"] == sorted(r.value for r in Role)
        assert frozen["blocker"]["faces"] == list(DEFAULT_POLICY.blocker.faces)
        assert frozen["blocker"]["logical_population"] == 4
        assert frozen["support"]["population"] == 1
        assert frozen["support"]["direction"] == [0.0, 0.0, -1.0]

    def test_the_amendment_does_not_authorise_a_scene(self) -> None:
        record = _amendment(2)
        assert record["safe_to_remeasure_hospital"] is False
        assert record["hospital_status"] == "NO_EVIDENCE / PENDING"
        assert "Hospital valid" in record["non_claims"]

    def test_no_amendment_resolves_wrong_1(self) -> None:
        """The property that actually holds across every record, present and future.

        Amendment 1 predates the ``non_claims`` convention and disclaims Hospital
        in its ``claim_boundary`` instead, so requiring a particular disclaimer
        *field* would assert a house style rather than a scientific invariant.
        What every amendment must carry is that it does not resolve wrong_1:
        that needs target-specific causal evidence no contract amendment supplies.
        """
        for record in _amendments():
            assert record["wrong_1"].startswith("UNRESOLVED"), (
                f"amendment {record['amendment_id']} claims to resolve wrong_1; "
                "that requires a causal experiment, not a contract change"
            )

    def test_every_amendment_disclaims_hospital_somewhere(self) -> None:
        for record in _amendments():
            disclaimer = json.dumps(record.get("non_claims", [])) + record.get("claim_boundary", "")
            assert "Hospital" in disclaimer, (
                f"amendment {record['amendment_id']} says nothing about Hospital's standing"
            )
