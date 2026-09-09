# Supervisor questions ledger — Prof. Bo Wei

Last updated 2026-09-07 with the compatibility package
(`BO_COMPATIBILITY_PACKAGE_20260907.md`) and verified references
(`METRIC_REFERENCES_20260907.md`).

Status vocabulary: COMPLETE · PARTIAL · BLOCKED · NOT STARTED · AWAITING SUPERVISOR DECISION.

Nothing is COMPLETE because it has been discussed. COMPLETE means the evidence
exists in this repository and can be re-derived from it.

Bo's governing sequence, which overrides internal task appeal:

    existing dataset format
      -> prove our new data loads directly in GNM/ViNT/NoMaD
      -> review existing metrics with proper paper references
      -> reproduce baselines
      -> only then literature gap / novelty / fine-tuning

| ID | Question | Status | Evidence today | What is still required |
|---|---|---|---|---|
| BO-01 | Existing dataset formats, real examples, references | COMPLETE | Package §2; refs verified in `METRIC_REFERENCES_20260907.md` | — |
| BO-02 | Our dataset format | COMPLETE | Package §3; enforced in `schema.py`/`writer.py` | — |
| BO-03 | Direct GNM/ViNT/NoMaD loader compatibility | SYNTHETIC COMPLETE / REAL-TRAJECTORY OUTSTANDING | **Executed**: 4 passed, upstream `dca7981`, torch 2.11.0+cu128 | Unchanged, and now blocked behind BO-10 rather than behind Hospital specifically: no environment has yet yielded an admitted route, so no real trajectory exists to run through the three loaders. Hospital preferred; **Office/Warehouse acceptable as pipeline proof**, never relabelled as Hospital |
| BO-04 | Existing metrics + paper provenance | COMPLETE | Package §5; every source opened, method recorded per row | Collision metric definition once a comparison protocol is chosen |
| BO-05 | Explanation of the evidence/provenance layer | COMPLETE | Package §6, plain English, H7/H7R as motivation | — |
| BO-06 | Novelty vs SaferPath | DEFERRED / NOVELTY HYPOTHESIS | SaferPath verified to exist (ICRA 2026) | Systematic literature review; SaferPath collision definition not yet read |
| BO-07 | RQ1/RQ2/RQ3 ordering | AWAITING SUPERVISOR DECISION | — | Not approved; described as draft direction |
| BO-08 | Path-reference metrics (nDTW/SDTW/CLS) | BLOCKED | Ilharco et al. verified: both require a reference trajectory | Trustworthy versioned reference paths |
| BO-09 | Published-result reproduction | **COMPLETE_WITH_EVIDENCED_LIMITATIONS** | ViNT +3.61%, GNM +13.888% (both executed, exactly repeatable, controls 17-19x worse); NoMaD executed blocker at `upstream.py:218` | None. No published number was reproduced; every ceiling is inherent to the release |
| BO-10 | New collection | BLOCKED — the ROUTE GENERATOR, not the scene, is the binding constraint | Two scenes measured under the identical frozen contract, both `NO_ADMISSIBLE_ROUTE`. Hospital 96/96 evaluated, 0 passing (89 fail G10 turns, 7 fail G5); Office 96/96 evaluated, 0 passing, **all 96 on G10 turns alone** with every other threshold passing. Zero-turn candidates: Hospital 73/96, Office 84/96. `smooth_path` string-pulls routes straight wherever line of sight permits, so in open interior floor most routes are straight lines — in Office, travelled distance equals start-goal separation to four decimals. G3–G10 implemented and controlled; G7 runtime-validated PASS with all three negative controls rejected. | A NEW preregistered experiment with a route population able to produce turning routes (multi-leg / waypoint), declared before any candidate is evaluated. **Not another scene under this contract** — Warehouse is predicted to fail identically (prediction, not a result; no Warehouse candidate enumerated). Thresholds unchanged; this is a change of route population, not of the adequacy bar. Hospital and Office frozen results must not be overwritten or amended. Hospital request stays open until Hospital data exists |
| BO-11 | Fine-tuning and comparison | NOT STARTED | — | Downstream of admitted data + baseline |

## The compatibility target

Model-facing, exactly as the published framework expects:

    HospitalDataset/trajectory_0001/
        0.jpg 1.jpg ... T.jpg
        traj_data.pkl        position [T,2], yaw [T]

Sidecar, kept separate so the official loader is untouched:

    HospitalDataset_provenance/trajectory_0001/
        scene identity/digest, camera identity, controller identity,
        start pose, goal provenance, timestamps, robot identity,
        collection parameters, checksums, admission result

## What Isaac-collected new data does and does not prove

PROVES: simulator execution pipeline · new temporal RGB collection · camera
mounting and extrinsics · trajectory/pose recording · official loader
compatibility.

DOES NOT PROVE: physical-robot execution · sim-to-real transfer ·
Hospital-domain performance if collected in Office or Warehouse · deployment
safety.

## Domain rule

Hospital is the preferred domain, **not** the root dependency. If Hospital cannot
be admitted, the collection-pipeline and loader-compatibility proof is completed
in the first environment that passes the same admission criteria, and reported as:

> "The full collection and model-loading pipeline has been validated on the
> admitted <environment> while Hospital scene admission is still being resolved.
> The same frozen collection protocol will then be applied to Hospital without
> changing the loader-facing data format."

Office/Warehouse data is never relabelled as Hospital data.

## Standing corrections

- H7/H7R are **historical diagnostic recordings, not admitted training data**.
- Do not write that the published format "deliberately carries no provenance".
  Write that the loader-facing format requires numbered RGB observations plus
  `traj_data.pkl` with position `[T,2]` and yaw `[T]`, and that provenance fields
  are not required by that loader.
- Every reference in supervisor-facing material must be checked against the
  primary source first. A reference supplied in conversation is a lead.