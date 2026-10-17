"""Build the v5 history positive-control call manifest from the frozen v3 manifest.

Metadata, file hashes and raw pixel statistics only: no model is loaded and no score is read
(logged scores already in the v3 manifest are copied unchanged).

The donor rule is fixed before any score exists. For a query from variant V on junction route r,
the five history frames are the images seen at decisions k = 10..14 of the same variant's
truncated-chain s_bend route r episode (scene 3, about 20 m from the junction scene). The same
five frames serve every query of that episode, so the choice cannot depend on any query's score.

Every v3 call except H1, H2 and H3 is kept byte-identical: H0 repeat 0, the H0 repeats and both
controls. One H4 call per query is added, and call_ids are renumbered in order.

Usage: build_positive_control_manifest_v5.py --evidence-root DIR --v3-manifest FILE --out FILE
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os

import numpy as np
from PIL import Image

V3_SHA256 = "391c2f02a944cd46f3683f53e4979041b34bad9060f035cf779fd283781ccfa7"
ARM = "H4_unrelated_location_positive_control"
KEEP = ("H0_real", "CTRL_goal_only", "CTRL_reversed_node_rows")
DONOR_DECISIONS = range(10, 15)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_json(path):
    with open(path) as f:
        return json.load(f)


def pixels(path):
    return np.asarray(Image.open(path).convert("RGB"), np.float32)


def donor_episode(variant, route):
    return f"cmp-{variant}-trunc-20261009-01/s_bend_run_{route[-4:]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-root", required=True)
    ap.add_argument("--v3-manifest", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if sha(args.v3_manifest) != V3_SHA256:
        raise SystemExit("v3 manifest digest differs from the pinned one")
    v3 = read_json(args.v3_manifest)
    queries = {q["query_id"]: q for q in v3["queries"]}
    donors = {}
    for q in v3["queries"]:
        key = donor_episode(q["variant"], q["route"])
        if key in donors:
            continue
        d = os.path.join(args.evidence_root, key)
        m = read_json(os.path.join(d, "runtime_manifest.json"))
        if m["route"]["scene"] != "s_bend" or m["route"]["split"] != "dev":
            raise SystemExit(f"{key} is not a dev s_bend episode")
        frames = []
        for k in DONOR_DECISIONS:
            name = f"{m['inference'][k]['frame'] - 1}.jpg"
            path = os.path.join(d, "trajectory", name)
            got = sha(path)
            if got != m["file_sha256"][name]:
                raise SystemExit(f"HASH MISMATCH {path}")
            pose = m["captures"][m["inference"][k]["frame"] - 1]["pose"]
            frames.append(dict(file={"path": path, "sha256": got}, pose=pose))
        donors[key] = dict(frames=frames, scene_index=m["route"]["scene_index"],
                           origin_y=m["fixture"]["origin_y"])
    calls, divergence = [], {}
    for c in v3["calls"]:
        if c["arm"] in KEEP:
            calls.append({k: v for k, v in c.items() if k != "call_id"})
    for c in v3["calls"]:
        if c["arm"] != "H0_real" or c["repeat"] != 0:
            continue
        q = queries[c["query_id"]]
        donor = donors[donor_episode(q["variant"], q["route"])]
        obs = [f["file"] for f in donor["frames"]] + [c["obs"][-1]]
        calls.append({**{k: v for k, v in c.items() if k != "call_id"}, "arm": ARM, "obs": obs})
        qx, qy, _ = q["image_pose"]
        divergence[q["query_id"]] = dict(
            world_distance_to_query_m=[math.hypot(f["pose"][0] - qx, f["pose"][1] - qy)
                                       for f in donor["frames"]],
            mean_abs_px_vs_H0_slots=[float(np.abs(pixels(f["file"]["path"]) - pixels(h["path"])).mean())
                                     for f, h in zip(donor["frames"], c["obs"][:5], strict=True)])
    order = {"H0_real": 0, ARM: 1, "CTRL_goal_only": 2, "CTRL_reversed_node_rows": 3}
    calls.sort(key=lambda c: (c["query_id"], order[c["arm"]], c["repeat"]))
    for i, c in enumerate(calls):
        c["call_id"] = i
    count = {}
    for c in calls:
        count[c["arm"]] = count.get(c["arm"], 0) + 1
    px = [x for d in divergence.values() for x in d["mean_abs_px_vs_H0_slots"]]
    dist = [x for d in divergence.values() for x in d["world_distance_to_query_m"]]
    summary = dict(
        derived_from_v3_sha256=V3_SHA256, donor_rule="same variant, s_bend_run_<route>, decisions 10-14",
        donor_episodes={k: dict(scene_index=v["scene_index"], origin_y=v["origin_y"],
                                frames=[f["file"]["sha256"] for f in v["frames"]]) for k, v in donors.items()},
        queries=len(queries), calls_by_arm=count, total_forwards=len(calls),
        H4_world_distance_to_query_m=[min(dist), float(np.median(dist)), max(dist)],
        H4_mean_abs_px_vs_H0_slots=[min(px), float(np.median(px)), max(px)],
        reference_scale_inregion_consecutive_abs_change=v3["summary"]["reference_scale_inregion_consecutive_abs_change"])
    out = dict(summary=summary, queries=v3["queries"], H4_divergence=divergence, calls=calls)
    with open(args.out, "x") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(summary, indent=1))
    print("manifest sha256:", sha(args.out))


if __name__ == "__main__":
    main()
