"""Generate the speech audio: OpenAI text-to-speech, then compression.

Two steps, each skipping whatever is already up to date:

1. **Masters**: each greeting, sentence, aside and closing becomes a 24 kHz WAV
   in ``data/audio/`` (git-ignored, development only). Needs OPENAI_API_KEY in
   .env, and costs a little on your OpenAI account.
2. **Clips**: each master is resampled to 16 kHz (the robot speaker's rate)
   and compressed to Ogg Opus in ``reachy_meets_planck/audio/``. These ship
   with the app (stored with Git LFS). Free and offline.

Usage::

    python scripts/render_audio.py --sample    # a few clips to audition the voice
    python scripts/render_audio.py --dry-run   # show what would be done
    python scripts/render_audio.py             # do everything that's missing
"""

import argparse
import json
import sys
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import soundfile
import soxr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reachy_meets_planck.playlist import (  # noqa: E402
    CLIP_DIR,
    CLIP_MANIFEST,
    FLOURISH,
    MASTER_DIR,
    MASTER_MANIFEST,
    PROJECT_DIR,
    Item,
    clip_path,
    fingerprint,
    load_performance,
    load_playlist,
    master_path,
    missing_clips,
    missing_masters,
    read_manifest,
)

PCM_RATE = 24000  # OpenAI "pcm" output: 24 kHz, 16-bit signed, mono
CLIP_RATE = 16000  # Reachy Mini speaker rate
WORKERS = 4


def render(client, item: Item, voice: dict) -> bytes:
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


def compress(item: Item) -> None:
    """Master WAV -> 16 kHz mono Ogg Opus clip."""
    with wave.open(str(master_path(item)), "rb") as wav:
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    samples = soxr.resample(samples, rate, CLIP_RATE)
    soundfile.write(clip_path(item), samples, CLIP_RATE, format="OGG", subtype="OPUS")


def write_manifest(path: Path, manifest: dict[str, str]) -> None:
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")


def render_masters(todo: list[Item], voice: dict) -> None:
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(PROJECT_DIR / ".env")
    client = OpenAI()  # reads OPENAI_API_KEY
    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(MASTER_MANIFEST)

    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(render, client, item, voice): item for item in todo}
        for done, future in enumerate(as_completed(futures), start=1):
            item = futures[future]
            save_wav(master_path(item), future.result())
            manifest[item.key] = fingerprint(item, voice)
            write_manifest(MASTER_MANIFEST, manifest)
            print(f"[{done}/{len(todo)}] {item.key}: {item.text[:60]}")


def compress_clips(todo: list[Item], voice: dict) -> None:
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(CLIP_MANIFEST)
    for item in todo:
        compress(item)
        manifest[item.key] = fingerprint(item, voice)
    write_manifest(CLIP_MANIFEST, manifest)
    size = sum(clip_path(i).stat().st_size for i in todo)
    print(f"Compressed {len(todo)} clips ({size / 1e6:.1f} MB) into "
          f"{CLIP_DIR.relative_to(PROJECT_DIR)}/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sample", action="store_true", help="render a few clips only")
    parser.add_argument("--dry-run", action="store_true", help="list work, change nothing")
    args = parser.parse_args()

    voice = load_performance()["voice"]
    playlist = load_playlist()
    if args.sample:
        first_flourish = next(i for i in playlist if i.style == FLOURISH)
        sample_keys = {"greeting", "seg-000", "seg-001", first_flourish.key}
        playlist = [item for item in playlist if item.key in sample_keys]

    masters = missing_masters(playlist, voice)
    chars = sum(len(item.text) for item in masters)
    print(f"Masters: {len(masters)} to render with OpenAI ({chars:,} characters).")
    if masters and not args.dry_run:
        render_masters(masters, voice)

    clips = missing_clips(playlist, voice)
    print(f"Clips: {len(clips)} to compress.")
    if clips and not args.dry_run:
        compress_clips(clips, voice)


if __name__ == "__main__":
    main()
