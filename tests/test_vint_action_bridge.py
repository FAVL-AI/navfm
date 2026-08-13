"""Tests for the ViNT-waypoint-to-robot-command bridge.

The bridge is two steps: un-normalise the prediction into metres, then convert
metres into a body twist. The second half already existed and is tested against
the reference PD controller. The first half did **not** exist -- it was a
sentence in a docstring describing the upstream deployment stack -- while
``waypoint_to_twist`` consumes metres directly.

That gap is the reason these tests exist. A policy trained on labels normalised
by ``metric_waypoint_spacing`` predicts in those units. Handing the raw
prediction to a controller expecting metres rescales every command by
``1 / metric_waypoint_spacing`` -- about 8x for GO Stanford's 0.12 m -- and:

* raises nothing;
* produces a trajectory that looks entirely plausible;
* is wrong at every timestep;
* is invisible in the recorded data, because nothing downstream records which
  units it received.

So the property worth pinning is not "the function returns a number". It is
that the round trip through normalisation and back is the identity, that the
scale is applied to displacements and *not* to the angle components, and that a
scale which would silently null or mirror the command is refused rather than
accepted.
"""

from __future__ import annotations

import numpy as np
import pytest

from navfm.control import M3PRO_LIMITS, PDConfig, reference_pd_twist, unnormalise_waypoint

#: GO Stanford. The constant ViNT's action labels were divided by.
SPACING = 0.12


class TestRoundTrip:
    """Un-normalisation must invert the label-side normalisation exactly."""

    @pytest.mark.parametrize("metres", [0.0, 0.12, 0.5, -0.36, 1.7])
    def test_normalise_then_unnormalise_is_the_identity(self, metres: float) -> None:
        normalised = metres / SPACING
        back = unnormalise_waypoint([normalised, 0.0], metric_waypoint_spacing=SPACING)
        assert back[0] == pytest.approx(metres, abs=1e-12)

    def test_the_documented_constant_gives_the_documented_answer(self) -> None:
        """One normalised unit is one metric_waypoint_spacing. If this ever
        changes, every recorded command changes with it."""
        assert unnormalise_waypoint([1.0, 0.0], metric_waypoint_spacing=SPACING)[0] == pytest.approx(0.12)

    def test_waypoint_spacing_multiplies_the_scale(self) -> None:
        wp = unnormalise_waypoint([1.0, 0.0], metric_waypoint_spacing=SPACING, waypoint_spacing=3)
        assert wp[0] == pytest.approx(0.36)

    def test_a_batch_of_waypoints_scales_elementwise(self) -> None:
        pred = np.array([[1.0, 0.0], [0.0, 2.0], [-1.0, -1.0]])
        out = unnormalise_waypoint(pred, metric_waypoint_spacing=SPACING)
        assert out == pytest.approx(pred * SPACING)


class TestAngleComponentsAreNotScaled:
    """(cos, sin) is a direction. Scaling it changes the angle it represents."""

    def test_the_angle_survives_unnormalisation(self) -> None:
        theta = 0.7
        wp = unnormalise_waypoint(
            [2.0, 1.0, np.cos(theta), np.sin(theta)], metric_waypoint_spacing=SPACING
        )
        assert np.arctan2(wp[3], wp[2]) == pytest.approx(theta)

    def test_the_unit_circle_stays_a_unit_circle(self) -> None:
        wp = unnormalise_waypoint([5.0, 5.0, 0.6, 0.8], metric_waypoint_spacing=SPACING)
        assert np.hypot(wp[2], wp[3]) == pytest.approx(1.0)

    def test_displacements_are_scaled_while_angles_are_not(self) -> None:
        wp = unnormalise_waypoint([1.0, 1.0, 1.0, 0.0], metric_waypoint_spacing=SPACING)
        assert wp[0] == pytest.approx(SPACING)
        assert wp[1] == pytest.approx(SPACING)
        assert wp[2] == pytest.approx(1.0)


class TestRefusals:
    """A bad scale must fail loudly. Silently is how it would reach the robot."""

    @pytest.mark.parametrize("bad", [0.0, -0.12, float("inf"), float("nan")])
    def test_a_scale_that_would_null_or_mirror_the_command_is_refused(self, bad: float) -> None:
        with pytest.raises(ValueError):
            unnormalise_waypoint([1.0, 0.0], metric_waypoint_spacing=bad)

    @pytest.mark.parametrize("shape", [(3,), (5,), (2, 3)])
    def test_a_waypoint_of_the_wrong_width_is_refused(self, shape: tuple[int, ...]) -> None:
        with pytest.raises(ValueError):
            unnormalise_waypoint(np.zeros(shape), metric_waypoint_spacing=SPACING)

    def test_the_input_is_not_mutated(self) -> None:
        """The caller keeps the normalised prediction for the run record."""
        pred = np.array([1.0, 2.0])
        unnormalise_waypoint(pred, metric_waypoint_spacing=SPACING)
        assert pred == pytest.approx([1.0, 2.0])


class TestTheScaleErrorThisPrevents:
    """The whole point, stated as a test rather than a comment."""

    def test_below_saturation_the_error_is_exactly_the_missing_scale(self) -> None:
        """Where the limiter does not bite, the wrong path is 1/spacing too fast."""
        cfg = PDConfig(dt=0.25)
        small = np.array([0.05, 0.0, 1.0, 0.0])  # 0.006 m once un-normalised
        correct = reference_pd_twist(
            unnormalise_waypoint(small, metric_waypoint_spacing=SPACING), M3PRO_LIMITS, cfg
        )
        wrong = reference_pd_twist(small, M3PRO_LIMITS, cfg)
        assert wrong[0] / correct[0] == pytest.approx(1.0 / SPACING, rel=1e-6)
        assert wrong[0] / correct[0] > 8.0

    def test_saturation_HIDES_the_scale_error_at_realistic_magnitudes(self) -> None:
        """The finding that matters, and the reason a runtime guard would not help.

        At a normalised prediction of 1.0 the correct command is 0.48 m/s and the
        wrong one is 4.0 m/s. Both exceed the M3 Pro's 0.45 m/s limit, so the
        saturation clamp returns **the same number for both**. The safety limiter,
        doing exactly its job, erases the evidence of an eightfold error.

        So the bug cannot be caught by inspecting commands, or by watching the
        robot, or by any downstream check on recorded velocity. It is visible
        only where the units are converted -- which is why that conversion is a
        named, tested function rather than a multiplication inline at the call
        site.
        """
        cfg = PDConfig(dt=0.25)
        pred = np.array([1.0, 0.0, 1.0, 0.0])
        correct = reference_pd_twist(
            unnormalise_waypoint(pred, metric_waypoint_spacing=SPACING), M3PRO_LIMITS, cfg
        )
        wrong = reference_pd_twist(pred, M3PRO_LIMITS, cfg)
        assert correct[0] == pytest.approx(M3PRO_LIMITS.max_v)
        assert wrong[0] == pytest.approx(M3PRO_LIMITS.max_v)
        assert correct[0] == wrong[0], (
            "both saturate, so the output is identical -- this is the concealment, "
            "and it is why the error must be prevented at the conversion"
        )

    def test_the_wrong_path_raises_nothing(self) -> None:
        """Which is exactly why it needs a test and not a runtime guard: both
        calls succeed, and only one of them is right."""
        cfg = PDConfig(dt=0.25)
        assert reference_pd_twist(np.array([1.0, 0.0, 1.0, 0.0]), M3PRO_LIMITS, cfg) is not None
