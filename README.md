---
title: Reachy Meets Planck
emoji: 🔬
colorFrom: red
colorTo: blue
sdk: static
license: mit
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

## Install on a robot

Install from Reachy Mini Control like any other app. The speech clips (about 10 MB of compressed
audio) are installed with the app, so no API key or internet access is needed while it runs,
except for a one-time download of the offline speech-recognition model (about 40 MB).

## Startup time

Expect a wait of several seconds between starting the app and Reachy's first word. Measured in
the MuJoCo simulator on an Apple Silicon Mac, the app logs "Ready to speak" **6.6–8.4 s** after its
process starts:

| Step | Time |
|---|---|
| Python start, connecting to the robot, camera and audio setup (Reachy Mini SDK) | ~3.5–5 s |
| Offline speech-recognition model | ~0.3 s |
| Wake-up animation (Reachy rises before speaking) | ~2.5 s |

The audio output may need up to about 2 s more to start the first time it plays. The app sends
it silence before the wake-up animation to give it a head start. On the robot's own computer,
startup will differ (it is slower than a Mac); the app logs the exact figure on every run as
"Ready to speak … s after the app process started".

## Development setup (macOS, uv)

```bash
uv venv .venv --python 3.12
uv pip install --python .venv -e ".[render]" "reachy-mini[mujoco]"
git lfs install --local     # the .ogg speech clips are stored with Git LFS
```

## Regenerate the speech (only after changing the text or the voice)

`reachy_meets_planck/data/performance.json` holds the voice settings. The script makes 24 kHz WAV
masters with OpenAI `gpt-4o-mini-tts` in `data/audio/` (git-ignored, needs `OPENAI_API_KEY` in
`.env`), then compresses them to the 16 kHz Ogg Opus clips in `reachy_meets_planck/audio/` that
ship with the app. Only what changed is redone.

```bash
cp .env.example .env                                  # then paste your OpenAI key into .env
.venv/bin/python scripts/render_audio.py --sample     # audition a few lines
.venv/bin/python scripts/render_audio.py              # everything that changed
.venv/bin/python scripts/check_audio.py               # flag clipped or odd-sounding masters
```

## Run in the simulator

```bash
.venv/bin/mjpython -m reachy_mini.daemon.app.main --sim       # terminal 1
.venv/bin/python -m reachy_meets_planck.main                  # terminal 2
```

## Run from a Mac on a real Reachy Mini Wireless

Turn the robot on and wait for it to join Wi-Fi (with no simulator running), then:

```bash
.venv/bin/python -m reachy_meets_planck.main
```

## How it's built

- `scripts/extract_lecture.py` turns Project Gutenberg's LaTeX source into 219 speakable
  sentences (`reachy_meets_planck/data/lecture1_text.json`). Equations are read out as words;
  Planck's wording is unchanged.
- `reachy_meets_planck/data/performance.json` adds the voice settings, greeting, closing, asides,
  gesture cues and `playback_gain` (1.25: the robot's own volume is already at 100%; clips peak at
  0.68, so this stays below full scale).
- `reachy_meets_planck/` contains the app itself: `speech.py` (decompresses each clip in memory,
  the next one in the background, and plays it in short chunks so it can pause at once),
  `listener.py` (offline Vosk command recognition), `gestures.py` (gentle, capped moves) and
  `main.py` (the state machine).

## Publish or update the Hugging Face Space

Commit first, then:

```bash
.venv/bin/hf auth login                        # once, with a write token
.venv/bin/python scripts/publish_space.py      # create (private) or update the Space
.venv/bin/python scripts/publish_space.py --public   # when ready to share
```

The script uploads exactly the files git tracks at the current commit, so `.env` and other local
files can never be sent. (Pollen's `reachy-mini-app-assistant publish` can fall back to uploading
the whole folder, so it is not used here.) Installed robots are offered the update in Reachy Mini
Control.

## About the voice

The voice is **AI-generated** with OpenAI text-to-speech. It is not Max Planck's voice, and no
recording of Planck was used.

## Credits and license

- Text: Max Planck, *Eight Lectures on Theoretical Physics*, translated by A. P. Wills (Columbia
  University Press, 1915). Public domain. Source: Project Gutenberg eBook #39017.
- Code and speech clips: MIT License (see `LICENSE`).
