"""Runtime attestation readers: observe what the simulator actually did.

The BO-10 metadata-to-runtime audit found that eight recorded configuration
fields were never applied by the code path that ran, because the collector
bypassed ``IsaacApp.start()``. The record said ``rt_subframes=4``; nothing set
it. The central defect was that **a setting written into a record became a claim
that the running system used it.**

This module exists so that cannot happen again. Its only job is to *observe*. It
never sees the requested value, so it cannot fall back to one: an
:class:`Observation` has no ``requested`` field, and ``value`` stays ``None``
unless ``status`` is ``OBSERVED``. Comparison against intent lives in
:mod:`navfm.collection.attestation_gate`, deliberately in a different module.

The readers implement the eight requirements in
``prospective_attestation_requirements.md`` (sha256
a8c6bd34d64cb5559097e620cd36ac14f56e3c628890cc6d18fc627b8f1551eb), keeping that
file's identifiers R1..R8.

Nothing here is a physical measurement. Every reader returns a software
read-back of a simulator or filesystem object, which is not hardware
calibration and must never be described as one.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import math
import subprocess
from pathlib import Path
from typing import Any

#: The requirements document these readers implement, bound by content hash.
REQUIREMENTS_SHA256 = "a8c6bd34d64cb5559097e620cd36ac14f56e3c628890cc6d18fc627b8f1551eb"

#: Requirement identifiers, in the source document's order.
REQUIREMENTS = ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8")


class Status(str, enum.Enum):
    """Outcome of an attempted observation.

    Only ``OBSERVED`` carries a value. Every other member means *we do not know*,
    and the gate must treat it as unresolved rather than substituting intent.
    """

    OBSERVED = "OBSERVED"
    FAILED_OBJECT_ABSENT = "FAILED_OBJECT_ABSENT"
    FAILED_NOT_INITIALISED = "FAILED_NOT_INITIALISED"
    FAILED_GETTER_RAISED = "FAILED_GETTER_RAISED"
    FAILED_NONFINITE = "FAILED_NONFINITE"
    UNRESOLVED_NO_SUPPORTED_ROUTE = "UNRESOLVED_NO_SUPPORTED_ROUTE"


class Provenance(str, enum.Enum):
    """Where the observation came from. Never inferred -- always declared."""

    LIVE_RUNTIME = "LIVE_RUNTIME"
    #: A stand-in used by tests. Proves reader/comparator behaviour only; it is
    #: NOT evidence that a real Isaac read-back succeeded.
    TEST_DOUBLE = "TEST_DOUBLE"
    FILESYSTEM = "FILESYSTEM"


@dataclasses.dataclass(frozen=True)
class Observation:
    """One observed quantity.

    Deliberately holds no requested/configured value. A reader cannot see intent,
    so no reader can implement ``observed = read() or requested``.
    """

    requirement: str
    name: str
    status: Status
    value: Any
    getter: str
    runtime_object: str
    lifecycle_point: str
    provenance: Provenance
    detail: str = ""
    units: str = ""
    #: Identity of the run this observation belongs to. The gate refuses an
    #: observation carrying a different run id, so a sample from another run
    #: cannot be admitted as this run's evidence.
    run_id: str = ""

    def __post_init__(self) -> None:
        if self.status is not Status.OBSERVED and self.value is not None:
            raise ValueError(
                f"{self.requirement}/{self.name}: a non-OBSERVED status must carry "
                f"value None, got {self.value!r} with {self.status.value}"
            )
        if self.requirement not in REQUIREMENTS:
            raise ValueError(f"unknown requirement id {self.requirement!r}")

    @property
    def resolved(self) -> bool:
        return self.status is Status.OBSERVED

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["status"] = self.status.value
        d["provenance"] = self.provenance.value
        return d


def _fail(req: str, name: str, status: Status, getter: str, obj: str,
          point: str, prov: Provenance, detail: str) -> Observation:
    return Observation(requirement=req, name=name, status=status, value=None,
                       getter=getter, runtime_object=obj, lifecycle_point=point,
                       provenance=prov, detail=detail)


def _read(req: str, name: str, obj: Any, getter: str, point: str,
          prov: Provenance, units: str = "", finite: bool = False) -> Observation:
    """Call one getter on the real consuming object and classify the outcome."""
    target = f"{type(obj).__name__} @ {getattr(obj, 'prim_path', '<no prim_path>')}"
    if obj is None:
        return _fail(req, name, Status.FAILED_OBJECT_ABSENT, getter, "None", point, prov,
                     "the consuming object does not exist")
    fn = getattr(obj, getter, None)
    if fn is None:
        return _fail(req, name, Status.UNRESOLVED_NO_SUPPORTED_ROUTE, getter, target, point,
                     prov, f"{type(obj).__name__} exposes no {getter}() on this Isaac version")
    try:
        value = fn()
    except Exception as exc:  # a getter on an uninitialised object commonly raises
        return _fail(req, name, Status.FAILED_GETTER_RAISED, getter, target, point, prov,
                     f"{type(exc).__name__}: {exc}")
    if value is None:
        return _fail(req, name, Status.FAILED_NOT_INITIALISED, getter, target, point, prov,
                     "getter returned None; the runtime object is not initialised")
    if finite:
        flat = value if isinstance(value, (list, tuple)) else [value]
        try:
            if not all(math.isfinite(float(v)) for v in flat):
                return _fail(req, name, Status.FAILED_NONFINITE, getter, target, point,
                             prov, f"non-finite value {value!r}")
        except (TypeError, ValueError):
            return _fail(req, name, Status.FAILED_NONFINITE, getter, target, point, prov,
                         f"value {value!r} is not numeric")
    if isinstance(value, tuple):
        value = list(value)
    return Observation(requirement=req, name=name, status=Status.OBSERVED, value=value,
                       getter=f"{getter}()", runtime_object=target, lifecycle_point=point,
                       provenance=prov, units=units,
                       detail="software read-back of the simulator object; not a physical measurement")


# ---------------------------------------------------------------------------
# R1. Source identity in the evidence artefact
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def read_source_identity(repo: Path, influencing_files: list[Path],
                         provenance: Provenance = Provenance.FILESYSTEM) -> list[Observation]:
    """R1: repository HEAD, dirty flag, and a SHA-256 per influencing file.

    The audited run recorded none of these, and the code it executed was
    uncommitted, so a HEAD alone would have been misleading. The per-file hashes
    are what make the executed source identifiable when the checkout is dirty --
    HEAD must never be presented as the executed source on a dirty tree.
    """
    point = "before collection begins"

    def git(*args: str) -> tuple[int, str]:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        return p.returncode, p.stdout.strip()

    out: list[Observation] = []
    rc, head = git("rev-parse", "HEAD")
    if rc != 0 or not head:
        out.append(_fail("R1", "repository_head", Status.FAILED_GETTER_RAISED,
                         "git rev-parse HEAD", str(repo), point, provenance,
                         "git rev-parse failed"))
    else:
        out.append(Observation("R1", "repository_head", Status.OBSERVED, head,
                               "git rev-parse HEAD", str(repo), point, provenance))
    rc, porcelain = git("status", "--porcelain", "--untracked-files=all")
    if rc != 0:
        out.append(_fail("R1", "worktree_dirty", Status.FAILED_GETTER_RAISED,
                         "git status --porcelain", str(repo), point, provenance,
                         "git status failed"))
    else:
        dirty = bool(porcelain.strip())
        out.append(Observation("R1", "worktree_dirty", Status.OBSERVED, dirty,
                               "git status --porcelain --untracked-files=all", str(repo),
                               point, provenance,
                               detail=("dirty: HEAD alone does not identify the executed source, "
                                       "so the per-file hashes below are load-bearing")
                               if dirty else "clean"))
    digests: dict[str, str] = {}
    missing: list[str] = []
    for f in influencing_files:
        rel = str(Path(f))
        d = sha256_file(Path(f))
        if d is None:
            missing.append(rel)
        else:
            digests[rel] = d
    if missing:
        out.append(_fail("R1", "influencing_file_digests", Status.FAILED_OBJECT_ABSENT,
                         "sha256_file", ", ".join(missing), point, provenance,
                         f"{len(missing)} declared influencing file(s) unreadable"))
    elif not digests:
        out.append(_fail("R1", "influencing_file_digests", Status.UNRESOLVED_NO_SUPPORTED_ROUTE,
                         "sha256_file", "<empty list>", point, provenance,
                         "no influencing files were declared, so the executed source is not pinned"))
    else:
        out.append(Observation("R1", "influencing_file_digests", Status.OBSERVED, digests,
                               "sha256_file", f"{len(digests)} declared files", point, provenance))
    return out


# ---------------------------------------------------------------------------
# R2. Composed camera attributes, read back after initialize()
# ---------------------------------------------------------------------------

#: Real getters on isaacsim.sensors.camera.Camera (verified against the installed
#: 5.1.0.0 source, not guessed): name -> (getter, units, finite-checked)
CAMERA_ATTRIBUTES: tuple[tuple[str, str, str, bool], ...] = (
    ("focal_length", "get_focal_length", "stage units", True),
    ("horizontal_aperture", "get_horizontal_aperture", "stage units", True),
    ("vertical_aperture", "get_vertical_aperture", "stage units", True),
    ("clipping_range", "get_clipping_range", "stage units", True),
    ("horizontal_fov", "get_horizontal_fov", "rad", True),
)


def read_camera_attributes(camera: Any,
                           provenance: Provenance = Provenance.LIVE_RUNTIME) -> list[Observation]:
    """R2: the composed USD camera attributes, after the camera exists.

    Read from the camera object the collector actually uses, never from a second
    camera built for the validator. ``horizontal_fov`` is included because it is
    the quantity the audited metadata claimed (``horizontal_fov_deg``) and never
    applied; a read-back is the only thing that can state it.

    These attributes can be re-authored later in a run, so this observation
    establishes the composed state at the lifecycle point recorded on it, not for
    all time.
    """
    point = "after Camera.initialize()"
    out = [
        _read("R2", name, camera, getter, point, provenance, units=units, finite=finite)
        for name, getter, units, finite in CAMERA_ATTRIBUTES
    ]
    prim = getattr(camera, "prim_path", None)
    if prim:
        out.append(Observation("R2", "resolved_prim_path", Status.OBSERVED, str(prim),
                               "Camera.prim_path", f"{type(camera).__name__}", point, provenance))
    else:
        out.append(_fail("R2", "resolved_prim_path", Status.FAILED_OBJECT_ABSENT,
                         "Camera.prim_path", f"{type(camera).__name__}", point, provenance,
                         "no prim_path attribute"))
    return out


# ---------------------------------------------------------------------------
# R3. Render product identity
# ---------------------------------------------------------------------------

def read_render_product(camera: Any, camera_target_reader: Any = None,
                        resolution_reader: Any = None,
                        provenance: Provenance = Provenance.LIVE_RUNTIME) -> list[Observation]:
    """R3: the render product's camera target and resolution, as the runtime reports them.

    This separates "the camera I configured" from "the camera that was rendered".
    The two readers correspond to
    ``isaacsim.core.utils.render_product.get_camera_prim_path`` and
    ``.get_resolution``; they are injected so the caller binds the real
    installation and tests can supply a double.
    """
    point = "after render product creation"
    out: list[Observation] = []
    rp = _read("R3", "render_product_path", camera, "get_render_product_path", point, provenance)
    out.append(rp)
    if not rp.resolved:
        for name in ("render_product_camera_target", "render_product_resolution"):
            out.append(_fail("R3", name, Status.FAILED_NOT_INITIALISED,
                             "render_product utils", "unknown render product", point, provenance,
                             "the render product path itself is unresolved, so its "
                             "properties cannot be read"))
        return out
    path = rp.value
    for name, reader, getter in (
        ("render_product_camera_target", camera_target_reader, "render_product.get_camera_prim_path"),
        ("render_product_resolution", resolution_reader, "render_product.get_resolution"),
    ):
        if reader is None:
            out.append(_fail("R3", name, Status.UNRESOLVED_NO_SUPPORTED_ROUTE, getter,
                             str(path), point, provenance,
                             "no reader was bound for this installation"))
            continue
        try:
            value = reader(path)
        except Exception as exc:
            out.append(_fail("R3", name, Status.FAILED_GETTER_RAISED, getter, str(path),
                             point, provenance, f"{type(exc).__name__}: {exc}"))
            continue
        if value is None:
            out.append(_fail("R3", name, Status.FAILED_NOT_INITIALISED, getter, str(path),
                             point, provenance, "reader returned None"))
            continue
        # The installed 5.1 utility returns a pxr.Sdf.Path for the camera
        # target. It cannot be deep-copied/pickled by dataclasses.asdict;
        # preserve its actual path text at the API boundary.
        if name == "render_product_camera_target":
            value = str(value)
        elif name == "render_product_resolution":
            value = [int(v) for v in value]
        out.append(Observation("R3", name, Status.OBSERVED,
                               list(value) if isinstance(value, tuple) else value,
                               getter, str(path), point, provenance))
    return out


# ---------------------------------------------------------------------------
# R4. Effective renderer and RTX settings, read back after all overrides
# ---------------------------------------------------------------------------

#: carb setting keys the audit named, plus the renderer and launch resolution.
SETTING_KEYS: tuple[tuple[str, str], ...] = (
    ("dlss_exec_mode", "/rtx/post/dlss/execMode"),
    ("rt_subframes", "/omni/replicator/RTSubframes"),
    # SimulationApp 5.1 _configure_renderer authors this effective RTX mode.
    ("active_renderer", "/rtx/rendermode"),
    ("launch_width", "/app/renderer/resolution/width"),
    ("launch_height", "/app/renderer/resolution/height"),
)


def read_effective_settings(settings: Any,
                            provenance: Provenance = Provenance.LIVE_RUNTIME) -> list[Observation]:
    """R4: effective carb settings, read AFTER startup and any later overrides.

    Five audited fields described ``IsaacApp.start()``, which the historical
    collector never called. A setting that is absent reads as unresolved here: no
    default is assumed, because the audit explicitly declined to assert what
    Kit's defaults were.
    """
    point = "after app startup and all setting overrides"
    out: list[Observation] = []
    if settings is None:
        return [_fail("R4", name, Status.FAILED_OBJECT_ABSENT, f"settings.get({key})",
                      "None", point, provenance, "no carb settings interface")
                for name, key in SETTING_KEYS]
    for name, key in SETTING_KEYS:
        try:
            value = settings.get(key)
        except Exception as exc:
            out.append(_fail("R4", name, Status.FAILED_GETTER_RAISED, f"settings.get({key})",
                             "carb.settings", point, provenance, f"{type(exc).__name__}: {exc}"))
            continue
        if value is None:
            out.append(_fail("R4", name, Status.UNRESOLVED_NO_SUPPORTED_ROUTE,
                             f"settings.get({key})", "carb.settings", point, provenance,
                             "setting is unset; no default is assumed on its behalf"))
            continue
        out.append(Observation("R4", name, Status.OBSERVED, value, f"settings.get({key})",
                               "carb.settings", point, provenance))
    return out


# ---------------------------------------------------------------------------
# R5. Simulation timestamps at both boundaries
# ---------------------------------------------------------------------------

def read_step_timestamps(sim_time_at_command: float | None, sim_time_at_capture: float | None,
                         clock_domain: str = "SimulationContext.current_time",
                         provenance: Provenance = Provenance.LIVE_RUNTIME) -> list[Observation]:
    """R5: sim time at command issue and at image capture, for one step.

    ``sim_time`` already attests the step cadence and is kept. This adds the two
    boundaries so command/observation alignment is attested rather than assumed.

    Both samples must come from the same clock, named in ``clock_domain``. The
    gap between them is NOT camera-to-actuator latency: it is the simulated
    interval between two reads of one clock, and nothing here measures hardware.
    """
    point = "per step, at command issue and at image capture"
    out: list[Observation] = []
    for name, value in (("sim_time_at_command", sim_time_at_command),
                        ("sim_time_at_capture", sim_time_at_capture)):
        if value is None:
            out.append(_fail("R5", name, Status.FAILED_NOT_INITIALISED, clock_domain,
                             clock_domain, point, provenance, "no sample was taken"))
            continue
        try:
            f = float(value)
        except (TypeError, ValueError):
            out.append(_fail("R5", name, Status.FAILED_NONFINITE, clock_domain, clock_domain,
                             point, provenance, f"{value!r} is not numeric"))
            continue
        if not math.isfinite(f):
            out.append(_fail("R5", name, Status.FAILED_NONFINITE, clock_domain, clock_domain,
                             point, provenance, f"non-finite {f!r}"))
            continue
        out.append(Observation("R5", name, Status.OBSERVED, f, clock_domain, clock_domain,
                               point, provenance, units="s",
                               detail="simulated time; not a wall-clock or hardware latency"))
    return out


def read_goal_capture_time(sim_time: float | None,
                           clock_domain: str = "SimulationContext.current_time",
                           provenance: Provenance = Provenance.LIVE_RUNTIME) -> Observation:
    """R5: the goal image's capture sim time, recorded as ``None`` in the audited run."""
    point = "at goal image capture, before motion begins"
    if sim_time is None:
        return _fail("R5", "goal_capture_sim_time", Status.FAILED_NOT_INITIALISED, clock_domain,
                     clock_domain, point, provenance,
                     "not sampled; the goal capture stays off the observation timeline")
    try:
        f = float(sim_time)
    except (TypeError, ValueError):
        return _fail("R5", "goal_capture_sim_time", Status.FAILED_NONFINITE, clock_domain,
                     clock_domain, point, provenance, f"{sim_time!r} is not numeric")
    if not math.isfinite(f):
        return _fail("R5", "goal_capture_sim_time", Status.FAILED_NONFINITE, clock_domain,
                     clock_domain, point, provenance, f"non-finite {f!r}")
    return Observation("R5", "goal_capture_sim_time", Status.OBSERVED, f, clock_domain,
                       clock_domain, point, provenance, units="s")


