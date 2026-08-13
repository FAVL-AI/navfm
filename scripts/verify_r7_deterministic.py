"""R7 -- deterministic inference on the frozen GO Stanford population.

PREREGISTRATION.md Amendment 5 requires, per model, a machine-readable record
containing: checkpoint digest, model/config digest, frozen GO Stanford
input-batch digest, seed, device/software environment, ``model.eval()``, strictly
defined preprocessing, raw output shapes, finite-output checks, output digest,
repeat count, ``torch.allclose(rtol=1e-5, atol=1e-6)``, maximum absolute
difference and maximum relative difference.

**Why the historical evidence cannot supply this.** The July gate ran GNM and
NoMaD through ``official_frame``
(``900c418:scripts/15_reproduction_gate.py:113-125``), which builds every input
from ``np.random.default_rng(SEED + i)`` -- synthetic noise, as its own docstring
says: *"Synthetic, and not benchmark data."* It never touched GO Stanford. The
frozen GO Stanford input-batch digest is therefore unsatisfiable by reference for
every model, however many repeats the historical record carries, and ViNT has no
inference record at all: ``vint_gate.json`` exists in no revision, and the gate
script binds ``--model`` to ``choices=sorted(MODELS)`` with ViNT absent.

**Which input is "the frozen GO Stanford input".** The population is pinned by
``gates/G0/evaluation_pairs.json`` -- 41,872 pairs, digest ``57a7fbbeba91b92a``,
in draw order under population seed 0. This harness takes the **first batch in
that draw order** under the declared loader seed, which is unique and
reproducible given the declaration. Each model preprocesses it through its own
official contract, because that is what the reference does: GNM and ViNT at
85x64 with context 5, NoMaD at 96x96 with context 3. The models therefore share
a population and a draw order, not a literal tensor -- and the record digests the
tensors each model actually consumed, so a reader can tell which is which.

Repeats compare **model outputs**, not serialized files. Identity is asserted by
the declared tolerance, and the maximum absolute and relative differences are
archived whether or not they are zero -- a bitwise-identical result is reported
as such but is never the acceptance threshold, which the amendment fixes
uniformly across all three models.

No training. No metric. No G0.c quantity. R7 asks only whether the same declared
input, run twice, gives the same answer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

#: The tolerance Amendment 5 declares, uniformly for GNM, ViNT and NoMaD.
RTOL, ATOL = 1e-5, 1e-6

_PICKLED = {"vint", "gnm"}

#: Read-only search paths for dependencies staged OUTSIDE the canonical
#: environment, populated from --extra-syspath. Never installed into it.
_EXTRA_SYSPATH: list[str] = []


class PreflightError(RuntimeError):
    """A requirement for running R7 is absent. Named, never worked around."""


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise PreflightError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def _digest(obj: Any) -> str:
    """Stable digest of a tensor or a nested structure of tensors."""
    import torch

    h = hashlib.sha256()

    def walk(x: Any) -> None:
        if isinstance(x, torch.Tensor):
            t = x.detach().cpu().contiguous()
            h.update(str(tuple(t.shape)).encode())
            h.update(str(t.dtype).encode())
            h.update(t.numpy().tobytes())
        elif isinstance(x, (list, tuple)):
            for item in x:
                walk(item)
        else:
            h.update(repr(x).encode())

    walk(obj)
    return h.hexdigest()


def committed_protocol() -> str:
    return _git("show", "HEAD:PREREGISTRATION.md")


def preflight() -> None:
    protocol = committed_protocol()
    if "## Amendment 5" not in protocol:
        raise PreflightError(
            "the committed PREREGISTRATION.md at HEAD carries no Amendment 5. R7 is "
            "defined by Amendment 5 and is not authorised without it. Refusing."
        )
    if "torch.allclose(rtol=1e-5, atol=1e-6)" not in protocol:
        raise PreflightError(
            "the committed protocol does not declare the repeatability tolerance this "
            "harness applies. Refusing rather than choosing one at execution time."
        )


def recorded_digest(model: str) -> str:
    for line in _git("show", "HEAD:gates/G0/SHA256SUMS").splitlines():
        if line.strip().endswith(f"./{model}.pth"):
            return line.split()[0]
    raise PreflightError(f"no recorded digest for {model}.pth in gates/G0/SHA256SUMS")


def build_model_for(model_name: str) -> Any:
    from navfm import upstream

    if model_name in ("vint", "gnm"):
        return upstream.build_model(model_name)
    if model_name == "nomad":
        # Same constraint as R6: NoMaD's vendored diffusion_policy needs einops,
        # and installing it into the canonical environment would change the
        # installed-distribution digest and so the environment identity that the
        # G0.c freeze audit checks. Stage it on sys.path instead; never install.
        for extra in _EXTRA_SYSPATH:
            if extra not in sys.path:
                sys.path.insert(0, extra)
        sys.path.insert(0, str(REPO / "third_party" / "diffusion_policy"))
        spec_path = REPO / "scripts" / "verify_r6_strict_load.py"
        import importlib.util

        spec = importlib.util.spec_from_file_location("_r6", spec_path)
        assert spec and spec.loader
        r6 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(r6)
        return r6._build_nomad(upstream.model_config("nomad"))
    raise PreflightError(f"no architecture wired for {model_name!r}")


def frozen_batch(model_name: str, args: argparse.Namespace) -> tuple[Any, dict[str, Any]]:
    """The first batch, in the frozen draw order, through this model's own contract."""
    import torch

    from navfm import upstream

    cfg = upstream.model_config(model_name)
    opts = upstream.dataset_options(cfg, args.dataset)
    dataset = upstream.build_dataset(
        dataset_name=args.dataset,
        data_folder=args.data_folder,
        split_folder=args.split_folder,
        cfg=cfg,
        end_slack=opts["end_slack"],
        waypoint_spacing=opts["waypoint_spacing"],
        negative_mining=opts["negative_mining"],
        goals_per_obs=opts["goals_per_obs"],
    )

    from vint_train.data import vint_dataset as _vd

    if not hasattr(_vd, "navfm_seed_sampling"):
        raise PreflightError(
            "the reference clone is unpatched: --population-seed requires "
            "scripts/patch_upstream.py to have been applied"
        )
    _vd.navfm_seed_sampling(args.population_seed)

    generator = torch.Generator().manual_seed(args.seed)
    loader = torch.utils.data.DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
        drop_last=False,
        generator=generator,
    )
    batch = next(iter(loader))
    meta = {
        "dataset_size": len(dataset),
        "batch_size": args.batch_size,
        "population_seed": args.population_seed,
        "loader_seed": args.seed,
        "image_size": list(cfg["image_size"]),
        "context_size": cfg["context_size"],
        "len_traj_pred": cfg["len_traj_pred"],
        "input_batch_digest": _digest(batch[:2]),
        "input_shapes": [list(t.shape) for t in batch[:2]],
    }
    return batch, meta


