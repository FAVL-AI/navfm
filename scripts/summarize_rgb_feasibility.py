"""Print offline feasibility metrics without passing evaluation state to policy."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from navfm.collection.feasibility_metrics import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text())
    if data["status"] != "PASS":
        parser.error("only completed recording PASS manifests can be summarized")
    rows = json.loads((args.manifest.parent / "trajectory/transitions.json").read_text())["records"]
    print(json.dumps(summarize(data, rows), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
