"""Gentle, always-safe gestures.

Every gesture is a short sequence of poses relative to neutral, each reached
with smooth min-jerk interpolation, ending back at neutral. Limits are checked
at import time, well inside the hardware limits (head pitch/roll 40 degrees,
yaw 180 degrees). The body never turns.
"""

import logging
import queue
import threading
from dataclasses import dataclass

import numpy as np
from reachy_mini import ReachyMini
from reachy_mini.io.protocol import MotorControlMode
from reachy_mini.utils import create_head_pose
from reachy_mini.utils.interpolation import InterpolationTechnique

MAX_ANGLE_DEG = 15.0  # head pitch and roll
MAX_YAW_DEG = 25.0
MAX_OFFSET_MM = 10.0  # head translation
MAX_ANTENNA_DELTA_DEG = 25.0  # from the rest position
MIN_DURATION_S = 0.8

REST_ANTENNAS_DEG = (-10.0, 10.0)  # [right, left], the SDK's resting position

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Pose:
    roll: float = 0.0  # degrees, positive tilts the head to its left
    pitch: float = 0.0  # degrees, positive looks down
    yaw: float = 0.0  # degrees, positive turns to its left
    z: float = 0.0  # mm, positive raises the head
    x: float = 0.0  # mm, positive moves the head forward
    antennas: tuple[float, float] = (0.0, 0.0)  # degrees added to rest [right, left]
    duration: float = 1.0  # seconds to reach this pose


NEUTRAL = Pose()

GESTURES: dict[str, list[Pose]] = {
    "nod": [Pose(pitch=8, duration=0.8), Pose(pitch=-2, duration=0.8), NEUTRAL],
    "bow": [Pose(pitch=14, z=-5, antennas=(10, -10), duration=1.4), NEUTRAL],
    "tilt": [Pose(roll=10, antennas=(-8, 8), duration=1.0), NEUTRAL],
    "ponder": [
        Pose(roll=-8, pitch=-6, yaw=10, antennas=(-15, 5), duration=1.4),
        Pose(roll=-8, pitch=-6, yaw=10, antennas=(-5, 15), duration=1.0),
        NEUTRAL,
    ],
    "aha": [
        Pose(pitch=-8, z=6, antennas=(20, -20), duration=0.8),
        NEUTRAL,
    ],
    "lean_in": [Pose(pitch=6, x=8, duration=1.2), NEUTRAL],
    "look_around": [
        Pose(yaw=20, duration=1.4),
        Pose(yaw=-20, duration=2.0),
        NEUTRAL,
    ],
    "look_up": [Pose(pitch=-12, z=5, duration=1.4), NEUTRAL],
    "shake": [
        Pose(yaw=8, duration=0.8),
        Pose(yaw=-8, duration=0.9),
        NEUTRAL,
    ],
    "antenna_flutter": [
        Pose(antennas=(15, -15), duration=0.8),
        Pose(antennas=(-10, 10), duration=0.8),
        Pose(antennas=(15, -15), duration=0.8),
        NEUTRAL,
    ],
}


def _check_limits() -> None:
    for name, poses in GESTURES.items():
        for pose in poses:
            assert abs(pose.roll) <= MAX_ANGLE_DEG, name
            assert abs(pose.pitch) <= MAX_ANGLE_DEG, name
            assert abs(pose.yaw) <= MAX_YAW_DEG, name
            assert abs(pose.z) <= MAX_OFFSET_MM and abs(pose.x) <= MAX_OFFSET_MM, name
            assert all(abs(a) <= MAX_ANTENNA_DELTA_DEG for a in pose.antennas), name
            assert pose.duration >= MIN_DURATION_S, name
        assert poses[-1] == NEUTRAL, f"{name} must end at neutral"


_check_limits()


def ensure_motors_enabled(reachy_mini: ReachyMini) -> None:
    """Switch torque on if it is off, without the head jumping.

    Another app, Reachy Mini Control, or the end of an earlier session can leave
    the motors disabled (limp). Movement commands are then silently ignored, so
    the robot would speak without rising. Pollen's safe pattern: make the
    current pose the goal, then disable and re-enable all motors together.
    """
    status = reachy_mini.client.get_status()
    mode = status.backend_status.motor_control_mode if status.backend_status else None
    if mode == MotorControlMode.Enabled:
        return
    logger.info("Motors were %s; enabling them safely", getattr(mode, "value", mode))
    head = reachy_mini.get_current_head_pose()
    _, antennas = reachy_mini.get_current_joint_positions()
    reachy_mini.goto_target(
        head=head, antennas=list(antennas), duration=0.05, body_yaw=None,
    )
    reachy_mini.disable_motors()  # all together: avoids a known mixed-state edge case
    reachy_mini.enable_motors()


def go_to(reachy_mini: ReachyMini, pose: Pose) -> None:
    head = create_head_pose(
        x=pose.x, z=pose.z, roll=pose.roll, pitch=pose.pitch, yaw=pose.yaw,
        mm=True, degrees=True,
    )
    antennas = np.deg2rad(np.add(REST_ANTENNAS_DEG, pose.antennas))
    reachy_mini.goto_target(
        head=head, antennas=antennas, duration=pose.duration,
        method=InterpolationTechnique.MIN_JERK, body_yaw=None,
    )


class GestureWorker(threading.Thread):
    """Plays one gesture at a time in the background; extra requests are dropped."""

    def __init__(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        super().__init__(name="gestures", daemon=True)
        self.reachy_mini = reachy_mini
        self.stop_event = stop_event
        self._requests: queue.Queue[str] = queue.Queue(maxsize=1)
        self._idle = threading.Event()
        self._idle.set()

    def play(self, name: str) -> None:
        if name not in GESTURES:
            logger.warning("Unknown gesture %r ignored", name)
            return
        try:
            self._requests.put_nowait(name)
        except queue.Full:
            logger.debug("Gesture %r dropped (one already pending)", name)

    def wait_idle(self, timeout: float = 10.0) -> None:
        self._idle.wait(timeout)

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                name = self._requests.get(timeout=0.1)
            except queue.Empty:
                continue
            self._idle.clear()
            try:
                for pose in GESTURES[name]:
                    go_to(self.reachy_mini, pose)
            except Exception:
                logger.exception("Gesture %r failed", name)
            finally:
                self._idle.set()
