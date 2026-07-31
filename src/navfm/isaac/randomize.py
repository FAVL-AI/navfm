"""Domain randomisation for the visual sim2real gap.

Scope note, stated plainly: randomisation here targets the *appearance* gap
(lighting, materials, exposure, optics), not the *behaviour* gap (dynamics,
latency, odometry drift). GNM-family models consume a stack of RGB frames and
emit geometric waypoints; their dominant failure mode when transferred from
simulation is photometric, not dynamic. Dynamics randomisation is handled in
the collector (velocity noise, actuation delay) because it must be applied per
control step rather than per episode.

Per-episode randomisation (lighting, materials) is applied on scene reset.
Per-frame randomisation (sensor noise, exposure jitter) is applied at capture.
Keeping them separate matters: a policy conditioned on a 5-frame context
learns to reject *temporally incoherent* noise trivially, so per-frame
appearance randomisation must stay small or it does nothing but blur the input.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

__all__ = ["RandomizationConfig", "SceneRandomizer", "apply_sensor_noise"]


@dataclasses.dataclass
class RandomizationConfig:
    enabled: bool = True

    # -- per episode --
    light_intensity_range: tuple[float, float] = (300.0, 3000.0)
    light_temperature_range: tuple[float, float] = (2700.0, 7500.0)
    dome_light_prob: float = 0.6
    randomize_materials: bool = True
    material_roughness_range: tuple[float, float] = (0.1, 0.9)
    texture_urls: tuple[str, ...] = ()
    #: Camera mount perturbation, modelling real mounting tolerance. Small on
    #: purpose: the physical camera is bolted, not hand-held.
    camera_pos_jitter_m: float = 0.015
    camera_rot_jitter_deg: float = 2.0

    # -- per frame --
    gaussian_noise_std: float = 0.006
    exposure_jitter: float = 0.06
    motion_blur_prob: float = 0.0
    jpeg_quality_range: tuple[int, int] = (88, 96)

    seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class SceneRandomizer:
    """Replicator-based per-episode randomisation.

    Uses the trigger/event pattern rather than ``rep.trigger.on_frame`` so that
    randomisation fires exactly when we ask, keeping episodes reproducible from
    the seed alone.
    """

    def __init__(self, config: RandomizationConfig, rng: np.random.Generator | None = None) -> None:
        self.config = config
        self.rng = rng or np.random.default_rng(config.seed)
        self._rep: Any = None
        self._registered = False

    def _ensure(self) -> Any:
        if self._rep is None:
            import omni.replicator.core as rep

            self._rep = rep
        return self._rep

    def register(self) -> None:
        """Build the randomisation graphs once per stage."""
        if not self.config.enabled or self._registered:
            return
        rep = self._ensure()
        cfg = self.config

        with rep.trigger.on_custom_event(event_name="navfm_randomize_lights"):
            rep.create.light(
                light_type="Dome",
                intensity=rep.distribution.uniform(*cfg.light_intensity_range),
                temperature=rep.distribution.uniform(*cfg.light_temperature_range),
            )
            rep.create.light(
                light_type="Distant",
                intensity=rep.distribution.uniform(*cfg.light_intensity_range),
                rotation=rep.distribution.uniform((-70, -180, 0), (-20, 180, 0)),
            )
        self._registered = True

    def randomize_episode(self) -> dict[str, Any]:
        """Fire one round of per-episode randomisation; return what was applied."""
        if not self.config.enabled:
            return {"enabled": False}
        rep = self._ensure()
        self.register()
        rep.utils.send_og_event(event_name="navfm_randomize_lights")
        return {
            "enabled": True,
            "camera_pos_jitter_m": float(self.rng.normal(0.0, self.config.camera_pos_jitter_m)),
            "camera_rot_jitter_deg": float(self.rng.normal(0.0, self.config.camera_rot_jitter_deg)),
        }


def apply_sensor_noise(
    rgb: np.ndarray, config: RandomizationConfig, rng: np.random.Generator
) -> np.ndarray:
    """Per-frame photometric perturbation, applied after capture.

    Deliberately mild. The purpose is to prevent the encoder from latching onto
    the renderer's noise-free statistics, not to simulate a bad camera.
    """
    if not config.enabled:
        return rgb
    x = rgb.astype(np.float32) / 255.0
    if config.exposure_jitter > 0:
        x *= float(np.exp(rng.normal(0.0, config.exposure_jitter)))
    if config.gaussian_noise_std > 0:
        x += rng.normal(0.0, config.gaussian_noise_std, size=x.shape).astype(np.float32)
    return np.clip(x * 255.0, 0, 255).astype(np.uint8)
