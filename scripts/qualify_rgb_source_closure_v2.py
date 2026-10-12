"""CPU-only authenticated production-loader closure check; no encoder construction."""

import hashlib
import inspect
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import get_type_hints

from recorded_rgb_stop_v1 import (
    CONFIG,
    load_ulvn_rgb_definitions_v2,
    reject_python_network,
    source_definitions,
)


def main():
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("CPU closure check requires CUDA_VISIBLE_DEVICES empty")
    sys.addaudithook(reject_python_network)
    started = time.monotonic()
    import numpy as np
    import torch
    import torchvision.transforms as transforms
    from PIL import Image

    if torch.cuda.is_available():
        raise ValueError("CUDA must be hidden")
    cfg = json.loads(CONFIG.read_text())
    row = cfg["encoder_sources"]["ulvn_ros"]
    namespace = dict(
        np=np,
        torch=torch,
        nn=torch.nn,
        F=torch.nn.functional,
        transforms=transforms,
        Image=Image,
        sys=sys,
        _torch_no_grad=torch.no_grad,
    )
    native = load_ulvn_rgb_definitions_v2(row, namespace)
    assert native.MyVPR.__bases__ == (native.VPRModelBase,)
    assert get_type_hints(native.VPRModelBase.encode)["return"] is np.ndarray
    hints = get_type_hints(inspect.unwrap(native.MyVPR.encode))
    assert hints["image"] is Image.Image and hints["return"] is torch.Tensor
    assert callable(native.build_transform) and issubclass(
        native.MegaLocEmbeddings, torch.nn.Module
    )
    controls = []
    for missing in namespace:
        reduced = dict(namespace)
        del reduced[missing]
        try:
            load_ulvn_rgb_definitions_v2(row, reduced)
        except ValueError:
            controls.append("missing_global:" + missing)
        else:
            raise AssertionError("missing global accepted")
    try:
        source_definitions(row, {"MyVPR"}, namespace.copy())
    except NameError:
        controls.append("actual_missing_native_base")
    else:
        raise AssertionError("missing native base accepted")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "altered.py"
        path.write_bytes(Path(row["local_path"]).read_bytes() + b"\n# altered\n")
        altered = dict(row, local_path=str(path))
        try:
            load_ulvn_rgb_definitions_v2(altered, namespace)
        except ValueError:
            controls.append("altered_source_bytes")
        else:
            raise AssertionError("altered source accepted")
    result = dict(
        status="PASS_CPU_SOURCE_CLOSURE_ONLY",
        source_sha256=row["sha256"],
        loader_sha256=hashlib.sha256(
            Path(__file__).with_name("recorded_rgb_stop_v1.py").read_bytes()
        ).hexdigest(),
        controls=controls,
        encoder_forwards=0,
        model_constructions=0,
        cuda_visible=False,
        wall_s=time.monotonic() - started,
    )
    if result["wall_s"] > 30:
        raise RuntimeError("30-second CPU qualification cap exceeded")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
