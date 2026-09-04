# Project Execution Governance

Global RIO-AI and enterprise execution standards apply.

Before substantive execution:

1. inspect the project;
2. identify the task route;
3. complete `.claude/execution-preflight.md`;
4. set `status: READY` only when the preflight is complete;
5. invoke the appropriate skill;
6. then execute.

Routes:

RESEARCH -> use `rio-research`

ENGINEERING -> use `enterprise-execution`

RESEARCH+ENGINEERING -> use both

HUMAN_IMPACT -> additionally evaluate affected humans, risks, trust, accessibility, incentives and real-world consequences.

Do not set the preflight to READY simply to bypass the execution gate.

The preflight must describe the actual task being performed.

For research tasks establish:

- research question;
- motivation;
- literature/evidence plan;
- baseline;
- hypothesis;
- metrics;
- success criteria;
- failure criteria.

For engineering tasks establish:

- current state;
- target state;
- requirements;
- constraints;
- risks;
- verification plan.

Never claim SOTA, novelty, enterprise readiness or production readiness without measured evidence.

## Relationship to the standing-instructions file at the repository root

The root instructions win wherever the two differ. They carry the authorship
rule, the gate discipline (G0-G6), the frozen pre-registration, the honesty
markers and the adversarial-review triggers, and every one of those is
narrower and more binding than the generic routing above. This router adds a
pre-execution checkpoint; it does not relax anything.
