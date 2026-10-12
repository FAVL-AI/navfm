"""Source-bound nondefault native RAVEL fixed-mode graph; no calibration or VPR calls."""

import argparse
import ast
import hashlib
import importlib.metadata
import inspect
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

from qualify_pinned_stop_interfaces_v1 import supervise_worker, write_json
from recorded_rgb_stop_v1 import (
    CONFIG as RGB_CONFIG,
)
from recorded_rgb_stop_v1 import (
    reject_python_network,
    source_module,
    validate_admission_fields,
    verify_file,
)

CONFIG = Path(__file__).resolve().parents[1] / "configs/eval/ravel_fixed_graph_v1.json"


def validate_contract(cfg):
    expected = dict(
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
    if cfg["native_mode"] != expected:
        raise ValueError("frozen native fixed-mode contract changed")
    if len(cfg["references"]) != 8 or [r["frame"] for r in cfg["references"]] != list(
        range(0, 32, 4)
    ):
        raise ValueError("fixed reference row/order changed")
    if len({r["path"] for r in cfg["references"]}) != 8:
        raise ValueError("duplicate reference identity")
    caps = dict(
        nodes=8,
        pairs=28,
        superpoint_forwards=56,
        lightglue_forwards=28,
        global_encoder_forwards=0,
        whole_worker_s=180,
        parent_wall_s=360,
        raw_output_acceptance_bytes=16777216,
    )
    if cfg["caps"] != caps:
        raise ValueError("frozen resource caps changed")
    for key, value in cfg["runtime"].items():
        if key != "overlay" and importlib.metadata.version(key) != value:
            raise ValueError("isolated runtime binding changed: " + key)


def load_native(cfg):
    """Actual production imports only; constructors/analysis/forwards are not invoked."""
    validate_contract(cfg)
    verify_file(cfg["source_metadata_path"], cfg["source_metadata_sha256"])
    for row in cfg["sources"].values():
        verify_file(row["local_path"], row["sha256"])
    package = types.ModuleType("lightglue")
    package.__path__ = []
    sys.modules["lightglue"] = package
    source_module(cfg["sources"]["utils"], "lightglue.utils")
    lg = source_module(cfg["sources"]["lightglue"], "lightglue.lightglue")
    sp = source_module(cfg["sources"]["superpoint"], "lightglue.superpoint")
    package.LightGlue, package.SuperPoint = lg.LightGlue, sp.SuperPoint
    analyzer = source_module(cfg["sources"]["analyze_parameters"], "analyze_parameters")
    build = source_module(cfg["sources"]["build_matrix"], "navfm_native_ravel_build")
    index = source_module(cfg["sources"]["build_index"], "navfm_native_ravel_index")
    prune = source_module(cfg["sources"]["prune_topomap_nx"], "navfm_native_ravel_prune")
    assert build.analyzer is analyzer
    assert analyzer.SuperPoint is sp.SuperPoint and analyzer.LightGlue is lg.LightGlue
    assert callable(analyzer.create_general_match_counter)
    return types.SimpleNamespace(
        analyzer=analyzer, build=build, index=index, prune=prune, sp=sp, lg=lg
    )


def native_main(module, args):
    previous = sys.argv
    try:
        sys.argv = [module.__file__, *map(str, args)]
        module.main()
    finally:
        sys.argv = previous


def admit_inputs(cfg, folder):
    import numpy as np

    rgb = json.loads(RGB_CONFIG.read_text())
    for key in ("admission", "finalization"):
        assert cfg[key] == rgb[key]
        verify_file(cfg[key]["path"], cfg[key]["sha256"])
    assert cfg["references"] == rgb["references"]
    validate_admission_fields(
        rgb,
        json.loads(Path(cfg["admission"]["path"]).read_text()),
        json.loads(Path(cfg["finalization"]["path"]).read_text()),
    )
    for row in cfg["references"]:
        verify_file(row["path"], row["sha256"])
    origin = cfg["descriptor_origin_result"]
    verify_file(origin["path"], origin["sha256"])
    record = json.loads(Path(origin["path"]).read_text())
    if (
        record["freeze"] != cfg["descriptor_origin_freeze"]
        or record["encoder_forwards"] != 32
        or record["status"] != "PASS_RECORDED_ENCODER_REFERENCE_MOCK_ONLY"
    ):
        raise ValueError("cached descriptor source outcome is not admitted")
    verify_file(cfg["descriptor_path"], cfg["descriptor_sha256"])
    with np.load(cfg["descriptor_path"], allow_pickle=False) as archive:
        features = archive["ulvn"][:8].copy()
    if (
        features.shape != (8, 8448)
        or features.dtype != np.float32
        or not np.isfinite(features).all()
    ):
        raise ValueError("admitted cached reference descriptors invalid")
    if not np.all(np.isclose(np.linalg.norm(features, axis=1), 1, atol=1e-5, rtol=0)):
        raise ValueError("admitted descriptor normalization invalid")
    np.save(folder / "features.npy", features)
    (folder / "paths.txt").write_text("".join(r["path"] + "\n" for r in cfg["references"]))
    write_json(
        folder / "node_map.json",
        dict(
            origin_freeze=cfg["descriptor_origin_freeze"],
            descriptor_sha256=cfg["descriptor_sha256"],
            nodes=cfg["references"],
        ),
    )


def observe_native_counter(counter, emit, stats):
    """Observe caught exceptions in the authenticated counter, preserving returns."""
    code = inspect.unwrap(counter).__code__

    def counted(*args):
        previous = sys.gettrace()
        if previous is not None:
            raise ValueError("external tracing is outside native qualification contract")

        def trace(frame, event, value):
            if frame.f_code is code:
                if event == "exception":
                    stats["technical_failures"] += 1
                    emit(
                        dict(
                            event="TECHNICAL_FAILURE",
                            kind="native_counter_caught_exception",
                            exception_type=value[0].__name__,
                        )
                    )
                return trace
            return None

        sys.settrace(trace)
        try:
            return counter(*args)
        finally:
            sys.settrace(previous)

    return counted


def verify_matcher_assets(cfg):
    for asset in ("superpoint_v1.pth", "superpoint_lightglue.pth"):
        row = cfg["weights"][asset]
        verify_file(row["local_path"], row["sha256"])


def checkpoint_structure(expected, parameters, buffers, supplied):
    return dict(
        missing_parameters=sorted(parameters.keys() - supplied.keys()),
        missing_buffers=sorted(buffers.keys() - supplied.keys()),
        unexpected_keys=sorted(supplied.keys() - expected.keys()),
        shape_mismatches={
            k: dict(expected=expected[k], supplied=supplied[k])
            for k in expected.keys() & supplied.keys()
            if expected[k] != supplied[k]
        },
    )


def checkpoint_admitted(missing_parameters, unexpected_keys):
    return not missing_parameters and not unexpected_keys


def native_remap_report(cfg, original_shapes, layers):
    row = cfg["sources"]["lightglue"]
    verify_file(row["local_path"], row["sha256"])
    parsed = ast.parse(Path(row["local_path"]).read_text())
    cls = next(
        node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == "LightGlue"
    )
    init = next(
        node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    loops = [
        node
        for node in ast.walk(init)
        if isinstance(node, ast.For)
        and any(isinstance(child, ast.Name) and child.id == "pattern" for child in ast.walk(node))
    ]
    if len(loops) != 1 or type(layers) is not int or not 1 <= layers <= 32:
        raise ValueError("native remap statement closure changed")
    code = compile(
        ast.fix_missing_locations(ast.Module(body=loops, type_ignores=[])),
        row["local_path"],
        "exec",
    )
    mapping = {}
    for original in original_shapes:
        namespace = dict(
            self=types.SimpleNamespace(conf=types.SimpleNamespace(n_layers=layers)),
            state_dict={original: original},
        )
        namespace["__builtins__"] = {"range": range}
        exec(code, namespace, namespace)
        mapped = namespace["state_dict"]
        if len(mapped) != 1:
            raise ValueError("native single-key remap changed")
        mapping[original] = next(iter(mapped))
    groups = {}
    for old, new in mapping.items():
        groups.setdefault(new, []).append(old)
    return dict(
        original_to_final=mapping, collisions={k: v for k, v in groups.items() if len(v) > 1}
    )


def native_matcher_constructor_preflight(native, cfg, emit):
    """Invoke exact authenticated native matcher constructor statements on CPU."""
    import torch

    verify_matcher_assets(cfg)
    stats = dict(superpoint=0, lightglue=0, technical_failures=0)
    configure_native_matcher_constructors(
        native, cfg, emit, stats, forward_caps=dict(superpoint=0, lightglue=0)
    )
    row = cfg["sources"]["analyze_parameters"]
    verify_file(row["local_path"], row["sha256"])
    parsed = ast.parse(Path(row["local_path"]).read_text())
    function = next(
        node
        for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_parameter_analysis"
    )
    assignments = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"extractor", "matcher"}
    ]
    if [node.targets[0].id for node in assignments] != ["extractor", "matcher"]:
        raise ValueError("native constructor statement closure changed")
    namespace = dict(
        SuperPoint=native.analyzer.SuperPoint,
        LightGlue=native.analyzer.LightGlue,
        args=types.SimpleNamespace(lightglue_weights="indoor"),
        device=torch.device("cpu"),
    )
    for assignment in assignments:
        emit(
            dict(
                event="CONSTRUCTOR_ATTEMPT",
                kind="superpoint" if assignment.targets[0].id == "extractor" else "lightglue",
                device="cpu",
            )
        )
        code = compile(
            ast.fix_missing_locations(ast.Module(body=[assignment], type_ignores=[])),
            row["local_path"],
            "exec",
        )
        exec(code, {"__builtins__": {}}, namespace)
    return namespace["extractor"], namespace["matcher"]


