---
title: Reachy Meets Planck
emoji: 🔬
colorFrom: red
colorTo: blue
sdk: static
pinned: false
short_description: Reachy Mini reads Planck's 1909 lecture aloud
tags:
 - reachy_mini
 - reachy_mini_python_app
---

# Reachy Meets Planck

Reachy Mini reads aloud **Max Planck's First Lecture**, *Introduction: Reversibility and
Irreversibility*, from *Eight Lectures on Theoretical Physics* (Columbia University, 1909). It adds a
few brief asides and occasional safe gestures, and listens for four voice commands.

A small effort was made to craft a speech style aligned to Planck, per https://en.wikipedia.org/wiki/Max_Planck, with limited success.

| Say | While reading | While paused | After the lecture |
|---|---|---|---|
| **stop** | pause | — | — |
| **continue** | — | resume at the interrupted sentence | — |
| **begin** | — | restart from the top | read it again |
| **end** | — | say goodbye and go to sleep | go to sleep |

While Reachy is reading, only **stop** is listened for. "Stop" never occurs in the lecture, so
Reachy can't interrupt itself.

## Setup (macOS, uv)

```bash
uv venv .venv --python 3.12
uv pip install --python .venv -e ".[render]" "reachy-mini[mujoco]"
cp .env.example .env        # then paste your OpenAI key into .env
```

## 1. Generate the speech (one time)

The voice is made by OpenAI `gpt-4o-mini-tts` and cached as WAV files in `data/audio/`
(git-ignored). Audition a few lines first, then render everything:

```bash
.venv/bin/python scripts/render_audio.py --sample     # greeting, title, one flourish
.venv/bin/python scripts/render_audio.py              # everything (~50 min of audio)
```

## 2. Run in the simulator

```bash
.venv/bin/mjpython -m reachy_mini.daemon.app.main --sim       # terminal 1
.venv/bin/python -m reachy_meets_planck.main                  # terminal 2
```

## 3. Run on the real Reachy Mini Wireless

Turn the robot on and wait for it to join Wi-Fi, then:

```bash
.venv/bin/python -m reachy_meets_planck.main
```

## How it's built

- `scripts/extract_lecture.py` turns Project Gutenberg's LaTeX source into 219 speakable
  sentences (`data/lecture1_text.json`). Equations are read out as words; Planck's wording is
  unchanged.
- `data/performance.json` adds the voice style, greeting, closing, asides, gesture cues and
  `playback_gain` (1.25: the robot's own volume is already at 100%; clips peak at 0.68, so this
  stays below full scale).
- `reachy_meets_planck/` contains the app itself: `speech.py` (chunked playback with instant
  pause), `listener.py` (offline Vosk command recognition), `gestures.py` (gentle, capped moves)
  and `main.py` (the state machine).

## Credits

Text: Max Planck, *Eight Lectures on Theoretical Physics*, translated by A. P. Wills (Columbia
University Press, 1915). Public domain. Source: Project Gutenberg eBook #39017.
