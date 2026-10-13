import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from prospective_collection_contracts_v1 import (
    admission,
    amended_capture,
    persist_measurement,
    validate_capsule,
)


def args_with_data(tmp_path):
    import hashlib

    frames = []
    for route, count in [
        ("synthetic_layout0_route0", 36),
        ("synthetic_layout0_route1", 36),
        ("synthetic_layout1_route0", 36),
        ("synthetic_layout1_route1", 36),
    ]:
        directory = tmp_path / "data" / route
        directory.mkdir(parents=True)
        for tick in range(count):
            image = directory / f"{tick}.jpg"
            image.write_bytes(f"known fixture {route} {tick}".encode())
            frames.append(
                dict(
                    route=route,
                    tick=tick,
                    status="PASS",
                    sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                )
            )
        (directory / "traj_data.pkl").write_bytes(b"known fixture label placeholder")
    spec = tmp_path / "specification.json"
    spec.write_text(
        json.dumps(
            {
                "layouts": [
                    {
                        "routes": [
                            {"id": "synthetic_layout0_route0"},
                            {"id": "synthetic_layout0_route1"},
                        ]
                    },
                    {
                        "routes": [
                            {"id": "synthetic_layout1_route0"},
                            {"id": "synthetic_layout1_route1"},
                        ]
                    },
                ]
            }
        )
    )
    return SimpleNamespace(out=tmp_path, spec=spec, frames=frames)


def test_capsule_is_atomic_before_nonreturning_context_exit(tmp_path):
    args = args_with_data(tmp_path)

    class Shutdown:
        def __enter__(self):
            return self

        def __exit__(self, *values):
            assert (
                json.loads((tmp_path / "measurement_complete.json").read_text())[
                    "measurement_status"
                ]
                == "COMPLETE"
            )
            raise SystemExit(0)

    source = """def main():
    with Shutdown():
        report={'status':'STARTED','mode':'acquire','frames':args.frames}
        report['status']='PASS'
main()
"""
    with pytest.raises(SystemExit):
        exec(
            compile(amended_capture(source), "mock-capture", "exec"),
            {"Shutdown": Shutdown, "args": args, "persist_measurement": persist_measurement},
        )
    capsule = json.loads((tmp_path / "measurement_complete.json").read_text())
    validate_capsule(capsule, tmp_path, json.loads(args.spec.read_text()))
    assert admission(capsule, 0, False, True, True)["status"] == "PASS"
    (tmp_path / "data" / "synthetic_layout0_route0" / "0.jpg").write_bytes(b"altered")
    with pytest.raises(ValueError, match="drift"):
        validate_capsule(capsule, tmp_path, json.loads(args.spec.read_text()))


def test_snapshot_failure_cannot_admit_completed_frames(tmp_path, monkeypatch):
    args = args_with_data(tmp_path)
    import offline_evaluation_contracts_v1 as snapshots

    def failed_replace(*values):
        raise OSError("controlled failure")

    monkeypatch.setattr(snapshots.os, "replace", failed_replace)
    with pytest.raises(OSError):
        persist_measurement(args, dict(status="PASS", frames=[dict(status="PASS")] * 144))
    assert not (tmp_path / "measurement_complete.json").exists()
    assert admission(None, 0, False, True)["status"] == "FAIL"


@pytest.mark.parametrize(
    "exitcode,timeout,reaped", [(1, False, True), (0, True, True), (0, False, False)]
)
def test_abnormal_exit_timeout_or_unreaped_never_admits(exitcode, timeout, reaped):
    capsule = dict(measurement_status="COMPLETE", report=dict(frames=[dict(status="PASS")] * 144))
    result = admission(capsule, exitcode, timeout, reaped, capsule_verified=True)
    assert result["measurement_complete"] is True and result["status"] == "FAIL"


def test_original_source_transform_only_inserts_snapshot_call():
    import ast

    original = (Path(__file__).parents[1] / "scripts/prospective_capture_v1.py").read_text()
    changed = amended_capture(original)

    class Remove(ast.NodeTransformer):
        def visit_Expr(self, node):
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "persist_measurement"
            ):
                return None
            return node

    assert ast.dump(Remove().visit(changed), include_attributes=False) == ast.dump(
        ast.parse(original), include_attributes=False
    )


def test_capsule_wrong_source_or_unverified_exit_zero_rejected(tmp_path):
    args = args_with_data(tmp_path)
    capsule = dict(measurement_status="COMPLETE", report=dict(frames=[dict(status="PASS")] * 144))
    assert admission(capsule, 0, False, True)["status"] == "FAIL"
    with pytest.raises(ValueError, match="identity"):
        validate_capsule(capsule, tmp_path, json.loads(args.spec.read_text()))


def test_explicit_post_shutdown_failure_never_admits_exit_zero():
    capsule = dict(measurement_status="COMPLETE", report=dict(frames=[dict(status="PASS")] * 144))
    assert admission(capsule, 0, False, True, True, "FAIL")["status"] == "FAIL"


def test_collection_population_tamper_rejected(tmp_path):
    args = args_with_data(tmp_path)
    persist_measurement(args, dict(status="PASS", mode="acquire", frames=args.frames))
    capsule = json.loads((tmp_path / "measurement_complete.json").read_text())
    capsule["report"]["frames"][-1]["tick"] = 0
    with pytest.raises(ValueError, match="population"):
        validate_capsule(capsule, tmp_path, json.loads(args.spec.read_text()))


def test_wrong_qualification_identity_rejected(tmp_path):
    from prospective_collection_contracts_v1 import verify_qualification

    (tmp_path / "ledger.json").write_text("{}")
    cfg = {
        "collection": {
            "qualification": {"out": str(tmp_path), "identity": {"ledger.json": "0" * 64}}
        }
    }
    with pytest.raises(ValueError, match="qualification identity"):
        verify_qualification(cfg)
