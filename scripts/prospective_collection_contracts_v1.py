"""Collection-only continuation; acquisition criteria are unchanged."""

import ast

from development_qualification_contracts_v1 import sha
from offline_evaluation_contracts_v1 import atomic_snapshot

ORIGINAL_CAPTURE_SHA = "c94f7e0ca1fc735e3b1d6b4edeae5e212a4139ffa26dd86756b95311d527208d"


def amended_capture(source):
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for index, statement in enumerate(node.body):
                if (
                    isinstance(statement, ast.Assign)
                    and len(statement.targets) == 1
                    and ast.unparse(statement.targets[0]) == "report['status']"
                    and isinstance(statement.value, ast.Constant)
                    and statement.value.value == "PASS"
                ):
                    found.append((node, index))
    if len(found) != 1:
        raise ValueError("one terminal PASS assignment in app context required")
    node, index = found[0]
    node.body.insert(index + 1, ast.parse("persist_measurement(args, report)").body[0])
    return ast.fix_missing_locations(tree)


def expected_frames(spec):
    routes = [r["id"] for layout in spec["layouts"] for r in layout["routes"]]
    if len(routes) != 4 or len(set(routes)) != 4:
        raise ValueError("sealed route population")
    return [(route, tick) for route in routes for tick in range(36)]


def persist_measurement(args, report):
    if (
        report["status"] != "PASS"
        or len(report["frames"]) != 144
        or any(x["status"] != "PASS" for x in report["frames"])
    ):
        raise ValueError("measurement population incomplete")
    artifacts = {
        str(p.relative_to(args.out)): sha(p) for p in (args.out / "data").rglob("*") if p.is_file()
    }
    artifacts["specification.json"] = sha(args.spec)
    capsule = dict(
        schema="prospective_collection_complete_v1",
        measurement_status="COMPLETE",
        expected_frames=144,
        report=report,
        original_capture_sha256=ORIGINAL_CAPTURE_SHA,
        measurement_artifacts=artifacts,
    )
    atomic_snapshot(args.out / "measurement_complete.json", capsule)


def validate_capsule(capsule, out, spec):
    if (
        not capsule
        or capsule.get("schema") != "prospective_collection_complete_v1"
        or capsule.get("original_capture_sha256") != ORIGINAL_CAPTURE_SHA
        or capsule.get("expected_frames") != 144
        or capsule.get("measurement_status") != "COMPLETE"
        or capsule.get("report", {}).get("status") != "PASS"
        or capsule["report"].get("mode") != "acquire"
    ):
        raise ValueError("measurement capsule source/schema identity")
    expected = expected_frames(spec)
    frames = capsule["report"]["frames"]
    if [(f.get("route"), f.get("tick")) for f in frames] != expected or any(
        f.get("status") != "PASS" for f in frames
    ):
        raise ValueError("measurement frame population identity")
    names = {f"data/{route}/{tick}.jpg" for route, tick in expected}
    names.update(f"data/{route}/traj_data.pkl" for route, _ in expected)
    names.add("specification.json")
    if set(capsule["measurement_artifacts"]) != names:
        raise ValueError("measurement artifact population identity")
    for name, digest in capsule["measurement_artifacts"].items():
        if sha(out / name) != digest:
            raise ValueError("measurement artifact drift")
    for frame in frames:
        name = f"data/{frame['route']}/{frame['tick']}.jpg"
        if frame["sha256"] != capsule["measurement_artifacts"][name]:
            raise ValueError("measurement frame/image hash mismatch")


def admission(
    capsule, exitcode, timeout, child_reaped, capsule_verified=False, post_shutdown_status=None
):
    measured = bool(
        capsule
        and capsule.get("measurement_status") == "COMPLETE"
        and len(capsule.get("report", {}).get("frames", [])) == 144
        and all(f.get("status") == "PASS" for f in capsule["report"]["frames"])
    )
    return dict(
        measurement_complete=measured,
        measurement_artifacts_verified=capsule_verified,
        child_exit_code=exitcode,
        timeout=timeout,
        child_reaped=child_reaped,
        sdk_cleanup_completion="NOT_INDEPENDENTLY_OBSERVED",
        status="PASS"
        if measured
        and capsule_verified
        and exitcode == 0
        and not timeout
        and child_reaped
        and post_shutdown_status != "FAIL"
        else "FAIL",
    )


def verify_qualification(cfg):
    import json
    from pathlib import Path

    from prospective_finalization_contracts_v2 import validate_capsule as verify_known

    q = cfg["collection"]["qualification"]
    root = Path(q["out"])
    for name, digest in q["identity"].items():
        if sha(root / name) != digest:
            raise ValueError("qualification identity drift")
    ledger = json.loads((root / "ledger.json").read_text())
    if (
        ledger["freeze"] != "3954fb8daf1de1d2a991a7df20a1effe93bdcba1"
        or ledger["status"] != "PASS"
        or ledger["child_exit_code"] != 0
        or ledger["timeout"]
        or not ledger["child_reaped"]
    ):
        raise ValueError("qualification admission identity")
    verify_known(json.loads((root / "measurement_complete.json").read_text()), root)
    for name, digest in ledger["artifacts"].items():
        if sha(root / name) != digest:
            raise ValueError("qualification artifact drift")
