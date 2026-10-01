"""Comparison and admission for runtime attestations.

Separated from :mod:`navfm.collection.attestation` on purpose. The readers report
what they observed and never see intent; this module holds the requested values
and the declared rules. The split is what makes

    observed = read_runtime_value() or requested_value

impossible to write by accident: the two values never live in the same object.

A requirement is satisfied only on positive evidence. Every non-``OBSERVED``
status is unresolved, never a pass, and the eight requirements are all mandatory
because their source document says what *must* be recorded before the next
collection. Accounting for a requirement is not the same as passing it: an
unresolved mandatory requirement blocks scientific collection.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from typing import Any

from .attestation import REQUIREMENTS, REQUIREMENTS_SHA256, Observation, Provenance, Status


class Verdict(str, enum.Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    #: The observation did not resolve, so conformance is unknown. Never a pass.
    UNRESOLVED = "UNRESOLVED"
    #: The observation belongs to a different run, or to no declared run.
    REJECTED_WRONG_RUN = "REJECTED_WRONG_RUN"


class RuleKind(str, enum.Enum):
    #: The requirement asks for the value to be RECORDED. Satisfied when observed.
    PRESENCE = "PRESENCE"
    #: The requirement additionally supports comparing observed against requested.
    AGREEMENT = "AGREEMENT"


@dataclasses.dataclass(frozen=True)
class Rule:
    requirement: str
    name: str
    kind: RuleKind
    #: How requested is mapped into the observed quantity's units/domain. Declared
    #: ahead of any measurement, never chosen after seeing a mismatch.
    transform: str = ""
    tolerance: float | None = None
    tolerance_justification: str = ""


def _deg_to_rad(v: Any) -> float:
    return math.radians(float(v))


def _dlss_flag_to_exec_mode(v: Any) -> int:
    # IsaacApp.start() sets /rtx/post/dlss/execMode = 2 when dlss_quality is true.
    return 2 if bool(v) else 0


TRANSFORMS = {
    "degrees_to_radians": _deg_to_rad,
    "dlss_quality_flag_to_exec_mode": _dlss_flag_to_exec_mode,
    "identity": lambda v: v,
}

#: The declared rule set. Requirements whose source text asks only that a value be
#: recorded get PRESENCE; only where a defensible mapping exists does a value get
#: compared against intent.
RULES: tuple[Rule, ...] = (
    # R1 -- recording source identity is the requirement; there is no intent to compare.
    Rule("R1", "repository_head", RuleKind.PRESENCE),
    Rule("R1", "worktree_dirty", RuleKind.PRESENCE),
    Rule("R1", "influencing_file_digests", RuleKind.PRESENCE),
    # R2 -- "only a read-back can state the intrinsics", so recording is the duty.
    Rule("R2", "focal_length", RuleKind.PRESENCE),
    Rule("R2", "horizontal_aperture", RuleKind.PRESENCE),
    Rule("R2", "vertical_aperture", RuleKind.PRESENCE),
    Rule("R2", "clipping_range", RuleKind.PRESENCE),
    Rule("R2", "resolved_prim_path", RuleKind.PRESENCE),
    # The one camera agreement that has an exact mapping: the audited metadata
    # claimed horizontal_fov_deg, and the runtime exposes horizontal_fov in rad.
    Rule("R2", "horizontal_fov", RuleKind.AGREEMENT, transform="degrees_to_radians",
         tolerance=1e-6,
         tolerance_justification=("float round-off of a deg->rad conversion only. Declared before "
                                  "any value was read; not widened to accommodate a result. A "
                                  "value supplied in the wrong unit fails by orders of magnitude")),
    # R3 -- record what was rendered, as the runtime reports it.
    Rule("R3", "render_product_path", RuleKind.PRESENCE),
    Rule("R3", "render_product_camera_target", RuleKind.PRESENCE),
    Rule("R3", "render_product_resolution", RuleKind.PRESENCE),
    # R4 -- these two have exact intent mappings; the rest are recorded.
    Rule("R4", "rt_subframes", RuleKind.AGREEMENT, transform="identity", tolerance=None,
         tolerance_justification="integer setting; exact equality, no tolerance"),
    Rule("R4", "dlss_exec_mode", RuleKind.AGREEMENT, transform="dlss_quality_flag_to_exec_mode",
         tolerance=None,
         tolerance_justification=("exact equality against the mapping IsaacApp.start() itself uses "
                                  "(dlss_quality true -> execMode 2)")),
    Rule("R4", "active_renderer", RuleKind.PRESENCE),
    Rule("R4", "launch_width", RuleKind.PRESENCE),
    Rule("R4", "launch_height", RuleKind.PRESENCE),
    # R5 -- both boundaries plus the goal capture time must exist.
    Rule("R5", "sim_time_at_command", RuleKind.PRESENCE),
    Rule("R5", "sim_time_at_capture", RuleKind.PRESENCE),
    Rule("R5", "goal_capture_sim_time", RuleKind.PRESENCE),
    # R6 -- record the pose. No agreement rule: physics settling legitimately
    # changes Z after spawn and no contract states an allowance, so inventing a
    # tolerance here would be exactly the error this work exists to prevent.
    Rule("R6", "spawn_world_position", RuleKind.PRESENCE),
    Rule("R6", "spawn_world_z", RuleKind.PRESENCE),
    # R7 -- record a statistic with its definition. No threshold: the audit applied
    # no retrospective admission rule and neither does this.
    Rule("R7", "frame_statistic", RuleKind.PRESENCE),
    # R8 -- the annotation must be produced.
    Rule("R8", "intent_field_annotation", RuleKind.PRESENCE),
)

#: All eight are mandatory: the source document states what must be recorded
#: before the next collection.
MANDATORY = set(REQUIREMENTS)


@dataclasses.dataclass(frozen=True)
class Comparison:
    rule: Rule
    observation: Observation
    requested: Any
    verdict: Verdict
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.rule.requirement,
            "name": self.rule.name,
            "rule_kind": self.rule.kind.value,
            "transform": self.rule.transform,
            "tolerance": self.rule.tolerance,
            "tolerance_justification": self.rule.tolerance_justification,
            "requested": self.requested,
            "observed": self.observation.value,
            "observation_status": self.observation.status.value,
            "observation_provenance": self.observation.provenance.value,
            "getter": self.observation.getter,
            "runtime_object": self.observation.runtime_object,
            "lifecycle_point": self.observation.lifecycle_point,
            "verdict": self.verdict.value,
            "detail": self.detail,
            "evidence_limitation": (
                "software read-back of a simulator object; not a physical measurement "
                "and not independent hardware verification"
            ),
        }


def compare(rule: Rule, observation: Observation, requested: Any = None, *,
            run_id: str = "") -> Comparison:
    """Apply one declared rule. The requested value enters only here."""
    if observation.requirement != rule.requirement or observation.name != rule.name:
        raise ValueError(
            f"rule {rule.requirement}/{rule.name} cannot judge observation "
            f"{observation.requirement}/{observation.name}"
        )
    if run_id and observation.run_id != run_id:
        return Comparison(rule, observation, requested, Verdict.REJECTED_WRONG_RUN,
                          f"observation run_id {observation.run_id!r} != declared run {run_id!r}; "
                          "an observation from another run is not this run's evidence")
    if observation.status is not Status.OBSERVED:
        return Comparison(rule, observation, requested, Verdict.UNRESOLVED,
                          f"not observed ({observation.status.value}): {observation.detail}. "
                          "The requested value is NOT substituted")
    if rule.kind is RuleKind.PRESENCE:
        return Comparison(rule, observation, requested, Verdict.MATCH,
                          "required observation is present and resolved")
    if requested is None:
        return Comparison(rule, observation, requested, Verdict.UNRESOLVED,
                          "an agreement rule needs a requested value and none was supplied")
    fn = TRANSFORMS.get(rule.transform)
    if fn is None:
        return Comparison(rule, observation, requested, Verdict.UNRESOLVED,
                          f"unknown transform {rule.transform!r}")
    try:
        expected = fn(requested)
    except Exception as exc:
        return Comparison(rule, observation, requested, Verdict.UNRESOLVED,
                          f"transform failed: {type(exc).__name__}: {exc}")
    observed = observation.value
    if rule.tolerance is None:
        ok = observed == expected
        how = "exact equality"
    else:
        try:
            ok = abs(float(observed) - float(expected)) <= rule.tolerance
        except (TypeError, ValueError):
            return Comparison(rule, observation, requested, Verdict.UNRESOLVED,
                              f"observed {observed!r} is not numerically comparable")
        how = f"|observed - expected| <= {rule.tolerance}"
    return Comparison(
        rule, observation, requested, Verdict.MATCH if ok else Verdict.MISMATCH,
        f"{how}: requested {requested!r} -> expected {expected!r}, observed {observed!r}"
        + ("" if ok else ". The requested value is preserved unchanged; nothing was "
                         "adjusted to make this pass"),
    )


@dataclasses.dataclass(frozen=True)
class Decision:
    comparisons: list[Comparison]
    per_requirement: dict[str, str]
    satisfied: list[str]
    unsatisfied: list[str]
    missing: list[str]
    scientific_collection_permitted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirements_source_sha256": REQUIREMENTS_SHA256,
            "mandatory_requirements": sorted(MANDATORY),
            "per_requirement": self.per_requirement,
            "satisfied": self.satisfied,
            "unsatisfied": self.unsatisfied,
            "requirements_with_no_observation": self.missing,
            "SCIENTIFIC_COLLECTION_PERMITTED": self.scientific_collection_permitted,
            "accounting_is_not_passing": (
                "every requirement appears above, which is accounting. Only those in "
                "'satisfied' passed; any mandatory requirement elsewhere blocks collection"
            ),
            "comparisons": [c.to_dict() for c in self.comparisons],
            "test_double_present": any(
                c.observation.provenance is Provenance.TEST_DOUBLE for c in self.comparisons
            ),
        }


def decide(observations: list[Observation], requested: dict[str, Any] | None = None, *,
           run_id: str = "") -> Decision:
    """Judge every declared rule against the supplied observations.

    ``requested`` is keyed ``"<requirement>.<name>"``. A rule with no matching
    observation is unresolved -- absence is never a pass.
    """
    requested = requested or {}
    by_key = {(o.requirement, o.name): o for o in observations}
    comparisons: list[Comparison] = []
    missing: list[str] = []
    for rule in RULES:
        obs = by_key.get((rule.requirement, rule.name))
        if obs is None:
            missing.append(f"{rule.requirement}.{rule.name}")
            continue
        comparisons.append(
            compare(rule, obs, requested.get(f"{rule.requirement}.{rule.name}"), run_id=run_id)
        )
    per_req: dict[str, str] = {}
    for req in REQUIREMENTS:
        rule_names = {r.name for r in RULES if r.requirement == req}
        got = [c for c in comparisons if c.rule.requirement == req]
        if len(got) != len(rule_names):
            per_req[req] = "UNRESOLVED_MISSING_OBSERVATION"
        elif any(c.verdict is Verdict.REJECTED_WRONG_RUN for c in got):
            per_req[req] = "REJECTED_WRONG_RUN"
        elif any(c.verdict is Verdict.MISMATCH for c in got):
            per_req[req] = "MISMATCH"
        elif any(c.verdict is Verdict.UNRESOLVED for c in got):
            per_req[req] = "UNRESOLVED"
        else:
            per_req[req] = "SATISFIED"
    satisfied = [r for r, v in per_req.items() if v == "SATISFIED"]
    unsatisfied = [r for r, v in per_req.items() if v != "SATISFIED"]
    permitted = not [r for r in unsatisfied if r in MANDATORY]
    return Decision(comparisons, per_req, satisfied, unsatisfied, missing, permitted)
