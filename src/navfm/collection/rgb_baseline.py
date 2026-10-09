"""Released ViNT direct-image-goal baseline; policy has no simulator handles."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from navfm.control import BaseLimits, PDConfig, reference_pd_twist

STOP_RULES = {
    # Historical project rule; its <=1 threshold is below the model's observed
    # goal-as-current output floor (docs/ARRIVAL_RESEARCH_DECISION.md).
    "project": "three consecutive predicted temporal distances <=1 and selected waypoint <=0.15m; latched",
    # Pinned deployment close_threshold default (navigate.py --close-threshold 3),
    # applied to the goal image as a single-node map; not fitted to project data.
    "upstream_t3": "predicted temporal distance <=3 (upstream close_threshold default); latched",
}


class RGBBaseline:
    def __init__(
        self,
        checkpoint: Path,
        *,
        action_scale_m: float = 0.2 / 4,
        stop_enabled: bool = False,
        max_v: float = 0.2,
        control_period_s: float = 0.25,
        stop_rule: str = "project",
    ):
        import torch
        from torchvision import transforms

        from navfm import upstream
        from navfm.models.loader import extract_state_dict, load_checkpoint, sha256

        if stop_rule not in STOP_RULES:
            raise ValueError(f"unknown stop rule {stop_rule!r}")
        if not control_period_s > 0:
            raise ValueError("control period must be positive")
        self.action_scale_m = action_scale_m
        self.control_period_s = control_period_s
        self.stop_rule = stop_rule
        self.stop_enabled = stop_enabled
        self.stop_count = 0
        self.stopped = False
        upstream.ensure_upstream()
        from vint_train.data.data_utils import resize_and_aspect_crop

        self.resize_and_aspect_crop = resize_and_aspect_crop
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.config = upstream.model_config("vint")
        self.digest = sha256(checkpoint)
        self.model = upstream.build_model("vint")
        state = extract_state_dict(
            load_checkpoint(checkpoint, trust_checkpoint=True, expected_sha256=self.digest)
        )
        self.model.load_state_dict(state, strict=True)
        self.model.to(self.device).eval()
        self.transform = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        self.limits = BaseLimits(max_v=max_v, max_w=0.4)
        self.manifest = {
            "model": "ViNT checkpoint",
            "checkpoint": str(checkpoint),
            "sha256": self.digest,
            "strict_load": True,
            "device": self.device,
            "upstream_commit": upstream.upstream_commit(),
            "config": self.config,
            "policy_inputs": ["six chronological RGB observations", "goal RGB"],
            "nonvisual_policy_inputs": [],
            "action_scale_m": self.action_scale_m,
            "waypoint_index": 2,
            "controller": "reference_pd_twist; differential",
            "max_v": max_v,
            "max_w": 0.4,
            "control_hz": 1.0 / control_period_s,
            "pd_dt_s": control_period_s,
            "preprocessing": "official 4:3 center crop, PIL resize, ImageNet mean/std",
            "initial_history": "repeat first observation until six real control frames exist",
            "stop_rule": STOP_RULES[stop_rule] if stop_enabled else "none",
        }

    def tensor(self, images):
        from PIL import Image

        values = [
            self.resize_and_aspect_crop(Image.fromarray(image), tuple(self.config["image_size"]))
            for image in images
        ]
        values = [
            (value - value.new_tensor([0.485, 0.456, 0.406])[:, None, None])
            / value.new_tensor([0.229, 0.224, 0.225])[:, None, None]
            for value in values
        ]
        return self.torch.cat(values, dim=0).unsqueeze(0).to(self.device)

    def step(self, history, goal):
        torch = self.torch
        if self.device == "cuda":
            torch.cuda.synchronize()
        start = time.perf_counter()
        observation, goal_tensor = self.tensor(history), self.tensor([goal])
        with torch.inference_mode():
            distance, actions = self.model(observation, goal_tensor)
        waypoint = actions[0, 2].detach().cpu().numpy()
        prediction = float(distance.detach().cpu().reshape(-1)[0])
        if not np.isfinite(waypoint).all() or not np.isfinite(prediction):
            raise ValueError("nonfinite baseline prediction")
        v, w = reference_pd_twist(
            waypoint * self.action_scale_m, self.limits, PDConfig(dt=self.control_period_s)
        )
        if self.stop_enabled:
            if self.stop_rule == "project":
                close = (
                    prediction <= 1.0 and np.linalg.norm(waypoint[:2] * self.action_scale_m) <= 0.15
                )
                self.stop_count = self.stop_count + 1 if close else 0
                self.stopped = self.stopped or self.stop_count >= 3
            else:
                self.stopped = self.stopped or prediction <= 3.0
            if self.stopped:
                v, w = 0.0, 0.0
        if self.device == "cuda":
            torch.cuda.synchronize()
        return {
            "command": [v, 0.0, w],
            "predicted_distance": prediction,
            "waypoint_normalized": waypoint.tolist(),
            "policy_stop": self.stopped,
            "latency_ms": (time.perf_counter() - start) * 1000,
        }
