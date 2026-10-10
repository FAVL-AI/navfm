"""Version 2 source/asset freeze and explicit bootstrap eligibility contracts."""

from __future__ import annotations

import json
from pathlib import Path

from initialization_diagnostic import FILES as V1_FILES
from initialization_diagnostic import REPO, git, sha, validate_render_interval

V1_FREEZE = "f831a110e6854c919a21c8397eee950cf79b77fd"
CONFIG = REPO / "configs/eval/initialization_diagnostic_v2.json"
FILES = [
    *V1_FILES,
    "scripts/initialization_diagnostic_v2.py",
    "scripts/collect_initialization_diagnostic_v2.py",
    "scripts/run_initialization_diagnostic_v2.py",
    "tests/test_initialization_diagnostic_v2.py",
    "docs/INITIALIZATION_DIAGNOSTIC_V2_PLAN.md",
    "configs/eval/initialization_diagnostic_v2.json",
]


def frozen(commit: str, *, launch: bool = False) -> dict:
    commit = git("rev-parse", commit).decode().strip()
    if launch and (
        git("status", "--porcelain") or git("rev-parse", "HEAD").decode().strip() != commit
    ):
        raise ValueError("Launch requires clean exact v2 freeze HEAD")
    for name in V1_FILES:
        if (REPO / name).read_bytes() != git("show", f"{V1_FREEZE}:{name}"):
            raise ValueError("Immutable v1 file drift: " + name)
    for name in FILES:
        if (REPO / name).read_bytes() != git("show", f"{commit}:{name}"):
            raise ValueError("Frozen v2 source drift: " + name)
    cfg = json.loads(CONFIG.read_text())
    for path, digest in cfg["asset_sha256"].items():
        if sha(Path(path)) != digest:
            raise ValueError("Asset drift: " + path)
    return cfg


def eligibility_ok(captures: list[dict], startup_mode: int) -> None:
    if len(captures) != 3:
        raise ValueError("Exactly three fixed eligibility captures required")
    for i, capture in enumerate(captures):
        if (
            capture["physical_step"] != i + 1
            or capture["mechanical_ok"] is not True
            or capture.get("unknown")
        ):
            raise ValueError("Unqualified eligibility state/index")
        if abs(capture["sensor_time"] - capture["sim_time"]) > 1e-8:
            raise ValueError("Stale eligibility observation")
        if capture["settings"]["/rtx/post/dlss/execMode"] != startup_mode:
            raise ValueError("Startup renderer mode drift")


def bootstrap_ok(record: dict) -> None:
    validate_render_interval(
        record["before_sim_time"], record["after_sim_time"], 0.0, record["feedback_updates"]
    )
    if record["requested_delta_s"] != 0.0 or record["qualified_policy_observation"] is not False:
        raise ValueError("Bootstrap must remain unqualified zero-delta initialization")
