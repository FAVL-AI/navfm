# Trigger 6: component comparison v1 results and component decisions, 2026-10-10

Why trigger 6: the decisions rest on one route and on "not encountered" findings
(absence-dependent), and on a sample shaped by which attempts reached the stop.

Reviewer: independent subagent, read-only, given only the write-up, frozen config,
measures, policy code, analysis scripts, outputs and raw manifests.
Verdict: ACCEPT-WITH-CORRECTIONS. Counts were reproduced (all 16 rows; 5 attempts
spot-checked against audit and manifests; analysis output reproduced byte for byte).
"Never encountered" for B/D was confirmed against the raw records, not just the definition.

Findings and resolution (all applied to docs/ARRIVAL_RESEARCH_DECISION.md before commit):
1. HIGH: offline near-goal acceptance was inflated by stop/post-stop frames (selected by
   the check under test). Fixed: evaluate_offline_verifiers.py reports pre-stop frames as the
   primary population; learned near accept 0.47 -> 0.31, pixel 0.29 -> 0.09; new output -02.
2. HIGH: "failures are in the decision logic, not frame-level" refuted. Fixed: frame-level
   false rejection (C trunc s_bend_0000) and chain-flag alternation both stated; causal links
   marked INFERENCE.
3. HIGH: decision table stated a cause the prose called inference. Fixed: "associated with
   ... (INFERENCE, effectively one trajectory per arm)".
4. MED: the claim that a reached decision implies distance <= 3 was false, and the threshold did act on a true chain. Fixed:
   both routes to a declaration described; two true-chain rejections reported.
5. MED: lost state "every off-chain attempt" false. Fixed: 6/10 B/D; attributed to the
   interaction with verification steering.
6. MED: 66 vs 68 interventions; the 2 swap interventions were forward. Fixed.
7. MED: pre-registered primary measure (current-node error) and route departure missing.
   Fixed: both added; B not better than A off s_bend_0000.
8. MED: "defined before reading outcomes" unsupported. Fixed: labelled post-freeze analysis
   definitions (session record: written 22:48 during collection, scored outcomes read 23:05,
   one termination label seen earlier).
9. MED: heading ranges omitted a true-chain repeat. Fixed: 1-21 deg, 0.46-0.77.
10. LOW/MED: below-threshold counts. Fixed: 4 and 7.
11. LOW/MED: integrity narrower than stated. Fixed: analysis now checks non-repo files,
    inference completeness, launch after freeze, 8321e9c match count, and has a
    --negative-control mode; new checks shown to fail on broken inputs; scripts committed.
12. LOW: stop-distance range. Fixed: -0.086 to +0.070 m.
13. LOW: s_bend_0001 backward step was correct (withholding wrong). Fixed.
14. LOW: chain-end declarations, failure mode 4, A's 6 wrong stops with repeats. Fixed.
15. LOW: retention of rejection rule must be conditional. Fixed: REVISE; retention
    conditional on the revision.
16. LOW: offline output older than script. Resolved: script re-run, output -02.
