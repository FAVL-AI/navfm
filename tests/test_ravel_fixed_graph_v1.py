"""Hermetic no-fit selection and finite-resource guards; no native graph inputs."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ravel_fixed_graph_v1 import CONFIG, validate_contract


@pytest.mark.parametrize(
    "key,value",
    [
        ("num_clusters", 2),
        ("tau", 1.0),
        ("radius", 4.0),
        ("index_type", "hnsw"),
        ("disable_ransac", True),
    ],
)
def test_native_fixed_mode_rejects_unreviewed_selection(key, value):
    cfg = json.loads(CONFIG.read_text())
    cfg["native_mode"][key] = value
    with pytest.raises(ValueError, match="fixed-mode contract"):
        validate_contract(cfg)


@pytest.mark.parametrize("key", ["pairs", "whole_worker_s"])
def test_native_graph_budget_cannot_expand_implicitly(key):
    cfg = json.loads(CONFIG.read_text())
    cfg["caps"][key] += 1
    with pytest.raises(ValueError, match="resource caps"):
        validate_contract(cfg)


def test_native_graph_duplicate_reference_identity_is_rejected():
    cfg = json.loads(CONFIG.read_text())
    cfg["references"][1]["path"] = cfg["references"][0]["path"]
    with pytest.raises(ValueError, match="duplicate reference"):
        validate_contract(cfg)


def test_native_graph_reference_order_cannot_be_reselected():
    cfg = copy.deepcopy(json.loads(CONFIG.read_text()))
    cfg["references"] = cfg["references"][::-1]
    with pytest.raises(ValueError, match="row/order"):
        validate_contract(cfg)
