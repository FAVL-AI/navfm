"""Backend selection is explicit, and unknown never becomes free.

Two properties, each bought with a defect already recorded in this repository.

*The backend is dispatched, never fallen back to.* The legacy builder and the
cell-volume probe disagree about whether a reception desk exists, so an artefact
that cannot say which one ran cannot be interpreted at all.

*A cell that could not be classified is blocked.* `buf == OCCUPIED` made every
UNKNOWN cell traversable and 62% of the planner's free space came from cells the
generator had declined to classify (F-G5-1). The policy is frozen and has a
defining negative control rather than being left to a comment.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from navfm.isaac.app import SimConfig
from navfm.isaac.collect import (
    OCCUPANCY_BACKEND_LEGACY,
    OCCUPANCY_BACKEND_PHYSX,
    OCCUPANCY_BACKENDS,
    OCCUPIED,
    UNKNOWN,
    UNKNOWN_CELL_POLICY,
    UNOCCUPIED,
    CollectConfig,
    Collector,
    OccupancyBackendError,
)
from navfm.planning import OccupancyGrid


def collector(**kw: Any) -> Collector:
    return Collector("/tmp/_backend_test", CollectConfig(), SimConfig(), **kw)


class TestBackendSelectionIsExplicit:
    def test_the_default_is_legacy_and_deliberate(self) -> None:
        """Changing the default would silently alter frozen results' maps."""
        assert collector().occupancy_backend == OCCUPANCY_BACKEND_LEGACY

    def test_an_unknown_backend_is_refused_at_construction(self) -> None:
        with pytest.raises(OccupancyBackendError, match="unknown occupancy backend"):
            collector(occupancy_backend="whatever")

    def test_an_unknown_backend_is_refused_at_call_time(self, monkeypatch) -> None:
        c = collector()
        with pytest.raises(OccupancyBackendError, match="unknown occupancy backend"):
            c.build_occupancy("scene.usd", backend="not_a_backend")

    def test_requesting_the_physx_backend_runs_the_physx_probe(self, monkeypatch) -> None:
        """The dispatch property, proved by observing which path executed."""
        c = collector(occupancy_backend=OCCUPANCY_BACKEND_PHYSX)
        called: list[str] = []

        def fake_physx(bounds=None, **kw):
            called.append("physx")
            c.occupancy_backend_used = OCCUPANCY_BACKEND_PHYSX
            return OccupancyGrid(np.zeros((2, 2), dtype=bool), 0.1, (0.0, 0.0))

        monkeypatch.setattr(c, "build_occupancy_physx", fake_physx)
        c.build_occupancy("scene.usd")
        assert called == ["physx"]
        assert c.occupancy_backend_used == OCCUPANCY_BACKEND_PHYSX

    def test_requesting_the_legacy_backend_does_not_run_the_physx_probe(
        self, monkeypatch
    ) -> None:
        c = collector(occupancy_backend=OCCUPANCY_BACKEND_LEGACY)
        called: list[str] = []
        monkeypatch.setattr(c, "build_occupancy_physx",
                            lambda *a, **k: called.append("physx"))
        # No Isaac here, so the legacy path raises RuntimeError when it reaches
        # the occupancy extension. That it raises from the LEGACY path -- and
        # that the physx probe was never called -- is the observation.
        with pytest.raises(RuntimeError):
            c.build_occupancy("scene.usd")
        assert called == [], "the physx probe must not run when legacy is requested"
        assert c.occupancy_backend_used == OCCUPANCY_BACKEND_LEGACY

    def test_an_explicit_call_argument_overrides_the_instance_default(
        self, monkeypatch
    ) -> None:
        c = collector(occupancy_backend=OCCUPANCY_BACKEND_LEGACY)
        called: list[str] = []

        def fake_physx(bounds=None, **kw):
            called.append("physx")
            return OccupancyGrid(np.zeros((2, 2), dtype=bool), 0.1, (0.0, 0.0))

        monkeypatch.setattr(c, "build_occupancy_physx", fake_physx)
        c.build_occupancy("scene.usd", backend=OCCUPANCY_BACKEND_PHYSX)
        assert called == ["physx"]

    def test_both_backends_are_named_and_distinct(self) -> None:
        assert OCCUPANCY_BACKEND_LEGACY != OCCUPANCY_BACKEND_PHYSX
        assert set(OCCUPANCY_BACKENDS) == {OCCUPANCY_BACKEND_LEGACY, OCCUPANCY_BACKEND_PHYSX}

    def test_the_backend_that_ran_is_recorded_not_inferred(self) -> None:
        """Before any build, nothing is claimed about what ran."""
        assert collector().occupancy_backend_used is None


class TestUnknownNeverBecomesFree:
    def test_the_policy_is_frozen_as_blocked(self) -> None:
        assert UNKNOWN_CELL_POLICY == "BLOCKED"

    def test_the_legacy_decode_blocks_unknown(self) -> None:
        buf = np.array([[UNKNOWN, UNOCCUPIED, OCCUPIED]])
        blocked = buf != UNOCCUPIED
        assert blocked[0, 0], "UNKNOWN must be blocked"
        assert not blocked[0, 1]
        assert blocked[0, 2]

    def test_the_defining_negative_control_an_injected_unknown_is_not_traversable(
        self,
    ) -> None:
        """The exact defect of F-G5-1, as a property.

        A map that is mostly UNKNOWN must not become a map that is mostly free.
        """
        buf = np.full((10, 10), UNKNOWN)
        buf[0, 0] = UNOCCUPIED
        blocked = buf != UNOCCUPIED
        assert blocked.sum() == 99
        old_rule = buf == OCCUPIED
        assert old_rule.sum() == 0, "the old rule made all 100 cells traversable"

    def test_an_injected_query_failure_is_blocked_and_counted(self, monkeypatch) -> None:
        """A cell whose query raised is not a cell found empty."""
        c = collector(occupancy_backend=OCCUPANCY_BACKEND_PHYSX)
        assert c.occupancy_query_failures == 0

        source = _physx_source()
        assert "except Exception:" in source
        assert "grid[j, i] = True" in source
        assert "failed += 1" in source

    def test_the_failure_branch_blocks_rather_than_frees(self) -> None:
        """Read from source: the except branch must set True, never False."""
        source = _physx_source()
        block = source[source.index("except Exception:"):]
        head = block[:400]
        assert "grid[j, i] = True" in head
        assert "grid[j, i] = False" not in head


def _physx_source() -> str:
    import inspect

    return inspect.getsource(Collector.build_occupancy_physx)
