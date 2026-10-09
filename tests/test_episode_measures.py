import pytest

from navfm.collection import episode_measures as em

LINE = [[0.0, 0.0], [3.0, 0.0]]


def manifest(xs, *, stop=None, contacts=(), dt=1 / 12):
    return {
        "captures": [{"pose": [x, 0.0, 0.0], "simulation_time": i * dt} for i, x in enumerate(xs)],
        "policy_stop_frame": stop,
        "contacts": [{"time": t, "paths": []} for t in contacts],
        "policy": {"stop_rule": "rule"},
    }


def drive_then_hold(stop_x, frames_after):
    xs = [min(0.1 * i / 12 * 6, stop_x) for i in range(200)]
    stop = next(i for i, x in enumerate(xs) if x >= stop_x)
    return xs[: stop + frames_after + 1], stop


def test_correct_stop_needs_measured_settling():
    xs, stop = drive_then_hold(2.8, 24)
    m = em.episode_measures(manifest(xs, stop=stop), LINE, None)
    assert m["settle"] == "SETTLED" and m["correct_stop"] and m["completion"]
    # Negative control: a stop on the last frames cannot be judged settled.
    xs, stop = drive_then_hold(2.8, 3)
    m = em.episode_measures(manifest(xs, stop=stop), LINE, None)
    assert m["settle"] == "UNMEASURABLE" and not m["correct_stop"] and m["wrong_stop"]


def test_moving_after_stop_is_not_correct():
    xs, stop = drive_then_hold(2.8, 24)
    xs = xs[:-12] + [xs[-13] + 0.01 * k for k in range(1, 13)]
    m = em.episode_measures(manifest(xs, stop=stop), LINE, None)
    assert m["settle"] == "MOVING" and not m["correct_stop"]


def test_scoring_goal_can_be_the_goal_image_pose():
    xs, stop = drive_then_hold(2.4, 24)
    end = em.episode_measures(manifest(xs, stop=stop), LINE, None)
    image = em.episode_measures(manifest(xs, stop=stop), LINE, [2.885, 0.0])
    assert end["stop_goal_distance_m"] == pytest.approx(0.6, abs=0.01) and not end["correct_stop"]
    assert image["stop_goal_distance_m"] == pytest.approx(0.485, abs=0.01) and image["correct_stop"]
    assert image["goal_offset_from_endpoint_m"] == pytest.approx(0.115)


def test_contact_after_stop_is_separate_from_collision_before_task_end():
    xs, stop = drive_then_hold(2.8, 24)
    after = em.episode_measures(manifest(xs, stop=stop, contacts=[(stop + 5) / 12]), LINE, None)
    assert after["contact_after_stop"] and not after["collision_before_task_end"]
    assert after["completion"]
    before = em.episode_measures(manifest(xs, stop=stop, contacts=[(stop - 5) / 12]), LINE, None)
    assert before["collision_before_task_end"] and not before["completion"]


def test_navigation_success_requires_entry_before_contact():
    xs = [0.05 * i for i in range(70)]
    entry = next(i for i, x in enumerate(xs) if x >= 2.5)
    ok = em.episode_measures(manifest(xs, contacts=[(entry + 3) / 12]), LINE, None)
    late = em.episode_measures(manifest(xs, contacts=[(entry - 3) / 12]), LINE, None)
    assert ok["navigation_success"] and ok["timeout"]
    assert not late["navigation_success"]


def test_turn_tracking_reports_insufficient_and_a_band_not_a_qualification():
    assert em.turn_tracking([0.05] * 100, [0.05] * 100)["status"] == "INSUFFICIENT"
    assert em.turn_tracking([0.2] * 25, [0.19] * 25)["status"] == "WITHIN_BAND"
    assert em.turn_tracking([0.2] * 25, [0.05] * 25)["status"] == "OUTSIDE_BAND"


def test_contact_at_stop_frame_counts_before_task_end():
    xs, stop = drive_then_hold(2.8, 24)
    m = em.episode_measures(manifest(xs, stop=stop, contacts=[(stop - 0.5) / 12]), LINE, None)
    assert m["collision_before_task_end"] and not m["contact_after_stop"]
    assert m["correct_stop"] and not m["completion"]


def test_entry_and_contact_in_same_frame_is_not_navigation_success():
    xs = [0.05 * i for i in range(70)]
    entry = next(i for i, x in enumerate(xs) if x >= 2.5)
    m = em.episode_measures(manifest(xs, contacts=[(entry - 0.5) / 12]), LINE, None)
    assert m["goal_region_entry_frame"] == entry and not m["navigation_success"]
    assert m["time_in_goal_region_s"] == 0.0


def test_fallback_scoring_goal_is_labelled_and_budget_recorded():
    xs, stop = drive_then_hold(2.8, 24)
    man = {**manifest(xs, stop=stop), "max_steps": 600}
    m = em.episode_measures(man, LINE, None)
    assert m["scoring_goal"] == "route_endpoint" and m["max_steps_budget"] == 600
    assert m["frames_recorded"] == len(xs)


def test_admitted_rate_counts_every_planned_route_from_artefacts():
    routes = [{"id": r} for r in ("a", "b", "c", "d", "e")]
    collection = {
        "episodes": [
            {"id": "a", "status": "PASS"},
            {"id": "b", "status": "PASS"},
            {"id": "c", "status": "FAILED"},
            {"id": "d", "status": "REFUSED_FIXTURE_IDENTITY"},
        ]
    }
    admission = {"trajectories": [{"id": "a", "admitted": True}, {"id": "b", "admitted": False}]}
    r = em.admitted_rate(routes, collection, admission)
    assert r == {
        "planned": 5,
        "never_run": 1,
        "failed": 1,
        "refused": 1,
        "rejected": 1,
        "admitted": 1,
        "rate": 0.2,
    }
    with pytest.raises(ValueError):
        em.admitted_rate([], collection, admission)