# ---------------------------------------------------------------------------
# R6. Post-spawn pose read-back
# ---------------------------------------------------------------------------

def read_spawn_pose(articulation: Any,
                    provenance: Provenance = Provenance.LIVE_RUNTIME) -> list[Observation]:
    """R6: the articulation root pose after spawn and settling.

    ``SimRobot.pose()`` returns only ``(x, y)`` and yaw -- it discards Z, which is
    exactly the quantity ``spawn_height`` claims. So this reads
    ``get_world_poses()`` on the articulation directly and keeps all three
    components.
    """
    point = "after spawn and settling steps"
    obs = _read("R6", "_raw_world_poses", articulation, "get_world_poses", point, provenance)
    if not obs.resolved:
        return [_fail("R6", "spawn_world_position", obs.status, "get_world_poses",
                      obs.runtime_object, point, provenance, obs.detail)]
    # get_world_poses() -> (positions, orientations); positions is (N, 3).
    try:
        positions = obs.value[0]
        first = positions[0]
        xyz = [float(first[0]), float(first[1]), float(first[2])]
    except Exception as exc:
        return [_fail("R6", "spawn_world_position", Status.FAILED_GETTER_RAISED,
                      "get_world_poses", obs.runtime_object, point, provenance,
                      f"unexpected pose shape {type(obs.value).__name__}: "
                      f"{type(exc).__name__}: {exc}")]
    if not all(math.isfinite(v) for v in xyz):
        return [_fail("R6", "spawn_world_position", Status.FAILED_NONFINITE, "get_world_poses",
                      obs.runtime_object, point, provenance, f"non-finite pose {xyz!r}")]
    return [
        Observation("R6", "spawn_world_position", Status.OBSERVED, xyz, "get_world_poses()[0]",
                    obs.runtime_object, point, provenance, units="m"),
        Observation("R6", "spawn_world_z", Status.OBSERVED, xyz[2], "get_world_poses()[0][2]",
                    obs.runtime_object, point, provenance, units="m",
                    detail="the component SimRobot.pose() discards; this is what spawn_height claims"),
    ]


