"""Build the ordered list of things Reachy says.

Combines Planck's words (``data/lecture1_text.json``) with the performance layer
(``data/performance.json``): greeting, gesture cues, flourishes and closing.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
MANIFEST_PATH = AUDIO_DIR / "manifest.json"

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


def audio_path(item: Item) -> Path:
    return AUDIO_DIR / f"{item.key}.wav"


def missing_audio(items: list[Item], voice: dict) -> list[Item]:
    """Items whose cached audio is absent or out of date."""
    manifest = (
        json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}
    )
    return [
        item
        for item in items
        if manifest.get(item.key) != fingerprint(item, voice)
        or not audio_path(item).exists()
    ]
