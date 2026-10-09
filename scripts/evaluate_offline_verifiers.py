"""Frozen thresholds (learned 7.745, pixel NCC 0.893) on the decision frames of the 44 fresh episodes.

Primary population: decisions before the latched stop (policy_stop false). Decisions at or
after the stop are reported separately: the stop is selected by the check under test for the
verifying variants, and post-stop frames are stationary repeats, so pooling them inflates
near-goal acceptance.
"""

import glob
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate_components import ncc

E = Path("/home/favl/navfm-runtime-evidence")
GR = E / "arrival-goal-traversal-final-frame-20261009-01"
goals = json.loads((GR / "goal_source.json").read_text())["goals"]
T_L, T_P = 7.745, 0.893
rows = []
for mp in sorted(glob.glob(str(E / "cmp-*-20261009-01/*/runtime_manifest.json"))):
    ep = Path(mp).parent
    m = json.loads(Path(mp).read_text())
    r = m["route"]["id"]
    src = json.loads((GR / r / "runtime_manifest.json").read_text())
    g = np.array(src["captures"][goals[r]["frame"]]["pose"][:2])
    goal = np.asarray(Image.open(ep / "goal.png").convert("RGB"))
    for x in m["inference"]:
        d = float(np.linalg.norm(np.array(m["captures"][x["frame"]]["pose"][:2]) - g))
        cur = np.asarray(Image.open(ep / "trajectory" / f"{x['frame']}.jpg").convert("RGB"))
        rows.append(
            (
                ep.parent.name,
                d,
                x["requested_goal_distance"],
                ncc(cur, goal),
                bool(x["policy_stop"]),
            )
        )
d = np.array([t[1] for t in rows])
L = np.array([t[2] for t in rows], float)
P = np.array([t[3] for t in rows])
stopped = np.array([t[4] for t in rows])
out = {"frames": len(rows), "thresholds": {"learned": T_L, "pixel_ncc": T_P}}
for pop, keep in [("pre_stop", ~stopped), ("at_or_after_stop", stopped)]:
    out[pop] = {"frames": int(keep.sum())}
    for name, sel in [
        ("near<=0.5", d <= 0.5),
        ("far>0.75", d > 0.75),
        ("band0.75-1.0", (d > 0.75) & (d <= 1.0)),
        ("band1.0-1.5", (d > 1.0) & (d <= 1.5)),
        (">1.5", d > 1.5),
    ]:
        sel = sel & keep
        out[pop][name] = {
            "frames": int(sel.sum()),
            "learned_accept": float(np.mean(L[sel] <= T_L)) if sel.any() else None,
            "pixel_accept": float(np.mean(P[sel] >= T_P)) if sel.any() else None,
        }
Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
