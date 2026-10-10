"""Actual policy state and timestamped boundary failures cannot receive credit."""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from replay_recovery_contracts import CONFIG, boundary_history, equivalent, forced_entry, snapshot

from navfm.collection.topomap import (
    BoundedTopomapState,
    RecoveringTopomapState,
    RecoveryConfig,
    TopomapConfig,
)


def policy(r2=True):
    state = (
        RecoveringTopomapState(goal_node=12, recovery=RecoveryConfig(exit=5.880692958831787))
        if r2
        else BoundedTopomapState(goal_node=12)
    )
    state.closest_node = 3
    state.history = [dict(window=[0, 8], argmin_node=2, argmin_distance=1.2)]
    return SimpleNamespace(
        state=state,
        recovery=state.recovery if r2 else None,
        confirm=None,
        topomap_cfg=TopomapConfig(),
        stop_count=4,
        stopped=True,
        abstained="old",
        verified_count=2,
        chain_reached_decisions=5,
        device="cuda",
        digest="fixed",
        manifest={"config": {}},
        chain=list(range(13)),
    )


@pytest.mark.parametrize("r2", [True, False])
def test_actual_arm_forced_entry_preserves_inferred_node_and_memory(r2):
    p = policy(r2)
    before, after = forced_entry(p)
    assert after["state"]["closest_node"] == before["state"]["closest_node"] == 3
    assert after["state"]["history"] == before["state"]["history"]
    assert after["state"]["lost"] and after["search_window"] == [0, 12]
    assert after["counters"] == dict(
        stop_count=0, stopped=False, abstained=None, verified_count=0, chain_reached_decisions=0
    )
    if r2:
        assert after["state"]["attempts"] == 1 and after["state"]["_scan"] == 0


def test_unknown_state_fails_closed():
    p = policy()
    p.state.unreviewed = True
    with pytest.raises(ValueError):
        snapshot(p)


def test_confirmation_schema_not_silently_omitted():
    p = policy()
    p.confirm = object()
    with pytest.raises(ValueError):
        snapshot(p)


def frames():
    return [
        dict(
            image=f"script_{i:02d}.png",
            physical_step=i + 1,
            sim_time=2 + (i + 1) / 12,
            sensor_time=2 + (i + 1) / 12,
        )
        for i in range(36)
    ]


def boundary():
    return dict(image="post_kidnap.png", physical_step=36, sim_time=5.0, sensor_time=5.0)


def test_post_kidnap_current_replaces_last_image_but_retains_pre_kidnap_ages():
    result = boundary_history(frames(), boundary())
    assert [x["physical_step"] for x in result] == [6, 12, 18, 24, 30, 36]
    assert [5 - x["sensor_time"] for x in result] == [2.5, 2, 1.5, 1, 0.5, 0]
    assert result[-1]["image"] == "post_kidnap.png"


@pytest.mark.parametrize("change", ["stale", "time", "index", "sensor"])
def test_boundary_rejects_stale_age_index_clock(change):
    current = boundary()
    if change == "stale":
        current["image"] = "script_35.png"
    if change == "time":
        current["sim_time"] += 0.5
    if change == "index":
        current["physical_step"] = 37
    if change == "sensor":
        current["sensor_time"] -= 0.1
    with pytest.raises(ValueError):
        boundary_history(frames(), current)


def test_missing_or_reordered_frame_cannot_form_history():
    f = frames()
    f[0], f[1] = f[1], f[0]
    with pytest.raises(ValueError):
        boundary_history(f, boundary())


def test_discrete_policy_divergence_not_accepted_by_float_tolerance():
    assert not equivalent({"closest_node": 2}, {"closest_node": 3})
    assert not equivalent({"stopped": False}, {"stopped": True})
    assert equivalent({"distance": 2.0}, {"distance": 2.0005})
    assert not equivalent({"distance": 2.0}, {"distance": 2.1})
    assert not equivalent({"distance": float("nan")}, {"distance": float("nan")})


def test_manifest_authorises_only_first_pair_and_no_retry_or_efficacy():
    cfg = json.loads(CONFIG.read_text())
    assert len(cfg["authorized_processes"]) == 2
    assert cfg["authorized_processes"] == [
        "A-s_bend_run_0000-R2_recover-r1-reference",
        "A-s_bend_run_0000-R2_recover-r1-replay",
    ]
    assert len(set(cfg["reserved_validation_ids"])) == 32
    assert cfg["continuation"].startswith("STOP_AFTER_FIRST_PAIR")


def test_boundary_history_is_serializable_and_revalidates_without_self_reference():
    current = boundary()
    current["history"] = boundary_history(frames(), current)
    report = {"captures": [*frames(), current], "boundary": current}
    restored = json.loads(json.dumps(report))
    assert (
        boundary_history(restored["captures"][:-1], restored["boundary"])
        == restored["boundary"]["history"]
    )


def test_acquisition_requires_actual_event_from_boundary_call_matching_rgb():
    from replay_recovery_contracts import acquisition_ok

    t = dict(
        kidnap_acquisition_before=0,
        acquisition_subscription_present=True,
        boundary_render_call_index=109,
        boundary_raw_rgb_sha256="new",
        boundary={"sim_time": 5.0},
        kidnap_acquisition_events=[
            dict(
                supported=True,
                render_call_index=109,
                rgb_sha256="new",
                sim_time=5.0,
                camera_sensor_time=5.0,
            )
        ],
    )
    acquisition_ok(t)
    for field, value in [
        ("kidnap_acquisition_events", []),
        ("acquisition_subscription_present", False),
    ]:
        bad = copy.deepcopy(t)
        bad[field] = value
        with pytest.raises(ValueError):
            acquisition_ok(bad)
    for field, value in [
        ("render_call_index", 108),
        ("rgb_sha256", "stale"),
        ("supported", False),
        ("camera_sensor_time", 4.9),
    ]:
        bad = copy.deepcopy(t)
        bad["kidnap_acquisition_events"][0][field] = value
        with pytest.raises(ValueError):
            acquisition_ok(bad)
