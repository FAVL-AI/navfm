"""Hermetic saved graph identity and bounded replay rejection controls."""

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from replay_saved_graph_ulvn_v1 import CONFIG, SavedGraphULVN, validate_map, validate_protocol


def nodes():
    return [dict(frame=i * 4, path=f"{i * 4}.jpg", sha256="a" * 64) for i in range(8)]


def test_admitted_numeric_order():
    validate_map(nodes(), nodes(), np.zeros((8, 8), dtype=np.int32))


@pytest.mark.parametrize(
    "kind", ["reorder", "duplicate", "dtype", "asymmetric", "diagonal", "negative"]
)
def test_invalid_map_rejected(kind):
    n = nodes()
    ref = nodes()
    g = np.zeros((8, 8), dtype=np.int32)
    if kind == "reorder":
        n.reverse()
    elif kind == "duplicate":
        n[1]["path"] = n[0]["path"]
        ref = copy.deepcopy(n)
    elif kind == "dtype":
        g = g.astype(np.uint16)
    elif kind == "asymmetric":
        g[0, 1] = 2
    elif kind == "diagonal":
        g[0, 0] = 1
    elif kind == "negative":
        g[0, 1] = g[1, 0] = -1
    with pytest.raises(ValueError):
        validate_map(n, ref, g)


@pytest.mark.parametrize("kind", ["goal", "query", "resets", "budget"])
def test_frozen_selection_rejected(kind):
    c = json.loads(CONFIG.read_text())
    if kind == "goal":
        c["goal_node"] = 0
    elif kind == "query":
        c["query_frames"].reverse()
    elif kind == "resets":
        c["repetitions"] = 3
    else:
        c["caps"]["neural_model_calls"] = 1
    with pytest.raises(ValueError):
        validate_protocol(c)


def test_stale_episode_rejects_before_native_state():
    obj = SavedGraphULVN(None, None, np.ones((8, 8448)), np.zeros((8, 8)), np.ones(8448))
    with pytest.raises(ValueError, match="stale"):
        obj.step(np.zeros(8448, dtype=np.float32), "stale", 0)
