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


@dataclass(frozen=True)
class BoundedConfig:
    """Bounded temporal localisation with a lost state (not upstream; a repair).

    - A proposed change of more than one node, or any backward move, is
      accepted only if proposed on `persistence` consecutive decisions, and then
      by at most `max_jump` nodes. Smaller forward changes follow upstream.
    - Lost: the window's minimum distance exceeds `lost_enter` on `lost_patience`
      consecutive decisions. While lost, every node is scored, the robot follows
      the global argmin node, the current node is frozen and the goal cannot be
      reached. Recovery: a global minimum <= `lost_exit` at the same node (+/-1)
      on `persistence` consecutive decisions relocalises to that node.
    """

    max_jump: int = 2
    persistence: int = 2
    lost_enter: float = 12.0
    lost_exit: float = 8.0
    lost_patience: int = 3

    def __post_init__(self):
        if self.max_jump < 1 or self.persistence < 1 or self.lost_patience < 1:
            raise ValueError("jump, persistence and patience must be >= 1")
        if not 0 < self.lost_exit <= self.lost_enter:
            raise ValueError("need 0 < lost_exit <= lost_enter")


@dataclass
class BoundedTopomapState(TopomapState):
    bounded: BoundedConfig = field(default_factory=BoundedConfig)
    lost: bool = False
    _far: int = 0
    _pending: list = field(default_factory=list)

    def window(self, cfg: TopomapConfig) -> tuple[int, int]:
        if self.lost:
            return 0, self.goal_node
        return super().window(cfg)

    def _persistent(self, node: int) -> bool:
        self._pending = [*self._pending, node][-self.bounded.persistence :]
        return len(self._pending) == self.bounded.persistence and all(
            abs(p - node) <= 1 for p in self._pending
        )

    def update(self, distances, cfg: TopomapConfig) -> int:
        start, end = self.window(cfg)
        d = np.asarray(distances, float)
        if d.shape != (end - start + 1,) or not np.isfinite(d).all():
            raise ValueError("one finite distance per window node required")
        b = self.bounded
        idx = int(np.argmin(d))
        argmin_node = start + idx
        event = "track"
        if self.lost:
            follow = idx
            if d[idx] > b.lost_exit:
                self._pending = []  # persistence means consecutive matches
            if d[idx] <= b.lost_exit and self._persistent(argmin_node):
                self.lost, self._far, self._pending = False, 0, []
                self.closest_node = min(argmin_node, self.goal_node)
                event = "recovered"
            else:
                event = "lost"
        else:
            self._far = self._far + 1 if d[idx] > b.lost_enter else 0
            if self._far >= b.lost_patience:
                self.lost, self._pending = True, []
                follow = idx
                event = "lost_entered"
            else:
                # Upstream proposal, then bounded.
                if d[idx] > cfg.close_threshold:
                    follow, proposed = idx, argmin_node
                else:
                    follow, proposed = (
                        min(idx + 1, len(d) - 1),
                        min(argmin_node + 1, self.goal_node),
                    )
                step = proposed - self.closest_node
                if 0 <= step <= 1:
                    self.closest_node, self._pending = proposed, []
                elif self._persistent(proposed):
                    self.closest_node += int(np.clip(step, -b.max_jump, b.max_jump))
                    self._pending = []
                    # Steer along the chain from the capped node, never to the raw argmin.
                    follow = int(np.clip(self.closest_node + 1, start, end)) - start
                    event = "bounded_jump"
                else:
                    # Unconfirmed jump: hold the node, follow the next node on the chain.
                    follow = min(self.closest_node + 1, end) - start
                    event = "jump_withheld"
        self.reached_goal = (not self.lost) and self.closest_node == self.goal_node
        self.history.append(
            {
                "window": [start, end],
                "argmin_node": argmin_node,
                "argmin_distance": float(d[idx]),
                "followed_node": start + follow,
                "closest_node": self.closest_node,
                "reached_goal": self.reached_goal,
                "lost": self.lost,
                "event": event,
            }
        )
        return follow


@dataclass(frozen=True)
class RecoveryConfig:
    """Explicit lost-state recovery (component_comparison_v2; replaces the v1 lost behaviour).

    Entry is unchanged (BoundedConfig.lost_enter on lost_patience decisions).
    While lost the robot does not translate: the caller rotates it in place at a
    fixed rate, so new evidence comes from new headings at the same place. Every
    node is scored each decision. Relocalisation: the global argmin distance is
    <= `exit` on `persistence` consecutive decisions at the same node (+/-1);
    the current node becomes that node. An attempt that has not relocalised after
    `scan_budget` decisions fails; a failed attempt, or more than `max_attempts`
    lost entries in an episode, is terminal (recovery_failed): a non-arrival halt.
    """

    exit: float
    persistence: int = 2
    scan_budget: int = 36
    max_attempts: int = 2

    def __post_init__(self):
        if not self.exit > 0 or self.persistence < 1 or self.scan_budget < self.persistence:
            raise ValueError("need exit > 0, persistence >= 1, scan budget >= persistence")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")


@dataclass
class RecoveringTopomapState(BoundedTopomapState):
    recovery: RecoveryConfig = field(default_factory=lambda: RecoveryConfig(exit=6.0))
    recovery_failed: bool = False
    attempts: int = 0
    _scan: int = 0

    @property
    def scanning(self) -> bool:
        return self.lost and not self.recovery_failed

    def update(self, distances, cfg: TopomapConfig) -> int:
        if self.recovery_failed:
            raise ValueError("recovery failed; the episode has ended")
        if not self.lost:
            follow = super().update(distances, cfg)
            if self.lost:  # entered on this decision
                self.attempts += 1
                self._scan = 0
                if self.attempts > self.recovery.max_attempts:
                    self.recovery_failed = True
                    self.history[-1]["event"] = "recovery_failed"
                self.history[-1]["attempt"] = self.attempts
            return follow
        start, end = self.window(cfg)
        d = np.asarray(distances, float)
        if d.shape != (end - start + 1,) or not np.isfinite(d).all():
            raise ValueError("one finite distance per window node required")
        idx = int(np.argmin(d))
        argmin_node = start + idx
        self._scan += 1
        r = self.recovery
        # Consecutive matches only: any decision above the exit threshold resets.
        self._pending = [*self._pending, argmin_node][-r.persistence :] if d[idx] <= r.exit else []
        if len(self._pending) == r.persistence and all(
            abs(p - argmin_node) <= 1 for p in self._pending
        ):
            self.lost, self._far, self._pending = False, 0, []
            self.closest_node = min(argmin_node, self.goal_node)
            event = "relocalised"
        else:
            event = "scan"
            if self._scan >= r.scan_budget:
                self.recovery_failed = True
                event = "recovery_failed"
        # A recovery decision is never an arrival; arrival needs a tracking decision.
        self.reached_goal = False
        self.history.append(
            {
                "window": [start, end],
                "argmin_node": argmin_node,
                "argmin_distance": float(d[idx]),
                "followed_node": argmin_node,
                "closest_node": self.closest_node,
                "reached_goal": self.reached_goal,
                "lost": self.lost,
                "event": event,
                "attempt": self.attempts,
                "scan_decisions": self._scan,
            }
        )
        return idx
