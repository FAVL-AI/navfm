"""Apply child-only camera-qualification launch settings, then exec worker."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", required=True)
    args, worker_args = parser.parse_known_args()
    os.chdir(ROOT)
    os.environ["OMNICLIENT_HUB_MODE"] = "disabled"
    worker = Path(args.worker).resolve()
    if not worker.is_relative_to(ROOT) or not worker.is_file():
        raise SystemExit("bound qualification worker path rejected")
    os.execv(sys.executable, [sys.executable, str(worker), *worker_args])


if __name__ == "__main__":
    main()
