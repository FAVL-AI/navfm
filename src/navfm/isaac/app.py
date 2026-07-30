"""Isaac Sim bootstrap with deterministic, lag-free (image, pose, time) capture.

Written against **Isaac Sim 6.0.1** (June 2026) with a compatibility shim for
5.0/5.1. The namespace has moved twice: ``omni.isaac.*`` -> ``isaacsim.*`` at
4.5, then Core -> ``isaacsim.core.experimental.*`` and sensors ->
``isaacsim.sensors.experimental.rtx`` at 6.0. Anything you find online older
than mid-2026 will not import.

The whole point of this module is the *synchronisation contract*. Getting a
GNM-format trajectory right means every ``t.jpg`` must correspond to
``position[t]`` and ``yaw[t]`` at the same simulated instant. Three things
break that by default:

1. **Frames in flight.** The RTX renderer pipelines ~3 frames. Reading a pose
   right after ``app.update()`` pairs it with an image from ~3 steps earlier.
   Fixed by ``rep.orchestrator.step(wait_for_render=True)``, which blocks until
   the current frame is rendered.
2. **Clock drift.** Isaac Sim 6.0 has three independent clocks (run loop,
   physics, renderer). If ``physics_dt != render_dt`` the timeline and physics
   times diverge within a physics step. Fixed by setting them equal via
   ``SimulationManager.setup_simulation(dt)`` and ``RenderingManager.set_dt(dt)``
   as a pair, and by *only* reading time from
   ``SimulationManager.get_simulation_time()``.
3. **Cold start.** The first frames after ``timeline.play()`` come out of an
   unwarmed frames-in-flight buffer and are dark or ghosted. Fixed by
   discarding a configurable warm-up burst.

A known 6.0 crash makes changing the step rate in the full UI app fatal, so
this module is headless-standalone only. That is also what you want for
throughput.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
from typing import Any

__all__ = ["IsaacApp", "SimConfig", "isaac_available"]


def isaac_available() -> bool:
    """True if the Isaac Sim Python package is importable in this interpreter."""
    try:  # pragma: no cover - environment dependent
        import isaacsim  # noqa: F401
    except Exception:
        return False
    return True


@dataclasses.dataclass
class SimConfig:
    """Everything that affects determinism, in one object that gets serialised
    into every trajectory's metadata."""

    #: Physics == render == run-loop rate. 12 Hz divides evenly by 3 to give the
    #: 4 Hz policy rate the reference deployment stack uses, and stays under the
    #: real DaBai DCW2's 15 fps ceiling.
    hz: float = 12.0
    headless: bool = True
    #: Capture resolution *before* the 4:3 crop. 640x480 is already 4:3, so the
    #: crop is a no-op and no field of view is thrown away.
    resolution: tuple[int, int] = (640, 480)
    #: Extra re-renders of the same frame; kills ghosting after teleports.
    rt_subframes: int = 4
    #: Frames discarded after play() to flush the frames-in-flight buffer.
    warmup_frames: int = 8
    #: DLSS execMode 2 == Quality. The default (Performance) produces visible
    #: artefacts below ~600x600, which is exactly our regime.
    dlss_quality: bool = True
    physics_substeps: int = 1
    seed: int = 0
    renderer: str = "RayTracedLighting"

    @property
    def dt(self) -> float:
        return 1.0 / float(self.hz)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["dt"] = self.dt
        return d


