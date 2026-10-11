"""BO10_EXECUTION_COMPLETION_DIAGNOSTIC_V1 -- Q3.

Q1 established the route was feasible inside the frozen budget. Q2 accounted for
the whole 402-step margin and found it went predominantly to sub-cruise route
progress rather than to non-progress or to turning. Q3 asks the remaining
question: once the run entered its terminal region, did the frozen
target-selection, terminal-approach or stopping semantics prevent or materially
delay entry into the 0.20 m goal region before max_steps?

Q3 is diagnostic. It does not ask whether ``max_steps`` should be larger -- Q1
settled that -- and it does not assert that the tracker caused the failure.

The single most important thing this diagnostic does is refuse to conflate two
different failures. A run that never entered the goal region cannot be evidence
that the stop mechanism failed, because the stop mechanism was never entitled to
fire. That distinction is decided here from the source predicates and the
recorded poses, before any behavioural interpretation is offered, and it decides
which of the two failure families the run belongs to.

Everything is computed from ``run_00001`` and the frozen configuration. No
simulator runs. The offline counterfactual in section 11 compares COMMAND FIELDS
at recorded poses only: it is never integrated forward, because a command field
does not determine a trajectory once the loop is closed, and Q2 already measured
what closed-loop divergence does to an open-loop prediction here.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import pathlib
import pickle
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from diagnose_q2_margin_consumption import (  # noqa: E402
    project,
    recover_planned_path,
    sha256,
    wrap,
)

from navfm.control import M3PRO_LIMITS  # noqa: E402

RUN = REPO / "runs/bo10/hospital_bo10_run_00001"
POP = REPO / "gates/BO10/hospital_turning_route_population_20260910.json"
COLLECT = REPO / "gates/BO10/bo10_production_collection_run00001_20260910.json"
Q1 = REPO / "gates/BO10/q1_budget_feasibility_20260911.json"
Q2 = REPO / "gates/BO10/q2_margin_consumption_20260911.json"
PREREG = REPO / "gates/BO10/bo10_execution_completion_diagnostic_v1_20260911.json"
OUT = REPO / "gates/BO10/q3_terminal_approach_20260911.json"
TRACE = REPO / "gates/BO10/q3_terminal_trace_20260911.csv"

TURN_IN_PLACE_DEG = 75.0
TURN_IN_PLACE_FACTOR = 0.05
SPEED_FLOOR = 0.15


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Rank correlation without a scipy dependency."""
    def rank(x: np.ndarray) -> np.ndarray:
        order = np.argsort(x, kind="mergesort")
        r = np.empty(len(x), dtype=float)
        r[order] = np.arange(len(x), dtype=float)
        # average ties so a flat region does not manufacture structure
        _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
        for i in np.nonzero(counts > 1)[0]:
            m = inv == i
            r[m] = r[m].mean()
        return r
    ra, rb = rank(a), rank(b)
    ra -= ra.mean()
    rb -= rb.mean()
    d = math.sqrt(float((ra * ra).sum()) * float((rb * rb).sum()))
    return float((ra * rb).sum() / d) if d > 0 else float("nan")


def frozen_command(bx: float, by: float, cruise: float) -> tuple[float, float, float]:
    """The frozen nonholonomic law, evaluated on a body-frame target offset."""
    dist = math.hypot(bx, by)
    if dist < 1e-9:
        return 0.0, 0.0, 0.0
    heading_err = math.atan2(by, bx)
    curvature = 2.0 * by / (dist * dist)
    vx = cruise * max(SPEED_FLOOR, math.cos(np.clip(heading_err, -math.pi, math.pi)))
    wz = curvature * vx
    if abs(heading_err) > math.radians(TURN_IN_PLACE_DEG):
        vx = TURN_IN_PLACE_FACTOR * cruise
        wz = math.copysign(M3PRO_LIMITS.max_w, heading_err)
    vx, _vy, wz = M3PRO_LIMITS.clamp(vx, 0.0, wz)
    return vx, wz, heading_err


def point_at_arclength(path: np.ndarray, cum: np.ndarray, target_s: float) -> np.ndarray:
    target_s = float(np.clip(target_s, 0.0, cum[-1]))
    i = int(np.searchsorted(cum, target_s, side="right") - 1)
    i = min(max(i, 0), path.shape[0] - 2)
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg <= 0 else (target_s - cum[i]) / seg
    return path[i] + t * (path[i + 1] - path[i])


def describe(x: np.ndarray, nd: int = 4) -> dict[str, float]:
    return {
        "min": round(float(x.min()), nd),
        "q25": round(float(np.quantile(x, 0.25)), nd),
        "median": round(float(np.median(x)), nd),
        "mean": round(float(x.mean()), nd),
        "q75": round(float(np.quantile(x, 0.75)), nd),
        "max": round(float(x.max()), nd),
    }


