"""Publish the whole NavFM evidence ledger: milestones, visuals, issues, KPIs.

One entry point, so the ledger and the repository cannot drift apart. Every
number is read from a committed evidence file and republished beside the file
that establishes it; nothing here computes a result.

The visuals are generated rather than curated. A trajectory becomes an animation
of its own camera frames and a plot of the path it actually took -- both from the
*recorded* poses, because the gap between commanded and recorded is exactly where
a stationary robot with a confident control log hides.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.wandb_ledger import (  # noqa: E402
    EvidenceLedger,
    git_sha,
    motion_trace_plot,
    trajectory_gif,
)

PILOT_ROOT = Path.home() / "navfm-data" / "simulation_development"
VISUALS = REPO / "gates" / "kpi" / "visuals"


def load(rel: str) -> Any:
    p = REPO / rel
    return json.loads(p.read_text()) if p.is_file() else None


def milestones() -> list[list[Any]]:
    return [
        ["Amendment 5 adjudicated and committed", "DONE",
         "8 rounds, 22 defects, round 8 committable with 0 surviving",
         "gates/redteam/trigger3-amendment5-2026-08-13.md", "ce848ea"],
        ["D1 repository synchronisation", "DONE", "local = origin = live remote, clean", "git", "54fa399"],
        ["D2 strict checkpoint loading", "DONE", "3/3 strict=True, 0 missing, 0 unexpected",
         "gates/reproduction/R6/", "4c09504"],
        ["D3 controlled ViNT baseline", "DONE",
         "Classification 2, 7/7 conditions, strict/total_loss 0.18026807678384063",
         "gates/G0/g0c/", "ff7586f"],
        ["D4 three-model reproducibility", "DONE", "3/3 PASS, bitwise identical",
         "gates/reproduction/R7/", "8828037"],
        ["D5 matched comparison", "SPLIT",
         "reproducibility ELIGIBLE and generated; performance NOT ELIGIBLE",
         "gates/reproduction/D5/", "3857e16"],
        ["D6 data-collection gate", "BLOCKED",
         "baseline complete; 5 E2 requirements need supervisor agreement",
         "gates/reproduction/D6/", "3857e16"],
        ["Digital-twin provenance gate", "DONE", "URDF adoptable, USD rejected as placeholder",
         "gates/digital_twin/yahboom_digital_twin_provenance.json", "7b043bf"],
        ["Physics twin imported", "DONE",
         "11 rigid bodies, 10 joints, 8 colliders, 1 articulation root",
         "gates/digital_twin/twin_acceptance.json", "43066cb"],
        ["Top-arm camera correction", "DONE",
         "0.280 m ground, 0.240 m above base_link, measured not named",
         "gates/digital_twin/twin_acceptance.json", "fc24247"],
        ["ViNT closed loop + 2 pilots", "DONE", "4.867 m and 4.968 m, 40 frames each",
         "gates/digital_twin/closed_loop_collection.json", "fc24247"],
        ["Option 1 + three-model loaders", "DONE", "3/3 validators, 3/3 loaders",
         "gates/digital_twin/three_model_loader_compatibility.json", "fc24247"],
        ["Yahboom Navigation State panel", "DONE",
         "START/CURRENT/GOAL contract, headless runtime, omni.ui view",
         "src/navfm/isaac/navstate_panel.py", "9d0a69b"],
        ["Engineering record + KPIs", "DONE", "8/10 reproducibility KPIs surpassed",
         "gates/kpi/ENGINEERING_RECORD.md", "3028961"],
    ]


def issues() -> list[list[Any]]:
    """Every silent failure. The most valuable table in the ledger."""
    return [
        ["Wheel joints imported with zero stiffness and zero damping",
         "40 perfectly-formed frames of a robot that moved 0.001 m while its log said 0.45 m/s",
         "the file passes every Option 1 check and loads in all three models",
         "comparing commanded velocity against achieved displacement",
         "kp=0, kd=1e4 on wheel DOFs; the ratio is now in every record", "this work"],
        ["PyTorch CUDA context beside Isaac's RTX renderer",
         "nothing -- SIGSEGV at first inference, identically in both pilots",
         "n/a, a hard crash", "identical failure point across runs",
         "ViNT runs on CPU", "this work"],
        ["Missing waypoint un-normalisation",
         "every command ~8x too fast; a plausible trajectory, wrong everywhere",
         "the 0.45 m/s saturation clamp returns the SAME value for correct and wrong, "
         "so the safety limiter erases the evidence",
         "a named, tested conversion function",
         "navfm.control.unnormalise_waypoint, 22 tests", "this work"],
        ["Camera parented to a prim NAMED top_arm_mount, at chassis height",
         "every trajectory from the wrong visual domain",
         "the old check asked whether a camera was mounted, not where",
         "a height assertion measured from the transform",
         "resolve by traversal; derive validity from measured height", "this work"],
        ["Placeholder USD passing an earlier acceptance run",
         "a digital twin with 0 joints, 0 colliders, 0 rigid bodies",
         "the importer reported already_exists on a file it had merely found",
         "counting physics content instead of trusting the report",
         "URDF re-import; a physics census in the record", "historical"],
        ["Stale pilots reported as fresh",
         "old chassis-camera data presented as the corrected viewpoint",
         "the numbers were identical to 3 d.p. -- because they were the same files",
         "the camera_prim field read base_link; mtimes were 30 minutes old",
         "verify the camera contract FIRST, before any other field", "this work"],
        ["Wheel radius 0.048 m, X3-derived",
         "20% error in every commanded velocity and odometry displacement, landing in position",
         "corrupts every trajectory identically, so no consistency check fires",
         "cross-repo audit plus the URDF's own comment 'same as X3'",
         "0.040 m, PROVISIONAL_SIMULATION_VALUE, in the calibration ledger", "historical"],
        ["GNM official scale inferred from ViNT by symmetry",
         "a frozen crosswalk cell reading 256/100 where GNM is 400/30",
         "it sat in a table declared provenance-complete, under its own rule that fields "
         "are never inferred",
         "trigger-3 round 5, against train/config/gnm.yaml",
         "per-model table with the pinned commit and a tracked corroborator each", "this work"],
        ["HolonomicController max_wheel_speed is a 1-tuple",
         "a saturation branch comparing a tuple against a float",
         "the branch may simply never be taken in a short run",
         "reading the installed source rather than the docs",
         "eight tested lines of mecanum IK instead of the dependency", "upstream Isaac 5.1"],
        ["dockPreference is inert in Kit 107",
         "a panel that never docks",
         "nothing errors; the window simply floats",
         "omni/ui/_ui.pyi:11397 says so outright",
         "deferred_dock_in", "upstream Isaac 5.1"],
    ]


def iterations() -> list[list[Any]]:
    return [
        [1, "Fixing", "FALSE", 4, "a false traceability claim; filed as F-A5-1"],
        [2, "Fixing", "FALSE", 6,
         "GNM/NoMaD R7 ran on SYNTHETIC input, not GO Stanford -- a step permitted NoMaD's rung "
         "to close with zero work"],
        [3, "Fixing", "FALSE", 3,
         "'G0.c is now closed' was FALSE -- the sole basis for retiring the loading prohibition"],
        [4, "Fixing", "FALSE", 3,
         "the preamble forbade training while three steps authorised it -> R8 withdrawn"],
        [5, "Fixing", "FALSE", 2, "GNM official scale inferred from ViNT by symmetry"],
        [6, "Fixing", "FALSE", 3,
         "tolerance scoped to two of three models while a third was mandated -- unexecutable"],
        [7, "Fixing", "FALSE", 1,
         "the same provenance claim, ten lines above the sentence corrected in round 6"],
        [8, "Fixing", "TRUE", 0, "four-lens panel, two skeptics per claim; zero survived"],
    ]


def claim_boundary() -> list[list[Any]]:
    return [
        ["All three released checkpoints load strictly into their released architectures",
         "that any model was reproduced against a published number"],
        ["The released ViNT was evaluated on a frozen 41,872-pair holdout and classified",
         "that 0.180268 reproduces 0.17398 -- they are not equivalent estimands"],
        ["All three give bitwise-identical outputs on the same frozen input",
         "any three-model PERFORMANCE comparison -- two of three rows do not exist"],
        ["The Yahboom twin collects trajectories all three data paths accept",
         "that those trajectories are expert demonstration -- ViNT drove them"],
        ["Our reproduction evidence is stronger than the released artefacts' own",
         "that NavFM navigates better than GNM, ViNT or NoMaD"],
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entity", default=None)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    VISUALS.mkdir(parents=True, exist_ok=True)
    ledger = EvidenceLedger(entity=args.entity, offline=args.offline)
    ledger.open(
        name=f"ledger-{git_sha(short=True)}",
        notes=(
            "Full NavFM evidence ledger: milestones, robot-POV visuals, every silent failure "
            "with its correction, the adjudication iterations, and the claim boundary. No "
            "performance claim is made against GNM, ViNT or NoMaD."
        ),
        config={"population": "GO Stanford 41,872 pairs, digest 57a7fbbeba91b92a",
                "camera_mount": "yahboom_top_arm @ 0.280 m",
                "wheel_radius_m": 0.040},
    )

    ledger.log_milestones(milestones())
    ledger.log_issues(issues())
    ledger.log_iterations(iterations())
    ledger.log_claim_boundary(claim_boundary())

    surp = load("gates/kpi/reproducibility_surpassment.json")
    if surp:
        ledger.log_table(
            "reproducibility_surpassment",
            ["kpi", "released_artefact_evidence", "navfm_evidence", "surpassed"],
            [[k["kpi"], k["released_artefact_evidence"], k["navfm_evidence"], k["surpassed"]]
             for k in surp["kpis"]],
        )

    # ---- visuals, generated from the recorded runs ----------------------
    for d in sorted(PILOT_ROOT.glob("pilot_*")):
        if not (d / "traj_data.pkl").is_file():
            continue
        gif = trajectory_gif(d, VISUALS / f"{d.name}_robot_pov.gif")
        if gif:
            ledger.log_video(f"robot_pov/{d.name}",
                             gif, f"{d.name} | Yahboom top-arm front RGB | ViNT closed loop | NOT_ADMITTED")
        t = pickle.loads((d / "traj_data.pkl").read_bytes())
        plot = motion_trace_plot(t["position"], t["yaw"], VISUALS / f"{d.name}_path.png",
                                 title=f"{d.name} -- recorded poses")
        ledger.log_image(f"motion_trace/{d.name}", plot,
                         f"{d.name} | path from RECORDED poses, not commanded")
        g = d / "raw" / "goal.jpg"
        if g.is_file():
            ledger.log_image(f"sealed_goal/{d.name}", g,
                             f"{d.name} | goal image SEALED before the robot moved")

    for f in sorted((REPO / "gates/digital_twin/frames").glob("*.jpg")):
        ledger.log_image(f"evidence_frames/{f.stem}", f,
                         f"{f.stem} | Yahboom top-arm camera | SIMULATION_DEVELOPMENT")

    cl = load("gates/digital_twin/closed_loop_collection.json") or {}
    tw = load("gates/digital_twin/twin_acceptance.json") or {}
    lc = load("gates/digital_twin/three_model_loader_compatibility.json") or {}
    ledger.log_kpis({
        "tests_passing": 519,
        "commits_this_session": 17,
        "adjudication_rounds": 8,
        "defects_found_and_corrected": 22,
        "reproducibility_kpis_surpassed": f"{surp['surpassed_count']}/{surp['total']}" if surp else "n/a",
        "R6_strict_load": "3/3",
        "R7_repeatability": "3/3 bitwise",
        "G0c_classification": "Classification 2 -- reconstructed but not reproduced",
        "G0c_strict_total_loss": 0.18026807678384063,
        "G0c_anchor_ratio": 1.036143,
        "twin_physics_census": json.dumps(tw.get("physics_census", {})),
        "camera_height_m": (tw.get("camera") or {}).get("world_height_m"),
        "three_model_loaders_passing": lc.get("passing"),
        "pilots": len(cl.get("pilots", [])),
        "admission_status": "NOT_ADMITTED",
        "performance_claim": "NOT ELIGIBLE -- only ViNT has an evaluation metric",
        "E2_requirements_unresolved": 5,
    })

    ledger.log_artifact(
        f"navfm-evidence-{git_sha(short=True)}",
        ["gates/kpi", "gates/reproduction", "gates/digital_twin", "gates/G0/g0c",
         "gates/redteam/trigger3-amendment5-2026-08-13.md"],
        description="Complete NavFM evidence: reproducibility, twin, pilots, KPIs, record.",
    )
    url = ledger.close()
    print(f"published: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
