"""Preregister TERMINAL_APPROACH_INTERVENTION_V1, amended before execution.

Q3 drafted this intervention inside its own result artefact. That artefact is
published and cited, so it is not edited here. This script emits the standalone
preregistration, carries the drafted design forward unchanged, and adds the one
amendment authorised before execution: cross-track error as a DECLARED SECONDARY
OUTCOME, together with the look-ahead-domain measure that is tied to it.

Why the amendment exists. Q3 found the terminal miss was dominated by lateral
offset rather than by shortfall along the route: 0.932 m short along the route
against 1.396 m to the side, whose hypotenuse reproduces the recorded 1.6787 m
goal distance to within 0.0000 m. An intervention that reached the goal while
leaving lateral tracking unmeasured would leave the proposed mechanism untested,
and a successful arm could then be read as evidence for a mechanism nobody
measured. Declaring the measure before execution is what prevents that.

What the amendment deliberately does NOT do. It does not become a second primary
endpoint, it does not become an acceptance gate, and it introduces no pass/fail
threshold. The historical values from ``run_00001`` -- 2.589 m peak cross-track,
18.2% of terminal steps inside the look-ahead radius -- motivate measurement and
must not be turned into a criterion the treatment arm is scored against. The one
number used as a domain boundary, 0.45 m, is the frozen look-ahead radius that
already exists in the collection configuration, not a threshold chosen here.

The projection implementation is pinned by content hash so that both arms are
measured by the same instrument against the same frozen polyline. Measuring one
arm against a replanned route would make the comparison meaningless, which is why
the polyline coordinates are written into the preregistration rather than
recomputed at analysis time.
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import pathlib
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from diagnose_q2_margin_consumption import sha256  # noqa: E402

Q3 = REPO / "gates/BO10/q3_terminal_approach_20260911.json"
Q2 = REPO / "gates/BO10/q2_margin_consumption_20260911.json"
PROJ_SRC = REPO / "scripts/diagnose_q2_margin_consumption.py"
CONTROL_SRC = REPO / "src/navfm/control.py"
OUT = REPO / "gates/BO10/terminal_approach_intervention_v1_20260911.json"

#: Raise this AND the output path together to issue a versioned amendment.
PREREG_VERSION = "V1"


def _rel(path: pathlib.Path) -> str:
    """Repo-relative where possible; the guard harness redirects OUT to a tmpdir."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)

STATS = [
    "mean_absolute_cross_track_m",
    "median_absolute_cross_track_m",
    "rmse_cross_track_m",
    "max_absolute_cross_track_m",
    "p90_absolute_cross_track_m",
    "p95_absolute_cross_track_m",
]


