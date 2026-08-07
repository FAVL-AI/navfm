#!/usr/bin/env python3
"""Validate the compatibility harness against the real GO Stanford corpus.

    python scripts/harness_validation.py --data-folder ~/navfm-data/go_stanford/go_stanford

**This is harness validation only. It does not count as either of Prof. Bo's two
collected trajectories and does not provide pilot evidence.** The two-trajectory
pilot remains BLOCKED on the missing Isaac Sim runtime (`gates/failures/F-PILOT-1.md`).

The point is to prove the evidence machinery works on a real trajectory *before*
collection is possible, so that when Isaac Sim becomes available the pilot tests
the data rather than debugging the harness at the same time.

Two reports are produced, deliberately, because one direction proves nothing:

* **as-released** — a GO Stanford trajectory exactly as distributed. This is
  expected to be **BLOCKED**: the released corpus stores `position` and `yaw` as
  object-dtype arrays and therefore does *not* satisfy the Option 1 contract
  (finding F13, `docs/DATA_CONTRACT.md`). A harness that passed this would be
  measuring nothing.
* **converted** — the same trajectory after the approved `navfm.trajio`
  normalisation boundary, written to a derived directory. This is expected to be
  **PASS**, and exercises `navfm.validate` and the unchanged ViNT data path
  end-to-end.

The original corpus is never modified. The converted trajectory is a derived
artefact, written under a scratch directory, and is not committed: what is
committed is the report about it.
"""

from __future__ import annotations

import argparse
import json
import pickle
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.compat import check_trajectory, format_report  # noqa: E402
from navfm.trajio import CONVERSION_VERSION, normalise_traj_data  # noqa: E402

CORPUS_DIGEST = "1fe1411945abd9cd0f335e845fe40d3477aac641aeb5669c961ec9debc4fb8a4"
SOURCE = "GO Stanford reference dataset"
PURPOSE = "compatibility-harness validation only -- NOT pilot evidence"


def convert(src: Path, dst: Path) -> None:
    """Write an Option 1 copy of one released trajectory.

    Images are copied byte-for-byte; `position` and `yaw` go through the single
    approved normalisation boundary. Nothing else is carried into
    `traj_data.pkl`: the contract admits exactly two keys, and provenance
    belongs beside it in `metadata.json`.
    """
    dst.mkdir(parents=True, exist_ok=True)
    images = sorted(
        (p for p in src.iterdir() if p.suffix == ".jpg" and p.stem.isdigit()),
        key=lambda p: int(p.stem),
    )
    for i, p in enumerate(images):
        shutil.copy2(p, dst / f"{i}.jpg")

    with open(src / "traj_data.pkl", "rb") as fh:
        raw = pickle.load(fh)
    out = normalise_traj_data(raw, trajectory=src.name)
    with open(dst / "traj_data.pkl", "wb") as fh:
        pickle.dump({"position": out["position"], "yaw": out["yaw"]}, fh)

    (dst / "metadata.json").write_text(
        json.dumps(
            {
                "trajectory_id": src.name,
                "source": SOURCE,
                "source_digest": CORPUS_DIGEST,
                "conversion_version": CONVERSION_VERSION,
                "frame_count": len(images),
                "collected_by_project": False,
                "pilot_evidence": False,
                "note": (
                    "Derived from the GO Stanford reference corpus for harness "
                    "validation. Not collected by this project and not evidence "
                    "for the two-trajectory pilot."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--data-folder", required=True)
    p.add_argument("--trajectory", default=None, help="default: first directory, sorted")
    p.add_argument("--out-dir", default="gates/pilot")
    p.add_argument("--scratch", default=None)
    args = p.parse_args(argv)

    root = Path(args.data_folder).expanduser()
    if not root.is_dir():
        print(f"REFUSED: --data-folder {root} is not a directory", file=sys.stderr)
        return 2
    name = args.trajectory or sorted(d.name for d in root.iterdir() if d.is_dir())[0]
    src = root / name
    if not (src / "traj_data.pkl").is_file():
        print(f"REFUSED: {src} has no traj_data.pkl", file=sys.stderr)
        return 2

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch = Path(args.scratch) if args.scratch else Path("/tmp") / "navfm-harness-validation"
    converted = scratch / f"{name}_option1"
    if converted.exists():
        shutil.rmtree(converted)

    print(f"trajectory: {name}\ncorpus digest: {CORPUS_DIGEST}\n")

    # 1: as released. Expected BLOCKED -- F13.
    released = check_trajectory(
        src,
        source=f"{SOURCE} (as released, unmodified)",
        purpose=PURPOSE,
        collected_by_project=False,
        pilot_evidence=False,
        dataset_digest=CORPUS_DIGEST,
    )
    (out_dir / "harness_validation_as_released.txt").write_text(format_report(released))
    print(f"as released : {released.overall}")

    # 2: after the approved conversion. Expected PASS.
    convert(src, converted)
    conv = check_trajectory(
        converted,
        source=f"{SOURCE} (converted to Option 1 via navfm.trajio {CONVERSION_VERSION})",
        purpose=PURPOSE,
        collected_by_project=False,
        pilot_evidence=False,
        dataset_digest=CORPUS_DIGEST,
    )
    (out_dir / "harness_validation_converted.txt").write_text(format_report(conv))
    (out_dir / "harness_validation_converted.json").write_text(
        json.dumps(conv.as_dict(), indent=2, sort_keys=True) + "\n"
    )
    print(f"converted   : {conv.overall}")

    # The harness is validated only if it discriminates. Both directions, or the
    # run means nothing: a harness that passes everything and a harness that
    # fails everything are equally uninformative.
    ok = released.overall == "BLOCKED" and conv.overall == "PASS"
    print(
        "\nharness validation: "
        + (
            "PASS -- refuses the non-conforming released form, accepts the converted form"
            if ok
            else "FAILED -- the harness did not discriminate as expected"
        )
    )
    print("\nThis is harness validation only. It does not count as either of")
    print("Prof. Bo's two collected trajectories and is not pilot evidence.")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
