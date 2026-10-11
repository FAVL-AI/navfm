#!/usr/bin/env python3

import json
import os
import re
import sys
from pathlib import Path


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }
    }))
    sys.exit(0)


def parse_preflight(path: Path) -> dict[str, str]:
    values = {}

    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line.strip())

        if match:
            values[match.group(1)] = match.group(2).strip()

    return values


try:
    payload = json.load(sys.stdin)
except Exception:
    deny("Unable to parse PreToolUse hook input.")

root = Path(
    os.environ.get(
        "CLAUDE_PROJECT_DIR",
        payload.get("cwd", ".")
    )
).resolve()

marker = root / ".claude" / "research-governance.enabled"

# Projects without the governance marker are unaffected.
if not marker.exists():
    sys.exit(0)

preflight = root / ".claude" / "execution-preflight.md"

tool_name = payload.get("tool_name", "")
tool_input = payload.get("tool_input", {})
session_id = payload.get("session_id", "")

# Claude must be able to edit the preflight itself.
if tool_name in {"Write", "Edit"}:
    target = tool_input.get("file_path", "")

    if target:
        try:
            target_path = Path(target).resolve()
        except Exception:
            target_path = None

        if target_path == preflight.resolve():
            sys.exit(0)

# Allow limited read-only orientation before preflight completion.
if tool_name == "Bash":
    command = str(tool_input.get("command", "")).strip()

    # Composition stays denied before READY. Deciding which compound command is
    # safe would mean writing a shell parser inside a security boundary; two
    # separate read-only calls cost a round trip and cost nothing to reason about.
    dangerous_shell = re.search(r"[;&>|`]|\$\(", command)

    readonly = re.match(
        r"^(pwd|"
        r"ls(\s|$)|"
        r"git\s+(status|log|diff|show|branch|rev-parse)(\s|$)|"
        # Named read-only gh subcommands only. `gh api` is deliberately absent:
        # it mutates or reads depending on its arguments, so treating it as
        # generically read-only would widen the gate to whatever was typed.
        r"gh\s+run\s+(list|view)(\s|$)|"
        r"gh\s+pr\s+(list|view|status|checks)(\s|$)|"
        r"gh\s+workflow\s+(list|view)(\s|$)|"
        r"gh\s+repo\s+view(\s|$)|"
        r"find\s|"
        r"cat\s|"
        r"head\s|"
        r"tail\s|"
        r"grep\s|"
        r"rg\s)",
        command,
    )

    if readonly and not dangerous_shell:
        sys.exit(0)

values = parse_preflight(preflight)

if not values:
    deny(
        "Execution blocked: .claude/execution-preflight.md is missing. "
        "Inspect the project using read-only tools, create the preflight, "
        "select the correct task route, and complete the required fields."
    )

if values.get("session_id") not in {session_id, "CURRENT"}:
    deny(
        f"Execution blocked: the preflight belongs to another session. "
        f"Set session_id to {session_id} after reviewing the current task."
    )

if values.get("status") != "READY":
    deny(
        "Execution blocked: execution preflight is not READY. "
        "Inspect the project, classify the task, invoke the appropriate "
        "research/engineering framework, complete the preflight, and only "
        "then set status: READY."
    )

required = [
    "route",
    "objective",
    "problem",
    "why",
    "current_state_or_baseline",
    "evidence_plan",
    "success_criteria",
    "failure_criteria",
    "risks",
]

bad_values = {"", "TBD", "UNSET", "UNKNOWN"}

missing = [
    key
    for key in required
    if values.get(key, "").strip().upper() in bad_values
]

if missing:
    deny(
        "Execution blocked: incomplete preflight fields: "
        + ", ".join(missing)
    )

route = values.get("route", "").upper()

if "RESEARCH" in route:
    research_required = [
        "research_question",
        "hypothesis",
        "primary_sources_plan",
        "metrics",
    ]

    research_missing = [
        key
        for key in research_required
        if values.get(key, "").strip().upper()
        in {"", "TBD", "UNSET", "UNKNOWN", "N/A"}
    ]

    if research_missing:
        deny(
            "Execution blocked: RESEARCH route requires: "
            + ", ".join(research_missing)
        )

# Passed governance gate.
sys.exit(0)
