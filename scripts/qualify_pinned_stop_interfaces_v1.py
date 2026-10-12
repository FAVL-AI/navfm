"""Frozen synthetic native-component probe with durable parent/worker outcome evidence."""

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from pinned_stop_interfaces_v1 import (
    DescriptorTensor,
    PinnedStopInterface,
    authenticated_module,
    load_config,
    native_arrival_rule,
)

REPO = Path(__file__).resolve().parents[1]


def source_paths(cfg):
    return {
        key: cfg["sources"][kind][role]["local_path"]
        for kind in ("placenav", "ulvn")
        for key, role in ((kind, "belief"), (kind + "_terminal", "terminal"))
    }


def run_probe(cfg, emit):
    start = time.monotonic()
    paths = source_paths(cfg)
    for row in cfg["provenance_auxiliary"]:
        emit({"event": "SOURCE_AUTH_START", "path": row["path"]})
        raw = Path(row["local_path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"], "auxiliary source drift"
    ids = [f"synthetic-reference-{i}" for i in range(4)]
    hashes = [hashlib.sha256(v.encode()).hexdigest() for v in ids]
    graph = np.zeros((4, 4))
    graph[0, 1], graph[1, 2], graph[2, 3] = 0.25, 2.0, 0.5
    calls = 0
    for dtype in (np.float32, np.float64):
        d = np.eye(4, dtype=dtype)
        for kind in ("placenav", "ulvn"):
            emit({"event": "CASE_START", "kind": kind, "dtype": dtype.__name__})
            a = PinnedStopInterface(kind, paths, cfg, ids, hashes, d, graph, ids[-1], hashes[-1])
            a.reset("sequence")
            native = authenticated_module(kind, paths[kind], cfg["sources"][kind]["belief"])
            rule = native_arrival_rule(
                kind, paths[kind + "_terminal"], cfg["sources"][kind]["terminal"]
            )
            planner, latched = None, False
            if kind == "placenav":
                c = cfg["native_constants"][kind]
                oracle = native.PlaceRecognitionTopologicalFilter(
                    lambda q: {"global_descriptor": DescriptorTensor(q)},
                    d,
                    None,
                    delta=c["delta"],
                    window_lower=c["window_lower"],
                    window_upper=c["window_upper"],
                )
            else:
                oracle = native.PlaceRecognition(d.copy(), graph.copy(), max_steps=3, delta=5)
                planner = native.BeliefAwareSubgoalSearch(graph.copy(), d.copy(), None)
            for sequence, index in enumerate([0, 1, 2, 3, 1, 0]):
                emit(
                    {
                        "event": "FRAME_START",
                        "kind": kind,
                        "dtype": dtype.__name__,
                        "sequence": sequence,
                    }
                )
                q = d[index].copy()
                if sequence == 0:
                    oracle.initialize_model(q)
                    initial = oracle.belief.copy()
                    if planner is not None:
                        planner.initial_localize(d[-1].copy(), q)
                        planner.plan_path()
                node, score = oracle.match(q)
                result = a.step(
                    q, episode_id="sequence", sequence=sequence, simulation_time=sequence / 4
                )
                calls += 2
                emit(
                    {
                        "event": "FRAME_OBSERVED",
                        "kind": kind,
                        "dtype": dtype.__name__,
                        "sequence": sequence,
                        "wrapper_status": result["status"],
                        "oracle_MAP": int(node),
                        "wrapper_MAP": result.get("MAP_node"),
                        "wrapper_arrival": result.get("native_arrival"),
                    }
                )
                assert result["status"] == "SYNTHETIC_COMPONENT_ONLY"
                assert np.array_equal(result["belief"], oracle.belief)
                assert result["MAP_node"] == int(node) and result["confidence"] == float(score)
                assert a.filter.lambda1 == oracle.lambda1
                if sequence == 0:
                    assert np.array_equal(a.initialized_belief, initial)
                if planner is None:
                    expected = bool(rule(node, SimpleNamespace(goal_node_idx=3)))
                else:
                    subgoal = planner.next_subgoal(int(node), n_ahead=2, replan_if_offpath=True)[
                        "subgoal_idx"
                    ]
                    if subgoal is not None:
                        latched = bool(rule(subgoal, 3, node, latched))
                    expected = latched if subgoal is not None else None
                    assert result["subgoal"] == subgoal
                    assert a.planner.state.__dict__ == planner.state.__dict__
                    assert result["native_arrival_state"] == latched
                assert result["native_arrival"] == expected
                assert result["STOP_proposal"] == (expected is True)
                assert time.monotonic() - start < cfg["limits"]["probe_wall_seconds"]
            emit({"event": "RESET_ISOLATION_START", "kind": kind, "dtype": dtype.__name__})
            fresh = PinnedStopInterface(
                kind, paths, cfg, ids, hashes, d, graph, ids[-1], hashes[-1]
            )
            fresh.reset("fresh")
            a.reset("reset")
            x = a.step(d[0], episode_id="reset", sequence=0, simulation_time=0)
            y = fresh.step(d[0], episode_id="fresh", sequence=0, simulation_time=0)
            calls += 2
            assert np.array_equal(x["belief"], y["belief"])
            assert not np.shares_memory(a.filter.belief, fresh.filter.belief)
            emit(
                {
                    "event": "GUARD_START",
                    "guard": "unsupported_goal",
                    "kind": kind,
                    "dtype": dtype.__name__,
                }
            )
            unsupported = PinnedStopInterface(
                kind, paths, cfg, ids, hashes, d, graph, "absent", hashes[-1]
            )
            unsupported.reset("unsupported")
            assert (
                unsupported.step(d[0], episode_id="unsupported", sequence=0, simulation_time=0)[
                    "status"
                ]
                == "REJECT_UNSUPPORTED_GOAL"
            )
            assert unsupported.filter.belief is None
            equal = PinnedStopInterface(
                kind, paths, cfg, ids, hashes, d, graph, ids[-1], hashes[-1]
            )
            equal.reset("equal")
            q_equal = -np.ones(4, dtype=dtype) / np.array(2, dtype=dtype)
            r = equal.step(q_equal, episode_id="equal", sequence=0, simulation_time=0)
            calls += 1
            emit(
                {
                    "event": "EQUAL_QUANTILE_OBSERVED",
                    "kind": kind,
                    "dtype": dtype.__name__,
                    "status": r["status"],
                }
            )
            assert r["status"] == (
                "ABSTAIN_INVALID_NATIVE_BELIEF"
                if kind == "placenav"
                else "SYNTHETIC_COMPONENT_ONLY"
            )
            if kind == "ulvn":
                assert equal.filter.lambda1 == 1
                assert rule(3, 3, 2, False) is False and rule(2, 3, 3, False) is False
                assert rule(3, 3, 3, False) is True and rule(2, 3, 2, True) is True
                weighted = native.PlaceRecognition(d, graph, max_steps=3, delta=5)
                binary = native.PlaceRecognition(d, (graph > 0).astype(float), max_steps=3, delta=5)
                assert not np.array_equal(weighted.transition_matrix, binary.transition_matrix)
                emit(
                    {
                        "event": "GUARD_START",
                        "guard": "latched_None_subgoal",
                        "dtype": dtype.__name__,
                    }
                )
                disconnected = PinnedStopInterface(
                    kind, paths, cfg, ids, hashes, d, np.zeros_like(graph), ids[-1], hashes[-1]
                )
                disconnected.reset("none")
                disconnected.latched = (
                    True  # Declared fault-state control, not a successful trajectory.
                )
                r = disconnected.step(d[0], episode_id="none", sequence=0, simulation_time=0)
                calls += 1
                assert r["subgoal"] is None and r["native_arrival"] is None
                assert r["native_arrival_state"] is True and r["STOP_proposal"] is False
                emit(
                    {
                        "event": "GUARD_START",
                        "guard": "descriptor_tied_goal",
                        "dtype": dtype.__name__,
                    }
                )
                duplicate = d.copy()
                duplicate[-1] = duplicate[0]
                tied = PinnedStopInterface(
                    kind, paths, cfg, ids, hashes, duplicate, graph, ids[-1], hashes[-1]
                )
                tied.reset("tied")
                r = tied.step(d[1], episode_id="tied", sequence=0, simulation_time=0)
                assert r["status"] == "REJECT_UNREPRESENTABLE_GOAL"
                emit({"event": "GUARD_START", "guard": "zero_likelihood", "dtype": dtype.__name__})
                fresh.filter.lambda1 = 1e308  # Invalid-likelihood negative control, never tuning.
                r = fresh.step(q_equal, episode_id="fresh", sequence=1, simulation_time=0.25)
                calls += 1
                assert r["status"] == "ABSTAIN_INVALID_NATIVE_BELIEF"
            emit({"event": "CASE_PASS", "kind": kind, "dtype": dtype.__name__})
    assert calls <= cfg["limits"]["probe_total_native_match_calls_cap"]
    return {
        "status": "PASS_SYNTHETIC_COMPONENTS_ONLY",
        "native_match_calls": calls,
        "wall_seconds": time.monotonic() - start,
        "GPU_calls": 0,
        "encoder_images_weights_navigation": "NOT_RUN",
        "controller_STOP": "BLOCKED_ADAPTATION",
    }


def write_json(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def supervise_worker(command, log, wall_cap):
    process = None
    try:
        process = subprocess.Popen(command, cwd=REPO, stdout=log, stderr=log)
        try:
            code = process.wait(timeout=wall_cap)
            return {"exit_code": code, "timeout": False, "reaped": True}
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait()
            return {"exit_code": code, "timeout": True, "reaped": True}
    except Exception as exc:
        reaped = False
        code = None
        if process is not None:
            if process.poll() is None:
                process.kill()
            code = process.wait()
            reaped = True
        return {
            "exit_code": code,
            "timeout": False,
            "reaped": reaped,
            "exception_type": type(exc).__name__,
            "reason": str(exc)[:400],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    if (
        head != args.freeze
        or subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).strip()
    ):
        raise ValueError("exact clean frozen source required")
    if args.out.resolve().is_relative_to(REPO):
        raise ValueError("external output required")
    cfg = load_config()
    folder = args.out.parent
    if args.worker:
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (cfg["limits"]["probe_cpu_seconds"], cfg["limits"]["probe_cpu_seconds"]),
        )
        try:

            def emit(event):
                with (folder / "partial.jsonl").open("a") as stream:
                    stream.write(json.dumps(event, allow_nan=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())

            result = run_probe(cfg, emit)
            result["source_freeze"] = head
            write_json(args.out, result)
            write_json(folder / "worker_status.json", {"status": "PASS", "freeze": head})
        except Exception as exc:
            write_json(
                folder / "worker_status.json",
                {
                    "status": "FAIL",
                    "freeze": head,
                    "exception_type": type(exc).__name__,
                    "reason": str(exc)[:400],
                },
            )
            raise SystemExit(1) from None
        return
    if folder.exists():
        raise ValueError("fresh external attempt directory required; no retry or overwrite")
    folder.mkdir(parents=True)
    write_json(
        folder / "attempt.json",
        {
            "status": "STARTED",
            "freeze": head,
            "config_sha256": hashlib.sha256(
                (REPO / "configs/eval/stop_interface_qualification_v1.json").read_bytes()
            ).hexdigest(),
            "wall_cap_s": cfg["limits"]["probe_wall_seconds"],
        },
    )
    started = time.monotonic()
    with (folder / "worker.log").open("x") as log:
        outcome = supervise_worker(
            [sys.executable, __file__, "--worker", "--freeze", head, "--out", str(args.out)],
            log,
            cfg["limits"]["probe_wall_seconds"],
        )
    exit_code, timeout = outcome["exit_code"], outcome["timeout"]
    elapsed = time.monotonic() - started
    size = sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
    worker_ok = False
    if args.out.exists() and (folder / "worker_status.json").exists():
        worker = json.loads((folder / "worker_status.json").read_text())
        result = json.loads(args.out.read_text())
        worker_ok = (
            worker == {"status": "PASS", "freeze": head}
            and result.get("source_freeze") == head
            and result.get("status") == "PASS_SYNTHETIC_COMPONENTS_ONLY"
        )
    status = (
        "PASS"
        if exit_code == 0
        and not timeout
        and outcome["reaped"]
        and worker_ok
        and size <= cfg["limits"]["probe_output_bytes_cap"]
        and elapsed <= cfg["limits"]["parent_total_wall_seconds"]
        else "FAIL"
    )
    record = {
        "status": status,
        "freeze": head,
        "exit_code": exit_code,
        "timeout": timeout,
        "reaped": outcome["reaped"],
        "worker_source_status_verified": worker_ok,
        "parent_wall_seconds": elapsed,
        "artifact_bytes_before_parent_status": size,
    }
    write_json(folder / "parent_status.json", record)
    print(json.dumps(record))
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
