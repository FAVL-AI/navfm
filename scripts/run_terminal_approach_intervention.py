"""Run one arm of TERMINAL_APPROACH_INTERVENTION_V1 from the frozen manifest.

A thin shell. Every scientific value -- route, seed, look-ahead, max_steps,
gains, cruise velocity, goal tolerance, scene, initial pose and above all the
target selector -- is read from the manifest, and this program refuses any
attempt to supply one. A command line that can change the experiment is a
command line that can be used to change it after seeing a result, so the only
arguments it accepts are which manifest and which arm.

Canonical invocation:

    python scripts/run_terminal_approach_intervention.py \\
        --manifest runs/bo10/intervention/execution_manifest_v2.json \\
        --arm ARM_A_CONTROL [--validate-only]

``--validate-only`` resolves the manifest, the arm, the selector, the collector
and the output producers, then stops. ``--rehearse`` goes further: it walks the
*same* orchestration the real run walks, substituting a fake runtime at every
external boundary, and records that each mandatory stage and producer was
invoked in order. Neither starts a simulator, consumes a production label, or
writes a scientific artefact.

``--authorise-real-execution`` is the only path that constructs the real Isaac
adapter and enters ``mode="REAL"``. It is off by default and no other flag
implies it: an arm that could start because a default changed is an arm that
did not require authorisation.

Passing either of the first two means the experiment is invokable and its
lifecycle actually executes. Neither means Isaac will succeed -- that is the one
thing only a real attempt can establish.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Callable
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.execution_manifest import ARM_ORDER  # noqa: E402
from navfm.intervention_runner import (  # noqa: E402
    SCIENTIFIC_FIELDS_NEVER_OVERRIDABLE,
    RunnerRefused,
    validate_only,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one frozen intervention arm.",
        epilog=("Scientific configuration comes from the manifest and cannot be "
                "supplied here."),
    )
    parser.add_argument("--manifest", required=True,
                        help="path to the frozen runtime execution manifest")
    parser.add_argument("--arm", required=True, choices=list(ARM_ORDER),
                        help="which frozen arm to run")
    parser.add_argument("--validate-only", action="store_true",
                        help="resolve the execution path and stop; launches nothing")
    parser.add_argument("--rehearse", action="store_true",
                        help=("traverse the real arm lifecycle with a fake runtime; "
                              "starts no simulator and consumes no production label"))
    parser.add_argument("--authorise-real-execution", action="store_true",
                        help=("enter the REAL lifecycle with the Isaac adapter. "
                              "Starts a simulator and creates production captures. "
                              "Off by default"))
    return parser


#: The real runtime boundary, named where the entry point builds it. The gate
#: asserts this is *constructed* here, not that a manifest mentions the dotted
#: path in a string -- which is what V6 did while nothing built it.
REAL_RUNTIME_ADAPTER = "navfm.arm_lifecycle:IsaacRuntimeAdapter"


def run_real_arm(
    manifest_path: str | pathlib.Path,
    arm: str,
    repo_root: str | pathlib.Path,
    *,
    runtime_factory: Callable[[], Any] | None = None,
) -> tuple[Any, Any]:
    """Enter the real arm lifecycle. The only path that can start Isaac.

    V6 declared the real adapter by dotted path in the manifest and nothing ever
    constructed it, so ``mode="REAL"`` had no entry point anywhere in the
    repository and the canonical Arm-A invocation could only refuse. Naming a
    class is not evidence that anything builds it.

    ``runtime_factory`` exists so the reachability gate can prove this path is
    entered without starting a simulator. It is deliberately unreachable from the
    command line: a CLI that can swap the runtime is a CLI that can swap the
    experiment after a result has been seen.
    """
    from navfm.arm_lifecycle import IsaacRuntimeAdapter, execute_arm

    factory: Callable[[], Any] = (
        IsaacRuntimeAdapter if runtime_factory is None else runtime_factory)
    runtime = factory()
    outcome = execute_arm(manifest_path, arm, repo_root, runtime=runtime, mode="REAL")
    return outcome, runtime


def refuse_scientific_overrides(argv: list[str]) -> None:
    """Any attempt to set a scientific value on the command line is refused.

    Checked against the raw argv rather than the parsed namespace, because
    argparse would reject an unknown flag with a usage error that reads like a
    typo. This names what was attempted and why it is not allowed.
    """
    for token in argv:
        if not token.startswith("--"):
            continue
        name = token.lstrip("-").split("=")[0].replace("-", "_").lower()
        if name in SCIENTIFIC_FIELDS_NEVER_OVERRIDABLE:
            raise RunnerRefused(
                f"--{name.replace('_', '-')} is a scientific value and comes from the "
                "frozen manifest. It cannot be supplied on the command line: an "
                "experiment whose configuration can be typed at run time can be "
                "retyped after a result is seen"
            )


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        refuse_scientific_overrides(arguments)
    except RunnerRefused as exc:
        print(f"RUNNER = REFUSED\n  {exc}")
        return 2

    args = build_parser().parse_args(arguments)

    selected = [name for name, on in (
        ("--validate-only", args.validate_only),
        ("--rehearse", args.rehearse),
        ("--authorise-real-execution", args.authorise_real_execution)) if on]
    if len(selected) > 1:
        print("RUNNER = REFUSED")
        print(f"  {', '.join(selected)} name different execution modes.")
        print("  Supplying more than one leaves it ambiguous which one ran.")
        return 2

    if args.authorise_real_execution:
        outcome, runtime = run_real_arm(args.manifest, args.arm, REPO)
        print(json.dumps(outcome.as_dict(), indent=2, default=str))
        print()
        print(f"EXECUTION_MODE      {outcome.mode}")
        print(f"ARM                 {args.arm}")
        print(f"ARM_EXECUTION       {outcome.status}")
        print(f"lifecycle           {outcome.lifecycle['LIFECYCLE']}")
        print(f"real adapter        {type(runtime).__name__}")
        print(f"stages entered      {outcome.lifecycle['stages_entered']}")
        if outcome.refusal:
            print(f"refused at          {outcome.refusal.get('stage')}")
            print(f"reason              {outcome.refusal.get('reason')}")
        return 0 if outcome.status == "VALID" else 1

    if args.rehearse:
        from navfm.arm_lifecycle import RehearsalRuntimeAdapter, execute_arm

        runtime = RehearsalRuntimeAdapter()
        outcome = execute_arm(args.manifest, args.arm, REPO,
                              runtime=runtime, mode="REHEARSAL")
        print(json.dumps(outcome.as_dict(), indent=2, default=str))
        print()
        print(f"REHEARSAL           {outcome.status}  arm={args.arm}")
        print(f"lifecycle           {outcome.lifecycle['LIFECYCLE']}")
        print(f"adapter boundaries  {runtime.calls}")
        print("isaac launched      False")
        print("production label    not consumed")
        return 0 if outcome.status == "VALID" else 1

    if not args.validate_only:
        print("RUNNER = REFUSED")
        print("  real execution of an arm requires explicit authorisation and is not")
        print("  performed by default. Use --validate-only to resolve the execution")
        print("  path, --rehearse to traverse the full lifecycle without a simulator,")
        print("  or --authorise-real-execution to enter the real lifecycle.")
        return 2

    report = validate_only(args.manifest, args.arm, REPO)
    print(json.dumps(report, indent=2, default=str))
    print()
    print(f"VALIDATE_ONLY       {report['VALIDATE_ONLY']}  arm={args.arm}")
    print(f"isaac launched      {report.get('isaac_launched')}")
    print(f"capture created     {report.get('production_capture_created')}")
    return 0 if report["VALIDATE_ONLY"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
