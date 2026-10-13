# Native fixed graph preflight record v1

The invocation at clean freeze `5dcc8d61a8ae87f38cc366b42ca590afdff49a53`
exited1 before worker launch because the manifest still declared
PREPARATION_NOT_FROZEN. The runtime guard refused matching. There were zero
matching/model/global-encoder calls and no runtime attempt directory was created.
This is a preserved preflight refusal, not a successful graph qualification.
No automatic retry occurred.

External record: `/home/favl/navfm-runtime-evidence/ravel-fixed-graph-v1-preflight-01/preflight.json`,
SHA256 `c176ef804d947b03f705cb7caf6c5031c7afe98e1e5db2452aae0600a4c2a00f`.

The amendment changes manifest readiness status to
FROZEN_NATIVE_FIXED_GRAPH_V1 and records this refusal. A separate parent-admission guard now explicitly
vetoes timeout even if exit0 and valid evidence are supplied; its focused
negative control passes. Native source imports/numeric bodies, inputs, weights,
fixed parameters and resource caps are unchanged. A bounded CPU source-closure recheck binds the final loader hash and confirms
zero matcher/model forwards. A separately authorised
first matching execution must use the amended clean freeze.
