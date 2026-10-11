"""Prove the production-chain tracer refuses a chain that is not there.

The tracer's claim is that m3pro_bringup loads M3Pro/urdf/m3pro.urdf and hands
it to robot_state_publisher. A tracer that reports that claim against any input
would prove nothing, so each edge is mutated away in a scratch copy of the
launch file and the tracer must refuse. The real workspace is never modified.

Five mutations, chosen because each is a different way the claim could be wrong:
the assignment absent, the package being a different robot, the xacro step gone,
the node built but never launched, and the assignment ambiguous.
"""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import tempfile
from collections.abc import Callable
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
TRACER = REPO / "scripts/record_production_description_chain.py"

MUTATIONS: dict[str, Callable[[str], str]] = {
    "model assignment deleted": lambda t: "\n".join(
        line for line in t.splitlines() if not line.strip().startswith("model=")),
    "package renamed to a different robot": lambda t: t.replace(
        "'M3Pro'", "'turtlebot3'"),
    "xacro processing step removed": lambda t: t.replace(
        "Command(['xacro ', model])", "model"),
    "node built but never launched": lambda t: t.replace(
        "        robot_state_publisher_node,\n", ""),
    "model assignment duplicated": lambda t: t.replace(
        "    model=os.path.join",
        "    model=os.path.join(get_package_share_directory('M3Pro'),"
        "'urdf','m3pro.urdf')\n    model=os.path.join", 1),
}


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("chain_tracer", TRACER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {TRACER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    tracer = _load()
    real_root = tracer.M3PRO_WS
    launch_rel = tracer.BRINGUP
    source = (real_root / launch_rel).read_text(encoding="utf-8")

    print("=" * 72)
    print("CHAIN TRACER DISCRIMINATION")
    print("=" * 72)

    try:
        edges = tracer.bringup_graph()["edges"]
        positive = True
    except SystemExit as exc:
        edges, positive = [], False
        print(f"positive control FAILED: {exc}")
    print(f"  positive control  real workspace -> "
          f"{'TRACED' if positive else 'REFUSED'} ({len(edges)} edges)")
    print()

    detected: list[str] = []
    missed: list[str] = []
    for name, mutate in MUTATIONS.items():
        scratch = pathlib.Path(tempfile.mkdtemp())
        target = scratch / launch_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(mutate(source), encoding="utf-8")
        tracer.M3PRO_WS = scratch
        try:
            tracer.bringup_graph()
            missed.append(name)
            print(f"  {name:40s} NOT DETECTED")
        except SystemExit as exc:
            detected.append(name)
            print(f"  {name:40s} refused: {str(exc).split(';')[0][:40]}")
        finally:
            tracer.M3PRO_WS = real_root
            shutil.rmtree(scratch, ignore_errors=True)

    print()
    print(f"  detected {len(detected)}/{len(MUTATIONS)}")
    ok = positive and not missed
    print(f"  VERDICT  {'DISCRIMINATING' if ok else 'NOT_DISCRIMINATING'}")
    if missed:
        print(f"  undetected: {missed}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
