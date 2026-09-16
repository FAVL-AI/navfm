# Gate fault-injection policy — DRAFT, not promoted

Author: Frank Asante Van Laarhoven
Status: **DRAFT.** Not enforced repo-wide. No existing gate is changed by this
document. It records a policy that three separate defects now justify, so that
promoting it later is a decision rather than a reconstruction.

## Why this exists

Three defects in this line of work shared one shape, and none of them was in
ordinary success-path code.

1. **V2 amendment** — a self-falsifying provenance field.
2. **Lifecycle rehearsal artefact** — recorded `repository_head = c542e21…`
   while the three modules whose reachability it certified existed at no
   commit. Checking out that head and re-running fails with `ImportError`.
3. **Arm-A collector wiring regression** — as committed at `c542e21`, claims
   `repository_head = effcce1…` while recording `collect.py = 430a57f8…` and
   `target_selection.py = 536dbd1d…`. Searched across all 214 commits: neither
   content exists anywhere in the history. It was measured against an
   uncommitted working tree and cannot be reproduced from any commit.

Two distinct patterns, both invisible to happy-path execution:

```
negative-space code            evidence measured against a dirty tree
refusal handlers                       while stamping a clean head
stale-state paths
unreachable dependencies
early returns
partial outputs
```

## Draft rule A — evidence provenance gate

No gate may emit an artefact recording both a `repository_head` and source
identities unless every recorded identity is the content at that head.

Reference implementation (not wired into any gate):

```python
def refuse_dirty_tree_evidence(head: str, recorded: dict[str, str]) -> list[str]:
    """Recorded identities must be what the named head actually contains."""
    return [
        f"{rel}: recorded {sha[:12]}, head {head[:12]} has {_blob_sha_at(head, rel)}"
        for rel, sha in recorded.items()
        if _blob_sha_at(head, rel) != sha
    ]
```

An artefact that cannot satisfy this should either refuse to emit, or record
`working_tree_dirty: true` and drop its reproducibility claim. It must not
print a clean head over a dirty measurement.

All three defects above would have been caught at emission by this rule.

## Draft rule B — minimum control set per scientific gate

Every scientific gate should carry at least:

| Control | What it proves |
|---|---|
| PASS | the gate can succeed |
| intended FAIL | the gate can fail at all |
| malformed evidence | it reads before it trusts |
| missing evidence | absence is not success |
| stale evidence | currency is checked, not assumed |
| unreachable dependency | resolution is not reachability |
| early return | partial completion is not completion |
| exception during refusal handling | the refusal path is itself a path |
| partial artefact | a truncated write is not a result |
| duplicate invocation | exactly-once is enforced, not hoped for |

`validate_lifecycle_reachability.py` already implements eight of these. It is
the worked example, not a new requirement on anything else.

## What this draft deliberately does not do

It does not change any existing gate, promote itself repo-wide, or alter
research governance outside this tranche. Promotion is a separate decision.
