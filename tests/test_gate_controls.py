"""Negative tests for two controls that could not previously fail.

Both are the same genus, now appearing for the fifth and sixth time in this
project: a mechanism that reports success while being structurally incapable of
observing its subject.

* Check 15 read ``sha256`` and ``pair_count`` **out of the manifest it was
  checking** and tested only truthiness. Any well-formed manifest passed,
  including one describing a population nobody drew.
* The execution declaration was written, committed, and read by nothing.

The standing rule says prove both directions: a check that cannot fail
certifies nothing, and a check that cannot pass gets deleted by whoever is in a
hurry. Each control below is exercised against a known-good state *and* against
a deliberately broken one.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "protocol_freeze_audit", REPO / "scripts" / "protocol_freeze_audit.py"
)
assert _SPEC and _SPEC.loader
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)

PAIRS = [("no2vc_1_0", "3", "no2vc_1_0", "9"), ("sim1h_2_0", "0", "no5vc_4_1", "5")]


def _write_population(
    manifest_path: Path, pairs_path: Path, *, pairs=PAIRS, digest=None, count=None
):
    pairs_path.write_text("".join("\t".join(r) + "\n" for r in pairs))
    payload = "\n".join("|".join(r) for r in pairs)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "evaluation_pairs_v1",
                "sha256": digest or hashlib.sha256(payload.encode()).hexdigest(),
                "pair_count": count if count is not None else len(pairs),
            }
        )
    )


def _check15(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(audit, "PAIR_MANIFEST", tmp_path / "evaluation_pairs.json")
    monkeypatch.setattr(audit, "PAIRS_ARTEFACT", tmp_path / "evaluation_pairs.tsv")
    checks = audit.audit("HEAD", tmp_path / "absent_run", None)
    return next(c for c in checks if c.name == "evaluation_pair_manifest_digest")


class TestPopulationCheckBothDirections:
    def test_known_good_population_passes(self, monkeypatch, tmp_path: Path) -> None:
        """The direction that gets skipped: prove it can pass."""
        _write_population(tmp_path / "evaluation_pairs.json", tmp_path / "evaluation_pairs.tsv")
        result = _check15(monkeypatch, tmp_path)
        assert result.passed, result.detail
        assert "recomputed and matching" in result.detail

    def test_tampered_manifest_digest_fails(self, monkeypatch, tmp_path: Path) -> None:
        _write_population(
            tmp_path / "evaluation_pairs.json", tmp_path / "evaluation_pairs.tsv", digest="0" * 64
        )
        result = _check15(monkeypatch, tmp_path)
        assert not result.passed
        assert "recomputed digest" in result.detail

    def test_tampered_manifest_count_fails(self, monkeypatch, tmp_path: Path) -> None:
        _write_population(
            tmp_path / "evaluation_pairs.json", tmp_path / "evaluation_pairs.tsv", count=999
        )
        result = _check15(monkeypatch, tmp_path)
        assert not result.passed
        assert "pair count" in result.detail

    def test_tampered_pairs_artefact_fails(self, monkeypatch, tmp_path: Path) -> None:
        """Tamper the other side: the pairs change, the manifest does not."""
        m, a = tmp_path / "evaluation_pairs.json", tmp_path / "evaluation_pairs.tsv"
        _write_population(m, a)
        a.write_text("no2vc_1_0\t3\tno2vc_1_0\t9\nTAMPERED\t0\tX\t1\n")
        result = _check15(monkeypatch, tmp_path)
        assert not result.passed

    def test_absent_pairs_artefact_fails_rather_than_trusting_the_manifest(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """The original defect's exact shape: a digest with nothing to verify
        against must not be treated as evidence."""
        _write_population(tmp_path / "evaluation_pairs.json", tmp_path / "evaluation_pairs.tsv")
        (tmp_path / "evaluation_pairs.tsv").unlink()
        result = _check15(monkeypatch, tmp_path)
        assert not result.passed
        assert "not evidence" in result.detail


class TestDeclarationEnforcement:
    def _run(self, *extra: str) -> subprocess.CompletedProcess[str]:
        import os

        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["MPLBACKEND"] = "Agg"
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "navfm.eval.offline",
                "--model",
                "vint",
                "--dataset",
                "go_stanford",
                "--declaration",
                "gates/G0/evaluation_declaration.json",
                "--data-folder",
                "/tmp/__nonexistent__",
                *extra,
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )

    @pytest.mark.torch
    @pytest.mark.upstream
    def test_contradicting_batch_size_is_refused_by_name(self) -> None:
        out = self._run("--batch-size", "32")
        assert "gate execution invalid" in out.stdout + out.stderr
        assert "batch_size: supplied 32, declared 400" in out.stdout + out.stderr

    @pytest.mark.torch
    @pytest.mark.upstream
    def test_contradicting_population_seed_is_refused(self) -> None:
        out = self._run("--population-seed", "7")
        assert "population_seed" in out.stdout + out.stderr

    @pytest.mark.torch
    @pytest.mark.upstream
    def test_undeclared_model_seed_is_refused(self) -> None:
        out = self._run("--model-seed", "99")
        assert "model_seed" in out.stdout + out.stderr

    @pytest.mark.torch
    @pytest.mark.upstream
    def test_conforming_arguments_pass_the_declaration_gate(self) -> None:
        """Proves the control can pass: it must fail later, on the missing
        dataset, not on the declaration."""
        out = self._run("--batch-size", "400", "--population-seed", "0", "--model-seed", "0")
        combined = out.stdout + out.stderr
        assert "declaration honoured" in combined
        assert "contradict the predeclared" not in combined
