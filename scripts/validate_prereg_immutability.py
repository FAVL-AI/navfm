"""PREREG_CANONICAL_PAYLOAD_GUARD -- prove the freeze-once emitter refuses drift.

A preregistration is only worth citing if "frozen" means more than "a file is
present". Two failure modes would both destroy that guarantee while leaving the
repository looking healthy:

  returning the existing artefact because it exists
      -> a changed design is never noticed
  regenerating and overwriting the artefact
      -> a cited record silently stops describing the frozen experiment

The emitter must instead regenerate the canonical payload, preserve the original
freeze timestamp, compare every other field, and REFUSE when they differ. This
harness proves it does, in both directions, and proves the refusal is load
bearing rather than cosmetic by checking that nothing was written and that the
process exit status is non-zero.

The real artefact is never touched. Every control runs against a temporary copy
with the emitter's output path redirected, because a validation harness that
mutates the evidence it is validating is the defect it is supposed to catch.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import preregister_terminal_approach_intervention as emitter  # noqa: E402

REAL = emitter.OUT
OUT = REPO / "gates/BO10/prereg_immutability_guard_20260911.json"

#: One representative field per structural kind, so a guard that only compares
#: the top level or only compares strings cannot pass this harness.
MUTATIONS: list[tuple[str, list[str], object]] = [
    ("scalar string, nested two deep",
     ["design_carried_forward_unchanged", "primary_outcome"],
     "entry into the 0.50 m goal region before max_steps"),
    ("integer",
     ["power_and_claim_limit", "sample_count_per_arm"], 3),
    ("boolean that the design depends on",
     ["secondary_outcome_cross_track_error", "is_primary"], True),
    ("float inside a pinned parameter",
     ["secondary_outcome_lookahead_domain", "lookahead_radius_m"], 0.9),
    ("list membership",
     ["secondary_outcome_cross_track_error",
      "statistics_to_report_per_arm_per_window"],
     ["mean_absolute_cross_track_m"]),
]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_emitter_against(path: pathlib.Path) -> tuple[bool, str]:
    """Run the emitter with its output redirected. Returns (refused, message)."""
    original = emitter.OUT
    emitter.OUT = path
    try:
        emitter.main()
        return False, "emitter completed without refusing"
    except SystemExit as exc:
        return True, str(exc.code if exc.code is not None else "")
    finally:
        emitter.OUT = original


def main() -> int:
    stamp = _dt.datetime.now(_dt.UTC).isoformat()
    if not REAL.exists():
        raise SystemExit(f"the frozen preregistration is absent: {REAL}")
    frozen_bytes = REAL.read_bytes()
    frozen_digest = sha256_bytes(frozen_bytes)
    controls: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)

        # --- Control A: unchanged design reproduces the frozen digest --------
        a_path = tmp / "arm_a.json"
        shutil.copyfile(REAL, a_path)
        refused, msg = run_emitter_against(a_path)
        a_digest = sha256_bytes(a_path.read_bytes())
        controls.append({
            "control": "A_unchanged_design_reproduces_digest",
            "expectation": "the emitter regenerates identical bytes and does not refuse",
            "refused": refused,
            "regenerated_digest": a_digest,
            "frozen_digest": frozen_digest,
            "digest_matches": a_digest == frozen_digest,
            "PASS": bool(not refused and a_digest == frozen_digest),
            "message": msg if refused else "",
        })

        # --- Control B: every mutation kind must be refused ------------------
        for label, fpath, value in MUTATIONS:
            b_path = tmp / f"arm_b_{'_'.join(fpath)}.json"
            payload = json.loads(frozen_bytes)
            node = payload
            for key in fpath[:-1]:
                node = node[key]
            before = node[fpath[-1]]
            node[fpath[-1]] = value
            b_path.write_text(json.dumps(payload, indent=2) + "\n")
            mutated_digest = sha256_bytes(b_path.read_bytes())

            refused, msg = run_emitter_against(b_path)
            after_digest = sha256_bytes(b_path.read_bytes())
            names_field = ".".join(fpath) in msg
            controls.append({
                "control": f"B_refuses_drift::{'.'.join(fpath)}",
                "mutation_kind": label,
                "field": ".".join(fpath),
                "frozen_value": before,
                "mutated_value": value,
                "expectation": (
                    "the emitter refuses, does not overwrite, and names the field"
                ),
                "refused": refused,
                "artefact_left_untouched": after_digest == mutated_digest,
                "would_have_silently_restored": after_digest == frozen_digest,
                "refusal_names_the_field": names_field,
                "PASS": bool(refused and after_digest == mutated_digest and names_field),
                "refusal_message_head": msg.splitlines()[0] if refused and msg else "",
            })

        # --- Control B-exit: refusal must exit non-zero ----------------------
        e_path = tmp / "arm_b_exit.json"
        payload = json.loads(frozen_bytes)
        payload["power_and_claim_limit"]["sample_count_per_arm"] = 99
        e_path.write_text(json.dumps(payload, indent=2) + "\n")
        code = subprocess.run(
            [sys.executable, "-c",
             "import sys,pathlib;"
             f"sys.path.insert(0, {str(REPO / 'scripts')!r});"
             f"sys.path.insert(0, {str(REPO / 'src')!r});"
             "import preregister_terminal_approach_intervention as e;"
             f"e.OUT = pathlib.Path({str(e_path)!r});"
             "raise SystemExit(e.main())"],
            capture_output=True, text=True, check=False,
        ).returncode
        controls.append({
            "control": "B_exit_status_is_non_zero",
            "expectation": (
                "a refusal that printed but exited 0 would let a caller proceed, so "
                "the status is part of the guard rather than decoration"
            ),
            "exit_code": code,
            "PASS": code != 0,
        })

        # --- Control C: the real artefact was never touched ------------------
        controls.append({
            "control": "C_real_artefact_untouched",
            "expectation": "every control ran against a temporary copy",
            "digest_before": frozen_digest,
            "digest_after": sha256_bytes(REAL.read_bytes()),
            "PASS": sha256_bytes(REAL.read_bytes()) == frozen_digest,
        })

    all_pass = all(bool(c["PASS"]) for c in controls)
    result = {
        "check": "PREREG_CANONICAL_PAYLOAD_GUARD",
        "artifact_semantics": "GUARD_VALIDATION_WITH_NEGATIVE_CONTROLS",
        "author": "Frank Asante Van Laarhoven",
        "timestamp_utc": stamp,
        "subject": {
            "emitter": "scripts/preregister_terminal_approach_intervention.py",
            "emitter_sha256": emitter.sha256(
                REPO / "scripts/preregister_terminal_approach_intervention.py"),
            "frozen_preregistration": str(REAL.relative_to(REPO)),
            "frozen_preregistration_sha256": frozen_digest,
            "prereg_version": emitter.PREREG_VERSION,
        },
        "required_behaviour": [
            "regenerate the canonical payload rather than returning the existing file",
            "preserve the original freeze timestamp",
            "compare every non-timestamp field against the frozen artefact",
            "identical -> same digest",
            "different -> refuse, do not overwrite, and require a new version",
        ],
        "defect_this_replaces": {
            "what_it_was": (
                "the first emitter preserved the timestamp but then overwrote the "
                "artefact with the regenerated payload unconditionally"
            ),
            "why_it_mattered": (
                "a changed design would have replaced a cited preregistration in "
                "place, with a changed hash as the only signal and no refusal. That "
                "is worse than returning a stale file, because the record that gets "
                "cited would quietly stop describing the frozen experiment"
            ),
            "found_by": "supervisor review before execution, not by this harness",
        },
        "controls": controls,
        "controls_total": len(controls),
        "controls_passed": sum(1 for c in controls if c["PASS"]),
        "PREREG_CANONICAL_PAYLOAD_GUARD": "PASS" if all_pass else "FAIL",
        "execution_gate": (
            "Isaac execution of TERMINAL_APPROACH_INTERVENTION_V1 may proceed"
            if all_pass else
            "STOP. Isaac execution is blocked until this guard passes"
        ),
    }

    OUT.write_text(json.dumps(result, indent=2) + "\n")
    back = json.loads(OUT.read_text())
    if "PREREG_CANONICAL_PAYLOAD_GUARD" not in back:
        raise SystemExit("evidence guard: verdict absent")
    if back["controls_total"] != len(controls):
        raise SystemExit("evidence guard: control count did not round-trip")

    for c in controls:
        print(f"  [{'PASS' if c['PASS'] else 'FAIL'}] {c['control']}")
    print()
    print(f"PREREG_CANONICAL_PAYLOAD_GUARD = {result['PREREG_CANONICAL_PAYLOAD_GUARD']}"
          f"  ({result['controls_passed']}/{result['controls_total']})")
    print(f"frozen prereg  {REAL.relative_to(REPO)}")
    print(f"prereg sha256  {frozen_digest}")
    print(f"artefact       {OUT.relative_to(REPO)}")
    print(f"sha256         {emitter.sha256(OUT)}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
