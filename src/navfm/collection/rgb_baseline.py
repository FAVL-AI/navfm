"""Released ViNT direct-image-goal baseline; policy has no simulator handles."""

from __future__ import annotations

import dataclasses
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


class RGBTopomapBaseline(RGBBaseline):
    """ViNT navigating a route of reference images (upstream topological map).

    The chain is the prior traversal's frames; localisation and node choice come
    only from the distance head on camera images (navfm.collection.topomap).
    Final arrival latches a stop when the goal node is reached; chain progress
    is logged per decision and never itself ends the episode.
    """

    def __init__(
        self,
        checkpoint: Path,
        *,
        radius: int = 4,
        close_threshold: float = 3.0,
        bounded=None,
        verify_threshold: float | None = None,
        verify_persistence: int = 2,
        confirmation=None,
        recovery=None,
        scan_rate: float = 0.4,
        approach_steering: bool = True,
        initial_node: int = 0,
        start_lost: bool = False,
        **kw,
    ):
        from navfm.collection.topomap import (
            BoundedTopomapState,
            RecoveringTopomapState,
            TopomapConfig,
            TopomapState,
        )

        kw.setdefault("stop_enabled", True)
        super().__init__(checkpoint, **kw)
        if verify_threshold is not None and not (verify_threshold > 0 and verify_persistence >= 1):
            raise ValueError("verification needs a positive threshold and persistence >= 1")
        self.chain: list = []
        self.topomap_cfg = TopomapConfig(radius=radius, close_threshold=close_threshold)
        self.bounded = bounded
        self.state_cls = TopomapState if bounded is None else BoundedTopomapState
        self.verify_threshold = verify_threshold
        self.verify_persistence = verify_persistence
        # v2 components (component_comparison_v2); None keeps the v1 code path.
        if confirmation is not None and verify_threshold is not None:
            raise ValueError("choose the v1 check or the v2 confirmation, not both")
        if recovery is not None and bounded is None:
            raise ValueError("recovery replaces the bounded lost state; it needs bounded")
        if start_lost and bounded is None:
            raise ValueError("a lost start needs a lost state")
        if recovery is not None and not 0 < abs(scan_rate) <= self.limits.max_w:
            raise ValueError("scan rate must be nonzero and within the angular limit")
        if recovery is not None:
            self.state_cls = RecoveringTopomapState
        self.confirmation = confirmation
        self.recovery = recovery
        self.scan_rate = scan_rate
        self.approach_steering = approach_steering
        self.initial_node = initial_node
        self.start_lost = start_lost
        arrival = "latched stop when closest_node == goal_node"
        if confirmation is not None:
            arrival = (
                "latched stop only when the requested-goal confirmation state confirms "
                "(approach latched at the first chain end; votes <= threshold; "
                f"{confirmation.votes} of the last {confirmation.window}; abstain after "
                f"{confirmation.approach_budget} approach decisions)"
            )
            arrival += (
                "; in approach the robot steers by the requested goal"
                if approach_steering
                else "; steering as v1 (requested goal only on chain-end decisions)"
            )
        if verify_threshold is not None:
            arrival += (
                f" AND requested-goal distance <= {verify_threshold} on "
                f"{verify_persistence} consecutive decisions"
            )
        self.manifest.update(
            policy_inputs=[
                "six chronological RGB observations",
                "route of reference RGB images",
                "requested goal RGB image (verification only)"
                if verify_threshold is not None or confirmation is not None
                else "requested goal RGB image (logged, unused)",
            ],
            stop_rule=arrival if self.stop_enabled else "none",
            topomap={
                "radius": radius,
                "close_threshold": close_threshold,
                "bounded": None if bounded is None else dataclasses.asdict(bounded),
                "verify_threshold": verify_threshold,
                "verify_persistence": verify_persistence if verify_threshold is not None else None,
                "confirmation": None if confirmation is None else dataclasses.asdict(confirmation),
                "recovery": None if recovery is None else dataclasses.asdict(recovery),
                "scan_rate": scan_rate if recovery is not None else None,
                "approach_steering": approach_steering if confirmation is not None else None,
                # The effective initial node is per episode (manifest["topomap"]), not here.
                "start_lost": start_lost,
            },
        )

    def set_chain(self, chain):
        if len(chain) < 2:
            raise ValueError("a route of reference images needs at least two nodes")
        self.chain = [np.asarray(c) for c in chain]
        self.reset_chain()

    def reset_chain(self):
        from navfm.collection.arrival_confirmation import ConfirmationState

        kw = {} if self.bounded is None else {"bounded": self.bounded}
        if self.recovery is not None:
            kw["recovery"] = self.recovery
        goal_node = len(self.chain) - 1
        if not 0 <= self.initial_node <= goal_node:
            raise ValueError("initial node outside the chain")
        self.state = self.state_cls(goal_node=goal_node, closest_node=self.initial_node, **kw)
        if self.start_lost:
            self.state.lost = True
            if self.recovery is not None:
                self.state.attempts = 1
        self.stopped = False
        self.abstained = None
        self.verified_count = 0
        self.chain_reached_decisions = 0
        self.confirm = None if self.confirmation is None else ConfirmationState(self.confirmation)

    def step(self, history, goal=None):
        torch = self.torch
        if self.device == "cuda":
            torch.cuda.synchronize()
        begin = time.perf_counter()
        start, end = self.state.window(self.topomap_cfg)
        nodes = self.chain[start : end + 1]
        images = nodes + ([goal] if goal is not None else [])
        obs = self.tensor(history).repeat(len(images), 1, 1, 1)
        goals = torch.cat([self.tensor([n]) for n in images], dim=0)
        with torch.inference_mode():
            distance, actions = self.model(obs, goals)
        d_all = np.asarray(distance.detach().cpu().numpy(), float).reshape(-1)
        d = d_all[: len(nodes)]
        requested = float(d_all[-1]) if goal is not None else None
        v2 = self.confirmation is not None or self.recovery is not None
        if v2 and (self.stopped or self.abstained):
            # v2 terminal: nothing further is decided; the robot is held still.
            # (The v1 path keeps updating after a stop, as recorded in v1.)
            return self._terminal_record(d, requested, begin)
        follow = self.state.update(d, self.topomap_cfg)
        waypoint = actions[follow, 2].detach().cpu().numpy()
        if v2:
            return self._step_v2(d, requested, actions, follow, waypoint, len(nodes), begin)
        verification = None
        if self.state.reached_goal:
            self.chain_reached_decisions += 1
            if self.verify_threshold is not None:
                if requested is None:
                    raise ValueError("verification needs the requested goal image")
                self.verified_count = (
                    self.verified_count + 1 if requested <= self.verify_threshold else 0
                )
                accepted = self.verified_count >= self.verify_persistence
                verification = "accepted" if accepted else "pending"
                if not accepted:
                    # Chain exhausted but arrival unverified: steer to the requested goal.
                    waypoint = actions[len(nodes), 2].detach().cpu().numpy()
        else:
            self.verified_count = 0
        if not np.isfinite(waypoint).all():
            raise ValueError("nonfinite baseline prediction")
        v, w = reference_pd_twist(
            waypoint * self.action_scale_m, self.limits, PDConfig(dt=self.control_period_s)
        )
        arrived = self.state.reached_goal and (
            self.verify_threshold is None or verification == "accepted"
        )
        if self.stop_enabled and arrived:
            self.stopped = True
        if self.stopped:
            v, w = 0.0, 0.0
        if self.device == "cuda":
            torch.cuda.synchronize()
        return {
            "command": [v, 0.0, w],
            "predicted_distance": float(d[follow]),
            "window_distances": d.tolist(),
            "requested_goal_distance": requested,
            "verification": verification,
            "chain_reached_decisions": self.chain_reached_decisions,
            "waypoint_normalized": waypoint.tolist(),
            "policy_stop": self.stopped,
            "chain": dict(self.state.history[-1]),
            "latency_ms": (time.perf_counter() - begin) * 1000,
        }

    def _step_v2(self, d, requested, actions, follow, waypoint, n_nodes, begin):
        """v2 decision: explicit recovery scan and/or requested-goal confirmation."""
        torch = self.torch
        scan = False
        confirmation = None
        if self.state.reached_goal:
            self.chain_reached_decisions += 1
        if self.recovery is not None and self.state.recovery_failed:
            self.abstained = "recovery_failed"
        elif self.recovery is not None and self.state.scanning:
            scan = True
        if self.confirm is not None and not self.abstained:
            if requested is None:
                raise ValueError("confirmation needs the requested goal image")
            confirmation = self.confirm.update(
                self.state.reached_goal, requested, paused=bool(getattr(self.state, "lost", False))
            )
            if (
                confirmation["phase"] == "approach"
                and not scan
                and (self.approach_steering or self.state.reached_goal)
            ):
                # V2b: steer to the requested goal throughout the approach phase.
                # V2a (approach_steering False): only on chain-end decisions, as v1.
                waypoint = actions[n_nodes, 2].detach().cpu().numpy()
            elif confirmation["phase"] == "abstained":
                self.abstained = "confirmation_budget"
        if not np.isfinite(waypoint).all():
            raise ValueError("nonfinite baseline prediction")
        v, w = reference_pd_twist(
            waypoint * self.action_scale_m, self.limits, PDConfig(dt=self.control_period_s)
        )
        if scan:
            v, w = 0.0, self.scan_rate
        if self.confirm is not None:
            arrived = confirmation is not None and confirmation["phase"] == "confirmed"
        else:
            arrived = self.state.reached_goal
        if self.stop_enabled and arrived and not self.abstained:
            self.stopped = True
        if self.stopped or self.abstained:
            v, w = 0.0, 0.0
        if self.device == "cuda":
            torch.cuda.synchronize()
        return {
            "command": [v, 0.0, w],
            "predicted_distance": float(d[follow]),
            "window_distances": d.tolist(),
            "requested_goal_distance": requested,
            "verification": None,
            "confirmation": confirmation,
            "scan": scan,
            "chain_reached_decisions": self.chain_reached_decisions,
            "waypoint_normalized": waypoint.tolist(),
            "policy_stop": self.stopped,
            "policy_abstain": self.abstained,
            "chain": dict(self.state.history[-1]),
            "latency_ms": (time.perf_counter() - begin) * 1000,
        }

    def _terminal_record(self, d, requested, begin):
        return {
            "command": [0.0, 0.0, 0.0],
            "predicted_distance": float(np.min(d)),
            "window_distances": d.tolist(),
            "requested_goal_distance": requested,
            "verification": None,
            "confirmation": None,
            "scan": False,
            "chain_reached_decisions": self.chain_reached_decisions,
            "waypoint_normalized": [0.0, 0.0],
            "policy_stop": self.stopped,
            "policy_abstain": self.abstained,
            "chain": dict(self.state.history[-1]) if self.state.history else {},
            "latency_ms": (time.perf_counter() - begin) * 1000,
        }


def topomap_components(spec: dict, *, start_lost: bool = False) -> dict:
    """Constructor arguments for a frozen comparison variant (v1 or v2 spec).

    Every variant receives start_lost, so a lost start can never be silently
    dropped for a v1-shaped variant.
    """
    from navfm.collection.arrival_confirmation import ConfirmationConfig
    from navfm.collection.topomap import BoundedConfig, RecoveryConfig

    out = {
        "bounded": BoundedConfig(**spec["bounded"]) if spec["bounded"] else None,
        "verify_threshold": spec["verify_threshold"],
        "verify_persistence": spec["verify_persistence"],
        "start_lost": bool(start_lost),
    }
    if spec.get("confirmation"):
        out["confirmation"] = ConfirmationConfig(**spec["confirmation"])
        out["approach_steering"] = bool(spec.get("approach_steering", True))
    if spec.get("recovery"):
        out["recovery"] = RecoveryConfig(**spec["recovery"])
        out["scan_rate"] = spec.get("scan_rate", 0.4)
    return out
