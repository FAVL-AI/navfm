# Red-team trigger 4: arrival-under-illumination pilot protocol, 2026-10-09

Artefact: `docs/ARRIVAL_RESEARCH_DECISION.md` (Phase A draft, base `cbddf90`).
Reviewer: independent read-only subagent given only the artefact, collector,
reference stop, results docs, live report and the pinned upstream. Instructed to
refute; default refuted.

**Verdict: DO-NOT-FREEZE.** Research decision: REVISE stands, not PASS. The
illumination study is not admissible until the arrival signal works under nominal
lighting.

| # | Severity | Finding | Re-verification by author session | Disposition |
| --- | --- | --- | --- | --- |
| 1 | BLOCKING | Horizon claim refuted: 0.5 m arrival needs ~1.5 m straight-line / 1.60-1.97 m route travel, within 2.0 m; robot drove 1.82-1.95 m, ended 0.55-1.32 m off | CONFIRMED from `frozen_routes.json` waypoints (straight 2.000/1.970/1.970 m; polyline 2.467/2.104/2.104 m) | Claim retracted in artefact |
| 2 | BLOCKING | Stop threshold `<=1` (one ~0.05 m step) unreachable; logged predicted distance min 4.2; waypoint clause non-discriminating | Min predictions 4.70/4.17/8.38 CONFIRMED from pretrained-04 manifests; label definition per reviewer's upstream citation | Added; H0 must measure distance head vs true distance |
| 3 | BLOCKING | Teacher speed 0.2-0.22 m/s vs live cap 0.1 m/s: context time-base out of distribution | Speeds CONFIRMED in `frozen_routes.json` | Added as untested candidate cause; speed-matched arm required |
| 4 | MAJOR | Six-step adapted checkpoint is a smoke artefact, not a baseline | Accepted | Pretrained only for H0 |
| 5 | MAJOR | Junction routes are `split: test` | CONFIRMED | Disclosed; corpus test split not confirmatory |
| 6 | MAJOR | H1 unfalsifiable as written (floor effect, undefined noise, frames not independent, no lookalikes, one dev route) | Accepted | Requirements added before freeze |
| 7 | MAJOR | Exposure/tonemap/DLSS unpinned; temporal DLSS ghosting; teacher-pose replay does not cover policy poses | No exposure setting in collector CONFIRMED (only DLSS execMode set) | Requirements added |
| 8 | MAJOR | Missing prior work (teach-and-repeat, Krantz ICCV 2023, Patch-NetVLAD, Active Neural Localization) | Krantz, Patch-NetVLAD, Chaplot verified at proceedings/arXiv; Furgale & Barfoot, Paton et al. not verified | Verified ones added; others listed as unverified leads |
| 9 | MINOR | AnyImageNav inputs sourced from HTML method, not abstract; Tokyo >95% unsourced | Accepted | Corrected / withdrawn |
| 10 | MINOR | "Stop decision" vs 24-frame hold before `reached` | Accepted | Endpoint definition required |
