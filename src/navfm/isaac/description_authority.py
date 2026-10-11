"""Decide which vendor description is authoritative, and for what.

Two descriptions of the ROSMASTER M3 Pro exist in the vendor archive and they
differ. Choosing between them is an apparatus decision, so the rule is frozen
here before any candidate is scored, and the rule is deliberately narrow:
authority follows the production reference chain and nothing else.

That narrowness is the point. Completeness, parse cleanliness, mesh quality,
import convenience and recency are not inputs to this function -- not weighted
low, absent -- because a tie-break on any of them is how a project ends up
simulating a robot the vendor does not ship. A candidate may be richer than the
production root and still lose, and there is a control for exactly that.

Authority is also plural. One file can be the whole-robot runtime root while
another is authoritative for manipulator-planning semantics it alone defines,
which avoids forcing a single file to carry every kind of truth or declaring
the other one wrong.

Four things this decision does not settle, kept apart because collapsing any of
them into authority would be a category error: whether the source may be
redistributed, whether its numbers match the physical robot, how colliders
should be built from it, and whether it is free of defects. A source can be
authoritative and broken at the same time -- being what the robot actually
loads is a fact about the vendor's software, not a certificate of quality.
"""

from __future__ import annotations

import dataclasses
from typing import Any

__all__ = [
    "AUTHORITY_ROLES",
    "DECISION_RULES",
    "Candidate",
    "classify_authority",
]

#: Roles a description may hold. More than one description may be authoritative,
#: each for a different scope.
AUTHORITY_ROLES: tuple[str, ...] = (
    "WHOLE_ROBOT_RUNTIME_AUTHORITY",
    "MANIPULATOR_PLANNING_AUTHORITY",
    "SENSOR_CONFIGURATION_AUTHORITY",
    "CAD_GEOMETRY_REFERENCE",
    "SUPPORTING_COMPONENT_SOURCE",
    "TUTORIAL_CONTENT",
    "LEGACY_CONTENT",
)

DECISION_RULES: tuple[str, ...] = (
    "A. exactly one candidate reached by the production bringup chain and "
    "passed to robot_state_publisher takes WHOLE_ROBOT_RUNTIME_AUTHORITY",
    "B. a candidate reached only through manipulator tooling takes "
    "MANIPULATOR_PLANNING_AUTHORITY when it defines planning semantics of its "
    "own, otherwise SUPPORTING_COMPONENT_SOURCE",
    "C. two candidates loaded as competing roots in the same production "
    "configuration make the decision AMBIGUOUS and it stops",
    "D. no candidate is preferred for being newer, more complete, cleaner or "
    "easier to simulate; none of those is an input to this function",
)


