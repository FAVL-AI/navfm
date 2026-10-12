"""Pinned recorded-RGB encoder/reference integration and mock STOP only; no navigation."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from pinned_stop_interfaces_v1 import DescriptorTensor, authenticated_module, native_arrival_rule
from qualify_pinned_stop_interfaces_v1 import supervise_worker, write_json

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "configs/eval/recorded_rgb_stop_v1.json"


class MockStop:
    """An explicit software adaptation; commands are never sent anywhere."""

    def __init__(self):
        self.reset("unstarted")

    def reset(self, episode):
        if not isinstance(episode, str) or not episode:
            raise ValueError("explicit episode required")
        self.episode, self.latched, self.canceled = episode, False, False
        self.pending, self.current, self.target = [], None, (0.0, 0.0)

    def observe(self, publication, episode):
        if episode != self.episode:
            raise ValueError("stale episode publication")
        if publication is not None and type(publication) is not bool:
            raise ValueError("boolean or absent publication required")
        if self.canceled:
            return {"status": "CANCELED", "new_mock_command": None, "latched": self.latched}
        command = None
        if publication is True and not self.latched:
            self.latched, command = True, "MOCK_STOP_ONLY"
            self.pending, self.current, self.target = [], None, (0.0, 0.0)
        return {"status": "MOCK_ONLY", "new_mock_command": command, "latched": self.latched}

    def cancel(self, episode):
        if episode != self.episode:
            raise ValueError("stale episode cancellation")
        self.canceled = True
        self.pending, self.current, self.target = [], None, (0.0, 0.0)

    def request_motion(self, target, episode):
        if episode != self.episode:
            raise ValueError("stale mock motion episode")
        if len(target) != 2 or not np.isfinite(target).all():
            raise ValueError("finite two-component mock target required")
        if self.latched or self.canceled:
            return "BLOCKED_MOCK_ONLY"
        self.pending.append(tuple(target))
        if self.current is None:
            self.current = self.pending.pop(0)
            self.target = self.current
        return "ACCEPTED_MOCK_ONLY"


def verify_file(path, digest):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    if h.hexdigest() != digest:
        raise ValueError("immutable input/source/weight digest mismatch")


def source_module(row, name, package=False):
    verify_file(row["local_path"], row["sha256"])
    spec = importlib.util.spec_from_file_location(
        name, row["local_path"], submodule_search_locations=[] if package else None
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def source_definitions(row, names, namespace):
    verify_file(row["local_path"], row["sha256"])
    parsed = ast.parse(Path(row["local_path"]).read_text())
    nodes = [
        n for n in parsed.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names
    ]
    if {n.name for n in nodes} != set(names):
        raise ValueError("native definition allowlist incomplete")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    tree = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(tree, row["local_path"], "exec"), namespace)
    return SimpleNamespace(**namespace)


ULVN_RGB_DEFINITIONS_V2 = frozenset(
    {"VPRModelBase", "MegaLocEmbeddings", "MyVPR", "build_transform"}
)
ULVN_RGB_GLOBALS_V2 = frozenset(
    {"np", "torch", "nn", "F", "transforms", "Image", "sys", "_torch_no_grad"}
)


def load_ulvn_rgb_definitions_v2(row, namespace):
    """Authenticated production definition closure; no construction or forward."""
    if namespace.keys() - ULVN_RGB_GLOBALS_V2:
        raise ValueError("native RGB globals outside fixed allowlist")
    missing = ULVN_RGB_GLOBALS_V2 - namespace.keys()
    if missing:
        raise ValueError("native RGB globals missing: " + ",".join(sorted(missing)))
    native = source_definitions(row, ULVN_RGB_DEFINITIONS_V2, dict(namespace))
    if native.MyVPR.__bases__ != (native.VPRModelBase,):
        raise ValueError("native RGB inheritance mismatch")
    return native


def validate_manifest(cfg):
    if cfg["navigation_authorized"] is not False or cfg["threshold_fitting"] is not False:
        raise ValueError("scope escalation refused")
    refs, queries = cfg["references"], cfg["queries"]
    if (
        len(refs) != 8
        or len(queries) != 8
        or [r["frame"] for r in refs] != list(range(0, 32, 4))
        or [r["frame"] for r in queries] != list(range(1, 33, 4))
    ):
        raise ValueError("fixed sequence/reference order drift")
    if (
        cfg["max_encoder_forwards"] != 32
        or cfg["graph_status"] != "FIXED_CHAIN_ADAPTATION_NATIVE_RAVEL_BLOCKED"
    ):
        raise ValueError("forward budget or native graph claim drift")


def reject_python_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("recorded replay refuses Python network access")


def validate_admission_fields(cfg, admission, finalization):
    if admission["status"] != "PASS" or admission["splits"]["train"] or admission["splits"]["test"]:
        raise ValueError("admitted DEV-only population required")
    if cfg["trajectory"] != sorted(admission["splits"]["dev"])[0]:
        raise ValueError("lexically frozen DEV selection drift")
    for item in cfg["references"] + cfg["queries"]:
        key = f"{cfg['trajectory']}/{item['frame']}.jpg"
        if (
            item["sha256"] != admission["dataset_file_sha256"].get(key)
            or Path(item["path"]) != Path(cfg["dataset_root"]) / key
        ):
            raise ValueError("selected RGB not bound to admitted identity")
    if (
        finalization["status"] != "COMPLETE"
        or finalization["freeze"] != admission["source_freeze"]
        or finalization["admission_sha256"] != cfg["admission"]["sha256"]
    ):
        raise ValueError("completed admission transaction required")


def encode_recorded(cfg, emit):
    import cv2
    import PIL
    import safetensors
    import torch
    import torchvision
    import torchvision.transforms as transforms
    from PIL import Image
    from safetensors.torch import load_file

    if (
        torch.__version__ != cfg["runtime"]["torch"]
        or torchvision.__version__ != cfg["runtime"]["torchvision"]
        or cv2.__version__ != cfg["runtime"]["cv2"]
        or PIL.__version__ != cfg["runtime"]["pillow"]
        or safetensors.__version__ != cfg["runtime"]["safetensors"]
        or np.__version__ != cfg["runtime"]["numpy"]
    ):
        raise ValueError("declared decoder/encoder runtime mismatch")
    if not torch.cuda.is_available():
        raise RuntimeError("declared CUDA encoder resource absent; no CPU substitution")
    device = torch.device("cuda:0")
    torch.cuda.reset_peak_memory_stats()
    s = cfg["encoder_sources"]
    package = types.ModuleType("navfm_recorded_cosplace")
    package.__path__ = []
    sys.modules[package.__name__] = package
    sub = types.ModuleType(package.__name__ + ".cosplace_model")
    sub.__path__ = []
    sys.modules[sub.__name__] = sub
    source_module(s["cos_layers"], sub.__name__ + ".layers")
    network = source_module(s["cos_network"], sub.__name__ + ".cosplace_network")
    # Only this module-local transport factory changes; torchvision is never patched.
    network.get_pretrained_torchvision_model = lambda name: getattr(
        torchvision.models, name.lower()
    )(weights=None)
    source_module(s["cos_base"], package.__name__ + ".base_model")
    wrapper = source_module(s["cos_wrapper"], package.__name__ + ".cosplace")
    verify_file(cfg["weights"]["placenav"]["path"], cfg["weights"]["placenav"]["sha256"])
    cos = wrapper.CosPlace.__new__(wrapper.CosPlace)
    torch.nn.Module.__init__(cos)
    cos.required_inputs = list(wrapper.CosPlace.required_inputs)
    cos.net = network.GeoLocalizationNet("EfficientNet_B0", 512)
    state = torch.load(cfg["weights"]["placenav"]["path"], map_location="cpu", weights_only=True)
    assert set(state) == set(cos.net.state_dict()), "CosPlace full state coverage missing"
    cos.net.load_state_dict(state, strict=True)
    cos = cos.eval().to(device)
    del state
    native_utils = source_definitions(
        s["cos_utils"],
        {"read_image", "get_image_transform"},
        {"cv2": cv2, "transforms": transforms},
    )
    cos_transform = native_utils.get_image_transform([85, 64])
    mega_source = source_module(s["megaloc"], "navfm_recorded_megaloc")
    verify_file(cfg["weights"]["ulvn"]["path"], cfg["weights"]["ulvn"]["sha256"])
    mega = mega_source.MegaLoc()
    state = load_file(cfg["weights"]["ulvn"]["path"], device="cpu")
    assert set(state) == set(mega.state_dict()), "MegaLoc full state coverage missing"
    mega.load_state_dict(state, strict=True)
    del state
    native_vpr = load_ulvn_rgb_definitions_v2(
        s["ulvn_ros"],
        {
            "np": np,
            "torch": torch,
            "nn": torch.nn,
            "F": torch.nn.functional,
            "transforms": transforms,
            "Image": Image,
            "sys": sys,
            "_torch_no_grad": torch.no_grad,
        },
    )
    embedding = native_vpr.MegaLocEmbeddings.__new__(native_vpr.MegaLocEmbeddings)
    torch.nn.Module.__init__(embedding)
    embedding.backbone, embedding.arch, embedding.out_dim = mega, "megaloc", 512
    embedding = embedding.eval().to(device)
    ulvn_transform = native_vpr.build_transform(320, 320, "megaloc")
    vpr = native_vpr.MyVPR(embedding, ulvn_transform, device)
    descriptors = {"placenav": [], "ulvn": []}
    calls = 0
    for role in ("references", "queries"):
        for item in cfg[role]:
            emit({"event": "RGB_START", "role": role, "frame": item["frame"]})
            verify_file(item["path"], item["sha256"])
            rgb = native_utils.read_image(Path(item["path"])).astype(np.uint8)
            pil = Image.open(item["path"]).convert("RGB")
            assert np.array_equal(rgb, np.asarray(pil)), "native RGB decoders disagree"
            with torch.no_grad():
                x = cos_transform(rgb).unsqueeze(0).to(device)
                c = cos({"image": x})["global_descriptor"].cpu().numpy()[0]
                if role == "references":
                    u = embedding(ulvn_transform(pil).unsqueeze(0).to(device)).cpu().numpy()[0]
                else:
                    u = vpr.encode(pil)
            calls += 2
            assert c.shape == (512,) and u.shape == (8448,) and c.dtype == u.dtype == np.float32
            assert np.isfinite(c).all() and np.isfinite(u).all()
            assert np.isclose(np.linalg.norm(c), 1, atol=1e-5, rtol=0) and np.isclose(
                np.linalg.norm(u), 1, atol=1e-5, rtol=0
            )
            descriptors["placenav"].append(c)
            descriptors["ulvn"].append(u)
            emit(
                {
                    "event": "RGB_ENCODED",
                    "role": role,
                    "frame": item["frame"],
                    "placenav_descriptor_sha256": hashlib.sha256(c.tobytes()).hexdigest(),
                    "ulvn_descriptor_sha256": hashlib.sha256(u.tobytes()).hexdigest(),
                }
            )
    assert calls == cfg["max_encoder_forwards"]
    # Goal reuses the already authenticated reference feature, applying MyVPR's extra normalization.
    goal = (
        torch.nn.functional.normalize(
            torch.from_numpy(descriptors["ulvn"][7]).unsqueeze(0).to(device), p=2, dim=1
        )
        .cpu()
        .numpy()[0]
    )
    torch.cuda.synchronize()
    peak = torch.cuda.max_memory_allocated()
    observed = {
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "opencv": cv2.__version__,
        "pillow": PIL.__version__,
        "safetensors": safetensors.__version__,
        "numpy": np.__version__,
        "python": sys.version.split()[0],
        "CUDA_build": torch.version.cuda,
        "device": torch.cuda.get_device_name(0),
    }
    return descriptors, goal, calls, peak, observed


def belief_replay(cfg, descriptors, goal, emit):
    source_cfg = json.loads(
        (REPO / "configs/eval/stop_interface_qualification_v1.json").read_text()
    )
    outputs = {}
    graph = np.zeros((8, 8), dtype=np.float64)
    for i in range(7):
        graph[i, i + 1] = 1
    for kind in ("placenav", "ulvn"):
        refs = np.stack(descriptors[kind][:8])
        queries = descriptors[kind][8:]
        spec = source_cfg["sources"][kind]
        native = authenticated_module(kind, spec["belief"]["local_path"], spec["belief"])
        rule = native_arrival_rule(kind, spec["terminal"]["local_path"], spec["terminal"])
        repeats = []
        for repetition in range(2):
            emit({"event": "BELIEF_RESET", "kind": kind, "repetition": repetition})
            planner, sticky = None, False
            mock = MockStop()
            mock.reset(f"{kind}-{repetition}")
            mock.request_motion((0.1, 0.0), mock.episode)
            mock.request_motion((0.05, 0.0), mock.episode)
            if kind == "placenav":
                filt = native.PlaceRecognitionTopologicalFilter(
                    lambda q: {"global_descriptor": DescriptorTensor(q)},
                    refs.copy(),
                    None,
                    delta=10,
                    window_lower=-1,
                    window_upper=2,
                )
            else:
                filt = native.PlaceRecognition(refs.copy(), graph.copy(), max_steps=3, delta=5)
                planner = native.BeliefAwareSubgoalSearch(graph.copy(), refs.copy(), None)
                actual_goal, _ = planner.initial_localize(goal.copy(), queries[0].copy())
                if actual_goal != 7:
                    raise ValueError(
                        "native RGB goal identity ambiguous/unrepresentable; no forced node"
                    )
                planner.plan_path()
            filt.initialize_model(queries[0])
            rows = []
            for i, query in enumerate(queries):
                node, confidence = filt.match(query)
                belief = filt.belief
                if (
                    not np.isfinite(belief).all()
                    or (belief < 0).any()
                    or not np.isclose(
                        belief.sum(), 1, atol=max(1e-12, 8 * np.finfo(belief.dtype).eps * 8)
                    )
                ):
                    raise ValueError(
                        "invalid native recorded belief; no inserted clipping/fallback"
                    )
                subgoal = None
                if planner is None:
                    publication = bool(rule(node, SimpleNamespace(goal_node_idx=7)))
                else:
                    subgoal = planner.next_subgoal(int(node), n_ahead=2, replan_if_offpath=True)[
                        "subgoal_idx"
                    ]
                    if subgoal is not None:
                        sticky = bool(rule(subgoal, 7, node, sticky))
                    publication = sticky if subgoal is not None else None
                mocked = mock.observe(publication, mock.episode)
                row = {
                    "MAP": int(node),
                    "confidence": float(confidence),
                    "belief_sha256": hashlib.sha256(belief.tobytes()).hexdigest(),
                    "subgoal": subgoal,
                    "native_publication": publication,
                    "mock": mocked,
                }
                rows.append(row)
                emit(
                    {
                        "event": "BELIEF_UPDATED",
                        "kind": kind,
                        "repetition": repetition,
                        "virtual_sequence": i,
                        "source_frame": cfg["queries"][i]["frame"],
                        "virtual_adapter_time_s": i / 4,
                        **row,
                    }
                )
            mock.cancel(mock.episode)
            assert mock.current is None and not mock.pending and mock.target == (0.0, 0.0)
            assert mock.request_motion((0.1, 0), mock.episode) == "BLOCKED_MOCK_ONLY"
            mock.reset("fresh")
            assert not mock.latched and not mock.canceled
            repeats.append(rows)
        assert repeats[0] == repeats[1], (
            "fresh belief/state replay differs; not an encoding determinism claim"
        )
        outputs[kind] = {"state_replays": 2, "query_updates": 16, "reset_parity": True}
    return outputs


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
        raise ValueError("exact clean freeze required")
    cfg = json.loads(CONFIG.read_text())
    validate_manifest(cfg)
    if args.out.resolve().is_relative_to(REPO):
        raise ValueError("fresh external output required")
    folder = args.out.parent
    if args.worker:
        started = time.monotonic()

        def emit(event):
            with (folder / "partial.jsonl").open("a") as f:
                f.write(json.dumps(event, allow_nan=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

        try:
            sys.addaudithook(reject_python_network)
            verify_file(cfg["admission"]["path"], cfg["admission"]["sha256"])
            verify_file(cfg["finalization"]["path"], cfg["finalization"]["sha256"])
            validate_admission_fields(
                cfg,
                json.loads(Path(cfg["admission"]["path"]).read_text()),
                json.loads(Path(cfg["finalization"]["path"]).read_text()),
            )
            desc, goal, calls, peak, observed = encode_recorded(cfg, emit)
            encoder_reserved = time.monotonic() - started
            assert encoder_reserved <= cfg["GPU_reserved_wall_cap_s"]
            np.savez(
                folder / "descriptors.npz",
                placenav=np.stack(desc["placenav"]),
                ulvn=np.stack(desc["ulvn"]),
                ulvn_goal=goal,
            )
            replay = belief_replay(cfg, desc, goal, emit)
            result = {
                "status": "PASS_RECORDED_ENCODER_REFERENCE_MOCK_ONLY",
                "freeze": head,
                "encoder_forwards": calls,
                "GPU_reserved_wall_s": encoder_reserved,
                "peak_GPU_allocated_bytes": peak,
                "runtime_observed": observed,
                "replay": replay,
                "native_graph": "BLOCKED_FIXED_CHAIN_ADAPTATION",
                "controller_STOP": "MOCK_ONLY_NO_ACTUATION",
                "wall_s": time.monotonic() - started,
            }
            write_json(args.out, result)
            write_json(folder / "worker_status.json", {"status": "PASS", "freeze": head})
        except Exception as exc:
            write_json(
                folder / "worker_status.json",
                {
                    "status": "FAIL",
                    "freeze": head,
                    "exception_type": type(exc).__name__,
                    "reason": str(exc)[:500],
                },
            )
            raise SystemExit(1) from None
        return
    if folder.exists():
        raise ValueError("one fresh attempt directory required")
    folder.mkdir(parents=True)
    write_json(
        folder / "attempt.json",
        {
            "status": "STARTED",
            "freeze": head,
            "configuration_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
            "encoder_forward_cap": 32,
        },
    )
    with (folder / "worker.log").open("x") as log:
        outcome = supervise_worker(
            [sys.executable, __file__, "--worker", "--freeze", head, "--out", str(args.out)],
            log,
            min(cfg["wall_cap_s"], cfg["GPU_reserved_wall_cap_s"]),
        )
    valid = False
    if (folder / "worker_status.json").exists() and args.out.exists():
        valid = (
            json.loads((folder / "worker_status.json").read_text())
            == {"status": "PASS", "freeze": head}
            and json.loads(args.out.read_text()).get("freeze") == head
        )
    output_bytes = sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
    valid = valid and output_bytes <= cfg["raw_output_byte_cap"]
    outcome.update(
        status="PASS" if outcome["exit_code"] == 0 and not outcome["timeout"] and valid else "FAIL",
        freeze=head,
        worker_source_status_verified=valid,
    )
    write_json(folder / "parent_status.json", outcome)
    print(json.dumps(outcome))
    raise SystemExit(0 if outcome["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