# ---------------------------------------------------------------------------
# R7. Per-frame image statistics at capture time
# ---------------------------------------------------------------------------

#: Pixel-statistic definitions. Named so a reader of the artefact knows exactly
#: what was computed. Neither is calibrated physical luminance.
PIXEL_STATISTICS = {
    "luma_601": "ITU-R 601-2 luma, 0.299*R + 0.587*G + 0.114*B, 8-bit 0-255",
    "rgb_unweighted_mean": "arithmetic mean over all R, G and B samples, 8-bit 0-255",
}


def frame_statistic(rgb: Any, definition: str = "luma_601",
                    provenance: Provenance = Provenance.LIVE_RUNTIME) -> Observation:
    """R7: one cheap per-frame pixel statistic, with its definition stated.

    Had this existed during collection, the 109-frame dark interval in
    ``hospital_bo10_run_00000`` and the near-saturated ``hospital_bo10_run_00001``
    would have been visible on the day rather than fifteen days later.

    This is an 8-bit sRGB-encoded pixel statistic, not a photometric measurement,
    and it carries no admission threshold: the statistic is recorded, and any rule
    about it is the gate's business.
    """
    import numpy as np

    point = "at image capture, per frame"
    if definition not in PIXEL_STATISTICS:
        return _fail("R7", "frame_statistic", Status.UNRESOLVED_NO_SUPPORTED_ROUTE,
                     f"frame_statistic({definition})", "rgb array", point, provenance,
                     f"unknown definition {definition!r}; known: {sorted(PIXEL_STATISTICS)}")
    if rgb is None:
        return _fail("R7", "frame_statistic", Status.FAILED_OBJECT_ABSENT,
                     f"frame_statistic({definition})", "None", point, provenance,
                     "no frame was supplied")
    try:
        a = np.asarray(rgb)
        if a.ndim != 3 or a.shape[2] < 3:
            return _fail("R7", "frame_statistic", Status.FAILED_NONFINITE,
                         f"frame_statistic({definition})", f"array{a.shape}", point, provenance,
                         f"expected HxWx3+, got shape {a.shape}")
        f = a[:, :, :3].astype("float64")
        if definition == "luma_601":
            value = float((0.299 * f[:, :, 0] + 0.587 * f[:, :, 1] + 0.114 * f[:, :, 2]).mean())
        else:
            value = float(f.mean())
    except Exception as exc:
        return _fail("R7", "frame_statistic", Status.FAILED_GETTER_RAISED,
                     f"frame_statistic({definition})", "rgb array", point, provenance,
                     f"{type(exc).__name__}: {exc}")
    if not math.isfinite(value):
        return _fail("R7", "frame_statistic", Status.FAILED_NONFINITE,
                     f"frame_statistic({definition})", "rgb array", point, provenance,
                     "statistic is non-finite")
    return Observation("R7", "frame_statistic", Status.OBSERVED, value,
                       f"frame_statistic({definition})", "captured RGB frame", point,
                       provenance, units="8-bit level",
                       detail=f"{definition}: {PIXEL_STATISTICS[definition]}. "
                              "Not calibrated physical luminance.")


