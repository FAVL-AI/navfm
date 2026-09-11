"""Q1 — was the frozen route executable inside the frozen budget at all?

A feasibility question, answered offline from versioned artefacts. It is NOT a
controller diagnosis, and it has no authority to become one: Q1 asks only whether
an idealised execution under the declared limits could finish in the budget.

The order matters. Asking about controller behaviour first risks diagnosing a
controller for failing to complete a route no controller could complete in the
budget, so feasibility is settled before execution quality is examined at all.

Three budgets are computed separately and never collapsed into one number, because
they answer different questions: an absolute bound at the velocity ceiling, a
bound at the speed the controller can actually command, and the budget available.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--population", required=True)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import hashlib

    from navfm.control import M3PRO_LIMITS
    from navfm.isaac.app import SimConfig
    from navfm.isaac.collect import CollectConfig

    pop = json.loads(Path(args.population).read_text())
    col = json.loads(Path(args.collection).read_text())
    sel = pop["selected_candidate"]
    cfg = CollectConfig()
    sim = SimConfig()

    # ---- every input bound to its source -------------------------------
    inputs: dict[str, Any] = {
        "planned_route_length_m": {
            "value": sel["route_length_m"], "unit": "m",
            "source": f"{args.population} -> selected_candidate.route_length_m",
            "artefact_sha256": hashlib.sha256(Path(args.population).read_bytes()).hexdigest()},
        "max_steps": {"value": cfg.max_steps, "unit": "steps",
                      "source": "src/navfm/isaac/collect.py CollectConfig.max_steps"},
        "control_hz": {"value": sim.hz, "unit": "Hz",
                       "source": "src/navfm/isaac/app.py SimConfig.hz"},
        "control_dt": {"value": sim.dt, "unit": "s",
                       "source": "src/navfm/isaac/app.py SimConfig.dt = 1/hz"},
        "max_linear_velocity": {"value": M3PRO_LIMITS.max_v, "unit": "m/s",
                                "source": "src/navfm/control.py M3PRO_LIMITS.max_v"},
        "commanded_cruise_velocity": {"value": cfg.cruise_v, "unit": "m/s",
                                      "source": "src/navfm/isaac/collect.py CollectConfig.cruise_v"},
        "max_angular_velocity": {"value": M3PRO_LIMITS.max_w, "unit": "rad/s",
                                 "source": "src/navfm/control.py M3PRO_LIMITS.max_w"},
        "goal_tolerance_m": {"value": cfg.goal_tol_m, "unit": "m",
                             "source": "src/navfm/isaac/collect.py CollectConfig.goal_tol_m"},
        "planned_turn_magnitudes_deg": {
            "value": sel["planned_turn_magnitudes_deg"], "unit": "deg",
            "source": f"{args.population} -> selected_candidate.planned_turn_magnitudes_deg"},
    }

    semantics = {
        "acceleration_limits": {
            "configured": {"max_a": M3PRO_LIMITS.max_a, "max_alpha": M3PRO_LIMITS.max_alpha,
                           "source": "src/navfm/control.py M3PRO_LIMITS"},
            "enforced_by_the_kinematic_drive": False,
            "evidence": ("KinematicDriver.step clamps velocity only; there is no acceleration term "
                         "in src/navfm/collection/kinematic_drive.py, and BaseLimits.clamp bounds "
                         "max_v / max_vy / max_w and nothing else"),
            "included_in_the_bound": False,
            "rule_applied": "configured != executed"},
        "translation_and_rotation_overlap": {
            "answer": True,
            "evidence": ("integrate_se2 applies vx and wz in the same step, so heading change and "
                         "translation are simultaneous"),
            "consequence": "angular time is NOT added to translational time; the bound uses the max of the two"},
        "speed_law": {
            "nonholonomic": "vx = cruise_v * max(0.15, cos(heading_err))",
            "turn_in_place_regime": ("when |heading_err| > 75 deg, vx = 0.05 * cruise_v = "
                                     f"{0.05 * cfg.cruise_v:.4f} m/s and wz = +/- max_w"),
            "consequence_for_q1": ("the controller can never command more than cruise_v, so a bound "
                                   "computed at max_v is unreachable in practice and is reported as "
                                   "a mathematical floor only"),
            "source": "src/navfm/control.py PurePursuit.step"},
        "step_cadence": {
            "one_collector_step": "one control update, one physics step and one rendered observation",
            "evidence": ("the collection shim calls SimulationContext.step(render=True) once per "
                         "control update, and the context was created with physics_dt = "
                         "rendering_dt = 1/hz"),
            "physics_dt_s": sim.dt, "control_dt_s": sim.dt, "render_dt_s": sim.dt,
            "rates_differ": False},
    }

    L = float(sel["route_length_m"])
    dt = float(sim.dt)
    steps = int(cfg.max_steps)
    v_max = float(M3PRO_LIMITS.max_v)
    v_cruise = float(cfg.cruise_v)
    w_max = float(M3PRO_LIMITS.max_w)
    tol = float(cfg.goal_tol_m)

    total_turn_rad = sum(abs(math.radians(t)) for t in sel["planned_turn_magnitudes_deg"])

    # A. absolute translational lower bound, at the velocity ceiling
    t_abs = L / v_max
    # A'. at the speed the controller can actually command
    t_cruise = L / v_cruise
    # B. kinematic bound: rotation overlaps translation, so the bound is the max
    t_rot = total_turn_rad / w_max
    t_kin = max(t_cruise, t_rot)
    # goal-tolerance adjusted: the last `tol` metres need not be traversed
    t_tol = max(0.0, L - tol) / v_cruise
    # C. available budget
    t_budget = steps * dt

    def to_steps(t: float) -> int:
        return int(math.ceil(t / dt))

    budgets = {
        "A_absolute_translational_lower_bound": {
            "seconds": round(t_abs, 4), "steps": to_steps(t_abs),
            "assumes": "instantaneous acceleration, no turn penalty, travel at max_v",
            "reachable_in_practice": False,
            "why": "the controller never commands more than cruise_v; this is a mathematical floor"},
        "A2_bound_at_commanded_cruise_ceiling": {
            "seconds": round(t_cruise, 4), "steps": to_steps(t_cruise),
            "assumes": "perfect tracking at the maximum speed the controller can command"},
        "B_kinematic_lower_bound_with_frozen_limits": {
            "seconds": round(t_kin, 4), "steps": to_steps(t_kin),
            "total_planned_rotation_rad": round(total_turn_rad, 4),
            "rotation_time_at_max_w_s": round(t_rot, 4),
            "combination": "max(translation, rotation) because they overlap; NOT additive",
            "acceleration_included": False},
        "B_tol_goal_tolerance_adjusted": {
            "seconds": round(t_tol, 4), "steps": to_steps(t_tol),
            "note": f"the final {tol} m need not be traversed to enter the success region"},
        "C_available_budget": {
            "seconds": round(t_budget, 4), "steps": steps,
            "max_distance_at_cruise_m": round(t_budget * v_cruise, 4),
            "max_distance_at_max_v_m": round(t_budget * v_max, 4)},
    }

    required = to_steps(t_kin)
    margin_steps = steps - required
    margin_seconds = t_budget - t_kin

    sensitivity = {
        "required_average_translational_speed_m_s": round(L / t_budget, 5),
        "as_fraction_of_cruise": round((L / t_budget) / v_cruise, 4),
        "budget_utilisation_at_kinematic_bound_pct": round(100.0 * t_kin / t_budget, 2),
        "route_length_capacity_at_cruise_m": round(t_budget * v_cruise, 3),
        "extra_path_length_allowance_before_exhaustion_m": round(t_budget * v_cruise - L, 3),
        "descriptive_only": "no new max_steps value is proposed from these numbers",
    }

    if margin_steps <= 0:
        verdict = "Q1_INFEASIBLE_UNDER_FROZEN_BUDGET"
    elif margin_steps < 0.20 * required:
        verdict = "Q1_FEASIBLE_BUT_TIGHT"
    else:
        verdict = "Q1_FEASIBLE_WITH_MARGIN"

    ep = col.get("episode", {})
    realised_len = float(ep.get("path_length_m", 0.0))
    comparison = {
        "planned_path_length_m": round(L, 4),
        "realised_path_length_m": round(realised_len, 4),
        "excess_realised_distance_m": round(realised_len - L, 4),
        "excess_pct": round(100.0 * (realised_len - L) / L, 2),
        "ideal_completion_steps_kinematic_bound": required,
        "realised_episode_steps": ep.get("n_frames"),
        "final_goal_miss_m": 1.679,
        "no_causality_attributed": True,
    }

    rec: dict[str, Any] = {
        "check": "BO10_EXECUTION_COMPLETION_DIAGNOSTIC_V1_Q1",
        "artifact_semantics": "OFFLINE_FEASIBILITY_ANALYSIS_NOT_A_CONTROLLER_DIAGNOSIS",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "question": ("was the frozen planned route executable inside the frozen step budget under "
                     "the declared nominal kinematic limits, BEFORE accounting for controller "
                     "tracking inefficiency?"),
        "no_simulator_rerun": True, "no_collection": True, "no_controller_change": True,
        "inputs": inputs, "semantics": semantics, "budgets": budgets,
        "margin": {"steps": margin_steps, "seconds": round(margin_seconds, 4),
                   "required_steps": required, "available_steps": steps,
                   "margin_as_fraction_of_required": round(margin_steps / required, 4)},
        "sensitivity_descriptive_only": sensitivity,
        "realised_comparison_descriptive_only": comparison,
        "Q1_CLASSIFICATION": verdict,
        "q2_authorised": verdict in ("Q1_FEASIBLE_WITH_MARGIN", "Q1_FEASIBLE_BUT_TIGHT"),
        "q1_has_no_authority_to_claim": [
            "pure pursuit caused failure", "overshoot caused failure",
            "turn amplification caused failure", "terminal logic caused failure"],
        "milestone_unaffected": {
            "BO-03_REAL_DATA_COMPATIBILITY": "COMPLETE",
            "BO-10_HOSPITAL_COLLECTION": "COMPLETE_FOR_COMPATIBILITY_PURPOSE",
            "note": "Q1 explains a recorded failure; it does not revise a compatibility claim"},
    }
    digest = emit_evidence(args.out, rec, required_keys=(
        "check", "artifact_semantics", "Q1_CLASSIFICATION"))
    print(f"wrote {args.out} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
