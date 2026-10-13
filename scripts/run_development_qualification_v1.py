"""Explicit one-stage launcher; no retries or automatic stage expansion."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from development_qualification_contracts_v1 import ORDER, ROOT, compare_initial, frozen, write


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--stage", choices=("compatibility", "development-pair"), required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    cfg_path = ROOT / "configs/eval/development_qualification_v1.json"
    cfg = json.loads(cfg_path.read_text())
    out = a.out.resolve()
    if out.is_relative_to(ROOT):
        raise ValueError("external evidence required")
    frozen(a.freeze, cfg)
    if a.stage == "development-pair" and not cfg.get("development_pair_authorized", False):
        raise ValueError(cfg["development_blocker"])
    if a.stage == "compatibility":
        if out.exists():
            raise ValueError("new external output required")
        out.mkdir(parents=True)
    elif not out.is_dir():
        raise ValueError("compatibility output required first")
    ledger = out / "ledger.jsonl"
    records = [json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
    import signal

    from development_qualification_contracts_v1 import (
        cancel_signal,
        next_launch,
        run_bounded,
        sha,
        validate_clocks,
        validate_prior,
    )

    signal.signal(signal.SIGTERM, cancel_signal)

    launches = ORDER[:4] if a.stage == "compatibility" else ORDER[4:]
    env = dict(os.environ, NAVFM_UPSTREAM=cfg["upstream"], PYTHONPATH=str(ROOT / "src"))
    if any(Path(x).exists() for x in cfg["cleanup_must_be_absent"]):
        raise ValueError("CI cleanup not complete; runtime prohibited")

    def append(r):
        with ledger.open("a") as f:
            f.write(json.dumps(r, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        records.append(r)

    for launch in launches:
        frozen(a.freeze, cfg)
        next_launch(records, launch)
        validate_prior(records, a.freeze, cfg, out)
        role = launch.removeprefix("compat-").removeprefix("dev-")
        dest = out / launch
        if dest.exists() or dest.with_suffix(".json").exists():
            raise ValueError("attempt output already exists")
        if launch.startswith("compat-"):
            cmd = [
                cfg["python"],
                str(ROOT / "scripts/development_compatibility_v1.py"),
                "--config",
                str(cfg_path),
                "--role",
                role,
                "--out",
                str(dest.with_suffix(".json")),
            ]
            timeout = 150
        else:
            model = cfg["models"][role]
            cmd = [
                cfg["python"],
                str(ROOT / "scripts/collect_development_vint_v1.py"),
                "--out",
                str(dest),
                "--robot",
                cfg["robot"],
                "--actuation",
                "wheel",
                "--checkpoint",
                model["checkpoint"],
                "--checkpoint-sha256",
                model["sha256"],
                "--qualification",
                cfg["qualification"],
                "--yaw-feedback",
                "--goal-root",
                cfg["goal_root"],
                "--route-id",
                cfg["route"],
                "--max-steps",
                "600",
                "--policy-period-frames",
                "6",
                "--policy-max-v",
                "0.1",
                "--stop-rule",
                "upstream_t3",
                "--topomap-root",
                cfg["topomap_root"],
                "--topomap-radius",
                "4",
                "--topomap-close-threshold",
                "3.0",
            ]
            timeout = 600
        append(
            {
                "event": "start",
                "id": launch,
                "freeze": a.freeze,
                "argv": cmd,
                "wall_time": time.time(),
            }
        )
        start = time.monotonic()
        rc = None
        status = "FAIL"
        error = None
        report_path = None
        try:
            with dest.with_suffix(".log").open("wb") as log:
                rc = run_bounded(cmd, env, ROOT, log, timeout)
            frozen(a.freeze, cfg)
            if rc != 0:
                raise ValueError("child failed")
            if launch.startswith("compat-"):
                report_path = dest.with_suffix(".json")
                report = json.loads(report_path.read_text())
                if (
                    report["status"] != "PASS"
                    or report.get("device_type") != "cuda"
                    or report.get("role") != role
                    or report.get("checkpoint_sha256") != cfg["models"][role]["sha256"]
                ):
                    raise ValueError("compatibility report failed")
            else:
                collection = json.loads((dest / "collection.json").read_text())
                if collection["status"] != "COMPLETED" or len(collection["episodes"]) != 1:
                    raise ValueError("incomplete single episode")
                episode = dest / collection["episodes"][0]["id"]
                subprocess.run(
                    [
                        cfg["python"],
                        str(ROOT / "scripts/verify_rgb_feasibility.py"),
                        "--manifest",
                        str(episode / "runtime_manifest.json"),
                    ],
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                boundary = json.loads((dest / "first_policy_input.json").read_text())
                manifest = json.loads((episode / "runtime_manifest.json").read_text())
                if manifest["policy"]["device"] != "cuda":
                    raise ValueError("development CUDA device required")
                if manifest["topomap"]["chain_json_sha256"] != cfg["chain_sha256"]:
                    raise ValueError("declared reference chain digest mismatch")
                boundary["camera"] = {
                    "local_pose": manifest["camera_local_pose"],
                    "product": {
                        o["name"]: o["value"]
                        for o in manifest["observations"]
                        if o["name"]
                        in (
                            "render_product_path",
                            "render_product_camera_target",
                            "render_product_resolution",
                            "active_renderer",
                        )
                    },
                }
                if len(boundary["camera"]["product"]) != 4 or any(
                    v is None for v in boundary["camera"]["product"].values()
                ):
                    raise ValueError("missing camera/product provenance")
                boundary["pose"] = manifest["inference"][0]["predecision_pose"]
                boundary["predecision_sim_time"] = manifest["inference"][0]["predecision_sim_time"]
                boundary["sensor_time"] = manifest["inference"][0]["sensor_time"]
                validate_clocks(boundary["sensor_time"], boundary["predecision_sim_time"])
                if boundary["history_sha256"][:-1] != manifest["initial_history_sha256"][1:]:
                    raise ValueError("first history does not equal initialized history")
                write(dest / "boundary.json", boundary)
                report_path = dest / "boundary.json"
                if launch == ORDER[-1]:
                    import numpy as np
                    from PIL import Image

                    previous = out / ORDER[-2]
                    first = json.loads((previous / "boundary.json").read_text())
                    if first["state"] != boundary["state"]:
                        raise ValueError("initial chain state mismatch")
                    if first["goal_rgb_sha256"] != boundary["goal_rgb_sha256"]:
                        raise ValueError("goal mismatch")
                    aa = np.asarray(
                        Image.open(previous / "first_policy_input.png").convert("L")
                    ).astype(float)
                    bb = np.asarray(
                        Image.open(dest / "first_policy_input.png").convert("L")
                    ).astype(float)
                    match = compare_initial(first, boundary, float(np.abs(aa - bb).mean()))
                    write(out / "initial-pair-integrity.json", match)
                    if match["status"] != "PASS":
                        raise ValueError("pair initialization integrity failed")
            status = "PASS"
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, InterruptedError)):
                status = "CANCELLED"
            error = type(exc).__name__ + ": " + str(exc)
        append(
            {
                "event": "end",
                "freeze": a.freeze,
                "report_sha256": sha(report_path)
                if report_path is not None and report_path.exists()
                else None,
                "id": launch,
                "status": status,
                "exit": rc,
                "wall_s": time.monotonic() - start,
                "error": error,
            }
        )
        if status != "PASS":
            raise SystemExit("HALTED: " + str(error))
    print("Stage complete; STOP. No automatic continuation.")


if __name__ == "__main__":
    main()
