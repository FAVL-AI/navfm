"""The three navigation states, and the rules that keep them apart.

An ImageNav episode has exactly three states and they are not the same kind of
thing:

    START    captured once, then immutable
    CURRENT  a stream, rewritten every control step
    GOAL     captured once and *sealed* before autonomous navigation begins

The distinction is the whole point. If a final frame can be relabelled as the
goal after a rollout, an episode can be made to look successful by editing its
own definition of success -- and the resulting trajectory file is
indistinguishable from an honest one. So sealing is enforced here in the data
model rather than left to operator discipline: once ``seal_goal`` is called,
the goal cannot be replaced, and any attempt raises.

This module is deliberately free of Isaac imports. It is the contract; the panel
is a view onto it. That means it can be tested on CPU without a simulator, which
is the only way the sealing rules get exercised in CI.

**The goal pose never reaches the policy.** ``GoalState`` carries both an image
and a pose, because the evaluator needs the pose to judge whether the robot
arrived. :meth:`GoalState.policy_observation` returns the image alone, and it is
the only accessor the navigation loop is permitted to use. Keeping them in one
object with two accessors is deliberate: the alternative -- two loosely related
variables -- is how privileged state leaks into a policy without anyone deciding
to leak it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "EpisodeRecorder",
    "EpisodeReplay",
    "GoalSealedError",
    "GoalState",
    "NavigationEpisode",
    "Pose2D",
    "StateSnapshot",
    "TransformRecord",
]


class GoalSealedError(RuntimeError):
    """An attempt to change a goal after it was sealed, or to run before sealing."""


@dataclasses.dataclass(frozen=True)
class Pose2D:
    """Planar robot pose. Frozen: a captured pose is a record, not a variable."""

    x: float
    y: float
    yaw: float

    def as_list(self) -> list[float]:
        return [self.x, self.y, self.yaw]

    def distance_to(self, other: Pose2D) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def heading_error_to(self, other: Pose2D) -> float:
        """Signed smallest angle from this heading to ``other``'s, in radians."""
        d = other.yaw - self.yaw
        return math.atan2(math.sin(d), math.cos(d))


@dataclasses.dataclass(frozen=True)
class TransformRecord:
    """One frame in the robot's transform tree, as read from the stage.

    ``is_static`` distinguishes a rigid mount from a moving joint. It is what
    makes the panel able to *show* that the camera is bolted on: the camera's
    transform relative to the base must not change while its world transform
    does.
    """

    frame: str
    parent: str
    translation: tuple[float, float, float]
    rotation_rpy: tuple[float, float, float]
    is_static: bool
    source: str

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class StateSnapshot:
    """An immutable moment: where the robot was, what it saw, how it was posed."""

    label: str
    pose: Pose2D
    image_path: str | None
    image_sha256: str | None
    transforms: tuple[TransformRecord, ...]
    timestamp_utc: str
    frame_index: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "pose": self.pose.as_list(),
            "image_path": self.image_path,
            "image_sha256": self.image_sha256,
            "transforms": [t.as_dict() for t in self.transforms],
            "timestamp_utc": self.timestamp_utc,
            "frame_index": self.frame_index,
        }


