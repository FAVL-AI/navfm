"""Collector selector wiring: does Arm A still behave as Arm A?

The seam was proved behaviour-neutral once already, but that proof stopped at
``PurePursuit``. The collector now resolves a declared selector and passes it in,
which is new code on the path every arm takes, so the same question has to be
asked again of the wired construction: does routing Arm A through a declaration
and a registry change what Arm A does?

The reference is the same as before -- the pre-seam tracker read out of git --
so the chain is end to end rather than each link vouching for the next.

Also records why the first Arm-A authorisation never became an execution. That
is not an Arm-A failure: Arm A never started, and a record that blurred the two
would leave a reader believing the control arm had been attempted and gone
badly.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
import json
import pathlib
import pickle
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.control import M3PRO_LIMITS, DemonstratorMode, PurePursuit, resample_path  # noqa: E402
from navfm.evidence import emit_evidence  # noqa: E402
from navfm.isaac.collect import CollectConfig  # noqa: E402
from navfm.target_selection import (  # noqa: E402
    ArcLengthInterpolatedTargetSelector,
    LegacyVertexTargetSelector,
    SelectorResolutionRefused,
    resolve_target_selector,
)
from navfm.tracker_equivalence import (  # noqa: E402
    COMMAND_CHANNELS,
    TARGET_CHANNELS,
    compare_sequences,
    run_command_sequence,
    run_target_sequence,
)

PRE_SEAM_COMMIT = "437ebfc63f828fb1200df1f01df56bc339209349"
CONTROL_REL = "src/navfm/control.py"
PREREG = REPO / "gates/BO10/terminal_approach_intervention_v1_20260911.json"
RUN_TRAJ = REPO / "runs/bo10/hospital_bo10_run_00001/traj_data.pkl"
GAP_OUT = REPO / "gates/BO10/execution_readiness_gap_v1_20260912.json"
OUT = REPO / "gates/BO10/collector_wiring_regression_20260912.json"

CONFIG: dict[str, Any] = {
    "lookahead": 0.45, "goal_tol": 0.20, "limits": M3PRO_LIMITS,
    "mode": DemonstratorMode.NONHOLONOMIC, "cruise_v": 0.35,
}


def sha256_file(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def load_pre_seam() -> tuple[Any, str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{PRE_SEAM_COMMIT}:{CONTROL_REL}"],
        capture_output=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"cannot read {CONTROL_REL} at {PRE_SEAM_COMMIT[:12]}")
    digest = hashlib.sha256(proc.stdout).hexdigest()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="preseam_")) / "control_pre_seam.py"
    tmp.write_bytes(proc.stdout)
    spec = importlib.util.spec_from_file_location("control_pre_seam_wiring", tmp)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, digest


def wired_tracker(path: np.ndarray, declaration: str | None) -> PurePursuit:
    """Construct the tracker exactly as the wired collector now does."""
    config = CollectConfig(
        max_steps=1200, cruise_v=CONFIG["cruise_v"], lookahead_m=CONFIG["lookahead"],
        goal_tol_m=CONFIG["goal_tol"], seed=0, target_selector=declaration)
    selector = resolve_target_selector(config.target_selector)
    return PurePursuit(
        path.copy(), lookahead=config.lookahead_m, goal_tol=config.goal_tol_m,
        limits=M3PRO_LIMITS, mode=DemonstratorMode(config.demonstrator),
        cruise_v=config.cruise_v, target_selector=selector)


def wiring_controls() -> dict[str, Any]:
    """Does a declaration reach the selector it names, and refuse when it does not?"""
    results: dict[str, Any] = {}

    arm_a = wired_tracker(np.array([[0.0, 0.0], [1.0, 0.0]]), "PATH_VERTEX")
    results["A_arm_a_reaches_legacy"] = isinstance(
        arm_a._selector, LegacyVertexTargetSelector)

    arm_b = wired_tracker(np.array([[0.0, 0.0], [1.0, 0.0]]), "ARC_LENGTH_INTERPOLATED")
    results["B_arm_b_reaches_interpolated"] = isinstance(
        arm_b._selector, ArcLengthInterpolatedTargetSelector)

    # Absence is the frozen control behaviour, never the treatment. The refusal
    # for a MISSING arm declaration lives in the runner, where an arm identity
    # exists to check it against; here what matters is that absence can never
    # silently become Arm B.
    absent = wired_tracker(np.array([[0.0, 0.0], [1.0, 0.0]]), None)
    results["C_absent_declaration_is_never_treatment"] = not isinstance(
        absent._selector, ArcLengthInterpolatedTargetSelector)
    results["C_absent_declaration_is_legacy"] = isinstance(
        absent._selector, LegacyVertexTargetSelector)

    try:
        resolve_target_selector("SOMETHING_ELSE")
        results["D_unknown_declaration_refused"] = False
    except SelectorResolutionRefused as exc:
        results["D_unknown_declaration_refused"] = True
        results["D_reason"] = str(exc)[:140]

    results["F_override_surface"] = ["target"]
    results["F_selector_surfaces"] = {
        name: sorted(
            n for n in dir(cls)
            if not n.startswith("_") and callable(getattr(cls, n)))
        for name, cls in (("legacy", LegacyVertexTargetSelector),
                          ("treatment", ArcLengthInterpolatedTargetSelector))
    }
    results["F_surface_is_one_method"] = all(
        surface == ["select_target"] for surface in results["F_selector_surfaces"].values())
    results["PASS"] = bool(
        results["A_arm_a_reaches_legacy"] and results["B_arm_b_reaches_interpolated"]
        and results["C_absent_declaration_is_never_treatment"]
        and results["C_absent_declaration_is_legacy"]
        and results["D_unknown_declaration_refused"]
        and results["F_surface_is_one_method"])
    return results


def regression(pre_seam: Any, path: np.ndarray, poses: np.ndarray) -> dict[str, Any]:
    """PRE_SEAM == post-seam default == explicit legacy == WIRED legacy."""
    out: dict[str, Any] = {}
    for pass_name, runner, channels in (
        ("command", run_command_sequence, COMMAND_CHANNELS),
        ("target", run_target_sequence, TARGET_CHANNELS),
    ):
        trackers = {
            "PRE_SEAM": pre_seam.PurePursuit(
                path.copy(), lookahead=CONFIG["lookahead"], goal_tol=CONFIG["goal_tol"],
                limits=pre_seam.M3PRO_LIMITS,
                mode=pre_seam.DemonstratorMode.NONHOLONOMIC,
                cruise_v=CONFIG["cruise_v"]),
            "LEGACY_DIRECT": PurePursuit(path.copy(), **CONFIG),
            "LEGACY_INJECTED": PurePursuit(
                path.copy(), **CONFIG, target_selector=LegacyVertexTargetSelector()),
            "WIRED_ARM_A": wired_tracker(path, "PATH_VERTEX"),
            "WIRED_DEFAULT": wired_tracker(path, None),
        }
        sequences = {name: runner(t, poses) for name, t in trackers.items()}
        for other in ("LEGACY_DIRECT", "LEGACY_INJECTED", "WIRED_ARM_A", "WIRED_DEFAULT"):
            out[f"{pass_name}:PRE_SEAM_vs_{other}"] = compare_sequences(
                sequences["PRE_SEAM"], sequences[other],
                left_label="PRE_SEAM", right_label=other, channels=channels)
    return out


def main() -> int:
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=False).stdout.strip()
    stamp = _dt.datetime.now(_dt.UTC).isoformat()

    gap = {
        "check": "EXECUTION_READINESS_GAP_V1",
        "artifact_semantics": "GOVERNANCE_RECORD_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "classification": "EXECUTION_READINESS_GAP_V1",
        "what_happened": (
            "the first Arm-A execution authorisation was refused at the pre-Isaac "
            "gates and never became an execution"
        ),
        "THIS_IS_NOT_AN_ARM_A_FAILURE": (
            "Arm A never started. Recording this as a failed control arm would leave "
            "a reader believing the experiment was attempted and went badly"
        ),
        "blockers": {
            "A_selector_not_wired_through_the_collector": (
                "selector injection existed in the controller layer but the collector "
                "constructed PurePursuit with no target_selector, so no production "
                "path could request an arm"),
            "B_no_manifest_driven_runner": (
                "no runner existed that could read EXECUTION_MANIFEST_V1 and produce "
                "the exact output artefacts it declared"),
            "C_stale_preflight_payload": (
                "the committed preflight recorded the pre-seam controller hash in "
                "three canonical fields, so its scientific payload described a tree "
                "that had moved"),
        },
        "observed_at": {
            "manifest": "runs/bo10/intervention/execution_manifest.json",
            "manifest_bound_head": "effcce1ee22e8480a4c43e656e7355e628cadcc5",
        },
        "explicitly_did_not_happen": [
            "no Isaac process was launched",
            "no Hospital scene was loaded",
            "no collector was executed",
            "no PRE_ARM_A was created",
            "no scientific arm result was produced",
        ],
        "methodological_correction": (
            "a valid manifest must establish declaration integrity AND execution-path "
            "existence. V1 established the first and not the second, so it was correct "
            "on paper and unrunnable at the same time"
        ),
        "manifest_v1_status": (
            "historically frozen and NOT overwritten. Its source HEAD was correctly "
            "pinned; its executability assurance was incomplete, and that limitation "
            "is recorded here rather than repaired in place"
        ),
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }
    gap_sha = emit_evidence(GAP_OUT, gap, required_keys=(
        "classification", "blockers", "THIS_IS_NOT_AN_ARM_A_FAILURE", "EXECUTION_STATUS"))

    print("=" * 68)
    print("COLLECTOR SELECTOR WIRING -- Arm A regression")
    print("=" * 68)
    print(f"HEAD                {head[:12]}")
    print(f"gap record          {GAP_OUT.relative_to(REPO)}  {gap_sha[:16]}...")
    print()

    controls = wiring_controls()
    for key in sorted(k for k in controls if k[0].isupper() and k != "PASS"):
        if isinstance(controls[key], bool):
            print(f"  {key:44s} {controls[key]}")
    print(f"wiring controls     {'PASS' if controls['PASS'] else 'FAIL'}")
    print()

    pre_seam, pre_seam_sha = load_pre_seam()
    prereg = json.loads(PREREG.read_text())
    route = np.array(
        prereg["secondary_outcome_cross_track_error"]["frozen_route_polyline"]["coordinates"],
        dtype=np.float64)
    with RUN_TRAJ.open("rb") as handle:
        traj = pickle.load(handle)
    positions = np.asarray(traj["position"], dtype=np.float64)
    poses = np.column_stack(
        [positions[:, 0], positions[:, 1], np.asarray(traj["yaw"], dtype=np.float64)])

    traces: dict[str, Any] = {}
    ok = True
    for name, trace_path in (("frozen_route_polyline", route),
                             ("frozen_route_resampled_0m25", resample_path(route, 0.25))):
        comparisons = regression(pre_seam, trace_path, poses)
        totals: dict[str, int] = {}
        for result in comparisons.values():
            for channel, count in result.get("mismatches_by_channel", {}).items():
                totals[channel] = totals.get(channel, 0) + int(count)
        passed = all(v.get("EQUIVALENCE") == "PASS" for v in comparisons.values())
        ok &= passed
        traces[name] = {
            "steps_evaluated": int(poses.shape[0]),
            "verdict": "PASS" if passed else "FAIL",
            "mismatches_by_channel": totals,
            "comparisons": {k: v["EQUIVALENCE"] for k, v in comparisons.items()},
            "max_numerical_difference": max(
                float(v.get("max_numerical_difference", 0.0)) for v in comparisons.values()),
        }
        print(f"  {name:36s} {traces[name]['verdict']}  steps={poses.shape[0]}  "
              f"mismatches={sum(totals.values())}")
    print(f"arm-A wiring regression  {'PASS' if ok else 'FAIL'}")

    verdict = "PASS" if (ok and controls["PASS"]) else "FAIL"
    record = {
        "check": "ARM_A_COLLECTOR_WIRING_REGRESSION",
        "artifact_semantics": "OFFLINE_REGRESSION_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "repository_head": head,
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "what_is_new_since_the_seam_proof": (
            "the collector now resolves a declared selector and passes it into the "
            "tracker. That is new code on the path every arm takes, so Arm A's "
            "behaviour is re-established through the wired construction rather than "
            "inherited from the earlier seam proof"
        ),
        "pre_seam_reference": {"commit": PRE_SEAM_COMMIT, "path": CONTROL_REL,
                               "sha256": pre_seam_sha},
        "implementations_compared": [
            "PRE_SEAM (tracker read from git before the seam existed)",
            "LEGACY_DIRECT (post-seam default)",
            "LEGACY_INJECTED (post-seam explicit selector)",
            "WIRED_ARM_A (collector declaration 'PATH_VERTEX')",
            "WIRED_DEFAULT (collector declaration absent)",
        ],
        "selector_wiring_controls": controls,
        "regression": {"verdict": "PASS" if ok else "FAIL", "traces": traces},
        "collector_identity": {
            "path": "src/navfm/isaac/collect.py",
            "sha256": sha256_file(REPO / "src/navfm/isaac/collect.py")},
        "selector_module_identity": {
            "path": "src/navfm/target_selection.py",
            "sha256": sha256_file(REPO / "src/navfm/target_selection.py")},
        "controller_identity": {
            "path": CONTROL_REL, "sha256": sha256_file(REPO / CONTROL_REL),
            "unchanged_by_this_tranche": sha256_file(REPO / CONTROL_REL) == (
                "679cd60f86ea2b84e4f8fe93cd464a8484bee69204f6716a62f3adb05d04abc6")},
        "claim_boundary": (
            "this extends the evidence chain; it does not replace the earlier seam "
            "proof. It establishes that collector propagation left Arm A unchanged "
            "over the frozen regression domain, and says nothing about runtime "
            "behaviour in Isaac"
        ),
        "ARM_A_COLLECTOR_WIRING_REGRESSION": verdict,
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }
    sha = emit_evidence(OUT, record, required_keys=(
        "ARM_A_COLLECTOR_WIRING_REGRESSION", "regression", "selector_wiring_controls",
        "EXECUTION_STATUS"))
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha}")
    print(f"VERDICT             {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
