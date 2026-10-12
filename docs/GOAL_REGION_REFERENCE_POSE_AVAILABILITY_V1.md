# Goal-region reference-pose availability v1

**Decision: stop integration of the 0.5 m goal-region feature for the current
deployment bank.** The admitted pilot contains enough identity-bound pose labels
to derive the region offline for its eight references, but the deployed
reference-bank builder and node map do not carry those poses. This is an input
availability finding, not a calibration or navigation result.

## Bounded provenance check

At source freeze `83b2ecb297c2aed382cd172d9e70e9545acff572`, the frozen RAVEL
configuration binds eight image references at frames `0, 4, 8, 12, 16, 20,
24, 28` from `prospective_v1_layout0_route0`. The external node map has only
`frame`, `path`, and image `sha256`; its entries match the configured references.
All eight image identities join to the admitted dataset manifest and the
capture record by route, tick, and image hash. The admitted trajectory label
file is hash-bound by the dataset admission; its position array has 36 finite
XY entries. The selected reference positions agree with their capture
`teacher_pose` records. The goal node is node 7 / frame 28. The project data
schema defines trajectory positions in metres in a fixed world/odometry frame
per trajectory. Since all eight references and the goal are from one
trajectory, a common frame for this offline calculation is supported.

The production bank-building path consumes the configured images and their
hashes. It does not read the trajectory labels or emit pose fields. The
resulting node map likewise contains no pose or coordinate-frame metadata.
Thus the labels are available to an offline evaluator, but are not inputs in
the current deployed reference-bank interface. Query ground truth is not
available to, or required by, the candidate inference function.

| Availability class | Finding |
|---|---|
| Current deployed reference-bank builder | **Unavailable.** Only image identity, frame index and descriptor/graph identity are retained. |
| Offline evaluator for this admitted bank | **Available.** All eight references map to finite metric XY labels in the same trajectory frame, including the requested goal. |
| Cross-trajectory or deployment-map alignment | **Not established.** No common transform across trajectories or authenticated M3 Pro map frame is provided by this bank. |

## Input required to resume integration

The builder would need an explicit, authenticated pose sidecar for every
reference: stable reference ID and RGB hash bound to `(x, y)` in metres, a
declared map/frame ID and transform, plus provenance for the mapping source.
The requested goal must resolve to one of those same identities. The sidecar
must be genuinely available to the deployed bank builder and runtime. It may
not be synthesized from node order, connectivity, match counts, descriptors,
or query ground truth. Acquiring a qualified mapping source is outside this
check; no mapping work or candidate adapter was started.

No images were decoded, no encoder or model was run, and no fitting, collection,
simulation or navigation occurred. No code or acceptance rule changed. The
prior synthetic tests remain evidence only for the candidate's arithmetic and
input validation.

Validation consisted of read-only identity/schema joins over the frozen config,
external node map, admitted metadata and source schema; no new tests were
applicable. Raw labels and runtime artifacts remain external.
