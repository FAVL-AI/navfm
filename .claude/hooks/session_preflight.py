#!/usr/bin/env python3

import json
import os
import sys
from pathlib import Path

payload = json.load(sys.stdin)

root = Path(
    os.environ.get(
        "CLAUDE_PROJECT_DIR",
        payload.get("cwd", ".")
    )
).resolve()

preflight = root / ".claude" / "execution-preflight.md"

session_id = payload.get("session_id", "UNKNOWN")

template = f"""# Claude Execution Preflight

session_id: {session_id}
status: DRAFT

route: UNSET

objective: TBD

problem: TBD

why: TBD

who: TBD

where: TBD

when: TBD

how: TBD

current_state_or_baseline: TBD

evidence_plan: TBD

success_criteria: TBD

failure_criteria: TBD

risks: TBD

research_question: N/A

hypothesis: N/A

primary_sources_plan: N/A

dataset_or_environment: N/A

metrics: N/A

human_impact: N/A
"""

preflight.parent.mkdir(parents=True, exist_ok=True)
preflight.write_text(template, encoding="utf-8")

print(
    "RIO-AI execution governance is active. "
    "Before substantive Write, Edit, or Bash execution, inspect the project, "
    "classify the task, invoke the relevant skill(s), complete "
    ".claude/execution-preflight.md, and set status to READY."
)
