"""Tests for ``scripts/check_g2_block.py`` — the mechanical G2 block.

Amendment 1 defers four E2 analysis decisions by name and says all four must be
fixed before the first E2 episode is collected. A deferral recorded only in
prose is one that gets forgotten at the moment it becomes inconvenient: the
collector is running, the GPU is warm, and the person who wrote the clause is
the person deciding whether it applies today.

So the property under test is that it is *mechanically impossible* to proceed,
and — the part that matters — that the obvious ways around a checker like this
do not work either.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_g2_block", Path(__file__).resolve().parents[1] / "scripts" / "check_g2_block.py"
)
assert _SPEC and _SPEC.loader
g2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(g2)

MARKER = "before the first E2 episode is collected"


def _decisions(**overrides: dict) -> dict:
    base = {
        "blocks_gate": "G2",
        "gate_condition_marker": MARKER,
        "decisions": {
            name: {"status": "DEFERRED", "value": None, "fixed_by_amendment": None}
            for name in (
                "estimation_software_and_tolerance",
                "held_out_scene_count",
                "per_cell_episode_count",
                "estimator_implementation",
            )
        },
    }
    base["decisions"].update(overrides)
    return base


def _write(tmp_path: Path, record: dict, protocol: str = f"... {MARKER} ...") -> tuple[Path, Path]:
    d = tmp_path / "g2.json"
    d.write_text(json.dumps(record))
    p = tmp_path / "PREREGISTRATION.md"
    p.write_text(protocol)
    return d, p


def _fixed(**extra: object) -> dict:
    return {"status": "FIXED", "value": "something", "fixed_by_amendment": "Amendment 3", **extra}


class TestTheBlockHolds:
    def test_all_four_deferred_blocks(self, tmp_path: Path) -> None:
        ok, problems = g2.check(*_write(tmp_path, _decisions()))
        assert ok is False
        assert len(problems) == 4

    def test_three_of_four_fixed_still_blocks(self, tmp_path: Path) -> None:
        """Partial progress is not progress past this gate."""
        record = _decisions(
            estimation_software_and_tolerance=_fixed(),
            held_out_scene_count=_fixed(),
            per_cell_episode_count=_fixed(),
        )
        ok, problems = g2.check(*_write(tmp_path, record))
        assert ok is False
        assert any("estimator_implementation" in p for p in problems)

    def test_all_four_fixed_unblocks(self, tmp_path: Path) -> None:
        record = _decisions(
            **{
                name: _fixed()
                for name in (
                    "estimation_software_and_tolerance",
                    "held_out_scene_count",
                    "per_cell_episode_count",
                    "estimator_implementation",
                )
            }
        )
        ok, problems = g2.check(*_write(tmp_path, record))
        assert ok is True, problems


class TestTheWaysAround:
    def test_fixed_with_no_value_fixes_nothing(self, tmp_path: Path) -> None:
        record = _decisions(held_out_scene_count={"status": "FIXED", "value": None})
        ok, problems = g2.check(*_write(tmp_path, record))
        assert ok is False
        assert any("no value" in p for p in problems)

    def test_fixed_outside_the_preregistration_is_not_preregistered(self, tmp_path: Path) -> None:
        record = _decisions(
            held_out_scene_count={"status": "FIXED", "value": 8, "fixed_by_amendment": None}
        )
        ok, problems = g2.check(*_write(tmp_path, record))
        assert ok is False
        assert any("not pre-registered" in p for p in problems)

    def test_deleting_the_clause_does_not_lift_the_block(self, tmp_path: Path) -> None:
        """The obvious way around a checker is to delete what it checks for.
        Removing the gate condition from the pre-registration must fail, not
        pass."""
        record = _decisions(
            **{
                name: _fixed()
                for name in (
                    "estimation_software_and_tolerance",
                    "held_out_scene_count",
                    "per_cell_episode_count",
                    "estimator_implementation",
                )
            }
        )
        ok, problems = g2.check(*_write(tmp_path, record, protocol="a protocol with no clause"))
        assert ok is False
        assert any("no longer carries the gate condition" in p for p in problems)

    def test_an_absent_marker_is_not_a_pass(self, tmp_path: Path) -> None:
        record = _decisions()
        del record["gate_condition_marker"]
        ok, _ = g2.check(*_write(tmp_path, record))
        assert ok is False


class TestRefusal:
    def test_assert_unblocked_raises_with_all_reasons(self, tmp_path: Path) -> None:
        with pytest.raises(g2.G2Blocked) as excinfo:
            g2.assert_unblocked(*_write(tmp_path, _decisions()))
        message = str(excinfo.value)
        assert "BLOCKED" in message
        assert "estimator_implementation" in message
        assert "not a collector fault" in message

    def test_cli_exit_codes(self, tmp_path: Path) -> None:
        d, p = _write(tmp_path, _decisions())
        assert g2.main(["--decisions", str(d), "--protocol", str(p)]) == 4

    def test_the_repository_is_currently_blocked(self) -> None:
        """The committed state must be blocked: all four are deferred today,
        and a green check here would mean the block was lifted without the
        amendment that lifts it."""
        ok, problems = g2.check()
        assert ok is False
        assert len(problems) == 4
