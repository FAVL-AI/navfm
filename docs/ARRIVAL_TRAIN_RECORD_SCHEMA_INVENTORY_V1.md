# Admitted training-record schema inventory v1

**Scope:** read-only schema inventory at source commit `7e9f8f8f269636530cd323a800c146175b0cf055`. Only the 31 records in the admitted training split were inspected. No RGB bytes were decoded, no encoder or model was run, and development, retired-test, pilot, and future-evaluation records were excluded.

## Method and observed record schema

The admission manifest's SHA-256 was checked for each of the 31 training `traj_data.pkl` files before loading. A restricted NumPy-only unpickler and the repository's `navfm.trajio.normalise_traj_data` conversion were used. Image filenames were enumerated only to check index continuity; image contents were not opened. All 31 records matched their manifest hashes and normalized to exactly these two keys:

| Field | Observed normalized representation | Documented meaning | Availability |
|---|---|---|---|
| `position` | `float64`, shape `(T, 2)`; observed `T` values: 36, 37, 38, 49 | Planar `(x, y)` position in metres, per frame | Present in all 31 records; finite and length-matched to yaw |
| `yaw` | `float64`, shape `(T,)`; observed `T` values: 36, 37, 38, 49 | Unwrapped heading in radians, per frame | Present in all 31 records; finite and length-matched to position |
| `timestamp` / elapsed time | No such key in the exact two-key record schema; no `metadata.json` beside any of these 31 records | Would be needed for measured frame intervals | **Absent from these admitted records**; do not infer from an assumed frame rate |

All records had contiguous image-index names `0.jpg` through `(T-1).jpg`, consistent with the documented frame mapping: image `t.jpg`, `position[t]`, and `yaw[t]` refer to the same indexed observation. This establishes index order, not elapsed time between observations.

The admission manifest separately contains 31 unique trajectory IDs and route IDs, eight scene IDs, and five collection IDs. These support record-level grouping and overlap audits. The frozen split specification documents partial appearance overlap between training and existing development/retired-test groups; these groups must not be treated as layout-independent. Episode balancing cannot remove layout leakage.

## Field-to-feature and label mapping

| Requirement | Evidence and status | Limit |
|---|---|---|
| Ordered query/reference identities | **Supported by derivation:** `(trajectory_id, frame_index)` identifies an indexed frame, and each record's image/pose indices align. | No reliable time interval is available. Chronological index order must not be reported as measured temporal spacing. |
| Position/yaw labels and units | **Supported:** per-frame position and yaw are present, finite, and length-matched. `DATA_CONTRACT.md` documents metres and radians, respectively. | Coordinate values are only authenticated within each record's own trajectory frame; no common cross-route world frame is established here. |
| Episode, route, and layout grouping | **Supported with caveat:** trajectory IDs can group episodes; route and scene IDs are available from the admission manifest. | Existing split documentation records partial appearance overlap. These identities do not establish independent layouts across partitions. |
| Geometric goal proximity | **Derivable, not yet extracted:** choose a goal frame within a trajectory and compute Euclidean distance from each query-frame position in metres. The derivation is independent of model predictions. A proximity class additionally requires a prospectively specified radius. | This is geometric proximity only. Position alone does not show settling, collision-free completion, successful task completion, or physical STOP. |
| Similarity/alias features | **Unavailable from this schema inventory:** similarity rows and alias margins require image/descriptor evidence and pinned encoder provenance. | No images were decoded and no descriptors were generated. Metadata cannot establish perceptual aliasing or the number of visually confusing negatives. |
| Correct-arrival / wrong-location labels | **Unavailable as observed labels:** the records contain no arrival, stop, settling, collision, or task-completion fields. | Do not relabel geometric proximity as successful arrival or wrong-stop ground truth. |

## Bounded training-only extraction candidate

The admitted training records contain 1,255 indexed frames. A deterministic geometry-only table could be derived from the 31 authenticated training records with columns for trajectory/route/scene identity, query frame index, selected same-trajectory goal frame index, position/yaw, and Euclidean distance in metres. The upper bound over all ordered query/goal frame pairs is `sum(T²) = 51,887`. That bound is a storage/work bound, **not** an independent sample count; pairs within a trajectory are correlated.

No extraction was performed. Before authorizing it, freeze the goal-frame selection rule, retain the source record hashes, and keep all rows confined to the admitted training split. Do not create a binary arrival label without a separately specified geometric radius and missingness rule. This table would provide geometry-only training inputs; it would not supply elapsed-time features, verified arrival outcomes, or alias-hard negative labels.

## Decision

The record-level inspection resolves the manifest-versus-source uncertainty for the inspected schema: the 31 admitted training records themselves contain per-frame position and yaw, but no timestamps or arrival outcomes. Frame identity/order and geometric proximity are supported or derivable; time-based calibration, verified successful-arrival labels, and perceptual-alias coverage remain unavailable or unverified.

Therefore this inventory does **not** make calibration ready and does not justify fitting, threshold selection, or a calibration-quality claim. It identifies one possible training-only geometry extraction and the exact evidence gaps that remain. Existing development/pilot exclusions and all source data remain unchanged.

Validation was documentation-only; no tests, fitting, inference, collection, simulation, navigation, or actuation were run. Skill retrieval was unavailable in this session.
