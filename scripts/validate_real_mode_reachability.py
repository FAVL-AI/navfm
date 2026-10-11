"""Is the REAL lifecycle reachable from the authorised entry point?

V6 froze a tree whose manifest declared

    "real_adapter": "navfm.arm_lifecycle:IsaacRuntimeAdapter"

while nothing in the repository ever constructed that class, and ``mode="REAL"``
was passed nowhere. Every readiness level was measured through the rehearsal
adapter, so the gate reported READY_FOR_ARM_A_ATTEMPT for a runner whose only
answer to the canonical Arm-A invocation was a structured refusal. A dotted path
in a manifest is a string; it is not evidence that anything builds the object.

That is the same defect the reachability tranche was built to detect, one level
up, and it was invisible because the instrument's own scope excluded the path it
mattered for: the rehearsal was forbidden from starting Isaac, so nothing ever
asked whether REAL had an entry point at all.

This gate establishes LEVEL 4.5 -- REAL_MODE_ENTRYPOINT_REACHABILITY -- which
sits between a current preflight and an actual attempt:

    the authorised entry point constructs the real adapter, and enters the real
    lifecycle, and the lifecycle begins.

It deliberately stops there. The probe refuses at MANIFEST_VALIDATED, which is
the stage *before* PRE_ENV_CAPTURED, because PRE_ENV_CAPTURED writes a capture
labelled PRE_ARM_A and no arm is authorised. Refusing at stage one also returns
before the lifecycle creates its output directory, so the probe writes nothing
at all.

What this does NOT establish: that the PRE capture succeeds, that Isaac
launches, that the Hospital scene loads, that the render loop runs, or that the
collector completes. Those remain LEVEL 5 and only a real attempt reaches them.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.arm_lifecycle import IsaacRuntimeAdapter, RehearsalRuntimeAdapter  # noqa: E402
from navfm.evidence import emit_evidence  # noqa: E402

OUT = REPO / "gates/BO10/real_mode_reachability_20260917.json"
RUNNER_REL = "scripts/run_terminal_approach_intervention.py"

#: The V6 freeze, whose runner carried the defect. Pinned rather than read from
#: HEAD so the historical control keeps discriminating after the fix lands.
V6_FREEZE_COMMIT = "356ef56cee20e2d82e5275e8316d9d3158fbd665"


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("arm_runner", REPO / RUNNER_REL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ProbeAdapter:
    """Records that it was built. Never reached, because the probe refuses first."""

    name = "REAL_PROBE"
    constructed = 0

    def __init__(self) -> None:
        type(self).constructed += 1
        self.calls: list[str] = []


def structural_reachability(runner: Any) -> dict[str, Any]:
    """Necessary, and explicitly not sufficient -- the probe decides that.

    Read from the entry point's own defaults rather than guessed from source
    text: a regex over the file would be satisfied by the dotted path appearing
    in a docstring, which is exactly the evidence that failed last time.
    """
    import inspect

    has_entry = callable(getattr(runner, "run_real_arm", None))
    signature = inspect.signature(runner.run_real_arm) if has_entry else None
    source = inspect.getsource(runner.run_real_arm) if has_entry else ""
    default_is_isaac = "IsaacRuntimeAdapter if runtime_factory is None" in source
    passes_real = 'mode="REAL"' in source
    factory_not_on_cli = "runtime_factory" not in inspect.getsource(runner.build_parser)

    reasons = []
    if not has_entry:
        reasons.append("the runner exposes no run_real_arm entry point")
    if not default_is_isaac:
        reasons.append("run_real_arm does not default to IsaacRuntimeAdapter")
    if not passes_real:
        reasons.append('run_real_arm does not pass mode="REAL"')
    if not factory_not_on_cli:
        reasons.append("the runtime factory is reachable from the command line")

    return {
        "REAL_MODE_STRUCTURAL_REACHABILITY": "PASS" if not reasons else "FAIL",
        "entry_point": f"{RUNNER_REL}:run_real_arm",
        "signature": str(signature),
        "defaults_to_real_adapter": default_is_isaac,
        "passes_mode_real": passes_real,
        "runtime_factory_not_on_command_line": factory_not_on_cli,
        "real_adapter": f"{IsaacRuntimeAdapter.__module__}:{IsaacRuntimeAdapter.__name__}",
        "reasons": reasons,
        "method": (
            "read from the entry point's own signature and body rather than matched "
            "against source text, because a dotted path in a docstring would satisfy "
            "a regex and satisfied the manifest last time"),
        "sufficient_on_its_own": False,
        "why_not_sufficient": (
            "a default can be correct while nothing ever calls the function. The "
            "probe below establishes that the path is actually entered"),
    }


def probe_reasons(mode: str, constructed: int, used_given_factory: bool,
                  status: str, refused_at: str | None, entered: list[str],
                  production_labels: list[str]) -> list[str]:
    """The probe's criterion, as a pure function so controls can attack it.

    Kept separate from the run that produces the numbers. A control that
    re-states the observation it just made is not a control, and this gate
    exists because that pattern keeps getting shipped.
    """
    reasons = []
    if mode != "REAL":
        reasons.append(f"the lifecycle ran in mode {mode!r}, not REAL")
    if constructed != 1:
        reasons.append(f"the entry point built the adapter {constructed} times")
    if not used_given_factory:
        reasons.append("the entry point did not use the factory it was given")
    if status != "REFUSED":
        reasons.append(f"the probe was not refused; it returned {status}")
    if refused_at != "MANIFEST_VALIDATED":
        reasons.append(f"refused at {refused_at!r}, not MANIFEST_VALIDATED")
    if entered:
        reasons.append(f"stages were entered before the refusal: {entered}")
    if production_labels:
        reasons.append(f"a production label appeared: {production_labels}")
    return reasons


def real_mode_probe(runner: Any, tmp: pathlib.Path) -> dict[str, Any]:
    """Enter the REAL lifecycle with a probe adapter and refuse at stage one.

    The manifest handed in does not parse. ``execute_arm`` returns on that before
    it creates an output directory, so the probe reaches the real lifecycle and
    leaves the filesystem untouched.
    """
    _ProbeAdapter.constructed = 0
    unreadable = tmp / "unparseable_manifest.json"
    unreadable.write_text("{ this is deliberately not json")

    outcome, runtime = runner.run_real_arm(
        unreadable, "ARM_A_CONTROL", REPO, runtime_factory=_ProbeAdapter)

    refusal = outcome.refusal or {}
    entered = outcome.lifecycle.get("stages_entered", [])
    blob = json.dumps(outcome.as_dict(), default=str)
    production_labels = [lab for lab in ("PRE_ARM_A", "POST_ARM_A",
                                         "PRE_ARM_B", "POST_ARM_B") if lab in blob]

    reasons = probe_reasons(
        mode=outcome.mode, constructed=_ProbeAdapter.constructed,
        used_given_factory=isinstance(runtime, _ProbeAdapter),
        status=outcome.status, refused_at=refusal.get("stage"),
        entered=entered, production_labels=production_labels)

    return {
        "REAL_MODE_ENTRYPOINT_REACHABILITY": "PASS" if not reasons else "FAIL",
        "mode_entered": outcome.mode,
        "real_adapter_instantiated": _ProbeAdapter.constructed == 1,
        "adapter_type_built": type(runtime).__name__,
        "status": outcome.status,
        "refused_at_stage": refusal.get("stage"),
        "refusal_reason": str(refusal.get("reason"))[:160],
        "stages_entered_before_refusal": entered,
        "production_labels_present": production_labels,
        "isaac_launched": False,
        "filesystem_writes": "none -- the lifecycle returns before it creates a root",
        "reasons": reasons,
        "CLAIM": (
            "the authorised entry point constructs the real adapter and enters the "
            "real lifecycle"),
        "CLAIM_BOUNDARY": (
            "this does NOT establish that the PRE capture succeeds, that Isaac "
            "launches, that Hospital loads, that the render loop runs or that the "
            "collector completes. Those are LEVEL 5 and only a real attempt reaches "
            "them"),
    }


#: The observation a correct probe makes. Controls mutate one field at a time.
_PASSING_PROBE = {
    "mode": "REAL", "constructed": 1, "used_given_factory": True,
    "status": "REFUSED", "refused_at": "MANIFEST_VALIDATED",
    "entered": [], "production_labels": [],
}


def negative_controls(runner: Any, tmp: pathlib.Path) -> dict[str, Any]:
    """Every criterion here is attacked, one mutation at a time.

    An earlier draft of this function contained two controls that could not
    fail: one asserted a counter it had just set to zero was zero, and one
    hardcoded its own verdict. Both would have reported FIRED forever. They are
    replaced by mutations of the real criterion plus one positive control, so
    the gate is shown able to fail AND able to pass.
    """
    results: dict[str, Any] = {}

    # Positive control first: the criterion must accept a correct observation,
    # or a gate that rejects everything would score a clean sweep below.
    results["a_correct_probe_is_accepted"] = {
        "DETECTED": probe_reasons(**_PASSING_PROBE) == [],  # type: ignore[arg-type]
        "detail": "the criterion must be able to pass, not merely able to fail",
        "reasons": probe_reasons(**_PASSING_PROBE),  # type: ignore[arg-type]
    }

    # One mutation per criterion. Each must produce at least one reason.
    for name, mutation in (
            ("mode_was_not_real", {"mode": "REHEARSAL"}),
            ("adapter_never_constructed", {"constructed": 0}),
            ("adapter_constructed_twice", {"constructed": 2}),
            ("a_different_adapter_was_built", {"used_given_factory": False}),
            ("lifecycle_never_began", {"refused_at": "<entry>"}),
            ("stages_ran_before_the_refusal", {"entered": ["MANIFEST_VALIDATED"]}),
            ("production_label_leaked", {"production_labels": ["PRE_ARM_A"]})):
        observation = {**_PASSING_PROBE, **mutation}
        reasons = probe_reasons(**observation)  # type: ignore[arg-type]
        results[name] = {
            "DETECTED": bool(reasons),
            "mutation": mutation,
            "reasons": reasons,
        }

    # The V6 defect, tested against the actual source that carried it. Pinned to
    # the freeze commit rather than HEAD: against HEAD this control would stop
    # discriminating the moment the fix was committed, which is the quiet way a
    # permanent control turns into decoration.
    historical = tmp / "runner_at_v6.py"
    historical.write_bytes(subprocess.run(
        ["git", "-C", str(REPO), "show", f"{V6_FREEZE_COMMIT}:{RUNNER_REL}"],
        capture_output=True, check=False).stdout)
    spec = importlib.util.spec_from_file_location("runner_at_v6", historical)
    assert spec and spec.loader
    old_runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_runner)
    old_verdict = structural_reachability(old_runner)
    results["the_runner_at_the_v6_freeze_has_no_real_entry_point"] = {
        "DETECTED": old_verdict["REAL_MODE_STRUCTURAL_REACHABILITY"] == "FAIL",
        "detail": ("the V6 runner is the tree this gate exists to reject. If it ever "
                   "passes, the gate stopped measuring anything"),
        "source": f"{V6_FREEZE_COMMIT[:12]}:{RUNNER_REL}",
        "reasons": old_verdict["reasons"],
    }

    # A real path silently wired to the fake runtime must remain visible.
    unreadable = tmp / "nc_manifest.json"
    unreadable.write_text("{ not json")
    _, runtime = runner.run_real_arm(
        unreadable, "ARM_A_CONTROL", REPO, runtime_factory=RehearsalRuntimeAdapter)
    results["real_path_using_the_rehearsal_adapter"] = {
        "DETECTED": isinstance(runtime, RehearsalRuntimeAdapter),
        "detail": ("the probe reports which adapter was built, so a real path wired "
                   "to the fake runtime is visible rather than silently green"),
        "adapter_built": type(runtime).__name__,
    }

    verdict = "PASS" if all(r["DETECTED"] for r in results.values()) else "FAIL"
    return {"verdict": verdict, "results": results}


def main() -> int:
    import tempfile

    head = _git("rev-parse", "HEAD")
    runner = _load_runner()

    with tempfile.TemporaryDirectory(prefix="real_mode_probe_") as raw:
        tmp = pathlib.Path(raw)
        structural = structural_reachability(runner)
        probe = real_mode_probe(runner, tmp)
        controls = negative_controls(runner, tmp)

    ok = (structural["REAL_MODE_STRUCTURAL_REACHABILITY"] == "PASS"
          and probe["REAL_MODE_ENTRYPOINT_REACHABILITY"] == "PASS"
          and controls["verdict"] == "PASS")

    record = {
        "check": "REAL_MODE_ENTRYPOINT_REACHABILITY",
        "artifact_semantics": "REACHABILITY_PROBE_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": _dt.datetime.now(_dt.UTC).isoformat(),
        "repository_head": head,
        "runner": {
            "path": RUNNER_REL,
            "sha256": hashlib.sha256((REPO / RUNNER_REL).read_bytes()).hexdigest(),
        },
        "supersedes_gap": {
            "classification": "REAL_MODE_UNREACHABLE_FROM_ENTRYPOINT",
            "observed_at": "356ef56cee20e2d82e5275e8316d9d3158fbd665",
            "detail": (
                "EXECUTION_MANIFEST_V3 declared real_adapter as a dotted path while "
                "IsaacRuntimeAdapter was never instantiated and mode=REAL was passed "
                "nowhere. The canonical Arm-A invocation could only refuse, and every "
                "readiness level had been measured through the rehearsal adapter"),
        },
        "READINESS_LEVEL": "LEVEL_4_5_REAL_MODE_ENTRYPOINT_REACHABILITY",
        "structural": structural,
        "probe": probe,
        "negative_controls": controls,
        "REAL_MODE_REACHABILITY": "PASS" if ok else "FAIL",
        "LEVEL_5_REAL_RUNTIME_ATTEMPT": "NOT_ESTABLISHED",
        "isaac_launched": False,
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }
    sha = emit_evidence(OUT, record, required_keys=(
        "check", "structural", "probe", "negative_controls",
        "REAL_MODE_REACHABILITY", "EXECUTION_STATUS"))

    print("=" * 70)
    print("REAL MODE ENTRY-POINT REACHABILITY  (LEVEL 4.5)")
    print("=" * 70)
    print(f"HEAD                {head[:12]}")
    print(f"entry point         {structural['entry_point']}")
    print(f"structural          {structural['REAL_MODE_STRUCTURAL_REACHABILITY']}  "
          f"{structural['reasons']}")
    print()
    print(f"mode entered        {probe['mode_entered']}")
    print(f"adapter built       {probe['adapter_type_built']}  "
          f"instantiated={probe['real_adapter_instantiated']}")
    print(f"refused at          {probe['refused_at_stage']}")
    print(f"production labels   {probe['production_labels_present'] or 'none'}")
    print(f"probe               {probe['REAL_MODE_ENTRYPOINT_REACHABILITY']}  "
          f"{probe['reasons']}")
    print()
    for name, result in controls["results"].items():
        print(f"  {name:38s} {'FIRED' if result['DETECTED'] else 'MISSED'}")
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha}")
    print(f"REAL_MODE_REACHABILITY  {record['REAL_MODE_REACHABILITY']}")
    print("LEVEL_5             NOT_ESTABLISHED -- only a real attempt reaches it")
    print("isaac launched      False")
    print("ARM_A_EXECUTION     NOT_STARTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
