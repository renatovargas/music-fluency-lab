# Musical Fluency Lab 0.9.1

An offline, MIDI-driven piano coach for practical fluency: hearing, recalling, accompanying and transposing without depending on chord charts. Run `mfl` with a keyboard connected and play any key to begin. There's nothing to choose first.

## What a session looks like

Each day MFL builds a ~30-minute lesson from your history, then leaves you in free play for as long as you like.

| Block | What happens |
| --- | --- |
| **Warm-up** | Chords that are due for review, mixed across keys, played from memory. Well-known chords are sometimes asked by function ("In F major, play vi"). |
| **Learn** | New material from the next unit. A new chord is taught first: MFL plays it, you copy the highlighted keys, then you play it from memory. A new progression is played for you first, then walked with a keyboard guide. |
| **Navigate** | Progressions in time with a virtual band (drums and bass). The chart fades as you improve: guided walk → chord symbols → Roman numerals → no chart, at rising tempos. You also learn comping rhythms such as ballad half notes, tresillo, habanera, cinquillo, pop eighths and broken chords. |
| **Ear** | Ear-to-hand training. Hear a cadence and a note, then find the scale degree. Echo short original phrases. Hear a chord in a key and play it. |
| **Play** | Free play with live chord naming, key estimation, Roman-numeral analysis and optional drum grooves. |

A spaced-repetition scheduler (SM-2 style, four grades) decides when each skill returns: something you found easy comes back in days or weeks, and something you struggled with comes back tomorrow or later in the same session. Grades come from what you actually played (first-try success, misses, hints, time to find a chord, timing spread), never from a self-rating. If you quit mid-session, the next launch that day resumes where you stopped.

The path has 21 units and 108 skills. It starts in C, G and A minor, introduces the Andalusian cadence and minor-key bolero cadences early, adds sevenths, secondary dominants (V7/vi), borrowed chords (iv, ♭VII), slash chords and walking bass, suspensions, blues, and then works around the circle of fifths. All musical examples are original or generated, and chord progressions are treated as shared vocabulary, not transcriptions.

## Keys while practising

The keyboard drives everything. Each new kind of exercise starts with a short card that explains what to do. Play any key when you're ready. Nothing moves on by itself while you're thinking. The computer keys are optional:

| Key | Action |
| --- | --- |
| `H` | Hint, or replay the example |
| `R` | Repeat this exercise (or the one just finished) |
| `B` / Backspace | Go back one step and see its explanation again |
| `S` | Skip this exercise |
| `+` / `-` | Volume (up to 200%) |
| `[` / `]` | Slower / faster: scales every play-along tempo (default 85%, remembered). In free play, the drum tempo |
| `I` | Change sound (sampled grand piano if installed, synth piano, electric piano, accordion, drawbar organ, warm pad) |
| `.` / `,` | Band exercises: move the moving lane later / earlier if it doesn't match what you hear |
| `G` | Free play: drum style |
| `P` | Progress screen: keys around the circle of fifths, the path, recent results |
| `Q` | Quit (progress is saved continuously) |
| `Ctrl+P` | Command palette (e.g. change the colour theme) |

A sustain pedal (CC 64) is supported. Launchkey drum pads (MIDI channel 10) play the built-in drum kit and never interfere with exercises.

## Sound

All sound is synthesized locally with NumPy. There are no sound fonts to download. The piano is an additive model with inharmonic partials, detuned unison strings, hammer noise and velocity-dependent brightness. The electric piano is two-operator FM through stereo tremolo, the accordion is three detuned free reeds (musette), the organ is a drawbar model with percussion and rotary chorus, and the pad uses detuned saws with chorus. Everything goes through a convolution reverb and a limiter. The first launch renders the samples in the background, which takes about 10 seconds and doesn't block practice. They are cached in `~/.cache/mfl` (about 50 MB) and load in under a second afterwards. `mfl sounds` auditions every sound and the band.

If the sound crackles, MFL enlarges its audio buffer automatically and remembers it. You can also set it: `mfl --latency 0.08` (default 0.045 s, minimum 0.03 s).

Before the first band exercise, a 15-second **sound check** asks you to tap along with clicks. It measures the delay between the software and your ears, so the moving lane matches what you hear. Run `mfl --resync` to redo it, for example after changing speakers.

Demonstrations never start while you hold keys. They wait until a short silence after you release, and playing anything cuts them off immediately.

## Install and run

From the repository directory, with Python 3.11 or later and `uv` available:

```sh
uv tool install --force .
mfl
```

On Fedora 44 the tested install used `uv tool install --force --python /usr/bin/python3 .`. A source build of `python-rtmidi` there needed `alsa-lib-devel` and `python3-devel`. On Linux, audio uses the system PortAudio library (`portaudio` on Arch and Fedora). There are no new dependencies since v0.4.

| Command | Purpose |
| --- | --- |
| `mfl` | Practise (`--device NAME`, `--silent`, `--minutes 20`, `--latency 0.08`, `--resync`) |
| `mfl plan` | Show today's plan without starting |
| `mfl stats` | Progress report |
| `mfl history` | Recent results (and v0.4 chord attempts) |
| `mfl devices` | List MIDI inputs and show the one MFL would pick |
| `mfl sounds` | Audition the built-in sounds |
| `mfl get-piano` | Download a real sampled grand piano (36 MB, see below) |

### Sampled grand piano (optional)

`mfl get-piano` downloads the [FreePats YDP Grand Piano](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html) into `~/.local/share/mfl/sounds` and makes it your keyboard sound. The download is 36 MB, and MFL reads the SoundFont itself, with no extra software. The download is verified against a SHA-256 hash.

Attribution (CC-BY 3.0): Grand piano by roberto@zenvoid.org for FreePats, built from the Zenph Studios Yamaha Disklavier Pro Piano Multisamples for OLPC. [License](http://creativecommons.org/licenses/by/3.0/).

## Data

Everything stays local, in `$XDG_DATA_HOME/mfl/progress.sqlite3` (default `~/.local/share/mfl/`). v0.5 migrates older databases in place. The v0.4 attempts table is kept, and chords you had already recalled from memory start as known skills.

## Development

```sh
uv sync
uv run --with pytest pytest -q   # 65 tests: theory, audio engine, exercises, planner, storage, session, app
uv run mfl devices
uv run mfl
```

The code is split into layers that don't depend on the UI:

- `mfl.theory`: spelled notes, intervals, scales and modes, chord qualities and identification, keys and Roman numerals, voice leading, progressions, rhythms and key finding.
- `mfl.audio`: the engine (scheduler, voices, effects, reverb and limiter) and the instruments.
- `mfl.exercises`: exercises as state machines driven by MIDI and time.
- `mfl.curriculum`, `mfl.srs` and `mfl.planner`: what to practise and when.
- `mfl.session`: runs a day's plan, records results and resumes.
- `mfl.ui`: the Textual front end.

Tests use fake MIDI, fake audio and temporary databases.

License is MIT. See [LICENSE](LICENSE).
