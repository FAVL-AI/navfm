"""Reconstruct a scene-grouped holdout for GO Stanford, deterministically.

    python scripts/make_go_stanford_split.py --zip ~/navfm-data/go_stanford/go_stanford.zip \
        --out gates/G0/splits

The frozen pre-registration requires scene-grouped holdouts and forbids
trajectory-level splits in any reported table. GO Stanford ships **no scene
field**: `traj_data.pkl` carries `position` and `yaw` and nothing else. Scene
identity therefore has to be reconstructed from the only authoritative
structure the artefact provides — the trajectory name — and named a
*reconstruction*, never "the upstream split", which finding F10 makes
unrecoverable.

**Scene key (`scene_key_v1`).** Every one of the 3696 trajectory names matches
``(no\\d+|sim\\d+)(vc|h)F?_<seq>_<sub>``. The leading location code is the scene;
the ``vc``/``h`` variant suffix and the trailing ``F`` are *not* part of it.

That last point is the one that matters. ``no2vc`` and ``no2vcF`` have
identical trajectory counts, and a key that kept the ``F`` would place them in
different groups — splitting one location across train and test, which is the
exact leakage scene-grouping exists to prevent. They are not duplicates (their
positions and yaws genuinely differ), but they are the same location, so they
are one scene.

**Stratification.** The corpus has two naming families: 27 ``no*`` scenes
(2656 trajectories) and 26 ``sim*`` scenes (1040). They are allocated
separately so the holdout carries both in proportion; an unstratified draw of
11 scenes from 53 could land entirely in one family and produce a holdout
unrepresentative of the corpus. Composition is recorded either way (F13).

**Determinism.** Allocation is by BLAKE2b of the scene id — no RNG, no
iteration order, no machine dependence. The reference `data_split.py` shuffles
unseeded (F10); this cannot.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

SCENE_KEY_VERSION = "scene_key_v1"
SCENE_RE = re.compile(r"^(?P<loc>no\d+|sim\d+)(?:vc|h)F?_")


def scene_id(trajectory: str) -> str | None:
    """The reconstructed scene for a trajectory name, or None if unparseable."""
    m = SCENE_RE.match(trajectory)
    return m.group("loc") if m else None


def family(scene: str) -> str:
    return "sim" if scene.startswith("sim") else "no"


def trajectory_names(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as z:
        names = {m.group(1) for n in z.namelist() if (m := re.match(r"^go_stanford/([^/]+)/", n))}
    return sorted(names)


def _rank(scene: str) -> str:
    return hashlib.blake2b(scene.encode(), digest_size=16).hexdigest()


def allocate(scenes: dict[str, int], test_fraction: float) -> tuple[set[str], set[str]]:
    """Assign whole scenes to test, per family, by stable hash order.

    Greedy on hash rank until the family's held-out *trajectory* share first
    reaches the target — scenes vary from 18 to 350 trajectories, so allocating
    by scene count would not produce the requested data fraction.
    """
    test: set[str] = set()
    by_family: dict[str, list[str]] = collections.defaultdict(list)
    for scene in scenes:
        by_family[family(scene)].append(scene)

    for _fam, members in sorted(by_family.items()):
        total = sum(scenes[s] for s in members)
        target = total * test_fraction
        held = 0
        for scene in sorted(members, key=_rank):
            if held >= target:
                break
            test.add(scene)
            held += scenes[scene]
    return test, set(scenes) - test


def build(zip_path: Path, test_fraction: float) -> dict[str, Any]:
    names = trajectory_names(zip_path)
    unparsed = [t for t in names if scene_id(t) is None]
    if unparsed:
        raise SystemExit(
            f"{len(unparsed)} trajectory name(s) do not match {SCENE_KEY_VERSION}: "
            f"{unparsed[:5]}. A scene key that cannot classify every trajectory "
            f"cannot ground a scene-grouped split; fix the key rather than dropping "
            f"the trajectories."
        )

    per_scene: dict[str, list[str]] = collections.defaultdict(list)
    for t in names:
        sid = scene_id(t)
        assert sid is not None
        per_scene[sid].append(t)
    counts = {s: len(v) for s, v in per_scene.items()}

    test_scenes, train_scenes = allocate(counts, test_fraction)
    train = sorted(t for s in train_scenes for t in per_scene[s])
    test = sorted(t for s in test_scenes for t in per_scene[s])

    # The proof, computed rather than asserted.
    overlap = sorted(test_scenes & train_scenes)
    train_of = {t: scene_id(t) for t in train}
    test_of = {t: scene_id(t) for t in test}
    leaked = sorted({s for s in train_of.values()} & {s for s in test_of.values()})

    return {
        # VERBATIM from the accepted external methodological review. Quoted
        # exactly; never edited within. Programme additions sit BESIDE it, in
        # the sibling fields below.
        "manifest_core_verbatim": {
            "grouping_status": (
                "Reconstructed scene grouping; no native scene identifier is present "
                "in traj_data.pkl."
            ),
            "scene_key_rule": (
                "scene_key_v1 extracts the location code matching ^(no\\d+|sim\\d+)."
            ),
            "variant_handling": (
                "Suffixes such as vc, vcF and h are excluded from scene identity.\n"
                "Trajectories sharing a location code remain in the same scene group."
            ),
            "allocation": (
                "Scene-grouped holdout, stratified across the no* and sim* naming families."
            ),
            "interpretation": (
                "The sim* prefix has no verified semantic interpretation. It is not "
                "classified as simulation data. Stratification is used only to preserve "
                "the observed family composition and make it explicit."
            ),
            "leakage_control": (
                "No scene_key_v1 value may appear in both development and holdout partitions."
            ),
        },
        "allocation_algorithm": {
            "version": "scene_order_v1",
            "ordering": "Ascending BLAKE2b(scene_key_v1)",
            "allocation": (
                "Whole reconstructed scenes allocated in deterministic order until "
                "approximately 20% of trajectories are assigned while preserving "
                "naming-family composition."
            ),
            "hash_function": "BLAKE2b",
            "digest_size_bytes": 16,
            "canonical_input": "the scene_key_v1 string, UTF-8 encoded, with no salt or prefix",
            "sort_rule": "ascending lexicographic order of the hex digest",
            "per_family_application": (
                "the 20% trajectory target is applied within each naming family "
                "independently, so both partitions retain the corpus's family composition"
            ),
            "seed": (
                "not applicable -- allocation is a deterministic function of scene_key_v1 "
                "via BLAKE2b"
            ),
        },
        "allocation_criterion": (
            "held-out trajectory share ~= 20% per naming family; scene counts are a "
            "consequence, not a target"
        ),
        "dataset": "go_stanford",
        "source_artefact": zip_path.name,
        "source_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
        "scene_key_version": SCENE_KEY_VERSION,
        "scene_key_regex": SCENE_RE.pattern,
        "scene_identity": "RECONSTRUCTED -- GO Stanford ships no scene field; "
        "traj_data.pkl carries position and yaw only",
        "allocation": "whole scenes by BLAKE2b(scene_id) rank, stratified per naming family",
        "test_fraction_requested": test_fraction,
        "n_trajectories": len(names),
        "n_scenes": len(counts),
        "inclusion_rationale": (
            "Both naming families are INCLUDED. The released checkpoint trained on the "
            "entire corpus, so the evaluation population should represent what the "
            "historical anchor's referent consumed; excluding a family would move our "
            "population further from the anchor's, not closer."
        ),
        "stratification_basis": (
            "NAMING-FAMILY COMPOSITION PRESERVATION under unresolved provenance. "
            "Allocation is stratified by the naming family of the scene key so that "
            "both partitions retain the corpus's family composition. This is NOT "
            "domain stratification, NOT balancing of any acquisition modality, and is "
            "NOT evidence that the families differ in origin. The families are "
            "orthographic categories whose meaning is undetermined -- see F-M2-3."
        ),
        "open_provenance_question": "F-M2-3 (UNVERIFIED): the reference corpus contains "
        "an undocumented second scene-naming family. Recorded so the population is "
        "described rather than assumed. Not a blocker for G0.c.",
        "scene_key_derivation": {
            "problem": "A key retaining the variant suffix yields 106 groups because "
            "no2vc and no2vcF are counted separately, which would split one location "
            "across train and test.",
            "collision_check": "All 3696 names parse; 0 unparsed; no singleton scenes.",
            "why_the_F_variant_is_the_same_scene": (
                "Paired names share suffix sets and trajectory counts exactly "
                "(no2vc/no2vcF 175/175, no5vc/no5vcF 122/122, no3vc/no3vcF 76/76). "
                "They are NOT duplicates: sampled pairs have genuinely different "
                "trajectories (no2vc_101_0 vs no2vcF_101_0, max |dpos| 37.13, "
                "max |dyaw| 50.91) and their frames are not mirrors of one another "
                "(mean abs pixel difference 64.9; horizontal-flip test negative). "
                "They are distinct traversals of one location, so they are one scene "
                "and must not be split apart."
            ),
            "why_not_scene_of": "navfm.splits.scene_of parses at recording level, "
            "which would group more finely than location and reintroduce the same leak.",
            "native_scene_field": "absent -- traj_data.pkl carries only position and yaw",
        },
        "families": {
            fam: {
                "scenes": sum(1 for s in counts if family(s) == fam),
                "trajectories": sum(v for s, v in counts.items() if family(s) == fam),
                "train_scenes": sorted(s for s in train_scenes if family(s) == fam),
                "train_trajectories": sum(counts[s] for s in train_scenes if family(s) == fam),
                "test_scenes": sorted(s for s in test_scenes if family(s) == fam),
                "test_trajectories": sum(counts[s] for s in test_scenes if family(s) == fam),
            }
            for fam in sorted({family(s) for s in counts})
        },
        "scene_inventory": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "train": {"n_scenes": len(train_scenes), "n_trajectories": len(train)},
        "test": {"n_scenes": len(test_scenes), "n_trajectories": len(test)},
        "proof_no_scene_in_both": {
            "scene_set_overlap": overlap,
            "scenes_appearing_in_both_splits": leaked,
            "holds": not overlap and not leaked,
        },
        "held_out_summary": {
            "trajectories": None,  # filled below
            "trajectory_fraction": None,
            "scenes": None,
            "scenes_by_family": None,
        },
        "train_names_sha256": hashlib.sha256("\n".join(train).encode()).hexdigest(),
        "test_names_sha256": hashlib.sha256("\n".join(test).encode()).hexdigest(),
        "_train": train,
        "_test": test,
        "_scene_of": dict(sorted({**train_of, **test_of}.items())),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--zip", required=True, help="the GO Stanford archive")
    p.add_argument("--out", required=True, help="directory for the committed split record")
    p.add_argument("--test-fraction", type=float, default=0.2)
    args = p.parse_args(argv)

    record = build(Path(args.zip), args.test_fraction)
    train, test = record.pop("_train"), record.pop("_test")
    scene_of = record.pop("_scene_of")

    record["held_out_summary"] = {
        "trajectories": len(test),
        "trajectory_fraction": round(len(test) / record["n_trajectories"], 4),
        "scenes": record["test"]["n_scenes"],
        "scenes_by_family": {fam: len(f["test_scenes"]) for fam, f in record["families"].items()},
    }

    if not record["proof_no_scene_in_both"]["holds"]:
        raise SystemExit("REFUSING to write: a scene appears in both splits")

    out = Path(args.out)
    (out / "train").mkdir(parents=True, exist_ok=True)
    (out / "test").mkdir(parents=True, exist_ok=True)
    (out / "train" / "traj_names.txt").write_text("\n".join(train) + "\n")
    (out / "test" / "traj_names.txt").write_text("\n".join(test) + "\n")
    (out / "scene_of.tsv").write_text(
        "trajectory\tscene_id\tsplit\n"
        + "".join(
            f"{t}\t{s}\t{'test' if t in set(test) else 'train'}\n" for t, s in scene_of.items()
        )
    )
    (out / "split_manifest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    print(f"scene-grouped RECONSTRUCTION written to {out}")
    print(f"  scenes {record['n_scenes']}  trajectories {record['n_trajectories']}")
    for fam, f in record["families"].items():
        pct = 100 * f["test_trajectories"] / f["trajectories"]
        print(
            f"  {fam + '*':6} {f['scenes']:3} scenes {f['trajectories']:5} trajs "
            f"-> test {len(f['test_scenes']):2} scenes {f['test_trajectories']:4} trajs ({pct:.1f}%)"
        )
    print(f"  no scene in both splits: {record['proof_no_scene_in_both']['holds']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
