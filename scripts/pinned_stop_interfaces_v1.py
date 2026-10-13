"""Authenticated native belief/arrival components with synthetic descriptor I/O only."""

from __future__ import annotations

import ast
import hashlib
import heapq
import json
import re
import sys
import types
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np

SOURCE_PINS = {
    "placenav": "633313be0665694d7ac5e95f5f6965e624245c83a44693bf1df4cfcc5569f5bc",
    "placenav_terminal": "9d026407dd9eb05bcf802794a7ff69e62a5d0a06d3a3a3d5ec18d8cd2c3c94b6",
    "ulvn": "1dfaa83a55c16741a818c30c9cbb9c9b1839e8fc868b6493e23bd0c9322601c3",
}

CONFIG = Path(__file__).resolve().parents[1] / "configs/eval/stop_interface_qualification_v1.json"

CONFIG_SHA256 = "599ec7dd33403a28e7cff537ca37008a45d5e552adfc0e0ce0519e618019cd8c"


def validate_configuration(cfg):
    raw = CONFIG.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONFIG_SHA256 or json.dumps(
        cfg, sort_keys=True, allow_nan=False
    ) != json.dumps(json.loads(raw), sort_keys=True, allow_nan=False):
        raise ValueError("versioned technical configuration drift")


def authenticated_module(kind, path, spec):
    """Execute allowlisted AST definitions, never imports or a native ROS program."""
    if spec["sha256"] != SOURCE_PINS[kind]:
        raise ValueError("unapproved native source digest")
    raw = Path(path).read_bytes()
    blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if hashlib.sha256(raw).hexdigest() != spec["sha256"] or blob != spec["git_blob_sha1"]:
        raise ValueError("native source hash/blob identity mismatch")
    parsed = ast.parse(raw, filename=str(path))
    allowed = {
        "placenav": {"PlaceRecognitionTopologicalFilter"},
        "ulvn": {
            "PlaceRecognition",
            "safe_cosine_distance",
            "safe_obs_likelihood",
            "PlanState",
            "BeliefAwareSubgoalSearch",
        },
    }[kind]
    nodes = [
        n
        for n in parsed.body
        if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in allowed
    ]
    if {n.name for n in nodes} != allowed or len(nodes) != len(allowed):
        raise ValueError("native definition allowlist incomplete or duplicated")
    name = f"navfm_native_{kind}_{spec['sha256'][:12]}"
    module = types.ModuleType(name)
    module.__dict__.update(
        np=np, heapq=heapq, deque=deque, dataclass=dataclass, PlaceRecognitionDBHandler=DescriptorDB
    )
    sys.modules[name] = module
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    tree = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


def native_arrival_rule(kind, path, spec):
    """Retain the exact source expression/conjunction; publication/actuation is absent."""
    pin = "placenav_terminal" if kind == "placenav" else "ulvn"
    if spec["sha256"] != SOURCE_PINS[pin]:
        raise ValueError("unapproved native terminal source")
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        raise ValueError("native terminal source mismatch")
    parsed = ast.parse(raw)
    if kind == "placenav":
        matches = [
            n.value
            for n in ast.walk(parsed)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "reached_goal" for t in n.targets)
            and ast.unparse(n.value) == "closest_node_idx == args.goal_node_idx"
        ]
        if len(matches) != 1:
            raise ValueError("native PlaceNav arrival expression absent or ambiguous")
        args = ["closest_node_idx", "args"]
        body = [ast.Return(matches[0])]
    else:
        matches = [
            n
            for n in ast.walk(parsed)
            if isinstance(n, ast.If)
            and ast.unparse(n.test) == "subgoal_idx == goal_idx and current_idx == goal_idx"
        ]
        if (
            len(matches) != 1
            or len(matches[0].body) != 1
            or ast.unparse(matches[0].body[0]) != "goal_reached = True"
        ):
            raise ValueError("native ULVN arrival conjunction/latch absent or ambiguous")
        args = ["subgoal_idx", "goal_idx", "current_idx", "goal_reached"]
        body = [matches[0], ast.Return(ast.Name(id="goal_reached", ctx=ast.Load()))]
    function = ast.FunctionDef(
        name="arrival",
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=a) for a in args],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=body,
        decorator_list=[],
    )
    tree = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace["arrival"]


