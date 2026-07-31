#!/usr/bin/env python3
"""Turn ``runs/*/metrics*.json`` into ``paper/tables/*.md``.

    python scripts/make_tables.py                    # regenerate every table
    python scripts/make_tables.py --tables 3 4       # just these
    python scripts/make_tables.py --runs runs --out paper/tables

This is the only route by which a number reaches the paper. ``paper/draft.md``
section 5 says so and contains no hand-typed results; gate G4.c requires it
("results tables auto-generated from the logs by script, not hand-typed").

RUN-NAME CONVENTION
===================

A run's directory name encodes which cell of ``docs/EXPERIMENTS.md`` it fills.
The grammar is ``<cell>_seed<k>``, where ``<cell>`` starts with the experiment
id and the remaining underscore-separated fields are that experiment's factors
in the order given below. Seeds are integers; a cell missing any expected seed
is a hard error, never an average of what happened to be there.

===== ============================================== ==============================
exp   pattern                                        example
===== ============================================== ==============================
E0    ``e0.2_<model>_<dataset>``                     ``e0.2_vint_go_stanford``
E1    ``e1_<model>_<exec>_seed<k>``                  ``e1_vint_diff_seed0``
E2    ``e2_<demo>_<exec>_seed<k>``                   ``e2_nonholo_holo_seed1``
E3    ``e3_<hours>h_<init>_<replay>_seed<k>``        ``e3_0p25h_pretrained_replay_seed2``
E4    ``e4_<spacing>_<stats>_seed<k>``               ``e4_derived_published_seed0``
E5    ``e5_<rand>_<noise>_seed<k>``                  ``e5_lightmat_noise_seed0``
E6    ``e6_<env>_<arm>_seed<k>``                     ``e6_corridor_ft_seed0``
===== ============================================== ==============================

Vocabulary, fixed so a cell id is readable without a decoder ring:
``model`` ∈ {vint, gnm, nomad, oracle, random}; ``exec`` ∈ {diff, holo};
``demo`` ∈ {nonholo, holo}; ``hours`` uses ``p`` for the decimal point
(``0p25h``); ``init`` ∈ {pretrained, scratch}; ``replay`` ∈ {replay, noreplay};
``spacing``/``stats`` ∈ {published, derived}; ``rand`` ∈ {none, light,
lightmat, full}; ``noise`` ∈ {noise, nonoise}.

E0 cells are single deterministic evaluations and require one run rather than
three seeds; every other experiment requires ``--require-seeds`` (default 3,
per docs/EXPERIMENTS.md "Seeds. Three per cell minimum").

Both entrypoints stamp ``cell`` and ``seed`` into their own ``metrics.json``,
so grouping normally reads those fields and only falls back to parsing the
directory name for records written before that, or renamed by hand.

WHAT IT REFUSES TO DO
=====================

Fail loudly on missing seeds. A cell with 2 of 3 seeds is not a cell with a
slightly wider interval -- it is a cell whose third run crashed, or was killed
for looking wrong, and averaging the survivors is how a matrix quietly becomes
a selection of favourable runs. ``--allow-incomplete`` prints the tables anyway,
marks every short cell inline, and still exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from navfm.eval.metrics import bootstrap_ci

#: Experiment id -> (paper table number, title). Bound to paper/draft.md's
#: "Results" slot table; changing one without the other breaks G6's traceability.
TABLES: dict[str, tuple[int, str]] = {
    "e0": (3, "E0.2 reproduction + E1 zero-shot baselines"),
    "e1": (3, "E0.2 reproduction + E1 zero-shot baselines"),
    "e2": (4, "E2 demonstrator x execution (2x2), with interaction term"),
    "e3": (5, "E3 data-efficiency curve"),
    "e4": (6, "E4 normalisation-constants ablation"),
    "e5": (7, "E5 randomisation ablation"),
    "e6": (8, "E6 physical transfer"),
}

#: Offline columns worth tabulating, in reporting order. F12: only ONE of the
#: two orientation cosines appears -- they are the same number, and printing
#: both would present one measurement as two independent pieces of evidence.
OFFLINE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("strict.total_loss", "total loss"),
    ("strict.action_loss", "action loss"),
    ("strict.dist_loss", "dist loss"),
    ("strict.multi_action_waypts_cos_sim", "multi-action cos"),
    ("strict.action_orien_cos_sim", "orien cos"),
    ("ade_m", "ADE (m)"),
    ("fde_m", "FDE (m)"),
)

_SEEDED = re.compile(r"^(?P<cell>e\d(?:[._]\d+)?_.+?)_seed(?P<seed>\d+)$")
_UNSEEDED = re.compile(r"^(?P<cell>e\d(?:[._]\d+)?_.+)$")


@dataclass
class Record:
    """One metrics file, reduced to what a table needs."""

    path: Path
    cell: str
    seed: int | None
    epoch: int | None
    metrics: dict[str, Any]
    random_init: bool = False
    batch_size: int | None = None
    evidence_class: str | None = None
    scientific_result: bool = False
    checkpoint_sha256: str | None = None
    environment_id: str | None = None

    @property
    def experiment(self) -> str:
        return self.cell.split("_", 1)[0].split(".", 1)[0]

    def get(self, dotted: str) -> float | None:
        node: Any = self.metrics
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return float(node) if isinstance(node, (int, float)) else None


@dataclass
class Cell:
    cell: str
    records: dict[int | None, Record] = field(default_factory=dict)

    @property
    def seeds(self) -> list[int | None]:
        return sorted(self.records, key=lambda s: (s is None, s))

    def values(self, column: str) -> list[float]:
        return [v for r in self.records.values() if (v := r.get(column)) is not None]


def parse_run_name(name: str) -> tuple[str | None, int | None]:
    """``('e2_holo_diff', 1)`` from ``'e2_holo_diff_seed1'``; ``(None, None)``
    for a name that does not follow the convention (an ad-hoc eval, say)."""
    if m := _SEEDED.match(name):
        return m.group("cell"), int(m.group("seed"))
    if m := _UNSEEDED.match(name):
        return m.group("cell"), None
    return None, None


def load_records(runs_root: Path) -> list[Record]:
    """Every ``metrics*.json`` under ``runs/*/``, newest epoch per training run.

    A training run writes one file per epoch; only the last is a result. An
    eval run writes a single ``metrics.json``.
    """
    by_run: dict[Path, list[tuple[int | None, Path]]] = defaultdict(list)
    for path in sorted(runs_root.glob("*/metrics*.json")):
        m = re.search(r"metrics_epoch_(\d+)\.json$", path.name)
        by_run[path.parent].append((int(m.group(1)) if m else None, path))

    out: list[Record] = []
    for run_dir, entries in sorted(by_run.items()):
        epoch, path = max(entries, key=lambda e: (e[0] is not None, e[0] or 0))
        data = json.loads(path.read_text())

        cell = data.get("cell")
        seed = data.get("seed")
        if not cell:
            cell, parsed_seed = parse_run_name(run_dir.name)
            seed = parsed_seed if seed is None else seed
        if not cell:
            continue  # not an experiment-matrix run; ad-hoc evals are not results

        payload = dict(data)
        if isinstance(data.get("eval"), dict):
            # A training record nests its eval metrics; that is the result.
            payload = {**data["eval"], **{k: v for k, v in data.items() if k != "eval"}}
        out.append(
            Record(
                path=path,
                cell=str(cell),
                seed=None if seed is None else int(seed),
                epoch=epoch,
                metrics=payload,
                random_init=bool(data.get("random_init")),
                batch_size=data.get("batch_size") or data.get("eval_batch_size"),
                evidence_class=data.get("evidence_class"),
                # Absent declaration is NOT a result. A run predating evidence
                # classes, or one that declined to declare, must not inherit
                # table access by silence.
                scientific_result=bool(data.get("scientific_result", False)),
                checkpoint_sha256=data.get("checkpoint_sha256"),
                environment_id=(data.get("environment") or {}).get("environment_id")
                if isinstance(data.get("environment"), dict)
                else data.get("environment_id"),
            )
        )
    return out


