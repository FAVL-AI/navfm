"""Observer credit follows actual ordered boundary acquisition, not digest search."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from replay_recovery_contracts_v2 import CONFIG, classify_acquisitions, event_membership


def event(seq, call=113, product="/camera/product", digest="saved"):
    return dict(
        sequence=seq,
        render_call_index=call,
        render_product=product,
        registration_order=0,
        callback_enter_order=seq * 3,
        camera_complete_order=seq * 3 + 1,
        rgb_read_order=seq * 3 + 2,
        actual_callback_completed=True,
        supported=True,
        rgb_sha256=digest,
        sim_time=5.0,
        camera_sensor_time=5.0,
    )


def trace(events):
    return dict(
        kidnap_acquisition_before=0,
        acquisition_subscription_present=True,
        boundary_render_call_index=113,
        boundary_render_product="/camera/product",
        boundary_raw_rgb_sha256="saved",
        boundary={"sim_time": 5.0},
        kidnap_acquisition_events=events,
    )


def test_preboundary_and_unrelated_events_retained_then_actual_boundary_qualifies():
    events = [event(0, call=None, digest="old"), event(1, product="/other/product"), event(2)]
    result = classify_acquisitions(trace(events))
    assert result["qualified_sequence"] == 2
    assert [x["classification"] for x in result["events"]] == [
        "outside_boundary_call",
        "unrelated_product",
        "qualified_final_boundary",
    ]
    assert len(events) == 3 and events[0]["render_call_index"] is None


def test_stale_only_cannot_qualify_even_if_digest_matches():
    with pytest.raises(ValueError):
        classify_acquisitions(trace([event(0, call=None)]))


@pytest.mark.parametrize("call,product", [(112, "/camera/product"), (113, "/other/product")])
def test_correct_digest_wrong_call_or_product_has_no_credit(call, product):
    with pytest.raises(ValueError):
        classify_acquisitions(trace([event(0, call=call, product=product)]))


def test_missing_acquisition_fails():
    with pytest.raises(ValueError):
        classify_acquisitions(trace([]))


@pytest.mark.parametrize(
    "key,value",
    [
        ("camera_complete_order", 0),
        ("rgb_read_order", 1),
        ("registration_order", 1000),
        ("actual_callback_completed", False),
    ],
)
def test_actual_native_completion_and_order_are_required(key, value):
    e = event(0)
    e[key] = value
    with pytest.raises(ValueError):
        classify_acquisitions(trace([e]))


def test_ambiguous_overlapping_order_rejects_even_matching_final_digest():
    events = [event(0), event(1)]
    events[1]["callback_enter_order"] = 1
    with pytest.raises(ValueError):
        classify_acquisitions(trace(events))


def test_do_not_search_arbitrary_digest_match_among_boundary_events():
    events = [event(0), event(1, digest="newer-unmatched")]
    with pytest.raises(ValueError):
        classify_acquisitions(trace(events))


def test_multiple_ordered_boundary_acquisitions_use_last_completion():
    result = classify_acquisitions(trace([event(0, digest="old"), event(1)]))
    assert result["qualified_sequence"] == 1
    assert result["events"][0]["classification"] == "superseded_boundary_acquisition"


def test_outside_camera_acquisition_after_boundary_is_ambiguous():
    with pytest.raises(ValueError):
        classify_acquisitions(trace([event(0), event(1, call=None)]))


def test_unknown_event_not_silently_discarded_even_with_later_valid_event():
    events = [event(0, call=None), event(1)]
    events[0]["supported"] = False
    t = trace(events)
    with pytest.raises(ValueError):
        classify_acquisitions(t)
    assert event_membership(t)[0]["classification"] == "unknown"
    assert len(t["kidnap_acquisition_events"]) == 2


def test_unordered_duplicate_event_identity_fails():
    events = [event(0), event(1)]
    events[1]["sequence"] = 0
    with pytest.raises(ValueError):
        classify_acquisitions(trace(events))


def test_v2_ids_root_separate_from_preserved_attempt_only_two_authorized():
    cfg = json.loads(CONFIG.read_text())
    assert len(cfg["authorized_processes"]) == 2
    assert all(
        x.startswith("v2-A-s_bend_run_0000-R2_recover-r1-") for x in cfg["authorized_processes"]
    )
    assert cfg["probe_prefix"] == "replay-recovery-validation-v2-20261010-01"
    assert cfg["continuation"].startswith("STOP_AFTER_FIRST_PAIR")


def test_event_then_precapture_failure_retains_live_evidence_in_serialized_fail():
    from replay_recovery_contracts_v2 import arm_observation

    events = []
    report = {"status": "RUNNING", "captures": []}
    arm_observation(report, events)
    try:
        events.append(event(0, call=None, digest="preboundary"))
        raise RuntimeError("native render failed before capture")
    except RuntimeError as exc:
        report.update(status="FAIL", failure=str(exc))
    saved = json.loads(json.dumps(report))
    assert saved["captures"] == []
    assert saved["kidnap_acquisition_events"][0]["rgb_sha256"] == "preboundary"
    assert saved["kidnap_acquisition_before"] == 0
