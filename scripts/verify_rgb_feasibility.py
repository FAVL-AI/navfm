"""Strict verification of recording and exact executed source snapshots."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from navfm.collection.scientific_preflight import verify_saved_recording


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    root = args.manifest.parent
    data = json.loads(args.manifest.read_text())
    if data["status"] != "PASS" or not data["preflight"]["SCIENTIFIC_COLLECTION_PERMITTED"]:
        raise ValueError("completed preflight PASS required")
    for name, digest in data["file_sha256"].items():
        if Path(name).name != name:
            raise ValueError("invalid recording filename")
        if hashlib.sha256((root / "trajectory" / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"recording hash changed: {name}")
    sources = next(
        o["value"] for o in data["observations"] if o["name"] == "influencing_file_digests"
    )
    archived = 0
    for name, digest in sources.items():
        source = Path(name)
        if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            source = root / "source_snapshot" / digest
            archived += 1
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError(f"executed source digest mismatch: {name}")
    resolution = next(
        o["value"] for o in data["observations"] if o["name"] == "render_product_resolution"
    )
    verify_saved_recording(root / "trajectory", data["captures"], tuple(resolution))
    print(
        f"PASS: {data['frames']} frames; exact recording and source digests ({archived} archived sources)"
    )


if __name__ == "__main__":
    main()
