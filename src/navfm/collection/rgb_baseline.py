"""Released ViNT direct-image-goal baseline; policy has no simulator handles."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from navfm.control import BaseLimits, PDConfig, reference_pd_twist


class RGBBaseline:
    def __init__(self, checkpoint: Path):
        import torch
        from torchvision import transforms

        from navfm import upstream
        from navfm.models.loader import extract_state_dict, load_checkpoint, sha256

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
        self.limits = BaseLimits(max_v=0.2, max_w=0.4)
        self.manifest = {
            "model": "released ViNT",
            "checkpoint": str(checkpoint),
            "sha256": self.digest,
            "strict_load": True,
            "device": self.device,
            "upstream_commit": upstream.upstream_commit(),
            "config": self.config,
            "policy_inputs": ["six chronological RGB observations", "goal RGB"],
            "nonvisual_policy_inputs": [],
            "action_scale_m": 0.2 / 4,
            "waypoint_index": 2,
            "controller": "reference_pd_twist; differential",
            "max_v": 0.2,
            "max_w": 0.4,
            "control_hz": 4,
            "preprocessing": "PIL resize to upstream image_size, tensor, ImageNet mean/std",
            "initial_history": "repeat first observation until six real control frames exist",
            "stop_rule": "none; baseline model has no terminating action; timeout is evaluator termination",
        }

    def tensor(self, images):
        from PIL import Image

        values = [
            self.transform(Image.fromarray(image).resize(tuple(self.config["image_size"])))
            for image in images
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
        v, w = reference_pd_twist(waypoint * (0.2 / 4), self.limits, PDConfig(dt=0.25))
        if self.device == "cuda":
            torch.cuda.synchronize()
        return {
            "command": [v, 0.0, w],
            "predicted_distance": prediction,
            "waypoint_normalized": waypoint.tolist(),
            "policy_stop": False,
            "latency_ms": (time.perf_counter() - start) * 1000,
        }
