# Prospective R2 protocol and executable review

Date: 2026-10-10. Scope: the narrow development R2 versus B1x recovery experiment.
No new-pose images, model outputs or runtime trials were inspected by the review.

Initial disposition: REVISE. Required corrections:

- Exclude post-stop and post-abstention filler records from recovery durability;
  name the primary as exact at first declaration with ten preterminal no-reentry
  decisions rather than continued exact localisation.
- Define a terminal-plus-24-frame contact/exposure gate and disclose extra recorded
  tail, settling contacts and initial pose/history/counter provenance.
- Declare pose/yaw/image matching bounds before seeing outcomes; mismatch fails
  integrity without deleting the pair. Rear-facing means a declared subgroup,
  not verified image informativeness.
- Restrict the confidence guard to first declarations within the common horizon;
  later transitions remain descriptive.

Executable follow-up disposition: REVISE. Four remaining corrections:

- Include the first commanded interval in path, time, translation and rotation.
- Pin imported scoring contracts and their measurement dependency.
- Require a single robot digest across all arms and attempts.
- Validate the entire launch ledger for undeclared starts/routes, duplicate
  launches, fixed initial ordering and a unique passing pilot gate preceding
  expansion; recompute the pilot observations when validating the final gate.

Final disposition: FREEZE. A bounded independent read-only re-review confirmed
all corrections in executable code. The 12 focused prospective tests passed
independently, including negative controls for those corrections. Review did not
modify files, run model trials or preview proposed-start evidence.

This is permission to freeze and execute the declared staged development
experiment, not a positive result or a generalisation/safety claim. The reused
matching bounds remain conservative and unvalidated for the new starts; any
failure must halt expansion. Runtime evidence remains outside git.