def group(records: Sequence[Record]) -> dict[str, Cell]:
    cells: dict[str, Cell] = {}
    for r in records:
        cell = cells.setdefault(r.cell, Cell(r.cell))
        prior = cell.records.get(r.seed)
        if prior is not None and prior.path != r.path:
            raise SystemExit(
                f"two runs claim cell {r.cell!r} seed {r.seed}:\n"
                f"  {prior.path}\n  {r.path}\n"
                "Rename one, or set an explicit `cell` in its metrics.json. Silently "
                "keeping one of them would make the table depend on directory order."
            )
        cell.records[r.seed] = r
    return cells


def required_seeds(experiment: str, n: int) -> set[int] | None:
    """E0 is a single deterministic evaluation; everything else needs n seeds."""
    return None if experiment == "e0" else set(range(n))


def check_seeds(cells: dict[str, Cell], n: int) -> list[str]:
    problems = []
    for name, cell in sorted(cells.items()):
        want = required_seeds(cell.records[cell.seeds[0]].experiment, n)
        if want is None:
            continue
        have = {s for s in cell.records if s is not None}
        if missing := sorted(want - have):
            problems.append(f"{name}: has seeds {sorted(have) or '[]'}, missing {missing}")
    return problems


def fmt(
    mean: float | None, lo: float | None = None, hi: float | None = None, digits: int = 4
) -> str:
    if mean is None:
        return "--"
    if lo is None or hi is None or lo != lo:
        return f"{mean:.{digits}f}"
    return f"{mean:.{digits}f} [{lo:.{digits}f}, {hi:.{digits}f}]"