@dataclasses.dataclass(frozen=True)
class Candidate:
    """One description, described only by facts relevant to the frozen rule.

    Deliberately missing: link counts, geometry quality, file age. They are
    recorded elsewhere in the evidence and must not reach the decision.
    """

    identity: str
    sha256: str
    robot_name: str
    #: Reached by the production bringup entry point, directly or transitively.
    reached_by_production_bringup: bool
    #: That same chain hands it to robot_state_publisher.
    reaches_robot_state_publisher: bool
    #: Loaded by manipulator tooling, in its own configuration.
    reached_by_manipulator_tooling: bool
    #: True when bringup and the manipulator tooling run as one configuration.
    shares_configuration_with_production: bool = False
    #: Planning semantics this candidate alone carries (SRDF groups, limits,
    #: solver configuration). Names only; never counted as "completeness".
    planning_semantics: tuple[str, ...] = ()

    def as_record(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        record["planning_semantics"] = list(self.planning_semantics)
        return record


def classify_authority(candidates: list[Candidate]) -> dict[str, Any]:
    """Apply the frozen rule. Returns a verdict and the reasoning behind it."""
    if not candidates:
        return {
            "VERDICT": "NO_CANDIDATES",
            "AUTHORITATIVE_ROBOT_DESCRIPTION": "UNDETERMINED",
            "rules_applied": list(DECISION_RULES),
            "reasoning": ["no candidate descriptions were supplied"],
            "roles": {},
        }

    reasoning: list[str] = []
    runtime = [c for c in candidates
               if c.reached_by_production_bringup and c.reaches_robot_state_publisher]

    competing = [c for c in runtime if c.shares_configuration_with_production]
    if len(runtime) > 1 and len(competing) > 1:
        return {
            "VERDICT": "AMBIGUOUS",
            "AUTHORITATIVE_ROBOT_DESCRIPTION": "AMBIGUOUS",
            "STOP": True,
            "rules_applied": list(DECISION_RULES),
            "reasoning": [
                f"{len(competing)} candidates are loaded as competing "
                "robot_description roots in the same production configuration: "
                + ", ".join(sorted(c.identity for c in competing)),
                "rule C applies and the decision stops rather than choosing",
            ],
            "roles": {},
        }

    roles: dict[str, str] = {}
    selected: Candidate | None = None

    if len(runtime) == 1:
        selected = runtime[0]
        roles[selected.identity] = "WHOLE_ROBOT_RUNTIME_AUTHORITY"
        reasoning.append(
            f"{selected.identity} is the only candidate the production bringup "
            "chain reaches and hands to robot_state_publisher; rule A applies")
    elif len(runtime) > 1:
        reasoning.append(
            f"{len(runtime)} candidates are reached by a production chain but "
            "not within one configuration, so none can be the single runtime "
            "root without a further decision")
        return {
            "VERDICT": "AMBIGUOUS",
            "AUTHORITATIVE_ROBOT_DESCRIPTION": "AMBIGUOUS",
            "STOP": True,
            "rules_applied": list(DECISION_RULES),
            "reasoning": reasoning,
            "roles": {},
        }
    else:
        reasoning.append(
            "no candidate is reached by the production bringup chain, so no "
            "whole-robot runtime authority can be established from this evidence")

    for candidate in candidates:
        if candidate.identity in roles:
            continue
        if candidate.reached_by_manipulator_tooling:
            if candidate.planning_semantics:
                roles[candidate.identity] = "MANIPULATOR_PLANNING_AUTHORITY"
                reasoning.append(
                    f"{candidate.identity} is loaded only by manipulator tooling "
                    f"and carries planning semantics "
                    f"({', '.join(candidate.planning_semantics)}); rule B applies")
            else:
                roles[candidate.identity] = "SUPPORTING_COMPONENT_SOURCE"
                reasoning.append(
                    f"{candidate.identity} is loaded only by manipulator tooling "
                    "and defines no planning semantics of its own; rule B applies")
        else:
            roles[candidate.identity] = "SUPPORTING_COMPONENT_SOURCE"
            reasoning.append(
                f"{candidate.identity} is not reached by any production or "
                "manipulator chain measured here")

    return {
        "VERDICT": "DECIDED" if selected is not None else "UNDETERMINED",
        "AUTHORITATIVE_ROBOT_DESCRIPTION":
            selected.identity if selected else "UNDETERMINED",
        "AUTHORITATIVE_SOURCE_SHA256": selected.sha256 if selected else None,
        "AUTHORITY_SCOPE":
            "WHOLE_ROBOT_RUNTIME_AUTHORITY" if selected else "NONE",
        "STOP": False,
        "rules_applied": list(DECISION_RULES),
        "inputs_deliberately_excluded": [
            "link or joint counts", "model completeness", "parse cleanliness",
            "mesh quality", "import convenience", "file recency"],
        "reasoning": reasoning,
        "roles": roles,
        "NOT_ESTABLISHED_BY_THIS_DECISION": [
            "permission to redistribute the source",
            "agreement between the source and the physical robot",
            "how colliders should be derived from it",
            "that the source is free of defects",
        ],
    }
