import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


def test_archived_execution_is_verified_and_tampering_rejected(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/verify_rgb_feasibility.py"
    spec = importlib.util.spec_from_file_location("rgb_verifier", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "verify_saved_recording", lambda *args: None)
    source = tmp_path / "current.py"
    source.write_text("changed source")
    executed = b"executed source"
    digest = hashlib.sha256(executed).hexdigest()
    archive = tmp_path / "source_snapshot"
    archive.mkdir()
    snapshot = archive / digest
    snapshot.write_bytes(executed)
    manifest = tmp_path / "runtime_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "PASS",
                "preflight": {"SCIENTIFIC_COLLECTION_PERMITTED": True},
                "file_sha256": {},
                "frames": 1,
                "captures": [],
                "observations": [
                    {"name": "influencing_file_digests", "value": {str(source): digest}},
                    {"name": "render_product_resolution", "value": [640, 480]},
                ],
            }
        )
    )
    monkeypatch.setattr(sys, "argv", ["verify", "--manifest", str(manifest)])
    module.main()
    snapshot.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="digest mismatch"):
        module.main()
