"""Bounded saved weighted graph to native ULVN belief/planner and mock STOP bridge."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from pinned_stop_interfaces_v1 import authenticated_module, native_arrival_rule
from qualify_pinned_stop_interfaces_v1 import supervise_worker, write_json
from recorded_rgb_stop_v1 import (
    MockStop,
    reject_python_network,
    validate_admission_fields,
    verify_file,
)

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "configs/eval/saved_graph_ulvn_replay_v1.json"


def validate_map(nodes, references, graph):
    if (
        nodes != references
        or len(nodes) != 8
        or [r["frame"] for r in nodes] != list(range(0, 32, 4))
    ):
        raise ValueError("saved node/reference order binding mismatch")
    if len({r["path"] for r in nodes}) != 8:
        raise ValueError("duplicate node identity")
    if graph.shape != (8, 8) or graph.dtype != np.int32 or not np.isfinite(graph).all():
        raise ValueError("saved weighted graph domain mismatch")
    if (graph < 0).any() or not np.array_equal(graph, graph.T) or np.diag(graph).any():
        raise ValueError("saved weighted graph invariant mismatch")


def validate_protocol(cfg):
    if cfg["caps"] != dict(
        worker_cpu_wall_s=30,
        parent_wall_s=60,
        raw_bytes=16777216,
        production_updates=16,
        unreachable_updates=1,
        transition_filter_objects=2,
        neural_model_calls=0,
        GPU_calls=0,
    ):
        raise ValueError("frozen CPU replay budget changed")
    if (
        cfg["goal_node"] != 7
        or cfg["query_frames"] != list(range(1, 32, 4))
        or cfg["repetitions"] != 2
    ):
        raise ValueError("fixed goal/query/reset selection changed")


def bound_json(row):
    verify_file(row["path"], row["sha256"])
    return json.loads(Path(row["path"]).read_text())


def admit(cfg):
    validate_protocol(cfg)
    for row in cfg["bindings"].values():
        verify_file(row["path"], row["sha256"])
    b = cfg["bindings"]
    result = bound_json(b["graph_result"])
    parent = bound_json(b["graph_parent"])
    if (
        result["freeze"] != cfg["graph_freeze"]
        or result["status"] != "PASS_NATIVE_FIXED_GRAPH_ONLY"
        or parent
        != dict(
            exit_code=0,
            timeout=False,
            reaped=True,
            worker_started=True,
            status="PASS",
            freeze=cfg["graph_freeze"],
        )
        or result["stats"]["technical_failures"] != 0
    ):
        raise ValueError("saved graph qualification not admitted")
    decisions = bound_json(b["pair_ledger"])
    if len(decisions) != 28 or {(r["i"], r["j"]) for r in decisions} != {
        (i, j) for i in range(8) for j in range(i + 1, 8)
    }:
        raise ValueError("saved graph pair ledger incomplete")
    rgb = bound_json(b["rgb_config"])
    rgb_result = bound_json(b["rgb_result"])
    if (
        rgb_result["freeze"] != cfg["rgb_freeze"]
        or rgb_result["encoder_forwards"] != 32
        or rgb_result["status"] != "PASS_RECORDED_ENCODER_REFERENCE_MOCK_ONLY"
        or [r["frame"] for r in rgb["queries"]] != cfg["query_frames"]
    ):
        raise ValueError("cached RGB descriptor proof mismatch")
    validate_admission_fields(rgb, bound_json(rgb["admission"]), bound_json(rgb["finalization"]))
    graph_cfg = bound_json(b["graph_config"])
    if (
        graph_cfg["references"] != rgb["references"]
        or graph_cfg["descriptor_sha256"] != b["descriptors"]["sha256"]
        or graph_cfg["descriptor_origin_freeze"] != cfg["rgb_freeze"]
        or graph_cfg["native_mode"]
        != dict(
            num_clusters=1,
            tau=0.0,
            radius=2.0,
            index_type="flat",
            metric="l2",
            binary_matrix=False,
            disable_ransac=False,
            num_threads=1,
            add_back_threshold=300,
        )
    ):
        raise ValueError("native fixed graph configuration binding mismatch")
    graph = np.load(b["pruned_graph"]["path"], allow_pickle=False)
    node_map = bound_json(b["node_map"])
    validate_map(node_map["nodes"], rgb["references"], graph)
    if (
        node_map["descriptor_sha256"] != b["descriptors"]["sha256"]
        or node_map["origin_freeze"] != cfg["rgb_freeze"]
    ):
        raise ValueError("saved graph descriptor row identity mismatch")
    with np.load(b["descriptors"]["path"], allow_pickle=False) as archive:
        refs = archive["ulvn"][:8].copy()
        queries = archive["ulvn"][8:].copy()
        goal = archive["ulvn_goal"].copy()
    for array, shape in ((refs, (8, 8448)), (queries, (8, 8448)), (goal, (8448,))):
        if array.shape != shape or array.dtype != np.float32 or not np.isfinite(array).all():
            raise ValueError("cached descriptor dtype/shape/finiteness mismatch")
        if not np.all(np.isclose(np.linalg.norm(array, axis=-1), 1, atol=1e-5, rtol=0)):
            raise ValueError("cached descriptor unit-domain mismatch")
    sources = bound_json(b["native_source_config"])["sources"]["ulvn"]
    native = authenticated_module("ulvn", sources["belief"]["local_path"], sources["belief"])
    rule = native_arrival_rule("ulvn", sources["terminal"]["local_path"], sources["terminal"])
    return native, rule, refs, queries, goal, graph


class SavedGraphULVN:
    def __init__(self, native, rule, refs, graph, goal):
        self.native, self.rule, self.refs, self.graph, self.goal = (
            native,
            rule,
            refs.copy(),
            graph.copy(),
            goal.copy(),
        )
        self.episode = None

    def reset(self, episode):
        self.episode, self.sequence, self.sticky, self.started = episode, -1, False, False
        self.filter = self.native.PlaceRecognition(
            self.refs.copy(), self.graph.copy(), max_steps=3, delta=5
        )
        self.planner = self.native.BeliefAwareSubgoalSearch(
            self.graph.copy(), self.refs.copy(), None
        )
        self.mock = MockStop()
        self.mock.reset(episode)
        self.mock.request_motion((0.1, 0), episode)
        self.mock.request_motion((0.05, 0), episode)

    def step(self, query, episode, sequence):
        if episode != self.episode or type(sequence) is not int or sequence != self.sequence + 1:
            raise ValueError("stale episode or query order")
        if query.shape != (8448,) or query.dtype != np.float32 or not np.isfinite(query).all():
            raise ValueError("query descriptor domain mismatch")
        if not np.isclose(np.linalg.norm(query), 1, atol=1e-5, rtol=0):
            raise ValueError("query descriptor norm mismatch")
        if not self.started:
            goal, start = self.planner.initial_localize(self.goal.copy(), query.copy())
            if goal != 7:
                raise ValueError("native goal identity unsupported; no forced index")
            self.initial_goal, self.initial_start = goal, start
            self.initial_path = self.planner.plan_path(edge_cost="unweighted")
            self.filter.initialize_model(query.copy())
            self.started = True
        node, confidence = self.filter.match(query.copy())
        belief = self.filter.belief.copy()
        if (
            not np.isfinite(belief).all()
            or (belief < 0).any()
            or not np.isclose(belief.sum(), 1, atol=1e-5, rtol=0)
        ):
            raise ValueError("invalid native belief; no repair")
        sub = self.planner.next_subgoal(int(node), n_ahead=2, replan_if_offpath=True)
        if sub["subgoal_idx"] is not None:
            self.sticky = bool(self.rule(sub["subgoal_idx"], 7, int(node), self.sticky))
        publication = True if self.sticky and sub["subgoal_idx"] is not None else None
        mocked = self.mock.observe(publication, episode)
        if publication is True and (
            not self.mock.latched
            or self.mock.current is not None
            or self.mock.pending
            or self.mock.target != (0, 0)
        ):
            raise ValueError("published arrival did not cancel mock motion")
        self.sequence = sequence
        return dict(
            MAP=int(node),
            confidence=float(confidence),
            posterior=belief.tolist(),
            goal_localization=self.initial_goal,
            start_localization=self.initial_start,
            initial_path=self.initial_path,
            path=sub["path"],
            subgoal=sub["subgoal_idx"],
            replanned=sub["replanned"],
            native_arrival_state=self.sticky,
            native_publication=publication,
            mock=mocked,
            mock_current=self.mock.current,
            mock_pending=self.mock.pending,
            mock_target=self.mock.target,
        )


def replay(cfg, folder, emit):
    native, rule, refs, queries, goal, graph = admit(cfg)
    adapter = SavedGraphULVN(native, rule, refs, graph, goal)
    repeats = []
    for repetition in range(2):
        episode = f"production-{repetition}"
        adapter.reset(episode)
        rows = []
        for i, query in enumerate(queries):
            row = adapter.step(query, episode, i)
            rows.append(row)
            emit(
                dict(
                    event="PRODUCTION_UPDATE",
                    episode=episode,
                    source_frame=cfg["query_frames"][i],
                    virtual_adapter_time_s=i / 4,
                    **row,
                )
            )
        repeats.append(rows)
    if repeats[0] != repeats[1]:
        raise ValueError("native reset/state isolation mismatch")
    weighted = native.PlaceRecognition(refs.copy(), graph.copy(), max_steps=3, delta=5)
    binary = native.PlaceRecognition(
        refs.copy(), (graph > 0).astype(graph.dtype), max_steps=3, delta=5
    )
    if np.allclose(weighted.transition_matrix, binary.transition_matrix):
        raise ValueError("weighted-vs-binary counterexample not exercised")
    for matrix in (weighted.transition_matrix, binary.transition_matrix):
        if (
            not np.isfinite(matrix).all()
            or (matrix < 0).any()
            or not np.allclose(matrix.sum(axis=1), 1)
        ):
            raise ValueError("invalid native transition control")
    emit(
        dict(
            event="WEIGHTED_BINARY_TRANSITION_CONTROL", changed=True, production_graph_changed=False
        )
    )
    np.save(folder / "weighted_transition.npy", weighted.transition_matrix)
    np.save(folder / "derived_binary_transition.npy", binary.transition_matrix)
    fixture = graph.copy()
    fixture[:] = 0
    np.save(folder / "derived_disconnected_fixture.npy", fixture)
    disconnected = SavedGraphULVN(native, rule, refs, fixture, goal)
    disconnected.reset("derived-unreachable")
    row = disconnected.step(queries[0], "derived-unreachable", 0)
    if (
        row["start_localization"] == 7
        or row["path"]
        or row["subgoal"] is not None
        or row["native_publication"] is not None
    ):
        raise ValueError("derived unreachable control not exercised")
    emit(dict(event="DERIVED_UNREACHABLE_CONTROL", production_graph_changed=False, **row))
    try:
        adapter.step(queries[0], "stale", 8)
    except ValueError:
        emit(dict(event="STALE_EPISODE_REJECTED"))
    else:
        raise AssertionError("stale episode accepted")
    mock = MockStop()
    mock.reset("cancel-control")
    mock.request_motion((0.1, 0), mock.episode)
    mock.request_motion((0.05, 0), mock.episode)
    mock.observe(True, mock.episode)
    mock.cancel(mock.episode)
    assert mock.latched and not mock.pending and mock.current is None and mock.target == (0, 0)
    for flag in (True, False, None):
        assert mock.observe(flag, mock.episode)["status"] == "CANCELED"
        assert mock.request_motion((0.1, 0), mock.episode) == "BLOCKED_MOCK_ONLY"
    mock.reset("fresh-control")
    assert not mock.latched and not mock.canceled
    emit(
        dict(
            event="MOCK_CANCEL_RESET_CONTROL", synthetic_publications=True, physical_actuation=False
        )
    )
    return dict(
        production_updates=16,
        native_true_publications=sum(
            row["native_publication"] is True for rows in repeats for row in rows
        ),
        mock_stop_commands=sum(
            row["mock"].get("new_mock_command") == "MOCK_STOP_ONLY" for rows in repeats for row in rows
        ),
        production_stop_path_exercised=any(
            row["native_publication"] is True for rows in repeats for row in rows
        ),
        derived_unreachable_updates=1,
        weighted_binary_counterexample=True,
        reset_parity=True,
        neural_model_calls=0,
        GPU_calls=0,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--worker", action="store_true")
    args = p.parse_args()
    cfg = json.loads(CONFIG.read_text())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != args.freeze or subprocess.check_output(["git", "status", "--porcelain"], text=True):
        raise ValueError("exact clean freeze required")
    if (
        cfg["status"] != "FROZEN_SAVED_GRAPH_ULVN_REPLAY_V1"
        or os.environ.get("CUDA_VISIBLE_DEVICES") != ""
    ):
        raise ValueError("frozen CPU-only replay required")
    folder = args.out.parent
    if args.worker:
        start = time.monotonic()
        sys.addaudithook(reject_python_network)

        def emit(row):
            with (folder / "partial.jsonl").open("a") as f:
                f.write(json.dumps(row, allow_nan=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

        try:
            stats = replay(cfg, folder, emit)
            write_json(
                args.out,
                dict(
                    status="PASS_SAVED_GRAPH_NATIVE_COMPONENT_MOCK_ONLY",
                    freeze=head,
                    stats=stats,
                    wall_s=time.monotonic() - start,
                ),
            )
            write_json(folder / "worker_status.json", dict(status="PASS", freeze=head))
        except BaseException as exc:
            write_json(
                folder / "worker_status.json",
                dict(
                    status="FAIL",
                    freeze=head,
                    exception_type=type(exc).__name__,
                    reason=str(exc)[:500],
                ),
            )
            raise SystemExit(1) from None
        return
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / "attempt.json", dict(status="STARTED", freeze=head, caps=cfg["caps"]))
    with (folder / "worker.log").open("x") as log:
        outcome = supervise_worker(
            [sys.executable, __file__, "--worker", "--freeze", head, "--out", str(args.out)],
            log,
            30,
        )
    valid = args.out.exists() and (folder / "worker_status.json").exists()
    if valid:
        valid = (
            json.loads((folder / "worker_status.json").read_text())
            == dict(status="PASS", freeze=head)
            and json.loads(args.out.read_text()).get("freeze") == head
        )
    valid = (
        valid
        and sum(f.stat().st_size for f in folder.iterdir() if f.is_file())
        <= cfg["caps"]["raw_bytes"]
    )
    outcome.update(
        status="PASS" if valid and outcome["exit_code"] == 0 and not outcome["timeout"] else "FAIL",
        freeze=head,
    )
    write_json(folder / "parent_status.json", outcome)
    print(json.dumps(outcome))
    raise SystemExit(0 if outcome["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
