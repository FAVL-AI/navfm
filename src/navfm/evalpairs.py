"""The evaluation-pair manifest: the population, frozen and digest-verified.

Upstream's `_sample_goal` drew from the global NumPy stream, so seeding a model
also changed *which* (observation, goal) pairs were scored. Model identity and
evaluation population were two experimental factors riding one RNG. The
`sampling_rng_isolation` patch separates the streams; this module freezes the
population the separated stream produces.

The manifest is a **first-class artefact**, not an implementation detail. It is
generated in a pre-execution pass under the declared population seed, its digest
is pinned, and every arm — both checkpoint runs and all three controls —
verifies its realised pairs against it at runtime. The population is therefore
verified *directly* rather than reconstructed indirectly from a seed, which
matters because a seed only reproduces a population under an unchanged sampler,
and the sampler is upstream code we patch.

    python -m navfm.evalpairs --dataset go_stanford --split test \
        --population-seed 0 --out gates/G0/evaluation_pairs.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "SCHEMA_VERSION",
    "EvaluationPairManifest",
    "manifest_digest",
    "pairs_digest",
    "verify",
]

SCHEMA_VERSION = "evaluation_pairs_v1"


@dataclass(frozen=True)
class EvaluationPairManifest:
    """The eight recorded fields. Each is load-bearing, none is decoration."""

    schema_version: str
    sha256: str
    generation_command: str
    population_seed: int
    dataset_digest: str
    split_digest: str
    trajectory_count: int
    pair_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def pairs_digest(pairs: list[tuple[str, int, str, int]]) -> str:
    """Digest of the realised population, in draw order.

    Order is part of the population: two runs drawing the same pairs in a
    different order have scored the same samples in different batches, and
    every metric in this repository is batch-composition dependent.
    """
    payload = "\n".join(f"{a}|{b}|{c}|{d}" for a, b, c, d in pairs)
    return hashlib.sha256(payload.encode()).hexdigest()


def manifest_digest(manifest: EvaluationPairManifest) -> str:
    """Digest over every field except ``sha256`` itself."""
    body = {k: v for k, v in manifest.to_dict().items() if k != "sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build(
    pairs: list[tuple[str, int, str, int]],
    *,
    generation_command: str,
    population_seed: int,
    dataset_digest: str,
    split_digest: str,
    trajectory_count: int,
) -> EvaluationPairManifest:
    partial = EvaluationPairManifest(
        schema_version=SCHEMA_VERSION,
        sha256="",
        generation_command=generation_command,
        population_seed=population_seed,
        dataset_digest=dataset_digest,
        split_digest=split_digest,
        trajectory_count=trajectory_count,
        pair_count=len(pairs),
    )
    return EvaluationPairManifest(**{**partial.to_dict(), "sha256": pairs_digest(pairs)})


def verify(
    manifest: EvaluationPairManifest, realised: list[tuple[str, int, str, int]]
) -> list[str]:
    """Mismatches between the pinned population and what an arm actually scored."""
    problems: list[str] = []
    if manifest.schema_version != SCHEMA_VERSION:
        problems.append(
            f"schema {manifest.schema_version!r} != {SCHEMA_VERSION!r}; the manifest was "
            f"written by a different generator and its fields may not mean what they say"
        )
    if len(realised) != manifest.pair_count:
        problems.append(f"pair count {len(realised)} != pinned {manifest.pair_count}")
    actual = pairs_digest(realised)
    if actual != manifest.sha256:
        problems.append(
            f"population digest {actual[:16]} != pinned {manifest.sha256[:16]} -- this arm "
            f"scored a different (observation, goal) population from the one frozen "
            f"pre-execution, so it is not comparable to the other arms"
        )
    return problems


def load(path: Path) -> EvaluationPairManifest:
    data = json.loads(Path(path).read_text())
    return EvaluationPairManifest(**{k: data[k] for k in EvaluationPairManifest.__annotations__})


def save(manifest: EvaluationPairManifest, path: Path) -> None:
    Path(path).write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", required=True)
    p.add_argument("--population-seed", type=int, required=True)
    p.add_argument("--dataset-digest", required=True)
    p.add_argument("--split-digest", required=True)
    p.add_argument("--trajectory-count", type=int, required=True)
    p.add_argument(
        "--pairs", required=True, help="JSON list of [obs_traj, obs_t, goal_traj, goal_t]"
    )
    args = p.parse_args(argv)

    pairs = [tuple(x) for x in json.loads(Path(args.pairs).read_text())]
    manifest = build(
        pairs,  # type: ignore[arg-type]
        generation_command=" ".join(["python -m navfm.evalpairs", *(argv or [])]),
        population_seed=args.population_seed,
        dataset_digest=args.dataset_digest,
        split_digest=args.split_digest,
        trajectory_count=args.trajectory_count,
    )
    save(manifest, Path(args.out))
    print(f"wrote {args.out}: {manifest.pair_count} pairs, digest {manifest.sha256[:16]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
