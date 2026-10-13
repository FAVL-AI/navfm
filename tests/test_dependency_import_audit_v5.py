"""Linear authenticated work and complete rejection evidence, without native imports."""

import hashlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dependency_import_audit_v5 import audit


def test_manifest_index_once_file_digest_once_all_objects_retained(tmp_path, monkeypatch):
    binary = tmp_path / "_C.so"
    binary.write_bytes(b"binary")
    source = tmp_path / "module.py"
    source.write_bytes(b"source")
    paths = [binary, source, *[tmp_path / f"unused{i}.py" for i in range(20)]]
    manifest = {
        "files": [
            {
                "path": str(p),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()
                if p in [binary, source]
                else "unused",
            }
            for p in paths
        ]
    }
    resolves = []
    reads = []
    original_resolve = Path.resolve
    original_read = Path.read_bytes

    def resolve(p, *a, **k):
        resolves.append(str(p))
        return original_resolve(p, *a, **k)

    def read(p):
        reads.append(str(p))
        return original_read(p)

    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(Path, "read_bytes", read)
    modules = {
        "torch._C": SimpleNamespace(__file__=str(binary)),
        **{f"torch.m{i}": SimpleNamespace(__file__=str(source)) for i in range(10)},
        "torch.bad1": types.ModuleType("torch.bad1"),
        "torch.bad2": types.ModuleType("torch.bad2"),
    }
    progress = []
    records = audit(manifest, modules, progress.append)
    assert len(records) == 13 and len(progress) == 13
    assert sum(r["status"] == "UNCLASSIFIED" for r in records) == 2
    assert reads.count(str(binary)) == 1 and reads.count(str(source)) == 1
    assert all(resolves.count(str(p)) == 1 for p in paths[2:])
