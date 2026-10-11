"""SUPPORT causal controls, on a fixture where targets can actually be removed.

Hospital could not supply this. Its floors are USD instance proxies, so
``CollisionAPI`` cannot be authored on them and the removal control refused to
run -- recorded there as NOT_RUN rather than as a null result. Without it, the
SUPPORT identity claim rests on prefix matching alone, which cannot distinguish
"this target answered" from "something coincident with this target answered".

So the controls run here instead, on synthetic geometry built from first
principles, with no Hospital value used anywhere in its construction. Five cases,
all under the frozen production SUPPORT policy:

    CORRECT_TARGET      the declared target is present and collidable
    TARGET_REMOVED      the same probe, its collider disabled
    WRONG_COLLIDER      a slab above the target intercepts the ray first
    SHARED_OWNER        several declared targets sit above one shared slab
    UNRELATED_GEOMETRY  a declared target with no collider anywhere beneath it

SHARED_OWNER reproduces the mechanism of the historical 12x5.9 defect: twelve
distinct declared targets in the Office audit at ``acd53d0`` all answered by one
wall, ``/World/Scene/SM_Wall_6m24_269/SM_Wall_6m/SM_Wall_6m``, at one distance,
5.9 m. The signature is a count times a value -- twelve probes, 5.9 m each -- not
a room measuring 12 by 5.9. This fixture is built to reproduce that *mechanism*
from geometry; its numbers are not tuned to reproduce 5.9, which would be fitting
a fixture to a remembered answer.

DIAGNOSTIC ONLY. Nothing here is an expectation, and no metric is selected. The
output populates the cells a replacement criterion would later have to satisfy.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.candidate_policy import (  # noqa: E402
    DEFAULT_POLICY,
    Aabb,
    Role,
    generate_candidates,
    policy_digest,
)
from navfm.evidence import emit_evidence  # noqa: E402
from navfm.probe_adjudication import identity_matches  # noqa: E402

#: Fixture geometry, chosen for separation rather than to hit any particular
#: number. Targets are 0.40 m cubes; the shared slab is wide enough to sit under
#: several of them at once.
TARGET_SIZE = 0.40
SLAB_SIZE = (6.0, 6.0, 0.10)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    import omni.kit.commands
    from isaacsim.core.api import SimulationContext
    from omni.physx import get_physx_scene_query_interface
    from pxr import Gf, UsdGeom, UsdPhysics

    rec: dict[str, Any] = {
        "check": "SUPPORT_CAUSAL_CONTROLS",
        "artifact_semantics": "DIAGNOSTIC_ONLY_NOT_AN_EXPECTATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "production_policy_digest": policy_digest(),
        "support_start_height_m": DEFAULT_POLICY.support.start_height_m,
        "historical_defect_reproduced_as_mechanism": {
            "signature": "12 x 5.9 m",
            "reading": ("twelve probes each returning 5.9 m, not a 12 m by 5.9 m room; "
                        "a count times a value"),
            "source_commit": "acd53d0",
            "source_path": "gates/scenes/office_collision_coverage_audit.json",
            "mechanism": ("twelve distinct declared door targets all answered by one collider, "
                          "/World/Scene/SM_Wall_6m24_269/SM_Wall_6m/SM_Wall_6m, at one distance"),
            "class": "SHARED_COLLIDER_ALIASING",
            "note": "geometry here reproduces the mechanism; it is not tuned to yield 5.9",
        },
        "claim_boundary": ("Establishes what each candidate observable can and cannot detect on "
                           "synthetic geometry. Says nothing about Hospital, and selects no metric."),
    }

    def make_box(path: str, c: tuple[float, float, float],
                 s: tuple[float, float, float], collide: bool = True) -> None:
        omni.kit.commands.execute("CreatePrim", prim_type="Cube", prim_path=path)
        prim = stage_utils.get_current_stage().GetPrimAtPath(path)
        xf = UsdGeom.Xformable(prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(*c))
        xf.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(s[0] / 2, s[1] / 2, s[2] / 2))
        if collide:
            UsdPhysics.CollisionAPI.Apply(prim)

    def aabb(c: tuple[float, float, float], s: tuple[float, float, float]) -> Aabb:
        return Aabb((c[0] - s[0] / 2, c[1] - s[1] / 2, c[2] - s[2] / 2),
                    (c[0] + s[0] / 2, c[1] + s[1] / 2, c[2] + s[2] / 2))

    def probe(q: Any, target: str, box: Aabb) -> dict[str, Any]:
        cand = generate_candidates(target, Role.SUPPORT, box, policy=DEFAULT_POLICY).candidates[0]
        res = q.raycast_closest(list(cand.origin), list(cand.direction), cand.max_range)
        hit = bool(res and res.get("hit"))
        collider = str(res.get("collision", "")) if hit else None
        observed = float(res.get("distance")) if hit else None
        expected = cand.origin[2] - box.maximum[2]
        match = identity_matches(collider, target)
        return {
            "declared_target": target,
            "origin": list(cand.origin), "direction": list(cand.direction),
            "expected_distance_m": expected,
            "observed_distance_m": observed,
            "residual_m": (observed - expected) if observed is not None else None,
            "hit": hit, "returned_collider": collider, "identity_match": match,
        }

    def fresh() -> Any:
        stage_utils.create_new_stage()
        return SimulationContext(stage_units_in_meters=1.0)

    def settle(sim: Any, n: int = 12) -> Any:
        sim.reset()
        for _ in range(n):
            sim.step(render=False)
        return get_physx_scene_query_interface()

    cases: dict[str, Any] = {}
    try:
        t_c, t_s = (0.0, 0.0, 1.0), (TARGET_SIZE,) * 3
        box = aabb(t_c, t_s)

        # CORRECT_TARGET -------------------------------------------------------
        sim = fresh()
        make_box("/World/T", t_c, t_s)
        cases["CORRECT_TARGET"] = probe(settle(sim), "/World/T", box)

        # TARGET_REMOVED -------------------------------------------------------
        sim = fresh()
        make_box("/World/T", t_c, t_s, collide=False)
        cases["TARGET_REMOVED"] = probe(settle(sim), "/World/T", box)

        # WRONG_COLLIDER: a slab intercepts the ray above the declared target ---
        sim = fresh()
        make_box("/World/T", t_c, t_s)
        make_box("/World/Interloper", (0.0, 0.0, 1.0 + TARGET_SIZE / 2 + 0.25), (2.0, 2.0, 0.05))
        cases["WRONG_COLLIDER"] = probe(settle(sim), "/World/T", box)

        # SHARED_OWNER: several declared targets, one collidable slab beneath ---
        sim = fresh()
        shared = []
        for i, x in enumerate((-1.0, 0.0, 1.0)):
            c = (x, 0.0, 1.0)
            make_box(f"/World/S{i}", c, t_s, collide=False)   # declared, not collidable
            shared.append((f"/World/S{i}", aabb(c, t_s)))
        make_box("/World/SharedSlab", (0.0, 0.0, 0.60), SLAB_SIZE)
        q = settle(sim)
        rows = [probe(q, path, b) for path, b in shared]
        cases["SHARED_OWNER"] = {
            "probes": rows,
            "distinct_declared_targets": len({r["declared_target"] for r in rows}),
            "distinct_returned_colliders": len({r["returned_collider"] for r in rows}),
            "distinct_observed_distances": len({r["observed_distance_m"] for r in rows}),
            "any_identity_match": any(r["identity_match"] for r in rows),
        }

        # UNRELATED_GEOMETRY: nothing collidable beneath the declared target ----
        sim = fresh()
        make_box("/World/T", t_c, t_s, collide=False)
        make_box("/World/Elsewhere", (10.0, 10.0, 0.5), (1.0, 1.0, 1.0))
        cases["UNRELATED_GEOMETRY"] = probe(settle(sim), "/World/T", box)

        rec["cases"] = cases

        # ---- what each candidate observable would have said -------------------
        def verdicts(name: str, r: dict[str, Any]) -> dict[str, Any]:
            obs, res = r.get("observed_distance_m"), r.get("residual_m")
            return {
                "old_invariant_applicable": "NOT_IDENTIFIABLE",   # single probe, and see the proof
                "geometric_residual": ("PASS" if res is not None and abs(res) < 1e-3
                                       else "FAIL" if res is not None else "NO_HIT"),
                "identity_causal": "PASS" if r.get("identity_match") else "FAIL",
                "observed_distance_m": obs,
            }
        rec["per_case_observable_response"] = {
            k: verdicts(k, v) for k, v in cases.items() if isinstance(v, dict) and "hit" in v
        }
        sh = cases["SHARED_OWNER"]
        rec["per_case_observable_response"]["SHARED_OWNER"] = {
            "old_invariant_applicable": ("FIRES" if sh["distinct_observed_distances"] == 1
                                         and len(sh["probes"]) > 2 else "DOES_NOT_FIRE"),
            "geometric_residual": ("FAIL" if any(
                r["residual_m"] is None or abs(r["residual_m"]) >= 1e-3 for r in sh["probes"])
                else "PASS"),
            "identity_causal": "FAIL" if not sh["any_identity_match"] else "PASS",
            "note": "this is the historical 12x5.9 mechanism",
        }

    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=("check", "artifact_semantics"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
