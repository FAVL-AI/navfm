"""Tests for ``scripts/make_tables.py``.

The script is the only path from a ``runs/`` directory to a number in the
paper, so the properties worth pinning are the ones that would let a wrong
number through quietly:

* missing seeds are a hard failure, not a narrower interval;
* two runs claiming one cell is a failure, not a directory-order coin flip;
* a training run contributes its LAST epoch, not its first or an average;
* the run-name grammar in the docstring is the grammar the code implements.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "make_tables", Path(__file__).resolve().parents[1] / "scripts" / "make_tables.py"
)
assert _SPEC and _SPEC.loader
make_tables = importlib.util.module_from_spec(_SPEC)
sys.modules["make_tables"] = make_tables
_SPEC.loader.exec_module(make_tables)


def write_eval(root: Path, name: str, **metrics):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    cell, seed = make_tables.parse_run_name(name)
    payload = {
        "cell": cell,
        "seed": seed,
        "kind": "eval",
        "batch_size": 400,
        "evidence_class": "registered_experiment",
        "scientific_result": True,
        "checkpoint_sha256": "0" * 64,
        "environment_id": "e" * 64,
        "strict": {"total_loss": metrics.get("total_loss", 0.2), "action_loss": 0.3},
        "plain": {"total_loss": 0.21},
        "ade_m": metrics.get("ade_m", 0.5),
        "fde_m": 0.9,
        **{k: v for k, v in metrics.items() if k not in {"total_loss", "ade_m"}},
    }
    (d / "metrics.json").write_text(json.dumps(payload))
    return d


def write_train_epochs(root: Path, name: str, losses: list[float]):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    cell, seed = make_tables.parse_run_name(name)
    for epoch, loss in enumerate(losses):
        (d / f"metrics_epoch_{epoch}.json").write_text(
            json.dumps(
                {
                    "cell": cell,
                    "seed": seed,
                    "kind": "train",
                    "evidence_class": "registered_experiment",
                    "scientific_result": True,
                    "checkpoint_sha256": "0" * 64,
                    "environment_id": "e" * 64,
                    "epoch": epoch,
                    "eval_batch_size": 400,
                    "eval": {"strict": {"total_loss": loss}, "ade_m": loss / 2},
                }
            )
        )
    return d


# ------------------------------------------------------------------- name parse


@pytest.mark.parametrize(
    ("name", "cell", "seed"),
    [
        ("e1_vint_diff_seed0", "e1_vint_diff", 0),
        ("e2_nonholo_holo_seed1", "e2_nonholo_holo", 1),
        ("e3_0p25h_pretrained_replay_seed2", "e3_0p25h_pretrained_replay", 2),
        ("e4_derived_published_seed0", "e4_derived_published", 0),
        ("e5_lightmat_noise_seed10", "e5_lightmat_noise", 10),
        ("e6_corridor_ft_seed0", "e6_corridor_ft", 0),
        ("e0.2_vint_go_stanford", "e0.2_vint_go_stanford", None),
        ("eval_vint_recon_test_20260731-120000", None, None),
        ("scratch_dir", None, None),
    ],
)
def test_run_name_grammar_matches_the_documented_convention(name, cell, seed):
    assert make_tables.parse_run_name(name) == (cell, seed)


def test_ad_hoc_eval_directories_are_not_results(tmp_path):
    """A timestamped exploratory eval must never silently become a table row."""
    write_eval(tmp_path, "eval_vint_recon_test_20260731-120000")
    assert make_tables.load_records(tmp_path) == []


# --------------------------------------------------------------- seed discipline


def test_missing_seeds_are_a_hard_failure(tmp_path, capsys):
    write_eval(tmp_path, "e2_nonholo_diff_seed0")
    write_eval(tmp_path, "e2_nonholo_diff_seed1")  # seed 2 never ran

    rc = make_tables.main(["--runs", str(tmp_path), "--out", str(tmp_path / "out")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "missing [2]" in err
    assert not (tmp_path / "out").exists(), "no table may be written on an incomplete cell"


def test_allow_incomplete_marks_the_cell_and_still_fails(tmp_path):
    write_eval(tmp_path, "e2_nonholo_diff_seed0")
    write_eval(tmp_path, "e2_nonholo_diff_seed1")

    rc = make_tables.main(
        ["--runs", str(tmp_path), "--out", str(tmp_path / "out"), "--allow-incomplete"]
    )
    assert rc == 2, "an incomplete matrix must never exit 0"
    text = (tmp_path / "out" / "table4.md").read_text()
    assert "INCOMPLETE 2/3" in text


def test_a_complete_cell_passes(tmp_path):
    for seed in range(3):
        write_eval(tmp_path, f"e2_nonholo_diff_seed{seed}", total_loss=0.2 + 0.01 * seed)
    rc = make_tables.main(
        ["--runs", str(tmp_path), "--out", str(tmp_path / "out"), "--n-boot", "200"]
    )
    assert rc == 0
    text = (tmp_path / "out" / "table4.md").read_text()
    assert "e2_nonholo_diff" in text
    assert "0,1,2" in text
    assert "[" in text, "a complete cell must carry a bootstrap interval"


def test_e0_needs_only_one_run(tmp_path):
    """E0.2 is a single deterministic evaluation of a released checkpoint;
    demanding three seeds of it would be demanding three identical numbers."""
    write_eval(tmp_path, "e0.2_vint_go_stanford")
    assert make_tables.main(["--runs", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    assert "(n=1)" in (tmp_path / "out" / "table3.md").read_text()


def test_duplicate_cell_and_seed_is_refused(tmp_path):
    """Two directories claiming one cell would make the table depend on
    filesystem ordering."""
    write_eval(tmp_path, "e2_holo_holo_seed0")
    d = tmp_path / "rerun"
    d.mkdir()
    (d / "metrics.json").write_text(json.dumps({"cell": "e2_holo_holo", "seed": 0, "strict": {}}))

    with pytest.raises(SystemExit, match="two runs claim cell"):
        make_tables.load_records(tmp_path) and make_tables.group(make_tables.load_records(tmp_path))


# ------------------------------------------------------------------- aggregation


def test_a_training_run_contributes_its_last_epoch(tmp_path):
    write_train_epochs(tmp_path, "e2_holo_diff_seed0", [0.9, 0.5, 0.11])
    (record,) = make_tables.load_records(tmp_path)
    assert record.epoch == 2
    assert record.get("strict.total_loss") == pytest.approx(0.11)


def _write_random_init_cell(tmp_path):
    for seed in range(3):
        write_eval(
            tmp_path,
            f"e1_vint_diff_seed{seed}",
            random_init=True,
            evidence_class="random_init_control",
            scientific_result=False,
            checkpoint_sha256=None,
        )


def test_random_init_runs_are_refused_outright(tmp_path):
    """A plumbing smoke run must not be able to pass as a result even if
    someone names it like a cell. Labelling it in the table was the old, weaker
    defence: by then the number is already rendered and citable."""
    _write_random_init_cell(tmp_path)
    out = tmp_path / "out"
    assert make_tables.main(["--runs", str(tmp_path), "--out", str(out), "--n-boot", "100"]) == 3
    assert not out.exists() or not list(out.glob("*.md")), "a refused table was still written"


def test_include_smoke_emits_but_watermarks_and_still_labels(tmp_path):
    """The override exists so smoke output can be inspected, not laundered."""
    _write_random_init_cell(tmp_path)
    out = tmp_path / "out"
    make_tables.main(
        ["--runs", str(tmp_path), "--out", str(out), "--n-boot", "100", "--include-smoke"]
    )
    text = (out / "table3.md").read_text()
    assert "NOT A SCIENTIFIC RESULT" in text, "smoke output was emitted without a watermark"
    assert "RANDOM INIT" in text
    assert text.index("NOT A SCIENTIFIC RESULT") < text.index("RANDOM INIT"), (
        "the watermark must precede the table, not trail it"
    )


def test_only_one_orientation_cosine_is_tabulated():
    """Finding F12: the reference logs the same number twice. Printing both
    would present one measurement as two pieces of evidence."""
    columns = [c for c, _ in make_tables.OFFLINE_COLUMNS]
    assert "strict.action_orien_cos_sim" in columns
    assert "strict.multi_action_orien_cos_sim" not in columns


def test_the_batch_size_appears_in_every_table(tmp_path):
    """docs/EXPERIMENTS.md: 'a metric without its batch size is not a metric here'."""
    for seed in range(3):
        write_eval(tmp_path, f"e5_full_noise_seed{seed}")
    make_tables.main(["--runs", str(tmp_path), "--out", str(tmp_path / "out"), "--n-boot", "100"])
    text = (tmp_path / "out" / "table7.md").read_text()
    assert "batch size: 400" in text
    assert "issue #51" in text


def test_tables_are_deterministic(tmp_path):
    """The bootstrap is seeded, so re-running the script on unchanged runs must
    not perturb a published interval."""
    for seed in range(3):
        write_eval(tmp_path, f"e4_derived_derived_seed{seed}", total_loss=0.2 + 0.05 * seed)
    args = ["--runs", str(tmp_path), "--out", str(tmp_path / "out"), "--n-boot", "500"]
    make_tables.main(args)
    first = (tmp_path / "out" / "table6.md").read_text()
    make_tables.main(args)
    assert (tmp_path / "out" / "table6.md").read_text() == first


def test_missing_checkpoint_hash_on_a_scientific_row_is_refused(tmp_path):
    """A scientific claim must identify which bytes produced it."""
    for seed in range(3):
        write_eval(tmp_path, f"e1_vint_diff_seed{seed}", checkpoint_sha256=None)
    assert make_tables.main(["--runs", str(tmp_path), "--out", str(tmp_path / "o")]) == 3


def test_mixed_environment_identities_are_refused(tmp_path):
    """Two instruments are not one instrument."""
    for seed in range(3):
        write_eval(
            tmp_path,
            f"e1_vint_diff_seed{seed}",
            environment_id=("a" * 64) if seed == 0 else ("b" * 64),
        )
    assert make_tables.main(["--runs", str(tmp_path), "--out", str(tmp_path / "o")]) == 3


def test_mixed_environments_can_be_overridden_explicitly(tmp_path):
    for seed in range(3):
        write_eval(
            tmp_path,
            f"e1_vint_diff_seed{seed}",
            environment_id=("a" * 64) if seed == 0 else ("b" * 64),
        )
    assert (
        make_tables.main(
            ["--runs", str(tmp_path), "--out", str(tmp_path / "o"), "--allow-mixed-environments"]
        )
        == 0
    )


def test_undeclared_evidence_does_not_inherit_table_access(tmp_path):
    """A run predating evidence classes must not be treated as a result by
    silence -- absent declaration is the conservative case, not the permissive
    one."""
    for seed in range(3):
        d = tmp_path / f"e1_vint_diff_seed{seed}"
        d.mkdir(parents=True)
        (d / "metrics.json").write_text(
            json.dumps(
                {
                    "cell": "e1_vint_diff",
                    "seed": seed,
                    "kind": "eval",
                    "batch_size": 400,
                    "strict": {"total_loss": 0.2},
                    "plain": {"total_loss": 0.2},
                }
            )
        )
    assert make_tables.main(["--runs", str(tmp_path), "--out", str(tmp_path / "o")]) == 3


def test_every_rendered_table_gets_a_lineage_source(tmp_path):
    """Markdown is where a number stops being traceable; the JSONL is the way
    back to the bytes, the split, the seed and the instrument."""
    for seed in range(3):
        write_eval(tmp_path, f"e1_vint_diff_seed{seed}")
    out = tmp_path / "out"
    assert make_tables.main(["--runs", str(tmp_path), "--out", str(out), "--n-boot", "100"]) == 0

    lineage = out / "table3.jsonl"
    assert lineage.is_file(), "a table was rendered with no machine-readable source"
    rows = [json.loads(line) for line in lineage.read_text().splitlines()]
    assert len(rows) == 3, "one row per (cell, seed) behind the table"

    for row in rows:
        for field in (
            "run_dir",
            "raw_artefact",
            "checkpoint_sha256",
            "seed",
            "config_digest",
            "evaluator_commit",
            "environment_id",
            "dataset_split_digest",
            "preregistration_commit",
            "evidence_class",
            "batch_size",
            "metrics",
        ):
            assert field in row, f"lineage row omits {field}"
        assert Path(row["raw_artefact"]).is_file(), "raw artefact path does not resolve"
        assert row["metrics"], "lineage row carries no metric values"


def test_lineage_seeds_match_the_rendered_cell(tmp_path):
    for seed in range(3):
        write_eval(tmp_path, f"e1_vint_diff_seed{seed}", total_loss=0.1 * seed)
    out = tmp_path / "out"
    make_tables.main(["--runs", str(tmp_path), "--out", str(out), "--n-boot", "100"])
    rows = [json.loads(line) for line in (out / "table3.jsonl").read_text().splitlines()]
    assert sorted(r["seed"] for r in rows) == [0, 1, 2]
    assert {r["cell"] for r in rows} == {"e1_vint_diff"}
