import pytest

from navfm.collection.yaw_rate_tracker import YawRateGains, YawRateTracker


def simulate(tracker, w_cmd, plant_gain, steps=48, dt=1 / 12):
    """First-order plant whose steady yaw rate is plant_gain * input."""
    measured = 0.0
    for _ in range(steps):
        u = tracker.update(w_cmd, measured, dt)
        measured += (plant_gain * u - measured) * 0.5
    return measured


@pytest.mark.parametrize("plant_gain", [0.2, 0.5, 1.0])
def test_feedback_recovers_weak_plant(plant_gain):
    # Open loop at gain 0.2 realises 20% of the command; PI must reach it.
    assert simulate(YawRateTracker(), 0.15, plant_gain) == pytest.approx(0.15, abs=0.01)


def test_negative_control_open_loop_does_not_recover():
    open_loop = YawRateTracker(YawRateGains(kp=0.0, ki=0.0))
    assert simulate(open_loop, 0.15, 0.2) == pytest.approx(0.03, abs=0.005)


def test_zero_command_clears_integral_and_output_is_bounded():
    t = YawRateTracker(YawRateGains(output_limit=0.6))
    for _ in range(100):
        out = t.update(0.4, 0.0, 1 / 12)
    assert out == pytest.approx(0.6)
    assert t.integral == pytest.approx(0.5)
    t.update(0.0, 0.0, 1 / 12)
    assert t.integral == 0.0


def test_rejects_bad_inputs():
    t = YawRateTracker()
    with pytest.raises(ValueError):
        t.update(0.1, 0.0, 0.0)
    with pytest.raises(ValueError):
        t.update(float("nan"), 0.0, 0.1)
    with pytest.raises(ValueError):
        YawRateTracker(YawRateGains(output_limit=0.0))
