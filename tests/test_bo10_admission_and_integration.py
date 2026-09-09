"""BO-10 gate composition, and the seam where it meets the production collector.

Two properties this suite exists to hold.

*All required gates must pass, and "not evaluated" is refused as loudly as
"failed".* A missing gate reaching a caller that expected "evaluated and passed"
is the failure the gate discipline exists to prevent.

*The E2 exclusion survives the collector.* Commit f2aeaee made the exclusion
mechanical; this proves a manifest written by the integrated collector still
carries it, so a later writer or manifest change cannot quietly drop the field.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from navfm.collection.admission import (
    POST_EPISODE_GATES,
    PRE_MOTION_GATES,
    AdmissionError,
    BO10CollectionAdmission,
)
from navfm.collection.gates import GateKind, GateResult, GateStatus
from navfm.collection.scope import (
    BO10_SCOPE_DECLARATION,
    E2ScopeViolation,
    assert_e2_admissible,
    authorise_g2_acknowledgement,
    bo10_scope,
    select_e2_population,
)

REPO = Path(__file__).resolve().parents[1]


def passing(gate: str, kind: GateKind = GateKind.PRECONDITION) -> GateResult:
    return GateResult(gate, GateStatus.PASS, kind, reason="ok")


def admission(**kw: object) -> BO10CollectionAdmission:
    return BO10CollectionAdmission(scope=bo10_scope(), route_id="r0",
                                   scene="Office", **kw)  # type: ignore[arg-type]


def all_pre_motion(adm: BO10CollectionAdmission) -> None:
    for gate in PRE_MOTION_GATES:
        kind = (GateKind.PREDICTED_CAPABILITY if gate == "G10_LONG_HORIZON"
                else GateKind.PRECONDITION)
        adm.record(passing(gate, kind))


def all_post_episode(adm: BO10CollectionAdmission) -> None:
    for gate in POST_EPISODE_GATES:
        adm.record(passing(gate, GateKind.POSTCONDITION))


class TestPreMotionAdmission:
    def test_all_pre_motion_gates_passing_authorises_motion(self) -> None:
        adm = admission()
        all_pre_motion(adm)
        assert adm.may_begin_motion()
        adm.assert_may_begin_motion()

    @pytest.mark.parametrize("omitted", PRE_MOTION_GATES)
    def test_any_missing_pre_motion_gate_refuses_motion(self, omitted: str) -> None:
        """Not evaluated is refused as loudly as failed."""
        adm = admission()
        for gate in PRE_MOTION_GATES:
            if gate != omitted:
                kind = (GateKind.PREDICTED_CAPABILITY if gate == "G10_LONG_HORIZON"
                        else GateKind.PRECONDITION)
                adm.record(passing(gate, kind))
        assert not adm.may_begin_motion()
        with pytest.raises(AdmissionError, match="not evaluated"):
            adm.assert_may_begin_motion()

    @pytest.mark.parametrize("failed", PRE_MOTION_GATES)
    def test_any_failing_pre_motion_gate_refuses_motion(self, failed: str) -> None:
        adm = admission()
        all_pre_motion(adm)
        adm.record(GateResult(failed, GateStatus.FAIL, GateKind.PRECONDITION, reason="x"))
        assert not adm.may_begin_motion()
        with pytest.raises(AdmissionError, match="did not pass"):
            adm.assert_may_begin_motion()

    def test_inconclusive_is_not_a_weak_pass(self) -> None:
        adm = admission()
        all_pre_motion(adm)
        adm.record(BO10CollectionAdmission.inconclusive("G7_CAMERA", "spawn failed"))
        assert not adm.may_begin_motion()
        with pytest.raises(AdmissionError, match="G7_CAMERA=INCONCLUSIVE"):
            adm.assert_may_begin_motion()

    def test_there_is_no_partial_credit(self) -> None:
        """Eight of nine passing is not eight-ninths admitted."""
        adm = admission()
        all_pre_motion(adm)
        adm.record(GateResult("G5_OBSTACLE_CLEARANCE", GateStatus.FAIL,
                              GateKind.PRECONDITION, reason="0.0003 m"))
        assert adm.may_begin_motion() is False


class TestPostconditionsCannotPrecedeTheEpisode:
    def test_asking_for_an_episode_verdict_before_the_episode_raises(self) -> None:
        adm = admission()
        all_pre_motion(adm)
        with pytest.raises(AdmissionError, match="nothing to measure"):
            adm.episode_admitted()

    def test_the_report_says_not_yet_measured_rather_than_guessing(self) -> None:
        adm = admission()
        all_pre_motion(adm)
        assert adm.to_dict()["EPISODE_ADMITTED"] == "NOT_YET_MEASURED"

    def test_a_full_episode_is_admitted(self) -> None:
        adm = admission()
        all_pre_motion(adm)
        all_post_episode(adm)
        assert adm.episode_admitted() is True

    def test_a_failing_postcondition_refuses_the_episode(self) -> None:
        adm = admission()
        all_pre_motion(adm)
        all_post_episode(adm)
        adm.record(GateResult("MOTION_REALISED", GateStatus.FAIL,
                              GateKind.POSTCONDITION, reason="did not move"))
        assert adm.episode_admitted() is False

    def test_a_predicted_capability_is_filed_pre_motion_not_as_a_measurement(self) -> None:
        """The kind decides the phase, not the caller."""
        adm = admission()
        adm.record(passing("G10_LONG_HORIZON", GateKind.PREDICTED_CAPABILITY))
        assert "G10_LONG_HORIZON" in adm.pre_motion
        assert "G10_LONG_HORIZON" not in adm.post_episode


class TestE2ExclusionSurvivesTheCollector:
    def test_the_collector_stamps_the_scope_into_its_manifest(self, tmp_path: Path) -> None:
        """The integration seam: a manifest the collector wrote is still refused."""
        from navfm.isaac.app import SimConfig
        from navfm.isaac.collect import CollectConfig, Collector

        collector = Collector(tmp_path / "out", CollectConfig(), SimConfig(),
                              scope=bo10_scope(declaration_path=str(BO10_SCOPE_DECLARATION)))
        collector.out_dir.mkdir(parents=True, exist_ok=True)
        collector._write_manifest()
        manifest = json.loads((collector.out_dir / "collection_manifest.json").read_text())

        assert manifest["purpose"] == "BO10_FRAMEWORK_COMPATIBILITY"
        assert manifest["e2_eligible"] is False
        with pytest.raises(E2ScopeViolation):
            assert_e2_admissible(manifest, label="bo10")

    def test_a_collector_manifest_is_excluded_from_an_e2_population(
        self, tmp_path: Path
    ) -> None:
        from navfm.isaac.app import SimConfig
        from navfm.isaac.collect import CollectConfig, Collector

        collector = Collector(tmp_path / "out2", CollectConfig(), SimConfig(),
                              scope=bo10_scope())
        collector.out_dir.mkdir(parents=True, exist_ok=True)
        collector._write_manifest()
        manifest = json.loads((collector.out_dir / "collection_manifest.json").read_text())

        population = select_e2_population([("hospital_bo10", manifest)])
        assert population.admitted == ()
        assert population.n_excluded == 1

    def test_a_scopeless_manifest_is_refused_rather_than_admitted(
        self, tmp_path: Path
    ) -> None:
        """No scope means REFUSED. Absence is not evidence of eligibility."""
        from navfm.isaac.app import SimConfig
        from navfm.isaac.collect import CollectConfig, Collector

        collector = Collector(tmp_path / "out3", CollectConfig(), SimConfig(), scope=None)
        collector.out_dir.mkdir(parents=True, exist_ok=True)
        collector._write_manifest()
        manifest = json.loads((collector.out_dir / "collection_manifest.json").read_text())

        assert "purpose" not in manifest
        with pytest.raises(E2ScopeViolation, match="declares no collection purpose"):
            assert_e2_admissible(manifest)


class TestTheG2AcknowledgementSeam:
    def test_the_collector_cli_binds_the_flag_to_the_declaration(self) -> None:
        """Passing the flag alone must not be enough; the source proves the binding."""
        source = (REPO / "src/navfm/isaac/collect.py").read_text()
        assert "authorise_g2_acknowledgement" in source
        assert "--scope-declaration" in source

    def test_the_frozen_declaration_still_authorises_only_bo10(self) -> None:
        scope = authorise_g2_acknowledgement(REPO / BO10_SCOPE_DECLARATION)
        assert scope.purpose.value == "BO10_FRAMEWORK_COMPATIBILITY"
        assert scope.e2_eligible is False

    def test_the_collector_refuses_an_unbound_acknowledgement(self, tmp_path: Path) -> None:
        from navfm.isaac.collect import main

        code = main([
            "--out", str(tmp_path / "o"),
            "--scenes", "dummy.usd",
            "--acknowledge-g2-block",
            "--scope-declaration", str(tmp_path / "absent.json"),
        ])
        assert code == 4, "an acknowledgement not bound to the declaration must be refused"


class TestGateListsAreCoherent:
    def test_g10_appears_in_both_phases_because_it_is_two_claims(self) -> None:
        assert "G10_LONG_HORIZON" in PRE_MOTION_GATES
        assert "G10_LONG_HORIZON" in POST_EPISODE_GATES

    def test_every_required_gate_is_named_once_per_phase(self) -> None:
        assert len(set(PRE_MOTION_GATES)) == len(PRE_MOTION_GATES)
        assert len(set(POST_EPISODE_GATES)) == len(POST_EPISODE_GATES)

    def test_the_nine_bo10_gates_are_all_covered(self) -> None:
        covered = set(PRE_MOTION_GATES) | set(POST_EPISODE_GATES)
        for n in (2, 3, 4, 5, 6, 7, 8, 9, 10):
            assert any(g.startswith(f"G{n}_") for g in covered), f"G{n} is not composed"


def test_a_realistic_admission_record_serialises() -> None:
    adm = admission()
    all_pre_motion(adm)
    all_post_episode(adm)
    record = adm.to_dict()
    json.dumps(record)
    assert record["MAY_BEGIN_MOTION"] is True
    assert record["EPISODE_ADMITTED"] is True
    assert record["scope"]["e2_eligible"] is False
    assert np.isfinite(len(record["pre_motion"]))
