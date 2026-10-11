"""Timing-only append journal and guarded instrumentation; no dataset admission."""

import ast
import json
import os
import time
from pathlib import Path

from prospective_collection_contracts_v1 import amended_capture


class Events:
    def __init__(self, path, clock_id):
        self.path = Path(path)
        self.clock_id = clock_id
        self.sequence = 0
        self.context = {}
        self.logging_ns = 0

    def emit(self, event, **fields):
        start = time.monotonic_ns()
        record = dict(
            clock_id=self.clock_id,
            sequence=self.sequence,
            event=event,
            monotonic_ns=start,
            wall_ns=time.time_ns(),
            **self.context,
            **fields,
        )
        with self.path.open("a") as f:
            f.write(json.dumps(record, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.sequence += 1
        self.logging_ns += time.monotonic_ns() - start

    def call(self, label, function, *args, **kwargs):
        self.emit(label + "_BEGIN")
        start = time.monotonic_ns()
        try:
            result = function(*args, **kwargs)
        except BaseException as exc:
            end = time.monotonic_ns()
            self.emit(
                label + "_ERROR",
                interval_start_ns=start,
                interval_end_ns=end,
                error_type=type(exc).__name__,
            )
            raise
        end = time.monotonic_ns()
        self.emit(label + "_END", interval_start_ns=start, interval_end_ns=end)
        return result

    def frame(self, route, tick):
        self.context = dict(route=route, tick=tick)
        self.emit("FRAME_BEGIN")


class TimedContext:
    def __init__(self, context, events):
        self.context, self.events = context, events

    def __enter__(self):
        return self.events.call("SDK_ENTER", self.context.__enter__)

    def __exit__(self, *args):
        return self.events.call("SDK_CLOSE", self.context.__exit__, *args)


def timing_capture(source):
    tree = amended_capture(source)
    counts = {}

    class Timing(ast.NodeTransformer):
        def visit_With(self, node):
            sdk_items = [
                i
                for i, item in enumerate(node.items)
                if isinstance(item.context_expr, ast.Call)
                and ast.unparse(item.context_expr.func) == "IsaacApp"
            ]
            node = self.generic_visit(node)
            for i in sdk_items:
                item = node.items[i]
                if True:
                    item.context_expr = ast.Call(
                        func=ast.Name(id="TimedContext", ctx=ast.Load()),
                        args=[item.context_expr, ast.Name(id="events", ctx=ast.Load())],
                        keywords=[],
                    )
                    counts["context"] = counts.get("context", 0) + 1
            return node

        def visit_Call(self, node):
            node = self.generic_visit(node)
            name = ast.unparse(node.func)
            labels = {
                "sim.step": "APP_STEP",
                "cam.set_world_pose": "POSE_AUTHOR",
                "cam.get_current_frame": "FRAME_READ",
                "write": "SNAPSHOT",
                "persist_measurement": "CAPSULE_PERSIST",
            }
            label = labels.get(name)
            if name.endswith(".save") and ast.unparse(node.func.value).startswith(
                "Image.fromarray"
            ):
                label = "IMAGE_ENCODE_WRITE"
            if name == "IsaacApp":
                label = "SDK_CONSTRUCT"
            if label:
                counts[label] = counts.get(label, 0) + 1
                return ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="events", ctx=ast.Load()), attr="call", ctx=ast.Load()
                    ),
                    args=[ast.Constant(label), node.func, *node.args],
                    keywords=node.keywords,
                )
            return node

        def visit_Assign(self, node):
            node = self.generic_visit(node)
            if len(node.targets) == 1:
                name = ast.unparse(node.targets[0])
                if name in ["candidate['hold_start_time']", "candidate['hold_end_time']"]:
                    label = "HOLD_START" if "start" in name else "HOLD_END"
                    counts[label] = counts.get(label, 0) + 1
                    marker = ast.parse(f"events.emit('{label}', simulation_time_s={name})").body[0]
                    return [node, marker]
            return node

        def visit_For(self, node):
            node = self.generic_visit(node)
            if ast.unparse(node.target) == "(tick, (x, y, yaw))":
                node.body.insert(0, ast.parse("events.frame(route_id, tick)").body[0])
                counts["frame"] = counts.get("frame", 0) + 1
            return node

    tree = Timing().visit(tree)
    expected = dict(
        context=1,
        SDK_CONSTRUCT=1,
        APP_STEP=1,
        POSE_AUTHOR=1,
        FRAME_READ=1,
        SNAPSHOT=6,
        CAPSULE_PERSIST=1,
        IMAGE_ENCODE_WRITE=1,
        frame=1,
        HOLD_START=1,
        HOLD_END=1,
    )
    if counts != expected:
        raise ValueError("timing transform source boundary drift")
    return ast.fix_missing_locations(tree)


def wait_child(child, record, start, events):
    import contextlib
    import signal
    import subprocess

    def cleanup_event(name, **fields):
        try:
            events.emit(name, **fields)
        except BaseException as exc:
            record.setdefault("event_logging_errors", []).append(
                dict(event=name, error_type=type(exc).__name__)
            )
            record["status"] = "FAIL"

    try:
        events.emit("LAUNCH_RETURN", pid=child.pid)
        events.emit("WAIT_BEGIN")
        try:
            record["child_exit_code"] = child.wait(
                timeout=max(0, 120 - (time.monotonic() - start) - 5)
            )
            events.emit("WAIT_RETURN", returncode=record["child_exit_code"])
        except subprocess.TimeoutExpired:
            record["timeout"] = True
            cleanup_event("TIMEOUT_CAUGHT")
    except BaseException:
        record["status"] = "FAIL"
        raise
    finally:
        polled = child.poll()
        cleanup_event("POLL_RETURN", returncode=polled)
        if polled is None:
            try:
                cleanup_event("SIGKILL_REQUEST", pid=child.pid)
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGKILL)
                    cleanup_event("SIGKILL_CALL_RETURN")
            finally:
                child.wait(timeout=5)
        record["child_exit_code"] = child.returncode
        record["child_reaped"] = True
        cleanup_event("REAP_RETURN", returncode=child.returncode)
    if record.get("event_logging_errors"):
        raise OSError("parent timing journal incomplete")
