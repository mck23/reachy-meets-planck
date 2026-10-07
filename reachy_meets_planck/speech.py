"""Play speech clips through the robot's speaker, pausable at any moment.

Clips are compressed Ogg Opus files. Each is decompressed in memory just
before it plays; ``prefetch()`` decompresses the next one in the background
while the current one is playing, so slow hardware adds no extra gap.

Audio is pushed in short chunks, never more than ``LEAD_S`` ahead of real
time, so a pause takes effect almost immediately. Any audio already queued is
flushed when interrupted.
"""

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile
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
        self._decoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix="decode")
        self._ahead: dict[Path, Future[np.ndarray]] = {}

    def decode(self, path: Path) -> np.ndarray:
        """Decompress a clip to mono float samples at the speaker's rate, with gain."""
        samples, rate = soundfile.read(path, dtype="float32", always_2d=True)
        samples = np.clip(samples[:, 0] * self.gain, -1.0, 1.0)
        if rate != self.rate:
            samples = soxr.resample(samples, rate, self.rate)
        return samples.astype(np.float32)

    def prefetch(self, path: Path) -> None:
        """Start decompressing ``path`` in the background (keeps only the latest)."""
        if path not in self._ahead:
            self._ahead = {path: self._decoder.submit(self.decode, path)}

    def load(self, path: Path) -> np.ndarray:
        """Return the decompressed clip, from the prefetch if one is ready."""
        future = self._ahead.pop(path, None)
        return future.result() if future else self.decode(path)

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

    def close(self) -> None:
        self._decoder.shutdown(wait=False, cancel_futures=True)
