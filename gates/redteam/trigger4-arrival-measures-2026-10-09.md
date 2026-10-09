# Trigger 4: evaluation measures freeze (arrival_measures_v1), 2026-10-09

Independent reviewers received only the artefacts and were told to refute.

## Revision 1: DO-NOT-FREEZE

1. CRITICAL: "commanded" yaw ambiguous (policy setpoint vs actuator after the
   0.8 / 1.5 wheel gains). Checked: with yaw feedback the gains are bypassed; in
   open-loop runs qualifier and episodes both applied 0.8 after the same setpoint.
2. HIGH: three conflicting stop/success definitions (config, audit, collector metrics).
3. HIGH: settle passed with no post-stop frames.
4. HIGH: distance scored to the route endpoint, goal image 0.115 m short of it.
5. HIGH: collision exposure bias between stopping and non-stopping runs.
6. HIGH: in-episode tracking built from 3-40 commands; slope vs median ratio.
7. MED: admitted-rate denominator excluded refused or crashed collections.
8. MED: navigation success counts pass-throughs; needs null rows.
9. MED: missing fields (timeout, stop rule, elapsed, path, wrong stop, departure,
   stop attribution, contact rounding).
10. MED: Wilson intervals at n = 4 uninformative.

Response: `src/navfm/collection/episode_measures.py` became the single
computation, with the audit delegating to it (commit 515baca).

## Revision 2: FREEZE-WITH-AMENDMENTS

Resolved 3, 5, 10; mostly resolved 9; partial 1, 2, 4, 6, 7, 8. New findings:
N1 HIGH silent endpoint fallback without --goal-root and no check that the
goal root is the episode's; N2 MED endpoint distance labelled closest_goal_m;
N3 MED stop wording omitted the frame-107 minimum; N4 MED late stop labelled
timeout by the collector; N5 LOW settle relative to window start, region time
included post-contact frames; N6 LOW untested edge cases.

Amendments applied before freeze:

- A1: audit refuses policy episodes without --goal-root and goal roots whose
  declared source frame or goal bytes differ from the episode's.
- A2: WITHIN_BAND / OUTSIDE_BAND instead of QUALIFIED; closest_endpoint_m;
  frames_recorded plus max_steps_budget (collector now records max_steps).
- A3: stop wording with the frame-107 minimum and the late-stop bias; settle
  window wording; displacement after stop reported; collector termination is
  policy_stop whenever a stop exists.
- A4: navigation success only with the measured goal-blind row, otherwise
  "goal-region visit".
- A5: admitted rate counted from frozen routes, collection and admission report.
- A6: collector metrics and feasibility_metrics.py declared superseded; tests
  for contact at the stop frame, entry and contact in one frame, fallback
  labelling, budget recording, artefact-derived admission counts, audit refusals.
