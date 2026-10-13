"""Finalization-only source amendment; measurement and process admission stay separate."""

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


def persist_measurement(args, report):
    if (
        report["status"] != "PASS"
        or len(report["frames"]) != 19
        or any(x["status"] != "PASS" for x in report["frames"])
    ):
        raise ValueError("measurement population incomplete")
    artifacts = {
        str(p.relative_to(args.out)): sha(p) for p in (args.out / "data").rglob("*") if p.is_file()
    }
    artifacts["specification.json"] = sha(args.spec)
    capsule = dict(
        schema="prospective_measurement_complete_v2",
        measurement_status="COMPLETE",
        expected_frames=19,
        report=report,
        original_capture_sha256=ORIGINAL_CAPTURE_SHA,
        measurement_artifacts=artifacts,
    )
    atomic_snapshot(args.out / "measurement_complete.json", capsule)


def validate_capsule(capsule, out):
    if (
        not capsule
        or capsule.get("schema") != "prospective_measurement_complete_v2"
        or capsule.get("original_capture_sha256") != ORIGINAL_CAPTURE_SHA
        or capsule.get("expected_frames") != 19
        or capsule.get("measurement_status") != "COMPLETE"
        or capsule.get("report", {}).get("status") != "PASS"
        or capsule["report"].get("mode") != "qualify"
    ):
        raise ValueError("measurement capsule source/schema identity")
    expected = []
    for route, count in [
        ("technical_fixture_layout0_route0", 16),
        ("technical_fixture_layout0_route1", 1),
        ("technical_fixture_layout1_route0", 1),
        ("technical_fixture_layout1_route1", 1),
    ]:
        expected.extend((route, tick) for tick in range(count))
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
        and len(capsule.get("report", {}).get("frames", [])) == 19
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
