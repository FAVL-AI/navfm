"""Declare the digital-twin programme, and bind the prototype that precedes it.

The M3 Pro must exist as a standalone reproducible twin in Isaac Sim / Isaac Lab
that can run GNM, ViNT and NoMaD through one interface. That is a mandatory
downstream acceptance gate, not an optional extension of BO-10.

It is also not greenfield. A prototype from 2026-08-13 already loads the robot,
passes all three model loaders and runs a closed loop. Every artefact of it is
marked NOT_ADMITTED and ENGINEERING_EVIDENCE_ONLY, and every one is bound to
apparatus that has since been superseded: the USD with the F-TWIN-1 squared box
colliders, a chassis-mast camera model that has been withdrawn, and a
provisional wheel radius.

So the programme's first job is re-qualification against corrected apparatus,
not construction from nothing. This record binds the prior artefacts by hash so
that what is being superseded is a measured set of files rather than a memory.

Declares scope. Implements nothing.
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

OUT = REPO / "gates/digital_twin/digital_twin_programme_20260917.json"

PRIOR = (
    "gates/digital_twin/twin_acceptance.json",
    "gates/digital_twin/three_model_loader_compatibility.json",
    "gates/digital_twin/closed_loop_collection.json",
    "gates/digital_twin/yahboom_digital_twin_provenance.json",
    "gates/digital_twin/yahboom_sim_to_real_calibration_ledger.json",
)

#: The asset every prototype artefact was built on. F-TWIN-1 measured its box
#: collider extents as the squares of the source values.
DEFECTIVE_USD_SHA = "0ba6ca5df86d2b8d7d631a25be1eeb57b66c28516e599a02486a14233971cb1b"

GATES = (
    ("DT0", "ROBOT_ASSET_LOAD", "loads from a clean clone with no host-local paths"),
    ("DT1", "KINEMATIC_STRUCTURE", "links, joints, axes, transforms, collision primitives"),
    ("DT2", "ARM_AND_CAMERA_CONFIGURATION",
     "base_link -> arm_base -> q1..q6 -> mount -> optical frame, arm pose frozen"),
    ("DT3", "SENSOR_PIPELINE",
     "what the model receives: dimensions, FOV, rate, colour order, "
     "normalisation, context frames, goal image, timestamps"),
    ("DT4", "ROS2_BRIDGE", "runtime interface"),
    ("DT5", "MODEL_ADAPTERS", "one contract, three adapters"),
    ("DT6", "CLOSED_LOOP_NAVIGATION", "episodes execute end to end"),
    ("DT7", "STOPPING_BEHAVIOUR", "measurable, not incidental"),
    ("DT8", "SAFETY_LAYER", "shield present and exercised"),
    ("DT9", "RESET_REPRODUCIBILITY", "same inputs, same initial state"),
    ("DT10", "MULTI_MODEL_EVALUATION", "GNM, ViNT and NoMaD on one task"),
    ("DT11", "EVIDENCE_PROVENANCE", "one schema regardless of model"),
    ("DT12", "PHYSICAL_CALIBRATION", "the only gate that can support an as-built claim"),
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


def prior_prototype() -> dict[str, Any]:
    """Bind what already exists, and why it does not carry forward."""
    members = []
    for rel in PRIOR:
        path = REPO / rel
        entry: dict[str, Any] = {"path": rel, "sha256": sha256_file(path),
                                 "present": path.is_file()}
        if path.is_file():
            try:
                payload = json.loads(path.read_text())
                entry["admission_status"] = payload.get("admission_status")
                entry["claim_status"] = payload.get("claim_status")
                entry["robot_usd_sha256"] = payload.get("robot_usd_sha256")
                entry["camera_mount"] = payload.get("camera_mount")
            except (json.JSONDecodeError, AttributeError):
                entry["parse"] = "NOT_JSON"
        members.append(entry)

    bound_to_defective = [m["path"] for m in members
                          if m.get("robot_usd_sha256") == DEFECTIVE_USD_SHA]
    chassis_mounted = [m["path"] for m in members if m.get("camera_mount")]

    return {
        "exists": True,
        "dated": "2026-08-13",
        "members": members,
        "already_demonstrated": [
            "robot asset loads in Isaac",
            "kinematic structure inspected",
            "all three model loaders pass (GNM, ViNT, NoMaD)",
            "closed loop run with a released ViNT policy",
            "motion trace and frames emitted",
            "a sim-to-real calibration ledger exists",
        ],
        "why_it_does_not_carry_forward": {
            "defective_asset": {
                "artefacts": bound_to_defective,
                "usd_sha256": DEFECTIVE_USD_SHA,
                "detail": ("bound to the USD whose box collider extents F-TWIN-1 "
                           "measured as the squares of the source values"),
            },
            "withdrawn_camera_model": {
                "artefacts": chassis_mounted,
                "detail": ("recorded a chassis mast mount. The physical camera is "
                           "carried by the 6-DOF manipulator, so the transform is "
                           "configuration-dependent"),
            },
            "census_not_measurement": (
                "twin_acceptance recorded verdict PASS on a physics census that "
                "counted rigid bodies, colliders and joints. That is why the "
                "squared colliders passed: a collider of the wrong size is still "
                "one collider"),
            "host_local_paths": (
                "at least one artefact references an absolute path outside the "
                "repository, which DT0 forbids"),
            "provisional_values": (
                "wheel radius carried as PROVISIONAL_SIMULATION_VALUE"),
        },
        "status": "SUPERSEDED_PROTOTYPE_EVIDENCE",
        "retained_because": (
            "it is honest engineering history and it shows the shape of the work. "
            "It is not admissible and no claim may cite it"),
    }


def main() -> int:
    head = _git("rev-parse", "HEAD")
    record: dict[str, Any] = {
        "check": "DIGITAL_TWIN_PROGRAMME",
        "artifact_semantics": "PROGRAMME_DECLARATION_NO_IMPLEMENTATION",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": _dt.datetime.now(_dt.UTC).isoformat(),
        "repository_head": head,
        "MANDATORY": True,
        "independent_of": "the current BO-10 Arm-A attempt",
        "levels": {
            "DT_LEVEL_1_FUNCTIONAL": {
                "requires": [
                    "production robot USD loads from a clean environment",
                    "link hierarchy and joints valid",
                    "mecanum base geometry valid",
                    "6-DOF arm represented",
                    "arm-mounted RGB-D camera represented",
                    "navigation arm pose explicitly frozen",
                    "RGB observation and goal-image pipelines work",
                    "runtime interface works",
                    "GNM, ViNT and NoMaD adapters work through one contract",
                    "closed-loop episodes run",
                    "stopping behaviour measurable",
                    "evidence artefacts produced",
                    "seeds, configuration, checkpoints and assets pinned",
                    "reproducible from a clean clone",
                ],
                "may_use_provisional_values": True,
                "provisional_values_must_be_labelled": True,
            },
            "DT_LEVEL_2_CALIBRATED": {
                "additionally_requires": [
                    "authoritative Yahboom source reconciled",
                    "chassis and wheel dimensions validated",
                    "arm kinematics validated",
                    "physical navigation arm pose measured",
                    "camera mount extrinsic measured",
                    "RGB optical frame identity established",
                    "camera intrinsics frozen",
                    "simulated-versus-physical discrepancies recorded",
                    "every remaining provisional value resolved or retained with a "
                    "justified limitation",
                ],
            },
        },
        "INVARIANT": "FUNCTIONAL is not CALIBRATED. A twin that runs is not a twin that matches the robot",
        "gates": [{"id": g, "name": n, "requires": r} for g, n, r in GATES],
        "model_interface": {
            "contract": "one NavigationPolicy / ModelAdapter: reset, act, stop_score",
            "adapters": ["GNM", "ViNT", "NoMaD"],
            "prohibited": "three separate simulator pipelines",
        },
        "canonical_runner": {
            "entry_point": "run_digital_twin_eval",
            "model_selection": ["--model gnm", "--model vint", "--model nomad"],
            "frozen": ["robot asset", "scene", "seed", "start pose", "goal",
                       "camera configuration", "arm configuration", "checkpoint",
                       "preprocessing", "controller interface", "metrics"],
            "clean_clone_requirement": (
                "reproducible from documented dependencies with no reliance on "
                "host-local assets"),
        },
        "reproducibility_claim_boundary": (
            "where simulator or GPU nondeterminism prevents bitwise equality, "
            "declare tolerance-based reproducibility rather than asserting exact "
            "equality"),
        "prior_prototype": prior_prototype(),
        "SEQUENCING": (
            "implementation does not start until the authorised robot-asset tranche "
            "reaches its source and asset milestone. The production USD is a "
            "prerequisite of DT0, not only of Attempt 003"),
        "IMPLEMENTATION_STARTED": False,
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "ARM_B_EXECUTION": "NOT_STARTED",
    }

    sha = emit_evidence(OUT, record, required_keys=(
        "check", "levels", "gates", "model_interface", "prior_prototype",
        "SEQUENCING", "IMPLEMENTATION_STARTED"))

    print("=" * 70)
    print("DIGITAL TWIN PROGRAMME -- DECLARATION")
    print("=" * 70)
    print(f"HEAD                {head[:12]}")
    print(f"gates declared      {len(GATES)}  (DT0..DT12)")
    print("levels              FUNCTIONAL, CALIBRATED")
    print()
    prior: dict[str, Any] = record["prior_prototype"]
    print(f"prior prototype     {prior['status']}  dated {prior['dated']}")
    for member in prior["members"]:
        print(f"  {member['path'].split('/')[-1]:44s} "
              f"{member.get('admission_status')!s:14s} "
              f"{str(member['sha256'])[:12]}")
    print()
    print("  already demonstrated:")
    for item in prior["already_demonstrated"]:
        print(f"    - {item}")
    print()
    print("  superseded because:")
    for key in prior["why_it_does_not_carry_forward"]:
        print(f"    - {key}")
    print()
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha}")
    print("IMPLEMENTATION      NOT_STARTED")
    print("ARM_A_ATTEMPT_003   NOT_AUTHORISED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