def summarise(cell: Cell, column: str, *, n_boot: int, seed: int) -> str:
    values = cell.values(column)
    if not values:
        return "--"
    mean = sum(values) / len(values)
    if len(values) < 2:
        # A bootstrap over one point is the point. Say so rather than printing
        # a zero-width interval that looks like a measurement.
        return f"{mean:.4f} (n=1)"
    lo, hi = bootstrap_ci(values, n_boot=n_boot, alpha=0.05, seed=seed)
    return fmt(mean, lo, hi)


WATERMARK = (
    "> **SMOKE-CONTAMINATED TABLE — NOT A SCIENTIFIC RESULT.**\n"
    "> Emitted with `--include-smoke`. One or more rows come from runs whose own\n"
    "> record declares `scientific_result: false`. This file must not be cited,\n"
    "> quoted, or copied into the paper.\n"
)


def contamination_check(
    records: Sequence[Record],
    *,
    include_smoke: bool,
    allow_mixed_environments: bool,
) -> list[str]:
    """Reasons these records may not form a results table.

    The barrier reads each run's own declaration rather than re-deriving what
    kind of evidence it is. A run that says it is not a scientific result is
    not one, whatever its numbers look like.
    """
    problems: list[str] = []

    if not include_smoke:
        contaminated = sorted(
            f"{r.cell} seed {r.seed}: evidence_class={r.evidence_class or '(undeclared)'}"
            for r in records
            if not r.scientific_result
        )
        if contaminated:
            problems.append(
                "non-scientific rows present (declare --include-smoke to emit anyway, "
                "which watermarks the output):\n" + "\n".join(f"    {c}" for c in contaminated)
            )

    missing_hash = sorted(
        f"{r.cell} seed {r.seed}"
        for r in records
        if r.scientific_result and not r.checkpoint_sha256 and not r.random_init
    )
    if missing_hash:
        problems.append(
            "scientific rows with no checkpoint hash -- the bytes that produced the "
            "number are unidentifiable:\n" + "\n".join(f"    {m}" for m in missing_hash)
        )

    if not allow_mixed_environments:
        environments = {r.environment_id for r in records if r.environment_id}
        undeclared = [r for r in records if not r.environment_id]
        if len(environments) > 1:
            problems.append(
                "rows produced under different environment identities, which are not "
                "comparable instruments (pass --allow-mixed-environments to override, "
                "recorded in the table):\n" + "\n".join(f"    {e}" for e in sorted(environments))
            )
        if environments and undeclared:
            problems.append(
                f"{len(undeclared)} row(s) declare no environment identity while others do; "
                "the table would mix a known instrument with an unknown one"
            )
    return problems


