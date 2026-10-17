"""v3 call manifest (supersedes v2: reference scales replace the practical scale; no change to calls).
v2 docstring follows.
v2 call manifest for the offline history-sensitivity diagnostic (supersedes v1).
Metadata, file hashes and raw pixel statistics only: no model, no predictions.
Logged requested_goal_distance is read only to (a) report the reproduction gap later and
(b) compute the declared practical scale, which uses logged scores of the SAME H0 inputs'
episodes, never any H1/H2/H3 output.

Changes from v1 (red-team review, 2026-10-16):
  F3  query/history poses = captures[f-1] (image pose; captures[f] is pose_after command f)
  F4  match = nearest-by-base-distance among candidates passing BOTH gates; reuse reported
  F1  H2 relabelled; per-slot pose and pixel divergence from H0 recorded; H3 added
  F7  goal-only controls spread 3 per episode; + 1 row-permutation control per episode
  F2  repeats reduced to 3 per episode (12 queries); scale declared in protocol
"""
import hashlib
import json
import math
import os
import sys

import numpy as np
from PIL import Image

E = "/home/favl/navfm-runtime-evidence"
EPISODES = [(v, r) for r in ("junction_run_0000", "junction_run_0001") for v in ("C_verify", "D_both")]
RADIUS, MATCH_M, MATCH_DEG, SHIFT = 0.5, 0.10, 5.0, 5
CTRL_PER_EP = 3  # repeat, goal-only; permutation: 1 per episode


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def wrapd(a):
    return (math.degrees(a) + 180) % 360 - 180


def load(v, r):
    d = f"{E}/cmp-{v}-trunc-20261009-01/{r}"
    m = json.load(open(f"{d}/runtime_manifest.json"))
    s = m["goal_source_frame"]
    src = os.path.dirname(os.path.dirname(s["source"]))
    gx, gy, _ = json.load(open(f"{src}/runtime_manifest.json"))["captures"][s["frame"]]["pose"]
    cam = m["camera_local_pose"][0]
    dec = []
    for k, i in enumerate(m["inference"]):
        f = i["frame"]
        if f < 1:
            dec.append(None)
            continue
        x, y, yaw = m["captures"][f - 1]["pose"]  # pose at which (f-1).jpg was rendered
        cx, cy = x + cam[0] * math.cos(yaw), y + cam[0] * math.sin(yaw)
        dec.append(dict(k=k, frame=f, image_frame=f - 1, pose=[x, y, yaw], cam_xy=[cx, cy],
                        dist_scoring=math.hypot(x - gx, y - gy), window=i["chain"]["window"],
                        logged=i["requested_goal_distance"]))
    return d, m, dec


def img(d, m, frame):
    p = f"{d}/trajectory/{frame}.jpg"
    got = sha(p)
    if got != m["file_sha256"][f"{frame}.jpg"]:
        raise SystemExit(f"HASH MISMATCH {p}")
    return {"path": p, "sha256": got}


def pix(p):
    return np.asarray(Image.open(p).convert("RGB"), np.float32)


def divergence(a_imgs, a_dec, b_imgs, b_dec):
    out = []
    for (ia, da), (ib, db) in zip(zip(a_imgs, a_dec), zip(b_imgs, b_dec)):
        out.append(dict(pos_m=math.hypot(da["pose"][0] - db["pose"][0], da["pose"][1] - db["pose"][1]),
                        dyaw_deg=abs(wrapd(da["pose"][2] - db["pose"][2])),
                        mean_abs_px=float(np.abs(pix(ia["path"]) - pix(ib["path"])).mean()),
                        same_bytes=ia["sha256"] == ib["sha256"]))
    return out


