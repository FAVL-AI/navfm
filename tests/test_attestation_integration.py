"""The engineering entry point must CALL the attestation path, not just import it.

Two kinds of evidence here, labelled so they are not confused:

* behavioural -- ``attest_and_record`` is driven with TEST_DOUBLE runtime objects
  and its effects on the evidence record are asserted;
* static wiring -- the collector's ``main()`` is parsed and the call is located
  inside the engineering branch.

Neither is a live Isaac read-back. Live verification is tracked separately.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from navfm.collection import attestation as att

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "collect_bo10_trajectory.py"
TD = att.Provenance.TEST_DOUBLE


def _collector():
    spec = importlib.util.spec_from_file_location("collect_bo10_trajectory", SCRIPT)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Cam:
    prim_path = "/World/Robot/base_link/Camera_front"
    def __init__(self, fov_deg: float = 64.0): self._fov = math.radians(fov_deg)
    def get_focal_length(self): return 24.0
    def get_horizontal_aperture(self): return 20.955
    def get_vertical_aperture(self): return 15.2908
    def get_clipping_range(self): return (0.01, 1000000.0)
    def get_horizontal_fov(self): return self._fov
    def get_render_product_path(self): return "/Render/RenderProduct_Replicator"


class _Art:
    prim_path = "/World/Robot"
    def get_world_poses(self):
        return (np.array([[1.0, 2.0, 0.061]]), np.array([[1.0, 0.0, 0.0, 0.0]]))


class _Settings:
    def __init__(self, sub=4, dlss=2): self._v = {
        "/rtx/post/dlss/execMode": dlss, "/omni/replicator/RTSubframes": sub,
        "/rtx/rendermode": "RaytracedLighting",
        "/app/renderer/resolution/width": 640, "/app/renderer/resolution/height": 480}
    def get(self, k): return self._v.get(k)


def _handles(mod, tmp_path: Path, *, sub=4, fov=64.0, full=True) -> Any:
    return att.RuntimeHandles(
        repo=REPO,
        influencing_files=[REPO / f for f in mod.INFLUENCING_FILES],
        camera=_Cam(fov), articulation=_Art(), settings=_Settings(sub=sub),
        render_product_camera_target_reader=lambda p: _Cam.prim_path,
        render_product_resolution_reader=lambda p: (640, 480),
        sim_time_at_command=2.0 if full else None,
        sim_time_at_capture=2.0833333 if full else None,
        goal_capture_sim_time=1.5 if full else None,
        frame=np.full((4, 4, 3), 120, np.uint8) if full else None,
        metadata={"sim": {"physics_substeps": 1}},
    )


METADATA = {"sim": {"rt_subframes": 4, "dlss_quality": True, "physics_substeps": 1},
            "robot": {"camera": {"horizontal_fov_deg": 64.0}}}


# --------------------------------------------------------------------------
# behavioural: the seam really runs the readers and the gate
# --------------------------------------------------------------------------

def test_seam_invokes_every_reader_and_records_the_decision(tmp_path: Path) -> None:
    mod = _collector()
    rec: dict[str, Any] = {}
    decision = mod.attest_and_record(rec, _handles(mod, tmp_path), "run_x", METADATA, TD,
                                     tmp_path / "blocked.json")
    assert set(rec["attestation"]["per_requirement"]) == set(att.REQUIREMENTS)
    observed = {o["requirement"] for o in rec["attestation"]["observations"]}
    assert observed == set(att.REQUIREMENTS), "a reader for some requirement never ran"
    assert rec["attestation"]["run_id"] == "run_x"
    assert decision.scientific_collection_permitted is True
    assert rec["SCIENTIFIC_COLLECTION_ELIGIBILITY"] == "ATTESTATION_SATISFIED_NOT_AN_ADMISSION"
    assert not (tmp_path / "blocked.json").exists()


def test_seam_marks_test_double_provenance(tmp_path: Path) -> None:
    """A test-double pass must never read as a live read-back."""
    mod = _collector()
    rec: dict[str, Any] = {}
    mod.attest_and_record(rec, _handles(mod, tmp_path), "run_x", METADATA, TD, None)
    assert rec["attestation"]["test_double_present"] is True
    provs = {o["provenance"] for o in rec["attestation"]["observations"]}
    assert "TEST_DOUBLE" in provs


def test_seam_blocks_and_writes_a_durable_failure_record(tmp_path: Path) -> None:
    mod = _collector()
    rec: dict[str, Any] = {}
    out = tmp_path / "nested" / "blocked.json"
    decision = mod.attest_and_record(rec, _handles(mod, tmp_path, sub=1), "run_y",
                                     METADATA, TD, out)
    assert decision.scientific_collection_permitted is False
    assert rec["SCIENTIFIC_COLLECTION_ELIGIBILITY"] == "BLOCKED_BY_UNSATISFIED_ATTESTATION"
    assert "R4" in rec["attestation_block_reason"]["unsatisfied"]
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["check"] == "ATTESTATION_BLOCKED"
    assert payload["run_id"] == "run_y"
    assert "R4" in payload["unsatisfied"]


def test_precondition_only_pass_leaves_collection_blocked(tmp_path: Path) -> None:
    """R5 and R7 need per-step wiring; without it the gate must still block."""
    mod = _collector()
    rec: dict[str, Any] = {}
    decision = mod.attest_and_record(rec, _handles(mod, tmp_path, full=False), "run_z",
                                     METADATA, TD, None)
    assert decision.per_requirement["R5"] == "UNRESOLVED"
    assert decision.per_requirement["R7"] == "UNRESOLVED"
    assert decision.scientific_collection_permitted is False
    # and the resolvable preconditions still resolved, so this is not a blanket failure
    assert decision.per_requirement["R2"] == "SATISFIED"
    assert decision.per_requirement["R6"] == "SATISFIED"


def test_requested_values_are_read_from_the_collector_metadata() -> None:
    req = att.requested_values(METADATA)
    assert req == {"R2.horizontal_fov": 64.0, "R4.rt_subframes": 4, "R4.dlss_exec_mode": True}
    # a metadata block missing them yields None, which the gate treats as unresolved
    assert att.requested_values({}) == {"R2.horizontal_fov": None, "R4.rt_subframes": None,
                                        "R4.dlss_exec_mode": None}


def test_mismatch_preserves_the_requested_value_in_the_record(tmp_path: Path) -> None:
    mod = _collector()
    rec: dict[str, Any] = {}
    mod.attest_and_record(rec, _handles(mod, tmp_path, fov=90.0), "run_m", METADATA, TD, None)
    fov = next(c for c in rec["attestation"]["comparisons"] if c["name"] == "horizontal_fov")
    assert fov["verdict"] == "MISMATCH"
    assert fov["requested"] == 64.0, "the requested value must survive a mismatch unchanged"


# --------------------------------------------------------------------------
# static wiring: main() calls the seam, inside the engineering branch
# --------------------------------------------------------------------------

def test_main_calls_attest_and_record() -> None:
    tree = ast.parse(SCRIPT.read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [n for n in ast.walk(main)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "attest_and_record"]
    assert len(calls) == 1, "main() must call the attestation seam exactly once"


def test_the_call_is_gated_on_engineering_mode() -> None:
    """It must not alter the default scientific collection path."""
    tree = ast.parse(SCRIPT.read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    gated = False
    for node in ast.walk(main):
        if not isinstance(node, ast.If):
            continue
        src = ast.dump(node.test)
        if "engineering_step_cap" not in src:
            continue
        if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
               and c.func.id == "attest_and_record" for c in ast.walk(node)):
            gated = True
    assert gated, "the attestation call must sit inside an engineering_step_cap branch"


def test_influencing_files_all_exist() -> None:
    mod = _collector()
    missing = [f for f in mod.INFLUENCING_FILES if not (REPO / f).is_file()]
    assert not missing, f"declared influencing files absent: {missing}"
    assert "src/navfm/collection/attestation.py" in mod.INFLUENCING_FILES


def test_r1_pins_the_attestation_code_itself() -> None:
    """The reader that attests source identity must itself be pinned."""
    mod = _collector()
    obs = {o.name: o for o in att.read_source_identity(
        REPO, [REPO / f for f in mod.INFLUENCING_FILES])}
    digests = obs["influencing_file_digests"].value
    assert any("attestation.py" in k for k in digests)
    assert any("attestation_gate.py" in k for k in digests)
    assert all(len(v) == 64 for v in digests.values())


def test_default_path_does_not_import_or_call_attestation() -> None:
    """Scientific default behaviour is unchanged: the seam is engineering-only."""
    src = SCRIPT.read_text()
    # the only call site is inside the gated branch, asserted above; here we check
    # the module does not attest at import time
    tree = ast.parse(src)
    toplevel_calls = [n for n in tree.body if isinstance(n, ast.Expr)
                      and isinstance(n.value, ast.Call)]
    assert not any(isinstance(c.value.func, ast.Name) and c.value.func.id == "attest_and_record"
                   for c in toplevel_calls)


def test_consumed_fields_are_not_marked_intent_only(tmp_path):
    from dataclasses import replace
    mod = _collector()
    handles = replace(_handles(mod, tmp_path), intent_only_fields=("sim.seed",))
    observations = att.collect_all(handles, run_id="prospective", provenance=TD)
    annotation = next(o.value for o in observations if o.name == "intent_field_annotation")
    assert "sim.physics_substeps" not in annotation["declared_intent_only"]