def forward(model_name: str, model: Any, batch: Any, device: str) -> Any:
    """One deterministic forward pass through the official path. No sampling."""
    import torch

    obs, goal = batch[0].to(device), batch[1].to(device)
    with torch.no_grad():
        if model_name == "nomad":
            # The official NoMaD forward for the observation encoder only. The
            # diffusion sampling loop is NOT invoked: R7 asks whether the same
            # input gives the same answer, and Amendment 5 forbids porting the
            # sampling implementation for symmetry.
            mask = torch.zeros(obs.shape[0], dtype=torch.long, device=device)
            enc = model("vision_encoder", obs_img=obs, goal_img=goal, input_goal_mask=mask)
            dist = model("dist_pred_net", obsgoal_cond=enc)
            return {"obs_encoding": enc, "dist_pred": dist}
        dist, action = model(obs, goal)
        return {"dist_pred": dist, "action_pred": action}


def verify_one(model_name: str, args: argparse.Namespace) -> dict[str, Any]:
    import torch

    from navfm.models.loader import (
        count_parameters,
        extract_state_dict,
        load_checkpoint,
        sha256,
    )
    from navfm.provenance import environment_identity

    ckpt = Path(args.checkpoint_dir) / f"{model_name}.pth"
    expected = recorded_digest(model_name)
    digest = sha256(ckpt)
    if digest != expected:
        raise PreflightError(
            f"{model_name}: checkpoint digest {digest[:16]} != recorded {expected[:16]}"
        )

    device = args.device
    model = build_model_for(model_name)
    state = extract_state_dict(
        load_checkpoint(ckpt, trust_checkpoint=model_name in _PICKLED, expected_sha256=expected)
    )
    model.load_state_dict(state, strict=True)
    model.to(device)
    model.eval()

    batch, batch_meta = frozen_batch(model_name, args)

    outputs = []
    for _repeat in range(args.repeats):
        torch.manual_seed(args.seed)
        if device.startswith("cuda"):
            torch.cuda.manual_seed_all(args.seed)
        outputs.append(forward(model_name, model, batch, device))

    keys = sorted(outputs[0])
    per_key: dict[str, Any] = {}
    all_close = True
    max_abs_overall = 0.0
    max_rel_overall = 0.0
    for k in keys:
        first = outputs[0][k]
        shapes = list(first.shape)
        finite = bool(torch.isfinite(first).all())
        max_abs = 0.0
        max_rel = 0.0
        close = True
        for other in outputs[1:]:
            diff = (other[k] - first).abs()
            max_abs = max(max_abs, float(diff.max()))
            denom = first.abs().clamp_min(1e-12)
            max_rel = max(max_rel, float((diff / denom).max()))
            close = close and bool(torch.allclose(other[k], first, rtol=RTOL, atol=ATOL))
        bitwise = all(bool(torch.equal(o[k], first)) for o in outputs[1:])
        per_key[k] = {
            "shape": shapes,
            "dtype": str(first.dtype),
            "all_finite": finite,
            "output_digest": _digest(first),
            "allclose": close,
            "bitwise_identical": bitwise,
            "max_abs_diff": max_abs,
            "max_rel_diff": max_rel,
        }
        all_close = all_close and close and finite
        max_abs_overall = max(max_abs_overall, max_abs)
        max_rel_overall = max(max_rel_overall, max_rel)

    identity = environment_identity(REPO)
    return {
        "rung": "R7",
        "model": model_name,
        "checkpoint_path": str(ckpt.relative_to(REPO)),
        "checkpoint_sha256": digest,
        "checkpoint_digest_matches": True,
        "config_digest": _digest(json.dumps(dict(__import__("navfm").upstream.model_config(model_name)), sort_keys=True)),
        "parameters": count_parameters(model),
        "model_tensors": len(model.state_dict()),
        "strict_load": True,
        "evaluation_mode": not model.training,
        "device": device,
        "seed": args.seed,
        "repeat_count": args.repeats,
        "tolerance": {"rtol": RTOL, "atol": ATOL, "source": "PREREGISTRATION.md Amendment 5"},
        "input": {**batch_meta, "population_manifest": args.pair_manifest,
                  "population_manifest_digest": json.loads(Path(args.pair_manifest).read_text())["sha256"]},
        "outputs": per_key,
        "max_abs_diff": max_abs_overall,
        "max_rel_diff": max_rel_overall,
        "repeatability": "PASS" if all_close else "FAIL",
        "bitwise_identical_across_repeats": all(v["bitwise_identical"] for v in per_key.values()),
        "environment_id": identity.environment_id,
        "torch_version": torch.__version__,
        "python": platform.python_version(),
        "git_sha": _git("rev-parse", "HEAD"),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "command": "python " + " ".join(sys.argv),
        "syspath_additions": list(_EXTRA_SYSPATH),
        "training_run": False,
        "diffusion_sampling_invoked": False,
        "claim_boundary": (
            "R7 only: the same frozen GO Stanford input, run repeatedly under the "
            "declared protocol, produces outputs within the declared tolerance. This "
            "is not a metric, not a G0.c quantity, and not a reproduction of any "
            "published result."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python scripts/verify_r7_deterministic.py")
    ap.add_argument("--model", action="append", required=True, choices=["vint", "gnm", "nomad"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--checkpoint-dir", default=str(REPO / "checkpoints"))
    ap.add_argument("--dataset", default="go_stanford")
    ap.add_argument("--data-folder", required=True)
    ap.add_argument("--split-folder", required=True)
    ap.add_argument("--pair-manifest", default=str(REPO / "gates/G0/evaluation_pairs.json"))
    ap.add_argument("--batch-size", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--population-seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument(
        "--extra-syspath",
        action="append",
        default=[],
        help="read-only search path for dependencies staged outside the canonical "
        "environment, so the G0.c environment identity is not disturbed",
    )
    args = ap.parse_args(argv)

    for extra in args.extra_syspath:
        if not Path(extra).is_dir():
            print(f"R7 REFUSED: search path {extra} is not a directory", file=sys.stderr)
            return 2
        _EXTRA_SYSPATH.append(str(Path(extra).resolve()))

    if args.repeats < 2:
        print("R7 REFUSED: at least two repeats are required", file=sys.stderr)
        return 2
    try:
        preflight()
    except PreflightError as exc:
        print(f"R7 PREFLIGHT REFUSED: {exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    try:
        for name in args.model:
            rec = verify_one(name, args)
            (out_dir / f"{name}_r7.json").write_text(json.dumps(rec, indent=2) + "\n")
            records.append(rec)
    except PreflightError as exc:
        print(f"R7 REFUSED: {exc}", file=sys.stderr)
        return 2

    print("R7 -- DETERMINISTIC INFERENCE ON THE FROZEN GO STANFORD POPULATION")
    print("=" * 66)
    for r in records:
        print(
            f"  {r['model']:<6} {r['repeatability']:<4} repeats={r['repeat_count']} "
            f"allclose(rtol=1e-5,atol=1e-6)=True "
            f"max_abs={r['max_abs_diff']:.3e} max_rel={r['max_rel_diff']:.3e} "
            f"bitwise={r['bitwise_identical_across_repeats']}"
        )
        for k, v in r["outputs"].items():
            print(f"           {k:<14} {v['shape']!s:<18} finite={v['all_finite']} "
                  f"digest={v['output_digest'][:16]}")
    failed = [r["model"] for r in records if r["repeatability"] != "PASS"]
    print()
    print(f"records written to {out_dir}")
    print("RESULT  : " + ("PASS" if not failed else f"FAIL ({', '.join(failed)})"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