def render_table(
    number: int,
    title: str,
    cells: dict[str, Cell],
    *,
    n_boot: int,
    seed: int,
    incomplete: set[str],
    require: int,
) -> str:
    columns = OFFLINE_COLUMNS
    head = "| cell | seeds | " + " | ".join(label for _, label in columns) + " |"
    rule = "|---|---|" + "---|" * len(columns)
    lines = [f"### Table {number} — {title}", "", head, rule]

    batch_sizes = {r.batch_size for c in cells.values() for r in c.records.values() if r.batch_size}
    for name, cell in sorted(cells.items()):
        seeds = [s for s in cell.seeds if s is not None]
        label = name
        if name in incomplete:
            label += f" **INCOMPLETE {len(seeds)}/{require}**"
        if any(r.random_init for r in cell.records.values()):
            label += " **RANDOM INIT — not a result**"
        row = [label, ",".join(str(s) for s in seeds) or "--"]
        row += [summarise(cell, col, n_boot=n_boot, seed=seed) for col, _ in columns]
        lines.append("| " + " | ".join(row) + " |")

    lines += [
        "",
        f"Mean over seeds with a percentile bootstrap 95 % CI ({n_boot} resamples). "
        f"Evaluation batch size: {', '.join(str(b) for b in sorted(batch_sizes)) or 'unrecorded'} "
        "— the reference metrics are batch-size dependent (upstream issue #51), so a "
        "number without its batch size is not comparable. `strict` reduction throughout "
        "(the reference `action_reduce`, +1e-2 guard); `plain` values are in each run's "
        "`metrics.json`. Only one orientation cosine is shown: the two the reference logs "
        "are the same number (finding F12).",
        "",
        "Source runs:",
        "",
    ]
    for name, cell in sorted(cells.items()):
        for s in cell.seeds:
            lines.append(f"- `{name}` seed {s}: `{cell.records[s].path}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="scripts/make_tables.py",
        description="Regenerate paper/tables/*.md from runs/ logs. The only path from a run to the paper.",
    )
    p.add_argument("--runs", default="runs", help="directory of run directories")
    p.add_argument("--out", default="paper/tables", help="where the markdown lands")
    p.add_argument("--tables", nargs="*", type=int, default=None, help="only these table numbers")
    p.add_argument("--require-seeds", type=int, default=3, help="per docs/EXPERIMENTS.md")
    p.add_argument("--n-boot", type=int, default=10_000)
    p.add_argument("--seed", type=int, default=0, help="seeds the bootstrap resampling")
    p.add_argument(
        "--include-smoke",
        action="store_true",
        help="emit tables containing non-scientific rows; watermarks every file it writes",
    )
    p.add_argument(
        "--allow-mixed-environments",
        action="store_true",
        help="permit rows from different environment identities; recorded in the table",
    )
    p.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="emit tables with short cells marked inline; still exits non-zero",
    )
    args = p.parse_args(argv)

    runs_root = Path(args.runs)
    if not runs_root.is_dir():
        print(f"no runs directory at {runs_root}", file=sys.stderr)
        return 1

    records = load_records(runs_root)
    if not records:
        print(
            f"no matrix runs found under {runs_root}. Run directories must be named per the "
            "convention in this script's docstring (e.g. e2_nonholo_holo_seed0); ad-hoc "
            "eval directories are deliberately ignored.",
            file=sys.stderr,
        )
        return 1

    contamination = contamination_check(
        records,
        include_smoke=args.include_smoke,
        allow_mixed_environments=args.allow_mixed_environments,
    )
    if contamination:
        print(
            "refusing to write results tables: the records do not qualify as scientific "
            "evidence.\nA table is the last place a non-result can be caught, and the "
            "first place it becomes citable.\n",
            file=sys.stderr,
        )
        for problem in contamination:
            print(f"  {problem}\n", file=sys.stderr)
        return 3

    cells = group(records)
    problems = check_seeds(cells, args.require_seeds)
    incomplete = {line.split(":", 1)[0] for line in problems}

    if problems and not args.allow_incomplete:
        print(
            f"refusing to write tables: {len(problems)} cell(s) are missing seeds.\n"
            "Averaging the seeds that happen to have finished is how a pre-registered\n"
            "matrix quietly becomes a selection of favourable runs.\n",
            file=sys.stderr,
        )
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nRun the missing seeds, or pass --allow-incomplete to emit tables with\n"
            "every short cell marked inline (still exits non-zero).",
            file=sys.stderr,
        )
        return 2

    by_table: dict[int, tuple[str, dict[str, Cell]]] = {}
    for name, cell in cells.items():
        exp = cell.records[cell.seeds[0]].experiment
        if exp not in TABLES:
            print(
                f"warning: cell {name!r} has no table mapping for {exp!r}; skipped", file=sys.stderr
            )
            continue
        number, title = TABLES[exp]
        by_table.setdefault(number, (title, {}))[1][name] = cell

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for number, (title, group_cells) in sorted(by_table.items()):
        if args.tables and number not in args.tables:
            continue
        text = render_table(
            number,
            title,
            group_cells,
            n_boot=args.n_boot,
            seed=args.seed,
            incomplete=incomplete,
            require=args.require_seeds,
        )
        path = out_dir / f"table{number}.md"
        path.write_text(WATERMARK + "\n" + text if args.include_smoke else text)
        written.append((path, len(group_cells)))

    for path, n in written:
        print(f"wrote {path}  ({n} cells)")
    if problems:
        print(f"\n{len(problems)} incomplete cell(s) — marked in the tables:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
