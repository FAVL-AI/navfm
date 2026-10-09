"""Topological-map (route of reference images) localisation, as in upstream ViNT.

Port of the ViNT branch of the pinned upstream deployment
(third_party/visualnav-transformer@dca7981, deployment/src/navigate.py, lines
195-233): a window of nodes around the current node is scored by the distance
head; the argmin node is the localisation; if its predicted distance is within
the close threshold the robot localises to, and steers toward, the next node.
`reached_goal` is `closest_node == goal_node`.

Localisation uses only model predictions on camera images; no pose, time or
frame index enters it. Chain progress is reported separately from final
arrival, which the caller turns into a latched stop (upstream only publishes
the flag; it does not itself zero the command).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class TopomapConfig:
    radius: int = 4
    close_threshold: float = 3.0

    def __post_init__(self):
        if self.radius < 0 or not self.close_threshold > 0:
            raise ValueError("radius must be >= 0 and close threshold positive")


@dataclass
class TopomapState:
    goal_node: int
    closest_node: int = 0
    reached_goal: bool = False
    history: list = field(default_factory=list)

    def __post_init__(self):
        if self.goal_node < 0:
            raise ValueError("chain needs at least one node")

    def window(self, cfg: TopomapConfig) -> tuple[int, int]:
        """Inclusive [start, end] node indices to score (upstream start/end)."""
        start = max(self.closest_node - cfg.radius, 0)
        end = min(self.closest_node + cfg.radius + 1, self.goal_node)
        return start, end

    def update(self, distances, cfg: TopomapConfig) -> int:
        """Apply one decision; returns the node whose waypoint is followed."""
        start, end = self.window(cfg)
        d = np.asarray(distances, float)
        if d.shape != (end - start + 1,) or not np.isfinite(d).all():
            raise ValueError("one finite distance per window node required")
        idx = int(np.argmin(d))
        if d[idx] > cfg.close_threshold:
            follow = idx
            self.closest_node = start + idx
        else:
            follow = min(idx + 1, len(d) - 1)
            self.closest_node = min(start + idx + 1, self.goal_node)
        self.reached_goal = self.closest_node == self.goal_node
        self.history.append(
            {
                "window": [start, end],
                "argmin_node": start + idx,
                "argmin_distance": float(d[idx]),
                "followed_node": start + follow,
                "closest_node": self.closest_node,
                "reached_goal": self.reached_goal,
            }
        )
        return follow