class DescriptorTensor:
    def __init__(self, descriptor):
        self.descriptor = descriptor

    def numpy(self):
        return self.descriptor.copy()


class DescriptorDB:
    """Explicit synthetic replacement for database I/O; not a VPR implementation."""

    def __init__(self, descriptors, unused_images):
        self.descriptors = np.array(descriptors, copy=True)

    def get_descriptors(self):
        return self.descriptors.copy()


class PinnedStopInterface:
    """Descriptor/arrival interface. A STOP proposal never commands a controller."""

    def __init__(
        self,
        kind,
        source_paths,
        cfg,
        reference_ids,
        rgb_hashes,
        descriptors,
        graph,
        goal_id,
        goal_hash,
    ):
        validate_configuration(cfg)
        if kind not in {"placenav", "ulvn"}:
            raise ValueError("unknown comparator")
        self.kind, self.cfg = kind, cfg
        admitted = validate_reference(
            cfg, reference_ids, rgb_hashes, descriptors, graph, goal_id, goal_hash
        )
        self.__dict__.update(admitted.__dict__)
        spec = cfg["sources"][kind]
        self.native = authenticated_module(kind, source_paths[kind], spec["belief"])
        self.arrival = native_arrival_rule(kind, source_paths[kind + "_terminal"], spec["terminal"])
        self.reset("unstarted")

    def _descriptor_domain(self, x):
        if x.dtype not in (np.dtype("float32"), np.dtype("float64")):
            raise ValueError("native float32/float64 dtype required; no implicit conversion")
        if not np.isfinite(x).all() or not np.allclose(
            np.linalg.norm(x, axis=-1), 1.0, rtol=0, atol=1e-6
        ):
            raise ValueError("finite normalized descriptors required; no adapter normalization")

    def reset(self, episode_id):
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError("explicit episode identity required")
        self.episode_id, self.sequence, self.time = episode_id, -1, None
        self.latched, self.failed, self.started = False, False, False
        self.initialized_belief = None
        if self.kind == "placenav":
            constants = self.cfg["native_constants"]["placenav"]
            self.filter = self.native.PlaceRecognitionTopologicalFilter(
                lambda q: {"global_descriptor": DescriptorTensor(q)},
                self.descriptors,
                None,
                delta=constants["delta"],
                window_lower=constants["window_lower"],
                window_upper=constants["window_upper"],
            )
            self.planner = None
        else:
            constants = self.cfg["native_constants"]["ulvn"]
            self.filter = self.native.PlaceRecognition(
                self.descriptors.copy(),
                self.graph.copy(),
                max_steps=constants["max_steps"],
                delta=constants["delta"],
            )
            self.planner = self.native.BeliefAwareSubgoalSearch(
                self.graph.copy(), self.descriptors.copy(), None
            )

    def step(self, query, *, episode_id, sequence, simulation_time):
        validate_acquisition(
            self.cfg,
            self.episode_id,
            self.sequence,
            self.time,
            episode_id,
            sequence,
            simulation_time,
        )
        if self.unsupported_goal:
            return {
                "status": "REJECT_UNSUPPORTED_GOAL",
                "native_arrival": None,
                "STOP_proposal": False,
                "belief": None,
            }
        if self.failed:
            raise ValueError("invalid native state requires explicit episode reset")
        q = np.array(query, copy=True)
        if q.dtype != self.descriptors.dtype:
            raise ValueError("query/reference floating dtype mismatch")
        if q.shape != (self.descriptors.shape[1],):
            raise ValueError("query descriptor shape mismatch")
        self._descriptor_domain(q)
        with np.errstate(all="ignore"):
            if not self.started:
                self.filter.initialize_model(q)
                self.initialized_belief = self.filter.belief.copy()
                if self.planner is not None:
                    goal, _ = self.planner.initial_localize(self.descriptors[self.goal].copy(), q)
                    if goal != self.goal:
                        self.failed = True
                        return {
                            "status": "REJECT_UNREPRESENTABLE_GOAL",
                            "native_arrival": None,
                            "STOP_proposal": False,
                            "belief": None,
                        }
                    self.planner.plan_path()
                self.started = True
            node, confidence = self.filter.match(q)
        belief = np.asarray(self.filter.belief)
        if (
            not np.isfinite(belief).all()
            or (belief < 0).any()
            or not np.isclose(
                belief.sum(),
                1.0,
                atol=max(1e-12, 8 * np.finfo(belief.dtype).eps * len(belief)),
                rtol=0,
            )
            or not np.isfinite(confidence)
        ):
            self.failed = True
            return {
                "status": "ABSTAIN_INVALID_NATIVE_BELIEF",
                "native_arrival": None,
                "STOP_proposal": False,
                "belief": None,
            }
        self.sequence, self.time = sequence, simulation_time
        subgoal = None
        if self.kind == "placenav":
            flag = bool(self.arrival(node, SimpleNamespace(goal_node_idx=self.goal)))
        else:
            subgoal = self.planner.next_subgoal(
                int(node),
                n_ahead=self.cfg["native_constants"]["ulvn"]["n_ahead"],
                replan_if_offpath=True,
            )["subgoal_idx"]
            flag = (
                self.latched
                if subgoal is None
                else bool(self.arrival(subgoal, self.goal, node, self.latched))
            )
            self.latched = flag
        return {
            "status": "SYNTHETIC_COMPONENT_ONLY",
            "MAP_node": int(node),
            "subgoal": subgoal,
            "native_arrival_state": flag,
            "native_arrival": flag if self.kind == "placenav" or subgoal is not None else None,
            "STOP_proposal": flag if self.kind == "placenav" or subgoal is not None else False,
            "controller_STOP": "BLOCKED_ADAPTATION",
            "belief": belief.copy(),
            "confidence": float(confidence),
        }