def build_payload(stamp: str) -> dict[str, Any]:
    """The canonical preregistration payload, for a given freeze timestamp."""
    q3 = json.loads(Q3.read_text())
    draft = q3["next_experiment"]
    lookahead = float(q3["inputs"]["frozen_parameters"]["lookahead_m"])
    goal_tol = float(q3["inputs"]["frozen_parameters"]["goal_tol_m"])
    polyline = q3["planned_path_recovery"]["polyline"]

    result = {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1",
        "artifact_semantics": "PREREGISTRATION_AMENDED_BEFORE_EXECUTION_NOT_EXECUTED",
        "author": "Frank Asante Van Laarhoven",
        "preregistered_at": stamp,
        "STATUS": "PREREGISTERED_NOT_EXECUTED",
        "authorisation": "NOT AUTHORISED. Neither arm may run until authorised.",
        "execution_status": (
            "NOT EXECUTED. No arm has been run. Nothing in this artefact reports a "
            "measurement"
        ),
        "supersedes": {
            "note": (
                "the drafted design embedded at next_experiment in the Q3 result. "
                "That artefact is published and cited and is NOT edited; this "
                "preregistration carries its design forward and is the authority "
                "from here"
            ),
            "q3_artefact": str(Q3.relative_to(REPO)),
            "q3_sha256": sha256(Q3),
        },
        "amendment": {
            "amendment_id": "TAI-V1-A1",
            "timestamp_utc": stamp,
            "what_changed": (
                "added CROSS_TRACK_ERROR as a declared secondary outcome, plus the "
                "look-ahead-domain measure fraction_of_steps_within_lookahead_radius "
                "and a per-step terminal mechanism trace"
            ),
            "reason": (
                "Q3 established that the terminal miss was dominated by lateral "
                "offset rather than by shortfall along the route: 0.932 m short "
                "along the route against 1.396 m to the side, whose hypotenuse "
                "reproduces the recorded 1.6787 m goal distance to 0.0000 m, with "
                "69% of the squared miss lateral. Without this measure an arm could "
                "reach the goal and be read as evidence for a route-tracking "
                "mechanism that was never measured"
            ),
            "is_it_fixing_the_protocol_or_rescuing_a_hypothesis": (
                "fixing the protocol. It adds an observation channel before any arm "
                "runs. It cannot change which arm wins, because the primary outcome "
                "and every acceptance rule are untouched"
            ),
            "unchanged_by_this_amendment": [
                "the intervention factor", "the primary outcome", "the route",
                "the seed", "controller gains", "the look-ahead radius",
                "cruise speed", "velocity limits", "goal tolerance", "max_steps",
                "sample count", "every existing acceptance rule",
            ],
            "no_new_pass_fail_threshold": True,
        },
        "design_carried_forward_unchanged": {
            "single_factor": draft["single_factor"],
            "primary_outcome": draft["primary_outcome"],
            "existing_secondary_outcomes": draft["secondary_outcomes"],
            "held_constant": draft["held_constant"],
            "explicitly_forbidden": draft["explicitly_forbidden"],
            "justified_by": draft["justified_by"],
            "sample_count": (
                "unchanged: one trajectory per arm, as the drafted power note "
                "already specified"
            ),
        },
        "secondary_outcome_cross_track_error": {
            "STATUS": "DECLARED SECONDARY OUTCOME",
            "is_primary": False,
            "is_co_primary": False,
            "is_an_acceptance_gate": False,
            "purpose": (
                "quantify whether changing ONLY target selection -- current "
                "path-vertex target versus arc-length interpolated look-ahead target "
                "-- changes lateral tracking relative to the frozen planned route"
            ),
            "definition": {
                "per_step": (
                    "cross_track_error_t is the Euclidean lateral distance from the "
                    "realised position at step t to the nearest valid projection of "
                    "that position onto the frozen planned polyline"
                ),
                "projection_rule": (
                    "for each polyline segment, clamp the parametric foot of the "
                    "perpendicular to [0, 1] so the projection cannot fall off the "
                    "segment, then take the segment giving the smallest distance. "
                    "The clamp is what makes the projection valid at vertices and "
                    "beyond the endpoints"
                ),
                "sign_convention": (
                    "the signed value is the 2-D cross product of the unit segment "
                    "direction with the offset vector; every summary statistic in "
                    "this preregistration is taken on the ABSOLUTE value, so the "
                    "sign convention cannot affect any reported number"
                ),
                "applied_to": "every recorded realised pose in both arms",
                "MUST_NOT_SUBSTITUTE": (
                    "distance to the active target vertex is NOT cross-track error "
                    "and may not stand in for it. The two differ by metres in "
                    "run_00001"
                ),
                "MUST_NOT_REPLAN": (
                    "both arms are measured against the SAME frozen polyline. "
                    "Measuring an arm against a route replanned for that arm would "
                    "make the arms incomparable"
                ),
            },
            "instrument_pinned": {
                "function": "project",
                "module": "scripts/diagnose_q2_margin_consumption.py",
                "module_sha256": sha256(PROJ_SRC),
                "reason": (
                    "the same implementation and the same coordinate conventions "
                    "must measure both arms; pinning by content hash makes a silent "
                    "change to the instrument detectable"
                ),
            },
            "frozen_route_polyline": {
                "coordinates": polyline,
                "provenance": (
                    "recovered in Q2 by lattice search and re-verified in Q3: a "
                    "unique solution matching the stored path length to 3.6e-15 m"
                ),
                "written_here_so_both_arms_project_against_identical_coordinates": True,
            },
            "windows": {
                "whole_trajectory": "every recorded step of the arm",
                "terminal_planned_leg": {
                    "definition": (
                        "the arclength window from the last interior route vertex to "
                        "the sealed goal, identical in both arms because it is a "
                        "property of the frozen route and not of behaviour"
                    ),
                    "note": (
                        "the STEP at which each arm enters this window will differ "
                        "between arms; the WINDOW does not. Comparisons are made "
                        "over the window, not over a fixed step range"
                    ),
                },
            },
            "statistics_to_report_per_arm_per_window": STATS,
            "threshold_status": (
                "NONE. These are descriptive. No pass/fail threshold is defined "
                "here, and none may be introduced after results are seen"
            ),
            "historical_values_are_motivation_only": {
                "run_00001_max_abs_cross_track_m": 2.5888,
                "run_00001_terminal_fraction_within_lookahead": 0.182,
                "WARNING": (
                    "these motivated the measurement. They are NOT a target, NOT a "
                    "baseline to beat, and NOT a criterion. run_00001 is a different "
                    "experiment: it is the observational run the intervention exists "
                    "to follow up, not a control arm"
                ),
            },
        },
        "secondary_outcome_lookahead_domain": {
            "STATUS": "DECLARED SECONDARY OUTCOME, mechanistic",
            "name": "fraction_of_steps_within_lookahead_radius",
            "definition": (
                "count(absolute cross_track_error <= 0.45 m) divided by the number "
                "of valid recorded steps"
            ),
            "lookahead_radius_m": lookahead,
            "radius_provenance": (
                "the frozen look-ahead already in the collection configuration. It "
                "is used here as a domain boundary, not as an acceptance threshold, "
                "and no new number was invented"
            ),
            "report_for": ["whole_trajectory", "terminal_planned_leg"],
            "INTERPRETATION_CAVEAT": (
                "cross_track <= lookahead_radius must NOT be read as proof that a "
                "textbook pure-pursuit circle intersection exists at that step. The "
                "circle of the look-ahead radius centred on the robot also requires "
                "enough path remaining ahead of the projection for a FORWARD "
                "intersection to exist, which fails near the end of a route. Claim a "
                "valid intersection only where both geometric preconditions are "
                "checked explicitly"
            ),
            "why_it_is_worth_measuring": (
                "in run_00001 cross-track reached 2.589 m against a 0.45 m radius, "
                "so a circle-intersection tracker would have had no solution for "
                "most of the run. This measure says how much of each arm sits inside "
                "the geometry the look-ahead assumes"
            ),
        },
        "terminal_mechanism_trace": {
            "purpose": (
                "permit testing whether any difference in goal approach coincides "
                "with a difference in lateral tracking, rather than asserting it"
            ),
            "persist_per_step_over_the_terminal_planned_leg": [
                "route_progress_coordinate_m",
                "cross_track_error_m",
                "target_type",
                "target_distance_m",
                "heading_error_deg",
                "commanded_vx_m_s",
                "commanded_wz_rad_s",
                "realised_progress_increment_m",
                "goal_distance_m",
            ],
            "format": "one CSV per arm, committed as text evidence",
        },
        "interpretation_rules": {
            "primary_conclusion_source": (
                "the already-frozen primary outcome alone. Cross-track is secondary "
                "and may not carry the primary conclusion"
            ),
            "allowed_phrasing": (
                "the interpolated-target arm was associated with lower or higher "
                "lateral tracking error"
            ),
            "case_goal_improves_and_cross_track_improves": (
                "supports the hypothesis that improved route tracking is part of the "
                "observed mechanism. It does NOT by itself prove mediation"
            ),
            "case_goal_improves_but_cross_track_does_not": (
                "do NOT claim the benefit operated through lateral tracking"
            ),
            "case_cross_track_improves_but_goal_does_not": (
                "report improved tracking WITHOUT claiming improved task completion"
            ),
            "case_neither_improves": (
                "report no observed improvement in this instance"
            ),
            "mediation_requires": (
                "a design that varies the mediator, which this one-factor "
                "intervention does not"
            ),
        },
        "power_and_claim_limit": {
            "retained_from_the_draft": draft["power_note"],
            "sample_count_per_arm": 1,
            "may_demonstrate": (
                "a difference in this controlled instance, with every other factor "
                "held constant"
            ),
            "may_not_demonstrate": [
                "an expected population-level effect",
                "a success-rate improvement",
                "that the physical robot would behave similarly",
            ],
            "NO_SIGNIFICANCE_TESTING": (
                "statistical significance must not be reported from one trajectory "
                "per arm. No p-value, no confidence interval, no significance claim"
            ),
            "what_a_population_claim_would_need": (
                "a route population and a seed sweep, preregistered separately"
            ),
        },
        "execution_preconditions": draft["preconditions"] + [
            "this amended preregistration persisted and hashed before either arm runs",
        ],
        "provenance": {
            "q3_result": {"path": str(Q3.relative_to(REPO)), "sha256": sha256(Q3)},
            "q2_result": {"path": str(Q2.relative_to(REPO)), "sha256": sha256(Q2)},
            "controller_source": {
                "path": str(CONTROL_SRC.relative_to(REPO)),
                "sha256": sha256(CONTROL_SRC),
                "reason": "arm A is this file's behaviour; pin it so a change is visible",
            },
            "goal_tolerance_m": goal_tol,
        },
        "milestone_unaffected": {
            "BO-03_REAL_DATA_COMPATIBILITY": "COMPLETE",
            "BO-10_HOSPITAL_COLLECTION": "COMPLETE_FOR_COMPATIBILITY_PURPOSE",
            "run_00001": "IMMUTABLE; not a control arm for this intervention",
        },
    }

    return result


