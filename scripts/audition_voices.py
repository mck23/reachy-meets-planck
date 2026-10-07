"""Render a few lines in several OpenAI voices to compare them side by side.

Uses the voice settings from ``data/performance.json``, optionally overridden
by a JSON file (e.g. alternative instructions). Output goes to
``data/audio/auditions/[<tag>-]<voice>-<clip>.wav``.

Usage::

    python scripts/audition_voices.py
    python scripts/audition_voices.py --voices ash verse --clips seg-182 flourish-142
    python scripts/audition_voices.py --voices ballad --override voice.json --tag draft
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR.parent))
sys.path.insert(0, str(SCRIPTS_DIR))
from render_audio import render, save_wav  # noqa: E402

from reachy_meets_planck.playlist import (  # noqa: E402
    AUDIO_DIR,
    PROJECT_DIR,
    load_performance,
    load_playlist,
)

AUDITION_DIR = AUDIO_DIR / "auditions"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--voices", nargs="+", default=["ash", "verse", "ballad"])
    parser.add_argument("--clips", nargs="+", default=["seg-182", "flourish-142"])
    parser.add_argument("--override", type=Path, help="JSON file of voice settings to override")
    parser.add_argument("--tag", default="", help="prefix for the output file names")
    args = parser.parse_args()

    load_dotenv(PROJECT_DIR / ".env")
    client = OpenAI()
    base_voice = load_performance()["voice"]
    if args.override:
        base_voice = {**base_voice, **json.loads(args.override.read_text())}
    prefix = f"{args.tag}-" if args.tag else ""
    items = {item.key: item for item in load_playlist()}
    AUDITION_DIR.mkdir(parents=True, exist_ok=True)

    jobs = [(v, items[c]) for v in args.voices for c in args.clips]
    with ThreadPoolExecutor(4) as pool:
        results = pool.map(
            lambda job: render(client, job[1], {**base_voice, "voice": job[0]}), jobs
        )
        for (voice, item), pcm in zip(jobs, results):
            path = AUDITION_DIR / f"{prefix}{voice}-{item.key}.wav"
            save_wav(path, pcm)
            print(f"{path.relative_to(PROJECT_DIR)}: {item.text[:60]}")


if __name__ == "__main__":
    main()
