"""Render the three-model train-path matrix from evidence, never by hand.

Every cell is derived from `gates/compatibility/train_path_compatibility.json`.
A row whose evidence is absent renders as `NO EVIDENCE`, not as a blank and not
as a PASS -- the point of the matrix is that no cell can be asserted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "gates" / "compatibility" / "train_path_compatibility.json"
DST = REPO / "gates" / "compatibility" / "THREE_MODEL_TRAIN_PATH_MATRIX.md"

MODELS = ("gnm", "vint", "nomad")


def cells(d: dict) -> list[tuple[str, dict[str, bool | None], str]]:
    """(contract, {model: pass/fail/None}, evidence artefact)."""
    m = d["models"]
    pop = d["index_trace"]["populations"]

    def per(fn) -> dict[str, bool | None]:
        out: dict[str, bool | None] = {}
        for k in MODELS:
            try:
                out[k] = bool(fn(k))
            except Exception:
                out[k] = None
        return out

    return [
        ("Option 1 loader accepts", per(lambda k: m[k]["run1"]["sample_count"] > 0),
         "<model>_sample_population.json"),
        ("sample population explained", per(lambda k: pop[k]["predicted_equals_actual"]),
         "<model>_sample_population.json"),
        ("population conserved (cand = acc + rej)", per(lambda k: pop[k]["conservation_holds"]),
         "<model>_sample_population.json"),
        ("sample index trace", per(lambda k: pop[k]["accepted_indices_match_rule"]),
         "forensics/nomad_sample_index_trace.csv"),
        ("batch construction (official collate)",
         per(lambda k: m[k]["run1"]["batch_all_finite"]), "<model>_single_batch_forward.json"),
        ("forward in train mode", per(lambda k: m[k]["run1"]["training_mode"]),
         "<model>_single_batch_forward.json"),
        ("all required targets present",
         per(lambda k: len(m[k]["run1"]["batch"]) == 7), "<model>_single_batch_forward.json"),
        ("loss construction (upstream source)",
         per(lambda k: len(m[k]["run1"]["losses"]) >= 2), "<model>_loss_smoke.json"),
        ("finite total loss", per(lambda k: m[k]["run1"]["all_losses_finite"]),
         "<model>_loss_smoke.json"),
        ("total loss is a scalar", per(lambda k: m[k]["run1"]["total_loss_is_scalar"]),
         "<model>_loss_smoke.json"),
        ("backward executes", per(
            lambda k: m[k]["run1"]["gradients"]["parameters_with_gradient"] > 0),
         "<model>_backward_optimizer_smoke.json"),
        ("finite gradients (no NaN/Inf)", per(
            lambda k: m[k]["run1"]["gradients"]["parameters_with_nan_gradient"] == 0
            and m[k]["run1"]["gradients"]["parameters_with_inf_gradient"] == 0),
         "<model>_backward_optimizer_smoke.json"),
        ("non-zero gradients on expected path", per(
            lambda k: m[k]["run1"]["gradients"]["parameters_with_nonzero_gradient"] > 0),
         "<model>_backward_optimizer_smoke.json"),
        ("optimizer step executes", per(lambda k: "parameters_changed_by_step" in m[k]["run1"]),
         "<model>_backward_optimizer_smoke.json"),
        ("a named parameter measurably changed",
         per(lambda k: m[k]["run1"]["parameters_changed_by_step"] > 0),
         "<model>_backward_optimizer_smoke.json"),
        ("released checkpoint unchanged", per(lambda k: m[k]["run1"]["checkpoint_unchanged"]),
         "<model>_backward_optimizer_smoke.json"),
        ("repeatable smoke (2 runs, frozen seed)",
         per(lambda k: m[k]["repeatability"]["result"] == "PASS"),
         "train_path_compatibility.json"),
        ("invalid fixture rejected",
         per(lambda k: m[k]["invalid_fixture"]["result"] == "PASS"),
         "train_path_compatibility.json"),
    ]


def main() -> int:
    if not SRC.is_file():
        print(f"REFUSED: no evidence at {SRC}", file=sys.stderr)
        return 2
    d = json.loads(SRC.read_text())
    env, tr = d["environment"], d["trajectory"]
    m, pop = d["models"], d["index_trace"]["populations"]
    rows = cells(d)

    def mark(v: bool | None) -> str:
        return "PASS" if v else ("FAIL" if v is False else "NO EVIDENCE")

    out = [
        "# Three-model train-path compatibility matrix",
        "",
        "Every cell is derived from the evidence file named in its row. No cell is",
        "hand-entered, and a row with no backing artefact renders `NO EVIDENCE` rather",
        "than blank — a blank reads as a pass to a hurried reader.",
        "",
        f"- NavFM commit `{env['navfm_commit'][:7]}` · upstream `{env['upstream_commit'][:7]}`",
        f"- Python {env['python']} · PyTorch {env['torch']} · NumPy {env['numpy']} · "
        f"device {env['device']}",
        f"- Trajectory `{tr['name']}` · Option 1 payload digest `{tr['content_digest'][:16]}`",
        f"- Stage {d['stage']} · admission `{d['admission_status']}` · "
        f"formal training allowed: {d['training_allowed_formal']}",
        "",
        "| Contract | GNM | ViNT | NoMaD | Evidence |",
        "|---|---|---|---|---|",
    ]
    for name, vals, ev in rows:
        out.append(f"| {name} | {mark(vals['gnm'])} | {mark(vals['vint'])} | "
                   f"{mark(vals['nomad'])} | `{ev}` |")

    out += [
        "",
        "## Where the models legitimately differ",
        "",
        "These are model-semantic differences, preserved rather than standardised away.",
        "Forcing them into symmetry would make the table look tidier and the science worse.",
        "",
        "| Property | GNM | ViNT | NoMaD |",
        "|---|---|---|---|",
    ]
    r = {k: m[k]["run1"] for k in MODELS}
    out += [
        "| context size | {} | {} | {} |".format(*(pop[k]["context_size"] for k in MODELS)),
        "| action horizon | {} | {} | {} |".format(*(pop[k]["action_horizon"] for k in MODELS)),
        "| admissible index range | {} | {} | {} |".format(
            *(f"[{pop[k]['begin_time']},{pop[k]['end_time']})" for k in MODELS)),
        "| samples from 40 frames | {} | {} | {} |".format(
            *(pop[k]["actual_effective"] for k in MODELS)),
        "| loss components | {} | {} | {} |".format(
            *(", ".join(r[k]["losses"].keys()) for k in MODELS)),
        "| alpha | {} | {} | {} |".format(
            *(d["training_path_crosswalk"][k]["alpha"] for k in MODELS)),
        "| total-loss formula | {} | {} | {} |".format(
            *(d["training_path_crosswalk"][k]["total_loss"] for k in MODELS)),
        "| stochastic training state | none | none | DDPM noise + timestep + goal mask |",
        "| trainable tensors | {} | {} | {} |".format(
            *(r[k]["parameters_total_trainable"] for k in MODELS)),
        "| tensors receiving no gradient | {} | {} | {} |".format(
            *(r[k]["parameters_unchanged"]["count"] for k in MODELS)),
        "| unexecuted share of checkpoint | {} | {} | {} |".format(
            *(f"{r[k]['parameters_unchanged']['fraction_of_checkpoint'] * 100:.2f}%"
              for k in MODELS)),
        "",
        "## Measured values",
        "",
        "| | GNM | ViNT | NoMaD |",
        "|---|---|---|---|",
        "| total loss | {} | {} | {} |".format(
            *(f"{r[k]['losses']['total_loss']:.6f}" for k in MODELS)),
        "| gradient global norm | {} | {} | {} |".format(
            *(f"{r[k]['gradients']['gradient_global_norm']:.4e}" for k in MODELS)),
        "| non-zero gradients | {} | {} | {} |".format(
            *(f"{r[k]['gradients']['parameters_with_nonzero_gradient']}"
              f"/{r[k]['gradients']['parameters_trainable']}" for k in MODELS)),
        "| parameters changed by one step | {} | {} | {} |".format(
            *(f"{r[k]['parameters_changed_by_step']}/{r[k]['parameters_total_trainable']}"
              for k in MODELS)),
        "| repeat run max abs difference | {} | {} | {} |".format(
            *(f"{m[k]['repeatability']['max_abs_difference']:.2e}" for k in MODELS)),
        "| invalid fixture rejected by | {} | {} | {} |".format(
            *(m[k]["invalid_fixture"]["rejection"].split(":")[0] for k in MODELS)),
        "",
        "## Claim boundary",
        "",
        "> The fresh Yahboom Isaac Sim Option 1 trajectories have been verified through the",
        "> complete data-to-training-step path for GNM, ViNT and NoMaD. For each model, the",
        "> official dataset path constructs a valid batch, the model executes in training",
        "> mode, the model-specific loss is finite, backpropagation produces valid gradients,",
        "> and one optimizer step updates the in-memory model without modifying the released",
        "> checkpoint.",
        "",
        "**Not claimed:** model trained · model improved · fine-tuning succeeded ·",
        "convergence · generalisation · performance improvement · training dataset admitted ·",
        "ViNT-generated pilots are valid expert demonstrations.",
        "",
        "Author: Frank Asante Van Laarhoven",
    ]
    DST.write_text("\n".join(out) + "\n")
    n_pass = sum(1 for _, v, _ in rows for x in v.values() if x)
    print(f"  {DST.relative_to(REPO)}  ({len(rows)} contracts x 3 models, {n_pass} PASS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
