"""Offline requested-goal history-sensitivity runner for history_call_manifest_v3.json.

Subcommands
  run      supervisor: consumes one attempt directory, launches one worker, enforces the
           wall-clock and sampled process-memory guards, never retries
  _worker  internal: preflight (no model), environment record, model load, the listed calls
  admit    accept or refuse a finished attempt; partial or test attempts are refused
  analyse  pre-declared reporting over an admitted attempt (protocol v4, "Reporting")

Production mode is pinned to the v3 manifest (306 calls), the ViNT checkpoint recorded by the
four episodes, and model/preprocessing source staged byte-exact from the episodes'
content-addressed source_snapshot/. Test mode exists only to drive this same path with a model
substitute on CPU; it requires CUDA to be invisible, labels every output TEST, and `admit`
refuses TEST attempts unless --accept-test is passed.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback

PINNED = dict(
    manifest_sha256="391c2f02a944cd46f3683f53e4979041b34bad9060f035cf779fd283781ccfa7",
    calls=306,
    calls_by_arm={"H0_real": 96, "H1_repeated_static": 72, "H3_own_history_shifted5": 72,
                  "H2_posematched_other_variant": 50, "CTRL_goal_only": 12,
                  "CTRL_reversed_node_rows": 4},
    checkpoint_sha256="c7686983099080649dde0eaf79575149c26239321e23cf96788b3dd25b0d5d7c",
    hard_forward_cap=320,
    wall_limit_s=600.0,
    gpu_allocator_cap_bytes=4 * 2**30,
    gpu_process_cap_mib=4096,
    sample_period_s=1.0,
)
EVIDENCE = None  # the runtime-evidence root; set only from the explicit --evidence-root argument


def evidence():
    if not EVIDENCE:
        raise Abort("CONFIG", "evidence root not set")
    return EVIDENCE

EPISODES = [f"cmp-{v}-trunc-20261009-01/{r}" for r in ("junction_run_0000", "junction_run_0001")
            for v in ("C_verify", "D_both")]
SNAPSHOT_EPISODE = EPISODES[0]
THRESHOLD = 7.745
ARMS_PAIRED = ("H1_repeated_static", "H3_own_history_shifted5", "H2_posematched_other_variant")
# Statements copied from the deployed RGBTopomapBaseline.step (source_snapshot cd55771c...,
# lines 219-225). The worker refuses to run unless the staged file contains them verbatim.
DEPLOYED_ASSEMBLY = [
    "nodes = self.chain[start:end + 1]",
    "images = nodes + ([goal] if goal is not None else [])",
    "obs = self.tensor(history).repeat(len(images), 1, 1, 1)",
    "goals = torch.cat([self.tensor([n]) for n in images], dim=0)",
    "d_all = np.asarray(distance.detach().cpu().numpy(), float).reshape(-1)",
]


class Abort(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _read_bytes(p):
    with open(p, "rb") as f:
        return f.read()


def _read_text(p):
    with open(p) as f:
        return f.read()


def _read_json(p):
    with open(p) as f:
        return json.load(f)


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    with open(p, "rb") as f:
        return sha_bytes(f.read())


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    d = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
    try:
        os.fsync(d)  # make the rename itself durable
    finally:
        os.close(d)


# --------------------------------------------------------------------------- forward budget
class ForwardBudget:
    """Counts listed calls and actual module forwards; any excess or mismatch aborts."""

    def __init__(self, cap):
        if not 0 < cap <= PINNED["hard_forward_cap"]:
            raise Abort("CAP_INVALID", cap)
        self.cap, self.listed, self.hooked = cap, 0, 0

    def pre_hook(self, module, args):
        self.hooked += 1
        if self.hooked > self.cap:
            raise Abort("FORWARD_CAP", f"module forward {self.hooked} > cap {self.cap}")

    def begin_listed(self):
        self.listed += 1
        if self.listed > self.cap:
            raise Abort("FORWARD_CAP", f"listed call {self.listed} > cap {self.cap}")
        if self.hooked != self.listed - 1:
            raise Abort("UNLISTED_FORWARD", f"{self.hooked} forwards before listed call {self.listed}")

    def end_listed(self):
        if self.hooked != self.listed:
            raise Abort("UNLISTED_FORWARD", f"{self.hooked} forwards for {self.listed} listed calls")


# --------------------------------------------------------------------------- memory
def parse_process_mib(text, pid):
    """nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits"""
    total = 0
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) == pid:
            total += int(parts[1])  # "[N/A]" raises ValueError: the sample counts as failed
    return total


def allocator_within_cap(stats, cap_bytes):
    return stats["max_memory_reserved"] <= cap_bytes and stats["max_memory_allocated"] <= cap_bytes


# --------------------------------------------------------------------------- manifest checks
def episode_of(path):
    rel = os.path.relpath(path, evidence())
    parts = rel.split(os.sep)
    if len(parts) != 4 or parts[2] != "trajectory" or f"{parts[0]}/{parts[1]}" not in EPISODES:
        raise Abort("MALFORMED_INPUT", f"observation outside the four episodes: {path}")
    return f"{parts[0]}/{parts[1]}", parts[3]


def load_episodes():
    eps = {}
    for e in EPISODES:
        m = _read_json(f"{evidence()}/{e}/runtime_manifest.json")
        eps[e] = m
    return eps


def check_manifest(man, mode):
    calls, queries = man.get("calls"), man.get("queries")
    if not isinstance(calls, list) or not isinstance(queries, list) or not calls:
        raise Abort("MALFORMED_INPUT", "manifest lacks calls/queries")
    need = {"call_id", "query_id", "arm", "repeat", "goal_row_index", "batch_rows", "obs"}
    for i, c in enumerate(calls):
        if not isinstance(c, dict) or not need <= set(c):
            raise Abort("MALFORMED_INPUT", f"call index {i} lacks fields")
        if c["call_id"] != i:
            raise Abort("MALFORMED_INPUT", f"call_id {c['call_id']} at position {i}")
        if len(c["obs"]) != 6:
            raise Abort("MALFORMED_INPUT", f"call {i} has {len(c['obs'])} observation frames")
        if c["goal_row_index"] != len(c["batch_rows"]) - 1:
            raise Abort("MALFORMED_INPUT", f"call {i} goal row is not last")
        for f in c["obs"] + c["batch_rows"]:
            if set(f) != {"path", "sha256"} or len(f["sha256"]) != 64:
                raise Abort("MALFORMED_INPUT", f"call {i} malformed file entry")
    count = {}
    for c in calls:
        count[c["arm"]] = count.get(c["arm"], 0) + 1
    if mode == "PRODUCTION" and (len(calls) != PINNED["calls"] or count != PINNED["calls_by_arm"]):
        raise Abort("POPULATION", f"{len(calls)} calls {count}")
    qids = [q["query_id"] for q in queries]
    if len(set(qids)) != len(qids):
        raise Abort("MALFORMED_INPUT", "duplicate query ids")
    h0 = {}
    for c in calls:
        if c["arm"] == "H0_real" and c["repeat"] == 0:
            if c["query_id"] in h0:
                raise Abort("MALFORMED_INPUT", f"two H0 repeat-0 calls for {c['query_id']}")
            h0[c["query_id"]] = c
    if set(h0) != set(qids):
        raise Abort("POPULATION", "H0 repeat 0 is not exactly one per query")
    seen = set()
    for c in calls:
        key = (c["query_id"], c["arm"], c["repeat"])
        if key in seen:
            raise Abort("MALFORMED_INPUT", f"duplicate call {key}")
        seen.add(key)
        ref = h0.get(c["query_id"])
        if ref is None:
            raise Abort("MALFORMED_INPUT", f"call {c['call_id']} names unknown query")
        if c["obs"][-1] != ref["obs"][-1]:
            raise Abort("PAIRING", f"call {c['call_id']} changes the query image")
        arm = c["arm"]
        if (arm in ARMS_PAIRED or arm == "H0_real") and c["batch_rows"] != ref["batch_rows"]:
            raise Abort("PAIRING", f"call {c['call_id']} changes the reference batch")
        if arm == "H0_real" and c["obs"] != ref["obs"]:
            raise Abort("PAIRING", f"repeat {c['call_id']} differs from H0 repeat 0")
        if arm == "H1_repeated_static" and c["obs"] != [ref["obs"][-1]] * 6:
            raise Abort("PAIRING", f"call {c['call_id']} is not the query repeated")
        if arm in ("H3_own_history_shifted5", "H2_posematched_other_variant") \
                and c["obs"][:5] == ref["obs"][:5]:
            raise Abort("PAIRING", f"call {c['call_id']} does not substitute history")
        if arm == "CTRL_goal_only" and (c["obs"] != ref["obs"] or c["batch_rows"] != [ref["batch_rows"][-1]]):
            raise Abort("PAIRING", f"control {c['call_id']} is not goal-only of H0")
        if arm == "CTRL_reversed_node_rows":
            want = [*list(reversed(ref["batch_rows"][:-1])), ref["batch_rows"][-1]]
            if c["obs"] != ref["obs"] or c["batch_rows"] != want:
                raise Abort("PAIRING", f"control {c['call_id']} is not reversed rows of H0")
        if arm not in (*ARMS_PAIRED, "H0_real", "CTRL_goal_only", "CTRL_reversed_node_rows"):
            raise Abort("MALFORMED_INPUT", f"unknown arm {arm}")
    return h0


def check_against_episodes(man, eps):
    """Every input is re-derived from the episode records, not trusted from the manifest."""
    digests = [eps[e]["observations"][2]["value"] for e in EPISODES]
    if any(d != digests[0] for d in digests):
        raise Abort("SOURCE_DIGEST", "episodes disagree on influencing_file_digests")
    ck = {(eps[e]["policy"]["checkpoint"], eps[e]["policy"]["sha256"]) for e in EPISODES}
    if len(ck) != 1:
        raise Abort("CHECKPOINT", f"episodes disagree on checkpoint {ck}")
    configs = [eps[e]["policy"]["config"] for e in EPISODES]
    if any(c != configs[0] for c in configs):
        raise Abort("CHECKPOINT", "episodes disagree on the model config")
    qmap = {q["query_id"]: q for q in man["queries"]}

    def frames(e, ks):
        return [f"{eps[e]['inference'][k]['frame'] - 1}.jpg" for k in ks]

    for c in man["calls"]:
        q = qmap[c["query_id"]]
        e = f"cmp-{q['variant']}-trunc-20261009-01/{q['route']}"
        m, k = eps[e], q["k"]
        if m["inference"][k]["requested_goal_distance"] != q["logged_requested_goal_distance"]:
            raise Abort("POPULATION", f"{q['query_id']} logged score differs from the episode")
        s, t = m["inference"][k]["chain"]["window"]
        if [s, t] != q["window"]:
            raise Abort("POPULATION", f"{q['query_id']} window differs from the episode")
        nodes = [n[1] for n in m["topomap"]["nodes"]][s:t + 1]
        rows = [r["sha256"] for r in c["batch_rows"]]
        if c["arm"] == "CTRL_goal_only":
            want = [m["fixed_goal_sha256"]]
        elif c["arm"] == "CTRL_reversed_node_rows":
            want = [*list(reversed(nodes)), m["fixed_goal_sha256"]]
        else:
            want = [*nodes, m["fixed_goal_sha256"]]
        if rows != want:
            raise Abort("POPULATION", f"call {c['call_id']} batch rows differ from the episode window")
        for f in c["obs"]:
            oe, name = episode_of(f["path"])
            if eps[oe]["file_sha256"].get(name) != f["sha256"]:
                raise Abort("HASH_MISMATCH", f"call {c['call_id']} {f['path']} vs episode record")
        names = [os.path.basename(f["path"]) for f in c["obs"]]
        own = [episode_of(f["path"])[0] for f in c["obs"]]
        query = frames(e, [k])
        if c["arm"] in ("H0_real", "CTRL_goal_only", "CTRL_reversed_node_rows"):
            want_names, want_eps = frames(e, range(k - 5, k)) + query, [e] * 6
        elif c["arm"] == "H1_repeated_static":
            want_names, want_eps = query * 6, [e] * 6
        elif c["arm"] == "H3_own_history_shifted5":
            want_names, want_eps = frames(e, range(k - 10, k - 5)) + query, [e] * 6
        else:
            if not q.get("match"):
                raise Abort("POPULATION", f"call {c['call_id']} is H2 for a query without a match")
            other = q["match"]["other_variant"]
            oe = f"cmp-{other}-trunc-20261009-01/{q['route']}"
            mk = q["match"]["k"]
            want_names, want_eps = frames(oe, range(mk - 5, mk)) + query, [oe] * 5 + [e]
        if names != want_names or own != want_eps:
            raise Abort("POPULATION", f"call {c['call_id']} history frames differ from the arm definition")
    return ck.pop(), digests[0], configs[0]


def read_verified(f):
    with open(f["path"], "rb") as fh:
        data = fh.read()
    if sha_bytes(data) != f["sha256"]:
        raise Abort("HASH_MISMATCH", f["path"])
    return data


def decode(data, path):
    import numpy as np
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        arr = np.asarray(img.convert("RGB"))
    except Exception as exc:  # any decoder failure is a malformed input
        raise Abort("MALFORMED_INPUT", f"{path}: {exc!r}") from exc
    if arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8 or min(arr.shape[:2]) < 16:
        raise Abort("MALFORMED_INPUT", f"{path}: shape {arr.shape} dtype {arr.dtype}")
    return arr


# --------------------------------------------------------------------------- source staging
def stage_source(digests, staged, snap=None):
    """Copy every recorded source file from the content-addressed snapshot into a package
    layout under `staged`, verifying each digest before and after the copy."""
    snap = snap or f"{evidence()}/{SNAPSHOT_EPISODE}/source_snapshot"
    layout = {}
    for path, digest in sorted(digests.items()):
        if "/upstream/train/" in path:
            rel = os.path.join("upstream_train", path.split("/upstream/train/", 1)[1])
        elif "/src/" in path:
            rel = os.path.join("navfm_src", path.split("/src/", 1)[1])
        elif "/scripts/" in path:
            rel = os.path.join("scripts", path.split("/scripts/", 1)[1])
        else:
            raise Abort("SOURCE_DIGEST", f"unmapped source path {path}")
        src = os.path.join(snap, digest)
        if not os.path.isfile(src) or sha_file(src) != digest:
            raise Abort("SOURCE_DIGEST", f"snapshot missing or altered for {path}")
        dst = os.path.join(staged, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        os.chmod(dst, 0o444)
        if sha_file(dst) != digest:
            raise Abort("SOURCE_DIGEST", f"staged copy differs for {path}")
        layout[os.path.realpath(dst)] = dict(recorded_path=path, sha256=digest)
    return layout


def check_assembly(staged, runner_path=None):
    path = os.path.join(staged, "navfm_src/navfm/collection/rgb_baseline.py")
    tree = ast.parse(_read_text(path))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RGBTopomapBaseline")
    step = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "step")
    have = [ast.unparse(s) for s in ast.walk(step) if isinstance(s, ast.Assign)]
    want = [ast.unparse(ast.parse(s).body[0]) for s in DEPLOYED_ASSEMBLY]
    missing = [w for w in want if w not in have]
    if missing:
        raise Abort("SOURCE_DIGEST", f"deployed step lacks {missing}")
    mine = next(n for n in ast.parse(_read_text(runner_path or os.path.abspath(__file__))).body
                if isinstance(n, ast.FunctionDef) and n.name == "worker")
    deployed, replica = assembly_signature(step), assembly_signature(mine)
    if deployed != replica:
        raise Abort("SOURCE_DIGEST", f"runner assembly {replica} differs from deployed {deployed}")
    binding = [ast.unparse(n) for n in ast.walk(mine) if isinstance(n, ast.Assign)
               and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("history", "rows", "images")]
    want_binding = [ast.unparse(ast.parse(x).body[0]) for x in RUNNER_INPUT_BINDING]
    if sorted(binding) != sorted(want_binding):
        raise Abort("SOURCE_DIGEST", f"runner input binding {binding} differs from {want_binding}")


# The runner-only statements that bind manifest entries to model inputs. They have no deployed
# counterpart (deployment received arrays), so they are pinned literally.
RUNNER_INPUT_BINDING = [
    'history = [decode(read_verified(f), f["path"]) for f in c["obs"]]',
    'rows = [decode(read_verified(f), f["path"]) for f in c["batch_rows"]]',
    "images = rows",
]


def assembly_signature(fn):
    """The model-facing statements of a function, with `self.` removed: the obs and goals
    tensors, the inference_mode block that calls the model, and the d_all conversion."""
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in ("obs", "goals", "d_all"):
            out.append((node.lineno, ast.unparse(node)))
        if isinstance(node, ast.With) and "inference_mode" in ast.unparse(node.items[0]):
            out.append((node.lineno, ast.unparse(node)))
    return [text.replace("self.", "") for _, text in sorted(out)]


def check_module_origins(layout, staged):
    """Every navfm / vint_train module in sys.modules must be a staged, digest-matching file."""
    loaded = {}
    for name, mod in list(sys.modules.items()):
        if not (name == "navfm" or name.startswith(("navfm.", "vint_train"))):
            continue
        f = getattr(mod, "__file__", None)
        real = os.path.realpath(f) if f else None
        if real not in layout or sha_file(real) != layout[real]["sha256"]:
            raise Abort("SOURCE_ORIGIN", f"{name} loaded from {f}")
        loaded[name] = layout[real]
    return loaded


# --------------------------------------------------------------------------- worker
def worker(attempt):
    t_start = time.monotonic()
    global EVIDENCE
    plan = _read_json(os.path.join(attempt, "plan.json"))
    EVIDENCE = plan["evidence_root"]
    deadline = t_start + plan["worker_wall_budget_s"]
    results_path = os.path.join(attempt, "results.jsonl")
    budget = None
    state = dict(stage="preflight", forwards_listed=0, forwards_hooked=0)
    # Hard self-limit: SIGALRM's default action terminates the worker even if the supervisor is
    # gone. It fires about 2 s before the supervisor's own deadline.
    signal.alarm(max(1, math.ceil(plan["worker_wall_budget_s"]) + 3))
    try:
        if sha_file(os.path.abspath(__file__)) != plan["runner_sha256"]:
            raise Abort("RUNNER_DIGEST", "worker file differs from the supervisor's")
        mode = plan["mode"]
        if mode == "TEST" and os.environ.get("CUDA_VISIBLE_DEVICES") != "":
            raise Abort("TEST_MODE_GPU", "test mode requires CUDA_VISIBLE_DEVICES=''")
        raw = _read_bytes(plan["manifest"])
        if sha_bytes(raw) != plan["manifest_sha256"]:
            raise Abort("HASH_MISMATCH", "manifest")
        if mode == "PRODUCTION" and plan["manifest_sha256"] != PINNED["manifest_sha256"]:
            raise Abort("HASH_MISMATCH", "manifest is not the pinned v3 manifest")
        try:
            man = json.loads(raw)
        except ValueError as exc:
            raise Abort("MALFORMED_INPUT", f"manifest JSON: {exc}") from exc
        check_manifest(man, mode)
        eps = load_episodes()
        (ckpt_path, ckpt_sha), digests, config = check_against_episodes(man, eps)
        if ckpt_sha != PINNED["checkpoint_sha256"]:
            raise Abort("CHECKPOINT", "episode checkpoint differs from the pinned digest")
        if sha_file(ckpt_path) != ckpt_sha:
            raise Abort("HASH_MISMATCH", f"checkpoint {ckpt_path}")
        files = {}
        for c in man["calls"]:
            for f in c["obs"] + c["batch_rows"]:
                files[f["path"]] = f
        for f in files.values():
            decode(read_verified(f), f["path"])
        staged = os.path.join(attempt, "staged_src")
        layout = stage_source(digests, staged)
        check_assembly(staged)
        cap = len(man["calls"])
        if cap > PINNED["hard_forward_cap"]:
            raise Abort("FORWARD_CAP", f"{cap} listed calls exceed the hard cap")
        budget = ForwardBudget(cap)
        write_json(os.path.join(attempt, "preflight.json"), dict(
            status="PASS", calls=cap, distinct_input_files=len(files), checkpoint=ckpt_path,
            checkpoint_sha256=ckpt_sha, staged_files=len(layout), elapsed_s=time.monotonic() - t_start))

        state["stage"] = "environment"
        sys.path[:0] = [os.path.join(staged, "upstream_train"), os.path.join(staged, "navfm_src")]
        import numpy as np
        import torch

        cuda = torch.cuda.is_available()
        if mode == "PRODUCTION" and (plan["backend"] != "vint" or not cuda):
            raise Abort("NO_CUDA" if not cuda else "BACKEND", "production needs the vint backend on CUDA")
        if mode == "TEST" and cuda:
            raise Abort("TEST_MODE_GPU", "CUDA is visible in test mode")
        device = "cuda" if cuda else "cpu"
        if cuda:
            total = torch.cuda.get_device_properties(0).total_memory
            torch.cuda.set_per_process_memory_fraction(PINNED["gpu_allocator_cap_bytes"] / total, 0)
        env = environment_record(torch, cuda)
        env["allocator_cap_bytes"] = PINNED["gpu_allocator_cap_bytes"] if cuda else None
        write_json(os.path.join(attempt, "environment.json"), env)

        state["stage"] = "model_load"
        from vint_train.data.data_utils import resize_and_aspect_crop

        from navfm import upstream
        from navfm.collection.rgb_baseline import RGBBaseline

        upstream.ensure_upstream = lambda: os.path.join(staged, "upstream_train")
        if plan["backend"] == "vint":
            from navfm.models.loader import extract_state_dict, load_checkpoint

            check_module_origins(layout, staged)  # before anything is constructed or unpickled
            model = upstream.build_model("vint", cfg=config)
            model.register_forward_pre_hook(budget.pre_hook)
            # trust_checkpoint=False: the deployed loader then uses torch.load(weights_only=True)
            # only and raises instead of falling back to unrestricted unpickling.
            state_dict = extract_state_dict(load_checkpoint(
                ckpt_path, trust_checkpoint=False, expected_sha256=ckpt_sha))
            model.load_state_dict(state_dict, strict=True)
            model.to(device).eval()
        else:
            if mode != "TEST":
                raise Abort("BACKEND", "substitutes are test-only")
            spec_path, name = plan["backend"].split("::")
            spec = importlib.util.spec_from_file_location("hsr_substitute", spec_path)
            sub = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sub)
            model = getattr(sub, name)()
            model.register_forward_pre_hook(budget.pre_hook)
            model.to(device).eval()
        origins = check_module_origins(layout, staged)
        shim = type("Shim", (), {})()
        shim.resize_and_aspect_crop, shim.config, shim.torch, shim.device = (
            resize_and_aspect_crop, config, torch, device)

        def tensor(images):
            return RGBBaseline.tensor(shim, images)

        load_stats = memory_stats(torch, cuda)
        write_json(os.path.join(attempt, "model_load.json"), dict(
            backend=plan["backend"], device=device, module_origins=origins,
            forwards_during_load=budget.hooked, memory=load_stats,
            elapsed_s=time.monotonic() - t_start))
        if budget.hooked:
            raise Abort("UNLISTED_FORWARD", f"{budget.hooked} forwards during load")
        if cuda and not allocator_within_cap(load_stats, PINNED["gpu_allocator_cap_bytes"]):
            raise Abort("GPU_ALLOCATOR_CAP", load_stats)

        state["stage"] = "calls"
        with open(results_path, "x") as out:
            for c in man["calls"]:
                if time.monotonic() > deadline:
                    raise Abort("TIMEOUT", f"worker deadline before call {c['call_id']}")
                history = [decode(read_verified(f), f["path"]) for f in c["obs"]]
                rows = [decode(read_verified(f), f["path"]) for f in c["batch_rows"]]
                t0 = time.perf_counter()
                budget.begin_listed()
                # Verbatim batch assembly of the deployed step(); the goal row is last.
                images = rows
                obs = tensor(history).repeat(len(images), 1, 1, 1)
                goals = torch.cat([tensor([n]) for n in images], dim=0)
                with torch.inference_mode():
                    distance, actions = model(obs, goals)  # noqa: RUF059 - pinned to deployed step()
                d_all = np.asarray(distance.detach().cpu().numpy(), float).reshape(-1)
                budget.end_listed()
                if cuda:
                    torch.cuda.synchronize()
                dt = time.perf_counter() - t0
                if d_all.shape != (len(rows),) or not np.isfinite(d_all).all():
                    raise Abort("OUTPUT_INVALID", f"call {c['call_id']} d_all {d_all.tolist()}")
                mem = memory_stats(torch, cuda)
                if cuda and not allocator_within_cap(mem, PINNED["gpu_allocator_cap_bytes"]):
                    raise Abort("GPU_ALLOCATOR_CAP", mem)
                rec = dict(call_id=c["call_id"], query_id=c["query_id"], arm=c["arm"],
                           repeat=c["repeat"], goal_row_index=c["goal_row_index"],
                           score=float(d_all[c["goal_row_index"]]), d_all=d_all.tolist(),
                           obs_sha256=[f["sha256"] for f in c["obs"]],
                           batch_sha256=[f["sha256"] for f in c["batch_rows"]],
                           forward_s=dt, memory=mem)
                out.write(json.dumps(rec, sort_keys=True) + "\n")
                out.flush()
                os.fsync(out.fileno())
                state["forwards_listed"], state["forwards_hooked"] = budget.listed, budget.hooked
        if budget.listed != cap or budget.hooked != cap:
            raise Abort("POPULATION", f"{budget.listed}/{budget.hooked} forwards for {cap} calls")
        final_origins = check_module_origins(layout, staged)
        write_json(os.path.join(attempt, "worker_terminal.json"), dict(
            status="COMPLETE", mode=mode, backend=plan["backend"], forwards_listed=budget.listed,
            forwards_hooked=budget.hooked, results_sha256=sha_file(results_path),
            module_origins_after_calls=sorted(final_origins),
            manifest_sha256=plan["manifest_sha256"], peak_memory=memory_stats(torch, cuda),
            peak_rss_kib=_rss_kib(), elapsed_s=time.monotonic() - t_start))
        return 0
    except BaseException as exc:
        code = exc.code if isinstance(exc, Abort) else type(exc).__name__
        if budget is not None:
            state["forwards_listed"], state["forwards_hooked"] = budget.listed, budget.hooked
        write_json(os.path.join(attempt, "worker_terminal.json"), dict(
            status="ABORTED", reason=code, detail=str(exc), traceback=traceback.format_exc(),
            mode=plan.get("mode"), **state, elapsed_s=time.monotonic() - t_start))
        return 3


def _rss_kib():
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def memory_stats(torch, cuda):
    if not cuda:
        return dict(device="cpu")
    return dict(max_memory_allocated=torch.cuda.max_memory_allocated(),
                max_memory_reserved=torch.cuda.max_memory_reserved(),
                memory_allocated=torch.cuda.memory_allocated())


def environment_record(torch, cuda):
    import numpy
    import PIL
    import torchvision

    rec = dict(
        python=sys.executable, python_version=sys.version, flags_isolated=sys.flags.isolated,
        torch=torch.__version__, torchvision=torchvision.__version__, pil=PIL.__version__,
        numpy=numpy.__version__, cuda_runtime=torch.version.cuda,
        cudnn=torch.backends.cudnn.version() if cuda else None, cuda_available=cuda,
        cudnn_benchmark=torch.backends.cudnn.benchmark,
        cudnn_deterministic=torch.backends.cudnn.deterministic,
        cuda_matmul_allow_tf32=torch.backends.cuda.matmul.allow_tf32,
        cudnn_allow_tf32=torch.backends.cudnn.allow_tf32,
        float32_matmul_precision=torch.get_float32_matmul_precision(),
        deterministic_algorithms=torch.are_deterministic_algorithms_enabled(),
    )
    try:
        import efficientnet_pytorch

        rec["efficientnet_pytorch"] = getattr(efficientnet_pytorch, "__version__", "unversioned")
        rec["efficientnet_pytorch_file"] = efficientnet_pytorch.__file__
        pkg = os.path.dirname(efficientnet_pytorch.__file__)
        # Recorded for the replay only; the deployment never recorded these, so they bind nothing.
        rec["efficientnet_pytorch_source_sha256_unbound"] = {
            n: sha_file(os.path.join(pkg, n)) for n in sorted(os.listdir(pkg)) if n.endswith(".py")}
    except ImportError:
        rec["efficientnet_pytorch"] = None
    if cuda:
        rec["device_name"] = torch.cuda.get_device_name(0)
        rec["device_total_memory"] = torch.cuda.get_device_properties(0).total_memory
        rec["driver"] = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20).stdout.strip()
    return rec


# --------------------------------------------------------------------------- supervisor
def supervise(args):
    t0 = time.monotonic()
    mode = "TEST" if args.test_mode else "PRODUCTION"
    if mode == "PRODUCTION":
        if args.backend != "vint" or args.wall_limit_s is not None or args.test_sampler_cmd:
            print("production mode accepts no backend, wall-limit or sampler override")
            return 2
        if args.manifest_sha256 != PINNED["manifest_sha256"]:
            print("production mode requires the pinned v3 manifest digest")
            return 2
    elif args.backend == "vint":
        print("test mode requires a substitute backend")
        return 2
    wall = PINNED["wall_limit_s"] if args.wall_limit_s is None else args.wall_limit_s
    evidence_root = os.path.abspath(args.evidence_root)
    if not all(os.path.isfile(os.path.join(evidence_root, e, "runtime_manifest.json")) for e in EPISODES):
        print(f"evidence root lacks the four episode records: {evidence_root}")
        return 2
    attempt = os.path.abspath(args.attempt_dir)
    try:
        os.mkdir(attempt)  # the attempt is consumed here; an existing directory is refused
    except FileExistsError:
        print(f"attempt directory exists, refusing: {attempt}")
        return 2
    runner = os.path.abspath(__file__)
    plan = dict(mode=mode, backend=args.backend, manifest=os.path.abspath(args.manifest),
                evidence_root=evidence_root,
                manifest_sha256=args.manifest_sha256, runner=runner, runner_sha256=sha_file(runner),
                wall_limit_s=wall, worker_wall_budget_s=wall - (time.monotonic() - t0) - 5.0,
                gpu_process_cap_mib=PINNED["gpu_process_cap_mib"], pinned=PINNED,
                started_unix=time.time(), argv=sys.argv)
    write_json(os.path.join(attempt, "plan.json"), plan)
    env = dict(os.environ)
    if mode == "TEST":
        env["CUDA_VISIBLE_DEVICES"] = ""
    interrupted = []
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda signum, frame: interrupted.append(signum))
    sampling = mode == "PRODUCTION" or bool(args.test_sampler_cmd)
    sampler = args.test_sampler_cmd or ("nvidia-smi --query-compute-apps=pid,used_memory "
                                        "--format=csv,noheader,nounits")
    mem = dict(attempted=0, present=0, failed=0, peak_mib=0, over=None)
    stop_sampling = threading.Event()
    proc, status, reason, execution_end, forced, survivors = None, None, None, None, False, None
    try:
        with open(os.path.join(attempt, "worker.stdout"), "w") as so, \
                open(os.path.join(attempt, "worker.stderr"), "w") as se:
            proc = subprocess.Popen([sys.executable, "-I", runner, "_worker", attempt],
                                    stdout=so, stderr=se, env=env, start_new_session=True)
        if sampling:
            threading.Thread(target=_sample_loop, args=(sampler, proc.pid, mem, stop_sampling),
                             daemon=True).start()
        # The loop below never blocks on anything but a 0.1 s sleep; sampling runs on its own
        # thread, so a hung nvidia-smi cannot delay the deadline.
        while proc.poll() is None:
            if interrupted:
                status, reason = "INTERRUPTED", f"supervisor received signal {interrupted[0]}"
            elif time.monotonic() - t0 > wall:
                status, reason = "TIMEOUT", f"wall clock {wall:.0f} s from supervisor start"
            elif mem["over"] is not None:
                status, reason = "MEMORY_CAP", f"sampled process memory {mem['over']} MiB"
            if status is not None:
                forced = True
                break
            time.sleep(0.1)
    except BaseException as exc:
        status, reason, forced = "SUPERVISOR_ERROR", repr(exc), True
    finally:
        execution_end = time.monotonic() - t0
        stop_sampling.set()
        # Cleanup and finalisation. The worker's session was created above, so this supervisor
        # owns it. Forced outcomes kill a live worker. After a natural exit the session is
        # normally empty already; a surviving member is recorded and makes the attempt
        # inadmissible.
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                survivors = True
            except ProcessLookupError:
                survivors = False
            proc.wait()  # reaps the direct child
        rc = None if proc is None else proc.returncode
        wt_path = os.path.join(attempt, "worker_terminal.json")
        try:
            wt = _read_json(wt_path) if os.path.exists(wt_path) else None
        except ValueError:
            wt = None
        if status is None:
            if rc == 0 and wt and wt.get("status") == "COMPLETE":
                status = "COMPLETE"
            elif rc == -signal.SIGALRM:
                status, reason = "TIMEOUT", "worker hard self-limit (SIGALRM)"
            elif wt and wt.get("status") == "ABORTED":
                status, reason = "ABORTED", wt.get("reason")
            elif wt and wt.get("status") == "COMPLETE":
                status, reason = "WORKER_FAILED", f"exit {rc} after a COMPLETE record"
            else:
                status, reason = "WORKER_FAILED", f"exit {rc} without a terminal record"
        write_json(os.path.join(attempt, "supervisor_terminal.json"), dict(
            status=status, reason=reason, worker_exit=rc, worker_pid=None if proc is None else proc.pid,
            mode=mode, natural_exit=not forced, forced_termination=forced,
            session_members_killed_at_cleanup=(survivors if not forced else None),
            deadline_s=wall, execution_end_s=execution_end, finalised_s=time.monotonic() - t0,
            gpu_process_samples_attempted=mem["attempted"], gpu_process_samples_present=mem["present"],
            gpu_process_samples_failed=mem["failed"], gpu_process_peak_sampled_mib=mem["peak_mib"],
            retries=0))
    print(json.dumps(dict(status=status, reason=reason, attempt=attempt)))
    return 0 if status == "COMPLETE" else 1


def _sample_loop(sampler, pid, mem, stop):
    """Sampled process-memory guard. An unreadable or hung sample counts as failed, never as 0."""
    cmd = sampler.replace("{pid}", str(pid))
    previous = None
    while not stop.is_set():
        mem["attempted"] += 1
        if previous is not None and previous.poll() is None:
            mem["failed"] += 1  # an unkillable earlier sample is still alive; do not stack another
            stop.wait(PINNED["sample_period_s"])
            continue
        try:
            p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, start_new_session=True)
            previous = p
            text, _ = p.communicate(timeout=5)
            present = [line for line in text.strip().splitlines()
                       if line.split(",")[0].strip() == str(pid)]
            mib = parse_process_mib(text, pid)
            if present:
                mem["present"] += 1
                mem["peak_mib"] = max(mem["peak_mib"], mib)
                if mib > PINNED["gpu_process_cap_mib"]:
                    mem["over"] = mib
        except subprocess.TimeoutExpired:
            mem["failed"] += 1
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, signal.SIGKILL)  # the sampler's own session; never waited on
        except (ValueError, OSError):
            mem["failed"] += 1
        stop.wait(PINNED["sample_period_s"])


# --------------------------------------------------------------------------- admission
def admit(attempt, accept_test=False, expected_runner_sha256=None):
    """Return (admitted, reasons). Never repairs or completes anything.

    Admission checks that an attempt's records are complete and mutually consistent. It cannot
    establish their authenticity: anyone able to rewrite the attempt directory can rewrite its
    records consistently. Authenticity rests on recording the hashes from `record_hashes`
    out of band immediately after the run."""
    bad = []

    def load(name):
        p = os.path.join(attempt, name)
        return _read_json(p) if os.path.exists(p) else None

    plan, sup, wt = load("plan.json"), load("supervisor_terminal.json"), load("worker_terminal.json")
    if not plan or not sup or not wt:
        return False, ["missing plan or terminal record"]
    if sup["status"] != "COMPLETE" or sup["worker_exit"] != 0 or wt["status"] != "COMPLETE":
        bad.append(f"terminal status {sup['status']}/{wt['status']}")
    if sup.get("forced_termination") is not False or sup.get("session_members_killed_at_cleanup") is not False:
        bad.append("execution was not a clean natural exit")
    ml, env = load("model_load.json"), load("environment.json")
    if not (wt.get("mode") == sup.get("mode") == plan["mode"] and wt.get("backend", plan["backend"]) == plan["backend"]
            and (ml is None or ml.get("backend") == plan["backend"])):
        bad.append("mode or backend differs between plan and records")
    if plan["mode"] == "PRODUCTION" and not (env and env.get("cuda_available") and ml
                                            and ml.get("device") == "cuda"):
        bad.append("production attempt did not run on CUDA")
    if plan["mode"] != "PRODUCTION" and not accept_test:
        bad.append("TEST attempt")
    if plan["mode"] == "PRODUCTION" and (plan["backend"] != "vint"
                                        or plan["manifest_sha256"] != PINNED["manifest_sha256"]):
        bad.append("production attempt not pinned")
    raw = _read_bytes(plan["manifest"])
    if sha_bytes(raw) != plan["manifest_sha256"]:
        return False, [*bad, "manifest changed since the attempt"]
    try:
        calls = json.loads(raw)["calls"]
        if not isinstance(calls, list):
            raise TypeError("calls is not a list")
    except (ValueError, KeyError, TypeError) as exc:
        return False, [*bad, f"manifest unreadable: {exc}"]
    if plan["mode"] == "PRODUCTION" and len(calls) != PINNED["calls"]:
        bad.append(f"{len(calls)} manifest calls; acceptance requires exactly {PINNED['calls']}")
    rpath = os.path.join(attempt, "results.jsonl")
    if not os.path.exists(rpath):
        return False, [*bad, "no results"]
    if wt.get("results_sha256") != sha_file(rpath):
        bad.append("results differ from the terminal digest")
    lines = _read_text(rpath).splitlines()
    if len(lines) != len(calls):
        bad.append(f"{len(lines)} results for {len(calls)} calls")
    for i, (line, c) in enumerate(zip(lines, calls, strict=False)):  # length checked above
        try:
            r = json.loads(line)
        except ValueError:
            bad.append(f"line {i} unreadable")
            continue
        ok = (r["call_id"] == c["call_id"] == i and r["arm"] == c["arm"]
              and r["query_id"] == c["query_id"] and r["repeat"] == c["repeat"]
              and r["obs_sha256"] == [f["sha256"] for f in c["obs"]]
              and r["batch_sha256"] == [f["sha256"] for f in c["batch_rows"]]
              and len(r["d_all"]) == len(c["batch_rows"])
              and all(math.isfinite(x) for x in r["d_all"])
              and r["score"] == r["d_all"][c["goal_row_index"]])
        if not ok:
            bad.append(f"result {i} does not match call {c['call_id']}")
    if wt.get("forwards_listed") != len(calls) or wt.get("forwards_hooked") != len(calls):
        bad.append("forward counters differ from the call count")
    for name in ("preflight.json", "environment.json", "model_load.json"):
        if load(name) is None:
            bad.append(f"missing {name}")
    if expected_runner_sha256 is not None and plan.get("runner_sha256") != expected_runner_sha256:
        bad.append("attempt runner digest differs from the expected frozen digest")
    if plan["mode"] == "PRODUCTION":
        if expected_runner_sha256 is None:
            bad.append("production admission requires --expected-runner-sha256")
        pre = load("preflight.json") or {}
        origins = set((ml or {}).get("module_origins", {}))
        try:
            results = [json.loads(x) for x in lines if x.strip()]
        except ValueError:
            results = []  # unreadable lines were already recorded above
        checks = {
            "plan pins differ from this runner's": plan.get("pinned") != json.loads(json.dumps(PINNED)),
            "attempt ran a different runner file": plan.get("runner_sha256") != sha_file(os.path.abspath(__file__)),
            "preflight checkpoint digest is not the pinned one":
                pre.get("checkpoint_sha256") != PINNED["checkpoint_sha256"],
            "environment lacks a CUDA device record": not (env or {}).get("device_name"),
            "ViNT and loader modules were not loaded from staged source":
                not {"navfm.models.loader", "vint_train.models.vint.vint"} <= origins,
            "results lack CUDA allocator statistics":
                not results or not all("max_memory_reserved" in r.get("memory", {}) for r in results),
            "the memory guard never observed the worker process": not sup.get("gpu_process_samples_present"),
        }
        bad += [k for k, v in checks.items() if v]
    return not bad, bad


def record_hashes(attempt):
    """sha256 of every file in the attempt, for out-of-band recording right after the run."""
    out = {}
    for root, _, names in os.walk(attempt):
        for n in sorted(names):
            p = os.path.join(root, n)
            out[os.path.relpath(p, attempt)] = sha_file(p)
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- analysis
def _q(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    pos = (len(xs) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _dist(xs):
    return dict(n=len(xs), p10=_q(xs, .1), p25=_q(xs, .25), median=_q(xs, .5), p75=_q(xs, .75),
                p90=_q(xs, .9), max_abs=max((abs(x) for x in xs), default=None))


def analyse(attempt, accept_test=False, expected_runner_sha256=None):
    ok, reasons = admit(attempt, accept_test, expected_runner_sha256)
    if not ok:
        raise SystemExit(f"not admitted: {reasons}")
    plan = _read_json(os.path.join(attempt, "plan.json"))
    man = _read_json(plan["manifest"])
    res = [json.loads(x) for x in _read_text(os.path.join(attempt, "results.jsonl")).splitlines()]
    out = analyse_records(man, res, plan["mode"])
    out["attempt_record_sha256"] = record_hashes(attempt)
    return out


def analyse_records(man, res, mode):
    """Pre-declared reporting over admitted results (pure; unit-tested on synthetic records)."""
    q = {x["query_id"]: x for x in man["queries"]}
    ep = {k: f"{x['variant']}/{x['route']}" for k, x in q.items()}
    ref = man["summary"]["reference_scale_inregion_consecutive_abs_change"]
    h0 = {r["query_id"]: r["score"] for r in res if r["arm"] == "H0_real" and r["repeat"] == 0}
    out = dict(mode=mode, label="replay regime; JPEG inputs; replay environment")

    # Replay agreement with logged deployed outputs (prospective criterion, not equivalence)
    gaps = {k: h0[k] - q[k]["logged_requested_goal_distance"] for k in q}
    disagree = [k for k in q if (h0[k] <= THRESHOLD) != (q[k]["logged_requested_goal_distance"] <= THRESHOLD)]
    med = _q([abs(g) for g in gaps.values()], .5)
    out["replay_agreement"] = dict(
        per_query={k: dict(logged=q[k]["logged_requested_goal_distance"], replay=h0[k], gap=gaps[k],
                           logged_accept=q[k]["logged_requested_goal_distance"] <= THRESHOLD,
                           replay_accept=h0[k] <= THRESHOLD) for k in sorted(q)},
        gap_distribution=_dist(list(gaps.values())),
        abs_gap_distribution=_dist([abs(g) for g in gaps.values()]),
        per_episode={e: _dist([gaps[k] for k in q if ep[k] == e]) for e in sorted(set(ep.values()))},
        gate_agreement=dict(agree=len(q) - len(disagree), disagree=sorted(disagree), n=len(q)),
        criterion=dict(rule="median |gap| <= 0.085", median_abs_gap=med, met=med <= 0.085,
                       meaning="replay reproduces logged outputs to the declared tolerance at the "
                               "median; it does not establish deployment equivalence"))

    # Numerical controls
    reps = {}
    for r in res:
        if r["arm"] == "H0_real":
            reps.setdefault(r["query_id"], []).append(r["score"])
    triples = {k: v for k, v in reps.items() if len(v) == 3}
    n_repeat = max((max(v) - min(v) for v in triples.values()), default=None)
    out["numerical"] = dict(
        N_repeat=n_repeat, repeat_triples=len(triples),
        repeats_bit_identical=all(len(set(v)) == 1 for v in triples.values()),
        N_batch={r["query_id"]: r["score"] - h0[r["query_id"]] for r in res if r["arm"] == "CTRL_goal_only"},
        N_order={r["query_id"]: r["score"] - h0[r["query_id"]] for r in res if r["arm"] == "CTRL_reversed_node_rows"},
        note="batch composition and row order are held fixed within each pair (controlled factor); "
             "this does not guarantee identical numerical error across different history inputs")

    # Paired history substitutions
    arms = {}
    for arm in ARMS_PAIRED:
        rows = [r for r in res if r["arm"] == arm]
        per = []
        for r in rows:
            k = r["query_id"]
            d = r["score"] - h0[k]
            margin = abs(h0[k] - THRESHOLD)  # replay margin: flips are judged against H0 replay
            margin_logged = abs(q[k]["logged_requested_goal_distance"] - THRESHOLD)  # v3 definition
            per.append(dict(query_id=k, episode=ep[k], delta=d, h0=h0[k], arm=r["score"],
                            margin_h0=margin, delta_over_margin=(d / margin) if margin else None,
                            margin_logged=margin_logged,
                            delta_over_margin_logged=(d / margin_logged) if margin_logged else None,
                            delta_over_episode_ref=d / ref[ep[k]]["median"],
                            flip=("accept_to_reject" if h0[k] <= THRESHOLD < r["score"] else
                                  "reject_to_accept" if r["score"] <= THRESHOLD < h0[k] else None),
                            exceeds_N_repeat=(abs(d) > n_repeat) if n_repeat is not None else None))
        summ = {}
        for key, sel in [(e, lambda p, e=e: p["episode"] == e) for e in sorted(set(ep.values()))] + \
                [(rt, lambda p, rt=rt: p["episode"].endswith(rt)) for rt in ("junction_run_0000", "junction_run_0001")]:
            ps = [p for p in per if sel(p)]
            summ[key] = dict(delta=_dist([p["delta"] for p in ps]),
                             delta_over_episode_ref=_dist([p["delta_over_episode_ref"] for p in ps]),
                             delta_over_margin=_dist([p["delta_over_margin"] for p in ps
                                                      if p["delta_over_margin"] is not None]),
                             delta_over_margin_logged=_dist([p["delta_over_margin_logged"] for p in ps
                                                             if p["delta_over_margin_logged"] is not None]),
                             flips_accept_to_reject=sum(p["flip"] == "accept_to_reject" for p in ps),
                             flips_reject_to_accept=sum(p["flip"] == "reject_to_accept" for p in ps),
                             n_exceeding_N_repeat=sum(bool(p["exceeds_N_repeat"]) for p in ps), n=len(ps))
        arms[arm] = dict(per_call=per, summary=summ)
    # H2 pair values: mean of both directions when mutual, otherwise the single direction
    d2 = {p["query_id"]: p for p in arms["H2_posematched_other_variant"]["per_call"]}
    pairs = {}
    for k, p in d2.items():
        m = q[k]["match"]
        other = f"{m['other_variant']}/{q[k]['route']}/k{m['k']:03d}"
        key = tuple(sorted([k, other]))
        pairs.setdefault(key, {})[k] = p["delta"]
    arms["H2_posematched_other_variant"]["pairs"] = [
        dict(pair=list(key), directions=v, value=sum(v.values()) / len(v), mutual=len(v) == 2)
        for key, v in sorted(pairs.items())]
    out["arms"] = arms
    return out


# --------------------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--manifest", required=True)
    r.add_argument("--manifest-sha256", required=True)
    r.add_argument("--attempt-dir", required=True)
    r.add_argument("--evidence-root", required=True)
    r.add_argument("--backend", default="vint")
    r.add_argument("--test-mode", action="store_true")
    r.add_argument("--wall-limit-s", type=float)
    r.add_argument("--test-sampler-cmd")
    w = sub.add_parser("_worker")
    w.add_argument("attempt")
    a = sub.add_parser("admit")
    a.add_argument("--attempt-dir", required=True)
    a.add_argument("--accept-test", action="store_true")
    a.add_argument("--expected-runner-sha256")
    h = sub.add_parser("hashes")
    h.add_argument("--attempt-dir", required=True)
    h.add_argument("--out", required=True)
    n = sub.add_parser("analyse")
    n.add_argument("--attempt-dir", required=True)
    n.add_argument("--out", required=True)
    n.add_argument("--accept-test", action="store_true")
    n.add_argument("--expected-runner-sha256")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        if args.test_mode is False and (args.wall_limit_s is not None or args.test_sampler_cmd):
            print("overrides are test-only")
            return 2
        return supervise(args)
    if args.cmd == "_worker":
        return worker(args.attempt)
    if args.cmd == "hashes":
        # Run immediately after `run`; --out must be outside the attempt directory.
        if os.path.commonpath([os.path.abspath(args.out), os.path.abspath(args.attempt_dir)]) == \
                os.path.abspath(args.attempt_dir):
            print("--out must be outside the attempt directory")
            return 2
        rec = dict(attempt=os.path.abspath(args.attempt_dir), recorded_unix=time.time(),
                   files=record_hashes(args.attempt_dir))
        with open(args.out, "x") as f:
            json.dump(rec, f, indent=1, sort_keys=True)
        print(sha_file(args.out))
        return 0
    if args.cmd == "admit":
        ok, reasons = admit(args.attempt_dir, args.accept_test, args.expected_runner_sha256)
        print(json.dumps(dict(admitted=ok, reasons=reasons)))
        return 0 if ok else 1
    out = analyse(args.attempt_dir, args.accept_test, args.expected_runner_sha256)
    with open(args.out, "x") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
