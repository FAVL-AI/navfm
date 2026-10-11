"""Saved-RGB replay through deployment adapter; command sink is a local list only."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--images", type=Path, required=True)
    p.add_argument("--goal", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists() or a.out.resolve().is_relative_to(REPO):
        p.error("new external output required")
    from navfm import upstream
    from navfm.collection.rgb_baseline import RGBBaseline
    from navfm.deployment.yahboom import YahboomAdapter

    policy = RGBBaseline(
        a.checkpoint, action_scale_m=0.049994826316833496, stop_enabled=True, max_v=0.1
    )
    sent = []
    goal = np.asarray(Image.open(a.goal).convert("RGB"))
    adapter = YahboomAdapter(policy, goal, sent.append)
    files = sorted(a.images.glob("*.jpg"), key=lambda x: int(x.stem))[2::3][:20]
    if len(files) < 6:
        raise ValueError("six saved observations required")
    results = []
    for i, f in enumerate(files):
        rgb = np.asarray(Image.open(f).convert("RGB"))
        results.append(adapter.observe(rgb, i * 0.25, i * 0.25))
    # Verify the deployed tensor equals official loader cropping + reference normalization.
    upstream.ensure_upstream()
    import torch
    from vint_train.data.data_utils import resize_and_aspect_crop

    raw = resize_and_aspect_crop(Image.fromarray(rgb), tuple(policy.config["image_size"]))
    official_obs, _ = upstream.apply_reference_transform(
        torch.cat([raw] * 6).unsqueeze(0),
        raw.unsqueeze(0),
        upstream.reference_transform(),
        policy.device,
    )
    torch.testing.assert_close(policy.tensor([rgb] * 6), official_obs, rtol=0, atol=0)
    # Demonstrate stale acquisition produces a zero command and rejection.
    rejected = False
    try:
        adapter.observe(rgb, 100, 101)
    except ValueError:
        rejected = True
    if not rejected or sent[-1] != [0, 0, 0]:
        raise ValueError("watchdog failed")
    a.out.mkdir(parents=True)
    report = {
        "status": "PASS",
        "hardware_transport": "NONE_LOCAL_LIST_SINK",
        "frames": len(files),
        "checkpoint": policy.manifest,
        "golden_tensor_exact": True,
        "stale_frame_stops": True,
        "commands": sent,
        "results": results,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (a.out / "adapter_check.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "status",
                    "frames",
                    "hardware_transport",
                    "golden_tensor_exact",
                    "stale_frame_stops",
                ]
            }
        )
    )


if __name__ == "__main__":
    main()