@dataclasses.dataclass(frozen=True)
class GoalState:
    """A sealed goal: an image the policy may see, and a pose it may not.

    Both live here so the separation is a property of the type rather than of
    whoever wires the loop.
    """

    snapshot: StateSnapshot
    sealed_at_utc: str

    def policy_observation(self) -> str | None:
        """The ONLY accessor the navigation loop may use. Image path, no pose."""
        return self.snapshot.image_path

    def evaluation_pose(self) -> Pose2D:
        """Ground truth, for judging arrival. Never an input to the policy."""
        return self.snapshot.pose

    @property
    def image_sha256(self) -> str | None:
        return self.snapshot.image_sha256


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NavigationEpisode:
    """START, CURRENT and GOAL, with the rules that keep them from blurring."""

    def __init__(self, episode_id: str, scene: str = "", robot: str = "") -> None:
        self.episode_id = episode_id
        self.scene = scene
        self.robot = robot
        self._start: StateSnapshot | None = None
        self._goal: GoalState | None = None
        self._current: StateSnapshot | None = None
        self._history: list[StateSnapshot] = []

    # -- capture ---------------------------------------------------------
    def capture_start(self, snapshot: StateSnapshot) -> StateSnapshot:
        """Fix the start. Recapturing replaces it, which is fine *before* sealing.

        After the goal is sealed the episode is defined, so the start is frozen
        too: moving the start line after the finish line is drawn changes the
        experiment, not the setup.
        """
        if self._goal is not None:
            raise GoalSealedError(
                "the goal is sealed, so the start is fixed too. Re-capturing it now "
                "would redefine the episode after its success condition was set. "
                "Begin a new episode instead."
            )
        self._start = dataclasses.replace(snapshot, label="START")
        return self._start

    def seal_goal(self, snapshot: StateSnapshot) -> GoalState:
        """Seal the goal. Irreversible for the life of the episode."""
        if self._goal is not None:
            raise GoalSealedError(
                f"goal already sealed at {self._goal.sealed_at_utc}. A sealed goal "
                f"cannot be replaced: an episode whose target can move after the "
                f"rollout can be made to succeed by redefining success."
            )
        if self._start is None:
            raise GoalSealedError(
                "capture START before sealing GOAL. Without a start the episode has "
                "no defined beginning and 'reset to start' has nothing to restore."
            )
        if snapshot.image_path is None or snapshot.image_sha256 is None:
            raise GoalSealedError(
                "a goal must carry an image and its digest. The image is what the "
                "policy navigates toward; the digest is what proves it was not "
                "swapped afterwards."
            )
        self._goal = GoalState(
            snapshot=dataclasses.replace(snapshot, label="GOAL"), sealed_at_utc=_now()
        )
        return self._goal

    def update_current(self, snapshot: StateSnapshot) -> StateSnapshot:
        """Advance the live state. The only mutable one of the three."""
        self._current = dataclasses.replace(
            snapshot, label="CURRENT", frame_index=len(self._history)
        )
        self._history.append(self._current)
        return self._current

    # -- access ----------------------------------------------------------
    @property
    def start(self) -> StateSnapshot | None:
        return self._start

    @property
    def goal(self) -> GoalState | None:
        return self._goal

    @property
    def current(self) -> StateSnapshot | None:
        return self._current

    @property
    def history(self) -> tuple[StateSnapshot, ...]:
        return tuple(self._history)

    @property
    def is_sealed(self) -> bool:
        return self._goal is not None

    @property
    def is_ready_to_run(self) -> bool:
        return self._start is not None and self._goal is not None

    # -- predicates for a UI ---------------------------------------------
    # A panel needs to know whether a button should be enabled BEFORE the user
    # presses it. Raising is the right behaviour at the moment of action and the
    # wrong behaviour when merely drawing a widget, so both exist: these return
    # (allowed, reason) and never raise; require_ready() raises.
    def can_capture_start(self) -> tuple[bool, str]:
        if self._goal is not None:
            return False, "goal sealed -- the episode is defined; start a new one"
        return True, "ready"

    def can_seal_goal(self) -> tuple[bool, str]:
        if self._goal is not None:
            return False, f"already sealed at {self._goal.sealed_at_utc}"
        if self._start is None:
            return False, "capture START first"
        return True, "ready"

    def can_run(self) -> tuple[bool, str]:
        if self._start is None:
            return False, "no START captured"
        if self._goal is None:
            return False, "no GOAL sealed"
        return True, "ready"

    def can_reset_to_start(self) -> tuple[bool, str]:
        if self._start is None:
            return False, "no START to reset to"
        return True, "ready"

    def require_ready(self) -> None:
        """Guard the navigation loop. Refuses rather than improvising a goal."""
        if self._start is None:
            raise GoalSealedError("cannot run: START has not been captured")
        if self._goal is None:
            raise GoalSealedError(
                "cannot run: GOAL has not been sealed. Navigation toward an unsealed "
                "goal is how a final frame becomes the goal after the fact."
            )

    def distance_to_goal(self) -> float | None:
        """Evaluation only. Never fed to the policy."""
        if self._goal is None or self._current is None:
            return None
        return self._current.pose.distance_to(self._goal.evaluation_pose())

    def as_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "scene": self.scene,
            "robot": self.robot,
            "stage": "SIMULATION_DEVELOPMENT",
            "admission_status": "NOT_ADMITTED",
            "start": self._start.as_dict() if self._start else None,
            "goal": (
                {**self._goal.snapshot.as_dict(), "sealed_at_utc": self._goal.sealed_at_utc}
                if self._goal
                else None
            ),
            "frames": len(self._history),
        }


