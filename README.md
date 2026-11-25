# Musical Fluency Lab (MFL) — v0.1.0

A tiny, offline-first, MIDI-driven **guided** piano coach. Open the program; it tells you what to play. No scale picker, exercise menu, or account.

## What works in this first prototype

- Automatically selects a MIDI input (prefers Launchkey / Roland, ignores DAW ports).
- Recognizes three-note major/minor triads in any inversion or octave.
- Guides you through a seven-step C–Am–F–G chord-recall session.
- Shows a **voicing-distance proxy** in semitones between successive chords; MIDI cannot identify fingers.
- Records successes, skips, response times, and voicings in a local SQLite database.
- Ends with an invitation to play a song you love.
- Works on Linux ALSA and macOS CoreMIDI when `python-rtmidi` is installed successfully.

**Not yet implemented:** synthesized sound or backing tracks, ear-training playback, true spaced repetition, adaptive curriculum, resume of an interrupted session, chord recognition from arpeggios, or analysis of actual singing. The first release always starts the same guided seven-step session; previous attempts are retained. These are explicit next milestones.

## Install on Fedora 44

If `python-rtmidi` needs compilation, install development dependencies first:

```bash
sudo dnf install alsa-lib-devel python3-devel gcc-c++ pkgconf-pkg-config
```

Unzip the archive, enter the directory, then:

```bash
uv tool install --python /usr/bin/python3 .
mfl devices
mfl
```

For development instead:

```bash
uv sync --python /usr/bin/python3
uv run mfl
```

If you modify code after installing, reinstall with `uv tool install --force --python /usr/bin/python3 .`.

## Install on macOS (Apple Silicon)

Install `uv` first, then in the unzipped directory:

```bash
uv tool install .
mfl devices
mfl
```

Depending on Python version and wheel availability, `python-rtmidi` may compile from source; that may require Xcode Command Line Tools. We'll verify on the M5 rather than promise a wheel exists.

## Commands

- `mfl`: launch the guided session
- `mfl devices`: list MIDI input ports
- `mfl history`: view recent attempts
- `mfl --device Launchkey`: choose a matching input when needed
- `q`: quit the interface; `r`: restart the session

## Practice notes

Use the Launchkey Mini with a connected computer. MIDI note events are input, not sound; this prototype does not produce audio. For the first exercise, play three notes **simultaneously** and hold them, then release all notes after success. A full piano is better for two-handed playing; the Mini is enough for these three-note challenges.

Data lives at `~/.local/share/mfl/progress.sqlite3` on Linux (or `$XDG_DATA_HOME/mfl/progress.sqlite3` when set). On macOS the same fallback path is used. No data leaves the machine.

## Known limitations

- Notes must be held simultaneously: arpeggios do not count as chords yet.
- The exercise recognizes exactly three held MIDI notes. Doubling a note in another octave is not accepted.
- There is no sustain-pedal processing yet.
- Skipping records a failed attempt; restarting doesn't erase history.
- An interrupted session restarts at step 1; resumable sessions are planned.
- Input-device auto-selection is best-effort. If it selects the wrong port, use `--device`.

## Roadmap

1. Resume interrupted sessions and adapt the daily plan based on past attempts.
2. Audio cues and short listen–sing–play challenges.
3. Spaced retrieval and new-key transfer tests.
4. Accompaniment patterns and expressive playing with a singer.
5. Cross-platform CI builds and GitHub releases.

License: MIT (see LICENSE).

## v0.2 guided learning preview

This version adds a **show → guided play → recall** sequence. During the guided stage, a chromatic two-octave note grid shows the target MIDI notes (◆) and the notes you play (●). It gives feedback on missing notes. The first four chords demonstrate specific economical voicings, while the final three prompts start in recall mode. You can request the guide again at any time.

**Important:** This is a text-based chromatic note grid, not yet a graphical piano with black/white keys or audio demonstrations. Live note feedback and lessons are a first iteration. The app still restarts the fixed session on launch and does not yet have adaptive scheduling.

Upgrade from the extracted folder using `uv tool install --force --python /usr/bin/python3 .`.
