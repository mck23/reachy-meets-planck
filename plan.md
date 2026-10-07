# Plan — Reachy Meets Planck

**Status:** built 2026-10-06. Simulator test passed (stop → continue, stop → end recognised; audio good; no self-triggers from Reachy's own voice across all 232 clips offline). First real Wireless robot run 2026-10-06: connected over Wi-Fi (WebRTC), greeting and lecture played from the robot, "stop" paused instantly and "end" exited cleanly. Packaged with compressed clips (10 MB) and published to the Space `mklejwa/reachy_meets_planck` (2026-10-06); install-from-Space verified on the Mac. Installed on the robot from Reachy Mini Control and run on the robot itself (2026-10-07): ready to speak in 8.3–8.6 s; commands work; motors switched back on safely at each start, so Reachy rises on first start and on restart. Space made public 2026-10-07 (community apps list); official-store request deferred.

A Reachy Mini **Wireless** app that reads aloud **Max Planck's First Lecture**, *Introduction:
Reversibility and Irreversibility*, from *Eight Lectures on Theoretical Physics* (Columbia
University, 1909; trans. A. P. Wills; Project Gutenberg #39017, public domain). It makes occasional
safe gestures and responds to the voice commands **stop / begin / continue / end**.

> **Voice:** A small effort was made to craft a speech style aligned to Planck, per https://en.wikipedia.org/wiki/Max_Planck, with limited success.

## Decisions (your answers)

| # | Question | Decision |
|---|---|---|
| Q1 | Voice | **OpenAI `gpt-4o-mini-tts`**, styled by written instructions. OpenAI's servers generate the speech; it **plays from the robot's speaker**. **No Anthropic API in the app.** |
| Q2 | Flourishes | **Yes.** 11 short in-character asides between sentences, plus a closing line. Planck's own words are unchanged. |
| Q3 | Commands | As proposed (see table below). |
| Q4 | Acknowledgements | **Gesture only.** |
| Q5 | Gesture frequency | **Occasional.** 67 cues across ~50 min. |
| Q6 | Greeting | On start, Reachy **rises** (`wake_up`), then says *"This is the first of Eight Lectures on Theoretical Physics, delivered at Columbia University in 1909, by Max Planck."* and **goes straight into the lecture**. |
| Q7 | Repo | **`mck23/reachy-meets-planck`**, public on GitHub (private during development). Local folder: `~/code/reachy-app-one`. |

## How it works

### Text (done at development time, committed to the repo)

- `scripts/extract_lecture.py`: downloads Gutenberg's LaTeX source and extracts Lecture One. It
  turns the notation into speech (equations as words; "e.g." becomes "for example") and splits the
  text into **219 sentences** → `reachy_meets_planck/data/lecture1_text.json` (7,095 words, about 50 min).
- `reachy_meets_planck/data/performance.json`: the voice style, greeting, closing, flourishes and gesture cues, written
  by Claude Code during development. **Claude is not called at run time.**

### Voice

- `scripts/render_audio.py` (one-time, about 50 min of audio) asks OpenAI for one WAV master per
  sentence or aside in `data/audio/` (git-ignored; uses `OPENAI_API_KEY` from `.env`), then
  compresses each to a 16 kHz Ogg Opus clip in `reachy_meets_planck/audio/` (10 MB in total,
  shipped with the app via Git LFS). On the robot each clip is decompressed in memory just before
  it plays, the next one in the background.
- At run time the app plays the cached audio in small chunks through `mini.media.push_audio_sample()`
  (the robot's speaker), so a pause takes effect within a fraction of a second. The head sways gently
  while speaking (`enable_wobbling`).

### Voice commands

- The robot's microphones (`mini.media.get_audio_sample()`) feed **Vosk**, an offline recogniser
  limited to the four command words (plus a "noise" catch-all).
- **While reading, only "stop" is accepted.** "Stop" never appears in the lecture or the flourishes,
  so the robot can't trigger itself.

| State | "begin" | "stop" | "continue" | "end" |
|---|---|---|---|---|
| **Reading** | ignored | **Pause** immediately + gesture | ignored | ignored (say "stop" first) |
| **Paused** | Restart from the very top + gesture | — | Resume at the **start of the interrupted sentence** + gesture | Closing gesture, rest pose, sleep, exit |
| **Finished** | Read again from the top | — | — | Sleep, exit |

### Gestures (gentle and always safe)

`bow`, `nod`, `tilt`, `ponder`, `aha`, `lean_in`, `look_around`, `look_up`, `shake`, `antenna_flutter`.
- Head pitch/roll ≤ 15° (hardware limit 40°), yaw ≤ 25°, body untouched, antennas small.
- Each move uses `goto_target()` with smooth `minjerk` interpolation and lasts ≥ 0.8 s, then
  returns to neutral. Gestures never overlap.
- The robot returns to the rest pose on stop, end, Ctrl-C or any error.

## Testing path

1. **Simulator on the Mac** (`mjpython -m reachy_mini.daemon.app.main --sim`). Audio and microphone
   are the Mac's own.
2. **Real Wireless robot over Wi-Fi.** Check timing, false triggers and gestures.
3. Hugging Face publishing: later, separate decision.

## Repo layout

```
reachy-app-one/              (GitHub: mck23/reachy-meets-planck, public)
├── .env                     ← OPENAI_API_KEY (never committed)
├── .env.example
├── .gitattributes           ← *.ogg stored with Git LFS
├── .githooks/               ← pre-commit blocks .env files and sk-… keys; Git LFS hooks
├── LICENSE                  ← MIT
├── README.md  index.html  style.css  pyproject.toml  plan.md
├── data/                    ← development only (ignored): WAV masters, Gutenberg source
├── scripts/                 ← extract_lecture, render_audio, check_audio, audition_voices
├── tests/
└── reachy_meets_planck/     ← the app package (everything here is installed on the robot)
    ├── main.py  speech.py  listener.py  gestures.py  playlist.py
    ├── data/                ← lecture1_text.json, performance.json
    └── audio/               ← 232 Ogg Opus clips + manifest.json
```
