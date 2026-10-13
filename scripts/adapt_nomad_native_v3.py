"""Unchanged native NoMaD objective with the authenticated EMA integration adapter."""

from adapt_nomad_native_v1 import (
    build as build,
)
from adapt_nomad_native_v1 import (
    loss as loss,
)
from adapt_nomad_native_v1 import (
    normalized_actions as normalized_actions,
)
from adapt_nomad_native_v1 import (
    predict as predict,
)
from adapt_nomad_native_v1 import (
    scheduler as scheduler,
)
from native_ema_integration_v3 import authenticated_ema_class


def make_ema(model, binding):
    cls = authenticated_ema_class(binding)
    return cls(model.parameters(), power=0.75, use_ema_warmup=True)
