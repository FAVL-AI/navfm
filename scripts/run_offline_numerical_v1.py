"""Sequential finite offline numerical diagnostic runner."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from offline_numerical_v1 import REPO, analyse, frozen


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", required=True)
    args = p.parse_args()
    cfg = frozen(args.freeze, launch=True)
    root = Path(cfg["output_root"])
    root.mkdir(parents=True, exist_ok=False)
    ledger = []
    workers = []

    def save():
        (root / "ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")

    for ident in cfg["process_ids"]:
        row = dict(process_id=ident, status="LAUNCHED")
        ledger.append(row)
        save()
        try:
            with (root / (ident + ".log")).open("w") as log:
                result = subprocess.run(
                    [
                        cfg["python"],
                        str(REPO / "scripts/offline_numerical_v1.py"),
                        "--freeze",
                        args.freeze,
                        "--process-id",
                        ident,
                    ],
                    cwd=REPO,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=cfg["timeout_s"],
                )
            row["returncode"] = result.returncode
            value = json.loads((root / ident / "result.json").read_text())
            if result.returncode or value["status"] != "PASS":
                raise ValueError("Worker execution failed")
            frozen(args.freeze, launch=True)
            workers.append(value)
            row["status"] = "PASS"
            save()
        except Exception as exc:
            row.update(status="FAIL", error=str(exc))
            save()
            (root / "analysis.json").write_text(
                json.dumps(
                    dict(status="HALTED", error=str(exc), further_runs_authorized=False), indent=2
                )
                + "\n"
            )
            raise
    try:
        value = analyse(workers, cfg)
        frozen(args.freeze, launch=True)
    except Exception as exc:
        (root / "analysis.json").write_text(
            json.dumps(
                dict(status="HALTED", error=str(exc), further_runs_authorized=False), indent=2
            )
            + "\n"
        )
        ledger.append(dict(status="HALTED", error=str(exc)))
        save()
        raise
    value["freeze"] = args.freeze
    (root / "analysis.json").write_text(json.dumps(value, indent=2) + "\n")
    ledger.append(dict(status="STOP", further_runs_authorized=False))
    save()


if __name__ == "__main__":
    main()
