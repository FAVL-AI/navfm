"""Validate an unapproved budget proposal only; no acquisition entry point."""

import json
from pathlib import Path

PHASES = (
    "parent_setup",
    "sdk_startup",
    "capture_non_snapshot_work",
    "snapshot_label_persistence",
    "completion_capsule",
    "sdk_shutdown",
    "child_reaping",
)


def validate_proposal(cfg):
    if cfg.get("status") != "UNAPPROVED_UNEXECUTED" or cfg.get("execution_authorized") is not False:
        raise ValueError("proposal cannot authorize execution")
    bounds = cfg["phase_allowance_seconds"]
    if set(bounds) != set(PHASES):
        raise ValueError("complete disjoint phase accounting required")
    if any(type(bounds[k]) is not int or bounds[k] <= 0 for k in PHASES):
        raise ValueError("positive integer phase allowance required")
    if (
        type(cfg["hard_total_seconds"]) is not int
        or sum(bounds.values()) != cfg["hard_total_seconds"]
    ):
        raise ValueError("phase sum differs from hard total")
    if cfg["hard_total_seconds"] != 190:
        raise ValueError("reviewed proposal total drift")
    invariant = cfg["unchanged_acquisition"]
    if invariant != dict(
        frames=144,
        routes=4,
        frames_per_route=36,
        held_steps_per_frame=4,
        resolution=[320, 240],
        jpeg_quality=95,
    ):
        raise ValueError("acquisition contract drift")
    if cfg.get("prior_layout_exposure") != "ACCESSED_NOT_UNINSPECTED":
        raise ValueError("exposure disclosure required")
    return dict(
        status="VALID_PROPOSAL_ONLY",
        execution_authorized=False,
        hard_total_seconds=cfg["hard_total_seconds"],
    )


def load_proposal(path):
    return validate_proposal(json.loads(Path(path).read_text()))
