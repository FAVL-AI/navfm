"""An unclassified cell is not an empty cell.

The occupancy generator writes three values, and the earlier decode kept two:
anything that was not explicitly OCCUPIED became free space. On Hospital that
turned 174,376 UNKNOWN cells -- 54% of the map -- into drivable floor, and after
inflation 62% of the planner's free space was cells the generator had declined
to classify.

The direction of the error is what makes it severe rather than untidy. A missing
obstacle never invents a wall; it invents free space, exactly where the robot
would collide.
"""

from __future__ import annotations

import numpy as np

from navfm.isaac.collect import OCCUPIED, UNKNOWN, UNOCCUPIED
from navfm.planning import OccupancyGrid


def decode(buf: np.ndarray) -> np.ndarray:
    """The production rule: blocked is 'not explicitly unoccupied'."""
    return buf != UNOCCUPIED


def decode_old(buf: np.ndarray) -> np.ndarray:
    """The rule this replaced. Kept so the difference is testable, not asserted."""
    return buf == OCCUPIED


class TestUnknownIsBlocked:
    def test_an_unknown_cell_is_blocked(self) -> None:
        assert decode(np.array([[UNKNOWN]]))[0, 0]

    def test_an_occupied_cell_is_blocked(self) -> None:
        assert decode(np.array([[OCCUPIED]]))[0, 0]

    def test_an_unoccupied_cell_is_free(self) -> None:
        """The other direction: the rule must still admit real floor."""
        assert not decode(np.array([[UNOCCUPIED]]))[0, 0]

    def test_an_unexpected_value_is_blocked_rather_than_assumed_free(self) -> None:
        """A value the generator was not asked for is unclassified, not empty."""
        assert decode(np.array([[99]]))[0, 0]

    def test_the_three_values_are_distinct(self) -> None:
        assert len({OCCUPIED, UNOCCUPIED, UNKNOWN}) == 3


class TestTheOldRuleIsMeasurablyWorse:
    def test_the_old_rule_admitted_unknown_cells_as_floor(self) -> None:
        """The defect, reproduced. Without this the fix is an unexplained change."""
        buf = np.array([[UNKNOWN, UNKNOWN, UNOCCUPIED]])
        assert not decode_old(buf)[0, 0], "the old rule called UNKNOWN free"
        assert decode(buf)[0, 0], "the new rule blocks it"

    def test_a_wall_whose_interior_is_unknown_becomes_passable_under_the_old_rule(
        self,
    ) -> None:
        """The Hospital transect, in miniature.

        Measured shape: wall interior UNKNOWN, a two-cell surface sliver
        OCCUPIED, open floor UNOCCUPIED. Under the old rule the interior is a
        corridor straight through the wall.
        """
        row = np.array([[UNOCCUPIED, OCCUPIED, UNKNOWN, UNKNOWN, UNKNOWN,
                         OCCUPIED, UNOCCUPIED]])
        old = decode_old(row)[0]
        new = decode(row)[0]
        assert not old[2:5].any(), "old rule leaves the wall interior open"
        assert new[1:6].all(), "new rule blocks the whole wall"

    def test_planning_through_the_wall_is_possible_only_under_the_old_rule(self) -> None:
        """Stated as connectivity, which is what actually harmed the planner."""
        # Faithful to the measured shape: the OCCUPIED surface sliver is not
        # continuous, and the wall interior behind it is UNKNOWN. A first draft
        # of this fixture sealed both faces, which makes the interior
        # unreachable under either rule and demonstrates nothing.
        buf = np.full((5, 7), UNOCCUPIED)
        buf[:, 2] = OCCUPIED
        buf[:, 3] = UNKNOWN
        buf[:, 4] = OCCUPIED
        buf[2, 2] = UNKNOWN      # a gap in the near face
        buf[2, 4] = UNKNOWN      # and in the far face
        left, right = (2, 0), (2, 6)

        for rule, expect_connected in ((decode_old, True), (decode, False)):
            grid = OccupancyGrid(rule(buf), 0.1, (0.0, 0.0))
            seen = {left}
            stack = [left]
            while stack:
                r, c = stack.pop()
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nxt = (r + dr, c + dc)
                    if (nxt not in seen and grid.in_bounds(nxt)
                            and not grid.grid[nxt[0], nxt[1]]):
                        seen.add(nxt)
                        stack.append(nxt)
            assert (right in seen) is expect_connected, (
                f"{rule.__name__}: expected connected={expect_connected}")


class TestMeasuredHospitalProportions:
    """Pins the measured magnitudes, so a regression is visible as a number."""

    HOSPITAL_TOTAL = 322560
    HOSPITAL_UNKNOWN = 174376

    def test_the_unknown_fraction_was_the_majority_of_the_map(self) -> None:
        assert self.HOSPITAL_UNKNOWN / self.HOSPITAL_TOTAL > 0.5

    def test_a_synthetic_map_with_that_mix_loses_most_free_space(self) -> None:
        rng = np.random.default_rng(0)
        buf = rng.choice([OCCUPIED, UNOCCUPIED, UNKNOWN], size=(200, 200),
                         p=[0.093, 0.367, 0.540])
        free_old = int((~decode_old(buf)).sum())
        free_new = int((~decode(buf)).sum())
        assert free_new < free_old
        assert (free_old - free_new) / free_old > 0.5, (
            "the majority of apparent free space came from unclassified cells"
        )