TIMESTAMP_FIELDS = (("preregistered_at",), ("amendment", "timestamp_utc"))


def strip_timestamps(payload: dict[str, Any]) -> dict[str, Any]:
    """The payload with freeze timestamps removed, for design comparison."""
    d = copy.deepcopy(payload)
    for fpath in TIMESTAMP_FIELDS:
        node: Any = d
        for key in fpath[:-1]:
            node = node.get(key, {})
        if isinstance(node, dict):
            node.pop(fpath[-1], None)
    return d


def diff_paths(a: Any, b: Any, prefix: str = "") -> list[str]:
    """Field paths at which two payloads differ, for the refusal message."""
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in b:
                out.append(f"{prefix}{k} (added)")
            elif k not in a:
                out.append(f"{prefix}{k} (removed)")
            else:
                out.extend(diff_paths(a[k], b[k], f"{prefix}{k}."))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{prefix.rstrip('.')} (length {len(b)} -> {len(a)})")
        else:
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                out.extend(diff_paths(x, y, f"{prefix}{i}."))
    elif a != b:
        out.append(prefix.rstrip(".") or "<root>")
    return out


def main() -> int:
    # A preregistration is frozen once, and "frozen" has to mean more than "a
    # file is present". Returning the existing artefact merely because it exists
    # would hide a design change behind an unchanged digest, which is the exact
    # opposite of what a preregistration is for. Overwriting it with a changed
    # design would be worse still: the record that gets cited would quietly stop
    # describing the experiment that was frozen.
    #
    # So the canonical payload is always REGENERATED, the original freeze
    # timestamp is preserved, and every other field is compared against the
    # frozen record. A match rewrites identical bytes and the digest is stable.
    # A mismatch REFUSES and demands an explicit new version.
    if OUT.exists():
        prior = json.loads(OUT.read_text())
        stamp = str(prior["preregistered_at"])
        result = build_payload(stamp)
        drift = diff_paths(strip_timestamps(result), strip_timestamps(prior))
        if drift:
            shown = "\n  ".join(drift[:20]) + ("\n  ..." if len(drift) > 20 else "")
            raise SystemExit(
                "PREREG_CANONICAL_PAYLOAD_GUARD = REFUSED\n\n"
                f"The canonical design no longer matches the frozen artefact at "
                f"{_rel(OUT)}.\n"
                f"Fields that differ ({len(drift)}):\n  {shown}\n\n"
                f"The frozen preregistration is {PREREG_VERSION} and is cited by "
                "hash. It will NOT be overwritten, and execution under it is "
                "refused.\n"
                "A changed design requires an explicit versioned amendment: raise "
                "PREREG_VERSION and write to a new artefact path, leaving this "
                "record and its digest intact."
            )
        refrozen = False
    else:
        stamp = _dt.datetime.now(_dt.UTC).isoformat()
        result = build_payload(stamp)
        refrozen = True

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())

    required = [
        "check", "STATUS", "amendment", "design_carried_forward_unchanged",
        "secondary_outcome_cross_track_error", "secondary_outcome_lookahead_domain",
        "terminal_mechanism_trace", "interpretation_rules", "power_and_claim_limit",
        "provenance",
    ]
    missing = [k for k in required if k not in back]
    if missing:
        raise SystemExit(f"evidence guard: missing required keys {missing}")
    ct = back["secondary_outcome_cross_track_error"]
    if ct["is_primary"] or ct["is_co_primary"] or ct["is_an_acceptance_gate"]:
        raise SystemExit("evidence guard: cross-track must remain secondary")
    if not back["amendment"]["no_new_pass_fail_threshold"]:
        raise SystemExit("evidence guard: amendment must introduce no threshold")
    if back["STATUS"] != "PREREGISTERED_NOT_EXECUTED":
        raise SystemExit("evidence guard: status must record that nothing has run")
    if set(ct["statistics_to_report_per_arm_per_window"]) != set(STATS):
        raise SystemExit("evidence guard: statistic list does not round-trip")
    q3_draft = json.loads(Q3.read_text())["next_experiment"]
    if back["design_carried_forward_unchanged"]["primary_outcome"] != q3_draft["primary_outcome"]:
        raise SystemExit("evidence guard: the primary outcome was altered")

    digest = sha256(OUT)
    print(f"preregistration   {_rel(OUT)}")
    print(f"freeze            {'FIRST FREEZE' if refrozen else 'PRESERVED from the existing artefact'}"
          f" at {stamp}")
    print(f"sha256            {digest}")
    print(f"status            {back['STATUS']} / {back['authorisation']}")
    print(f"cross-track       primary={ct['is_primary']} co_primary={ct['is_co_primary']} "
          f"gate={ct['is_an_acceptance_gate']}")
    print(f"primary outcome   {back['design_carried_forward_unchanged']['primary_outcome']}")
    print(f"new thresholds    {'none' if back['amendment']['no_new_pass_fail_threshold'] else 'SOME'}")
    print(f"statistics        {', '.join(STATS)}")
    print("windows           whole_trajectory, terminal_planned_leg")
    print(f"lookahead domain  |cross_track| <= "
          f"{back['secondary_outcome_lookahead_domain']['lookahead_radius_m']} m"
          "  (frozen radius, not a threshold)")
    print(f"projection pinned {ct['instrument_pinned']['module']} "
          f"@ {ct['instrument_pinned']['module_sha256'][:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
