"""CPU-only complete native imports and fixed batches; no model or optimizer construction."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path

from development_qualification_contracts_v1 import sha, write
from native_dependency_closure_v2 import (
    contract_digest,
    loaded_native_sources,
    verify_native_dependencies,
)

IMPORTS = (
    "vint_train.data.vint_dataset",
    "vint_train.data.pristine_loader",
    "vint_train.training.train_utils",
    "vint_train.training.train_eval_loop",
    "navfm.models.loader",
    "diffusion_policy.model.diffusion.conditional_unet1d",
    "diffusers.optimization",
    "warmup_scheduler",
    "vint_train.models.gnm.gnm",
    "vint_train.models.nomad.nomad",
    "vint_train.models.nomad.nomad_vint",
    "diffusers.training_utils",
    "diffusers.schedulers.scheduling_ddpm",
    "adapt_gnm_native_v1",
    "adapt_nomad_native_v1",
    "verify_r6_strict_load",
    "adapt_nomad_native_v3",
)


def capture_files(base, records):
    files = {x["path"]: x["sha256"] for x in base["files"]}
    files.update({x["source"]: x["sha256"] for x in records})
    roots = set()
    for row in records:
        path = Path(row["source"])
        if "site-packages" in path.parts:
            i = path.parts.index("site-packages")
            roots.add(Path(*path.parts[: i + 2]))
    for root in sorted(roots):
        if root.is_dir():
            for f in root.rglob("*"):
                path = str(f.resolve())
                if (
                    f.is_file()
                    and f.suffix in (".py", ".so")
                    and "__pycache__" not in f.parts
                    and path not in files
                ):
                    files[path] = sha(f)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--capture-manifest", action="store_true")
    a = parser.parse_args()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("CPU preflight requires CUDA hidden")
    if a.out.exists():
        raise ValueError("fresh CPU report required")
    cfg = json.loads(a.config.read_text())

    def phase(name):
        with a.out.with_suffix(".phases.jsonl").open("a") as f:
            f.write(json.dumps({"phase": name, "monotonic_s": time.monotonic()}) + "\n")
            f.flush()
            os.fsync(f.fileno())

    phase("ENTRY")
    report = {
        "status": "STARTED",
        "python": sys.executable,
        "models": ["nomad"],
        "errors": [],
        "imports": [],
    }
    try:
        for row in cfg["inputs"]:
            if sha(Path(row["path"])) != row["sha256"]:
                raise ValueError("input drift")
        for row in cfg["upstream_files"]:
            if sha(Path(cfg["upstream"]) / row["path"]) != row["sha256"]:
                raise ValueError("upstream drift")
        from nomad_dependency_boundary_v6 import install_boundary, verify_loaded_dependencies

        install_boundary(cfg["diffusion_root"], cfg["diffusion_files"])
        from navfm import upstream

        upstream.ensure_upstream()
        for name in IMPORTS:
            phase("IMPORT:" + name)
            try:
                importlib.import_module(name)
                report["imports"].append(name)
            except Exception as exc:
                report["errors"].append(
                    {"module": name, "type": type(exc).__name__, "error": str(exc)}
                )
        import torch
        from native_adaptation_worker_v3 import fixed_batch, verify_upstream

        report["batches"] = {}
        for model in report["models"]:
            for partition in ("train", "development"):
                try:
                    phase("BATCH:" + model + "/" + partition)
                    batch, details = fixed_batch(
                        cfg, upstream.model_config(model), partition, torch, device="cpu"
                    )
                    if any(x.device.type != "cpu" for x in batch):
                        raise ValueError("CPU-only batch required")
                    report["batches"][model + "/" + partition] = details
                except Exception as exc:
                    report["errors"].append(
                        {
                            "batch": model + "/" + partition,
                            "type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
        from native_ema_integration_v3 import cpu_ema_control

        phase("CPU_EMA_CONTROL")
        report["ema_control"] = cpu_ema_control(cfg["ema_integration"])
        base = json.loads(Path(cfg["installed_dependency_manifest"]).read_text())
        report["selected_dependencies"] = verify_loaded_dependencies(base)
        report["upstream"] = verify_upstream(cfg)
        if a.capture_manifest:
            target = Path(cfg["native_dependency_manifest"])
            if target.exists():
                raise ValueError("fresh dependency snapshot required")
            records = loaded_native_sources()
            phase("SNAPSHOT_UNIQUE_ROOTS")
            files = capture_files(base, records)
            write(
                target,
                {
                    "files": [{"path": p, "sha256": h} for p, h in sorted(files.items())],
                    "loaded": records,
                },
            )
        phase("VERIFY_NATIVE_CLOSURE")
        report["native_dependencies"] = verify_native_dependencies(cfg)
        report["configuration_digest"] = contract_digest(cfg)
        report["status"] = "FAIL" if report["errors"] else "PASS"
    except Exception as exc:
        report["errors"].append({"type": type(exc).__name__, "error": str(exc)})
        report["status"] = "FAIL"
    finally:
        write(a.out, report)
    if report["status"] != "PASS":
        raise RuntimeError("complete CPU native preflight failed; all observed errors preserved")


if __name__ == "__main__":
    main()
