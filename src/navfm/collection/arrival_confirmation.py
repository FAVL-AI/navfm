"""Requested-goal confirmation state (component_comparison_v2, replaces the v1 check).

The v1 check counted requested-goal evidence only on decisions where the chain's
reached flag was also true, and reset on any other decision. On mismatched
chains the flag alternated, so in-region evidence was discarded (v1 results).

This state separates three things:

- Eligibility. The approach phase latches the first time the chain reports its
  end (reached flag). It does not unlatch when the flag falls back.
- Evidence. In the approach phase each decision casts one vote: requested-goal
  distance <= threshold. Votes expire after `window` decisions. Arrival is
  confirmed when at least `votes` of the last `window` eligible decisions voted.
- Termination. CONFIRMED is the only arrival. A pause (lost localisation)
  clears the votes and neither counts toward nor consumes the approach budget.
  ABSTAINED is a terminal non-arrival: the approach budget ran out without
  confirmation. The episode budget is enforced by the caller and is separate.

Inputs are model outputs only (chain flag, requested-goal distance, paused
flag); no pose enters.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

TRACKING, APPROACH, CONFIRMED, ABSTAINED = "tracking", "approach", "confirmed", "abstained"


@dataclass(frozen=True)
class ConfirmationConfig:
    threshold: float
    votes: int = 2
    window: int = 4
    approach_budget: int = 40

    def __post_init__(self):
        if not self.threshold > 0:
            raise ValueError("threshold must be positive")
        if not 1 <= self.votes <= self.window:
            raise ValueError("need 1 <= votes <= window")
        if self.approach_budget < self.window:
            raise ValueError("approach budget shorter than the evidence window")


@dataclass
class ConfirmationState:
    config: ConfirmationConfig
    phase: str = TRACKING
    approach_decisions: int = 0
    first_approach_decision: int | None = None
    decisions: int = 0
    _recent: deque = field(default_factory=deque)

    @property
    def terminal(self) -> bool:
        return self.phase in (CONFIRMED, ABSTAINED)

    def update(self, chain_reached: bool, requested_distance: float, paused: bool = False) -> dict:
        """Apply one decision; returns the per-decision record."""
        k = self.decisions
        self.decisions += 1
        vote = None
        if not self.terminal:
            if paused:
                self._recent.clear()
            else:
                if self.phase == TRACKING and chain_reached:
                    self.phase = APPROACH
                    self.first_approach_decision = k
                if self.phase == APPROACH:
                    vote = bool(requested_distance <= self.config.threshold)
                    self._recent.append(vote)
                    while len(self._recent) > self.config.window:
                        self._recent.popleft()
                    self.approach_decisions += 1
                    if sum(self._recent) >= self.config.votes:
                        self.phase = CONFIRMED
                    elif self.approach_decisions >= self.config.approach_budget:
                        self.phase = ABSTAINED
        return {
            "phase": self.phase,
            "vote": vote,
            "votes_in_window": int(sum(self._recent)),
            "approach_decisions": self.approach_decisions,
            "paused": bool(paused),
        }
