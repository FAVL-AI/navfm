"""Low-level yaw-rate tracking for the articulated sphere-wheel proxy.

The open-loop wheel map realises only a fraction of small turn commands while
driving forward (docs/ARRIVAL_RESEARCH_DECISION.md, controller re-audit). This
PI loop closes on the measured body yaw rate, the quantity an on-board gyro
reports. It is a base-controller input only: it never reaches the policy, and
it uses no pose, map or goal information.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class YawRateGains:
    feedforward: float = 1.0
    kp: float = 1.0
    ki: float = 4.0
    integral_limit: float = 0.5
    output_limit: float = 1.5


class YawRateTracker:
    """Return the wheel-differential yaw term for a commanded body yaw rate."""

    def __init__(self, gains: YawRateGains = YawRateGains()):
        if gains.integral_limit < 0 or gains.output_limit <= 0:
            raise ValueError("limits must be non-negative and the output limit positive")
        self.gains = gains
        self.integral = 0.0

    def reset(self) -> None:
        self.integral = 0.0

    def update(self, w_cmd: float, w_measured: float, dt: float) -> float:
        if not dt > 0:
            raise ValueError("dt must be positive")
        if not (math.isfinite(w_cmd) and math.isfinite(w_measured)):
            raise ValueError("nonfinite yaw rate")
        g = self.gains
        if w_cmd == 0.0:
            # A zero command is a stop or straight segment: no stored turn effort.
            self.integral = 0.0
        error = w_cmd - w_measured
        self.integral = max(-g.integral_limit, min(g.integral_limit, self.integral + error * dt))
        out = g.feedforward * w_cmd + g.kp * error + g.ki * self.integral
        return max(-g.output_limit, min(g.output_limit, out))
