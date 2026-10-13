"""Bounded startup/close diagnostic worker; no scene or camera work."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _event(path: Path, name: str, **fields: Any) -> None:
    row = {
        "event": name,
        "utc": datetime.now(timezone.utc).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
        **fields,
    }
    payload = json.dumps(row, sort_keys=True, allow_nan=False) + "\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def run(output: Path, config_path: Path) -> None:
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    events = output / "child_events.jsonl"
    if events.exists():
        raise FileExistsError("child event journal already exists")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    app_cfg = cfg["application"]
    launch = {
        "headless": app_cfg["headless"],
        "renderer": app_cfg["renderer"],
        "width": app_cfg["resolution"][0],
        "height": app_cfg["resolution"][1],
    }
    sim_config = {
        "hz": app_cfg["sim_hz"],
        "headless": app_cfg["headless"],
        "resolution": app_cfg["resolution"],
        "rt_subframes": app_cfg["rt_subframes"],
        "warmup_frames": app_cfg["warmup_frames"],
        "dlss_quality": app_cfg["dlss_quality"],
        "physics_substeps": app_cfg["physics_substeps"],
        "seed": app_cfg["seed"],
        "renderer": app_cfg["renderer"],
    }
    sim_config["resolution"] = tuple(sim_config["resolution"])
    _event(
        events,
        "worker_started",
        python=sys.executable,
        python_realpath=os.path.realpath(sys.executable),
        cwd=os.getcwd(),
        hub_mode=os.environ.get("OMNICLIENT_HUB_MODE"),
        isaacsim_version=version("isaacsim"),
        launch_arguments=launch,
        sim_config=sim_config,
        scene_or_capture_work=False,
    )
    if (
        os.environ.get("OMNICLIENT_HUB_MODE") != "disabled"
        or Path.cwd() != ROOT
        or version("isaacsim") != cfg["runtime"]["isaacsim_distribution_version"]
        or Path(sys.executable).resolve() != Path(cfg["runtime"]["python"]).resolve()
    ):
        _event(events, "preflight_rejected", reason="runtime_binding_mismatch")
        raise RuntimeError("startup diagnostic runtime binding mismatch")

    _event(events, "before_isaac_import")
    import isaacsim

    _event(events, "after_isaac_import")

    native_constructor = isaacsim.SimulationApp

    def observed_constructor(*args: Any, **kwargs: Any) -> Any:
        actual_launch = args[0] if args and isinstance(args[0], dict) else {}
        observed_launch = {
            key: actual_launch.get(key) for key in ("headless", "renderer", "width", "height")
        }
        _event(events, "before_simulation_app_constructor", launch_arguments=observed_launch)
        if observed_launch != launch:
            _event(events, "launch_arguments_mismatch")
            raise ValueError("actual SimulationApp arguments differ from frozen launch")
        app = native_constructor(*args, **kwargs)
        _event(events, "after_simulation_app_constructor")
        return app

    isaacsim.SimulationApp = observed_constructor
    from navfm.isaac.app import IsaacApp, SimConfig

    sim = IsaacApp(SimConfig(**sim_config))
    try:
        _event(events, "before_isaac_app_start")
        sim.start()
        _event(
            events,
            "application_start_returned",
            bootstrap_compatibility_branch=list(sim._version or ()),
        )
    except BaseException as exc:
        _event(events, "application_start_raised", error_type=type(exc).__name__)
        raise
    finally:
        if sim.app is not None:
            _event(events, "before_close")
            try:
                sim.close()
            except BaseException as exc:
                _event(events, "close_raised", error_type=type(exc).__name__)
                raise
            else:
                _event(events, "close_returned")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.out.resolve(), args.config.resolve())
    except BaseException as exc:
        print(f"STARTUP_DIAGNOSTIC_FAIL: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
