"""Bank ARM_A_ATTEMPT_002 as an append-only execution-attempt record.

Attempt 002 ran under V8 and EXECUTION_MANIFEST_V5 with the repaired
adapter/collector seam. It entered real execution mode, wrote and validated its
own PRE capture at its own attempt path, launched Isaac, constructed the real
Collector, and propagated the adapter's live IsaacApp into it -- the defect that
ended Attempt 001 did not recur.

It then stopped at robot instantiation, because the robot USD the apparatus
needs does not exist and the converter module referenced by the error message
has never been written.

This is an infrastructure failure before the episode, not a navigation outcome.
No episode started, no scientific command was sent, and the scientific Arm-A
sample count is unchanged at zero. The record says so in the fields a later
reader would otherwise mine for a result.

It records only what the run evidenced. It does not resolve which robot
description is authoritative, how a scientifically admissible USD should be
produced, or where that asset should live. Each of those changes the physical
apparatus the experiment represents, so each is carried here as
DECISION_PENDING and settled elsewhere.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402

OUT = REPO / "gates/BO10/arm_a_attempt_002_20260917.json"

ATTEMPT_001_REL = "gates/BO10/arm_a_attempt_001_20260917.json"
ATTEMPT_001_PRE_REL = "runs/bo10/intervention/arm_a/pre_capture.json"
ATTEMPT_002_PRE_REL = "runs/bo10/intervention/arm_a_attempt_002/pre_capture.json"
MANIFEST_REL = "runs/bo10/intervention/execution_manifest_v5.json"
V8_REL = "gates/BO10/environment_identity_v8_20260917.json"

#: The commit Attempt 002 executed from, and the state its PRE capture bound.
ATTEMPT_002_HEAD = "4ba61f8999caa290a3fca5bf38e9033518c97da2"

#: Tracked sources cited by this record. Their identities must be verifiable at
#: the head the record names, under the rule that has governed every gate
#: artefact since the provenance defect was found.
CITED_SOURCES = (
    "src/navfm/isaac/robot.py",
    "src/navfm/isaac/collect.py",
    "src/navfm/arm_lifecycle.py",
)

#: Verbatim from the structured result the run returned. Not paraphrased: the
#: reason text is the diagnostic a later reader has, and shortening it would
#: quietly improve the evidence.
OBSERVED_REFUSAL = {
    "stage": "SCENE_READY",
    "exception_type": "ValueError",
    "reason": (
        "unhandled ValueError: RobotConfig.usd_path is unset. Convert "
        "yahboomcar_description to USD first:\n  python -m navfm.isaac.urdf_import "
        "--urdf .../yahboomcar.urdf --out assets/m3pro.usd --holonomic"),
    "escaped_exception": True,
    "raised_at": "src/navfm/isaac/robot.py:150 (SimRobot.spawn, guard at :148)",
}

STAGES_ENTERED = (
    "MANIFEST_VALIDATED", "PRE_ENV_CAPTURED", "RUNTIME_INITIALISING",
    "COLLECTOR_READY", "SCENE_READY",
)


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def sha256_file(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _blob_sha_at(commit: str, rel: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{rel}"],
                          capture_output=True, check=False)
    return hashlib.sha256(proc.stdout).hexdigest() if proc.returncode == 0 else None


def head_content_coherence(head: str) -> dict[str, Any]:
    rows = []
    for rel in CITED_SOURCES:
        recorded = sha256_file(REPO / rel)
        at_head = _blob_sha_at(head, rel)
        rows.append({"path": rel, "recorded_sha256": recorded,
                     "sha256_at_head": at_head, "matches": recorded == at_head})
    return {
        "EVIDENCE_HEAD_CONTENT_COHERENCE":
            "PASS" if all(r["matches"] for r in rows) else "FAIL",
        "repository_head": head,
        "sources": rows,
    }


def robot_asset_state() -> dict[str, Any]:
    """What the apparatus actually offers, measured rather than remembered."""
    from navfm.isaac.robot import M3PRO

    expected = REPO / "assets/m3pro.usd"
    converter = REPO / "src/navfm/isaac/urdf_import.py"
    return {
        "m3pro_usd_path_config": M3PRO.usd_path,
        "expected_asset_path": "assets/m3pro.usd",
        "expected_asset_present": expected.is_file(),
        "referenced_converter_module": "src/navfm/isaac/urdf_import.py",
        "referenced_converter_present": converter.is_file(),
        "declared_at": "src/navfm/isaac/robot.py:100",
        "enforced_at": "src/navfm/isaac/robot.py:148-151",
        "ROBOT_ASSET_ADMISSION": "FAIL",
    }


def build_record(head: str, stamp: str) -> dict[str, Any]:
    pre_002 = REPO / ATTEMPT_002_PRE_REL
    capture = json.loads(pre_002.read_text()) if pre_002.is_file() else {}
    attempt_001 = REPO / ATTEMPT_001_REL
    prior = json.loads(attempt_001.read_text()) if attempt_001.is_file() else {}

    return {
        "check": "ARM_A_ATTEMPT_002",
        "artifact_semantics": "EXECUTION_ATTEMPT_RECORD_NO_SCIENTIFIC_RESULT",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "repository_head": head,
        "intervention_id": "TERMINAL_APPROACH_INTERVENTION_V1",
        "arm_id": "ARM_A_CONTROL",
        "attempt_id": "002",
        "CLASSIFICATION": "INFRASTRUCTURE_FAILURE_BEFORE_EPISODE",
        "executed_at_head": ATTEMPT_002_HEAD,
        "executed_under_contract": {
            "version": "V8", "path": V8_REL, "sha256": sha256_file(REPO / V8_REL)},
        "executed_under_manifest": {
            "version": "EXECUTION_MANIFEST_V5", "path": MANIFEST_REL,
            "sha256": sha256_file(REPO / MANIFEST_REL)},

        "ESTABLISHED": {
            "runner_entered_real_execution_mode": True,
            "execution_mode": "REAL",
            "attempt_provenance_path_worked": True,
            "pre_capture_created_and_validated":
                capture.get("CAPTURE_VALIDATION") == "PASS",
            "attempt_001_pre_unchanged": True,
            "isaac_process_launched": True,
            "isaac_runtime_available": True,
            "real_collector_constructed": True,
            "isaac_app_propagated_to_collector": True,
            "same_object_app_binding": True,
            "robot_instantiation_path_reached": True,
            "selector_resolved": "PATH_VERTEX",
            "detail": (
                "the adapter/collector live-application seam repaired in V8 held "
                "under real execution: the collector reported isaac_app_bound=true "
                "with the production IsaacRuntimeAdapter and the production "
                "Collector. The defect that ended Attempt 001 did not recur"),
        },

        "NOT_ESTABLISHED": {
            "hospital_scene_loaded": False,
            "first_render_succeeded": False,
            "robot_spawned": False,
            "camera_initialised": False,
            "collector_episode_ran": False,
            "trajectory_produced": False,
            "detail": (
                "Isaac reported a stage opened, but the adapter's "
                "HOSPITAL_SCENE_LOADED flag was never set because open_scene raised "
                "before returning. Whether the remote Hospital content fully "
                "resolved is not established and is not claimed"),
        },

        "stages_entered": list(STAGES_ENTERED),
        "EARLIEST_FAILING_STAGE": "ROBOT_INSTANTIATION_PRECONDITION",
        "why_the_stage_label_reads_scene_ready": (
            "Collector.open_scene performs stage-open, robot spawn and camera "
            "attach inside the single SCENE_READY plan step, so the recorded stage "
            "is coarser than the failure. The sub-step that failed is the second"),
        "observed_refusal": OBSERVED_REFUSAL,

        "STRUCTURED_REFUSAL": False,
        "claim_boundary_on_the_diagnostic": (
            "the message was actionable -- it named the missing asset and the "
            "command that would produce it -- but the boundary raised a bare "
            "ValueError that propagated to the outer catch-all. Good diagnostic "
            "text is not a structured refusal, and escaped_exception=true is "
            "recorded rather than smoothed. Repairing that boundary belongs to a "
            "future tranche"),

        "robot_asset_state": robot_asset_state(),

        "ATTEMPT_002_PRE_CAPTURE": {
            "path": ATTEMPT_002_PRE_REL,
            "sha256": sha256_file(pre_002),
            "label": capture.get("label"),
            "attempt": capture.get("attempt"),
            "timestamp_utc": capture.get("timestamp_utc"),
            "capture_validation": capture.get("CAPTURE_VALIDATION"),
            "critical_digest": capture.get("critical_digest"),
            "is_production_label": capture.get("is_production_label"),
            "PRESERVED": True,
            "never_reused": (
                "this capture belongs to attempt 002. Attempt 003, if authorised, "
                "receives its own identity and its own capture"),
        },
        "ATTEMPT_001": {
            "record": {"path": ATTEMPT_001_REL, "sha256": sha256_file(attempt_001)},
            "pre_capture": {"path": ATTEMPT_001_PRE_REL,
                            "sha256": sha256_file(REPO / ATTEMPT_001_PRE_REL)},
            "classification": prior.get("CLASSIFICATION"),
            "PRESERVED_UNCHANGED": True,
            "separate_attempt": True,
        },

        "EPISODE_STARTED": False,
        "SCIENTIFIC_COMMANDS_SENT": 0,
        "ARM_A_SCIENTIFIC_RESULT": "NOT_OBSERVED",
        "NOT_A_NAVIGATION_OUTCOME": (
            "no episode ran and no scientific command was sent, so this attempt "
            "has no success, no failure, no SR, no OSR, no goal distance and no "
            "cross-track. Recording success=false would assert a completed trial "
            "that never began, and recording SR=0 would put a non-observation into "
            "a rate"),
        "excluded_from": [
            "n", "SR", "OSR", "goal distance", "cross-track", "treatment comparison"],
        "SCIENTIFIC_ARM_A_N": 0,
        "attempt_history": [
            {"attempt_id": "001",
             "classification": "INFRASTRUCTURE_FAILURE_BEFORE_EPISODE"},
            {"attempt_id": "002",
             "classification": "INFRASTRUCTURE_FAILURE_BEFORE_EPISODE"},
        ],
        "treatment_comparison_exists": False,

        "PENDING_APPARATUS_DECISIONS": {
            "ROBOT_DESCRIPTION_AUTHORITY": {
                "status": "DECISION_PENDING",
                "candidates_observed": [
                    "the navfm twin description",
                    "the upstream description it was derived from",
                    "vendor yahboomcar_description, acquired under an explicit "
                    "provenance decision",
                ],
                "note": ("recorded as observed candidates. This record expresses no "
                         "preference among them"),
            },
            "URDF_TO_USD_CONVERSION_STRATEGY": {"status": "DECISION_PENDING"},
            "SCIENTIFIC_ASSET_STORAGE": {"status": "DECISION_PENDING"},
        },
        "UNRESOLVED_SOURCE_CANDIDATE_DIFFERENCES": {
            "wheel_radius_m": {"candidate_values": [0.048, 0.040],
                               "physically_measured": False},
            "camera_apparatus": {
                "candidate_configurations": [
                    "body-mounted, lower", "elevated forward top-arm"],
                "physically_measured": False},
            "status": "UNRESOLVED_CONTEXT",
            "note": ("neither candidate is declared authoritative here, and neither "
                     "is called physically correct. These values are not physically "
                     "measured"),
        },
        "source_closure_observation": {
            "external_mesh_references": 0,
            "note": ("observed for the candidate under inspection. Useful later; it "
                     "does not resolve source authority"),
        },

        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "attempt_003_started": False,
        "attempt_003_requires": [
            "the three apparatus decisions",
            "a validated robot asset",
            "a new authoritative freeze",
            "explicit human authorisation",
        ],

        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_EXECUTION": "NOT_ESTABLISHED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }


def main() -> int:
    head = _git("rev-parse", "HEAD")
    stamp = _dt.datetime.now(_dt.UTC).isoformat()

    record = build_record(head, stamp)
    coherence = head_content_coherence(head)
    record["EVIDENCE_HEAD_CONTENT_COHERENCE"] = coherence

    sha = emit_evidence(OUT, record, required_keys=(
        "CLASSIFICATION", "EARLIEST_FAILING_STAGE", "observed_refusal",
        "ATTEMPT_002_PRE_CAPTURE", "ATTEMPT_001", "EPISODE_STARTED",
        "ARM_A_SCIENTIFIC_RESULT", "SCIENTIFIC_ARM_A_N",
        "PENDING_APPARATUS_DECISIONS", "EXECUTION_STATUS"))

    print("=" * 70)
    print("ARM_A_ATTEMPT_002 -- EXECUTION ATTEMPT RECORD")
    print("=" * 70)
    print(f"HEAD                  {head[:12]}")
    print(f"classification        {record['CLASSIFICATION']}")
    print(f"earliest failing stage {record['EARLIEST_FAILING_STAGE']}")
    print(f"exception             {OBSERVED_REFUSAL['exception_type']}  "
          f"escaped={OBSERVED_REFUSAL['escaped_exception']}")
    print(f"structured refusal    {record['STRUCTURED_REFUSAL']}")
    print()
    print(f"episode started       {record['EPISODE_STARTED']}")
    print(f"scientific commands   {record['SCIENTIFIC_COMMANDS_SENT']}")
    print(f"scientific result     {record['ARM_A_SCIENTIFIC_RESULT']}")
    print(f"scientific Arm-A n    {record['SCIENTIFIC_ARM_A_N']}")
    print()
    established = record["ESTABLISHED"]
    print(f"isaac launched        {established['isaac_process_launched']}")
    print(f"collector constructed {established['real_collector_constructed']}")
    print(f"app propagated        {established['isaac_app_propagated_to_collector']}")
    print(f"PRE 002 validated     {established['pre_capture_created_and_validated']}")
    print(f"attempt 001 unchanged {record['ATTEMPT_001']['PRESERVED_UNCHANGED']}")
    print()
    asset = record["robot_asset_state"]
    print(f"M3PRO.usd_path        {asset['m3pro_usd_path_config']}")
    print(f"assets/m3pro.usd      present={asset['expected_asset_present']}")
    print(f"urdf_import module    present={asset['referenced_converter_present']}")
    print()
    for name, decision in record["PENDING_APPARATUS_DECISIONS"].items():
        print(f"  {name:34s} {decision['status']}")
    print()
    print(f"EVIDENCE_HEAD_CONTENT_COHERENCE  "
          f"{coherence['EVIDENCE_HEAD_CONTENT_COHERENCE']}")
    print(f"artefact              {OUT.relative_to(REPO)}")
    print(f"sha256                {sha}")
    print("ARM_A_ATTEMPT_003     NOT_AUTHORISED")
    print("ARM_B_EXECUTION       NOT_STARTED")
    return 0 if coherence["EVIDENCE_HEAD_CONTENT_COHERENCE"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
