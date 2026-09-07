# Verified metric and format references — frozen 2026-09-07

Every row below was checked against a primary source in this session. A reference
supplied in conversation counted only as a lead until it was opened.

Verification method is recorded per row, because "verified" without a method is
just a stronger-sounding assertion.

---

## Frozen table

| Item | Primary source | Verification | Status |
|---|---|---|---|
| **R2R dataset; Navigation Error, Success, Oracle Success** | Anderson, Wu, Teney, Bruce, Johnson, Sünderhauf, Reid, Gould, van den Hengel. *Vision-and-Language Navigation: Interpreting visually-grounded navigation instructions in real environments.* CVPR 2018. arXiv:1711.07280 | **Full PDF read.** Table 1 column headers printed as `Trajectory Length (m)`, `Navigation Error (m)`, `Success (%)`, `Oracle Success (%)`; caption "Average R2R navigation results using evaluation metrics defined in Section 4.4". Figure 7 plots Navigation Error and Success. | **VERIFIED from the full paper**, not from generic "R2R/VLN literature". |
| **SPL** | Anderson, Chang, Chaplot, Dosovitskiy, Gupta, Koltun, Kosecka, Malik, Mottaghi, Savva, Zamir. *On Evaluation of Embodied Navigation Agents.* 2018. arXiv:1807.06757 | **Full PDF read.** §4 "Evaluation Measures", equation (1). | **VERIFIED — strongest evidence in this table.** |
| **CLS** | Jain, Magalhaes, Ku, Vaswani, Ie, Baldridge. *Stay on the Path: Instruction Fidelity in Vision-and-Language Navigation.* ACL 2019 (long paper). arXiv:1905.12255 | arXiv abstract fetched; authors state they "propose a new metric, Coverage weighted by Length Score (CLS)". | **VERIFIED as the introducing paper.** Full formula not read; CLS is path-sensitive by description. |
| **nDTW / SDTW** | Ilharco, Jain, Ku, Ie, Baldridge. *General Evaluation for Instruction Conditioned Navigation using Dynamic Time Warping.* NeurIPS 2019. arXiv:1907.05446 | arXiv abstract fetched. nDTW "softly penalizes deviations from the reference path"; SDTW constrains nDTW "to only successful paths". | **VERIFIED, including that both require a reference trajectory.** This is the direct justification for marking them BLOCKED. |
| **VLN-CE** | Krantz, Wijmans, Majumdar, Batra, Lee. *Beyond the Nav-Graph: Vision-and-Language Navigation in Continuous Environments.* 2020. arXiv:2004.02857 | **Full text read (ar5iv).** "we call this task Vision-and-Language Navigation in Continuous Environments (VLN-CE)"; "the VLN-CE dataset consists of 4475 trajectories converted from R2R train and validation splits"; "we instead transfer those from the nav-graph-based Room-to-Room dataset to our continuous setting". | **VERIFIED**, including the VLN-CE name and the R2R-derived construction. |
| **GNM/ViNT/NoMaD processed data format** | `robodhruv/visualnav-transformer`, pinned in this repository at `third_party/visualnav-transformer` @ `dca79815b704e5aa9c6bdc3082351f9e3b2848c2` | **Read from the pinned clone on disk**, `README.md` lines 77–99. | **VERIFIED — primary source under our own version control.** |
| **SaferPath** | Zhang, Jiang, Chen. *SaferPath: Hierarchical Visual Navigation with Learned Guidance and Safety-Constrained Control.* ICRA 2026. arXiv:2603.01898 | arXiv page fetched; identifier resolves. | **VERIFIED that the paper exists.** Its collision-metric definition was **not** read and must not be cited until it is. |
| **Collision rate** | — | — | **NO CANONICAL SOURCE. Do not cite one.** See below. |

---

## SPL, quoted from the primary source

*On Evaluation of Embodied Navigation Agents*, §4, equation (1):

    (1/N) · Σᵢ₌₁ᴺ  Sᵢ · ℓᵢ / max(pᵢ, ℓᵢ)

where `Sᵢ` is a binary success indicator for episode *i*, `ℓᵢ` the shortest-path
distance from start to goal, and `pᵢ` the length of the path actually taken.

> "We will refer to this measure as SPL, short for Success weighted by
> (normalized inverse) Path Length."

> **Recommendation 3.** "We recommend adopting SPL as the primary measure of
> navigation performance."

**SPL is therefore not an R2R-original metric.** Attributing SPL, CLS, nDTW and
SDTW to the R2R paper is the citation ambiguity to avoid: four metrics, three
different papers, none of them R2R. Navigation Error, Success and Oracle Success
*are* reported by the R2R paper (Table 1) and may be cited to it directly.

---

## Collision metrics — deliberately not attributed

The same paper lists, among *auxiliary* suggestions only:

> "e) number of infractions (e.g., contact with obstacles)"

That is a suggestion to report something, not a defined metric. It is not a
collision rate, and it must not be cited as one.

These are different quantities and must never be collapsed into one row:

    collision count
    collision rate
    collision-free success
    safety violation rate

**Rule:** a collision metric is cited only against the exact paper and
experimental protocol whose definition we reproduce, and only after that
definition has been read in full. SaferPath is the likely comparison target and
its definition is **NOT YET READ**.

---

## The published loader-facing format, quoted from the pinned clone

`third_party/visualnav-transformer/README.md` @ `dca7981`:

    <dataset>/<name_of_traj>/
        0.jpg
        1.jpg
        ...
        T.jpg
        traj_data.pkl

> "Each `*.jpg` file contains an forward-facing RGB observation from the robot,
> and they are temporally labeled. The `traj_data.pkl` file is the odometry data
> for the trajectory. It's a pickled dictionary with the keys:
> - `"position"`: An np.ndarray [T, 2] of the xy-coordinates of the robot at each
>   image observation.
> - `"yaw"`: An np.ndarray [T,] of the yaws of the robot at each image
>   observation."

**Correct phrasing for supervisor material:** these are the fields the
loader-facing format requires; provenance fields such as scene identity,
controller identity and checksums **are not required by that loader**.

**Do not write** that the published format "deliberately carries no provenance" —
that asserts an intent the source does not state.

---

## Global research standard — binding the exact version

The global research standard lives in the machine-level policy directory outside
this repository, so no commit here preserves it. Its content at the time this
table was frozen:

    SHA-256  c46a128a1e9562eb57f8099f0afe773635cd10ae1c7efb6f8498c8a954b40e57

Recorded so a later reader can tell whether the standard in force has changed.
