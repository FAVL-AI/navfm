"""RGB-only adapter with an injected command sink; no hardware transport imports."""

from __future__ import annotations

import math
import time
from collections import deque

import numpy as np


class YahboomAdapter:
    def __init__(self, policy, goal, sink, *, max_age_s=0.2):
        self.policy, self.goal, self.sink = policy, goal, sink
        self.max_age_s = max_age_s
        self.history = deque(maxlen=6)
        self.last_timestamp = None
        self.last_control = None

    def stop(self):
        self.sink([0.0, 0.0, 0.0])

    def observe(self, rgb, timestamp, now):
        start = time.perf_counter()
        if (
            not math.isfinite(timestamp)
            or not math.isfinite(now)
            or timestamp > now
            or now - timestamp > self.max_age_s
            or (self.last_timestamp is not None and timestamp <= self.last_timestamp)
        ):
            self.stop()
            raise ValueError("stale, future or nonmonotonic camera timestamp")
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
            self.stop()
            raise ValueError("expected uint8 RGB HxWx3")
        self.last_timestamp = timestamp
        if self.last_control is not None and timestamp - self.last_control < 0.25 - 1e-6:
            return None
        if self.last_control is not None and timestamp - self.last_control > 0.375:
            self.stop()
            self.history.clear()
            raise ValueError("4Hz history gap exceeded .375s")
        self.last_control = timestamp
        if not self.history:
            self.history.extend([rgb.copy() for _ in range(5)])
        self.history.append(rgb.copy())
        try:
            result = self.policy.step(list(self.history), self.goal)
            command = np.asarray(result["command"], float)
            if (
                command.shape != (3,)
                or not np.isfinite(command).all()
                or not 0 <= command[0] <= 0.2
                or command[1] != 0
                or abs(command[2]) > 0.4
            ):
                raise ValueError("invalid bounded command")
            self.sink(command.tolist())
        except Exception:
            self.stop()
            raise
        return dict(
            result,
            perception_to_submission_ms=(time.perf_counter() - start) * 1000,
            acquisition_age_s=now - timestamp,
        )
