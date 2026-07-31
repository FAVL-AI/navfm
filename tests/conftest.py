"""Machine-readable test-population reporting.

Delta 1 of the canonical-environment review: the evidence that a verification
run happened must be a *population* proof, not a summary line. F-M2-1 is why —
an environment missing `matplotlib` and `cv2` degraded the 26 upstream-marked
tests to 9 passed / 6 skipped / 11 uncollected, and the run still exited 0 and
printed a green count. Nothing in "228 passed" distinguishes that from a
healthy run; only the population does.

Parsing pytest's terminal summary would reintroduce the same weakness one layer
down, so this emits structured data straight from the hooks: every collected
node id, its marker membership, every skip with its reason, every deselection,
and every collection error.

Opt-in, so ordinary runs are unaffected:

    pytest --population-report=gates/M2/test_population.json

`scripts/check_test_population.py` consumes it and enforces the three
conditions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_REPORT_KEY = "navfm_population"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--population-report",
        action="store",
        default=None,
        metavar="PATH",
        help="write a machine-readable test-population report to PATH",
    )


def _state(config: pytest.Config) -> dict[str, Any]:
    state: dict[str, Any] | None = getattr(config, _REPORT_KEY, None)
    if state is None:
        state = {
            "collected": {},  # node id -> sorted marker names
            "deselected": [],
            "collection_errors": [],
            "outcomes": {},  # node id -> passed | failed | skipped | error
            "skip_reasons": {},  # node id -> reason
        }
        setattr(config, _REPORT_KEY, state)
    return state


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--population-report") is None:
        return
    collected = _state(config)["collected"]
    for item in items:
        collected[item.nodeid] = sorted({m.name for m in item.iter_markers()})


def pytest_deselected(items: list[pytest.Item]) -> None:
    if not items:
        return
    config = items[0].config
    if config.getoption("--population-report") is None:
        return
    state = _state(config)
    for item in items:
        state["deselected"].append(item.nodeid)
        state["collected"].setdefault(item.nodeid, sorted({m.name for m in item.iter_markers()}))


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.failed:
        # The config is not reachable from a CollectReport, so stash on the
        # module and merge at session finish. A collection error is exactly the
        # case where the run must not be trusted, so it must never be dropped.
        _PENDING_COLLECTION_ERRORS.append(str(report.nodeid))


_PENDING_COLLECTION_ERRORS: list[str] = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Any:
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    if item.config.getoption("--population-report") is None:
        return
    state = _state(item.config)
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        prior = state["outcomes"].get(item.nodeid)
        # A failure anywhere in the item's lifecycle wins over a later pass.
        if prior not in {"failed", "error"}:
            state["outcomes"][item.nodeid] = report.outcome
        if report.outcome == "skipped" and isinstance(report.longrepr, tuple):
            state["skip_reasons"][item.nodeid] = report.longrepr[2]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    path = session.config.getoption("--population-report")
    if path is None:
        return
    state = _state(session.config)
    state["collection_errors"] = sorted(set(_PENDING_COLLECTION_ERRORS))
    payload = {
        "exitstatus": int(exitstatus),
        "collected": state["collected"],
        "deselected": sorted(set(state["deselected"])),
        "collection_errors": state["collection_errors"],
        "outcomes": state["outcomes"],
        "skip_reasons": state["skip_reasons"],
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
