# Trigger 4: component comparison protocol (component_comparison_v1), 2026-10-09

Verdict: DO-NOT-FREEZE as written; freezable after F1-F3 (code) and config amendments.

1. HIGH code: an accepted bounded jump still followed the raw (aliased) argmin node,
   reproducing the s_bend failure. Fixed: follow the capped node + 1; failing-first test.
2. MED code: lost-state persistence not consecutive (a failing decision did not reset it).
   Fixed: reset on any failing lost decision; failing-first test.
3. MED code/config: runtime fields not enforced. Fixed: collector refuses any mismatch
   (radius, threshold, speed, rate, budget, checkpoint, goal root, qualification, yaw
   feedback, condition root, chain hash); test.
4. HIGH calibration: pooled false-accept hid the near band. Reported: 0.75-1.0 m learned
   4.4% (pixel 9.7%), below the reviewer's ~10% usability bound.
5. MED: C vs A on true chains and pending oscillation / D lost-drag modes pre-registered.
6. MED measures: jump count biased toward B. Primary measure now pose-true node error of
   current and followed node; verification delay only for C and D.
7. MED calibration provenance: lost thresholds from one collection (~8 tail points);
   in-sample caveat and goal/chain roots recorded.
8. LOW: visits labelled goal-region visit; pause/lost cannot be arrival (confirmed).
9. HIGH design: B answered by mechanism trace with a NOT-TESTED rule; two s_bend repeats
   per variant; run order and determinism reporting stated.
10. LOW controls: one cross-scene swap route restored; released checkpoint and online
   pixel verifier stated as scope limits.