# ---------------------------------------------------------------------------
# R8. Declare which fields are intent
# ---------------------------------------------------------------------------

#: Metadata paths the audit found to have no runtime consumer on the executed
#: path. Declared, not auto-detected: consumer absence was established by reading
#: the source at the audited revision, and that judgement is recorded here rather
#: than guessed at runtime.
INTENT_ONLY_FIELDS = (
    "sim.physics_substeps",
    "sim.seed",
    "collect.episodes",
    "collect.max_stationary_fraction",
)


def annotate_intent_fields(metadata: dict[str, Any],
                           intent_only: tuple[str, ...] = INTENT_ONLY_FIELDS) -> Observation:
    """R8: mark recorded fields that have no runtime consumer as intent.

    Returns an observation whose value is the annotation to embed in the
    artefact. The input metadata is not modified: historical records are never
    rewritten, and the annotation is additive.
    """
    point = "when the evidence artefact is assembled"
    present: list[str] = []
    for path in intent_only:
        cur: Any = metadata
        for key in path.split("."):
            if not isinstance(cur, dict) or key not in cur:
                cur = None
                break
            cur = cur[key]
        if cur is not None or _path_exists(metadata, path):
            present.append(path)
    annotation = {
        "declared_intent_only": sorted(present),
        "meaning": ("these recorded fields had no runtime consumer on the executed path at the "
                    "audited revision; they state intent and must not be read as runtime evidence"),
        "declared_not_autodetected": True,
    }
    return Observation("R8", "intent_field_annotation", Status.OBSERVED, annotation,
                       "annotate_intent_fields", "evidence artefact", point,
                       Provenance.FILESYSTEM,
                       detail=f"{len(present)} of {len(intent_only)} declared paths present")


