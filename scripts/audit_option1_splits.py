"""Audit identifiers and exact RGB overlap; shared procedural family remains a limitation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("new report required")
    admission = json.loads((a.dataset / "admission.json").read_text())
    sets = {s: {"scene": set(), "route": set(), "rgb": set()} for s in ["train", "dev", "test"]}
    for split, names in admission["splits"].items():
        for name in names:
            root = a.dataset / "data/option1_m3pro" / name
            route = json.loads((root / "processing.json").read_text())["route"]
            sets[split]["scene"].add(route["scene"])
            sets[split]["route"].add(route["route_id"])
            sets[split]["rgb"].update(
                hashlib.sha256(f.read_bytes()).hexdigest() for f in root.glob("*.jpg")
            )
    overlap = {}
    for left, right in [("train", "dev"), ("train", "test"), ("dev", "test")]:
        overlap[left + "_" + right] = {
            k: len(sets[left][k] & sets[right][k]) for k in ["scene", "route", "rgb"]
        }
    r = {
        "status": "PASS_IDENTIFIER_AND_EXACT_IMAGE_AUDIT"
        if all(v == 0 for pair in overlap.values() for v in pair.values())
        else "FAIL",
        "dataset_digest": admission["dataset_digest"],
        "admission_sha256": hashlib.sha256((a.dataset / "admission.json").read_bytes()).hexdigest(),
        "overlap": overlap,
        "scene_counts": {s: len(v["scene"]) for s, v in sets.items()},
        "limitation": "Original5corridors share procedural template, texture palette, floor tiles and stripes. Variants are translated paths. Identifier disjointness is not architectural/domain independence; heldout engineering pairs repeatedly inspected. Confirmatory scenes must use new independently designed layouts and untouched data.",
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(r, indent=2) + "\n")
    print(json.dumps(r))


if __name__ == "__main__":
    main()