class EpisodeRecorder:
    """Writes an episode to disk in a form the replay can reconstruct exactly."""

    def __init__(self, episode: NavigationEpisode, out_dir: str | Path) -> None:
        self.episode = episode
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._rows: list[dict[str, Any]] = []

    def record_step(
        self,
        snapshot: StateSnapshot,
        *,
        control_mode: str,
        commanded: tuple[float, float, float],
        achieved: tuple[float, float, float],
        policy_output: dict[str, Any] | None = None,
    ) -> None:
        self._rows.append(
            {
                "frame": snapshot.frame_index,
                "timestamp_utc": snapshot.timestamp_utc,
                "pose": snapshot.pose.as_list(),
                "image_path": snapshot.image_path,
                "image_sha256": snapshot.image_sha256,
                "transforms": [t.as_dict() for t in snapshot.transforms],
                "control_mode": control_mode,
                "commanded_vx_vy_w": list(commanded),
                "achieved_vx_vy_w": list(achieved),
                "policy_output": policy_output,
            }
        )

    def finalise(self) -> Path:
        manifest = {
            **self.episode.as_dict(),
            "recorded_utc": _now(),
            "steps": self._rows,
            "claim_boundary": (
                "SIMULATION_DEVELOPMENT engineering evidence. Not admitted for "
                "training, validation or evaluation. If the control mode is a "
                "learned policy the recorded motion is that policy's own behaviour, "
                "not a demonstration."
            ),
        }
        path = self.out_dir / "episode_manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        return path


class EpisodeReplay:
    """Reads a recorded episode back for scrubbing.

    Replay shows the same three states as LIVE, from the recording rather than
    the simulator. START and GOAL are immutable there for the same reason they
    are immutable here: a replay that let you edit the goal would be a worse
    record than the run it replays.
    """

    def __init__(self, manifest_path: str | Path) -> None:
        self.path = Path(manifest_path)
        self.data = json.loads(self.path.read_text())
        self.steps: list[dict[str, Any]] = self.data.get("steps", [])

    def __len__(self) -> int:
        return len(self.steps)

    @property
    def episode_id(self) -> str:
        return str(self.data.get("episode_id", ""))

    @property
    def start(self) -> dict[str, Any] | None:
        return self.data.get("start")

    @property
    def goal(self) -> dict[str, Any] | None:
        return self.data.get("goal")

    def at(self, frame: int) -> dict[str, Any]:
        """The CURRENT state at a replay position. Clamped, never wrapped.

        Wrapping would make frame -1 silently show the last frame, which reads
        as the robot having finished when it has not started.
        """
        if not self.steps:
            raise IndexError("this recording contains no steps")
        idx = max(0, min(int(frame), len(self.steps) - 1))
        return self.steps[idx]

    def poses(self) -> list[list[float]]:
        return [s["pose"] for s in self.steps]