def _path_exists(metadata: dict[str, Any], path: str) -> bool:
    cur: Any = metadata
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return False
        cur = cur[key]
    return True


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class RuntimeHandles:
    """The real objects the collector already uses, bound for observation.

    Nothing here is constructed by the attestation path. Passing the collector's
    own camera, articulation and settings is the point: a validator that builds
    its own second camera would attest that camera, not the one that rendered.
    """

    repo: Path
    influencing_files: list[Path]
    camera: Any = None
    articulation: Any = None
    settings: Any = None
    render_product_camera_target_reader: Any = None
    render_product_resolution_reader: Any = None
    sim_time_at_command: float | None = None
    sim_time_at_capture: float | None = None
    goal_capture_sim_time: float | None = None
    frame: Any = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    frame_statistic_definition: str = "luma_601"


def collect_all(handles: RuntimeHandles, *, run_id: str,
                provenance: Provenance = Provenance.LIVE_RUNTIME) -> list[Observation]:
    """Run every reader for R1..R8 and stamp each observation with the run id.

    ``provenance`` is declared by the caller, never inferred. A caller using test
    doubles must pass ``Provenance.TEST_DOUBLE`` so the resulting record cannot be
    mistaken for a live Isaac read-back.
    """
    out: list[Observation] = []
    out += read_source_identity(handles.repo, handles.influencing_files)
    out += read_camera_attributes(handles.camera, provenance=provenance)
    out += read_render_product(
        handles.camera,
        camera_target_reader=handles.render_product_camera_target_reader,
        resolution_reader=handles.render_product_resolution_reader,
        provenance=provenance)
    out += read_effective_settings(handles.settings, provenance=provenance)
    out += read_step_timestamps(handles.sim_time_at_command, handles.sim_time_at_capture,
                               provenance=provenance)
    out.append(read_goal_capture_time(handles.goal_capture_sim_time, provenance=provenance))
    out += read_spawn_pose(handles.articulation, provenance=provenance)
    out.append(frame_statistic(handles.frame, handles.frame_statistic_definition,
                               provenance=provenance))
    out.append(annotate_intent_fields(handles.metadata))
    return [dataclasses.replace(o, run_id=run_id) for o in out]


def requested_values(metadata: dict[str, Any]) -> dict[str, Any]:
    """Extract the intent the gate compares against, keyed "<requirement>.<name>".

    Read from the metadata the collector already assembles. Returning a key with a
    missing value is deliberate: the gate treats a missing requested value for an
    agreement rule as unresolved rather than skipping the check.
    """
    sim = metadata.get("sim", {}) if isinstance(metadata.get("sim"), dict) else {}
    cam = {}
    robot = metadata.get("robot")
    if isinstance(robot, dict) and isinstance(robot.get("camera"), dict):
        cam = robot["camera"]
    return {
        "R2.horizontal_fov": cam.get("horizontal_fov_deg"),
        "R4.rt_subframes": sim.get("rt_subframes"),
        "R4.dlss_exec_mode": sim.get("dlss_quality"),
    }
