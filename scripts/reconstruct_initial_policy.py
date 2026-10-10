"""Retrospective CPU reconstruction of the eight preserved initial invocations."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from initialization_diagnostic import (
    REPO,
    frozen,
    normalized_prediction,
    raw_rgb_sha,
    recorded_state_fields,
    sha,
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze-commit", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    cfg = frozen(a.freeze_commit, launch=True)
    if a.out.exists():
        p.error("output already exists")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["NAVFM_UPSTREAM"] = cfg["upstream"]
    sys.path.insert(0, str(REPO / "src"))
    import numpy as np
    import torch
    from PIL import Image

    from navfm.collection.rgb_baseline import RGBTopomapBaseline, topomap_components

    torch.set_num_threads(4)
    torch.manual_seed(0)
    comparison = json.loads((REPO / "configs/eval/prospective_r2_recovery_v1.json").read_text())
    chain = json.loads(Path(cfg["chain_json"]).read_text())
    report = dict(status="RUNNING", freeze_commit=a.freeze_commit, backend="cpu", attempts=[])

    def save():
        a.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")

    save()
    try:
        for arm in ["R2_recover", "B1x_exit"]:
            policy = RGBTopomapBaseline(
                Path(cfg["checkpoint"]),
                radius=4,
                close_threshold=3.0,
                **topomap_components(comparison["variants"][arm], start_lost=True),
                action_scale_m=0.049994826316833496,
                stop_enabled=True,
                max_v=0.1,
                control_period_s=0.5,
            )
            if policy.device != "cpu":
                raise ValueError("CPU reconstruction backend required")
            for route in cfg["existing_routes"]:
                root = Path(cfg["evidence_root"]) / f"v2-prospective_r2_a-{arm}-20261010-01" / route
                manifest = json.loads((root / "runtime_manifest.json").read_text())
                old = manifest["inference"][0]
                start = root / "start.png"
                goal = root / "goal.png"
                if manifest["initial_history_sha256"] != [raw_rgb_sha(start)] * 6:
                    raise ValueError("initial history provenance mismatch")
                if old["frame"] != 0 or old["sensor_time"] != old["predecision_sim_time"]:
                    raise ValueError("initial indexing mismatch")
                nodes = chain["routes"][route]["nodes"]
                if [[n["frame"], n["sha256"]] for n in nodes] != manifest["topomap"]["nodes"]:
                    raise ValueError("chain indexing mismatch")
                images = [np.asarray(Image.open(n["source"]).convert("RGB")) for n in nodes]
                runs = []
                for repeat in [1, 2]:
                    policy.set_chain(images)
                    if (
                        policy.manifest["config"] != manifest["policy"]["config"]
                        or policy.digest != manifest["policy"]["sha256"]
                    ):
                        raise ValueError("model identity mismatch")
                    observed_state = recorded_state_fields(
                        policy.state, list(manifest["initial_policy_state"])
                    )
                    observed_counters = {
                        key: getattr(policy, key) for key in manifest["initial_policy_counters"]
                    }
                    if (
                        observed_state != manifest["initial_policy_state"]
                        or observed_counters != manifest["initial_policy_counters"]
                    ):
                        raise ValueError("initial policy state/counters mismatch")
                    pred = policy.step(
                        [np.asarray(Image.open(start).convert("RGB"))] * 6,
                        np.asarray(Image.open(goal).convert("RGB")),
                    )
                    fields = [
                        "window_distances",
                        "requested_goal_distance",
                        "waypoint_normalized",
                        "command",
                        "predicted_distance",
                    ]
                    differences = {}
                    for field in fields:
                        av, bv = np.asarray(old[field]), np.asarray(pred[field])
                        differences[field] = dict(
                            max_abs=float(np.max(np.abs(av - bv))),
                            within_tolerance=bool(np.allclose(av, bv, atol=1e-3, rtol=1e-5)),
                        )
                    runs.append(
                        dict(
                            repetition=repeat,
                            prediction=normalized_prediction(pred),
                            recorded_comparison=differences,
                            window_exact=pred["chain"]["window"] == old["chain"]["window"],
                            chain_state_exact={
                                k: v for k, v in pred["chain"].items() if k != "argmin_distance"
                            }
                            == {k: v for k, v in old["chain"].items() if k != "argmin_distance"},
                            chain_distance_within_tolerance=bool(
                                np.isclose(
                                    pred["chain"]["argmin_distance"],
                                    old["chain"]["argmin_distance"],
                                    atol=1e-3,
                                    rtol=1e-5,
                                )
                            ),
                            terminal_exact=pred["policy_stop"] == old["policy_stop"]
                            and pred.get("policy_abstain") == old.get("policy_abstain"),
                        )
                    )
                report["attempts"].append(
                    dict(
                        attempt=root.parent.name + "/" + route,
                        manifest_sha256=sha(root / "runtime_manifest.json"),
                        initial_png_sha256=sha(start),
                        original_backend=manifest["policy"]["device"],
                        runs=runs,
                        repeat_exact=runs[0]["prediction"] == runs[1]["prediction"],
                    )
                )
                save()
        frozen(a.freeze_commit, launch=True)
        report["post_run_actual_asset_sha256"] = {
            path: sha(Path(path)) for path in cfg["asset_sha256"]
        }
        report["source_asset_preflight_and_postflight_match"] = True
        report["status"] = "COMPLETE"
        save()
    except Exception as exc:
        report["status"] = "FAIL"
        report["failure"] = str(exc)
        save()
        raise


if __name__ == "__main__":
    main()
