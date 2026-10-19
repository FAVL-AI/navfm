"""Harmless model substitutes for driving history_runner.py in TEST mode on CPU.
None of them loads weights, touches the checkpoint, or uses a GPU."""
import os
import time

import torch
from torch import nn


class Ok(nn.Module):
    """Deterministic function of the inputs, shaped like ViNT's (distance, actions)."""

    def forward(self, obs, goals):
        d = (obs.mean(dim=(1, 2, 3)) - goals.mean(dim=(1, 2, 3))).abs().unsqueeze(1) * 10.0
        return d, torch.zeros(obs.shape[0], 5, 4)


class _Counting(Ok):
    def __init__(self):
        super().__init__()
        self.n = 0


class Slow(Ok):
    def forward(self, obs, goals):
        time.sleep(10_000)
        return super().forward(obs, goals)


class Crash(_Counting):
    def forward(self, obs, goals):
        self.n += 1
        if self.n == 3:
            os._exit(7)
        return super().forward(obs, goals)


class Unlisted(_Counting):
    """Issues one extra, unlisted forward through the module call path at its third call."""

    def forward(self, obs, goals):
        self.n += 1
        if self.n == 3:
            self(obs, goals)
        return super().forward(obs, goals)


class NaN(_Counting):
    def forward(self, obs, goals):
        self.n += 1
        d, a = super().forward(obs, goals)
        if self.n == 2:
            d = d * float("nan")
        return d, a


class SlowIgnoringAlarm(Ok):
    """Disables the worker's SIGALRM self-limit so only the supervisor deadline can stop it."""

    def forward(self, obs, goals):
        import signal

        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        time.sleep(10_000)
        return super().forward(obs, goals)


class OrderSensitive(nn.Module):
    """Weights every input channel by its index, so any reordering of history frames or batch
    rows changes the output."""

    def forward(self, obs, goals):
        w_obs = torch.arange(1, obs.shape[1] + 1, dtype=obs.dtype).view(1, -1, 1, 1)
        w_goal = torch.arange(1, goals.shape[1] + 1, dtype=goals.dtype).view(1, -1, 1, 1)
        d = (obs * w_obs).mean(dim=(1, 2, 3)) - (goals * w_goal).mean(dim=(1, 2, 3))
        d = d + torch.arange(obs.shape[0], dtype=obs.dtype) * 1e-3 * goals.mean(dim=(1, 2, 3))
        return d.unsqueeze(1), torch.zeros(obs.shape[0], 5, 4)
