"""Discriminating controls for the eight runtime-attestation requirements.

Every runtime object here is a TEST_DOUBLE. These tests prove reader and
comparator behaviour; they are NOT evidence that a real Isaac read-back
succeeded. Live verification is tracked separately.

The defect this guards against is the one the BO-10 audit found: a setting
written into a record becoming a claim that the running system used it. So the
controls below always check three things per requirement -- a valid observation
passes, a changed observation against a FIXED requested value is reported as a
mismatch, and a missing observation yields no pass and no collection permission.
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from navfm.collection import attestation as att
from navfm.collection import attestation_gate as gate

TD = att.Provenance.TEST_DOUBLE
RUN = "run_under_test"


# --------------------------------------------------------------------------
# structural guards: the no-fallback property
# --------------------------------------------------------------------------

def test_observation_has_no_requested_field() -> None:
    """A reader cannot see intent, so it cannot fall back to it."""
    names = {f.name for f in dataclasses.fields(att.Observation)}
    assert "requested" not in names
    assert "configured" not in names
    assert "fallback" not in names


def test_non_observed_status_cannot_carry_a_value() -> None:
    with pytest.raises(ValueError, match="must carry value None"):
        att.Observation("R4", "rt_subframes", att.Status.FAILED_GETTER_RAISED, 4,
                        "settings.get", "carb", "after startup", TD)


def test_failed_read_does_not_return_the_requested_value() -> None:
    """The exact anti-pattern: observed = read() or requested."""
    class Boom:
        prim_path = "/World/Cam"
        def get_focal_length(self) -> float: raise RuntimeError("not initialised")
    obs = {o.name: o for o in att.read_camera_attributes(Boom(), provenance=TD)}
    fl = obs["focal_length"]
    assert fl.status is att.Status.FAILED_GETTER_RAISED
    assert fl.value is None
    # and the comparator reports unresolved rather than inventing agreement
    rule = next(r for r in gate.RULES if (r.requirement, r.name) == ("R2", "focal_length"))
    c = gate.compare(rule, fl, requested=24.0)
    assert c.verdict is gate.Verdict.UNRESOLVED
    assert "NOT substituted" in c.detail


# --------------------------------------------------------------------------
# R1. source identity
# --------------------------------------------------------------------------

def test_r1_valid_on_a_real_repository(tmp_path: Path) -> None:
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    f = tmp_path / "script.py"
    f.write_text("x = 1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "script.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t",
                    "-c", "user.email=t@e", "commit", "-qm", "init"], check=True)
    obs = {o.name: o for o in att.read_source_identity(tmp_path, [f])}
    assert obs["repository_head"].resolved and len(obs["repository_head"].value) == 40
    assert obs["worktree_dirty"].value is False
    assert obs["influencing_file_digests"].resolved
    assert list(obs["influencing_file_digests"].value) == [str(f)]


def test_r1_missing_when_no_influencing_files_declared(tmp_path: Path) -> None:
    """A HEAD alone is not enough on a dirty tree, so an empty list is unresolved."""
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    obs = {o.name: o for o in att.read_source_identity(tmp_path, [])}
    d = obs["influencing_file_digests"]
    assert d.status is att.Status.UNRESOLVED_NO_SUPPORTED_ROUTE
    assert d.value is None


def test_r1_unreadable_influencing_file_fails(tmp_path: Path) -> None:
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    obs = {o.name: o for o in att.read_source_identity(tmp_path, [tmp_path / "absent.py"])}
    assert obs["influencing_file_digests"].status is att.Status.FAILED_OBJECT_ABSENT


def test_r1_dirty_tree_is_recorded_as_dirty(tmp_path: Path) -> None:
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "loose.py").write_text("y = 2\n")
    obs = {o.name: o for o in att.read_source_identity(tmp_path, [tmp_path / "loose.py"])}
    assert obs["worktree_dirty"].value is True
    assert "per-file hashes" in obs["worktree_dirty"].detail


# --------------------------------------------------------------------------
# R2. composed camera attributes
# --------------------------------------------------------------------------

class FakeCamera:
    """TEST_DOUBLE standing in for isaacsim.sensors.camera.Camera."""

    def __init__(self, *, focal=24.0, h_ap=20.955, v_ap=15.2908,
                 clip=(0.01, 1000000.0), fov=math.radians(64.0),
                 rp="/Render/RenderProduct_Replicator", res=(640, 480)):
        self.prim_path = "/World/Robot/base_link/Camera_front"
        self._f, self._h, self._v, self._c, self._fov = focal, h_ap, v_ap, clip, fov
        self._rp, self._res = rp, res
    def get_focal_length(self): return self._f
    def get_horizontal_aperture(self): return self._h
    def get_vertical_aperture(self): return self._v
    def get_clipping_range(self): return self._c
    def get_horizontal_fov(self): return self._fov
    def get_render_product_path(self): return self._rp
    def get_resolution(self): return self._res


def _obs_map(observations):
    return {o.name: o for o in observations}


def test_r2_valid_reads_every_declared_attribute() -> None:
    obs = _obs_map(att.read_camera_attributes(FakeCamera(), provenance=TD))
    for name in ("focal_length", "horizontal_aperture", "vertical_aperture",
                 "clipping_range", "horizontal_fov", "resolved_prim_path"):
        assert obs[name].resolved, name
        assert obs[name].provenance is TD
    assert obs["clipping_range"].value == [0.01, 1000000.0]
    assert obs["resolved_prim_path"].value == "/World/Robot/base_link/Camera_front"


def test_r2_fov_agreement_matches_the_requested_degrees() -> None:
    """Observed radians vs requested degrees -- a real comparison, not self-equality."""
    obs = _obs_map(att.read_camera_attributes(FakeCamera(fov=math.radians(64.0)), provenance=TD))
    rule = next(r for r in gate.RULES if r.name == "horizontal_fov")
    c = gate.compare(rule, obs["horizontal_fov"], requested=64.0)
    assert c.verdict is gate.Verdict.MATCH
    assert c.requested == 64.0
    assert c.observation.value != 64.0, "the comparison must cross a unit boundary"


def test_r2_fov_mismatch_with_requested_held_fixed() -> None:
    """Requested stays 64.0; the observed value changes; the mismatch is named."""
    rule = next(r for r in gate.RULES if r.name == "horizontal_fov")
    good = _obs_map(att.read_camera_attributes(FakeCamera(fov=math.radians(64.0)), provenance=TD))
    bad = _obs_map(att.read_camera_attributes(FakeCamera(fov=math.radians(90.0)), provenance=TD))
    assert gate.compare(rule, good["horizontal_fov"], requested=64.0).verdict is gate.Verdict.MATCH
    c = gate.compare(rule, bad["horizontal_fov"], requested=64.0)
    assert c.verdict is gate.Verdict.MISMATCH
    assert c.requested == 64.0
    assert "preserved unchanged" in c.detail


def test_r2_unit_mismatch_is_caught() -> None:
    """A camera reporting degrees where radians are expected must fail."""
    rule = next(r for r in gate.RULES if r.name == "horizontal_fov")
    wrong_units = _obs_map(att.read_camera_attributes(FakeCamera(fov=64.0), provenance=TD))
    c = gate.compare(rule, wrong_units["horizontal_fov"], requested=64.0)
    assert c.verdict is gate.Verdict.MISMATCH


def test_r2_missing_getter_on_an_older_api_is_unresolved() -> None:
    class Older:
        prim_path = "/World/Cam"
        def get_focal_length(self): return 24.0
    obs = _obs_map(att.read_camera_attributes(Older(), provenance=TD))
    assert obs["focal_length"].resolved
    assert obs["horizontal_aperture"].status is att.Status.UNRESOLVED_NO_SUPPORTED_ROUTE
    assert obs["horizontal_aperture"].value is None


def test_r2_uninitialised_camera_returning_none_is_not_a_pass() -> None:
    class Uninit:
        prim_path = "/World/Cam"
        def get_focal_length(self): return None
    obs = _obs_map(att.read_camera_attributes(Uninit(), provenance=TD))
    assert obs["focal_length"].status is att.Status.FAILED_NOT_INITIALISED


def test_r2_nonfinite_is_refused() -> None:
    obs = _obs_map(att.read_camera_attributes(FakeCamera(focal=float("nan")), provenance=TD))
    assert obs["focal_length"].status is att.Status.FAILED_NONFINITE


def test_r2_absent_object_is_refused() -> None:
    obs = _obs_map(att.read_camera_attributes(None, provenance=TD))
    assert obs["focal_length"].status is att.Status.FAILED_OBJECT_ABSENT


# --------------------------------------------------------------------------
# R3. render product identity
# --------------------------------------------------------------------------

def test_r3_valid_records_target_and_resolution() -> None:
    cam = FakeCamera()
    obs = _obs_map(att.read_render_product(
        cam, camera_target_reader=lambda p: "/World/Robot/base_link/Camera_front",
        resolution_reader=lambda p: (640, 480), provenance=TD))
    assert obs["render_product_path"].value == "/Render/RenderProduct_Replicator"
    assert obs["render_product_camera_target"].value == "/World/Robot/base_link/Camera_front"
    assert obs["render_product_resolution"].value == [640, 480]


def test_r3_wrong_runtime_object_is_visible_not_hidden() -> None:
    """The render product may point at a DIFFERENT camera than the one configured."""
    cam = FakeCamera()
    obs = _obs_map(att.read_render_product(
        cam, camera_target_reader=lambda p: "/World/SomeOtherCamera",
        resolution_reader=lambda p: (640, 480), provenance=TD))
    assert obs["render_product_camera_target"].value == "/World/SomeOtherCamera"
    assert obs["render_product_camera_target"].value != cam.prim_path


def test_r3_unresolved_render_product_cascades_without_inventing_values() -> None:
    class NoRp:
        prim_path = "/World/Cam"
        def get_render_product_path(self): return None
    obs = _obs_map(att.read_render_product(NoRp(), provenance=TD))
    assert obs["render_product_path"].status is att.Status.FAILED_NOT_INITIALISED
    for n in ("render_product_camera_target", "render_product_resolution"):
        assert obs[n].value is None


def test_r3_reader_failure_is_reported() -> None:
    def boom(_p): raise RuntimeError("invalid render product path")
    obs = _obs_map(att.read_render_product(FakeCamera(), camera_target_reader=boom,
                                           resolution_reader=lambda p: (640, 480), provenance=TD))
    assert obs["render_product_camera_target"].status is att.Status.FAILED_GETTER_RAISED


def test_r3_missing_reader_is_unresolved_not_assumed() -> None:
    obs = _obs_map(att.read_render_product(FakeCamera(), provenance=TD))
    assert obs["render_product_camera_target"].status is att.Status.UNRESOLVED_NO_SUPPORTED_ROUTE


# --------------------------------------------------------------------------
# R4. effective settings
# --------------------------------------------------------------------------

class FakeSettings:
    def __init__(self, values: dict[str, Any]): self._v = values
    def get(self, key: str): return self._v.get(key)


def _settings(dlss=2, subframes=4, renderer="RaytracedLighting", w=640, h=480):
    return FakeSettings({"/rtx/post/dlss/execMode": dlss,
                         "/omni/replicator/RTSubframes": subframes,
                         "/rtx/rendermode": renderer,
                         "/app/renderer/resolution/width": w,
                         "/app/renderer/resolution/height": h})


def test_r4_valid_agreement_for_both_mapped_settings() -> None:
    obs = _obs_map(att.read_effective_settings(_settings(), provenance=TD))
    rs = {r.name: r for r in gate.RULES if r.requirement == "R4"}
    assert gate.compare(rs["rt_subframes"], obs["rt_subframes"], requested=4).verdict is gate.Verdict.MATCH
    assert gate.compare(rs["dlss_exec_mode"], obs["dlss_exec_mode"], requested=True).verdict is gate.Verdict.MATCH


def test_r4_mismatch_reproduces_the_audited_defect() -> None:
    """The historical case: metadata said 4, nothing set it, runtime had 1."""
    obs = _obs_map(att.read_effective_settings(_settings(subframes=1), provenance=TD))
    rule = next(r for r in gate.RULES if r.name == "rt_subframes")
    c = gate.compare(rule, obs["rt_subframes"], requested=4)
    assert c.verdict is gate.Verdict.MISMATCH
    assert c.requested == 4 and c.observation.value == 1


def test_r4_dlss_flag_mapping_mismatch() -> None:
    obs = _obs_map(att.read_effective_settings(_settings(dlss=0), provenance=TD))
    rule = next(r for r in gate.RULES if r.name == "dlss_exec_mode")
    c = gate.compare(rule, obs["dlss_exec_mode"], requested=True)
    assert c.verdict is gate.Verdict.MISMATCH
    assert "expected 2" in c.detail


def test_r4_unset_setting_assumes_no_default() -> None:
    obs = _obs_map(att.read_effective_settings(FakeSettings({}), provenance=TD))
    for n in ("rt_subframes", "dlss_exec_mode", "active_renderer"):
        assert obs[n].status is att.Status.UNRESOLVED_NO_SUPPORTED_ROUTE
        assert obs[n].value is None
        assert "no default is assumed" in obs[n].detail


def test_r4_getter_failure_is_reported() -> None:
    class Boom:
        def get(self, key): raise RuntimeError("carb unavailable")
    obs = _obs_map(att.read_effective_settings(Boom(), provenance=TD))
    assert obs["rt_subframes"].status is att.Status.FAILED_GETTER_RAISED


# --------------------------------------------------------------------------
# R5. timestamps at both boundaries
# --------------------------------------------------------------------------

def test_r5_valid_records_both_boundaries() -> None:
    obs = _obs_map(att.read_step_timestamps(2.0, 2.0833333, provenance=TD))
    assert obs["sim_time_at_command"].value == 2.0
    assert obs["sim_time_at_capture"].value == pytest.approx(2.0833333)
    assert "not a wall-clock or hardware latency" in obs["sim_time_at_command"].detail


def test_r5_missing_sample_is_not_a_pass() -> None:
    obs = _obs_map(att.read_step_timestamps(2.0, None, provenance=TD))
    assert obs["sim_time_at_capture"].status is att.Status.FAILED_NOT_INITIALISED
    assert obs["sim_time_at_capture"].value is None


def test_r5_nonfinite_sample_refused() -> None:
    obs = _obs_map(att.read_step_timestamps(float("inf"), 2.0, provenance=TD))
    assert obs["sim_time_at_command"].status is att.Status.FAILED_NONFINITE


def test_r5_goal_capture_time_none_is_the_audited_gap() -> None:
    o = att.read_goal_capture_time(None, provenance=TD)
    assert o.status is att.Status.FAILED_NOT_INITIALISED
    assert "off the observation timeline" in o.detail
    assert att.read_goal_capture_time(1.5, provenance=TD).value == 1.5


# --------------------------------------------------------------------------
# R6. post-spawn pose
# --------------------------------------------------------------------------

class FakeArticulation:
    def __init__(self, xyz=(1.0, 2.0, 0.061)): self._xyz = xyz
    prim_path = "/World/Robot"
    def get_world_poses(self):
        return (np.array([list(self._xyz)]), np.array([[1.0, 0.0, 0.0, 0.0]]))


def test_r6_valid_keeps_the_z_that_pose_discards() -> None:
    obs = _obs_map(att.read_spawn_pose(FakeArticulation(), provenance=TD))
    assert obs["spawn_world_position"].value == pytest.approx([1.0, 2.0, 0.061])
    assert obs["spawn_world_z"].value == pytest.approx(0.061)
    assert "SimRobot.pose() discards" in obs["spawn_world_z"].detail


def test_r6_getter_failure_is_reported() -> None:
    class Boom:
        prim_path = "/World/Robot"
        def get_world_poses(self): raise RuntimeError("physics view not ready")
    obs = _obs_map(att.read_spawn_pose(Boom(), provenance=TD))
    assert obs["spawn_world_position"].status is att.Status.FAILED_GETTER_RAISED
    assert obs["spawn_world_position"].value is None


def test_r6_no_agreement_rule_is_declared_for_z() -> None:
    """Settling legitimately changes Z and no contract states an allowance."""
    z = [r for r in gate.RULES if r.name == "spawn_world_z"]
    assert len(z) == 1 and z[0].kind is gate.RuleKind.PRESENCE
    assert z[0].tolerance is None


# --------------------------------------------------------------------------
# R7. per-frame statistic
# --------------------------------------------------------------------------

def test_r7_both_definitions_differ_on_a_colour_frame() -> None:
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    frame[:, :, 1] = 100  # green only
    luma = att.frame_statistic(frame, "luma_601", provenance=TD)
    rgb = att.frame_statistic(frame, "rgb_unweighted_mean", provenance=TD)
    assert luma.value == pytest.approx(58.7)
    assert rgb.value == pytest.approx(100.0 / 3.0)
    assert luma.value != rgb.value, "the two definitions must not be conflated"
    assert "Not calibrated physical luminance" in luma.detail


def test_r7_black_and_saturated_frames_reproduce_the_audited_extremes() -> None:
    black = np.zeros((8, 8, 3), dtype=np.uint8)
    bright = np.full((8, 8, 3), 231, dtype=np.uint8)
    assert att.frame_statistic(black, provenance=TD).value == pytest.approx(0.0)
    assert att.frame_statistic(bright, provenance=TD).value == pytest.approx(231.0)


def test_r7_unknown_definition_is_unresolved() -> None:
    o = att.frame_statistic(np.zeros((2, 2, 3), np.uint8), "brightness", provenance=TD)
    assert o.status is att.Status.UNRESOLVED_NO_SUPPORTED_ROUTE


def test_r7_malformed_frame_refused() -> None:
    assert att.frame_statistic(np.zeros((4, 4), np.uint8), provenance=TD).status \
        is att.Status.FAILED_NONFINITE
    assert att.frame_statistic(None, provenance=TD).status is att.Status.FAILED_OBJECT_ABSENT


def test_r7_carries_no_admission_threshold() -> None:
    """Recording the statistic is the duty; no retrospective dark-frame rule exists."""
    rule = next(r for r in gate.RULES if r.requirement == "R7")
    assert rule.kind is gate.RuleKind.PRESENCE and rule.tolerance is None


# --------------------------------------------------------------------------
# R8. intent declaration
# --------------------------------------------------------------------------

def test_r8_annotates_declared_intent_fields_without_mutating_input() -> None:
    md = {"sim": {"physics_substeps": 1, "seed": 0, "hz": 12.0}, "collect": {"episodes": 200}}
    before = repr(md)
    o = att.annotate_intent_fields(md)
    assert o.resolved
    assert "sim.physics_substeps" in o.value["declared_intent_only"]
    assert "sim.hz" not in o.value["declared_intent_only"]
    assert o.value["declared_not_autodetected"] is True
    assert repr(md) == before, "historical metadata must not be rewritten"


def test_r8_absent_fields_are_not_claimed() -> None:
    o = att.annotate_intent_fields({"sim": {"hz": 12.0}})
    assert o.value["declared_intent_only"] == []


# --------------------------------------------------------------------------
# the admission decision
# --------------------------------------------------------------------------

def _full_observations(run_id: str = RUN) -> list[att.Observation]:
    obs: list[att.Observation] = []
    obs += att.read_camera_attributes(FakeCamera(), provenance=TD)
    obs += att.read_render_product(FakeCamera(),
                                   camera_target_reader=lambda p: "/World/Robot/base_link/Camera_front",
                                   resolution_reader=lambda p: (640, 480), provenance=TD)
    obs += att.read_effective_settings(_settings(), provenance=TD)
    obs += att.read_step_timestamps(2.0, 2.0833333, provenance=TD)
    obs.append(att.read_goal_capture_time(1.5, provenance=TD))
    obs += att.read_spawn_pose(FakeArticulation(), provenance=TD)
    obs.append(att.frame_statistic(np.full((4, 4, 3), 120, np.uint8), provenance=TD))
    obs.append(att.annotate_intent_fields({"sim": {"physics_substeps": 1}}))
    obs += [att.Observation("R1", n, att.Status.OBSERVED, v, "git", "repo", "before", TD)
            for n, v in (("repository_head", "a" * 40), ("worktree_dirty", False),
                         ("influencing_file_digests", {"s.py": "d" * 64}))]
    return [dataclasses.replace(o, run_id=run_id) for o in obs]


REQUESTED = {"R2.horizontal_fov": 64.0, "R4.rt_subframes": 4, "R4.dlss_exec_mode": True}


def test_decision_permits_collection_only_when_all_eight_are_satisfied() -> None:
    d = gate.decide(_full_observations(), REQUESTED, run_id=RUN)
    assert d.per_requirement == {r: "SATISFIED" for r in att.REQUIREMENTS}
    assert sorted(d.satisfied) == sorted(att.REQUIREMENTS)
    assert d.unsatisfied == [] and d.missing == []
    assert d.scientific_collection_permitted is True
    assert d.to_dict()["test_double_present"] is True


def test_one_mismatch_blocks_collection_and_names_the_requirement() -> None:
    obs = [o for o in _full_observations() if o.name != "rt_subframes"]
    obs.append(dataclasses.replace(
        _obs_map(att.read_effective_settings(_settings(subframes=1), provenance=TD))["rt_subframes"],
        run_id=RUN))
    d = gate.decide(obs, REQUESTED, run_id=RUN)
    assert d.per_requirement["R4"] == "MISMATCH"
    assert "R4" in d.unsatisfied
    assert d.scientific_collection_permitted is False


def test_a_missing_observation_blocks_collection() -> None:
    obs = [o for o in _full_observations() if o.name != "spawn_world_z"]
    d = gate.decide(obs, REQUESTED, run_id=RUN)
    assert d.per_requirement["R6"] == "UNRESOLVED_MISSING_OBSERVATION"
    assert "R6.spawn_world_z" in d.missing
    assert d.scientific_collection_permitted is False


def test_an_unresolved_observation_blocks_collection() -> None:
    obs = [o for o in _full_observations() if o.name != "goal_capture_sim_time"]
    obs.append(dataclasses.replace(att.read_goal_capture_time(None, provenance=TD), run_id=RUN))
    d = gate.decide(obs, REQUESTED, run_id=RUN)
    assert d.per_requirement["R5"] == "UNRESOLVED"
    assert d.scientific_collection_permitted is False


def test_a_stale_observation_from_another_run_is_rejected() -> None:
    obs = [o for o in _full_observations() if o.name != "focal_length"]
    stale = _obs_map(att.read_camera_attributes(FakeCamera(), provenance=TD))["focal_length"]
    obs.append(dataclasses.replace(stale, run_id="a_previous_run"))
    d = gate.decide(obs, REQUESTED, run_id=RUN)
    assert d.per_requirement["R2"] == "REJECTED_WRONG_RUN"
    assert d.scientific_collection_permitted is False


def test_accounting_for_all_eight_is_not_passing_all_eight() -> None:
    """The distinction the supervisor asked to be preserved."""
    obs = [o for o in _full_observations() if o.name != "rt_subframes"]
    d = gate.decide(obs, REQUESTED, run_id=RUN)
    assert set(d.per_requirement) == set(att.REQUIREMENTS)        # all accounted for
    assert d.per_requirement["R4"] != "SATISFIED"                  # but not all passed
    assert d.scientific_collection_permitted is False
    assert "accounting" in d.to_dict()["accounting_is_not_passing"]


def test_agreement_rule_without_a_requested_value_is_unresolved() -> None:
    rule = next(r for r in gate.RULES if r.name == "rt_subframes")
    obs = _obs_map(att.read_effective_settings(_settings(), provenance=TD))["rt_subframes"]
    assert gate.compare(rule, obs, requested=None).verdict is gate.Verdict.UNRESOLVED


def test_rule_cannot_judge_a_different_observation() -> None:
    rule = next(r for r in gate.RULES if r.name == "rt_subframes")
    obs = _obs_map(att.read_camera_attributes(FakeCamera(), provenance=TD))["focal_length"]
    with pytest.raises(ValueError, match="cannot judge"):
        gate.compare(rule, obs)


def test_every_requirement_has_at_least_one_declared_rule() -> None:
    expected = set(att.REQUIREMENTS)
    covered = {r.requirement for r in gate.RULES}
    assert covered == expected
    assert expected == gate.MANDATORY
