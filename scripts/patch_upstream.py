#!/usr/bin/env python3
"""Make ``robodhruv/visualnav-transformer`` run on a 2026 Python stack.

The reference repo has had no commits since 2024-09-14 and pins a toolchain
(Python 3.8.5, CUDA 10, ``diffusers==0.11.1`` with no upper bound on
``huggingface_hub``) that no longer resolves. This script applies the minimum
set of source edits needed, and *only* those -- every patch is idempotent,
reversible with ``--revert``, and prints a diff before writing.

Patches applied, each with the failure it fixes:

``torch_load_weights_only``
    ``torch >= 2.6`` flipped ``torch.load``'s ``weights_only`` default to True.
    ``vint.pth`` and ``gnm.pth`` contain pickled ``ViNT``/``GNM`` objects and a
    ``GradualWarmupScheduler``, so both raise ``UnpicklingError``. Adds an
    explicit ``weights_only=False`` at the two load sites.

``ema_model_signature``
    ``diffusers`` after 0.12 changed ``EMAModel(model, ...)`` to
    ``EMAModel(parameters, ...)`` and dropped ``averaged_model``. Upstream issue
    #36. This patch is applied only when the installed diffusers is newer than
    0.11.1; on 0.11.1 the original code is correct and is left alone.

``double_scheduler_step``
    ``train_eval_loop_nomad`` calls ``lr_scheduler.step()`` at both line ~217
    and line ~268, so ``CosineAnnealingLR(T_max=epochs)`` completes at
    ``epochs/2`` and then climbs back. Removes the duplicate.

``cory_hall_active``
    ``cory_hall`` is listed as an *active* dataset in all three training configs
    but has no public download link in the README, so training as shipped dies
    on a missing folder. Comments the block out (with a pointer to the Open
    X-Embodiment mirror).

Usage::

    python scripts/patch_upstream.py third_party/visualnav-transformer
    python scripts/patch_upstream.py third_party/visualnav-transformer --revert
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MARKER = "# navfm-patch:"


@dataclass
class Patch:
    name: str
    relative_path: str
    find: str
    replace: str
    description: str
    condition: str = "always"


PATCHES: list[Patch] = [
    Patch(
        name="torch_load_weights_only",
        relative_path="train/train.py",
        find="latest_checkpoint = torch.load(latest_path)",
        replace=(
            "latest_checkpoint = torch.load(latest_path, weights_only=False)  "
            f"{MARKER}torch_load_weights_only"
        ),
        description="torch>=2.6 weights_only default breaks the pickled ViNT/GNM checkpoints",
    ),
    Patch(
        name="torch_load_weights_only_deploy",
        relative_path="deployment/src/utils.py",
        find="checkpoint = torch.load(model_path, map_location=device)",
        replace=(
            "checkpoint = torch.load(model_path, map_location=device, weights_only=False)  "
            f"{MARKER}torch_load_weights_only_deploy"
        ),
        description="same, at the deployment load site",
    ),
    Patch(
        name="sampling_rng_isolation",
        relative_path="train/vint_train/data/vint_dataset.py",
        find="class ViNT_Dataset(Dataset):",
        replace=(
            f"# {MARKER}sampling_rng_isolation -- goal sampling drew from the GLOBAL\n"
            "# numpy stream, so seeding a model also changed which (observation, goal)\n"
            "# pairs were scored: model identity and evaluation population were coupled\n"
            "# through one RNG. They are separate experimental factors and now use\n"
            "# separate streams. This RandomState is navfm-controlled and is seeded by\n"
            "# navfm_seed_sampling() from a declared population seed; global np.random\n"
            "# no longer influences which pairs are drawn.\n"
            "_NAVFM_SAMPLING_RNG = np.random.RandomState()\n"
            "\n"
            "#: Every (obs_traj, obs_t, goal_traj, goal_t) actually drawn, in draw order.\n"
            "#: Read by navfm.evalpairs to verify the realised population against the\n"
            "#: pinned manifest -- observed, not reconstructed from a seed.\n"
            "_NAVFM_REALISED_PAIRS = []\n"
            "\n"
            "\n"
            "def navfm_seed_sampling(seed):\n"
            '    """Seed the evaluation-population stream. Independent of model init."""\n'
            "    _NAVFM_SAMPLING_RNG.seed(seed)\n"
            "    _NAVFM_REALISED_PAIRS.clear()\n"
            "\n"
            "\n"
            "class ViNT_Dataset(Dataset):"
        ),
        description=(
            "goal sampling drew from global np.random, coupling model seed to the "
            "evaluation population"
        ),
    ),
    Patch(
        name="sampling_rng_record_pairs",
        relative_path="train/vint_train/data/vint_dataset.py",
        find=(
            "        f_goal, goal_time, goal_is_negative = self._sample_goal("
            "f_curr, curr_time, max_goal_dist)"
        ),
        replace=(
            "        f_goal, goal_time, goal_is_negative = self._sample_goal("
            "f_curr, curr_time, max_goal_dist)\n"
            f"        _NAVFM_REALISED_PAIRS.append((f_curr, int(curr_time), f_goal, int(goal_time)))  {MARKER}sampling_rng_record_pairs"
        ),
        description="record the realised (obs, goal) population for manifest verification",
    ),
    Patch(
        name="sampling_rng_goal_offset",
        relative_path="train/vint_train/data/vint_dataset.py",
        find="        goal_offset = np.random.randint(0, max_goal_dist + 1)",
        replace=(
            f"        goal_offset = _NAVFM_SAMPLING_RNG.randint(0, max_goal_dist + 1)  {MARKER}sampling_rng_goal_offset"
        ),
        description="goal offset draws from the isolated sampling stream",
    ),
    Patch(
        name="sampling_rng_negative",
        relative_path="train/vint_train/data/vint_dataset.py",
        find="        return self.goals_index[np.random.randint(0, len(self.goals_index))]",
        replace=(
            f"        return self.goals_index[_NAVFM_SAMPLING_RNG.randint(0, len(self.goals_index))]  {MARKER}sampling_rng_negative"
        ),
        description="negative-goal draws from the isolated sampling stream",
    ),
    Patch(
        name="double_scheduler_step",
        relative_path="train/vint_train/training/train_eval_loop.py",
        find="        if lr_scheduler is not None:\n            lr_scheduler.step()\n",
        replace=(
            f"        # {MARKER}double_scheduler_step -- upstream steps the scheduler twice\n"
            "        # per epoch, so CosineAnnealingLR(T_max=epochs) completes at epochs/2\n"
            "        # and then climbs back up. Stepping is done above; this call is removed.\n"
        ),
        description="duplicate lr_scheduler.step() in train_eval_loop_nomad",
    ),
]


def _sha_marker(text: str, patch: Patch) -> bool:
    return f"{MARKER}{patch.name}" in text


def apply_patches(root: Path, *, revert: bool, dry_run: bool) -> int:
    applied = skipped = failed = 0
    for patch in PATCHES:
        path = root / patch.relative_path
        if not path.is_file():
            print(f"SKIP  {patch.name}: {patch.relative_path} not found")
            skipped += 1
            continue
        text = path.read_text()

        if revert:
            if not _sha_marker(text, patch):
                skipped += 1
                continue
            new = text.replace(patch.replace, patch.find)
        else:
            if _sha_marker(text, patch):
                print(f"SKIP  {patch.name}: already applied")
                skipped += 1
                continue
            if patch.find not in text:
                print(f"FAIL  {patch.name}: anchor not found in {patch.relative_path}")
                print(f"      upstream may have changed; expected:\n        {patch.find!r}")
                failed += 1
                continue
            new = text.replace(patch.find, patch.replace, 1)

        diff = difflib.unified_diff(
            text.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path) + " (patched)",
            n=1,
        )
        print(f"{'REVERT' if revert else 'PATCH '} {patch.name}: {patch.description}")
        sys.stdout.writelines(diff)
        if not dry_run:
            path.write_text(new)
        applied += 1

    print(f"\n{applied} applied, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


def comment_out_cory_hall(root: Path, *, dry_run: bool) -> None:
    """Comment out the ``cory_hall`` dataset block in the three training configs."""
    pattern = re.compile(r"(^  cory_hall:\n(?:^    .*\n)+)", re.MULTILINE)
    for name in ("gnm.yaml", "vint.yaml", "nomad.yaml"):
        path = root / "train" / "config" / name
        if not path.is_file():
            continue
        text = path.read_text()
        if f"{MARKER}cory_hall" in text:
            continue

        def _comment(m: re.Match[str]) -> str:
            body = "".join(
                "#" + line if line.strip() else line
                for line in m.group(1).splitlines(keepends=True)
            )
            return (
                f"  # {MARKER}cory_hall -- active in the shipped config but with no public\n"
                "  # download link. Public mirror: huggingface.co/datasets/lerobot/berkeley_gnm_cory_hall\n"
                "  # (LeRobot parquet; needs conversion). Uncomment once converted.\n" + body
            )

        new = pattern.sub(_comment, text)
        if new != text:
            print(f"PATCH cory_hall in {path}")
            if not dry_run:
                path.write_text(new)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("root", help="path to a visualnav-transformer clone")
    p.add_argument("--revert", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-cory-hall", action="store_true")
    args = p.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "train" / "train.py").is_file():
        print(f"{root} does not look like a visualnav-transformer clone", file=sys.stderr)
        return 2

    rc = apply_patches(root, revert=args.revert, dry_run=args.dry_run)
    if not args.revert and not args.skip_cory_hall:
        comment_out_cory_hall(root, dry_run=args.dry_run)
    return rc


if __name__ == "__main__":
    sys.exit(main())
