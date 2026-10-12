"""Preserve rejection facts without changing native dependency acceptance."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from native_dependency_closure_v2 import loaded_native_sources, verify_generated_remote
from offline_evaluation_contracts_v1 import atomic_snapshot


def verify_native_dependencies(cfg, modules=None, writer=atomic_snapshot):
    modules = sys.modules if modules is None else modules
    manifest = json.loads(Path(cfg["native_dependency_manifest"]).read_text())
    expected = {x["path"]: x["sha256"] for x in manifest["files"]}
    records = loaded_native_sources(modules)
    for row in records:
        wanted = expected.get(row["source"])
        if wanted == row["sha256"]:
            continue
        try:
            row["generated_authentication"] = verify_generated_remote(row, manifest, modules)
        except BaseException as exc:
            rejection = dict(
                status="REJECTED",
                module=row["module"],
                resolved_origin=row["source"],
                actual_sha256=row["sha256"],
                manifest_expected_sha256=wanted,
                category="UNLISTED_ORIGIN" if wanted is None else "FILE_HASH_MISMATCH",
                authentication_error_type=type(exc).__name__,
                generated_identity_authenticated=False,
                generator_export_identity="UNKNOWN",
            )
            target = Path(cfg["diagnostic_rejection_path"])
            if target.exists():
                previous = json.loads(target.read_text())
                if previous.get("status") != "REJECTED":
                    raise ValueError("invalid existing first-rejection evidence") from exc
            else:
                writer(target, rejection)
            raise
    return records


def run_observed(cmd, env, cwd, log, timeout, outcome, popen=subprocess.Popen, killpg=os.killpg):
    outcome.update(child_exit_code=None, timeout=False, child_reaped=None)
    child = popen(
        cmd, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    )
    try:
        try:
            outcome["child_exit_code"] = child.wait(timeout=timeout)
            outcome["child_reaped"] = True
            return outcome["child_exit_code"]
        except subprocess.TimeoutExpired:
            outcome["timeout"] = True
            raise
    finally:
        if child.poll() is None:
            try:
                killpg(child.pid, signal.SIGKILL)
                outcome["kill_requested"] = True
            except ProcessLookupError:
                outcome["kill_requested"] = False
            except BaseException as exc:
                outcome["cleanup_signal_error_type"] = type(exc).__name__
            try:
                outcome["child_exit_code"] = child.wait(timeout=5)
                outcome["child_reaped"] = True
            except BaseException:
                outcome["child_reaped"] = False
                raise
        elif not outcome["child_reaped"]:
            outcome["child_exit_code"] = child.wait(timeout=0)
            outcome["child_reaped"] = True


def validate_rejection_path(cfg, out):
    if Path(cfg["diagnostic_rejection_path"]).resolve() != out.resolve() / "rejection.json":
        raise ValueError("rejection evidence must belong to fresh attempt output")
