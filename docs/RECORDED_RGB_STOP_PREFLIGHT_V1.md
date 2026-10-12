# Recorded RGB qualification preflight record v1

The invocation at freeze `621f63aadfcc639cc2ed03327d068bc7dcd93c75` exited 1
with `ValueError: exact clean freeze required`. HEAD matched the requested
revision, but the scientific review note had a post-freeze completion edit.
The clean-tree guard refused before worker launch: **zero encoder forwards**.
This is a preserved preflight failure, not a successful qualification.

External record: `/home/favl/navfm-runtime-evidence/recorded-rgb-stop-v1-preflight-01/preflight.json`,
SHA256 `0072bf1ab8b44e14e345975ca28e677f4867851315836abe3f09439e548bb455`. No worker outputs or model inference were produced.

The freeze amendment contains the review-note completion and this record only.
Runtime code, selected frames, checkpoints, thresholds and resource limits stay
unchanged. A separately authorised first actual encoder execution will use the
new clean revision. No automatic retry occurred.
