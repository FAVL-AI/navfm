"""ARM_A_LEGACY == ARM_A_INJECTED: is the target-selection seam behaviour-neutral?

The seam is a refactor inside the tracker, and that is precisely the confound
the intervention cannot carry. If introducing it changed behaviour at all, a
later A/B result would conflate "arc-length interpolated targeting" with "the
tracker was rewritten in between". So the seam is proved neutral now, while the
treatment does not exist and the answer cannot be chosen.

The reference is the pre-seam tracker itself, read out of the git object store
at a pinned commit and executed side by side with the current one. Comparing the
post-seam default path against the post-seam injected path alone would be nearly
a tautology: after the refactor they are the same call. Three configurations are
therefore compared, not two.

Nothing here runs a simulator, opens an episode, or touches run_00001, which is
used strictly as an offline pose trace.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
import inspect
import json
import math
import pathlib
import pickle
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.control import (  # noqa: E402
    M3PRO_LIMITS,
    DemonstratorMode,
    PurePursuit,
)
from navfm.evidence import emit_evidence  # noqa: E402
from navfm.target_selection import (  # noqa: E402
    LegacyVertexTargetSelector,
    TargetSelection,
)
from navfm.tracker_equivalence import (  # noqa: E402
    COMMAND_CHANNELS,
    TARGET_CHANNELS,
    compare_sequences,
    run_command_sequence,
    run_target_sequence,
)

#: The commit at which ``PurePursuit`` had no seam. Pinned, not HEAD: this
#: commit is the reference, and HEAD moves when the seam is committed.
PRE_SEAM_COMMIT = "437ebfc63f828fb1200df1f01df56bc339209349"
CONTROL_REL = "src/navfm/control.py"

PREREG = REPO / "gates/BO10/terminal_approach_intervention_v1_20260911.json"
RUN_TRAJ = REPO / "runs/bo10/hospital_bo10_run_00001/traj_data.pkl"
OUT = REPO / "gates/BO10/tracker_injection_equivalence_20260911.json"

#: The frozen collection configuration. Restated nowhere: read from the code
#: the arms will run under, via the same constants the runtime contract pins.
CONFIG: dict[str, Any] = {
    "lookahead": 0.45,
    "goal_tol": 0.20,
    "limits": M3PRO_LIMITS,
    "mode": DemonstratorMode.NONHOLONOMIC,
    "cruise_v": 0.35,
}


def sha256_file(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


# --- the pre-seam reference, loaded from git ---------------------------------


def load_pre_seam_module() -> tuple[Any, str]:
    """Import ``navfm.control`` as it stood before the seam existed."""
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{PRE_SEAM_COMMIT}:{CONTROL_REL}"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"cannot read {CONTROL_REL} at {PRE_SEAM_COMMIT[:12]}")
    source = proc.stdout
    digest = hashlib.sha256(source).hexdigest()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="preseam_")) / "control_pre_seam.py"
    tmp.write_bytes(source)
    spec = importlib.util.spec_from_file_location("control_pre_seam", tmp)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves a class's module through sys.modules, so a module
    # loaded from a spec has to be registered before it executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if "target_selector" in inspect.signature(module.PurePursuit.__init__).parameters:
        raise SystemExit(
            "the pinned reference already has the seam; it is not a pre-seam reference"
        )
    return module, digest


# --- the three configurations ------------------------------------------------


def make_trackers(pre_seam: Any, path: np.ndarray) -> dict[str, Any]:
    """PRE_SEAM, LEGACY_DIRECT and LEGACY_INJECTED over an identical path.

    These are instrument configurations, not intervention arms, and carry no
    production capture label.
    """
    return {
        "PRE_SEAM": pre_seam.PurePursuit(
            path.copy(),
            lookahead=CONFIG["lookahead"],
            goal_tol=CONFIG["goal_tol"],
            limits=pre_seam.M3PRO_LIMITS,
            mode=pre_seam.DemonstratorMode.NONHOLONOMIC,
            cruise_v=CONFIG["cruise_v"],
        ),
        "LEGACY_DIRECT": PurePursuit(path.copy(), **CONFIG),
        "LEGACY_INJECTED": PurePursuit(
            path.copy(), **CONFIG, target_selector=LegacyVertexTargetSelector()
        ),
    }


PAIRS = (
    ("PRE_SEAM", "LEGACY_DIRECT"),
    ("PRE_SEAM", "LEGACY_INJECTED"),
    ("LEGACY_DIRECT", "LEGACY_INJECTED"),
)


def compare_all(pre_seam: Any, path: np.ndarray, poses: np.ndarray) -> dict[str, Any]:
    """Both passes, all three pairs, from identical initial state."""
    out: dict[str, Any] = {}
    for pass_name, runner, channels in (
        ("command", run_command_sequence, COMMAND_CHANNELS),
        ("target", run_target_sequence, TARGET_CHANNELS),
    ):
        trackers = make_trackers(pre_seam, path)
        sequences = {name: runner(tracker, poses) for name, tracker in trackers.items()}
        for left, right in PAIRS:
            out[f"{pass_name}:{left}_vs_{right}"] = compare_sequences(
                sequences[left], sequences[right],
                left_label=left, right_label=right, channels=channels,
            )
    return out


def verdict_of(comparisons: dict[str, Any]) -> tuple[bool, int, float]:
    total = 0
    worst = 0.0
    for result in comparisons.values():
        if result.get("EQUIVALENCE") != "PASS":
            total += int(result.get("mismatch_total", 1) or 1)
        worst = max(worst, float(result.get("max_numerical_difference", 0.0)))
    return total == 0, total, worst


# --- analytic fixtures -------------------------------------------------------

_SQUARE = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 4.0]])
_STRAIGHT = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0], [4.0, 0.0]])
_CORNER = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
_LA = CONFIG["lookahead"]


def analytic_fixtures() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Deterministic scenarios covering the selector's decision surface."""
    walk = np.array([[t, 0.0, 0.0] for t in np.linspace(0.0, 4.0, 41)])
    return {
        "A_straight_path": (_STRAIGHT, np.array([[0.5, 0.0, 0.0], [1.5, 0.0, 0.0]])),
        "B_pose_exactly_on_vertex": (_STRAIGHT, np.array([[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])),
        "C_pose_between_vertices": (_STRAIGHT, np.array([[1.5, 0.0, 0.0]])),
        "D_single_corner": (_CORNER, np.array([[0.6, 0.0, 0.0], [0.95, 0.2, 1.4]])),
        "E_multiple_corners": (_SQUARE, np.array([[1.9, 0.1, 0.5], [2.0, 1.9, 2.0]])),
        # The comparison is strict ``<``, so a pose exactly one look-ahead from
        # the current vertex must NOT advance. Straddling that boundary is where
        # a transcription error would show first.
        "F_near_lookahead_boundary": (
            _STRAIGHT,
            np.array([[1.0 - _LA - 1e-9, 0.0, 0.0], [1.0 - _LA + 1e-9, 0.0, 0.0]]),
        ),
        "G_exactly_on_lookahead_boundary": (
            _STRAIGHT, np.array([[1.0 - _LA, 0.0, 0.0]])),
        "H_off_route_pose": (_SQUARE, np.array([[5.0, -3.0, 0.0], [-2.0, 6.0, 3.0]])),
        "I_final_segment": (_STRAIGHT, np.array([[3.6, 0.0, 0.0]])),
        "J_near_route_end_short_remainder": (
            _STRAIGHT, np.array([[3.9, 0.0, 0.0], [3.99, 0.0, 0.0]])),
        "K_final_goal_vertex": (_STRAIGHT, np.array([[4.0, 0.0, 0.0]])),
        "L_target_index_advancement": (_SQUARE, walk[:20]),
        "M_persistent_state_repeated_calls": (_STRAIGHT, np.repeat(walk[:10], 3, axis=0)),
        "N_zero_heading_error": (_STRAIGHT, np.array([[0.5, 0.0, 0.0], [0.5, 0.0, 1e-12]])),
        # The speed law switches to an in-place turn beyond 75 degrees; both
        # sides of that boundary are exercised.
        "O_large_heading_error_regime_boundary": (
            _STRAIGHT,
            np.array([
                [0.5, 0.0, math.radians(74.0)],
                [0.5, 0.0, math.radians(75.0)],
                [0.5, 0.0, math.radians(76.0)],
                [0.5, 0.0, math.radians(179.0)],
            ]),
        ),
    }


# --- negative controls (test-only selectors, never production) ---------------


class _OffByOneSelector:
    """Advances one vertex past legacy. Must be caught."""

    target_type = "NEGATIVE_CONTROL_OFF_BY_ONE"

    def select_target(
        self, path: np.ndarray, position: np.ndarray, index: int, lookahead: float
    ) -> TargetSelection:
        legacy = LegacyVertexTargetSelector().select_target(path, position, index, lookahead)
        idx = min(legacy.next_index + 1, path.shape[0] - 1)
        return TargetSelection(path[idx], idx)


class _StateDriftSelector:
    """Correct point, wrong state transition. Must be caught on index, even
    where the instantaneous target and command agree."""

    target_type = "NEGATIVE_CONTROL_STATE_DRIFT"

    def select_target(
        self, path: np.ndarray, position: np.ndarray, index: int, lookahead: float
    ) -> TargetSelection:
        legacy = LegacyVertexTargetSelector().select_target(path, position, index, lookahead)
        return TargetSelection(legacy.point, index)


class _CommandPerturbedTracker(PurePursuit):
    """Legacy target selection, perturbed command. Proves the proof is not
    merely comparing selector coordinates."""

    def step(self, position: np.ndarray, yaw: float) -> tuple[float, float, float, bool]:
        vx, vy, wz, done = super().step(position, yaw)
        return vx, vy, wz + 1e-12, done


def negative_controls(pre_seam: Any, path: np.ndarray, poses: np.ndarray) -> dict[str, Any]:
    """The instrument must fail when it should. A proof that cannot fail is not
    a proof."""
    out: dict[str, Any] = {}

    reference = run_command_sequence(PurePursuit(path.copy(), **CONFIG), poses)
    reference_target = run_target_sequence(PurePursuit(path.copy(), **CONFIG), poses)

    wrong = run_target_sequence(
        PurePursuit(path.copy(), **CONFIG, target_selector=_OffByOneSelector()), poses)
    out["wrong_selector"] = compare_sequences(
        reference_target, wrong, left_label="LEGACY", right_label="OFF_BY_ONE",
        channels=TARGET_CHANNELS)

    drift = run_target_sequence(
        PurePursuit(path.copy(), **CONFIG, target_selector=_StateDriftSelector()), poses)
    out["state_drift"] = compare_sequences(
        reference_target, drift, left_label="LEGACY", right_label="STATE_DRIFT",
        channels=TARGET_CHANNELS)

    perturbed = run_command_sequence(_CommandPerturbedTracker(path.copy(), **CONFIG), poses)
    out["command_drift"] = compare_sequences(
        reference, perturbed, left_label="LEGACY", right_label="COMMAND_PERTURBED",
        channels=COMMAND_CHANNELS)

    out["refusal_malformed_poses"] = run_command_sequence(
        PurePursuit(path.copy(), **CONFIG), [[1.0, 2.0], [3.0, 4.0]])
    out["refusal_mismatched_lengths"] = compare_sequences(
        reference, run_command_sequence(PurePursuit(path.copy(), **CONFIG), poses[:3]),
        left_label="LEGACY", right_label="SHORT", channels=COMMAND_CHANNELS)
    return out


# --- control-law invariance --------------------------------------------------


def control_law_invariance(pre_seam: Any) -> dict[str, Any]:
    """Did the mathematics move, or only the plumbing?

    ``control.py`` necessarily changed -- the seam lives in it -- so claiming
    the file is unchanged by hash would be false. What is claimed instead is
    narrower and checkable: the source of every law outside the seam is
    byte-identical between the pinned pre-seam module and the current one.
    """
    members = {
        "speed_and_angular_law_step": (pre_seam.PurePursuit.step, PurePursuit.step),
        # __dict__ rather than attribute access: the property object is what
        # carries the source, and mypy does not model .fget on the descriptor.
        "route_completion_finished": (
            pre_seam.PurePursuit.__dict__["finished"].fget,
            PurePursuit.__dict__["finished"].fget,
        ),
        "velocity_clipping_clamp": (
            pre_seam.BaseLimits.clamp, M3PRO_LIMITS.__class__.clamp),
        "se2_integration_unicycle": (pre_seam.unicycle_step, _current("unicycle_step")),
        "se2_integration_holonomic": (pre_seam.holonomic_step, _current("holonomic_step")),
        "waypoint_to_twist": (pre_seam.waypoint_to_twist, _current("waypoint_to_twist")),
    }
    detail: dict[str, Any] = {}
    unchanged = True
    for name, (before, after) in members.items():
        a = hashlib.sha256(inspect.getsource(before).encode()).hexdigest()
        b = hashlib.sha256(inspect.getsource(after).encode()).hexdigest()
        detail[name] = {"pre_seam_sha256": a, "current_sha256": b, "identical": a == b}
        unchanged &= a == b
    return {
        "CONTROL_LAW_INVARIANCE": "PASS" if unchanged else "FAIL",
        "method": "byte comparison of each law's source between the pinned pre-seam module and now",
        "members": detail,
        "control_py_file_hash_changed": True,
        "why_the_file_hash_is_not_the_claim": (
            "the seam is an edit to control.py, so the file hash necessarily moved. "
            "Claiming unchanged-by-hash would be false. The claim made here is that "
            "the source of every law OUTSIDE the target seam is byte-identical"
        ),
        "what_changed_in_control_py": [
            "an import of the seam module",
            "a target_selector keyword argument defaulting to None",
            "assignment of the default LegacyVertexTargetSelector",
            "PurePursuit.target now delegates selection and applies the returned index",
        ],
    }


def _current(name: str) -> Any:
    import navfm.control as current

    return getattr(current, name)


# --- override surface --------------------------------------------------------


def override_surface() -> dict[str, Any]:
    """What can an injected selector actually reach?"""
    signature = inspect.signature(LegacyVertexTargetSelector.select_target)
    parameters = [p for p in signature.parameters if p != "self"]
    forbidden = {"tracker", "self_tracker", "limits", "cruise_v", "mode", "goal_tol",
                 "dt", "max_steps", "route", "goal"}
    reachable = sorted(set(parameters) & forbidden)
    behavioural = [
        name for name in dir(LegacyVertexTargetSelector)
        if not name.startswith("_") and callable(getattr(LegacyVertexTargetSelector, name))
    ]
    return {
        "BEHAVIOURAL_OVERRIDE_SURFACE": behavioural,
        "surface_is_target_selection_only": behavioural == ["select_target"],
        "selector_parameters": parameters,
        "selector_cannot_reach": sorted(forbidden),
        "forbidden_parameters_present": reachable,
        "why_it_is_structural": (
            "the selector is never handed the tracker, so it has no path to the speed "
            "law, the gains, the limits, the stop branch, dt, max_steps or the goal "
            "criteria. A treatment wanting those would have to edit the tracker, where "
            "the change is a visible source diff rather than an injected object"
        ),
        "intervention_contract_field": "target",
    }


def main() -> int:
    pre_seam, pre_seam_sha = load_pre_seam_module()
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()

    prereg = json.loads(PREREG.read_text())
    route = np.array(
        prereg["secondary_outcome_cross_track_error"]["frozen_route_polyline"]["coordinates"],
        dtype=np.float64,
    )

    print("=" * 66)
    print("ARM_A_LEGACY == ARM_A_INJECTED")
    print("=" * 66)
    print(f"HEAD                {head[:12]}")
    print(f"pre-seam reference  {PRE_SEAM_COMMIT[:12]}:{CONTROL_REL}")
    print(f"pre-seam sha256     {pre_seam_sha[:32]}...")
    print()

    surface = override_surface()
    invariance = control_law_invariance(pre_seam)
    print(f"override surface    {surface['BEHAVIOURAL_OVERRIDE_SURFACE']}  "
          f"target-only={surface['surface_is_target_selection_only']}")
    print(f"control-law invariance {invariance['CONTROL_LAW_INVARIANCE']}")
    print()

    # --- analytic fixtures ---
    fixture_results: dict[str, Any] = {}
    fixture_ok = True
    fixture_worst = 0.0
    for name, (path, poses) in analytic_fixtures().items():
        comparisons = compare_all(pre_seam, path, poses)
        ok, total, worst = verdict_of(comparisons)
        fixture_ok &= ok
        fixture_worst = max(fixture_worst, worst)
        fixture_results[name] = {
            "steps": int(poses.shape[0]),
            "verdict": "PASS" if ok else "FAIL",
            "mismatch_total": total,
            "max_numerical_difference": worst,
            "comparisons": {k: v["EQUIVALENCE"] for k, v in comparisons.items()},
            "failing": {k: v for k, v in comparisons.items() if v.get("EQUIVALENCE") != "PASS"},
        }
        print(f"  {name:42s} {fixture_results[name]['verdict']}  "
              f"steps={fixture_results[name]['steps']}")
    print(f"analytic fixtures   {'PASS' if fixture_ok else 'FAIL'}  "
          f"({len(fixture_results)} fixtures)")
    print()

    # --- recorded pose trace (offline input only) ---
    with RUN_TRAJ.open("rb") as handle:
        traj = pickle.load(handle)
    positions = np.asarray(traj["position"], dtype=np.float64)
    yaws = np.asarray(traj["yaw"], dtype=np.float64)
    poses = np.column_stack([positions[:, 0], positions[:, 1], yaws])

    traces: dict[str, Any] = {}
    trace_ok = True
    trace_worst = 0.0
    from navfm.control import resample_path

    for trace_name, trace_path in (
        ("frozen_route_polyline", route),
        # A densified copy of the same route, so index advancement is exercised
        # across many vertices rather than saturating after four.
        ("frozen_route_resampled_0m25", resample_path(route, 0.25)),
    ):
        comparisons = compare_all(pre_seam, trace_path, poses)
        ok, total, worst = verdict_of(comparisons)
        trace_ok &= ok
        trace_worst = max(trace_worst, worst)
        channels: dict[str, int] = {}
        for result in comparisons.values():
            for channel, count in result.get("mismatches_by_channel", {}).items():
                channels[channel] = channels.get(channel, 0) + count
        traces[trace_name] = {
            "path_vertices": int(np.asarray(trace_path).shape[0]),
            "steps_evaluated": int(poses.shape[0]),
            "verdict": "PASS" if ok else "FAIL",
            "mismatch_total": total,
            "mismatches_by_channel": channels,
            "max_numerical_difference": worst,
            "comparisons": {k: v["EQUIVALENCE"] for k, v in comparisons.items()},
        }
        print(f"  {trace_name:42s} {traces[trace_name]['verdict']}  "
              f"steps={poses.shape[0]}  vertices={traces[trace_name]['path_vertices']}  "
              f"mismatches={total}")
    print(f"recorded trace      {'PASS' if trace_ok else 'FAIL'}")
    print()

    # --- negative controls ---
    controls = negative_controls(pre_seam, resample_path(route, 0.25), poses)
    control_verdicts = {
        "wrong_selector": controls["wrong_selector"]["EQUIVALENCE"] == "FAIL",
        "state_drift": controls["state_drift"]["EQUIVALENCE"] == "FAIL",
        "command_drift": controls["command_drift"]["EQUIVALENCE"] == "FAIL",
        "refusal_malformed_poses": (
            controls["refusal_malformed_poses"]["EQUIVALENCE"] == "EQUIVALENCE_REFUSED"),
        "refusal_mismatched_lengths": (
            controls["refusal_mismatched_lengths"]["EQUIVALENCE"] == "EQUIVALENCE_REFUSED"),
    }
    state_drift_index_only = (
        controls["state_drift"]["mismatches_by_channel"].get("index_after", 0) > 0
    )
    controls_ok = all(control_verdicts.values()) and state_drift_index_only
    for name, fired in control_verdicts.items():
        print(f"  {name:42s} {'FIRED' if fired else 'DID NOT FIRE'}")
    print(f"negative controls   {'PASS' if controls_ok else 'FAIL'}")
    print()

    verdict = (
        "PASS"
        if (fixture_ok and trace_ok and controls_ok
            and invariance["CONTROL_LAW_INVARIANCE"] == "PASS"
            and surface["surface_is_target_selection_only"])
        else "FAIL"
    )

    record = {
        "check": "TRACKER_INJECTION_HOOK_V1_ARM_A_EQUIVALENCE",
        "artifact_semantics": "INSTRUMENT_EQUIVALENCE_PROOF_NO_ARM_HAS_RUN",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": _dt.datetime.now(_dt.UTC).isoformat(),
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
        "repository_head": head,
        "pre_seam_reference": {
            "commit": PRE_SEAM_COMMIT,
            "path": CONTROL_REL,
            "sha256": pre_seam_sha,
            "why_pinned_not_head": (
                "committing the seam moves HEAD; a reference that follows HEAD would "
                "compare the new implementation with itself"
            ),
        },
        "implementations": {
            "PRE_SEAM": f"{PRE_SEAM_COMMIT[:12]}:{CONTROL_REL} PurePursuit",
            "LEGACY_DIRECT": "navfm.control.PurePursuit (no explicit selector)",
            "LEGACY_INJECTED": (
                "navfm.control.PurePursuit(target_selector=LegacyVertexTargetSelector())"),
            "these_are_not_intervention_arms": True,
        },
        "selector_identity": {
            "class": "navfm.target_selection.LegacyVertexTargetSelector",
            "target_type": LegacyVertexTargetSelector.target_type,
            "module_sha256": sha256_file(REPO / "src/navfm/target_selection.py"),
        },
        "controller_identity": {
            "path": CONTROL_REL,
            "current_sha256": sha256_file(REPO / CONTROL_REL),
            "pre_seam_sha256": pre_seam_sha,
        },
        "configuration": {
            "lookahead": CONFIG["lookahead"],
            "goal_tol": CONFIG["goal_tol"],
            "cruise_v": CONFIG["cruise_v"],
            "mode": CONFIG["mode"].value,
            "max_v": M3PRO_LIMITS.max_v,
            "max_w": M3PRO_LIMITS.max_w,
        },
        "route_identity": {
            "source": "gates/BO10/terminal_approach_intervention_v1_20260911.json",
            "preregistration_sha256": sha256_file(PREREG),
            "vertices": int(route.shape[0]),
        },
        "run_00001_source": {
            "path": "runs/bo10/hospital_bo10_run_00001/traj_data.pkl",
            "sha256": sha256_file(RUN_TRAJ),
            "used_as": "OFFLINE_POSE_TRACE_ONLY",
            "dynamics_replayed": False,
            "modified": False,
        },
        "override_surface": surface,
        "control_law_invariance": invariance,
        "numerical_standard": {
            "criterion": "exact equality",
            "tolerance": 0.0,
            "justification": (
                "both paths execute the same arithmetic on the same inputs, so a "
                "refactor should agree bitwise. No tolerance was fitted to an "
                "observed discrepancy, because none was observed"
            ),
        },
        "analytic_fixtures": {
            "count": len(fixture_results),
            "verdict": "PASS" if fixture_ok else "FAIL",
            "max_numerical_difference": fixture_worst,
            "results": fixture_results,
        },
        "recorded_pose_equivalence": {
            "verdict": "PASS" if trace_ok else "FAIL",
            "max_numerical_difference": trace_worst,
            "traces": traces,
        },
        "negative_controls": {
            "verdict": "PASS" if controls_ok else "FAIL",
            "fired": control_verdicts,
            "state_drift_detected_on_index_after": state_drift_index_only,
            "detail": {
                name: {
                    "EQUIVALENCE": result.get("EQUIVALENCE"),
                    "mismatch_total": result.get("mismatch_total"),
                    "mismatches_by_channel": result.get("mismatches_by_channel"),
                    "first_mismatch": (result.get("first_mismatches") or [None])[0],
                    "reason": result.get("reason"),
                }
                for name, result in controls.items()
            },
        },
        "claim_boundary": (
            "this establishes that the seam is behaviour-neutral for the legacy "
            "selector, over these fixtures and this recorded pose trace, under the "
            "frozen configuration. It does not establish anything about the "
            "treatment selector, which does not exist in this tranche, and it is not "
            "an intervention result: no arm has run"
        ),
        "EXECUTION_MANIFEST_OWES_ARM_OUTPUT_ALLOWLIST": True,
        "ARM_A_EXECUTION": "NOT_STARTED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "ARM_A_LEGACY_INJECTION_EQUIVALENCE": verdict,
    }

    sha = emit_evidence(
        OUT,
        record,
        required_keys=(
            "ARM_A_LEGACY_INJECTION_EQUIVALENCE",
            "pre_seam_reference",
            "analytic_fixtures",
            "recorded_pose_equivalence",
            "negative_controls",
            "EXECUTION_STATUS",
        ),
    )
    print(f"artefact            {OUT.relative_to(REPO)}")
    print(f"sha256              {sha}")
    print(f"ARM_A_LEGACY_INJECTION_EQUIVALENCE  {verdict}")
    print("ARM_A_EXECUTION     NOT_STARTED")
    print("ARM_B_EXECUTION     NOT_STARTED")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
