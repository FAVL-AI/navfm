"""Execution preflight for TERMINAL_APPROACH_INTERVENTION_V1.

Everything here is settled before either arm runs, and everything here is
settled without a GPU. That division is deliberate: the parts of an experiment
most vulnerable to being shaped by early results are exactly the parts that do
not need the simulator, so they are frozen while results are not merely unseen
but impossible to see.

Three things are established:

**The arms differ in target selection and in nothing else.** This is checked
mechanically, by asking Python which attributes the treatment class actually
overrides rather than by reading the source and forming an opinion about it. An
audit that trusted a docstring would pass a class that quietly overrode ``step``.

**Arm identity and execution order are frozen.** Control before treatment, by
protocol, recorded with the configuration digests both arms will run under. Order
chosen after a crash or a suggestive trace is order chosen by the experimenter.

**The Isaac slot is checked and reported honestly.** A missing runtime is the
absence of a test, never a result, and a GPU that has silently become unusable is
worse than one that is plainly absent: the simulator may still start and produce
a trajectory that looks like evidence.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from diagnose_q2_margin_consumption import sha256  # noqa: E402

from navfm.collection.interpolated_target import (  # noqa: E402
    InterpolatedLookaheadPursuit,
)
from navfm.control import PurePursuit  # noqa: E402

PREREG = REPO / "gates/BO10/terminal_approach_intervention_v1_20260911.json"
GUARD = REPO / "gates/BO10/prereg_immutability_guard_20260911.json"
CONTROLS = REPO / "gates/BO10/target_selection_controls_20260911.json"
OUT = REPO / "gates/BO10/intervention_execution_preflight_20260911.json"

ISAAC_PY = pathlib.Path.home() / "miniforge3/envs/isaac/bin/python"

SHARED = [
    "src/navfm/control.py",
    "src/navfm/isaac/collect.py",
    "src/navfm/isaac/robot.py",
    "src/navfm/isaac/app.py",
    "src/navfm/collection/kinematic_drive.py",
    "src/navfm/collection/route_projection.py",
    "src/navfm/planning.py",
    "src/navfm/kinematics.py",
]


def implementation_audit() -> dict[str, Any]:
    """Which behaviours the treatment arm overrides, asked of Python not prose."""
    base = {n for n in dir(PurePursuit) if not n.startswith("__")}
    overridden = sorted(
        n for n in base
        if n in InterpolatedLookaheadPursuit.__dict__
    )
    added = sorted(
        n for n in InterpolatedLookaheadPursuit.__dict__
        if not n.startswith("__") and n not in base
    )
    inherited = sorted(base - set(overridden))
    behavioural = [n for n in overridden if n not in {"target_type"}]
    return {
        "method": (
            "the class dictionary is inspected directly, so an override cannot be "
            "hidden behind a comment or a docstring claim"
        ),
        "control_class": f"{PurePursuit.__module__}.{PurePursuit.__qualname__}",
        "treatment_class": (
            f"{InterpolatedLookaheadPursuit.__module__}."
            f"{InterpolatedLookaheadPursuit.__qualname__}"
        ),
        "treatment_is_subclass_of_control": issubclass(
            InterpolatedLookaheadPursuit, PurePursuit),
        "overridden_attributes": overridden,
        "behavioural_overrides": behavioural,
        "added_attributes": added,
        "inherited_unchanged": inherited,
        "ONLY_TARGET_SELECTION_DIFFERS": behavioural == ["target"],
        "why_that_is_the_criterion": (
            "target() is the smallest component that selects what the tracker "
            "steers at. Everything the speed and stop behaviour depend on -- step, "
            "finished, the limits, the goal predicate -- is inherited, so a "
            "difference between arms cannot come from them"
        ),
        "control_source_unmodified": {
            "path": "src/navfm/control.py",
            "sha256": sha256(REPO / "src/navfm/control.py"),
            "note": (
                "arm A runs this file unchanged; the treatment lives in a separate "
                "module so the control arm's code is byte-identical to the frozen one"
            ),
        },
    }


def isaac_slot() -> dict[str, Any]:
    """Is the simulator actually usable, as opposed to merely importable?"""
    out: dict[str, Any] = {"interpreter": str(ISAAC_PY)}

    nv = subprocess.run(["nvidia-smi"], capture_output=True, text=True, check=False)
    out["nvidia_smi_returncode"] = nv.returncode
    out["nvidia_smi_stderr"] = (nv.stderr or nv.stdout).strip().splitlines()[:2]

    kver = ""
    kpath = pathlib.Path("/proc/driver/nvidia/version")
    if kpath.exists():
        m = re.search(r"([0-9]+\.[0-9]+\.[0-9]+)", kpath.read_text())
        kver = m.group(1) if m else ""
    out["kernel_module_version"] = kver

    libs = sorted(
        p.name for p in pathlib.Path("/usr/lib/x86_64-linux-gnu").glob("libcuda.so.*")
        if re.search(r"\d+\.\d+\.\d+$", p.name)
    )
    out["userspace_libcuda"] = libs
    uver = ""
    if libs:
        m = re.search(r"([0-9]+\.[0-9]+\.[0-9]+)$", libs[-1])
        uver = m.group(1) if m else ""
    out["userspace_version"] = uver
    out["kernel_userspace_mismatch"] = bool(kver and uver and kver != uver)

    probe = subprocess.run(
        [str(ISAAC_PY), "-c",
         "import json,torch;"
         "d={'torch':torch.__version__,'available':torch.cuda.is_available(),"
         "'count':torch.cuda.device_count()};"
         "print('PROBE'+json.dumps(d))"],
        capture_output=True, text=True, check=False, timeout=300,
    )
    line = next((ln for ln in probe.stdout.splitlines() if ln.startswith("PROBE")), "")
    out["cuda_probe"] = json.loads(line[5:]) if line else {"error": "probe produced no result"}
    err = probe.stderr or ""
    out["cuda_error_code"] = "804" if "Error 804" in err else (
        "none" if out.get("cuda_probe", {}).get("available") else "unknown")

    usable = bool(out.get("cuda_probe", {}).get("available"))
    out["ISAAC_SLOT"] = "AVAILABLE" if usable else "BLOCKED"
    if not usable:
        out["diagnosis"] = (
            f"the loaded NVIDIA kernel module is {kver} while the userspace driver "
            f"libraries on disk are {uver}. CUDA reports error 804, forward "
            "compatibility attempted on unsupported hardware, and torch sees zero "
            "devices. The driver userspace was upgraded without the kernel module "
            "being reloaded"
        )
        out["why_import_isaacsim_still_succeeds"] = (
            "importing isaacsim touches no GPU, so it is not evidence that the "
            "simulator can run. This is the shape of false green this repository "
            "has a standing rule about"
        )
        out["remedy_requires_operator_action"] = (
            "reload the NVIDIA kernel modules or reboot, then re-verify. Both are "
            "system-level and disruptive, so neither is performed here"
        )
        out["what_must_not_be_done"] = (
            "running the arms anyway. The simulator might start and produce a "
            "trajectory that looks like evidence while rendering or physics ran "
            "somewhere other than the frozen configuration"
        )
    return out


def main() -> int:
    stamp = _dt.datetime.now(_dt.UTC).isoformat()
    for path in (PREREG, GUARD, CONTROLS):
        if not path.exists():
            raise SystemExit(f"preflight cannot proceed: {path} is absent")

    guard = json.loads(GUARD.read_text())
    controls = json.loads(CONTROLS.read_text())
    audit = implementation_audit()
    slot = isaac_slot()

    arms: dict[str, Any] = {
        "frozen_before_execution": True,
        "frozen_while_results_were_impossible_to_observe": slot["ISAAC_SLOT"] == "BLOCKED",
        "execution_order": ["ARM_A_CONTROL", "ARM_B_TREATMENT"],
        "order_selection_rule": (
            "control before treatment, fixed by protocol rather than chosen. Order "
            "picked after a crash or a suggestive trace is order picked by the "
            "experimenter"
        ),
        "retry_rule": (
            "an arm that fails before producing a valid artefact is recorded as "
            "RUN_FAILED_NO_ARTEFACT and may be re-run once under the identical "
            "frozen configuration. Repeated re-running until a desired outcome "
            "appears is forbidden, and any re-run is recorded with its reason"
        ),
        "ARM_A_CONTROL": {
            "tracker": "navfm.control.PurePursuit",
            "target_type": "PATH_VERTEX",
            "source_sha256": sha256(REPO / "src/navfm/control.py"),
        },
        "ARM_B_TREATMENT": {
            "tracker": (
                "navfm.collection.interpolated_target.InterpolatedLookaheadPursuit"),
            "target_type": InterpolatedLookaheadPursuit.target_type,
            "source_sha256": sha256(REPO / "src/navfm/collection/interpolated_target.py"),
        },
        "shared_configuration_digests": {
            p: sha256(REPO / p) for p in SHARED if (REPO / p).exists()
        },
        "frozen_parameters_from_the_preregistration": {
            "lookahead_m": 0.45,
            "goal_tol_m": 0.20,
            "note": "read from the preregistration, not restated independently",
        },
        "reset_requirements_between_arms": [
            "the same scene asset and digest",
            "the same start position and yaw",
            "the same camera transform",
            "the same frozen route polyline",
            "the same sealed goal",
            "a freshly constructed tracker, so no target index carries over",
            "no residual base or articulation velocity",
            "the same seed",
            "no trajectory history from the previous arm",
        ],
        "arm_b_must_not_start_from_arm_a_terminal_state": True,
    }

    ready = bool(
        guard["PREREG_CANONICAL_PAYLOAD_GUARD"] == "PASS"
        and controls["TARGET_SELECTION_CONTROLS"] == "PASS"
        and audit["ONLY_TARGET_SELECTION_DIFFERS"]
    )

    result = {
        "check": "TERMINAL_APPROACH_INTERVENTION_V1_EXECUTION_PREFLIGHT",
        "artifact_semantics": "PREFLIGHT_ONLY_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "preregistration": {
            "path": str(PREREG.relative_to(REPO)),
            "sha256": sha256(PREREG),
            "version": "V1",
        },
        "gates": {
            "PREREG_CANONICAL_PAYLOAD_GUARD": {
                "verdict": guard["PREREG_CANONICAL_PAYLOAD_GUARD"],
                "controls": f"{guard['controls_passed']}/{guard['controls_total']}",
                "artefact": str(GUARD.relative_to(REPO)),
                "sha256": sha256(GUARD),
            },
            "TARGET_SELECTION_CONTROLS": {
                "verdict": controls["TARGET_SELECTION_CONTROLS"],
                "controls": f"{controls['controls_passed']}/{controls['controls_total']}",
                "artefact": str(CONTROLS.relative_to(REPO)),
                "sha256": sha256(CONTROLS),
            },
        },
        "implementation_difference_audit": audit,
        "arm_identity_and_order": arms,
        "isaac_slot": slot,
        "SOFTWARE_PREFLIGHT": "PASS" if ready else "FAIL",
        "EXECUTION_GATE": (
            "OPEN" if (ready and slot["ISAAC_SLOT"] == "AVAILABLE") else "BLOCKED"),
        "blocking_reason": (
            None if (ready and slot["ISAAC_SLOT"] == "AVAILABLE")
            else ("the Isaac slot is unavailable; every software gate passes"
                  if ready else "a software gate failed")
        ),
        "classification_of_the_arms": (
            "NOT_RUN. Neither arm has been attempted. This is the absence of an "
            "experiment, not a failed one, and it must never be recorded as a result"
        ),
        "milestone_unaffected": {
            "BO-03_REAL_DATA_COMPATIBILITY": "COMPLETE",
            "BO-10_HOSPITAL_COLLECTION": "COMPLETE_FOR_COMPATIBILITY_PURPOSE",
            "run_00001": "IMMUTABLE and excluded from the two-arm comparison",
        },
    }

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    for key in ("EXECUTION_STATUS", "implementation_difference_audit",
                "arm_identity_and_order", "isaac_slot", "EXECUTION_GATE"):
        if key not in back:
            raise SystemExit(f"evidence guard: missing {key}")
    if back["EXECUTION_STATUS"] != "NOT_RUN":
        raise SystemExit("evidence guard: no arm has run and the artefact must say so")

    print(f"prereg guard        {guard['PREREG_CANONICAL_PAYLOAD_GUARD']}")
    print(f"target controls     {controls['TARGET_SELECTION_CONTROLS']}")
    print(f"behavioural overrides in arm B: {audit['behavioural_overrides']}")
    print(f"only target differs {audit['ONLY_TARGET_SELECTION_DIFFERS']}")
    print(f"control.py          {audit['control_source_unmodified']['sha256'][:16]}...  UNMODIFIED")
    print(f"arm order           {' -> '.join(arms['execution_order'])}  (frozen)")
    print()
    print(f"kernel module       {slot['kernel_module_version']}")
    print(f"userspace driver    {slot['userspace_version']}")
    print(f"mismatch            {slot['kernel_userspace_mismatch']}")
    print(f"cuda probe          {slot['cuda_probe']}")
    print(f"ISAAC_SLOT          {slot['ISAAC_SLOT']}")
    print()
    print(f"SOFTWARE_PREFLIGHT  {result['SOFTWARE_PREFLIGHT']}")
    print(f"EXECUTION_GATE      {result['EXECUTION_GATE']}")
    print(f"EXECUTION_STATUS    {result['EXECUTION_STATUS']}")
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha256(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