def configure_native_matcher_constructors(native, cfg, emit, stats, forward_caps=None):
    import torch

    class TorchTransport:
        def __getattr__(self, name):
            return getattr(torch, name)

        hub = types.SimpleNamespace()

    def local_weights(url, **kwargs):
        name = url.rsplit("/", 1)[-1]
        row = cfg["weights"].get(name)
        if row is None or url != row["url"]:
            raise ValueError("unbound native model download")
        verify_file(row["local_path"], row["sha256"])
        emit(dict(event="WEIGHT_LOAD", asset=name, sha256=row["sha256"]))
        return torch.load(row["local_path"], map_location="cpu", weights_only=True)

    TorchTransport.hub.load_state_dict_from_url = local_weights
    native.sp.torch = TorchTransport()
    native.lg.torch = TorchTransport()

    def observed_class(base, kind, cap):
        class Observed(base):
            def load_state_dict(self, state, *args, **kwargs):
                self.load_sequence = getattr(self, "load_sequence", 0) + 1
                parameters = {k: list(v.shape) for k, v in self.named_parameters()}
                buffers = {k: list(v.shape) for k, v in self.named_buffers()}
                expected = {k: list(v.shape) for k, v in self.state_dict().items()}
                supplied = {k: list(v.shape) for k, v in state.items()}
                if self.load_sequence == 1:
                    self.original_checkpoint_shapes = supplied
                effective = self.conf if isinstance(self.conf, dict) else vars(self.conf)
                detail = dict(
                    event="STATE_LOAD_DIAGNOSTIC",
                    kind=kind,
                    sequence=self.load_sequence,
                    strict=kwargs.get("strict", args[0] if args else True),
                    parameter_shapes=parameters,
                    buffer_shapes=buffers,
                    checkpoint_shapes=supplied,
                    effective_config=effective,
                    source_sha256=cfg["sources"][kind]["sha256"],
                    checkpoint_sha256=cfg["weights"][
                        "superpoint_v1.pth" if kind == "superpoint" else "superpoint_lightglue.pth"
                    ]["sha256"],
                )
                detail.update(checkpoint_structure(expected, parameters, buffers, supplied))
                if kind == "lightglue":
                    detail["native_remap"] = native_remap_report(
                        cfg, self.original_checkpoint_shapes, self.conf.n_layers
                    )
                emit(detail)  # Durable before native load can fail on shapes.
                try:
                    result = super().load_state_dict(state, *args, **kwargs)
                except Exception as exc:
                    emit(
                        dict(
                            event="STATE_LOAD_REFUSED",
                            kind=kind,
                            sequence=self.load_sequence,
                            exception_type=type(exc).__name__,
                            reason=str(exc)[:500],
                        )
                    )
                    raise
                self.last_load = result
                emit(
                    dict(
                        event="STATE_LOAD_RESULT",
                        kind=kind,
                        sequence=self.load_sequence,
                        missing_keys=result.missing_keys,
                        unexpected_keys=result.unexpected_keys,
                    )
                )
                return result

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                missing = set(self.last_load.missing_keys) & dict(self.named_parameters()).keys()
                emit(
                    dict(
                        event="FINAL_ADMISSION_DIAGNOSTIC",
                        kind=kind,
                        missing_parameters=sorted(missing),
                        missing_buffers=sorted(
                            set(self.last_load.missing_keys) & dict(self.named_buffers()).keys()
                        ),
                        unexpected_keys=self.last_load.unexpected_keys,
                        admitted=checkpoint_admitted(missing, self.last_load.unexpected_keys),
                    )
                )
                if not checkpoint_admitted(missing, self.last_load.unexpected_keys):
                    raise ValueError("native final checkpoint coverage incomplete")
                emit(
                    dict(
                        event="MODEL_CONSTRUCTED",
                        kind=kind,
                        missing_buffers=self.last_load.missing_keys,
                        unexpected_keys=self.last_load.unexpected_keys,
                    )
                )

            def forward(self, *args, **kwargs):
                if stats[kind] >= cap:
                    stats["technical_failures"] += 1
                    raise ValueError("native matching forward cap exceeded")
                stats[kind] += 1
                try:
                    result = super().forward(*args, **kwargs)
                except Exception:
                    stats["technical_failures"] += 1
                    emit(dict(event="TECHNICAL_FAILURE", kind=kind))
                    raise
                emit(dict(event="FORWARD_COMPLETE", kind=kind, count=stats[kind]))
                return result

        return Observed

    native.analyzer.SuperPoint = observed_class(
        native.sp.SuperPoint, "superpoint", (forward_caps or {}).get("superpoint", 56)
    )
    native.analyzer.LightGlue = observed_class(
        native.lg.LightGlue, "lightglue", (forward_caps or {}).get("lightglue", 28)
    )
    return native.analyzer.SuperPoint, native.analyzer.LightGlue


