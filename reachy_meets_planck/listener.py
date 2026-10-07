"""Listen to the robot's microphones for the four voice commands.

Uses Vosk, an offline speech recogniser, in two ways at once:

- A **full-vocabulary** recogniser listens for "stop". Reachy's own voice gets
  transcribed as the lecture's words (which never include "stop"), so it can't
  pause itself, while a person's "stop" counts as soon as it is heard.
- A **command-only** recogniser (grammar: the four words plus "[unk]" for
  anything else) listens for "begin", "continue" and "end". The small
  full-vocabulary model mishears these single words ("end" -> "and"), but the
  grammar gets them right. An utterance counts only if it is *just* the command
  word, so chatter like "let's begin cooking" is ignored.
"""

import io
import json
import logging
import threading
import time
import urllib.request
import zipfile
from collections import deque
from pathlib import Path

import numpy as np
import soxr
import vosk

from reachy_meets_planck.playlist import PROJECT_DIR

STOP = "stop"
BEGIN = "begin"
CONTINUE = "continue"
END = "end"
COMMANDS = (STOP, BEGIN, CONTINUE, END)

VOSK_RATE = 16000
HOLD_OFF_S = 0.5  # after clear(), ignore audio that started before it
MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MODEL_DIR = PROJECT_DIR / "models"

logger = logging.getLogger(__name__)


def ensure_model() -> Path:
    """Return the Vosk model folder, downloading it (~40 MB) on first use."""
    path = MODEL_DIR / MODEL_NAME
    if not path.exists():
        logger.info("Downloading speech model %s ...", MODEL_NAME)
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(MODEL_URL) as resp:
            zipfile.ZipFile(io.BytesIO(resp.read())).extractall(MODEL_DIR)
    return path


class CommandListener(threading.Thread):
    def __init__(self, media, stop_event: threading.Event) -> None:
        super().__init__(name="command-listener", daemon=True)
        self.media = media
        self.stop_event = stop_event
        self.in_rate = media.get_input_audio_samplerate()
        vosk.SetLogLevel(-1)
        model = vosk.Model(str(ensure_model()))
        self.free_speech = vosk.KaldiRecognizer(model, VOSK_RATE)
        self.commands_only = vosk.KaldiRecognizer(
            model, VOSK_RATE, json.dumps([STOP, BEGIN, CONTINUE, END, "[unk]"])
        )
        self._heard: deque[str] = deque()
        self._lock = threading.Lock()
        self._stop_sent_this_utterance = False
        self._reset_requested = False
        self._ignore_until = 0.0

    # --- consumer side ---------------------------------------------------

    def take(self, allowed: tuple[str, ...]) -> str | None:
        """Return the oldest allowed command heard, discarding others."""
        with self._lock:
            while self._heard:
                command = self._heard.popleft()
                if command in allowed:
                    return command
        return None

    def clear(self) -> None:
        """Forget everything heard so far, including half-finished utterances."""
        with self._lock:
            self._heard.clear()
            self._reset_requested = True
            self._ignore_until = time.monotonic() + HOLD_OFF_S

    # --- recogniser thread -----------------------------------------------

    def run(self) -> None:
        while not self.stop_event.is_set():
            samples = self.media.get_audio_sample()
            if samples is None or len(samples) == 0:
                time.sleep(0.01)
                continue
            if self._reset_requested:
                self.free_speech.Reset()
                self.commands_only.Reset()
                self._stop_sent_this_utterance = False
                self._reset_requested = False

            mono = samples.mean(axis=1) if samples.ndim == 2 else samples
            if self.in_rate != VOSK_RATE:
                mono = soxr.resample(mono, self.in_rate, VOSK_RATE)
            pcm = (np.clip(mono, -1.0, 1.0) * 32767).astype("<i2").tobytes()

            self._listen_for_stop(pcm)
            self._listen_for_commands(pcm)

    def _listen_for_stop(self, pcm: bytes) -> None:
        if self.free_speech.AcceptWaveform(pcm):
            text = json.loads(self.free_speech.Result()).get("text", "")
            final = True
        else:
            text = json.loads(self.free_speech.PartialResult()).get("partial", "")
            final = False
        if STOP in text.split() and not self._stop_sent_this_utterance:
            self._stop_sent_this_utterance = True
            self._emit(STOP, text)
        if final:
            self._stop_sent_this_utterance = False

    def _listen_for_commands(self, pcm: bytes) -> None:
        if not self.commands_only.AcceptWaveform(pcm):
            return
        words = set(json.loads(self.commands_only.Result()).get("text", "").split())
        for command in (BEGIN, CONTINUE, END):
            if words == {command}:
                self._emit(command, command)

    def _emit(self, command: str, heard: str) -> None:
        if time.monotonic() < self._ignore_until:
            return
        logger.info('Heard "%s" -> %s', heard, command)
        with self._lock:
            self._heard.append(command)