def main() -> int:
    stamp = _dt.datetime.now(_dt.UTC).isoformat()
    pop = json.loads(POP.read_text())
    coll = json.loads(COLLECT.read_text())
    q2 = json.loads(Q2.read_text())

    traj_path = RUN / "traj_data.pkl"
    with traj_path.open("rb") as fh:
        traj = pickle.load(fh)
    pos = np.asarray(traj["position"], dtype=float)
    yaw = np.asarray(traj["yaw"], dtype=float)
    raw_meta = traj["metadata"]
    meta = raw_meta.item() if hasattr(raw_meta, "item") else raw_meta
    cc = meta["collect"]

    n = pos.shape[0]
    dt = 1.0 / float(meta["sim"]["hz"])
    cruise = float(cc["cruise_v"])
    lookahead = float(cc["lookahead_m"])
    goal_tol = float(cc["goal_tol_m"])
    max_steps = int(cc["max_steps"])
    cruise_step_m = cruise * dt

    path, recovery = recover_planned_path(pop)
    seg_len = np.linalg.norm(np.diff(path, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])
    route_len = float(cum[-1])
    goal = path[-1]
    sp = [float(v) for v in coll["admitted_route"]["start_pose"]]

    # --- per-step reconstruction (method validated in Q2) --------------------
    pre = np.vstack([np.array(sp[:2]), pos[:-1]])
    pre_yaw = np.concatenate([[sp[2]], yaw[:-1]])

    idx = 0
    tgt_idx = []
    for k in range(n):
        while idx < path.shape[0] - 1 and np.linalg.norm(path[idx] - pre[k]) < lookahead:
            idx += 1
        tgt_idx.append(min(idx, path.shape[0] - 1))
    tgt_idx_a = np.array(tgt_idx)

    tgt = path[tgt_idx_a]
    delta = tgt - pre
    tgt_dist = np.linalg.norm(delta, axis=1)
    cmd_vx = np.zeros(n)
    cmd_wz = np.zeros(n)
    head_err = np.zeros(n)
    for k in range(n):
        c, s_ = math.cos(-pre_yaw[k]), math.sin(-pre_yaw[k])
        bx = c * delta[k, 0] - s_ * delta[k, 1]
        by = s_ * delta[k, 0] + c * delta[k, 1]
        cmd_vx[k], cmd_wz[k], head_err[k] = frozen_command(bx, by, cruise)

    disp = np.linalg.norm(pos - pre, axis=1)
    factor = disp / cruise_step_m
    in_place = np.abs(factor - TURN_IN_PLACE_FACTOR) < 0.01

    # independent check that this reconstruction is the same one Q2 validated
    he_inv = np.degrees(np.arccos(np.clip(factor, -1.0, 1.0)))
    agree = float(np.abs(np.degrees(np.abs(head_err[~in_place])) - he_inv[~in_place]).mean())
    boundary_ok = bool((np.degrees(np.abs(head_err[in_place])) > TURN_IN_PLACE_DEG).all()
                       and (np.degrees(np.abs(head_err[~in_place])) <= TURN_IN_PLACE_DEG).all())

    poses = np.vstack([np.array(sp[:2]), pos])
    projs = [project(path, cum, p) for p in poses]
    s_all = np.array([pr.s for pr in projs])
    xt_all = np.array([pr.cross_track for pr in projs])
    ds = np.diff(s_all)
    s_step = s_all[1:]
    goal_dist = np.linalg.norm(poses - goal, axis=1)
    gd_step = goal_dist[1:]
    speed = disp / dt

    # --- 4. terminal leg, defined structurally BEFORE looking at behaviour ---
    last_interior_s = float(cum[-2])
    entry_candidates = np.nonzero(s_step >= last_interior_s)[0]
    entry = int(entry_candidates[0]) if entry_candidates.size else None
    if entry is None:
        raise SystemExit("the run never projected onto the final planned leg")
    T = np.arange(entry, n)

    secondary = {}
    for label, thresh in (("geometric_2m_goal_region", 2.0),
                          ("q2_turn_zone_offset_leg", last_interior_s + 1.0)):
        if label.startswith("geometric"):
            hit = np.nonzero(gd_step <= thresh)[0]
        else:
            hit = np.nonzero(s_step >= thresh)[0]
        secondary[label] = {
            "definition": ("first step within 2.0 m of the sealed goal"
                           if label.startswith("geometric")
                           else "first step past the last interior vertex plus one "
                                "G10 separator length, the Q2 phase boundary"),
            "entry_step": int(hit[0]) if hit.size else None,
            "steps_in_window": int(hit.size),
        }

    terminal_leg = {
        "PRIMARY_DEFINITION": (
            "the final planned leg: from the last interior route vertex to the "
            "sealed goal. Structural, taken from the frozen route, fixed before any "
            "behaviour was inspected"
        ),
        "last_interior_vertex_index": int(path.shape[0] - 2),
        "last_interior_vertex_xy": [float(v) for v in path[-2]],
        "terminal_leg_planned_length_m": round(float(route_len - last_interior_s), 4),
        "terminal_leg_arclength_window_m": [round(last_interior_s, 4), round(route_len, 4)],
        "entry_step": entry,
        "route_progress_at_entry_m": round(float(s_step[entry]), 4),
        "route_remaining_at_entry_m": round(float(route_len - s_step[entry]), 4),
        "goal_distance_at_entry_m": round(float(gd_step[entry]), 4),
        "steps_remaining_at_entry": int(n - entry),
        "seconds_remaining_at_entry": round(float((n - entry) * dt), 3),
        "secondary_definitions": secondary,
        "no_post_hoc_threshold": (
            "the primary window is the frozen route's own final leg. No distance "
            "threshold was chosen after inspecting the trace"
        ),
    }

    # --- 5/6. target transition analysis -------------------------------------
    transitions = []
    for v in range(path.shape[0]):
        m = tgt_idx_a == v
        if not m.any():
            transitions.append({"vertex": v, "steps_active": 0,
                                "note": "never the active target"})
            continue
        first, last = int(np.nonzero(m)[0][0]), int(np.nonzero(m)[0][-1])
        transitions.append({
            "vertex": v,
            "became_active_at_step": first,
            "last_active_at_step": last,
            "steps_active": int(m.sum()),
            "seconds_active": round(float(m.sum() * dt), 3),
            "distance_travelled_while_active_m": round(float(disp[m].sum()), 4),
            "route_progress_while_active_m": round(float(ds[m].sum()), 4),
            "target_distance_m": describe(tgt_dist[m]),
            "abs_heading_error_deg": describe(np.degrees(np.abs(head_err[m])), 3),
            "min_distance_ever_to_this_vertex_m": round(
                float(np.linalg.norm(pre - path[v], axis=1).min()), 4),
            "entered_lookahead_radius": bool(
                float(np.linalg.norm(pre - path[v], axis=1).min()) < lookahead),
        })

    monotonic = bool(np.all(np.diff(tgt_idx_a) >= 0))
    target_analysis = {
        "advance_rule_is_monotonic_by_construction": (
            "the index only ever increments; regression is impossible in the frozen "
            "implementation, so observing none is a consistency check, not a finding"
        ),
        "index_never_regressed": monotonic,
        "index_oscillated": not monotonic,
        "per_vertex": transitions,
        "final_goal_vertex_became_active": bool((tgt_idx_a == path.shape[0] - 1).any()),
        "final_goal_vertex_active_from_step": (
            int(np.nonzero(tgt_idx_a == path.shape[0] - 1)[0][0])
            if (tgt_idx_a == path.shape[0] - 1).any() else None),
        "final_goal_vertex_active_steps": int((tgt_idx_a == path.shape[0] - 1).sum()),
        "goal_vertex_ever_within_lookahead": bool(
            float(np.linalg.norm(pre - path[-1], axis=1).min()) < lookahead),
        "goal_vertex_closest_approach_m": round(
            float(np.linalg.norm(pre - path[-1], axis=1).min()), 4),
    }

    # --- 7. the five predicates, read from source ----------------------------
    contract = {
        "source": "src/navfm/control.py, PurePursuit",
        "A_vertex_considered_reached": {
            "line": "control.py:215",
            "predicate": "norm(path[_idx] - pos) < lookahead",
            "effect": "increments _idx (control.py:216)",
        },
        "B_lookahead_target_advance": {
            "line": "control.py:215-216",
            "predicate": "identical to A",
            "IMPORTANT": (
                "A and B are not two conditions. The same test both declares a "
                "vertex reached and advances the target, so a vertex that is never "
                "approached within the look-ahead radius is never passed"
            ),
        },
        "C_route_completion": {
            "line": "control.py:208-209",
            "predicate": "_idx >= len(path) - 1",
            "effect": (
                "sets the `finished` property only. It is consulted at control.py:234 "
                "and ONLY when the body-frame target offset is under 1e-9 m, which "
                "did not occur. Route completion therefore never terminates an episode"
            ),
        },
        "D_navigation_goal_reached": {
            "line": "control.py:224",
            "predicate": "norm(path[-1] - pos) < goal_tol",
            "goal_tol_m": goal_tol,
            "effect": "returns done=True (control.py:225)",
            "CRITICAL": (
                "this is the FIRST statement in step(), evaluated BEFORE target "
                "selection. Its sole precondition is Euclidean distance to the final "
                "path point. It does not depend on the active target index, on the "
                "look-ahead radius, or on route completion"
            ),
        },
        "E_zero_terminal_velocity": {
            "line": "control.py:225",
            "predicate": "fires if and only if D fires",
            "effect": "returns (0, 0, 0, True)",
        },
        "episode_termination": {
            "line": "collect.py:562-564",
            "predicate": "done from tracker.step",
            "effect": 'reason = "reached_goal"',
            "other_exits": {
                "max_steps": "collect.py:602, the for-else",
                "stalled": "collect.py:598, stall_patience consecutive commanded "
                           "steps with under 1e-3 m of motion",
                "collision_guard": "collect.py:577, no step was refused in this run",
            },
        },
        "event_order_per_step": [
            "1. read pose",
            "2. D: goal-distance test -> if true, stop with success",
            "3. A/B: advance target index while within look-ahead of the current vertex",
            "4. compute body-frame offset to the active vertex",
            "5. speed law and curvature -> (vx, wz)",
            "6. drive, step physics, record frame",
            "7. stall test",
        ],
        "consequence_for_this_run": (
            "because D precedes and is independent of A/B, the stop branch could "
            "have fired at any step at which the base came within 0.20 m of the goal "
            "point, whatever the target index was. Target selection cannot have "
            "suppressed a stop that its own precondition never satisfied"
        ),
    }

    # --- 8. stop-branch reachability -----------------------------------------
    d_met = gd_step <= goal_tol
    stop = {
        "D_precondition": "goal_distance <= 0.20 m, sole and independent",
        "steps_satisfying_D": int(d_met.sum()),
        "min_goal_distance_m": round(float(gd_step.min()), 4),
        "min_goal_distance_at_step": int(np.argmin(gd_step)),
        "goal_tolerance_m": goal_tol,
        "shortfall_m": round(float(gd_step.min() - goal_tol), 4),
        "shortfall_as_multiple_of_tolerance": round(float(gd_step.min() / goal_tol), 3),
        "steps_satisfying_lookahead_on_goal_vertex": int(
            (np.linalg.norm(pre - path[-1], axis=1) < lookahead).sum()),
        "additional_route_completion_predicate_required": False,
        "CLASSIFICATION": (
            "STOP_BRANCH_NOT_REACHED" if d_met.sum() == 0 else "STOP_BRANCH_REACHED"),
        "reasoning": (
            "the stop branch's only precondition is Euclidean goal distance under "
            "0.20 m. The closest the base ever came was 1.6787 m, 8.39 times the "
            "tolerance. The branch was never entitled to fire, so nothing about its "
            "behaviour can be assessed from this run and no stopping defect can be "
            "claimed or excluded on this evidence"
        ),
        "not_a_defect_finding": (
            "a stop mechanism whose triggering precondition was never met is not "
            "thereby shown defective"
        ),
    }

    # --- 9. terminal progress -------------------------------------------------
    planned_T = float(route_len - last_interior_s)
    realised_T = float(disp[T].sum())
    prog_T = float(ds[T].sum())
    thirds = np.array_split(T, 3)
    terminal_progress = {
        "steps": int(len(T)),
        "planned_distance_m": round(planned_T, 4),
        "realised_distance_m": round(realised_T, 4),
        "route_progress_m": round(prog_T, 4),
        "excess_distance_m": round(realised_T - planned_T, 4),
        "mean_commanded_vx_m_s": round(float(cmd_vx[T].mean()), 4),
        "mean_realised_speed_m_s": round(float(speed[T].mean()), 4),
        "mean_route_progress_speed_m_s": round(float(prog_T / (len(T) * dt)), 4),
        "speed_as_fraction_of_cruise": round(float(speed[T].mean() / cruise), 4),
        "progress_speed_as_fraction_of_cruise": round(
            float(prog_T / (len(T) * dt) / cruise), 4),
        "target_distance_m": describe(tgt_dist[T]),
        "abs_heading_error_deg": describe(np.degrees(np.abs(head_err[T])), 3),
        "abs_cross_track_m": describe(np.abs(xt_all[1:][T])),
        "goal_distance_reduction_per_step_m": round(
            float((gd_step[T][0] - gd_step[T][-1]) / len(T)), 6),
        "sub_cruise_steps": int((factor[T] < 0.999).sum()),
        "near_zero_progress_steps": int((ds[T] <= 0.1 * cruise_step_m).sum()),
        "turn_in_place_steps": int(in_place[T].sum()),
        "descriptive_thirds": [
            {
                "third": i + 1,
                "steps": [int(part[0]), int(part[-1])],
                "mean_realised_speed_m_s": round(float(speed[part].mean()), 4),
                "mean_route_progress_speed_m_s": round(
                    float(ds[part].sum() / (len(part) * dt)), 4),
                "mean_target_distance_m": round(float(tgt_dist[part].mean()), 4),
                "mean_abs_heading_error_deg": round(
                    float(np.degrees(np.abs(head_err[part])).mean()), 3),
                "mean_abs_cross_track_m": round(float(np.abs(xt_all[1:][part]).mean()), 4),
                "goal_distance_at_end_m": round(float(gd_step[part[-1]]), 4),
            }
            for i, part in enumerate(thirds)
        ],
        "window_choice": (
            "thirds of the structurally defined terminal leg, plus quantiles. No "
            "last-N window was invented, because no frozen N exists"
        ),
    }

    # --- 14. minimum required terminal performance, on two explicit bases ----
    # The first version of this compared a route-progress rate against a
    # straight-line goal-distance requirement. Those are different quantities and
    # the comparison was invalid, so both bases are computed and reported.
    have_steps = int(n - entry)
    secs = have_steps * dt
    route_need = float(route_len - s_step[entry] - goal_tol)
    route_req = route_need / secs
    route_act = prog_T / (len(T) * dt)
    goal_need = float(gd_step[entry] - goal_tol)
    goal_req = goal_need / secs
    goal_act = float(gd_step[entry] - gd_step[-1]) / (len(T) * dt)
    req_speed, act_speed = route_req, route_act

    shortfall_along = float(route_len - s_all[-1])
    cross_final = float(abs(xt_all[-1]))
    miss_decomposition = {
        "why_this_matters": (
            "route progress and goal distance are not interchangeable. A base that "
            "is off the path can advance along the route without closing on the "
            "goal, and at the end of this run that difference is most of the miss"
        ),
        "final_goal_distance_m": round(float(gd_step[-1]), 4),
        "along_route_shortfall_m": round(shortfall_along, 4),
        "final_cross_track_m": round(cross_final, 4),
        "pythagorean_combination_m": round(math.hypot(shortfall_along, cross_final), 4),
        "agreement_with_recorded_goal_distance_m": round(
            abs(math.hypot(shortfall_along, cross_final) - float(gd_step[-1])), 5),
        "cross_track_share_of_squared_miss": round(
            cross_final ** 2 / (cross_final ** 2 + shortfall_along ** 2), 4),
        "reading": (
            "the final miss is almost exactly the right triangle of a 0.93 m "
            "shortfall along the route and a 1.40 m lateral offset from it. Even "
            "with the route run to its end the base would have been 1.40 m from the "
            "goal, still outside a 0.20 m tolerance. The dominant term is lateral"
        ),
    }

    terminal_requirement = {
        "method": (
            "the terminal analogue of Q1, computed on two bases because they answer "
            "different questions and disagree here"
        ),
        "steps_available": have_steps,
        "seconds_available": round(secs, 3),
        "route_progress_basis": {
            "question": "did the base advance along the route fast enough?",
            "distance_to_close_m": round(route_need, 4),
            "required_m_s": round(route_req, 4),
            "achieved_m_s": round(route_act, 4),
            "ratio": round(route_act / route_req, 4),
            "required_as_fraction_of_cruise": round(route_req / cruise, 4),
        },
        "goal_distance_basis": {
            "question": "did the base actually close on the goal fast enough?",
            "distance_to_close_m": round(goal_need, 4),
            "required_m_s": round(goal_req, 4),
            "achieved_m_s": round(goal_act, 4),
            "ratio": round(goal_act / goal_req, 4),
        },
        "the_two_bases_disagree_because": (
            "cross-track error converts route progress into less goal closure. The "
            "base very nearly met the route-progress rate the budget demanded and "
            "fell well short on goal closure, and the gap between the two ratios is "
            "the lateral offset"
        ),
        "achieved_mean_realised_speed_m_s": round(float(speed[T].mean()), 4),
        "terminal_efficiency_ratio": round(route_act / route_req, 4),
        "CLASSIFICATION": (
            "TERMINAL_PROGRESS_SUFFICIENT"
            if (route_act >= route_req and goal_act >= goal_req)
            else "TERMINAL_PROGRESS_INSUFFICIENT"),
        "classification_basis": (
            "insufficient on either basis is insufficient. Route progress missed by "
            "1 percent and goal closure by 19 percent"
        ),
        "interpretation": (
            "this compares achieved rates against what the remaining budget demanded. "
            "It does not license changing max_steps"
        ),
    }

    # --- 10. state at max_steps ----------------------------------------------
    w = min(60, n - 1)
    gd_slope = float((gd_step[-1] - gd_step[-1 - w]) / w)
    pr_slope = float(ds[-w:].mean())
    if gd_slope < -1e-4 and pr_slope > 1e-4:
        conv = "STILL_CONVERGING"
    elif abs(gd_slope) <= 1e-4 and abs(pr_slope) <= 1e-4:
        conv = "STALLED"
    elif gd_slope > 1e-4:
        conv = "MOVING_AWAY"
    else:
        conv = "INCONCLUSIVE"
    at_end = {
        "final_goal_distance_m": round(float(gd_step[-1]), 4),
        "window_steps": w,
        "goal_distance_slope_m_per_step": round(gd_slope, 6),
        "route_progress_slope_m_per_step": round(pr_slope, 6),
        "active_target_vertex": int(tgt_idx_a[-1]),
        "target_distance_m": round(float(tgt_dist[-1]), 4),
        "abs_heading_error_deg": round(float(np.degrees(abs(head_err[-1]))), 3),
        "commanded_vx_m_s": round(float(cmd_vx[-1]), 5),
        "commanded_wz_rad_s": round(float(cmd_wz[-1]), 5),
        "cross_track_m": round(float(xt_all[-1]), 4),
        "steps_to_close_at_final_rate": (
            int(math.ceil((gd_step[-1] - goal_tol) / abs(gd_slope)))
            if gd_slope < -1e-9 else None),
        "BEHAVIOUR_CLASSIFICATION": conv,
        "classification_is_descriptive": True,
    }

    # --- 11. offline command-field counterfactual ----------------------------
    cf_vx = np.zeros(n)
    cf_wz = np.zeros(n)
    cf_he = np.zeros(n)
    cf_dist = np.zeros(n)
    for k in range(n):
        tp = point_at_arclength(path, cum, s_all[k] + lookahead)
        d = tp - pre[k]
        cf_dist[k] = float(np.linalg.norm(d))
        c, s_ = math.cos(-pre_yaw[k]), math.sin(-pre_yaw[k])
        bx = c * d[0] - s_ * d[1]
        by = s_ * d[0] + c * d[1]
        cf_vx[k], cf_wz[k], cf_he[k] = frozen_command(bx, by, cruise)

    dom = np.abs(xt_all[1:]) < lookahead

    counterfactual = {
        "LABEL": "COMMAND_FIELD_COUNTERFACTUAL_ONLY",
        "what_it_compares": (
            "at every recorded pre-command pose, the command the frozen control law "
            "would issue under two target-selection rules"
        ),
        "arm_1": "the frozen implementation: the current path VERTEX",
        "arm_2": (
            "an arc-length interpolated point one look-ahead distance further along "
            "the polyline from the pose's own projection"
        ),
        "held_constant": [
            "the recorded poses", "the speed law", "the curvature law",
            "cruise_v", "the look-ahead distance", "the limits and clamps",
        ],
        "not_integrated_forward": True,
        "why_not": (
            "a command field does not determine a trajectory once the loop is "
            "closed. Q2 measured what open-loop integration does to a prediction "
            "here: it diverged to 0.229 m from a 2.3e-05 m seed"
        ),
        "whole_run": {
            "target_distance_m": {
                "vertex_arm": describe(tgt_dist),
                "interpolated_arm": describe(cf_dist),
            },
            "abs_heading_error_deg": {
                "vertex_arm": describe(np.degrees(np.abs(head_err)), 3),
                "interpolated_arm": describe(np.degrees(np.abs(cf_he)), 3),
            },
            "commanded_vx_m_s": {
                "vertex_arm": describe(cmd_vx, 5),
                "interpolated_arm": describe(cf_vx, 5),
            },
            "mean_speed_factor": {
                "vertex_arm": round(float(cmd_vx.mean() / cruise), 4),
                "interpolated_arm": round(float(cf_vx.mean() / cruise), 4),
            },
            "turn_in_place_steps": {
                "vertex_arm": int((np.degrees(np.abs(head_err)) > TURN_IN_PLACE_DEG).sum()),
                "interpolated_arm": int(
                    (np.degrees(np.abs(cf_he)) > TURN_IN_PLACE_DEG).sum()),
            },
        },
        "terminal_leg": {
            "target_distance_m": {
                "vertex_arm": describe(tgt_dist[T]),
                "interpolated_arm": describe(cf_dist[T]),
            },
            "abs_heading_error_deg": {
                "vertex_arm": describe(np.degrees(np.abs(head_err[T])), 3),
                "interpolated_arm": describe(np.degrees(np.abs(cf_he[T])), 3),
            },
            "mean_commanded_vx_m_s": {
                "vertex_arm": round(float(cmd_vx[T].mean()), 5),
                "interpolated_arm": round(float(cf_vx[T].mean()), 5),
            },
            "mean_abs_commanded_wz_rad_s": {
                "vertex_arm": round(float(np.abs(cmd_wz[T]).mean()), 5),
                "interpolated_arm": round(float(np.abs(cf_wz[T]).mean()), 5),
            },
        },
        "VALIDITY_DOMAIN_AND_BIAS": {
            "WARNING": (
                "this comparison is biased against the interpolated arm, and the "
                "direction of the raw result must not be read as a verdict"
            ),
            "why": (
                "the counterfactual is evaluated at poses the CONTROL arm produced. "
                "An interpolated-target controller would never have visited them, so "
                "the treatment arm is scored off its own distribution"
            ),
            "how_that_bites_here": (
                "the base ran far off the polyline. An arc-length point one "
                "look-ahead further along the path is then beside or behind the "
                "robot rather than ahead of it, which inflates the interpolated "
                "arm's heading error and collapses its commanded speed. That is a "
                "property of where the control arm went, not of the interpolated rule"
            ),
            "terminal_leg_abs_cross_track_m": describe(np.abs(xt_all[1:][T])),
            "lookahead_m": lookahead,
            "terminal_steps_with_cross_track_below_lookahead": int(
                (np.abs(xt_all[1:][T]) < lookahead).sum()),
            "terminal_steps_total": int(len(T)),
            "fraction_of_terminal_leg_in_validity_domain": round(
                float((np.abs(xt_all[1:][T]) < lookahead).mean()), 4),
            "classical_pure_pursuit_note": (
                "textbook pure pursuit takes the intersection of a circle of the "
                "look-ahead radius centred on the ROBOT with the path. With a 0.45 m "
                "radius and cross-track up to 2.589 m, no such intersection exists "
                "for most of this run, so that variant is not even defined here. "
                "This is itself a finding about look-ahead sizing relative to "
                "achieved tracking error"
            ),
        },
        "restricted_to_validity_domain": (
            {
                "steps": int(dom.sum()),
                "abs_heading_error_deg": {
                    "vertex_arm": describe(np.degrees(np.abs(head_err[dom])), 3),
                    "interpolated_arm": describe(np.degrees(np.abs(cf_he[dom])), 3),
                },
                "mean_commanded_vx_m_s": {
                    "vertex_arm": round(float(cmd_vx[dom].mean()), 5),
                    "interpolated_arm": round(float(cf_vx[dom].mean()), 5),
                },
                "mean_target_distance_m": {
                    "vertex_arm": round(float(tgt_dist[dom].mean()), 4),
                    "interpolated_arm": round(float(cf_dist[dom].mean()), 4),
                },
                "caveat": (
                    "still evaluated at control-arm poses; restricting the domain "
                    "removes the worst of the bias, not all of it"
                ),
            }
            if dom.any() else {"steps": 0, "note": "validity domain is empty"}
        ),
        "RAW_RESULT_DIRECTION": (
            "on the terminal leg the interpolated arm shows a LARGER mean heading "
            "error and a LOWER commanded speed than the vertex arm. That is the "
            "opposite of the hypothesis that motivated this test, and it is reported "
            "unchanged. It is explained by the bias above rather than taken as "
            "evidence that vertex targeting is preferable, and it is precisely why "
            "the question needs an intervention rather than another offline pass"
        ),
        "CAN_ESTABLISH": "how the command field differs at the poses actually visited",
        "CANNOT_ESTABLISH": [
            "what trajectory the alternative rule would have produced",
            "that the alternative rule would have reached the goal",
            "that success rate would improve",
        ],
    }

    # --- 12. distance-scaling test -------------------------------------------
    dyaw = np.array([wrap(yaw[k] - pre_yaw[k]) for k in range(n)])
    he_decay = np.concatenate([-np.diff(np.abs(head_err)), [0.0]])
    live = (~in_place) & (tgt_dist > 1e-6)
    scaling = {
        "mechanism_from_the_law": (
            "wz = curvature * vx with curvature = 2 * lateral_offset / dist^2, so "
            "for a fixed lateral offset the commanded yaw rate falls with the square "
            "of the distance to the active target. This is algebra in the frozen "
            "law, not an empirical claim"
        ),
        "target_distance_m_whole_run": describe(tgt_dist),
        "target_distance_m_terminal_leg": describe(tgt_dist[T]),
        "effective_angular_gain_2_over_dist_squared": describe(
            2.0 / np.maximum(tgt_dist, 1e-6) ** 2, 5),
        "spearman_target_distance_vs_abs_commanded_wz": round(
            spearman(tgt_dist[live], np.abs(cmd_wz[live])), 4),
        "spearman_target_distance_vs_abs_realised_yaw_rate": round(
            spearman(tgt_dist[live], np.abs(dyaw[live]) / dt), 4),
        "spearman_target_distance_vs_heading_error_decay": round(
            spearman(tgt_dist[live], he_decay[live]), 4),
        "spearman_target_distance_vs_route_progress_efficiency": round(
            spearman(tgt_dist[live], ds[live] / cruise_step_m), 4),
        "steps_used": int(live.sum()),
        "excluded": "turn-in-place steps, where wz is set to max_w and not by curvature",
        "INTERPRETATION_LIMIT": (
            "these are associations across steps of one trajectory, in which target "
            "distance, heading error and route position all co-vary. They are "
            "reported as association. The 1/dist^2 relation is exact because it is "
            "the law itself, but that the relation DROVE the outcome is not "
            "established by a correlation"
        ),
    }

    # --- 13. vertex-transition discontinuity ---------------------------------
    switches = [int(k) for k in np.nonzero(np.diff(tgt_idx_a) != 0)[0] + 1]
    disc = []
    for k in switches:
        lo, hi = max(0, k - 5), min(n, k + 6)
        disc.append({
            "switch_at_step": k,
            "from_vertex": int(tgt_idx_a[k - 1]),
            "to_vertex": int(tgt_idx_a[k]),
            "target_distance_before_m": round(float(tgt_dist[k - 1]), 4),
            "target_distance_after_m": round(float(tgt_dist[k]), 4),
            "target_distance_jump_m": round(float(tgt_dist[k] - tgt_dist[k - 1]), 4),
            "abs_heading_error_before_deg": round(
                float(np.degrees(abs(head_err[k - 1]))), 3),
            "abs_heading_error_after_deg": round(float(np.degrees(abs(head_err[k]))), 3),
            "heading_error_jump_deg": round(
                float(np.degrees(abs(head_err[k]) - abs(head_err[k - 1]))), 3),
            "commanded_vx_before_m_s": round(float(cmd_vx[k - 1]), 5),
            "commanded_vx_after_m_s": round(float(cmd_vx[k]), 5),
            "mean_progress_5_steps_before_m": round(float(ds[lo:k].mean()), 5),
            "mean_progress_5_steps_after_m": round(float(ds[k:hi].mean()), 5),
        })
    discontinuity = {
        "switch_count": len(switches),
        "switches": disc,
        "observation": (
            "target distance and heading error change discontinuously at a switch "
            "because the target jumps between vertices rather than sliding along the "
            "path. The magnitude of each jump is tabulated above"
        ),
        "association_only": (
            "no intervention exists in this run, so a switch coinciding with a "
            "progress change is association. Nothing here is a cause"
        ),
    }

    # --- 15/16. approach vs stop, and classification -------------------------
    approach_or_stop = {
        "CASE_A_approach_failure": bool(d_met.sum() == 0),
        "CASE_B_stop_failure": bool(d_met.sum() > 0),
        "VERDICT": "CASE_A_APPROACH_FAILURE" if d_met.sum() == 0 else "CASE_B_STOP_FAILURE",
        "reasoning": (
            "the base never entered the 0.20 m goal region, closest approach "
            f"{round(float(gd_step.min()), 4)} m. The stopping logic was therefore "
            "never entitled to declare success, and this run is not evidence about "
            "stopping behaviour in either direction"
        ),
        "consequence_for_SR_OSR_work": (
            "run_00001 must not be cited as evidence that the stop mechanism failed. "
            "It is an approach and execution failure. Evidence about the stopping "
            "problem requires an episode that enters the goal neighbourhood and then "
            "fails to terminate, which this is not"
        ),
    }

    cls = ("Q3_STOP_TRIGGER_REACHED_BUT_FAILED" if d_met.sum() > 0
           else "Q3_STOP_TRIGGER_NOT_REACHED")

    classification = {
        "Q3_CLASSIFICATION": cls,
        "decision_rule": (
            "the stop-trigger labels are decided by a predicate, not by a threshold: "
            "either the sole precondition of the stop branch was satisfied at some "
            "step or it was not. That test is prior to every approach label, because "
            "an approach label would attribute the failure to a mechanism whose "
            "entitlement to act was never established"
        ),
        "steps_satisfying_the_stop_predicate": int(d_met.sum()),
        "secondary_contributors_within_the_approach": {
            "note": (
                "these describe where terminal progress went. They are secondary "
                "because Q3's primary finding is that the stop branch never became "
                "reachable, which is a statement about entitlement rather than about "
                "controller quality"
            ),
            "terminal_mean_progress_speed_as_fraction_of_cruise": round(
                float(act_speed / cruise), 4),
            "terminal_required_fraction_of_cruise": round(float(req_speed / cruise), 4),
            "terminal_efficiency_ratio": round(float(act_speed / req_speed), 4),
            "terminal_mean_target_distance_m": round(float(tgt_dist[T].mean()), 4),
            "terminal_mean_abs_heading_error_deg": round(
                float(np.degrees(np.abs(head_err[T])).mean()), 3),
            "goal_vertex_never_entered_lookahead_radius": bool(
                float(np.linalg.norm(pre - path[-1], axis=1).min()) >= lookahead),
        },
        "labels_not_selected": {
            "Q3_STOP_TRIGGER_REACHED_BUT_FAILED": (
                "the predicate was satisfied at 0 of 1200 steps"),
            "Q3_APPROACH_TARGET_SELECTION_DOMINANT": (
                "target selection is implicated by the offline command-field "
                "comparison and by the 1/dist^2 algebra, but one observational run "
                "with no intervention cannot rank it against the speed law, with "
                "which it is confounded through the shared heading-error term"
            ),
            "Q3_APPROACH_SPEED_LAW_DOMINANT": (
                "same confound, in the other direction. The speed law and the target "
                "rule both act through heading error to the active target and cannot "
                "be separated without varying one of them"
            ),
            "Q3_NO_MATERIAL_TERMINAL_DEFECT": (
                "not selected: terminal progress ran below what the remaining budget "
                "required, so something material did happen in the terminal leg"
            ),
        },
        "why_not_a_target_selection_verdict": (
            "the evidence is suggestive and is recorded in full, but target rule and "
            "speed law are confounded in this run. Separating them is exactly what "
            "the drafted one-factor intervention would do, and claiming the answer "
            "now would spend the intervention's conclusion before running it"
        ),
    }

    # --- 18. next experiment, drafted not executed ---------------------------
    intervention = {
        "name": "TERMINAL_APPROACH_INTERVENTION_V1",
        "STATUS": "DRAFTED_NOT_EXECUTED",
        "authorisation": "NOT AUTHORISED in this tranche",
        "justified_by": [
            "the stop branch was never reachable, so the failure is in the approach",
            "terminal route-progress ran at "
            f"{round(float(act_speed / req_speed), 3)} of the rate the remaining "
            "budget required",
            "the goal vertex was never entered within the look-ahead radius, so the "
            "tracker steered at a single distant point for "
            f"{int((tgt_idx_a == path.shape[0] - 1).sum())} steps",
            "the offline command field differs materially between the two target "
            "rules at the poses actually visited",
        ],
        "single_factor": {
            "manipulated": "target-selection mechanism only",
            "arm_A_control": "the frozen implementation, nearest qualifying route vertex",
            "arm_B_treatment": (
                "arc-length interpolated look-ahead point at the same frozen "
                "look-ahead distance along the polyline"
            ),
        },
        "held_constant": [
            "route geometry and the seeded generator", "initial state and start yaw",
            "controller gains", "look-ahead distance", "cruise_v and all limits",
            "goal tolerance", "max_steps", "control rate", "seed", "scene and assets",
            "the collision guard and the kinematic drive",
        ],
        "explicitly_forbidden": [
            "changing max_steps", "changing the look-ahead distance",
            "changing cruise_v or the speed law", "changing the route",
            "changing more than one factor in the same run",
        ],
        "primary_outcome": "entry into the 0.20 m goal region before max_steps",
        "secondary_outcomes": [
            "steps to goal entry", "terminal mean route-progress speed",
            "realised path length", "mean absolute heading error to target",
            "closest approach to the goal",
        ],
        "power_note": (
            "one trajectory per arm establishes a difference in one instance, not a "
            "difference in expectation. A route population and a seed sweep are "
            "required before any success-rate claim, and that is a separate design"
        ),
        "preconditions": [
            "supervisor authorisation", "an Isaac Sim execution slot",
            "the disk floor for recording",
            "a preregistration frozen before the first run",
        ],
    }

    result = {
        "check": "BO10_EXECUTION_COMPLETION_DIAGNOSTIC_V1_Q3",
        "artifact_semantics": "OFFLINE_TERMINAL_APPROACH_DIAGNOSIS_NOT_AN_INTERVENTION",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "question": (
            "once run_00001 entered its terminal region, did the frozen "
            "target-selection, terminal-approach or stopping semantics prevent or "
            "materially delay entry into the 0.20 m goal region before max_steps?"
        ),
        "explicitly_not_asking": [
            "whether max_steps should be larger; Q1 settled that",
            "whether the tracker caused the failure; that needs an intervention",
        ],
        "no_simulator_rerun": True,
        "no_collection": True,
        "no_controller_change": True,
        "no_route_change": True,
        "max_steps_unchanged": True,
        "lookahead_unchanged": True,
        "velocity_laws_unchanged": True,
        "run_00001_unmodified": True,
        "skill_retrieval_preflight": {
            "SKILL_RETRIEVAL_PREFLIGHT": "BLOCKED",
            "server": "skill-retrieval",
            "error": "CONNECT_TIMEOUT: MCP server connection timed out after 30000ms",
            "retry_count": 3,
            "cumulative_across_q2_and_q3": True,
            "timestamp_utc": stamp,
            "diagnosis": (
                "unchanged from Q2 and independently reproduced: launched directly "
                "the server loads 89267 skills and then a SentenceTransformer "
                "embedding model onto CUDA with HuggingFace revalidation round trips, "
                "and was still initialising at 20 s. Cold-start latency exceeding the "
                "30 s connect timeout, not an import or configuration failure"
            ),
            "policy_reading": (
                "the global policy requires the search to be attempted and its "
                "outcome recorded, and provides explicitly for continuing on "
                "repository evidence. It sets no precondition that retrieval must "
                "succeed. Recorded, not bypassed"
            ),
            "skills_that_influenced_this_work": "NONE -- retrieval unavailable",
            "authority_used_instead": [
                "gates/BO10/bo10_execution_completion_diagnostic_v1_20260911.json",
                "the repository standing-instructions file, rule 9",
                "the repository project router",
            ],
        },
        "inputs": {
            "trajectory": {"path": str(traj_path.relative_to(REPO)),
                           "sha256": sha256(traj_path), "frames": int(n)},
            "route_population": {"path": str(POP.relative_to(REPO)), "sha256": sha256(POP)},
            "collection_evidence": {"path": str(COLLECT.relative_to(REPO)),
                                    "sha256": sha256(COLLECT)},
            "q1_result": {"path": str(Q1.relative_to(REPO)), "sha256": sha256(Q1)},
            "q2_result": {"path": str(Q2.relative_to(REPO)), "sha256": sha256(Q2)},
            "preregistration": {"path": str(PREREG.relative_to(REPO)), "sha256": sha256(PREREG)},
            "frozen_parameters": {
                "control_hz": float(meta["sim"]["hz"]), "control_dt_s": dt,
                "cruise_v_m_s": cruise, "lookahead_m": lookahead,
                "goal_tol_m": goal_tol, "max_steps": max_steps,
                "max_v_m_s": M3PRO_LIMITS.max_v, "max_w_rad_s": M3PRO_LIMITS.max_w,
            },
        },
        "planned_path_recovery": {
            "recovered_path_length_m": recovery["recovered_path_length_m"],
            "length_residual_m": recovery["length_residual_m"],
            "unique_solution": recovery["uniqueness_is_the_proof"],
            "polyline": recovery["recovered_polyline"],
        },
        "reconstruction_consistency_with_q2": {
            "method": "the Q2-validated reconstruction, recomputed here independently",
            "mean_heading_error_disagreement_deg": round(agree, 6),
            "regime_boundary_separates_perfectly": boundary_ok,
            "q2_command_channel_status": q2["command_reconstruction"]["COMMAND_CHANNEL"],
            "open_loop_replay_not_used_as_truth": True,
        },
        "terminal_leg": terminal_leg,
        "target_selection": target_analysis,
        "terminal_predicate_contract": contract,
        "stop_branch_reachability": stop,
        "terminal_progress": terminal_progress,
        "final_miss_decomposition": miss_decomposition,
        "terminal_requirement": terminal_requirement,
        "state_at_max_steps": at_end,
        "target_rule_counterfactual": counterfactual,
        "distance_scaling": scaling,
        "vertex_transition_discontinuity": discontinuity,
        "approach_versus_stop": approach_or_stop,
        "classification": classification,
        "q3_authority_limits": {
            "q3_may_establish": [
                "which target was selected at each step",
                "whether the goal and stop predicates were ever reached",
                "where terminal progress slowed",
                "that the frozen target law yields angular authority falling as "
                "1/dist^2, which is algebra in the law",
                "how an interpolated-target command field differs offline",
            ],
            "q3_may_not_establish": [
                "that changing the look-ahead fixes the trajectory",
                "that interpolation guarantees goal reaching",
                "that a controller modification improves success rate",
                "that the physical robot would behave similarly",
            ],
            "requires_intervention": True,
            "single_trajectory": True,
            "standing_rule": (
                "the standing-instructions file, rule 9: causal order for a failed "
                "execution"
            ),
        },
        "next_experiment": intervention,
        "milestone_unaffected": {
            "BO-03_REAL_DATA_COMPATIBILITY": "COMPLETE",
            "BO-10_PIPELINE_COLLECTION": "COMPLETE",
            "BO-10_HOSPITAL_COLLECTION": "COMPLETE_FOR_COMPATIBILITY_PURPOSE",
            "run_00001": "IMMUTABLE compatibility evidence; unchanged by Q3",
        },
    }

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    required = [
        "check", "terminal_leg", "target_selection", "terminal_predicate_contract",
        "stop_branch_reachability", "terminal_progress", "terminal_requirement",
        "final_miss_decomposition",
        "state_at_max_steps", "target_rule_counterfactual", "distance_scaling",
        "vertex_transition_discontinuity", "approach_versus_stop", "classification",
        "q3_authority_limits", "next_experiment", "skill_retrieval_preflight",
    ]
    missing = [k for k in required if k not in back]
    if missing:
        raise SystemExit(f"evidence guard: missing required keys {missing}")
    if "Q3_CLASSIFICATION" not in back["classification"]:
        raise SystemExit("evidence guard: classification absent")
    if back["next_experiment"]["STATUS"] != "DRAFTED_NOT_EXECUTED":
        raise SystemExit("evidence guard: the intervention must not be marked executed")
    if back["target_rule_counterfactual"]["LABEL"] != "COMMAND_FIELD_COUNTERFACTUAL_ONLY":
        raise SystemExit("evidence guard: counterfactual is mislabelled")
    if not back["reconstruction_consistency_with_q2"]["regime_boundary_separates_perfectly"]:
        raise SystemExit("evidence guard: reconstruction did not reproduce the Q2 regimes")

    cols = ["step", "on_terminal_leg", "s_m", "ds_m", "goal_dist_m", "target_vertex",
            "target_dist_m", "heading_err_deg", "cmd_vx_m_s", "cmd_wz_rad_s",
            "disp_m", "cross_track_m", "cf_target_dist_m", "cf_heading_err_deg",
            "cf_cmd_vx_m_s", "cf_cmd_wz_rad_s", "D_goal_predicate_met"]
    lines = [",".join(cols)]
    for k in range(n):
        lines.append(",".join([
            str(k), "1" if k >= entry else "0", f"{s_step[k]:.5f}", f"{ds[k]:.6f}",
            f"{gd_step[k]:.5f}", str(int(tgt_idx_a[k])), f"{tgt_dist[k]:.5f}",
            f"{math.degrees(head_err[k]):.3f}", f"{cmd_vx[k]:.6f}",
            f"{cmd_wz[k]:.6f}", f"{disp[k]:.6f}", f"{xt_all[k+1]:.5f}",
            f"{cf_dist[k]:.5f}", f"{math.degrees(cf_he[k]):.3f}", f"{cf_vx[k]:.6f}",
            f"{cf_wz[k]:.6f}", "1" if d_met[k] else "0",
        ]))
    TRACE.write_text("\n".join(lines) + "\n")
    if len(TRACE.read_text().strip().splitlines()) != n + 1:
        raise SystemExit("evidence guard: trace row count does not match frames")

    print(f"terminal leg entry   step {entry}  ({n - entry} steps remaining, "
          f"{(n-entry)*dt:.2f} s)")
    print(f"  route remaining    {route_len - s_step[entry]:.4f} m   goal distance "
          f"{gd_step[entry]:.4f} m")
    print(f"active target seq    {[t['vertex'] for t in transitions if t['steps_active']]}"
          f"  dwell {[t['steps_active'] for t in transitions if t['steps_active']]}")
    print(f"goal vertex active   {target_analysis['final_goal_vertex_became_active']} "
          f"from step {target_analysis['final_goal_vertex_active_from_step']} "
          f"({target_analysis['final_goal_vertex_active_steps']} steps)")
    print(f"goal vtx closest     {target_analysis['goal_vertex_closest_approach_m']} m "
          f"vs lookahead {lookahead} -> entered: "
          f"{target_analysis['goal_vertex_ever_within_lookahead']}")
    print(f"target distance      terminal mean {tgt_dist[T].mean():.3f} m, "
          f"max {tgt_dist.max():.3f} m")
    print()
    print(f"D predicate met      {int(d_met.sum())} / {n} steps   "
          f"min goal distance {gd_step.min():.4f} m (tol {goal_tol})")
    print(f"STOP BRANCH          {stop['CLASSIFICATION']}")
    print(f"VERDICT              {approach_or_stop['VERDICT']}")
    print()
    print(f"terminal progress    achieved {act_speed:.4f} m/s vs required "
          f"{req_speed:.4f} m/s  ratio {act_speed/req_speed:.3f}")
    print(f"                     {terminal_requirement['CLASSIFICATION']}")
    print(f"state at max_steps   {conv}  (goal slope {gd_slope:.5f} m/step, "
          f"{at_end['steps_to_close_at_final_rate']} steps to close at that rate)")
    print()
    print("counterfactual command field (offline, not integrated):")
    print(f"  target dist   vertex {tgt_dist[T].mean():.3f} m -> interpolated "
          f"{cf_dist[T].mean():.3f} m")
    print(f"  |heading err| vertex {np.degrees(np.abs(head_err[T])).mean():.2f} deg -> "
          f"interpolated {np.degrees(np.abs(cf_he[T])).mean():.2f} deg")
    print(f"  commanded vx  vertex {cmd_vx[T].mean():.4f} -> interpolated "
          f"{cf_vx[T].mean():.4f} m/s")
    print()
    print(f"spearman dist vs |wz|          {scaling['spearman_target_distance_vs_abs_commanded_wz']}")
    print(f"spearman dist vs progress eff  "
          f"{scaling['spearman_target_distance_vs_route_progress_efficiency']}")
    print(f"target switches               {len(switches)} at {switches}")
    print()
    print(f"Q3 CLASSIFICATION    {cls}")
    print(f"intervention         {intervention['STATUS']}")
    print(f"artefact             {OUT.relative_to(REPO)}")
    print(f"sha256               {sha256(OUT)}")
    print(f"trace                {TRACE.relative_to(REPO)}")
    print(f"trace sha256         {sha256(TRACE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
