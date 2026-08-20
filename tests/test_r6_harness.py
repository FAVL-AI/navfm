"""Tests for the R6 strict-load harness.

The harness is a gate script, so the properties worth pinning are the refusals,
not the happy path. Three recorded failures shape what is tested here:

* **F-M1-1** -- a gate script must never infer execution state. It preflights,
  refuses, and names the missing requirement. So the tests assert that it refuses
  *and* that the refusal message names what is missing.
* **F-M2-1 / F-M2-4** -- a verification must fail when its subject is absent. Every
  refusal below is paired with the corresponding acceptance, so each check is
  shown to discriminate rather than merely to pass.
* The Amendment 5 rule that only `DELTA` and `RERUN` work may execute: a `REUSE`
  row must be refused, because rerunning it "for symmetry" is exactly what the
  execution order forbids.

The single most important property is the first one tested: **the harness must
refuse to load a released checkpoint while Amendment 5 is uncommitted.** Amendment
5 is what authorises that load. A gate satisfiable before its authorising
amendment exists is not a gate.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "verify_r6_strict_load", REPO / "scripts" / "verify_r6_strict_load.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r6 = _load_harness()


CROSSWALK = """
| Model · Rung | Disposition | source_commit / tag |
|---|---|---|
| GNM R5 | REUSE | n/a |
| GNM R6 | DELTA | `900c418` |
| ViNT R6 | **DELTA** | `0afa095` |
| NoMaD R6 | DELTA | `900c418` |
| NoMaD R7 | **UNDER RECONCILIATION** | `900c418` |
"""


class TestDispositionsAreDerivedNotAssumed:
    def test_every_r6_row_is_read_from_the_crosswalk(self) -> None:
        assert r6.r6_dispositions(CROSSWALK) == {
            "gnm": "DELTA",
            "vint": "DELTA",
            "nomad": "DELTA",
        }

    def test_bold_markers_do_not_change_the_disposition(self) -> None:
        """`| ViNT R6 | **DELTA** |` and `| GNM R6 | DELTA |` must parse alike."""
        rows = r6.r6_dispositions(CROSSWALK)
        assert rows["vint"] == rows["gnm"] == "DELTA"

    def test_a_reuse_row_is_reported_as_reuse(self) -> None:
        text = CROSSWALK.replace("| GNM R6 | DELTA |", "| GNM R6 | REUSE |")
        assert r6.r6_dispositions(text)["gnm"] == "REUSE"

    def test_only_r6_rows_are_read(self) -> None:
        """R5 and R7 rows share the table; picking them up would invent a DELTA set."""
        assert "UNDER RECONCILIATION" not in r6.r6_dispositions(CROSSWALK).values()

    def test_a_protocol_without_r6_rows_refuses_rather_than_returning_empty(self) -> None:
        with pytest.raises(r6.PreflightError) as excinfo:
            r6.r6_dispositions("## Amendment 4\n\nno crosswalk here\n")
        assert "R6 crosswalk rows" in str(excinfo.value)


class TestPreflightRefusals:
    """Each refusal is paired with its acceptance, so the check is shown to discriminate."""

    def test_refuses_while_amendment_5_is_uncommitted(self, monkeypatch) -> None:
        """The load-bearing one. Amendment 5 authorises the checkpoint load."""
        monkeypatch.setattr(r6, "committed_protocol", lambda: "## Amendment 4\n")
        with pytest.raises(r6.PreflightError) as excinfo:
            r6.preflight(["vint"], [])
        message = str(excinfo.value)
        assert "Amendment 5" in message
        assert "not authorised" in message

    @pytest.mark.torch
    def test_accepts_once_amendment_5_is_committed(self, monkeypatch) -> None:
        """The other direction: without this, the refusal above proves nothing."""
        monkeypatch.setattr(
            r6, "committed_protocol", lambda: "## Amendment 5\n" + CROSSWALK
        )
        context = r6.preflight(["vint"], [])
        assert context["r6_dispositions"]["vint"] == "DELTA"

    def test_refuses_a_model_whose_row_is_reuse(self, monkeypatch) -> None:
        text = "## Amendment 5\n" + CROSSWALK.replace(
            "| ViNT R6 | **DELTA** |", "| ViNT R6 | REUSE |"
        )
        monkeypatch.setattr(r6, "committed_protocol", lambda: text)
        with pytest.raises(r6.PreflightError) as excinfo:
            r6.preflight(["vint"], [])
        assert "REUSE" in str(excinfo.value)
        assert "symmetry" in str(excinfo.value)

    def test_refuses_a_model_with_no_row_at_all(self, monkeypatch) -> None:
        text = "## Amendment 5\n" + CROSSWALK.replace("| NoMaD R6 | DELTA |", "")
        monkeypatch.setattr(r6, "committed_protocol", lambda: text)
        with pytest.raises(r6.PreflightError) as excinfo:
            r6.preflight(["nomad"], [])
        assert "no R6 row" in str(excinfo.value)

    def test_refuses_a_search_path_that_does_not_exist(self) -> None:
        with pytest.raises(r6.PreflightError) as excinfo:
            r6.stage_syspath(["/nonexistent/navfm-r6-deps"])
        assert "not a directory" in str(excinfo.value)


class TestFiniteCensus:
    """`isfinite` is meaningless for integer buffers, so they are skipped, not passed."""

    @staticmethod
    def _model(state):
        class _M:
            def state_dict(self):
                return state

        return _M()

    @pytest.mark.torch
    def test_a_clean_model_reports_all_finite(self) -> None:
        torch = pytest.importorskip("torch")
        census = r6.finite_census(self._model({"w": torch.ones(3)}))
        assert census["all_finite"] is True
        assert census["tensors_checked"] == 1

    @pytest.mark.torch
    @pytest.mark.parametrize("bad", ["inf", "-inf", "nan"])
    def test_a_non_finite_value_is_caught_and_named(self, bad: str) -> None:
        torch = pytest.importorskip("torch")
        tensor = torch.tensor([1.0, float(bad)])
        census = r6.finite_census(self._model({"layer.weight": tensor}))
        assert census["all_finite"] is False
        assert census["non_finite_tensors"] == ["layer.weight"]

    @pytest.mark.torch
    def test_integer_buffers_are_skipped_not_counted_as_checked(self) -> None:
        """Counting them would inflate the census with values never examined."""
        torch = pytest.importorskip("torch")
        census = r6.finite_census(
            self._model(
                {
                    "bn.num_batches_tracked": torch.tensor(7),
                    "bn.weight": torch.ones(2),
                }
            )
        )
        assert census["tensors_checked"] == 1
        assert census["tensors_skipped_non_float"] == 1
        assert census["all_finite"] is True


class TestTheHarnessDoesNotSmuggleInR7:
    def test_no_tolerance_or_frozen_batch_is_required_at_r6(self) -> None:
        """Adding an R7 requirement here would import one the preregistration
        did not make of R6, and would make the rung unexecutable as written."""
        source = (REPO / "scripts" / "verify_r6_strict_load.py").read_text()
        assert '"tolerance_declared": False' in source
        assert '"frozen_input_batch_used": False' in source
        assert '"inference_run": False' in source

    @pytest.mark.upstream
    def test_nomad_evaluation_path_is_not_enabled_by_this_harness(self) -> None:
        """`upstream.build_model` must keep refusing NoMaD: R6 reconstructs the
        architecture for loading, and must not hand any evaluator a NoMaD."""
        upstream = pytest.importorskip("navfm.upstream")
        with pytest.raises(NotImplementedError):
            upstream.build_model("nomad")
