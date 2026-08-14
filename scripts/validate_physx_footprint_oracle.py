"""Prove the PhysX footprint oracle answers known physical questions correctly.

The previous free-space estimator used mesh bounding boxes and an invented robot
radius, and produced 1.3% usable floor with every corridor length equal to the
search cap. Both failures were visible in the output and neither was caught,
because nothing in the pipeline knew what the right answer looked like.

So this harness builds scenes whose answers are fixed by construction, and
compares against ``physx_fixture_expected_answers.json`` -- written before this
file ran, from fixture geometry, never from the query implementation. Per FL-018,
a check that shares an implementation with the thing under test verifies the
implementation.

Three contracts the fixtures exist to pin down:

**Support and overlap are different questions.** A hole in the floor produces no
obstacle overlap at all. ``NO_FLOOR`` fails if the oracle reports occupiable, and
it is listed first because every other result depends on that distinction being
right.

**A boundary is not a measurement.** No hit before the cap means clear distance
``>= cap``, so ``distance`` is null and a lower bound is reported instead.
Emitting ``distance = cap`` asserts a wall exists exactly at the search limit --
which ``WALL_BEYOND_CAP`` guarantees is false.

**The API is trusted only behaviourally.** ``inspect.signature`` raises on these
native bindings, so argument order and yaw convention cannot be read off. The
``ROTATED_BOX`` fixture uses an aperture that admits one orientation and refuses
the other: an implementation with swapped half-extents or ignored yaw returns the
same answer for both, which no correct one can.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.measurement import Liveness, MeasurementEnvelope  # noqa: E402

OUT = REPO / "gates" / "scenes"
EXPECTED = OUT / "physx_fixture_expected_answers.json"

HX, HY = 0.1175, 0.0975      # measured half-extents
# The obstacle envelope is NOT the full body. The Yahboom's wheels rest on the
# floor by design, so a box spanning the whole 0.28 m body reports the floor
# itself as an obstacle -- which is what the first fixture run did: overlap_hits
# of 1 on bare floor and a sweep distance of 0.0 everywhere. Support and obstacle
# are separate questions, so the obstacle box starts above ground clearance and
# the floor is established separately by the downward probes. The floor is
# excluded by geometry, never by prim name.
GROUND_CLEARANCE_M = 0.02    # below this the wheels are meant to be in contact
HZ = (0.2803 - GROUND_CLEARANCE_M) / 2      # obstacle-envelope half height
OBSTACLE_BOX_CENTRE_Z = GROUND_CLEARANCE_M + HZ
SWEEP_CAP = 20.0
SUPPORT_PROBE_M = 1.0        # downward probe length from the query centre
SUPPORT_TOL_M = 0.05         # declared engineering tolerance for height agreement


def footprint_samples() -> list[tuple[float, float]]:
    """Centre plus four corners, in the robot's own frame."""
    return [(0.0, 0.0), (HX, HY), (HX, -HY), (-HX, HY), (-HX, -HY)]