class IsaacApp:
    """Context manager owning the ``SimulationApp`` lifetime.

    ``SimulationApp`` must be constructed before *any* other Omniverse import;
    every Isaac import in this package is therefore deferred to inside methods.

        with IsaacApp(SimConfig(hz=12.0)) as app:
            app.open_stage(usd_path)
            ...
            app.warmup()
            while ...:
                t = app.step()          # blocks until the frame is rendered
    """

    def __init__(self, config: SimConfig | None = None, **kwargs: Any) -> None:
        self.config = config or SimConfig()
        self._extra = kwargs
        self.app: Any = None
        self._timeline: Any = None
        self._rep: Any = None
        self._sim_manager: Any = None
        self._version: tuple[int, int] | None = None

    # -- lifecycle -------------------------------------------------------

    def __enter__(self) -> IsaacApp:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
        from isaacsim import SimulationApp

        launch = {
            "headless": self.config.headless,
            "renderer": self.config.renderer,
            "width": self.config.resolution[0],
            "height": self.config.resolution[1],
        }
        launch.update(self._extra)
        self.app = SimulationApp(launch)

        import carb
        import omni.replicator.core as rep
        import omni.timeline

        self._rep = rep
        self._timeline = omni.timeline.get_timeline_interface()

        settings = carb.settings.get_settings()
        # Capture only when we explicitly step, never on play.
        rep.orchestrator.set_capture_on_play(False)
        if self.config.dlss_quality:
            settings.set("/rtx/post/dlss/execMode", 2)
        settings.set("/app/runLoops/main/rateLimitEnabled", True)
        settings.set("/app/runLoops/main/rateLimitFrequency", round(self.config.hz))
        settings.set("/omni/replicator/RTSubframes", int(self.config.rt_subframes))

        self._configure_rates()
        self._seed_everything()

    def _configure_rates(self) -> None:
        """Pin physics, render and run-loop dt to the same value."""
        dt = self.config.dt
        try:  # Isaac Sim 6.0 path
            from isaacsim.core.rendering_manager import RenderingManager
            from isaacsim.core.simulation_manager import SimulationManager

            SimulationManager.setup_simulation(dt=dt)
            RenderingManager.set_dt(dt)
            self._sim_manager = SimulationManager
            self._version = (6, 0)
        except ImportError:  # Isaac Sim 5.x fallback
            from isaacsim.core.api import SimulationContext

            ctx = SimulationContext.instance() or SimulationContext(
                physics_dt=dt, rendering_dt=dt, stage_units_in_meters=1.0
            )
            ctx.set_simulation_dt(physics_dt=dt, rendering_dt=dt)
            self._sim_manager = ctx
            self._version = (5, 0)

    def _seed_everything(self) -> None:
        import random

        import numpy as np

        random.seed(self.config.seed)
        np.random.seed(self.config.seed)
        with contextlib.suppress(Exception):  # older Replicator lacks the helper
            self._rep.set_global_seed(self.config.seed)

    def close(self) -> None:
        if self._timeline is not None:
            with contextlib.suppress(Exception):
                self._timeline.stop()
        if self.app is not None:
            self.app.close()
            self.app = None

    # -- stage -----------------------------------------------------------

    def open_stage(self, usd_path: str) -> None:
        import omni.usd

        ctx = omni.usd.get_context()
        ctx.open_stage(usd_path)
        while ctx.get_stage_loading_status()[2] > 0:
            self.app.update()

    def assets_root(self) -> str:
        from isaacsim.storage.native import get_assets_root_path

        root = get_assets_root_path()
        if root is None:
            raise RuntimeError(
                "Isaac Sim asset root is unreachable. Either restore network access to "
                "the S3 asset bucket or install the local Assets Pack and set "
                "ISAACSIM_ASSET_ROOT / persistent.isaac.asset_root.default."
            )
        return root

    # -- stepping --------------------------------------------------------

    def play(self) -> None:
        self._timeline.play()
        self.app.update()

    def warmup(self) -> None:
        """Flush the frames-in-flight buffer so the first captured frame is valid."""
        for _ in range(self.config.warmup_frames):
            self.step()

    def step(self) -> float:
        """Advance exactly one synchronised frame; return simulation time (s).

        Blocks until the renderer has finished the frame, so any sensor read or
        pose read performed *after* this returns refers to the same instant.
        """
        self._rep.orchestrator.step(
            rt_subframes=self.config.rt_subframes, delta_time=self.config.dt, pause_timeline=False
        )
        return self.sim_time()

    def sim_time(self) -> float:
        """Authoritative timestamp. Never use ``omni.timeline`` time for this."""
        if self._version == (6, 0):
            return float(self._sim_manager.get_simulation_time())
        return float(self._sim_manager.current_time)
