"""One native NoMaD check with versioned authenticated dependency admission."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import sys
from pathlib import Path

from nomad_dependency_boundary_v2 import install_boundary, verify_loaded_dependencies


def main():
    cfg = json.loads(Path(sys.argv[sys.argv.index("--config") + 1]).read_text())
    install_boundary(cfg["diffusion_root"], cfg["diffusion_files"])
    out = Path(sys.argv[sys.argv.index("--out") + 1])
    provenance = {"status": "STARTED", "diffusion_git_head": cfg["diffusion_git_head"]}
    manifest = None
    try:
        manifest = json.loads(Path(cfg["installed_dependency_manifest"]).read_text())
        for package in manifest["packages"]:
            if importlib.metadata.version(package["name"]) != package["version"]:
                raise ValueError("installed dependency version drift")
        importlib.import_module("diffusion_policy.model.diffusion.conditional_unet1d")
        provenance["loaded_before_native"] = verify_loaded_dependencies(manifest)
        provenance.update(
            status="IMPORT_PASS",
            modules=[
                {
                    "module": item["module"],
                    "source": sys.modules[item["module"]].__file__,
                    "sha256": item["sha256"],
                }
                for item in cfg["diffusion_files"]
            ],
        )
        from development_compatibility_v1 import main as native_check

        native_check()
        provenance["status"] = "PASS"
    except BaseException as error:
        provenance.update(status="FAIL", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        try:
            if manifest is not None:
                provenance["loaded_after_native"] = verify_loaded_dependencies(manifest)
        except BaseException as error:
            provenance.update(
                status="FAIL", origin_error_type=type(error).__name__, origin_error=str(error)
            )
            raise
        finally:
            out.with_name("import-resolution.json").write_text(
                json.dumps(provenance, indent=2) + "\n"
            )


if __name__ == "__main__":
    main()
