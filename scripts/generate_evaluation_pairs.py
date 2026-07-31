"""Pre-execution pass: draw the G0.c evaluation population and freeze it.

    python scripts/generate_evaluation_pairs.py \
        --data-folder ~/navfm-data/go_stanford/go_stanford \
        --split-folder gates/G0/splits/test \
        --declaration gates/G0/evaluation_declaration.json

Runs **before** any checkpoint is loaded and produces no model metric. Its only
job is to draw the (observation, goal) population the declared population seed
produces, write it out, and pin its digest — so that every arm can afterwards be
checked against a population that was fixed before any of them ran.

Two artefacts, deliberately:

* ``evaluation_pairs.tsv`` — the population itself, in draw order;
* ``evaluation_pairs.json`` — the manifest summarising it.

The manifest alone would be unverifiable. Freeze-audit check 15 recomputes the
digest and the pair count from the ``.tsv`` and compares them against the
manifest's claims, so a manifest asserting a population nobody drew fails.

Draw order matters and is preserved: the same pairs in a different order are
different batches, and every metric in this repository is batch-composition
dependent (F6).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from navfm import evalpairs, upstream


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--data-folder", required=True)
    p.add_argument("--split-folder", required=True)
    p.add_argument("--declaration", required=True)
    p.add_argument("--dataset", default="go_stanford")
    p.add_argument("--model", default="vint")
    p.add_argument("--out-dir", default="gates/G0")
    args = p.parse_args(argv)

    declared = json.loads(Path(args.declaration).read_text())
    seed = declared["population"]["evaluation_seed"]
    batch_size = declared["loader"]["batch_size"]
    num_workers = declared["loader"]["num_workers"]

    upstream.ensure_upstream()
    from vint_train.data import vint_dataset as vd

    if not hasattr(vd, "navfm_seed_sampling"):
        raise SystemExit(
            "the reference clone is unpatched: sampling would draw from the global "
            "numpy stream and the population would depend on model initialisation. "
            "Run scripts/patch_upstream.py third_party/visualnav-transformer"
        )

    cfg = upstream.model_config(args.model)
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
    print(f"dataset built: {len(dataset)} samples")

    import torch

    # Seed immediately before iteration, exactly as every arm will.
    vd.navfm_seed_sampling(seed)
    generator = torch.Generator().manual_seed(seed)
    loader = torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        drop_last=False,
        generator=generator,
    )
    for n, _ in enumerate(loader, 1):
        if n % 1 == 0:
            print(f"  batch {n}", end="\r")
    print()

    pairs = [tuple(x) for x in vd._NAVFM_REALISED_PAIRS]
    if not pairs:
        raise SystemExit("no pairs were drawn; the population would be empty")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation_pairs.tsv").write_text(
        "".join("\t".join(str(f) for f in row) + "\n" for row in pairs)
    )

    split_names = (Path(args.split_folder) / "traj_names.txt").read_text().split()
    manifest = evalpairs.build(
        pairs,  # type: ignore[arg-type]
        generation_command=(
            f"python scripts/generate_evaluation_pairs.py --data-folder {args.data_folder} "
            f"--split-folder {args.split_folder} --declaration {args.declaration}"
        ),
        population_seed=seed,
        dataset_digest=json.loads((Path("gates/G0/splits/split_manifest.json")).read_text())[
            "source_sha256"
        ],
        split_digest=hashlib.sha256("\n".join(split_names).encode()).hexdigest(),
        trajectory_count=len(split_names),
    )
    evalpairs.save(manifest, out / "evaluation_pairs.json")

    print(f"population frozen: {manifest.pair_count} pairs, digest {manifest.sha256[:16]}")
    print(f"  {out / 'evaluation_pairs.tsv'}")
    print(f"  {out / 'evaluation_pairs.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
