"""Play cached speech through the robot's speaker, pausable at any moment.

Audio is pushed in short chunks, never more than ``LEAD_S`` ahead of real time,
so a pause takes effect almost immediately. Any audio already queued is flushed
when interrupted.
"""

import time
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np
import soxr

CHUNK_S = 0.1  # size of each pushed chunk
LEAD_S = 0.3  # how far ahead of playback we may queue audio
POLL_S = 0.02


class Speaker:
    def __init__(self, media, gain: float = 1.0) -> None:
        self.media = media
        self.gain = gain
        self.rate = media.get_output_audio_samplerate()
        if self.rate <= 0:
            raise RuntimeError("Robot audio output is not available.")

    def load(self, path: Path) -> np.ndarray:
        """Read a mono 16-bit WAV, apply the gain and resample to the speaker's rate."""
        with wave.open(str(path), "rb") as wav:
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        samples = np.clip(samples * self.gain, -1.0, 1.0)
        if rate != self.rate:
            samples = soxr.resample(samples, rate, self.rate)
        return samples.astype(np.float32)

    def play(self, samples: np.ndarray, interrupted: Callable[[], bool]) -> bool:
        """Play ``samples``; return True if finished, False if interrupted."""
        chunk = int(CHUNK_S * self.rate)
        start = time.monotonic()
        queued_s = 0.0

        for offset in range(0, len(samples), chunk):
            while queued_s - (time.monotonic() - start) > LEAD_S:
                if interrupted():
                    self.flush()
                    return False
                time.sleep(POLL_S)
            if interrupted():
                self.flush()
                return False
            piece = samples[offset : offset + chunk]
            self.media.push_audio_sample(piece)
            queued_s += len(piece) / self.rate

        while time.monotonic() - start < queued_s:
            if interrupted():
                self.flush()
                return False
            time.sleep(POLL_S)
        return True

    def pause(self, seconds: float, interrupted: Callable[[], bool]) -> bool:
        """Stay silent for ``seconds``; return False if interrupted."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if interrupted():
                return False
            time.sleep(POLL_S)
        return True

    def flush(self) -> None:
        """Drop any audio already queued for the speaker."""
        audio = getattr(self.media, "audio", None)
        if audio is not None and hasattr(audio, "clear_player"):
            audio.clear_player()
