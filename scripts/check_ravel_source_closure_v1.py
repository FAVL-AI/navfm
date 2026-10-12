"""Actual production source/FAISS/pruning CPU boundary check, no matching models."""

import copy
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import get_type_hints

from ravel_fixed_graph_v1 import CONFIG, load_native, native_main, observe_native_counter
from recorded_rgb_stop_v1 import reject_python_network


def main():
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("CUDA must be hidden for source closure")
    sys.addaudithook(reject_python_network)
    started = time.monotonic()
    import faiss
    import numpy as np
    import torch

    assert not torch.cuda.is_available()
    cfg = json.loads(CONFIG.read_text())
    controls = []
    sys.modules["kornia"] = None
    try:
        load_native(cfg)
    except ModuleNotFoundError:
        controls.append("actual_missing_kornia_dependency")
    else:
        raise AssertionError("missing dependency admitted")
    del sys.modules["kornia"]
    native = load_native(cfg)
    assert get_type_hints(native.analyzer.run_parameter_analysis)["args"].__name__ == "Namespace"
    folder = Path(sys.argv[1]).parent / "cpu_artifacts"
    folder.mkdir(parents=True, exist_ok=False)
    altered = folder / "altered.py"
    row = cfg["sources"]["build_matrix"]
    altered.write_bytes(Path(row["local_path"]).read_bytes() + b"\n# alteration\n")
    bad = copy.deepcopy(cfg)
    bad["sources"]["build_matrix"]["local_path"] = str(altered)
    try:
        load_native(bad)
    except ValueError:
        controls.append("altered_native_source_bytes")
    else:
        raise AssertionError("altered source admitted")
    features = np.array([[1, 0], [0, 1], [-1, 0], [0.6, 0.8]], dtype=np.float32)
    np.save(folder / "features.npy", features)
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
    index = faiss.read_index(str(folder / "index.faiss"))
    lims, distances, ids = index.range_search(features[:1], 2.0)
    assert set(ids.tolist()) == {0, 3}
    assert lims.tolist() == [0, 2] and np.all(distances < 2)
    controls.append("native_flat_squared_L2_radius2_boundary_not_all_pairs")
    matrix = np.zeros((5, 5), dtype=np.uint16)
    for i, j, weight in [(0, 1, 400), (1, 2, 350), (0, 2, 300), (0, 3, 390), (1, 3, 301)]:
        matrix[i, j] = matrix[j, i] = weight
    np.save(folder / "matrix.npy", matrix)
    (folder / "paths.txt").write_text("".join(f"node{i}.jpg\n" for i in range(5)))
    native_main(
        native.prune,
        [
            "--weighted_matrix",
            folder / "matrix.npy",
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
    pruned = np.load(folder / "pruned.npy", allow_pickle=False)
    assert pruned.shape == (5, 5) and not pruned[4].any()
    assert pruned[0, 2] == 0 and pruned[1, 3] == 301
    assert np.array_equal(pruned, pruned.T) and not np.diag(pruned).any()
    controls.append("native_pruning_strict300_301_and_isolated_node")
    from PIL import Image

    image = folder / "synthetic.jpg"
    Image.new("RGB", (8, 8)).save(image)

    class FailingPreprocessor:
        def extract(self, tensor):
            raise RuntimeError("synthetic preprocessing failure outside model forward")

    counter = native.analyzer.create_general_match_counter(
        [image, image], False, torch.device("cpu"), FailingPreprocessor(), object()
    )
    observed = []
    stats = dict(technical_failures=0)
    checked = observe_native_counter(counter, observed.append, stats)
    assert checked(0, 1) == 0
    assert stats["technical_failures"] == 1
    assert observed[0]["exception_type"] == "RuntimeError"
    assert sys.gettrace() is None
    controls.append("native_swallowed_preprocessing_error_observed_without_changing_zero")
    (folder / "swallowed_failure.json").write_text(json.dumps(observed, indent=2) + "\n")
    elapsed = time.monotonic() - started
    assert elapsed < 30
    result = dict(
        status="PASS_CPU_SOURCE_AND_SYNTHETIC_COMPONENT_BOUNDARIES_ONLY",
        controls=controls,
        matching_model_constructions=0,
        encoder_forwards=0,
        matching_forwards=0,
        cuda_visible=False,
        wall_s=elapsed,
        production_loader_sha256=hashlib.sha256(
            Path(__file__).with_name("ravel_fixed_graph_v1.py").read_bytes()
        ).hexdigest(),
    )
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
