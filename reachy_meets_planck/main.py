"""Reachy Meets Planck: Reachy Mini reads Planck's First Lecture aloud.

States::

    READING  --"stop"-->      PAUSED
    PAUSED   --"continue"-->  READING (from the start of the interrupted sentence)
    PAUSED   --"begin"-->     READING (from the very top)
    PAUSED   --"end"-->       goodbye, sleep, exit
    FINISHED --"begin"-->     READING (from the very top)
    FINISHED --"end"-->       sleep, exit
"""

import logging
import threading
import time

import numpy as np
import psutil
from reachy_mini import ReachyMini, ReachyMiniApp

from reachy_meets_planck.gestures import (
    NEUTRAL,
    GestureWorker,
    ensure_motors_enabled,
    go_to,
)
from reachy_meets_planck.listener import BEGIN, CONTINUE, END, STOP, CommandListener
from reachy_meets_planck.playlist import (
    FLOURISH,
    clip_path,
    load_performance,
    load_playlist,
    missing_clips,
)
from reachy_meets_planck.speech import Speaker

GAP_AFTER_SENTENCE_S = 0.35
GAP_AROUND_FLOURISH_S = 0.6
IDLE_POLL_S = 0.1
WARM_UP_SILENCE_S = 0.5

# Gesture used to acknowledge each command (no spoken acknowledgements).
ACKNOWLEDGE = {STOP: "tilt", CONTINUE: "nod", BEGIN: "aha", END: "bow"}

logger = logging.getLogger(__name__)


class ReachyMeetsPlanck(ReachyMiniApp):
    custom_app_url: str | None = None  # no settings page
    request_media_backend: str | None = None  # auto: local on-robot, WebRTC remote

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        playlist = load_playlist()
        performance = load_performance()
        missing = missing_clips(playlist, performance["voice"])
        if missing:
            raise RuntimeError(
                f"{len(missing)} speech clips are missing or out of date "
                f"(e.g. {missing[0].key}). Run: python scripts/render_audio.py"
            )

        media = reachy_mini.media
        media.start_recording()
        media.start_playing()
        speaker = Speaker(media, gain=performance.get("playback_gain", 1.0))
        # The audio output can take a couple of seconds to start the first time it
        # receives sound. Feed it silence now, so it can start up during the wake-up
        # animation rather than after the greeting has been sent.
        media.push_audio_sample(np.zeros(int(WARM_UP_SILENCE_S * speaker.rate), np.float32))
        listener = CommandListener(media, stop_event)
        gestures = GestureWorker(reachy_mini, stop_event)
        listener.start()
        gestures.start()

        try:
            ensure_motors_enabled(reachy_mini)
            reachy_mini.wake_up()
            reachy_mini.enable_wobbling()
            started = psutil.Process().create_time()
            logger.info("Ready to speak %.1f s after the app process started", time.time() - started)
            Performance(playlist, speaker, listener, gestures, stop_event).perform()
        finally:
            stop_event.set()
            speaker.flush()
            speaker.close()
            reachy_mini.disable_wobbling()
            go_to(reachy_mini, NEUTRAL)
            reachy_mini.goto_sleep()
            media.stop_playing()
            media.stop_recording()


class Performance:
    def __init__(self, playlist, speaker, listener, gestures, stop_event) -> None:
        self.playlist = playlist
        self.speaker = speaker
        self.listener = listener
        self.gestures = gestures
        self.stop_event = stop_event

    def _stop_requested(self) -> bool:
        return self.stop_event.is_set() or self.listener.take((STOP,)) == STOP

    def perform(self) -> None:
        index = 0
        while not self.stop_event.is_set():
            index = self._read_from(index)
            if index is None:  # paused or finished, then "end"
                return

    def _read_from(self, index: int) -> int | None:
        """Read until the end or a pause; return where to resume, or None to exit."""
        self.listener.clear()
        while index < len(self.playlist):
            item = self.playlist[index]
            logger.info("[%s] %s", item.key, item.text[:70])
            if item.gesture:
                self.gestures.play(item.gesture)

            is_flourish = item.style == FLOURISH
            gap = GAP_AROUND_FLOURISH_S if is_flourish else GAP_AFTER_SENTENCE_S
            if is_flourish and not self.speaker.pause(gap, self._stop_requested):
                return self._paused(index)
            samples = self.speaker.load(clip_path(item))
            if index + 1 < len(self.playlist):
                self.speaker.prefetch(clip_path(self.playlist[index + 1]))
            if not self.speaker.play(samples, self._stop_requested):
                return self._paused(index)
            if not self.speaker.pause(gap, self._stop_requested):
                return self._paused(index + 1)
            index += 1

        return self._finished()

    def _paused(self, index: int) -> int | None:
        if self.stop_event.is_set():
            return None
        logger.info("Paused at %s. Say continue, begin or end.", self.playlist[index].key)
        self.gestures.play(ACKNOWLEDGE[STOP])
        command = self._wait_for((CONTINUE, BEGIN, END))
        if command is None or command == END:
            return None
        self.gestures.wait_idle()
        return index if command == CONTINUE else 0

    def _finished(self) -> int | None:
        logger.info("Lecture finished. Say begin to hear it again, or end.")
        command = self._wait_for((BEGIN, END))
        if command is None or command == END:
            return None
        self.gestures.wait_idle()
        return 0

    def _wait_for(self, allowed: tuple[str, ...]) -> str | None:
        self.listener.clear()
        while not self.stop_event.is_set():
            command = self.listener.take(allowed)
            if command:
                self.gestures.play(ACKNOWLEDGE[command])
                if command == END:
                    self.gestures.wait_idle()
                return command
            self.stop_event.wait(IDLE_POLL_S)
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    app = ReachyMeetsPlanck()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