def instrument_models(native, cfg, emit, stats):
    configure_native_matcher_constructors(native, cfg, emit, stats)
    original = native.analyzer.create_general_match_counter
    seen = set()

    def counter_factory(*args, **kwargs):
        counter = observe_native_counter(original(*args, **kwargs), emit, stats)

        def counted(i, j):
            if not (0 <= i < j < 8) or (i, j) in seen or len(seen) >= 28:
                stats["technical_failures"] += 1
                raise ValueError("native candidate pair identity/budget changed")
            seen.add((i, j))
            stats["pairs"] += 1
            emit(dict(event="PAIR_STARTED", i=int(i), j=int(j)))
            count = counter(i, j)
            emit(dict(event="PAIR_RESULT", i=int(i), j=int(j), match_count=int(count)))
            return count

        return counted

    def observed_call(function, kind):
        def call(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except Exception:
                stats["technical_failures"] += 1
                emit(dict(event="TECHNICAL_FAILURE", kind=kind))
                raise

        return call

    native.analyzer.load_image = observed_call(native.analyzer.load_image, "image_decode")
    real_cv2 = native.analyzer.cv2

    class CV2Observation:
        def __getattr__(self, name):
            return getattr(real_cv2, name)

        findFundamentalMat = staticmethod(
            observed_call(real_cv2.findFundamentalMat, "fundamental_matrix")
        )

    native.analyzer.cv2 = CV2Observation()
    real_faiss = native.analyzer.faiss

    class IndexObservation:
        def __init__(self, index):
            self.index = index

        def __getattr__(self, name):
            return getattr(self.index, name)

        def range_search(self, query, radius):
            try:
                result = self.index.range_search(query, radius)
            except Exception:
                stats["technical_failures"] += 1
                emit(dict(event="TECHNICAL_FAILURE", kind="range_search"))
                raise
            emit(
                dict(
                    event="RANGE_RESULT",
                    row=stats["range_rows"],
                    radius=radius,
                    candidates=result[2].tolist(),
                    squared_distances=result[1].tolist(),
                )
            )
            stats["range_rows"] += 1
            return result

    class FAISSObservation:
        def __getattr__(self, name):
            return getattr(real_faiss, name)

        @staticmethod
        def read_index(path):
            return IndexObservation(real_faiss.read_index(path))

    native.analyzer.faiss = FAISSObservation()
    analysis = native.analyzer.run_parameter_analysis

    def fixed_analysis(args):
        if args.num_clusters != 1 or args.disable_ransac:
            raise ValueError("native fixed-mode admission changed")
        result = analysis(args)
        if result[0:2] != (0.0, 2.0) or result[5] != 8:
            raise ValueError("native fixed-mode returned unexpected parameters/node count")
        emit(dict(event="FIXED_PARAMETERS", tau=result[0], radius=result[1], nodes=result[5]))
        return result

    native.analyzer.run_parameter_analysis = fixed_analysis
    native.analyzer.create_general_match_counter = counter_factory
    native.analyzer.KMeans = lambda *a, **kw: (_ for _ in ()).throw(ValueError("fitting forbidden"))


def run_graph(cfg, folder, emit):
    import numpy as np
    import torch

    native = load_native(cfg)
    admit_inputs(cfg, folder)
    if not torch.cuda.is_available():
        raise RuntimeError("declared GPU unavailable; no automatic CPU substitution")
    stats = dict(
        superpoint=0, lightglue=0, technical_failures=0, global_encoder=0, range_rows=0, pairs=0
    )
    torch.cuda.reset_peak_memory_stats()
    instrument_models(native, cfg, emit, stats)
    native_main(
        native.index,
        [
            "--features",
            folder / "features.npy",
            "--out",
            folder / "index.faiss",
            "--type",
            "flat",
            "--metric",
            "l2",
        ],
    )
    native_main(
        native.build,
        [
            "--features_path",
            folder / "features.npy",
            "--index_path",
            folder / "index.faiss",
            "--paths_txt",
            folder / "paths.txt",
            "--num_clusters",
            "1",
            "--num_threads",
            "1",
            "--out_plot_path",
            folder / "unused_fixed_mode_analysis.png",
            "--result_dir",
            folder,
        ],
    )
    if stats["technical_failures"] or stats["range_rows"] != 8:
        raise RuntimeError("native matching caught technical failures; graph not qualified")
    events = [json.loads(line) for line in (folder / "partial.jsonl").read_text().splitlines()]
    ranges = {row["row"]: row["candidates"] for row in events if row["event"] == "RANGE_RESULT"}
    counts = {
        (row["i"], row["j"]): row["match_count"] for row in events if row["event"] == "PAIR_RESULT"
    }
    decisions = []
    for i in range(8):
        for j in range(i + 1, 8):
            if j not in ranges[i]:
                status = "EXCLUDED_NATIVE_RADIUS"
            elif (i, j) not in counts:
                raise ValueError("native candidate lacks complete match outcome")
            else:
                status = "ACCEPTED_COUNT_GT_ZERO" if counts[i, j] > 0 else "REJECTED_COUNT_ZERO"
            decisions.append(dict(i=i, j=j, status=status, match_count=counts.get((i, j))))
    write_json(folder / "pair_decisions.json", decisions)
    native_main(
        native.prune,
        [
            "--weighted_matrix",
            folder / "adjacency_matrix.npy",
            "--paths_txt",
            folder / "paths.txt",
            "--out_matrix_path",
            folder / "pruned.npy",
            "--out_viz_path",
            folder / "pruned.png",
            "--add_back_threshold",
            "300",
        ],
    )
    for path in (folder / "adjacency_matrix.npy", folder / "pruned.npy"):
        matrix = np.load(path, allow_pickle=False)
        if (
            matrix.shape != (8, 8)
            or not np.array_equal(matrix, matrix.T)
            or np.any(np.diag(matrix))
        ):
            raise ValueError("native graph/node-map invariant failed")
    stats["peak_GPU_allocated_bytes"] = torch.cuda.max_memory_allocated()
    stats["device"] = torch.cuda.get_device_name(0)
    return stats


def accept_worker_outcome(outcome, valid):
    """Timeout veto is independent of child exit and evidence acceptance."""
    return bool(valid and outcome["exit_code"] == 0 and not outcome["timeout"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != args.freeze or subprocess.check_output(["git", "status", "--porcelain"], text=True):
        raise ValueError("exact clean freeze required")
    if cfg["status"] != "FROZEN_NATIVE_FIXED_GRAPH_V1":
        raise ValueError("native graph protocol must be frozen before matching")
    folder = args.out.parent
    if args.worker:
        started = time.monotonic()
        sys.addaudithook(reject_python_network)

        def emit(event):
            with (folder / "partial.jsonl").open("a") as stream:
                stream.write(json.dumps(event) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

        try:
            stats = run_graph(cfg, folder, emit)
            write_json(
                args.out,
                dict(
                    status="PASS_NATIVE_FIXED_GRAPH_ONLY",
                    freeze=head,
                    stats=stats,
                    wall_s=time.monotonic() - started,
                    adaptive_RAVEL="NOT_QUALIFIED_NONDEFAULT_FIXED_MODE",
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
    write_json(
        folder / "attempt.json",
        dict(
            status="STARTED",
            freeze=head,
            config_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
            caps=cfg["caps"],
        ),
    )
    with (folder / "worker.log").open("x") as log:
        outcome = supervise_worker(
            [sys.executable, __file__, "--worker", "--freeze", head, "--out", str(args.out)],
            log,
            cfg["caps"]["whole_worker_s"],
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
        and sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
        <= cfg["caps"]["raw_output_acceptance_bytes"]
    )
    outcome.update(status="PASS" if accept_worker_outcome(outcome, valid) else "FAIL", freeze=head)
    write_json(folder / "parent_status.json", outcome)
    print(json.dumps(outcome))
    raise SystemExit(0 if outcome["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