def validate_reference(cfg, reference_ids, rgb_hashes, descriptors, graph, goal_id, goal_hash):
    obj = object.__new__(PinnedStopInterface)
    obj.cfg = cfg
    obj.descriptors = np.array(descriptors, copy=True)
    obj.graph = np.array(graph, dtype=np.float64, copy=True)
    obj.ids, obj.hashes = tuple(reference_ids), tuple(rgb_hashes)
    n = len(obj.ids)
    if any(not isinstance(v, str) or not v for v in obj.ids) or any(
        not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in obj.hashes
    ):
        raise ValueError("nonempty string reference IDs and64hex RGB identities required")
    if (
        not 1 <= n <= cfg["limits"]["max_reference_nodes"]
        or len(set(obj.ids)) != n
        or len(obj.hashes) != n
    ):
        raise ValueError("bounded unique reference identity contract required")
    if (
        obj.descriptors.ndim != 2
        or obj.descriptors.shape[0] != n
        or not 1 <= obj.descriptors.shape[1] <= cfg["limits"]["max_descriptor_width"]
    ):
        raise ValueError("descriptor shape/budget mismatch")
    if obj.graph.shape != (n, n) or not np.isfinite(obj.graph).all() or (obj.graph < 0).any():
        raise ValueError("finite nonnegative weighted graph required")
    obj._descriptor_domain(obj.descriptors)
    obj.goal = obj.ids.index(goal_id) if goal_id in obj.ids else None
    obj.unsupported_goal = (
        obj.goal is None
        or obj.hashes.count(goal_hash) != 1
        or (obj.goal is not None and obj.hashes[obj.goal] != goal_hash)
    )
    return obj


def validate_acquisition(
    cfg, expected_episode, last_sequence, last_time, episode_id, sequence, simulation_time
):
    if (
        episode_id != expected_episode
        or sequence != last_sequence + 1
        or isinstance(sequence, bool)
        or not isinstance(sequence, (int, np.integer))
    ):
        raise ValueError("episode/ordered acquisition identity mismatch")
    if (
        not isinstance(simulation_time, (int, float))
        or isinstance(simulation_time, bool)
        or not np.isfinite(simulation_time)
        or simulation_time < 0
    ):
        raise ValueError("finite simulation clock required")
    if last_time is not None and not np.isclose(
        simulation_time - last_time, 0.25, rtol=0, atol=1e-9
    ):
        raise ValueError("fixed four-Hz acquisition order required")
    if sequence >= cfg["limits"]["max_observations"]:
        raise ValueError("finite inference-call budget exhausted")


def load_config():
    cfg = json.loads(CONFIG.read_text())
    validate_configuration(cfg)
    return cfg
