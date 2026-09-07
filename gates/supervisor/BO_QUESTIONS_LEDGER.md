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
| BO-03 | Direct GNM/ViNT/NoMaD loader compatibility | SYNTHETIC_COMPATIBILITY_COMPLETE / HOSPITAL_COMPATIBILITY_BLOCKED_ON_ADMITTED_TRAJECTORY | **Executed**: 4 passed, `.venv-train` py3.11.15 torch 2.11.0+cu128, upstream `dca7981` | Same chain on a newly admitted Hospital trajectory |
| BO-04 | Existing metrics + paper provenance | COMPLETE | Package §5; every source opened, method recorded per row | Collision metric definition once a comparison protocol is chosen |
| BO-05 | Explanation of the evidence/provenance layer | COMPLETE | Package §6, plain English, H7/H7R as motivation | — |
| BO-06 | Novelty vs SaferPath | DEFERRED / NOVELTY HYPOTHESIS | SaferPath verified to exist (ICRA 2026) | Systematic literature review; SaferPath collision definition not yet read |
| BO-07 | RQ1/RQ2/RQ3 ordering | AWAITING SUPERVISOR DECISION | — | Not approved; described as draft direction |
| BO-08 | Path-reference metrics (nDTW/SDTW/CLS) | BLOCKED | Ilharco et al. verified: both require a reference trajectory | Trustworthy versioned reference paths |
| BO-09 | Baseline reproduction | PARTIAL | `gates/M1/`, `gates/G0/g0c/` | Published-performance reproduction is a separate, unmade claim |
| BO-10 | New Hospital collection | BLOCKED ON SCENE ADMISSION | `gates/G2/`; Hospital REVIEW_REQUIRED / PENDING | Scene admission |
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

## Standing corrections

- H7/H7R are **historical diagnostic recordings, not admitted training data**.
- Do not write that the published format "deliberately carries no provenance".
  Write that the loader-facing format requires numbered RGB observations plus
  `traj_data.pkl` with position `[T,2]` and yaw `[T]`, and that provenance fields
  are not required by that loader.
- Every reference in supervisor-facing material must be checked against the
  primary source first. A reference supplied in conversation is a lead.