"""R6 -- explicit strict checkpoint load, for every model the crosswalk marks DELTA.

PREREGISTRATION.md Amendment 5, execution-order step 1:

    For each model whose R6 row is `DELTA`, instantiate the frozen architecture
    and perform an explicit strict checkpoint load, producing a durable
    machine-readable record containing checkpoint digest, parameter/tensor
    counts, missing keys and unexpected keys. Models whose R6 row is `REUSE`
    are not rerun.

Why this rung is a DELTA rather than a reuse of the July evidence. The historical
records report 0 missing and 0 unexpected keys for all three models -- but every
one of those loads was performed with ``strict=False``
(``scripts/02_verify_checkpoints.py:168`` and ``scripts/15_reproduction_gate.py:319``
in the FAVL-AI/visualnav-transformer lineage). Under ``strict=False`` those counts
are a *report*, not an *assertion*: the call cannot fail, so nothing in those runs
would have behaved differently had the counts been non-zero. R6 requires the
assertion. This script therefore performs both loads and records them separately
-- the enumerating load, which says what did not match, and the strict load,
which is the claim.

Three rules inherited from recorded failures:

* It never infers execution state (F-M1-1). No interpreter discovery, no
  dependency installation, no path guessing. It preflights, refuses, and names
  the missing requirement.
* It refuses to run until Amendment 5 is committed, because Amendment 5 is what
  authorises loading a released checkpoint -- and only for R6. A gate that can be
  satisfied before the amendment authorising it exists is not a gate.
* The DELTA set is *derived* from the committed crosswalk, never assumed. Passing
  ``--model`` for a row the crosswalk marks REUSE is refused.

**The environment constraint, and why NoMaD is handled separately.** The G0.c
evaluation declaration pins an environment identity, and the protocol freeze audit
recomputes it at gate time and FAILS on mismatch. That identity includes the
installed-distribution digest, so installing a package into the canonical
environment would break G0.c. NoMaD's architecture needs ``diffusion_policy``,
which is vendored at ``third_party/diffusion_policy`` but whose own import needs
``einops``. This script therefore never installs anything: it adds the vendored
clone to ``sys.path``, accepts additional read-only search paths via
``--extra-syspath`` for dependencies staged outside the environment, and records
the resulting environment identity in every record so a reader can see exactly
which environment produced which row.

No inference is run. No frozen input batch is required and none is used; no
numerical tolerance is declared or applied. Both are R7 requirements, and adding
them here would import a requirement the preregistration did not make of R6.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PROTOCOL = "PREREGISTRATION.md"

#: Crosswalk rows look like:  | ViNT R6 | **DELTA** | ... |
_R6_ROW = re.compile(
    r"^\|\s*(?P<model>GNM|ViNT|NoMaD)\s+R6\s*\|\s*\**(?P<disposition>[A-Z ]+?)\**\s*\|",
    re.MULTILINE,
)

#: Checkpoints that pickle live Python objects. Loading these executes code from
#: the file, so the trust flag is explicit per model rather than global.
_PICKLED = {"vint", "gnm"}


class PreflightError(RuntimeError):
    """A requirement for running R6 is absent. Named, never worked around."""


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise PreflightError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def committed_protocol() -> str:
    """The protocol as committed at HEAD -- never the working copy.

    An uncommitted amendment authorises nothing. Reading the worktree here would
    let an unadjudicated edit unlock the gate it is supposed to pass through.
    """
    return _git("show", f"HEAD:{PROTOCOL}")


def r6_dispositions(protocol_text: str) -> dict[str, str]:
    """Every R6 disposition, derived from the committed crosswalk."""
    rows = {
        m.group("model").lower(): m.group("disposition").strip()
        for m in _R6_ROW.finditer(protocol_text)
    }
    if not rows:
        raise PreflightError(
            f"no R6 crosswalk rows found in the committed {PROTOCOL}. Amendment 5 "
            "defines the R6 dispositions; if it is not committed, R6 is not authorised."
        )
    return rows


def stage_syspath(extra: list[str]) -> list[str]:
    """Add read-only search paths. Never installs; never writes."""
    added: list[str] = []
    for candidate in [str(REPO / "third_party" / "diffusion_policy"), *extra]:
        path = Path(candidate)
        if not path.is_dir():
            raise PreflightError(f"search path {candidate} is not a directory")
        resolved = str(path.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
            added.append(resolved)
    return added


def preflight(models: list[str], extra_syspath: list[str]) -> dict[str, Any]:
    """Refuse, with the missing requirement named, rather than proceeding weakly."""
    protocol = committed_protocol()
    if "## Amendment 5" not in protocol:
        raise PreflightError(
            f"the committed {PROTOCOL} at HEAD carries no Amendment 5. Amendment 5 is "
            "what authorises loading a released checkpoint, and only for R6; until it "
            "is adjudicated under trigger-3 and committed, loading is not authorised. "
            "Refusing."
        )

    dispositions = r6_dispositions(protocol)
    for model in models:
        if model not in dispositions:
            raise PreflightError(
                f"{model!r} has no R6 row in the committed crosswalk; "
                f"rows present: {sorted(dispositions)}"
            )
        if dispositions[model] != "DELTA":
            raise PreflightError(
                f"{model!r} R6 is {dispositions[model]}, not DELTA. The execution order "
                "permits only DELTA and RERUN work; REUSE evidence is adopted by "
                "reference and must not be rerun for symmetry. Refusing."
            )

    added = stage_syspath(extra_syspath) if "nomad" in models else []

    required = [
        ("torch", "the canonical environment is not active"),
        ("navfm", "pip install -e . in the canonical environment"),
        ("vint_train", "pip install -e third_party/visualnav-transformer/train"),
    ]
    if "nomad" in models:
        required += [
            (
                "einops",
                "NoMaD's vendored diffusion_policy needs einops. Do NOT install it into "
                "the canonical environment: the G0.c declaration pins an environment "
                "identity that includes the installed-distribution digest, and the "
                "protocol freeze audit fails on mismatch. Stage it outside the "
                "environment instead, e.g. "
                "`pip install --target /tmp/navfm-r6-deps einops` and pass "
                "`--extra-syspath /tmp/navfm-r6-deps`",
            ),
            (
                "diffusion_policy",
                "expected vendored at third_party/diffusion_policy",
            ),
        ]
    for module, hint in required:
        try:
            __import__(module)
        except ImportError as exc:
            raise PreflightError(f"cannot import {module!r}: {hint} ({exc})") from exc

    return {
        "r6_dispositions": dispositions,
        "protocol_source": f"HEAD:{PROTOCOL}",
        "syspath_additions": added,
    }


def recorded_digest(model: str) -> str:
    """The digest this project froze, from the tracked record.

    ``gates/G0/SHA256SUMS`` is tracked; ``checkpoints/SHA256SUMS`` is an ignored
    working copy with identical checkpoint lines. The tracked one is the record.
    """
    sums = _git("show", "HEAD:gates/G0/SHA256SUMS")
    for line in sums.splitlines():
        if line.strip().endswith(f"./{model}.pth"):
            return line.split()[0]
    raise PreflightError(f"no recorded digest for {model}.pth in gates/G0/SHA256SUMS")


def build_architecture(model: str) -> Any:
    """Instantiate the frozen architecture exactly as the reference builds it."""
    from navfm import upstream

    if model in ("vint", "gnm"):
        return upstream.build_model(model)
    if model == "nomad":
        return _build_nomad(upstream.model_config("nomad"))
    raise PreflightError(f"no frozen architecture wired for {model!r}")


def _build_nomad(cfg: dict[str, Any]) -> Any:
    """NoMaD's architecture, for checkpoint loading only.

    Copied from the reference ``train.py`` construction block, not inferred from
    class signatures -- the two differ, and the state-dict keys follow the
    construction, not the defaults. ``replace_bn_with_gn`` is part of the
    architecture: skipping it renames every normalisation buffer and the strict
    load would fail for a reason that has nothing to do with the checkpoint.

    This deliberately does NOT provide the diffusion sampling path. R6 asks
    whether the released weights load into the released architecture; it does not
    ask the model to produce anything. ``upstream.build_model`` continues to
    refuse ``nomad`` so that no evaluation path acquires one by accident, and
    Amendment 5 forbids porting the sampling implementation for symmetry.
    """
    from diffusion_policy.model.diffusion.conditional_unet1d import ConditionalUnet1D
    from vint_train.models.nomad.nomad import DenseNetwork, NoMaD
    from vint_train.models.nomad.nomad_vint import NoMaD_ViNT, replace_bn_with_gn

    if cfg["vision_encoder"] != "nomad_vint":
        raise PreflightError(
            f"released NoMaD uses vision_encoder 'nomad_vint'; config says "
            f"{cfg['vision_encoder']!r}. Refusing rather than substituting one."
        )
    vision_encoder = replace_bn_with_gn(
        NoMaD_ViNT(
            obs_encoding_size=cfg["encoding_size"],
            context_size=cfg["context_size"],
            mha_num_attention_heads=cfg["mha_num_attention_heads"],
            mha_num_attention_layers=cfg["mha_num_attention_layers"],
            mha_ff_dim_factor=cfg["mha_ff_dim_factor"],
        )
    )
    return NoMaD(
        vision_encoder=vision_encoder,
        noise_pred_net=ConditionalUnet1D(
            input_dim=2,
            global_cond_dim=cfg["encoding_size"],
            down_dims=cfg["down_dims"],
            cond_predict_scale=cfg["cond_predict_scale"],
        ),
        dist_pred_net=DenseNetwork(embedding_dim=cfg["encoding_size"]),
    )


def finite_census(model: Any) -> dict[str, Any]:
    """Every floating value in the loaded model is an ordinary number, or it is not.

    Integer buffers (``num_batches_tracked``) are excluded rather than silently
    passed: ``isfinite`` is meaningless for them, and counting them as "checked"
    would inflate the census with values the check never examined.
    """
    import torch

    checked = skipped = 0
    offenders: list[str] = []
    for name, tensor in model.state_dict().items():
        if not torch.is_floating_point(tensor):
            skipped += 1
            continue
        checked += 1
        if not bool(torch.isfinite(tensor).all()):
            offenders.append(name)
    return {
        "tensors_checked": checked,
        "tensors_skipped_non_float": skipped,
        "non_finite_tensors": offenders,
        "all_finite": not offenders,
    }


def verify_one(model_name: str, ckpt: Path) -> dict[str, Any]:
    import torch

    from navfm import upstream
    from navfm.models.loader import (
        count_parameters,
        extract_state_dict,
        load_checkpoint,
        sha256,
    )

    record: dict[str, Any] = {
        "rung": "R6",
        "model": model_name,
        "checkpoint_path": str(ckpt.relative_to(REPO)),
    }

    # B -- digest, before anything is loaded from the file.
    digest = sha256(ckpt)
    expected = recorded_digest(model_name)
    record["checkpoint_sha256"] = digest
    record["checkpoint_sha256_recorded"] = expected
    record["checkpoint_digest_matches"] = digest == expected
    record["checkpoint_bytes"] = ckpt.stat().st_size
    if digest != expected:
        raise PreflightError(
            f"{model_name}: checkpoint digest {digest[:16]} does not match the recorded "
            f"{expected[:16]}. This is not the artefact the project froze. Refusing."
        )

    # A -- frozen architecture.
    model = build_architecture(model_name)
    record["architecture_config"] = dict(upstream.model_config(model_name))

    # C, D -- counts.
    record["parameters"] = count_parameters(model)
    record["model_tensors"] = len(model.state_dict())

    state = extract_state_dict(
        load_checkpoint(ckpt, trust_checkpoint=model_name in _PICKLED, expected_sha256=expected)
    )
    record["checkpoint_tensors"] = len(state)

    # F, G -- enumerate first: strict=True raises, and would report only the first
    # mismatch it happened to encounter.
    enumerating = model.load_state_dict(state, strict=False)
    missing = list(enumerating.missing_keys)
    unexpected = list(enumerating.unexpected_keys)
    record["missing_keys"] = missing
    record["unexpected_keys"] = unexpected
    record["missing_key_count"] = len(missing)
    record["unexpected_key_count"] = len(unexpected)

    # E -- the assertion R6 actually requires, and the whole reason this rung is a
    # DELTA rather than a REUSE of the July evidence.
    try:
        model.load_state_dict(state, strict=True)
        record["strict_load"] = True
        record["strict_load_error"] = None
    except RuntimeError as exc:
        record["strict_load"] = False
        record["strict_load_error"] = str(exc)

    # H -- finite values.
    record["finite_check"] = finite_census(model)

    # I, J -- evaluation mode, then confirm it took effect on every submodule.
    model.eval()
    still_training = [n or "<root>" for n, m in model.named_modules() if m.training]
    record["evaluation_mode"] = {
        "eval_called": True,
        "root_training_flag": bool(model.training),
        "submodules_still_training": still_training,
        "verified": not model.training and not still_training,
    }

    record["torch_version"] = torch.__version__
    record["result"] = (
        "PASS"
        if record["strict_load"]
        and record["finite_check"]["all_finite"]
        and record["evaluation_mode"]["verified"]
        and record["checkpoint_digest_matches"]
        else "FAIL"
    )
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python scripts/verify_r6_strict_load.py",
        description="R6 explicit strict checkpoint load for the crosswalk's DELTA models.",
    )
    ap.add_argument("--model", action="append", required=True, choices=["vint", "gnm", "nomad"])
    ap.add_argument("--checkpoint-dir", default=str(REPO / "checkpoints"))
    ap.add_argument("--out-dir", required=True, help="where machine-readable records are written")
    ap.add_argument(
        "--extra-syspath",
        action="append",
        default=[],
        help="read-only search path for dependencies staged OUTSIDE the canonical "
        "environment (never installed into it, so the G0.c environment identity holds)",
    )
    args = ap.parse_args(argv)

    try:
        context = preflight(args.model, args.extra_syspath)
    except PreflightError as exc:
        print(f"R6 PREFLIGHT REFUSED: {exc}", file=sys.stderr)
        return 2

    from navfm.provenance import environment_identity

    identity = environment_identity(REPO)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_dir = Path(args.checkpoint_dir)

    common = {
        "git_sha": _git("rev-parse", "HEAD"),
        "git_worktree_clean": _git("status", "--porcelain") == "",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "command": "python " + " ".join(sys.argv),
        "environment_id": identity.environment_id,
        "protocol_source": context["protocol_source"],
        "r6_dispositions": context["r6_dispositions"],
        "syspath_additions": context["syspath_additions"],
        "inference_run": False,
        "frozen_input_batch_used": False,
        "tolerance_declared": False,
        "claim_boundary": (
            "R6 only: the released weights load strictly into the released architecture. "
            "This establishes neither deterministic inference (R7) nor any published "
            "result, and produces no G0.c metric."
        ),
    }

    records = []
    try:
        for model_name in args.model:
            ckpt = ckpt_dir / f"{model_name}.pth"
            if not ckpt.is_file():
                print(f"R6 REFUSED: {ckpt} is absent", file=sys.stderr)
                return 2
            record = {**common, **verify_one(model_name, ckpt)}
            (out_dir / f"{model_name}_r6.json").write_text(json.dumps(record, indent=2) + "\n")
            records.append(record)
    except PreflightError as exc:
        print(f"R6 REFUSED: {exc}", file=sys.stderr)
        return 2

    width = max(len(r["model"]) for r in records)
    print("R6 -- EXPLICIT STRICT CHECKPOINT LOAD")
    print("=" * 37)
    print(f"environment_id : {identity.environment_id}")
    if common["syspath_additions"]:
        print(f"syspath added  : {common['syspath_additions']}")
    print()
    for r in records:
        print(
            f"  {r['model']:<{width}}  {r['result']:<4}  "
            f"strict={r['strict_load']!s:<5} "
            f"tensors={r['model_tensors']:<4} "
            f"params={r['parameters']['total']:>11,} "
            f"missing={r['missing_key_count']:<3} "
            f"unexpected={r['unexpected_key_count']:<3} "
            f"finite={r['finite_check']['all_finite']!s:<5} "
            f"eval={r['evaluation_mode']['verified']}"
        )
    failed = [r["model"] for r in records if r["result"] != "PASS"]
    print()
    print(f"records written to {out_dir}")
    print("RESULT  : " + ("PASS" if not failed else f"FAIL ({', '.join(failed)})"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
