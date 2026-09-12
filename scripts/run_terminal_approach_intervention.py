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
and the output producers, then stops. It launches no simulator, creates no
production capture and writes no scientific artefact. Passing it means the
experiment is invokable; it does not mean Isaac will succeed.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

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
    return parser


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

    if not args.validate_only:
        print("RUNNER = REFUSED")
        print("  execution of an arm requires explicit authorisation and is not")
        print("  performed by default. Re-run with --validate-only to resolve the")
        print("  execution path without launching anything.")
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
