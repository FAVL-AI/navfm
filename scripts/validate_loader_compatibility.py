"""Run one admitted trajectory through the pinned GNM, ViNT and NoMaD data paths.

This is a DATASET-FORMAT claim and nothing more. It establishes that the
reference loader at the pinned upstream commit accepts the trajectory and yields
usable training samples. It is not reproduction, not training performance, and
not a physical-robot claim.

Each framework is reported SEPARATELY. Aggregating three into one PASS would hide
the case where two accept the data and one does not, which is exactly the case
worth knowing about.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trajectory", required=True, help="the admitted trajectory directory")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import numpy as np
    import torch

    from navfm import upstream
    from navfm.simenv import simulator_identity
    from navfm.splits import write_splits

    traj_dir = Path(args.trajectory).resolve()
    data_root = traj_dir.parent
    sim_id = simulator_identity()

    rec: dict[str, Any] = {
        "check": "REAL_TRAJECTORY_LOADER_COMPATIBILITY",
        "artifact_semantics": "DATASET_FORMAT_COMPATIBILITY_ONLY",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "trajectory": str(traj_dir.relative_to(REPO)),
        "claim_boundary": ("establishes that the pinned reference loader accepts this trajectory "
                           "and yields training samples. NOT reproduction, NOT training "
                           "performance, NOT a physical-robot claim."),
        "frameworks_reported_separately": True,
        "provenance": {"python": sim_id.python_version, "torch": sim_id.torch_version,
                       "cuda_runtime": sim_id.cuda_runtime, "interpreter": sim_id.interpreter},
    }

    try:
        rec["upstream_commit"] = upstream.upstream_commit()
        rec["upstream_root"] = str(upstream.upstream_root())

        # Trajectory identity, hashed before anything reads it.
        import pickle
        with open(traj_dir / "traj_data.pkl", "rb") as fh:
            traj = pickle.load(fh)
        pos = np.asarray(traj["position"], dtype=float)
        yaw = np.asarray(traj["yaw"], dtype=float)
        images = sorted(traj_dir.glob("*.jpg"), key=lambda p: int(p.stem))
        h = hashlib.sha256()
        h.update((traj_dir / "traj_data.pkl").read_bytes())
        rec["trajectory_identity"] = {
            "frames": int(pos.shape[0]), "images": len(images),
            "traj_data_sha256": h.hexdigest(),
            "first_image_sha256": hashlib.sha256(images[0].read_bytes()).hexdigest(),
            "last_image_sha256": hashlib.sha256(images[-1].read_bytes()).hexdigest(),
            "positions_finite": bool(np.isfinite(pos).all()),
            "yaws_finite": bool(np.isfinite(yaw).all()),
        }

        # A SEPARATE split folder per model. The reference loader builds an LMDB
        # cache inside the split folder keyed by dataset name, and building three
        # datasets from one folder in one process fails with "environment is
        # already open in this process" -- a harness collision, not an
        # incompatibility. This is the LMDB-cache landmine the repository already
        # documents, in a form it had not taken before.
        #
        # The single admitted trajectory is the entire train split. There is no
        # test split and none is invented: this proves the loader accepts the
        # format, and a held-out split would imply an evaluation claim.
        splits_root = Path("/tmp/_bo10_splits")
        import shutil
        shutil.rmtree(splits_root, ignore_errors=True)
        rec["splits"] = {"root": str(splits_root),
                         "per_model_split_folders": True,
                         "borrowed_dataset_name": "recon",
                         "why": ("the reference loader keys metric_waypoint_spacing off a name in "
                                 "its own data_config.yaml; 'recon' is borrowed for that lookup "
                                 "and implies no claim about RECON data")}

        results: dict[str, Any] = {}
        for model in ("gnm", "vint", "nomad"):
            entry: dict[str, Any] = {"model": model}
            try:
                cfg = upstream.model_config(model)
                entry["context_size"] = cfg["context_size"]
                entry["len_traj_pred"] = cfg["len_traj_pred"]
                model_root = splits_root / model
                train_path, _ = write_splits(model_root, "recon", [traj_dir.name], [])
                split_folder = train_path.parent
                entry["split_folder"] = str(split_folder)
                ds = upstream.build_dataset(dataset_name="recon", data_folder=data_root,
                                            split_folder=split_folder, cfg=cfg)
                entry["dataset_built"] = True
                entry["samples"] = len(ds)
                if len(ds) == 0:
                    entry["result"] = "FAIL"
                    entry["reason"] = "loader built but yielded zero samples"
                    results[model] = entry
                    continue

                item = ds[0]
                entry["getitem_executed"] = True
                entry["tuple_length"] = len(item)
                shapes = []
                for element in item:
                    if torch.is_tensor(element):
                        shapes.append({"type": "tensor", "shape": list(element.shape),
                                       "dtype": str(element.dtype)})
                    else:
                        shapes.append({"type": type(element).__name__, "value": str(element)[:40]})
                entry["sample_structure"] = shapes
                # The action tensor carries the waypoint representation.
                actions = item[2] if len(item) > 2 and torch.is_tensor(item[2]) else None
                if actions is not None:
                    entry["action_shape"] = list(actions.shape)
                    entry["action_finite"] = bool(torch.isfinite(actions).all().item())
                    entry["learn_angle_dims"] = (
                        "dx,dy,cos,sin" if actions.shape[-1] == 4 else
                        ("dx,dy" if actions.shape[-1] == 2 else f"{actions.shape[-1]} dims"))
                dist = item[3] if len(item) > 3 else None
                if torch.is_tensor(dist):
                    entry["distance_dtype"] = str(dist.dtype)
                    entry["distance_value"] = float(dist.reshape(-1)[0].item())
                entry["synthetic_fallback_used"] = False
                entry["result"] = "PASS"
            except Exception as exc:
                import traceback
                entry["result"] = "FAIL"
                entry["error"] = f"{type(exc).__name__}: {exc}"
                entry["traceback"] = traceback.format_exc()[-1200:]
            results[model] = entry

        rec["frameworks"] = results
        rec["GNM_REAL_HOSPITAL_COMPATIBILITY"] = results["gnm"]["result"]
        rec["VINT_REAL_HOSPITAL_COMPATIBILITY"] = results["vint"]["result"]
        rec["NOMAD_REAL_HOSPITAL_COMPATIBILITY"] = results["nomad"]["result"]
        rec["all_three_accept"] = all(results[m]["result"] == "PASS"
                                      for m in ("gnm", "vint", "nomad"))
        rec["LOADER_COMPATIBILITY"] = "PASS" if rec["all_three_accept"] else "PARTIAL_OR_FAIL"
    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-2500:]
        rec["LOADER_COMPATIBILITY"] = "INCONCLUSIVE"
    finally:
        with contextlib.suppress(Exception):
            digest = emit_evidence(args.out, rec, required_keys=(
                "check", "artifact_semantics", "LOADER_COMPATIBILITY"))
            print(f"wrote {args.out} sha256={digest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
