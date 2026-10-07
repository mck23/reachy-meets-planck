"""Build the ordered list of things Reachy says, and locate their audio.

Combines Planck's words (``data/lecture1_text.json``) with the performance layer
(``data/performance.json``): greeting, gesture cues, asides and closing.

Audio lives in two places:

- **Clips** (``reachy_meets_planck/audio/*.ogg``): compressed 16 kHz Ogg Opus,
  shipped inside the package so they are installed on the robot.
- **Masters** (``data/audio/*.wav`` in the project folder): the original
  24 kHz WAVs from text-to-speech. Development only, never installed.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
CLIP_DIR = PACKAGE_DIR / "audio"
CLIP_MANIFEST = CLIP_DIR / "manifest.json"

PROJECT_DIR = PACKAGE_DIR.parent  # only meaningful in a development checkout
MASTER_DIR = PROJECT_DIR / "data" / "audio"
MASTER_MANIFEST = MASTER_DIR / "manifest.json"

LECTURE = "lecture"
FLOURISH = "flourish"


@dataclass(frozen=True)
class Item:
    """One thing Reachy says, with an optional gesture at its start."""

    key: str  # stable id, also the audio file name: "greeting", "seg-012", ...
    style: str  # LECTURE or FLOURISH: which voice instructions to use
    text: str
    gesture: str | None = None


def load_performance() -> dict:
    return json.loads((DATA_DIR / "performance.json").read_text(encoding="utf-8"))


def load_playlist() -> list[Item]:
    segments = json.loads(
        (DATA_DIR / "lecture1_text.json").read_text(encoding="utf-8")
    )["segments"]
    performance = load_performance()
    cues = {cue["segment"]: cue for cue in performance["cues"]}

    items = [Item("greeting", LECTURE, performance["greeting"])]
    for segment in segments:
        cue = cues.get(segment["id"], {})
        items.append(
            Item(
                f"seg-{segment['id']:03d}",
                LECTURE,
                segment["text"],
                cue.get("gesture"),
            )
        )
        if "flourish_after" in cue:
            items.append(
                Item(f"flourish-{segment['id']:03d}", FLOURISH, cue["flourish_after"])
            )
    items.append(Item("closing", FLOURISH, performance["closing"], "bow"))
    return items


def fingerprint(item: Item, voice: dict) -> str:
    """Identify the exact audio an item needs; changes when text or voice change."""
    instructions = voice[f"{item.style}_instructions"]
    material = "\n".join([voice["model"], voice["voice"], instructions, item.text])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def clip_path(item: Item) -> Path:
    return CLIP_DIR / f"{item.key}.ogg"


def master_path(item: Item) -> Path:
    return MASTER_DIR / f"{item.key}.wav"


def read_manifest(path: Path) -> dict[str, str]:
    return json.loads(path.read_text()) if path.exists() else {}


def stale(items: list[Item], voice: dict, manifest: Path, path_of) -> list[Item]:
    """Items whose audio file is absent or was made from other text/voice."""
    recorded = read_manifest(manifest)
    return [
        item
        for item in items
        if recorded.get(item.key) != fingerprint(item, voice) or not path_of(item).exists()
    ]


def missing_clips(items: list[Item], voice: dict) -> list[Item]:
    return stale(items, voice, CLIP_MANIFEST, clip_path)


def missing_masters(items: list[Item], voice: dict) -> list[Item]:
    return stale(items, voice, MASTER_MANIFEST, master_path)
