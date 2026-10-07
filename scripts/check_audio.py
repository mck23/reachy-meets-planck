"""Sanity-check the rendered speech masters (data/audio/*.wav).

Flags clips whose speaking rate is far from the typical rate (a sign that the
speech was cut off or that the voice wandered), clips that clip (too loud), and
clips with long silences. Prints total running time.

Usage::

    python scripts/check_audio.py
"""

import sys
import wave
from pathlib import Path
from statistics import median

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reachy_meets_planck.playlist import (  # noqa: E402
    LECTURE,
    PROJECT_DIR,
    load_performance,
    load_playlist,
    master_path,
    missing_masters,
)

RATE_TOLERANCE = 0.45  # flag clips more than 45% faster or slower than typical
PEAK_LIMIT = 0.99
MAX_SILENCE_S = 2.5
SILENCE_LEVEL = 0.01


def read(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0, rate


def longest_silence_s(samples: np.ndarray, rate: int) -> float:
    window = rate // 20  # 50 ms
    usable = len(samples) // window * window
    loud = np.abs(samples[:usable]).reshape(-1, window).max(axis=1) > SILENCE_LEVEL
    longest = run = 0
    for is_loud in loud:
        run = 0 if is_loud else run + 1
        longest = max(longest, run)
    return longest * window / rate


def main() -> None:
    playlist = load_playlist()
    missing = missing_masters(playlist, load_performance()["voice"])
    if missing:
        print(f"{len(missing)} clips missing or out of date, e.g. {missing[0].key}")

    stats = []
    for item in playlist:
        if item in missing:
            continue
        samples, rate = read(master_path(item))
        seconds = len(samples) / rate
        stats.append((item, seconds, len(item.text) / seconds, np.abs(samples).max(),
                      longest_silence_s(samples, rate)))

    typical = median(chars_per_s for item, _, chars_per_s, _, _ in stats if item.style == LECTURE)
    total = sum(seconds for _, seconds, _, _, _ in stats)
    print(f"{len(stats)} clips, {total / 60:.1f} min total, "
          f"typical lecture rate {typical:.1f} characters/s\n")

    flagged = 0
    for item, seconds, chars_per_s, peak, silence in stats:
        problems = []
        if item.style == LECTURE and abs(chars_per_s / typical - 1) > RATE_TOLERANCE:
            problems.append(f"rate {chars_per_s:.1f} chars/s")
        if peak >= PEAK_LIMIT:
            problems.append(f"peak {peak:.2f}")
        if silence > MAX_SILENCE_S:
            problems.append(f"silence {silence:.1f}s")
        if problems:
            flagged += 1
            print(f"{item.key:14s} {seconds:5.1f}s  {', '.join(problems):35s} {item.text[:50]}")

    print(f"\n{flagged} clip(s) flagged." if flagged else "No problems found.")
    if flagged:
        print("Listen to them in "
              f"{master_path(playlist[0]).parent.relative_to(PROJECT_DIR)}/. To re-render one, "
              "delete its .wav file and run scripts/render_audio.py again.")


if __name__ == "__main__":
    main()