def main() -> int:
    if not EXPECTED.is_file():
        print(f"REFUSED: expectations must exist before execution: {EXPECTED}", file=sys.stderr)
        return 2
    exp_doc = json.loads(EXPECTED.read_text())
    expected = {f["fixture_id"]: f for f in exp_doc["fixtures"]}

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    import omni.kit.commands
    from isaacsim.core.api import SimulationContext
    from omni.physx import get_physx_scene_query_interface
    from pxr import Gf, UsdGeom, UsdPhysics

    results: dict[str, Any] = {}
    envelopes: list[MeasurementEnvelope] = []

    def box(path: str, cx: float, cy: float, cz: float,
            sx: float, sy: float, sz: float) -> None:
        omni.kit.commands.execute("CreatePrim", prim_type="Cube", prim_path=path)
        prim = stage_utils.get_current_stage().GetPrimAtPath(path)
        xf = UsdGeom.Xformable(prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(cx, cy, cz))
        xf.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(sx / 2, sy / 2, sz / 2))
        UsdPhysics.CollisionAPI.Apply(prim)

    def run_fixture(fid: str, build) -> dict[str, Any]:
        """Each fixture gets a clean stage: leftover colliders would silently
        contaminate the next answer."""
        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0)
        build(box)
        sim.reset()
        for _ in range(12):
            sim.step(render=False)
        q = get_physx_scene_query_interface()

        live = Liveness(process_started=True, runtime_started=True,
                        subject_open_attempted=True, subject_open_succeeded=True,
                        measurement_executed=True, artifact_written=True)
        return {"sim": sim, "q": q, "live": live}

    def support(q: Any, x: float, y: float, z_start: float) -> dict[str, Any]:
        """Downward probes across the footprint. Support is its own question."""
        hits, heights = 0, []
        for dx, dy in footprint_samples():
            r = q.raycast_closest([x + dx, y + dy, z_start], [0.0, 0.0, -1.0], SUPPORT_PROBE_M)
            if r and r.get("hit"):
                hits += 1
                heights.append(z_start - r["distance"])
        spread = (max(heights) - min(heights)) if len(heights) > 1 else 0.0
        return {
            "samples": len(footprint_samples()), "hits": hits,
            "heights": [round(h, 4) for h in heights],
            "height_spread_m": round(spread, 4),
            "tolerance_m": SUPPORT_TOL_M,
            # Every sample must find floor: a footprint with one corner over a
            # ledge is not supported, however clear its centre.
            "support_valid": hits == len(footprint_samples()) and spread <= SUPPORT_TOL_M,
        }

    def overlap(q: Any, x: float, y: float, z: float, yaw_deg: float) -> dict[str, Any]:
        rot = Gf.Rotation(Gf.Vec3d(0, 0, 1), yaw_deg).GetQuat()
        n = q.overlap_box([HX, HY, HZ], [x, y, z],
                          [rot.GetImaginary()[0], rot.GetImaginary()[1],
                           rot.GetImaginary()[2], rot.GetReal()],
                          lambda h: True, False)
        return {"hits": int(n)}

    def sweep(q: Any, x: float, y: float, z: float, yaw_deg: float,
              dx: float, dy: float) -> dict[str, Any]:
        rot = Gf.Rotation(Gf.Vec3d(0, 0, 1), yaw_deg).GetQuat()
        r = q.sweep_box_closest(
            [HX, HY, HZ], [x, y, z],
            [rot.GetImaginary()[0], rot.GetImaginary()[1], rot.GetImaginary()[2], rot.GetReal()],
            [dx, dy, 0.0], SWEEP_CAP, False)
        if r and r.get("hit"):
            return {"sweep_status": "MEASURED_HIT",
                    "distance": round(float(r["distance"]), 4),
                    "collider": str(r.get("collision", "")),
                    "clear_run_lower_bound_m": None}
        # No hit within the cap. The quantity is bounded, not measured.
        return {"sweep_status": "CENSORED_AT_CAP", "distance": None,
                "clear_run_lower_bound_m": SWEEP_CAP,
                "note": "no hit within the search cap; clear distance >= cap, never == cap"}

    # ---------------------------------------------------------------- fixtures
    def f_no_floor(b):
        b("/World/floor_a", -3.0, 0.0, -0.05, 4.0, 8.0, 0.1)   # floor stops short
        b("/World/floor_b", 6.0, 0.0, -0.05, 4.0, 8.0, 0.1)    # resumes past the gap

    def f_open(b):
        b("/World/floor", 0.0, 0.0, -0.05, 60.0, 20.0, 0.1)

    def f_blocked(b):
        b("/World/floor", 0.0, 0.0, -0.05, 40.0, 20.0, 0.1)
        b("/World/obstacle", 0.0, 0.0, 0.20, 0.4, 0.4, 0.4)

    def _gap(width: float, terminal: float | None):
        def build(b):
            b("/World/floor", 0.0, 0.0, -0.05, 40.0, 20.0, 0.1)
            off = width / 2 + 0.5
            b("/World/wall_l", 2.0, off, 0.25, 0.4, 1.0, 0.5)
            b("/World/wall_r", 2.0, -off, 0.25, 0.4, 1.0, 0.5)
            if terminal is not None:
                b("/World/terminal", terminal, 0.0, 0.25, 0.2, 6.0, 0.5)
        return build

    def f_wall(b):
        b("/World/floor", 0.0, 0.0, -0.05, 40.0, 20.0, 0.1)
        b("/World/wall", 3.0 + 0.1, 0.0, 0.25, 0.2, 6.0, 0.5)   # near face at 3.0 m

    def f_wall_far(b):
        b("/World/floor", 0.0, 0.0, -0.05, 80.0, 20.0, 0.1)
        b("/World/wall", 30.0, 0.0, 0.25, 0.2, 6.0, 0.5)

    def f_rot(b):
        b("/World/floor", 0.0, 0.0, -0.05, 40.0, 20.0, 0.1)
        off = 0.220 / 2 + 0.5
        b("/World/wall_l", 2.0, off, 0.25, 0.4, 1.0, 0.5)
        b("/World/wall_r", 2.0, -off, 0.25, 0.4, 1.0, 0.5)

    Z = OBSTACLE_BOX_CENTRE_Z  # above ground clearance; floor is support, not obstacle

    ctx = run_fixture("NO_FLOOR", f_no_floor)
    s = support(ctx["q"], 2.0, 0.0, 0.5)
    o = overlap(ctx["q"], 2.0, 0.0, Z, 0.0)
    results["NO_FLOOR"] = {"support": s, "overlap": o,
                           "occupiable": s["support_valid"] and o["hits"] == 0}

    ctx = run_fixture("OPEN_FLOOR", f_open)
    s = support(ctx["q"], 0.0, 0.0, 0.5)
    o = overlap(ctx["q"], 0.0, 0.0, Z, 0.0)
    w = sweep(ctx["q"], 0.0, 0.0, Z, 0.0, 1.0, 0.0)
    results["OPEN_FLOOR"] = {"support": s, "overlap": o, "sweep": w,
                             "occupiable": s["support_valid"] and o["hits"] == 0}

    ctx = run_fixture("BLOCKED_POSE", f_blocked)
    s = support(ctx["q"], 0.0, 0.0, 0.5)
    o = overlap(ctx["q"], 0.0, 0.0, Z, 0.0)
    results["BLOCKED_POSE"] = {"support": s, "overlap": o,
                               "occupiable": s["support_valid"] and o["hits"] == 0}

    ctx = run_fixture("NARROW_GAP", _gap(0.150, None))
    s = support(ctx["q"], 0.0, 0.0, 0.5)
    o = overlap(ctx["q"], 0.0, 0.0, Z, 0.0)
    w = sweep(ctx["q"], 0.0, 0.0, Z, 0.0, 1.0, 0.0)
    results["NARROW_GAP"] = {"support": s, "overlap": o, "sweep": w,
                             "occupiable": s["support_valid"] and o["hits"] == 0,
                             "traversable": w["sweep_status"] == "CENSORED_AT_CAP"}

    ctx = run_fixture("WIDE_GAP", _gap(0.400, 6.0))
    s = support(ctx["q"], 0.0, 0.0, 0.5)
    o = overlap(ctx["q"], 0.0, 0.0, Z, 0.0)
    w = sweep(ctx["q"], 0.0, 0.0, Z, 0.0, 1.0, 0.0)
    results["WIDE_GAP"] = {"support": s, "overlap": o, "sweep": w,
                           "occupiable": s["support_valid"] and o["hits"] == 0,
                           "traversable": w["sweep_status"] == "MEASURED_HIT"
                           and (w["distance"] or 0) > 2.5}

    ctx = run_fixture("WALL_HIT", f_wall)
    s = support(ctx["q"], 0.0, 0.0, 0.5)
    o = overlap(ctx["q"], 0.0, 0.0, Z, 0.0)
    w = sweep(ctx["q"], 0.0, 0.0, Z, 0.0, 1.0, 0.0)
    results["WALL_HIT"] = {"support": s, "overlap": o, "sweep": w,
                        "occupiable": s["support_valid"] and o["hits"] == 0}

    ctx = run_fixture("WALL_BEYOND_CAP", f_wall_far)
    s = support(ctx["q"], 0.0, 0.0, 0.5)
    o = overlap(ctx["q"], 0.0, 0.0, Z, 0.0)
    w = sweep(ctx["q"], 0.0, 0.0, Z, 0.0, 1.0, 0.0)
    results["WALL_BEYOND_CAP"] = {"support": s, "overlap": o, "sweep": w,
                        "occupiable": s["support_valid"] and o["hits"] == 0}

    ctx = run_fixture("ROTATED_BOX", f_rot)
    w_al = sweep(ctx["q"], 0.0, 0.0, Z, 0.0, 1.0, 0.0)
    w_pp = sweep(ctx["q"], 0.0, 0.0, Z, 90.0, 1.0, 0.0)
    results["ROTATED_BOX"] = {
        "aligned": w_al, "perpendicular": w_pp,
        "traversable_at_yaw_aligned": w_al["sweep_status"] == "CENSORED_AT_CAP",
        "traversable_at_yaw_perpendicular": w_pp["sweep_status"] == "CENSORED_AT_CAP",
    }

    ctx = run_fixture("FILTERING", f_blocked)
    o = overlap(ctx["q"], 0.0, 0.0, Z, 0.0)
    results["FILTERING"] = {"overlap": o, "obstacle_detected": o["hits"] > 0}

    # ------------------------------------------------------------ adjudication
    def check(fid: str) -> dict[str, Any]:
        e, r = expected[fid]["expected"], results[fid]
        fails = []

        def cmp(key: str, got: Any) -> None:
            if key not in e:
                return
            want = e[key]
            if want == ">0":
                if not (isinstance(got, int) and got > 0):
                    fails.append(f"{key}: expected >0, got {got}")
            elif isinstance(want, float) and isinstance(got, (int, float)):
                tol = e.get("tolerance_m", 0.1)
                if got is None or abs(got - want) > tol:
                    fails.append(f"{key}: expected {want}+-{tol}, got {got}")
            elif got != want:
                fails.append(f"{key}: expected {want!r}, got {got!r}")

        cmp("support_valid", r.get("support", {}).get("support_valid"))
        cmp("overlap_hits", r.get("overlap", {}).get("hits"))
        cmp("occupiable", r.get("occupiable"))
        cmp("traversable", r.get("traversable"))
        cmp("obstacle_detected", r.get("obstacle_detected"))
        cmp("sweep_status", r.get("sweep", {}).get("sweep_status"))
        cmp("distance", r.get("sweep", {}).get("distance"))
        cmp("clear_run_lower_bound_m", r.get("sweep", {}).get("clear_run_lower_bound_m"))
        cmp("first_hit_distance_m_approx", r.get("sweep", {}).get("distance"))
        cmp("traversable_at_yaw_aligned", r.get("traversable_at_yaw_aligned"))
        cmp("traversable_at_yaw_perpendicular", r.get("traversable_at_yaw_perpendicular"))
        return {"result": "PASS" if not fails else "FAIL", "failures": fails}

    verdicts = {fid: check(fid) for fid in results}
    for fid, v in verdicts.items():
        envelopes.append(MeasurementEnvelope(
            measurement=f"physx_fixture_{fid}",
            liveness=Liveness(process_started=True, runtime_started=True,
                              subject_open_attempted=True, subject_open_succeeded=True,
                              measurement_executed=True, artifact_written=True),
            value=v["result"], items_examined=1,
            evidence={"observed": results[fid], "expected": expected[fid]["expected"]},
        ))

    doc = {
        "check": "PHYSX_FOOTPRINT_ORACLE_VALIDATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "expectations_digest": exp_doc["expected_answers_digest"],
        "expectations_written_at": exp_doc["written_at"],
        "footprint_half_extents_m": [HX, HY, HZ],
        "sweep_cap_m": SWEEP_CAP,
        "support_tolerance_m": SUPPORT_TOL_M,
        "results": results, "verdicts": verdicts,
        "measurements": [e.to_json() for e in envelopes],
        "all_pass": all(v["result"] == "PASS" for v in verdicts.values()),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "physx_fixture_results.json").write_text(json.dumps(doc, indent=2, default=str) + "\n")

    print("PHYSX FOOTPRINT ORACLE — known-answer fixtures")
    print("=" * 68)
    for fid, v in verdicts.items():
        print(f"  {fid:<18} {v['result']}")
        for f in v["failures"]:
            print(f"      {f}")
    print(f"\n  ALL PASS: {doc['all_pass']}")
    app.close()
    return 0 if doc["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
