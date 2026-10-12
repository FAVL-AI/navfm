"""Hermetic exact-source/config transport binding and no-forward CPU budget guards."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ravel_fixed_graph_v1 import CANONICAL_POLICY_V2, validate_canonical_binding_v2
from ravel_fixed_graph_v1 import CONFIG as GRAPH_CONFIG
from validate_ravel_checkpoint_v2 import CONFIG, validate_protocol


@pytest.mark.parametrize("case", ["source", "asset", "config"])
def test_legacy_transport_rejects_any_changed_binding(case):
    graph = json.loads(GRAPH_CONFIG.read_text())
    policy = json.loads(CANONICAL_POLICY_V2.read_text())
    effective = copy.deepcopy(policy["effective_config"])
    if case == "source":
        graph["sources"]["lightglue"]["sha256"] = "0" * 64
    elif case == "asset":
        graph["weights"]["superpoint_lightglue.pth"]["sha256"] = "0" * 64
    else:
        effective["n_layers"] = 10
    with pytest.raises(ValueError, match="binding mismatch"):
        validate_canonical_binding_v2(graph, effective, policy)


def test_legacy_transport_cannot_expand_unused_key_removal():
    graph = json.loads(GRAPH_CONFIG.read_text())
    policy = json.loads(CANONICAL_POLICY_V2.read_text())
    policy["legacy_keys"].append("other_unused")
    with pytest.raises(ValueError, match="policy changed"):
        validate_canonical_binding_v2(graph, policy["effective_config"], policy)


@pytest.mark.parametrize(
    "key", ["forwards", "GPU_calls", "constructor_attempts", "worker_cpu_wall_s"]
)
def test_canonical_cpu_validation_cannot_expand_budget(key):
    cfg = json.loads(CONFIG.read_text())
    cfg["caps"][key] += 1
    with pytest.raises(ValueError, match="validation budget"):
        validate_protocol(cfg)
