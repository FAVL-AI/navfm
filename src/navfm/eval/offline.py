"""Offline evaluation of ViNT / GNM against the reference metric definitions.

    python -m navfm.eval.offline --model vint --checkpoint checkpoints/vint.pth \
        --dataset go_stanford --split test --batch-size 400

This is the entrypoint that produces gate G0.c -- the first published
reproduction number for this model family -- and the same code path scores
every epoch of every fine-tune, so that a training curve and a headline table
can never be computed two different ways.

Three properties are load-bearing and none of them are obvious:

**Metrics are averaged over batches, unweighted.** Upstream's ``Logger``
appends one value per batch and takes a plain mean, so a smaller trailing batch
counts as much as a full one, and ``action_reduce``'s ``mask.mean()`` term is
computed *within* each batch. This is why upstream issue #51 sees cosine
similarity fall 0.96 -> 0.5 between batch 400 and batch 1: the metric is a
function of the batch size. Concatenating every prediction and reducing once
would produce a cleaner number that is not comparable to anything published.
Hence ``--batch-size 400`` as the default and the batch size in every record.

**Both reductions are reported.** ``strict`` reproduces the reference exactly,
including the ``+1e-2`` guard that scales action metrics by ``p / (p + 0.01)``.
``plain`` is the honest masked mean. Papers comparing against upstream numbers
must quote ``strict``; papers reporting our own models are free to quote
``plain``, as long as they say which. Both are in ``metrics.json`` always.

**ADE/FDE are converted to metres.** Normalised MSE on unit-free waypoints is
uninterpretable; the conversion factor is
``metric_waypoint_spacing * waypoint_spacing``, read from the reference
``data_config.yaml`` for the named dataset. An unregistered dataset is an
error, never a default -- see :func:`navfm.upstream.metric_waypoint_spacing`.

Output lands in ``runs/eval_<model>_<dataset>_<split>_<timestamp>/`` as
``metrics.json``, ``config.json`` and ``git_sha.txt``. ``scripts/make_tables.py``
reads exactly those files; no number reaches the paper by hand.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from navfm import prereg, upstream
from navfm.eval import metrics as M
from navfm.evidence import EvidenceClass, evidence_block

__all__ = [
    "MetricAccumulator",
    "evaluate",
    "git_describe",
    "main",
    "run_directory",
]

#: The reference logs these seven for ViNT/GNM (six when ``learn_angle`` is off).
REFERENCE_KEYS = (
    "dist_loss",
    "action_loss",
    "action_waypts_cos_sim",
    "multi_action_waypts_cos_sim",
    "action_orien_cos_sim",
    "multi_action_orien_cos_sim",
    "total_loss",
)


class MetricAccumulator:
    """Per-batch metric accumulation with upstream ``Logger`` semantics.

    Deliberately numpy-only and free of any torch or dataset dependency, so the
    aggregation -- the part with the surprising semantics -- is unit-testable
    without a GPU, a model, or the reference package.

    Two behaviours copied from ``Logger``:

    * ``average()`` is an unweighted mean over the logged per-batch values; a
      short trailing batch is not down-weighted;
    * ``log_data`` silently *drops* NaN. A batch whose mask is entirely zero
      makes the plain reduction NaN, and upstream would omit it rather than
      poison the average. We drop it too, and count the drops so a run whose
      numbers rest on half its batches cannot look like one that did not.
    """

    def __init__(
        self, *, alpha: float = 0.5, learn_angle: bool = True, metres_per_unit: float = 1.0
    ):
        self.alpha = float(alpha)
        self.learn_angle = bool(learn_angle)
        self.metres_per_unit = float(metres_per_unit)
        self._values: dict[str, list[float]] = {}
        self._dropped: dict[str, int] = {}
        self.n_batches = 0
        self.n_samples = 0

    def _log(self, key: str, value: float) -> None:
        if np.isnan(value):
            self._dropped[key] = self._dropped.get(key, 0) + 1
            return
        self._values.setdefault(key, []).append(float(value))

    def update(
        self,
        *,
        dist_pred: np.ndarray,
        dist_label: np.ndarray,
        action_pred: np.ndarray,
        action_label: np.ndarray,
        action_mask: np.ndarray,
    ) -> None:
        """Score one batch. Arrays are ``(B, ...)`` numpy, already on the host."""
        self.n_batches += 1
        self.n_samples += int(np.shape(action_label)[0])

        for strict in (True, False):
            prefix = "strict" if strict else "plain"
            losses = M.reference_losses(
                dist_pred=dist_pred,
                dist_label=dist_label,
                action_pred=action_pred,
                action_label=action_label,
                action_mask=action_mask,
                alpha=self.alpha,
                learn_angle=self.learn_angle,
                strict=strict,
            )
            for key, value in losses.items():
                self._log(f"{prefix}/{key}", value)

        # ADE/FDE use the plain masked mean in both variants -- they are our own
        # metrics, not the reference's, so there is no quirk to reproduce.
        self._log("ade_normalized", M.ade(action_pred, action_label, action_mask))
        self._log("fde_normalized", M.fde(action_pred, action_label, action_mask))

    def result(self) -> dict[str, Any]:
        avg = {k: float(np.mean(v)) for k, v in self._values.items()}
        out: dict[str, Any] = {
            "n_batches": self.n_batches,
            "n_samples": self.n_samples,
            "strict": {k.split("/", 1)[1]: v for k, v in avg.items() if k.startswith("strict/")},
            "plain": {k.split("/", 1)[1]: v for k, v in avg.items() if k.startswith("plain/")},
            "ade_normalized": avg.get("ade_normalized", float("nan")),
            "fde_normalized": avg.get("fde_normalized", float("nan")),
            "metres_per_unit": self.metres_per_unit,
        }
        out["ade_m"] = out["ade_normalized"] * self.metres_per_unit
        out["fde_m"] = out["fde_normalized"] * self.metres_per_unit
        if self._dropped:
            out["dropped_nan_batches"] = dict(sorted(self._dropped.items()))
        return out


def _to_numpy(t: Any) -> np.ndarray:
    return np.asarray(t.detach().to("cpu", copy=False).float().numpy(), dtype=np.float64)


def evaluate(
    model: Any,
    dataloader: Iterable[Any],
    *,
    device: Any = "cpu",
    alpha: float = 0.5,
    learn_angle: bool = True,
    metres_per_unit: float = 1.0,
    limit_batches: int | None = None,
    amp: Any = None,
    progress: bool = True,
) -> dict[str, Any]:
    """Score ``model`` over ``dataloader``; the one eval path in this codebase.

    Mirrors ``train_utils.evaluate``'s batch handling exactly -- the 7-tuple
    unpacking, the per-frame normalisation, ``model.eval()`` and ``no_grad`` --
    and differs from it only in what it does with the numbers afterwards.
    ``train/run.py`` calls this for its per-epoch eval, so a fine-tune's
    validation curve is the same measurement as the headline table.
    """
    import contextlib

    import torch

    transform = upstream.reference_transform()
    acc = MetricAccumulator(alpha=alpha, learn_angle=learn_angle, metres_per_unit=metres_per_unit)
    ctx = amp if amp is not None else contextlib.nullcontext()

    was_training = model.training
    model.eval()
    try:
        with torch.no_grad():
            for i, batch in enumerate(_progress(dataloader, limit_batches, progress)):
                if limit_batches is not None and i >= limit_batches:
                    break
                (
                    obs_image,
                    goal_image,
                    action_label,
                    dist_label,
                    _goal_pos,
                    _ds_index,
                    action_mask,
                ) = batch

                obs_image, goal_image = upstream.apply_reference_transform(
                    obs_image, goal_image, transform, device
                )
                with ctx:
                    dist_pred, action_pred = model(obs_image, goal_image)

                acc.update(
                    dist_pred=_to_numpy(dist_pred),
                    dist_label=_to_numpy(dist_label),
                    action_pred=_to_numpy(action_pred),
                    action_label=_to_numpy(action_label),
                    action_mask=_to_numpy(action_mask),
                )
    finally:
        model.train(was_training)

    if acc.n_batches == 0:
        raise RuntimeError(
            "the evaluation dataloader yielded no batches. Usually an empty split: "
            "check that traj_names.txt lists trajectories long enough to survive "
            "context_size + len_traj_pred + end_slack (docs/METHODOLOGY.md §5, row 6)."
        )
    return acc.result()


def _progress(loader: Iterable[Any], limit: int | None, enabled: bool) -> Iterator[Any]:
    if not enabled:
        return iter(loader)
    try:
        import tqdm
    except ImportError:  # pragma: no cover - tqdm is a train-extra
        return iter(loader)
    total = limit if limit is not None else None
    if total is None:
        try:
            total = len(loader)  # type: ignore[arg-type]
        except TypeError:
            total = None
    return iter(tqdm.tqdm(loader, total=total, dynamic_ncols=True, desc="eval", leave=False))


# ------------------------------------------------------------------ bookkeeping


def git_describe(repo: str | Path = ".") -> str:
    """``<sha>`` or ``<sha>-dirty``. A dirty tree in a run record is a warning
    to the person reading the record, not an error at the time of the run."""
    try:
        sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except Exception:  # pragma: no cover - no git, or not a repo
        return "unknown"
    return f"{sha}-dirty" if dirty else sha


def seed_model_rng(seed: int) -> None:
    """Seed every RNG stream model construction can draw from.

    Called before ``build_model``. A control arm whose initialisation cannot be
    replayed is not a control: its score is one draw from an unrecorded
    distribution, and Layer B's repeatability requirement is unsatisfiable for
    it.
    """
    import random

    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def run_directory(log_dir: str | Path, name: str) -> Path:
    d = Path(log_dir) / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_run_record(run_dir: Path, *, metrics: dict[str, Any], config: dict[str, Any]) -> None:
    """``metrics.json`` + ``config.json`` + ``git_sha.txt``, the trio every gate
    and every table depends on."""
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (run_dir / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    (run_dir / "git_sha.txt").write_text(
        f"navfm    {git_describe(Path(__file__).resolve().parents[3])}\n"
        f"upstream {upstream.upstream_commit()}\n"
    )


def cell_and_seed(run_name: str) -> tuple[str | None, int | None]:
    """Parse ``scripts/make_tables.py``'s run-name convention.

    Kept here as well as there so that every run record carries an explicit
    ``cell``/``seed``, and table generation never has to re-parse a directory
    name that someone may have renamed.
    """
    import re

    m = re.match(r"^(e\d(?:[_.]\d+)?_.+?)(?:_seed(\d+))?$", run_name)
    if not m:
        return None, None
    return m.group(1), (int(m.group(2)) if m.group(2) else None)


# -------------------------------------------------------------------------- CLI


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m navfm.eval.offline",
        description="Offline evaluation of ViNT/GNM with reference-exact metrics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Batch size is part of the measurement (upstream issue #51: cosine\n"
            "similarity falls 0.96 -> 0.5 between batch 400 and batch 1). The\n"
            "default of 400 is the reference eval_batch_size; state whatever you use."
        ),
    )
    p.add_argument("--model", required=True, choices=["vint", "gnm"])
    p.add_argument(
        "--checkpoint",
        default=None,
        help="released or fine-tuned weights. Omit ONLY for a plumbing smoke test: "
        "the model is then randomly initialised and the run is marked random_init.",
    )
    p.add_argument(
        "--dataset", required=True, help="dataset name as registered in data_config.yaml"
    )
    p.add_argument("--split", default="test", choices=["train", "test"])
    p.add_argument("--batch-size", type=int, default=400)
    p.add_argument(
        "--limit-batches", type=int, default=None, help="stop after N batches (smoke tests)"
    )

    p.add_argument(
        "--data-folder", default=None, help="explicit dataset root; overrides --data-root"
    )
    p.add_argument("--data-root", default="/data", help="dataset lives at <data-root>/<dataset>")
    p.add_argument("--split-folder", default=None, help="explicit dir holding traj_names.txt")
    p.add_argument(
        "--splits-root",
        default=None,
        help="splits at <splits-root>/<dataset>/<split>; defaults to the reference data_splits dir",
    )

    p.add_argument("--device", default=None, help="cuda | cpu (default: cuda when available)")
    p.add_argument("--num-workers", type=int, default=0, help="reference test loaders use 0")
    p.add_argument("--seed", type=int, default=0, help="seeds the eval loader's shuffle")
    p.add_argument(
        "--declaration",
        default=None,
        help=(
            "path to the predeclared execution parameters. When given, arguments "
            "contradicting the declaration are REFUSED, naming the conflicting field. "
            "A declaration nothing reads is documentation, not a control."
        ),
    )
    p.add_argument(
        "--population-seed",
        type=int,
        default=None,
        help=(
            "seeds the evaluation population -- which (observation, goal) pairs are "
            "drawn. Isolated from model initialisation; identical in every arm. "
            "Declared in gates/G0/evaluation_declaration.json for gate runs."
        ),
    )
    p.add_argument(
        "--pair-manifest",
        default=None,
        help="verify the realised population against this pinned manifest at runtime",
    )
    p.add_argument(
        "--model-seed",
        type=int,
        default=None,
        help=(
            "seeds model construction, so a random-init control is reproducible and "
            "replayable. Defaults to --seed. Three independent control arms are three "
            "different --model-seed values, not three dataloader shuffles."
        ),
    )
    p.add_argument(
        "--trust-checkpoint",
        action="store_true",
        help="required for vint.pth/gnm.pth: they contain pickled objects, so loading "
        "them executes code from the file. Verify the SHA-256 first.",
    )
    p.add_argument("--expected-sha256", default=None, help="pin the checkpoint hash")
    p.add_argument(
        "--preregistration-commit",
        default=None,
        metavar="SHA",
        help=(
            "bind this run to the commit that fixed its protocol. Five checks run before "
            "any evaluation work; any failure aborts as 'gate execution invalid'. Required "
            "for gate runs -- retrospective git log inspection is the fallback record, not "
            "the control."
        ),
    )
    p.add_argument(
        "--evidence-class",
        default=None,
        help=(
            "what kind of evidence this run produces: pipeline_smoke_test, "
            "random_init_control, checkpoint_sanity, baseline_evaluation, "
            "registered_experiment, diagnostic_unregistered. Defaults to "
            "random_init_control without a checkpoint and checkpoint_sanity with one; "
            "a run that belongs in a results table must say so explicitly."
        ),
    )
    p.add_argument(
        "--data-source",
        default=None,
        help="provenance of the corpus, e.g. 'go_stanford_reconstruction' or 'synthetic_noise'",
    )
    p.add_argument(
        "--allow-partial-load",
        action="store_true",
        help="permit a checkpoint that fills <90%% of the model; recorded in the manifest",
    )
    p.add_argument("--alpha", type=float, default=None, help="override the config's loss split")
    p.add_argument("--log-dir", default="runs")
    p.add_argument("--run-name", default=None, help="output dir name; also sets the table cell id")
    p.add_argument("--no-progress", action="store_true")
    return p


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    data_folder = (
        Path(args.data_folder) if args.data_folder else Path(args.data_root) / args.dataset
    )
    if args.split_folder:
        split_folder = Path(args.split_folder)
    else:
        root = Path(args.splits_root) if args.splits_root else upstream.default_splits_root()
        split_folder = root / args.dataset / args.split
    return data_folder, split_folder


def _summary(record: dict[str, Any]) -> str:
    lines = [
        "",
        "=" * 72,
        f"  {record['model']}  |  {record['dataset']} / {record['split']}  |  batch {record['batch_size']}",
        "=" * 72,
        f"  samples {record['n_samples']}  batches {record['n_batches']}"
        f"   metres/unit {record['metres_per_unit']:.4f}",
        "",
        f"  {'metric':<32}{'strict (reference)':>20}{'plain':>16}",
        "  " + "-" * 68,
    ]
    for key in REFERENCE_KEYS:
        if key not in record["strict"]:
            continue
        lines.append(f"  {key:<32}{record['strict'][key]:>20.6f}{record['plain'][key]:>16.6f}")
    lines += [
        "  " + "-" * 68,
        f"  {'ADE':<32}{record['ade_normalized']:>20.6f}{record['ade_m']:>13.4f} m",
        f"  {'FDE':<32}{record['fde_normalized']:>20.6f}{record['fde_m']:>13.4f} m",
        "",
    ]
    if record.get("random_init"):
        lines += [
            "  *** RANDOM INITIALISATION -- no checkpoint was loaded.            ***",
            "  *** These numbers measure the plumbing, not a model. Not a result. ***",
            "",
        ]
    if record.get("dropped_nan_batches"):
        lines.append(
            f"  NaN batches dropped (upstream Logger behaviour): {record['dropped_nan_batches']}"
        )
        lines.append("")
    lines.append(f"  -> {record['run_dir']}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    import torch

    upstream.ensure_upstream()
    cfg = upstream.model_config(args.model)
    opts = upstream.dataset_options(cfg, args.dataset)
    spacing = upstream.metric_waypoint_spacing(args.dataset)
    metres_per_unit = spacing * opts["waypoint_spacing"]
    alpha = float(args.alpha if args.alpha is not None else cfg["alpha"])

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    data_folder, split_folder = _resolve_paths(args)

    # Seed BEFORE construction. Without this the random-init control's weights
    # come from the ambient, unrecorded global RNG: the control arm is then
    # unrepeatable, its draw is not in the manifest, and every directional
    # comparison against it rests on one draw nobody can reproduce. The
    # dataloader generator below is a different seed for a different purpose.
    model_seed = args.model_seed if args.model_seed is not None else args.seed
    seed_model_rng(model_seed)
    model = upstream.build_model(args.model, cfg)
    missing: list[str] = []
    unexpected: list[str] = []
    load_census: dict[str, object] | None = None
    checkpoint_sha: str | None = None
    if args.checkpoint:
        from navfm.models.loader import load_into, sha256

        # Hash first, always, and record it whether or not a pin was given: the
        # artefact appendix has to be able to say which bytes produced a number.
        checkpoint_sha = sha256(args.checkpoint)
        if args.expected_sha256 is not None and checkpoint_sha != args.expected_sha256:
            raise SystemExit(
                f"checkpoint hash mismatch for {args.checkpoint}:\n"
                f"  expected {args.expected_sha256}\n  actual   {checkpoint_sha}"
            )
        missing, unexpected = load_into(
            model,
            args.checkpoint,
            trust_checkpoint=args.trust_checkpoint,
            strict=False,
            verbose=True,
        )
        # load_state_dict(strict=False) cannot fail, so a checkpoint that
        # matched nothing would score a randomly initialised model under this
        # checkpoint's SHA. Refuse before any batch is scored.
        from navfm.models.loader import CheckpointLoadError, audit_load

        try:
            load_census = audit_load(
                model, missing, unexpected, allow_partial=args.allow_partial_load
            )
        except CheckpointLoadError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        print(
            "WARNING: no --checkpoint given; evaluating a RANDOMLY INITIALISED model.\n"
            "         This is a plumbing smoke test, not a reproduction number.",
            file=sys.stderr,
        )
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_name = args.run_name or f"eval_{args.model}_{args.dataset}_{args.split}_{stamp}"

    # The commit-order control. Runs before any dataset is opened and any batch
    # is scored, because a binding verified afterwards is a description, not a
    # control. Every check is recorded, pass or fail.
    prereg_checks: list[dict[str, Any]] = []
    protocol_sha256: str | None = None
    if args.preregistration_commit:
        repo_root = Path(__file__).resolve().parents[3]
        checks, protocol_sha256 = prereg.verify(
            args.preregistration_commit,
            repo_root=repo_root,
            output_dir=Path(args.log_dir) / run_name,
        )
        prereg_checks = [c.as_dict() for c in checks]
        for c in checks:
            print(f"  prereg {c.name:<32} {'PASS' if c.passed else 'FAIL'}  {c.detail}")
        try:
            prereg.enforce(checks)
        except prereg.GateExecutionInvalid as exc:
            raise SystemExit(str(exc)) from exc

    model.to(device)

    # Enforce the declaration before anything else. A predeclared parameter that
    # the evaluator does not read cannot constrain the evaluator.
    if args.declaration:
        declared = json.loads(Path(args.declaration).read_text())
        conflicts: list[str] = []
        checks_map = [
            ("batch_size", args.batch_size, declared.get("loader", {}).get("batch_size")),
            ("num_workers", args.num_workers, declared.get("loader", {}).get("num_workers")),
            (
                "population_seed",
                args.population_seed,
                declared.get("population", {}).get("evaluation_seed"),
            ),
        ]
        for field, supplied, want in checks_map:
            if want is not None and supplied is not None and supplied != want:
                conflicts.append(f"{field}: supplied {supplied!r}, declared {want!r}")
        allowed_model_seeds = set(declared.get("control_arm", {}).get("model_seeds", [])) | {
            declared.get("checkpoint_arm", {}).get("model_seed")
        }
        if (
            args.model_seed is not None
            and allowed_model_seeds
            and (args.model_seed not in allowed_model_seeds)
        ):
            conflicts.append(
                f"model_seed: supplied {args.model_seed!r}, declared values "
                f"{sorted(x for x in allowed_model_seeds if x is not None)!r}"
            )
        if conflicts:
            raise SystemExit(
                "gate execution invalid -- arguments contradict the predeclared "
                "execution parameters:\n"
                + "\n".join(f"    {c}" for c in conflicts)
                + f"\n  declaration: {args.declaration}"
            )
        print(f"  declaration honoured: {args.declaration}")

    # What kind of evidence is this? Declared, or defaulted to the most
    # conservative class consistent with the arguments -- never to a class that
    # would grant table access. Promotion to a scientific class is an explicit
    # act by the caller.
    if args.evidence_class is not None:
        try:
            evidence = EvidenceClass.parse(args.evidence_class)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        evidence = (
            EvidenceClass.RANDOM_INIT_CONTROL
            if args.checkpoint is None
            else EvidenceClass.CHECKPOINT_SANITY
        )
    if evidence.requires_checkpoint_hash and checkpoint_sha is None:
        raise SystemExit(
            f"evidence class '{evidence.value}' makes a claim about a model, so the run "
            f"must identify which bytes produced it -- but no checkpoint was given. "
            f"Either pass --checkpoint, or declare a class that makes no model claim "
            f"(random_init_control, pipeline_smoke_test)."
        )

    dataset = upstream.build_dataset(
        dataset_name=args.dataset,
        data_folder=data_folder,
        split_folder=split_folder,
        cfg=cfg,
        end_slack=opts["end_slack"],
        waypoint_spacing=opts["waypoint_spacing"],
        negative_mining=opts["negative_mining"],
        goals_per_obs=opts["goals_per_obs"],
    )
    generator = torch.Generator().manual_seed(args.seed)
    loader = torch.utils.data.DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,  # upstream shuffles its test loaders; seeded here so we can repeat
        num_workers=args.num_workers,
        drop_last=False,  # upstream keeps the short trailing batch, and it counts equally
        generator=generator,
    )

    # Seed the population immediately before iteration, in every arm. The
    # sampling stream is navfm-controlled and isolated from model init, so the
    # population is a function of this seed alone.
    realised_pairs: list[tuple[str, int, str, int]] = []
    if args.population_seed is not None:
        from vint_train.data import vint_dataset as _vd

        if not hasattr(_vd, "navfm_seed_sampling"):
            raise SystemExit(
                "--population-seed requires the patched reference clone: run "
                "scripts/patch_upstream.py third_party/visualnav-transformer"
            )
        _vd.navfm_seed_sampling(args.population_seed)

    started = time.time()
    result = evaluate(
        model,
        loader,
        device=device,
        alpha=alpha,
        learn_angle=cfg["learn_angle"],
        metres_per_unit=metres_per_unit,
        limit_batches=args.limit_batches,
        progress=not args.no_progress,
    )

    if args.population_seed is not None:
        from vint_train.data import vint_dataset as _vd

        realised_pairs = [tuple(x) for x in _vd._NAVFM_REALISED_PAIRS]  # type: ignore[misc]
        if args.pair_manifest:
            from navfm import evalpairs

            problems = evalpairs.verify(evalpairs.load(Path(args.pair_manifest)), realised_pairs)
            if problems:
                raise SystemExit(
                    "gate execution invalid -- this arm scored a different evaluation "
                    "population from the one pinned pre-execution:\n"
                    + "\n".join(f"    {p}" for p in problems)
                )
            print(f"  population verified against {args.pair_manifest}")

    run_dir = run_directory(args.log_dir, run_name)
    cell, seed = cell_and_seed(run_name)

    # Archive the protocol beside the numbers it governs, and mark this gate as
    # initialised under that protocol so a later run under a different one is
    # refused by check 5 rather than silently accepted.
    if args.preregistration_commit and protocol_sha256:
        blob = prereg.protocol_blob(
            Path(__file__).resolve().parents[3], args.preregistration_commit
        )
        if blob is not None:
            (run_dir / prereg.PROTOCOL_PATH).write_bytes(blob)
        (run_dir / "preregistration.json").write_text(
            json.dumps(
                {
                    "commit": args.preregistration_commit,
                    "protocol_sha256": protocol_sha256,
                    "checks": prereg_checks,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    record = {
        **result,
        "model": args.model,
        "dataset": args.dataset,
        "split": args.split,
        "batch_size": args.batch_size,
        "limit_batches": args.limit_batches,
        "alpha": alpha,
        "learn_angle": cfg["learn_angle"],
        "metric_waypoint_spacing": spacing,
        "waypoint_spacing": opts["waypoint_spacing"],
        "checkpoint": args.checkpoint,
        "checkpoint_sha256": checkpoint_sha,
        "random_init": args.checkpoint is None,
        **evidence_block(
            evidence,
            model_initialization="random" if args.checkpoint is None else "checkpoint",
            data_source=args.data_source or args.dataset,
        ),
        "device": device,
        "kind": "eval",
        "run_name": run_name,
        "cell": cell,
        "seed": seed,
        "wall_clock_s": round(time.time() - started, 3),
        "timestamp": stamp,
    }
    config = {
        "argv": list(argv) if argv is not None else sys.argv[1:],
        "data_folder": str(data_folder),
        "split_folder": str(split_folder),
        "dataset_options": opts,
        "model_config": cfg,
        "checkpoint_load": load_census,
        "preregistration_commit": args.preregistration_commit,
        "preregistration_protocol_sha256": protocol_sha256,
        "preregistration_checks": prereg_checks,
        "checkpoint_missing_keys": missing,
        "checkpoint_unexpected_keys": unexpected,
        "checkpoint_sha256": checkpoint_sha,
        "upstream_root": str(upstream.upstream_root()),
        "upstream_commit": upstream.upstream_commit(),
        "seed": args.seed,
        "model_seed": model_seed,
        "population_seed": args.population_seed,
        "realised_pair_count": len(realised_pairs),
        "realised_population_sha256": (
            __import__("navfm.evalpairs", fromlist=["pairs_digest"]).pairs_digest(realised_pairs)
            if realised_pairs
            else None
        ),
        "num_workers": args.num_workers,
    }
    write_run_record(run_dir, metrics=record, config=config)

    record["run_dir"] = str(run_dir)
    print(_summary(record))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
