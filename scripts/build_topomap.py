"""Build routes of reference images (upstream topological maps) from a prior traversal.

For each route, nodes are the prior teacher traversal's frames every
--spacing-frames (upstream create_topomap.py saves one image per dt = 1.0 s;
12 frames at 12 Hz), always ending at the declared goal frame, so the final
node is the goal image. Image bytes are copied unchanged and hashed.

--swap A=B builds route A's chain from route B's traversal: a wrong-chain
control that tests whether goal-region visits depend on the supplied route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--goal-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--spacing-frames", type=int, default=12)
    p.add_argument("--swap", action="append", default=[], help="ROUTE=SOURCE_ROUTE")
    p.add_argument(
        "--truncate-fraction",
        type=float,
        help="same-scene mismatch control: keep the first fraction of nodes (chain ends short of the goal)",
    )
    a = p.parse_args()
    out = a.out.resolve()
    if out.exists() or out.is_relative_to(REPO):
        p.error("output must be new and external")
    if a.spacing_frames < 1:
        p.error("spacing must be positive")
    if a.truncate_fraction is not None and not 0 < a.truncate_fraction < 1:
        p.error("truncate fraction must be in (0, 1)")
    goals = json.loads((a.goal_root / "goal_source.json").read_text())["goals"]
    swap = dict(s.split("=", 1) for s in a.swap)
    if set(swap) - set(goals) or set(swap.values()) - set(goals):
        p.error("unknown route in --swap")
    out.mkdir(parents=True)
    chains = {}
    for route in goals:
        source_route = swap.get(route, route)
        declared = goals[source_route]
        trajectory = Path(declared["source"]).parent
        final = int(declared["frame"])
        frames = [*range(0, final, a.spacing_frames), final]
        (out / route).mkdir()
        nodes = []
        for k, f in enumerate(frames):
            src = trajectory / f"{f}.jpg"
            data = src.read_bytes()
            shutil.copyfile(src, out / route / f"{k}.jpg")
            nodes.append(
                {
                    "node": k,
                    "frame": f,
                    "source": str(src),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
        if nodes[-1]["sha256"] != declared["source_sha256"]:
            raise ValueError(f"{source_route}: final node is not the declared goal frame")
        if a.truncate_fraction is not None:
            keep = max(2, int(len(nodes) * a.truncate_fraction))
            for extra in nodes[keep:]:
                (out / route / f"{extra['node']}.jpg").unlink()
            nodes = nodes[:keep]
        chains[route] = {
            "chain_source_route": source_route,
            "control": source_route != route or a.truncate_fraction is not None,
            "truncated_fraction": a.truncate_fraction,
            "traversal": str(trajectory.parent),
            "nodes": nodes,
        }
    (out / "chain.json").write_text(
        json.dumps(
            {
                "definition": "route of reference images from a prior teacher traversal; final node is the declared goal frame",
                "spacing_frames": a.spacing_frames,
                "spacing_basis": "upstream create_topomap.py dt default 1.0 s at 12 Hz",
                "goal_root": str(a.goal_root.resolve()),
                "routes": chains,
            },
            indent=2,
        )
        + "\n"
    )
    for route, c in chains.items():
        print(route, "<-", c["chain_source_route"], "nodes", len(c["nodes"]))


if __name__ == "__main__":
    main()
