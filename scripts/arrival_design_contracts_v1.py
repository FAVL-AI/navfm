"""Validate a preparation-only arrival design; calculate assumptions, never execute a study."""

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

CONFIG = Path(__file__).resolve().parents[1] / "configs/eval/arrival_contribution_design_v1.json"

DRAFT_CONFIG_SHA256 = "5c42b49ab8c8dc1630080f4e7dec01c86bf822886d7ec4d9cd9e733bc5ed120c"


def required_layouts(sd, gap, alpha=0.025, power=0.8):
    """Normal approximation for a paired layout mean; not empirical/joint power."""
    values = (sd, gap, alpha, power)
    if any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
        for x in values
    ):
        raise ValueError("finite numeric planning assumptions required")
    if sd <= 0 or gap <= 0 or not 0 < alpha < 0.5 or not 0.5 < power < 1:
        raise ValueError("positive SD/gap and valid alpha/power required")
    z = NormalDist().inv_cdf(1 - alpha) + NormalDist().inv_cdf(power)
    return math.ceil((z * sd / gap) ** 2)


def validate_draft_semantics(cfg):
    """Refuse specific unsafe design claims independently of the byte binding."""
    try:
        p, c, m, method = (cfg[k] for k in ("population", "comparison", "metrics", "method"))
        checks = [
            cfg["runtime_authorized"] is False,
            cfg["status"] == "DRAFT_NOT_FROZEN",
            p["test_access"] == "BLOCKED",
            p["human_reviewer"] is None,
            p["independent_seed_custodian"] is None,
            p["independent_attestation"] is None,
            cfg["gates"]["motion_qualification"] == "BLOCKED",
            cfg["gates"]["illumination_authorization"] == "BLOCKED",
            c["test_tuning"] is False,
            c["seed_aggregation"] == "all_seeds_mean_within_layout_no_best_seed",
            p["denominator"] == "all_planned_attempts_failures_and_refusals_retained",
            p["unit"] == "independent_layout",
            m["oracle"] == "ground_truth_evaluation_only_not_policy_arm",
            method["cadence_hz"] == method["reference_cadence_hz"] == 4,
            p["feasible_episodes_per_layout"]
            == p["base_start_goals_per_layout"] * p["alias_levels"] * p["illumination_levels"],
        ]
    except (KeyError, TypeError) as exc:
        raise ValueError("required draft semantic fields missing") from exc
    if not all(checks):
        raise ValueError("draft safety, custody, population or comparison semantics violated")


def design_summary(cfg):
    """Only the versioned draft is admitted; unsupported amendments need another version."""
    if hashlib.sha256(CONFIG.read_bytes()).hexdigest() != DRAFT_CONFIG_SHA256:
        raise ValueError("draft source binding drift; review config and validator together")
    validate_draft_semantics(cfg)
    canonical = json.loads(CONFIG.read_text())
    if json.dumps(cfg, sort_keys=True, allow_nan=False) != json.dumps(
        canonical, sort_keys=True, allow_nan=False
    ):
        raise ValueError("versioned design contract drift; amend through a reviewed new version")
    if cfg["runtime_authorized"] or cfg["status"] != "DRAFT_NOT_FROZEN":
        raise ValueError("this design cannot authorize runtime")
    p, c, m, plan = (cfg[k] for k in ("population", "comparison", "metrics", "planning"))
    alpha, power = cfg["inference"]["one_sided_alpha"], plan["target_power"]
    binary_gap = (
        cfg["inference"]["wrong_location_delta_upper_bound"] - plan["wrong_location_alternative"]
    )
    completion_gap = (
        plan["completion_alternative"] - cfg["inference"]["completion_delta_lower_bound"]
    )
    time_gap = cfg["inference"]["restricted_time_delta_upper_bound_s"] - plan["time_alternative_s"]
    z = NormalDist().inv_cdf(1 - alpha) + NormalDist().inv_cdf(power)
    feasible = p["feasible_episodes_per_layout"]
    controls = p["goal_mismatch_controls_per_layout"]
    cells = p["planned_test_layouts"] * (feasible + controls) * len(c["seeds"])
    duration = m["decision_horizon_s"] + m["post_stop_reserve_s"]
    r = cfg["resources"]
    prep = sum(
        r[k]
        for k in (
            "qualification_episode_equivalents_cap",
            "reference_acquisition_episodes_cap",
            "development_calibration_episodes_cap",
        )
    )
    full_wall = (prep + cells * len(c["test_arms"])) * r["episode_wall_cap_s"] / 3600
    full_GPU = full_wall + r["training_GPU_hours_cap"]
    full_wall += r["training_wall_hours_cap"]
    if full_GPU > r["total_GPU_hours_cap"] or full_wall > r["total_wall_hours_cap"]:
        raise ValueError("proposed finite resource ceilings exceeded")
    return {
        "status": "VALID_DRAFT_RUNTIME_BLOCKED",
        "statistical_unit": p["unit"],
        "baseline_wrong_location_rate": "UNKNOWN",
        "central_assumption_normal_CI_half_width_binary": NormalDist().inv_cdf(1 - alpha)
        * 0.15
        / math.sqrt(p["planned_test_layouts"]),
        "central_assumption_normal_CI_half_width_time_s": NormalDist().inv_cdf(1 - alpha)
        * 15
        / math.sqrt(p["planned_test_layouts"]),
        "binary_sensitivity_layouts": [
            max(
                required_layouts(sd, binary_gap, alpha, power),
                required_layouts(sd, completion_gap, alpha, power),
            )
            for sd in plan["binary_sd_sensitivity"]
        ],
        "time_sensitivity_layouts": [
            required_layouts(sd, time_gap, alpha, power) for sd in plan["time_sd_sensitivity_s"]
        ],
        "binary_sd_ceiling_for_planned_layouts": math.sqrt(p["planned_test_layouts"])
        * min(binary_gap, completion_gap)
        / z,
        "time_sd_ceiling_for_planned_layouts_s": math.sqrt(p["planned_test_layouts"])
        * time_gap
        / z,
        "planning_limit": "marginal_normal_approximation_not_joint_claim_power; pilot_variance_support_missing",
        "full_design_episodes": cells * len(c["test_arms"]),
        "primary_pair_episodes": cells * len(c["primary_arms"]),
        "full_design_simulated_hours_ceiling": cells * len(c["test_arms"]) * duration / 3600,
        "primary_pair_simulated_hours_ceiling": cells * len(c["primary_arms"]) * duration / 3600,
        "proposed_full_with_preparation_wall_hours_ceiling": full_wall,
        "proposed_full_with_preparation_GPU_hours_ceiling": full_GPU,
        "proposed_storage_GiB_cap": r["external_storage_GiB_cap"],
        "measured_wall_clock_GPU_memory_storage": "UNKNOWN_PENDING_SEPARATE_RESOURCE_MEASUREMENT",
        "runtime": "NOT_RUN",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    print(json.dumps(design_summary(json.loads(args.config.read_text())), indent=2))


if __name__ == "__main__":
    main()
