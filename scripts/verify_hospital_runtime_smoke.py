"""Read back a trusted local smoke manifest and its pinned recording."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.collection.scientific_preflight import verify_saved_recording  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True)
    args = p.parse_args()
    file = Path(args.manifest).resolve()
    manifest = json.loads(file.read_text())
    if manifest.get("status") != "PASS":
        raise ValueError(f"smoke status is {manifest.get('status')}")
    if not manifest["preflight"]["SCIENTIFIC_COLLECTION_PERMITTED"]:
        raise ValueError("instrumentation preflight did not pass")
    trajectory = file.parent / "trajectory"
    for name, expected in manifest["file_sha256"].items():
        if Path(name).name != name:
            raise ValueError("invalid recording filename")
        if hashlib.sha256((trajectory / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"recording hash changed: {name}")
    sources = next(o["value"] for o in manifest["observations"]
                   if o["name"] == "influencing_file_digests")
    for name, expected in sources.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"executed source changed: {name}")
    resolution = next(o["value"] for o in manifest["observations"]
                      if o["name"] == "render_product_resolution")
    verify_saved_recording(trajectory, manifest["captures"], tuple(resolution))
    print(f"PASS: {manifest['frames']} frames; saved images, poses, transitions and source hashes verified")
    print("Stationary instrumentation only; semantic visibility and navigation admission remain separate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