def main(out):
    eps = {key: load(*key) for key in EPISODES}
    queries, calls, pop, reuse = [], [], {}, {}
    for (v, r), (d, m, dec) in eps.items():
        other = "D_both" if v == "C_verify" else "C_verify"
        od, om, odec = eps[(other, r)]
        chain = json.load(open(f"{m['topomap']['root']}/chain.json"))["routes"][r]["nodes"]
        assert [[n["frame"], n["sha256"]] for n in chain] == m["topomap"]["nodes"], "chain binding"
        goal_png = {"path": f"{d}/goal.png", "sha256": sha(f"{d}/goal.png")}
        assert goal_png["sha256"] == m["fixed_goal_sha256"], "goal binding"
        n_in = 0
        for q in dec:
            if q is None or q["dist_scoring"] > RADIUS:
                continue
            n_in += 1
            if q["k"] < 5 + SHIFT:  # H0 and H3 both need real, non-initial frames
                raise SystemExit(f"query {v}/{r}/k{q['k']} lacks predecessors for H3")
            qid = f"{v}/{r}/k{q['k']:03d}"
            s, e = q["window"]
            refs = [{"path": n["source"], "sha256": n["sha256"]} for n in chain[s:e + 1]]
            for ref in refs:
                if sha(ref["path"]) != ref["sha256"]:
                    raise SystemExit(f"HASH MISMATCH {ref['path']}")
            qimg = img(d, m, q["image_frame"])
            h0_dec = [dec[q["k"] - j] for j in range(5, 0, -1)]
            h3_dec = [dec[q["k"] - SHIFT - j] for j in range(5, 0, -1)]
            h0 = [img(d, m, x["image_frame"]) for x in h0_dec]
            h3 = [img(d, m, x["image_frame"]) for x in h3_dec]
            cand = [o for o in odec if o is not None and o["k"] >= 5
                    and math.hypot(o["pose"][0] - q["pose"][0], o["pose"][1] - q["pose"][1]) <= MATCH_M
                    and abs(wrapd(o["pose"][2] - q["pose"][2])) <= MATCH_DEG]
            match = None
            if cand:
                b = min(cand, key=lambda o: math.hypot(o["pose"][0] - q["pose"][0], o["pose"][1] - q["pose"][1]))
                h2_dec = [odec[b["k"] - j] for j in range(5, 0, -1)]
                h2 = [img(od, om, x["image_frame"]) for x in h2_dec]
                match = dict(other_variant=other, k=b["k"],
                             base_dist_m=math.hypot(b["pose"][0] - q["pose"][0], b["pose"][1] - q["pose"][1]),
                             dyaw_deg=abs(wrapd(b["pose"][2] - q["pose"][2])),
                             camera_dist_m=math.hypot(b["cam_xy"][0] - q["cam_xy"][0], b["cam_xy"][1] - q["cam_xy"][1]),
                             divergence_from_H0=divergence(h2, h2_dec, h0, h0_dec))
                reuse.setdefault(f"{other}/{r}/k{b['k']:03d}", []).append(qid)
            queries.append(dict(query_id=qid, variant=v, route=r, k=q["k"], decision_frame=q["frame"],
                                image_frame=q["image_frame"], image_pose=q["pose"], camera_xy=q["cam_xy"],
                                dist_scoring_m=q["dist_scoring"], logged_requested_goal_distance=q["logged"],
                                window=[s, e], n_refs=len(refs), match=match,
                                H3_divergence_from_H0=divergence(h3, h3_dec, h0, h0_dec)))
            base = dict(query_id=qid, goal_row_index=len(refs), batch_rows=refs + [goal_png])
            calls.append({**base, "arm": "H0_real", "repeat": 0, "obs": h0 + [qimg]})
            calls.append({**base, "arm": "H1_repeated_static", "repeat": 0, "obs": [qimg] * 6})
            calls.append({**base, "arm": "H3_own_history_shifted5", "repeat": 0, "obs": h3 + [qimg]})
            if match:
                calls.append({**base, "arm": "H2_posematched_other_variant", "repeat": 0, "obs": h2 + [qimg]})
        pop[f"{v}/{r}"] = dict(queries=n_in, decisions=len(dec))
    # controls: CTRL_PER_EP queries per episode at fixed positions (first, middle, last by k)
    for key in [f"{v}/{r}" for v, r in EPISODES]:
        qs = [q for q in queries if q["query_id"].startswith(key + "/")]
        picks = [qs[0], qs[len(qs) // 2], qs[-1]][:CTRL_PER_EP]
        for q in picks:
            h0 = next(c for c in calls if c["query_id"] == q["query_id"] and c["arm"] == "H0_real")
            for rep in (1, 2):
                calls.append({**h0, "arm": "H0_real", "repeat": rep})
            calls.append({"query_id": q["query_id"], "arm": "CTRL_goal_only", "repeat": 0, "goal_row_index": 0,
                          "batch_rows": [h0["batch_rows"][-1]], "obs": h0["obs"]})
        q = picks[1]
        h0 = next(c for c in calls if c["query_id"] == q["query_id"] and c["arm"] == "H0_real")
        rows = list(reversed(h0["batch_rows"][:-1])) + [h0["batch_rows"][-1]]
        calls.append({"query_id": q["query_id"], "arm": "CTRL_reversed_node_rows", "repeat": 0,
                      "goal_row_index": len(rows) - 1, "batch_rows": rows, "obs": h0["obs"]})
    for i, c in enumerate(calls):
        c["call_id"] = i
    count = {}
    for c in calls:
        count[c["arm"]] = count.get(c["arm"], 0) + 1
    elig = [q for q in queries if q["match"]]
    pairs = {tuple(sorted([q["query_id"], f"{q['match']['other_variant']}/{q['route']}/k{q['match']['k']:03d}"]))
             for q in elig}
    # v3 (review 2, F1/F2): descriptive REFERENCE scales only, never a materiality gate.
    # In-region consecutive decisions (k and k+1 both queries) of each episode; pose, image,
    # 5/6 of history and (in C) steering state all change between them.
    ref = {}
    allsteps = []
    for key in sorted({f"{q['variant']}/{q['route']}" for q in queries}):
        xs = sorted((q for q in queries if f"{q['variant']}/{q['route']}" == key), key=lambda q: q["k"])
        st = [abs(b["logged_requested_goal_distance"] - a["logged_requested_goal_distance"])
              for a, b in zip(xs, xs[1:]) if b["k"] == a["k"] + 1]
        allsteps += st
        ref[key] = dict(n=len(st), median=float(np.median(st)), p25=float(np.percentile(st, 25)),
                        p75=float(np.percentile(st, 75)))
    ref["pooled"] = dict(n=len(allsteps), median=float(np.median(allsteps)),
                         p25=float(np.percentile(allsteps, 25)), p75=float(np.percentile(allsteps, 75)))
    margins = [abs(q["logged_requested_goal_distance"] - 7.745) for q in queries]
    h2div = [s for q in elig for s in q["match"]["divergence_from_H0"]]
    h3div = [s for q in queries for s in q["H3_divergence_from_H0"]]
    summary = dict(
        population=pop, queries=len(queries), eligible_H2=len(elig),
        H2_distinct_unordered_pairs=len(pairs),
        H2_reused_matches={k: v for k, v in reuse.items() if len(v) > 1},
        calls_by_arm=count, total_forwards=len(calls),
        batch_rows_range=[min(len(c["batch_rows"]) for c in calls if c["arm"].startswith("H")),
                          max(len(c["batch_rows"]) for c in calls)],
        match_residuals=dict(base_m_max=max(q["match"]["base_dist_m"] for q in elig),
                             dyaw_deg_max=max(q["match"]["dyaw_deg"] for q in elig),
                             camera_m_max=max(q["match"]["camera_dist_m"] for q in elig)),
        H2_slot_divergence=dict(pos_m=[min(s["pos_m"] for s in h2div), float(np.median([s["pos_m"] for s in h2div])), max(s["pos_m"] for s in h2div)],
                                mean_abs_px_median=float(np.median([s["mean_abs_px"] for s in h2div]))),
        H3_slot_divergence=dict(pos_m=[min(s["pos_m"] for s in h3div), float(np.median([s["pos_m"] for s in h3div])), max(s["pos_m"] for s in h3div)],
                                mean_abs_px_median=float(np.median([s["mean_abs_px"] for s in h3div]))),
        reference_scale_inregion_consecutive_abs_change=ref,
        logged_threshold_margin=dict(median=float(np.median(margins)), n_within_1=int(sum(m <= 1 for m in margins)),
                                     n=len(margins)),
        H2_pair_directions=(lambda dn: dict(
            mutual_both_directions=sum(1 for a, b in pairs if dn.get(a) == b and dn.get(b) == a),
            one_direction=sum(1 for a, b in pairs if not (dn.get(a) == b and dn.get(b) == a)),
            queries_in_more_than_one_pair=sum(1 for x in {m for p in pairs for m in p}
                                              if sum(x in p for p in pairs) > 1)))(
            {q["query_id"]: f"{q['match']['other_variant']}/{q['route']}/k{q['match']['k']:03d}" for q in elig}),
        H3_gap_frames_last_slot_to_query=sorted({int(c["obs"][-1]["path"].rsplit("/", 1)[1][:-4]) - int(c["obs"][-2]["path"].rsplit("/", 1)[1][:-4])
                                                 for c in calls if c["arm"].startswith("H3")}),
        H0_gap_frames_last_slot_to_query=sorted({int(c["obs"][-1]["path"].rsplit("/", 1)[1][:-4]) - int(c["obs"][-2]["path"].rsplit("/", 1)[1][:-4])
                                                 for c in calls if c["arm"] == "H0_real"}))
    json.dump(dict(summary=summary, queries=queries, calls=calls), open(out, "w"), indent=1)
    print(json.dumps(summary, indent=1))
    print("manifest sha256:", sha(out))


if __name__ == "__main__":
    main(sys.argv[1])
