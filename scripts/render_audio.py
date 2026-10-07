"""Generate the speech audio with OpenAI text-to-speech (run once).

Each greeting, sentence, flourish and closing becomes one WAV file in
``data/audio/`` (git-ignored). Clips that already match the current text and
voice settings are skipped, so re-running only renders what changed.

Usage::

    python scripts/render_audio.py --sample    # a few clips to audition the voice
    python scripts/render_audio.py --dry-run   # show what would be rendered
    python scripts/render_audio.py             # render everything missing

Needs OPENAI_API_KEY in .env.
"""

import argparse
import json
import sys
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reachy_meets_planck.playlist import (  # noqa: E402
    AUDIO_DIR,
    FLOURISH,
    MANIFEST_PATH,
    PROJECT_DIR,
    Item,
    audio_path,
    fingerprint,
    load_performance,
    load_playlist,
    missing_audio,
)

PCM_RATE = 24000  # OpenAI "pcm" output: 24 kHz, 16-bit signed, mono
WORKERS = 4


def render(client: OpenAI, item: Item, voice: dict) -> bytes:
    with client.audio.speech.with_streaming_response.create(
        model=voice["model"],
        voice=voice["voice"],
        input=item.text,
        instructions=voice[f"{item.style}_instructions"],
        response_format="pcm",
    ) as response:
        return response.read()


def save_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(PCM_RATE)
        wav.writeframes(pcm)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sample", action="store_true", help="render a few clips only")
    parser.add_argument("--dry-run", action="store_true", help="list work, call nothing")
    args = parser.parse_args()

    voice = load_performance()["voice"]
    playlist = load_playlist()
    todo = missing_audio(playlist, voice)
    if args.sample:
        first_flourish = next(i for i in playlist if i.style == FLOURISH)
        sample_keys = {"greeting", "seg-000", "seg-001", first_flourish.key}
        todo = [item for item in todo if item.key in sample_keys]

    chars = sum(len(item.text) for item in todo)
    print(f"{len(todo)} of {len(playlist)} clips to render ({chars:,} characters).")
    if args.dry_run or not todo:
        return

    load_dotenv(PROJECT_DIR / ".env")
    client = OpenAI()  # reads OPENAI_API_KEY
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}

    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(render, client, item, voice): item for item in todo}
        for done, future in enumerate(as_completed(futures), start=1):
            item = futures[future]
            save_wav(audio_path(item), future.result())
            manifest[item.key] = fingerprint(item, voice)
            MANIFEST_PATH.write_text(json.dumps(manifest, indent=1, sort_keys=True))
            print(f"[{done}/{len(todo)}] {item.key}: {item.text[:60]}")

    if args.sample:
        print(f"\nListen: open {AUDIO_DIR.relative_to(PROJECT_DIR)}/ "
              "and play greeting.wav, seg-001.wav and the flourish clip.")


if __name__ == "__main__":
    main()
