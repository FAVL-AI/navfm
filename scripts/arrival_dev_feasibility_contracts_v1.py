"""Check a blocked DEV feasibility proposal; no runtime or empirical analysis entry point."""

import argparse
import hashlib
import json
import math
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "configs/eval/arrival_dev_feasibility_design_v1.json"
DRAFT_CONFIG_SHA256 = "6e8e029ec2fa2c77877fe72c15556ad3208e2c69085a9afa3b594682c1f05744"


def allocation(cfg):
    """Finite proposed slot ceiling; unsupported goals are not invented outcomes."""
    p, r = cfg["population"], cfg["resources"]
    feasible = (
        p["layouts"]
        * p["feasible_tasks_per_layout"]
        * len(cfg["arms"])
        * len(cfg["backbone"]["seeds"])
    )
    controls = (
        p["layouts"]
        * p["mismatch_control_slots_per_layout"]
        * len(cfg["arms"])
        * len(cfg["backbone"]["seeds"])
    )
    slots = feasible + controls
    episode_h = slots * r["episode_process_wall_cap_s"] / 3600
    prep_h = (
        (r["reference_processes_cap"] + r["comparator_measurement_replay_processes_cap"])
        * r["episode_process_wall_cap_s"]
        / 3600
    )
    known_h = (
        episode_h
        + prep_h
        + r["calibrator_training_wall_GPU_hours_cap"]
        + r["analysis_wall_GPU_hours_cap"]
    )
    if known_h > r["total_wall_GPU_hours_cap"]:
        raise ValueError("proposed hard wall/GPU allocation exceeded")
    return {
        "status": "VALID_DRAFT_RUNTIME_BLOCKED",
        "feasible_episode_slots": feasible,
        "separate_control_slots_maximum": controls,
        "all_slots_maximum": slots,
        "navigation_simulation_hours_ceiling": feasible
        * (r["decision_horizon_simulation_s"] + r["post_stop_reserve_simulation_s"])
        / 3600,
        "episode_reserved_wall_GPU_hours": episode_h,
        "known_reserved_wall_GPU_hours": known_h,
        "hard_wall_GPU_hours_cap": r["total_wall_GPU_hours_cap"],
        "unassigned_headroom_hours_no_extra_trials": r["total_wall_GPU_hours_cap"] - known_h,
        "external_storage_GiB_cap": r["external_storage_GiB_cap"],
        "first_block_slots_included": cfg["first_block"]["slots"],
        "baseline_W_C_Tstar_layout_SD_runtime_storage": "UNKNOWN_NOT_MEASURED",
        "runtime": "NOT_RUN",
    }


def validate_semantics(cfg):
    """Specific draft restrictions are checked separately from version-byte consistency."""
    if cfg["runtime_authorized"] is not False or cfg["status"] != "DRAFT_NOT_FROZEN":
        raise ValueError("runtime authorization cannot come from this draft")
    if (
        cfg["arms"] != ["PlaceNav_STOP_adapter", "ULVN_STOP_adapter", "full_candidate"]
        or cfg["fairness"]["comparator_fallback"] is not False
    ):
        raise ValueError("both strong comparator adapters required; no fallback")
    if cfg["backbone"]["seeds"] != [0, 11, 22]:
        raise ValueError("all fixed seeds required; no reselection")
    p, b, r = (cfg[k] for k in ("population", "first_block", "resources"))
    if (
        p["test_budget_authorization"] is not False
        or p["test_geometry_access"] != "BLOCKED_UNCHANGED"
    ):
        raise ValueError("confirmatory test access and budgets stay blocked")
    if (
        b["included_in_total"] is not True
        or b["slots"] != b["layouts"] * b["feasible_tasks"] * b["arms"] * b["seeds"]
        or b["outcome_based_retuning_or_early_success"] is not False
    ):
        raise ValueError("first matched block must be included without outcome tuning")
    if (
        p["feasible_tasks_per_layout"]
        != p["reference_chains_per_layout"] * p["starts_per_reference_chain"]
    ):
        raise ValueError("fixed reference/start allocation inconsistent")
    if (
        cfg["controls"]["navigation_permitted"] is not False
        or cfg["controls"]["unsupported_interface"] != "NOT_RUN_UNSUPPORTED_GOAL_INTERFACE"
    ):
        raise ValueError("unsupported goal cannot become a fabricated rollout")
    if cfg["fairness"]["photometric_or_cadence_perturbation"] is not False:
        raise ValueError("paused perturbation work cannot resume")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        for key, value in r.items()
        if key.endswith(("_cap", "_s"))
    ):
        raise ValueError("positive finite numeric resource caps required")
    allocation(cfg)


def design_summary(cfg):
    if hashlib.sha256(CONFIG.read_bytes()).hexdigest() != DRAFT_CONFIG_SHA256:
        raise ValueError("draft source binding drift")
    validate_semantics(cfg)
    if json.dumps(cfg, sort_keys=True, allow_nan=False) != json.dumps(
        json.loads(CONFIG.read_text()), sort_keys=True, allow_nan=False
    ):
        raise ValueError("reviewed draft configuration drift")
    return allocation(cfg)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    print(json.dumps(design_summary(json.loads(args.config.read_text())), indent=2))


if __name__ == "__main__":
    main()
