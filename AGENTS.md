# AGENTS.md — Musical Fluency Lab (MFL)

## Mission and product philosophy

MFL is an offline-first, MIDI-driven personal piano coach and an experimental learning project. Its purpose is **practical musical fluency, not repertoire accumulation or theoretical knowledge alone**: hear, anticipate, recall, accompany, improvise and create music without depending on chord charts. The aspirational outcome is a living-room pianist who can accompany friends singing, transpose for a singer, recover from mistakes, and add tasteful fills. Pop/rock and Latin ballads are the primary musical laboratory; borrow jazz learning techniques and harmonic vocabulary in service of that goal, not as a prerequisite.

The owner calls the desired experience **Miyagi Sensei** (wax on, wax off). This is a non-negotiable product requirement:

- Opening `mfl` should automatically connect the keyboard, resume where the learner left off, and prescribe the next task. Never require the learner to choose a scale, key, exercise, difficulty or curriculum before practicing.
- Teach before testing. Demonstrate a movement or musical idea, let the learner imitate with feedback, then remove assistance and test recall. Reintroduce support when needed. Short explanations are welcome; long theory lectures are not.
- Minimize computer interaction: playing the MIDI keyboard should drive progress. No mandatory confirmation clicks between seeing a chord and trying it. Optional hint, skip, quit and accessibility controls are fine.
- Make every exercise musically meaningful. Preserve the pleasure of playing; finish sessions with an invitation to play a favorite song freely. Do not turn all piano time into homework or optimize solely for exercise scores.
- Prefer durable retrieval and transfer to unfamiliar music over short-term performance on repeated exercises. Speed is useful only alongside accuracy, musicality and retention. Accelerated learning is a hypothesis to test, not a validated promise.

## Learner and target environment

The owner is an experienced programmer/economist, not a beginning musician. He can sing while accompanying himself from chord charts, understands major/minor triads and some inversions, and uses economical voicings on a small Casiotone. C major/A minor and, to a lesser extent, G major/E minor are familiar. Other keys make sense during practice but do not stick. Ear-to-hand connection, harmonic prediction, spontaneous retrieval across keys, and accompaniment fluency are the principal bottlenecks. Do not assume his precise ear-training level before assessing it.

- Practice budget: 20–30 minutes/day, five days/week, including enjoyable free playing.
- Musical references: Elton John, Billy Joel, Alicia Keys (*If I Ain't Got You*), Fito Páez (*11 y 6*), Ricardo Arjona, Luis Miguel, Ana Gabriel. These are stylistic goals, not a request to embed copyrighted song transcriptions. Use original short musical examples for built-in exercises.
- Owner shared a performance of *Your Song*: https://youtu.be/q39nQeKKrFk . Previous assistant could not access the performance; do not claim it was evaluated.
- Primary portable controller: Novation Launchkey Mini MK3 (25 keys), USB. Also Launchkey 49 and Roland FP-30X (88 keys). Exercises must fit the available register or adapt intelligently. Do not require two-handed full-range playing on the Mini.
- Tested machine: Fedora 44, Intel/x86-64. Other Fedora 44 machines, Apple Silicon Mac Mini M5, and now an Omarchy machine running Codex. The owner tested v0.4 with the Launchkey Mini MK3 on Omarchy. Apple Silicon still needs live verification.
- Prefer Python, `uv`, lightweight dependencies, Typer CLI and Textual TUI. Keep deployment simple. Reference packaging workflow: https://renatovargas.github.io/esa-toolbox/ . Eventually publish versioned GitHub releases and installable wheels; no repository URL for MFL was established in the chat.

## Handover and current implementation

The original handover was prepared on 2026-11-24 from the v0.2.0 ZIP. The owner successfully ran v0.1 and v0.2 on Fedora. v0.1 felt like an examiner, and v0.2 introduced guidance but required an intermediate click that made it unclear when to play. v0.3 removed the click, and v0.4 added sound. The v0.4 feedback (too quiet; a double sound after blind recall) was addressed in v0.5, which the current checkout implements. Inspect the working tree and tests before editing, and preserve unrelated owner changes.

### Current implementation (v0.5.0)

v0.5 (2026-11-27) replaced the fixed seven-chord lesson with a daily adaptive coach. See `README.md` and `CHANGELOG.md`.

- **Layers:**
  - `mfl.theory` (pure Python): spelled notes and intervals, scales and modes, 36 chord qualities with parsing and identification from MIDI, keys and Roman numerals (pop convention relative to the major scale, `V7/vi` secondaries, `I/3` slash basses), voice leading, `PROGRESSIONS`, `COMP_PATTERNS`, `GROOVES` and key estimation.
  - `mfl.audio`: the engine and instruments.
  - `mfl.exercises`: UI-agnostic state machines.
  - `mfl.curriculum`: 21 units and 108 skills with stable IDs (`chord/F#m`, `prog/axis/G`, `groove/tresillo`, `ear/degrees/135`, `ear/echo/4`, `ear/chords/vi`).
  - `mfl.srs`: SM-2 style scheduling with grades 1–4 derived from performance.
  - `mfl.planner`: the daily plan.
  - `mfl.session`: runs the plan, records results, re-queues failures and resumes.
  - `mfl.ui.app`: the Textual front end. `mfl.tui` is a shim for it.
- **Plan:** Warm-up (due chords, interleaved, sometimes asked by Roman numeral), Learn (new items, chords weighted 0.5, at most 5 weighted), Navigate (walks → play-along with cues fading from symbols to Roman numerals to none, plus ungraded consolidation play-alongs for today's new progressions), Ear, then free play. The default is 30 minutes of structured practice (owner request), then open-ended free play.
- **Exercises:** chord (probe 6 s → guided → recall; the guide accepts the shape in any octave plus a lower left-hand chord tone; recall accepts any inversion or doubling, may omit the fifth of 4+ note chords, and slash chords need their bass), walk (legato changes allowed), play-along (count-in, optional example pass, drums and bass, hit clustering, timing windows, learned `timing_offset` setting), degrees, echo, chord-by-ear, and free play.
- **Audio:**
  - 44.1/48 kHz stereo, 256-frame blocks.
  - Additive piano and FM electric piano are rendered every 3 semitones and resampled. Organ and pad are real-time wavetables.
  - Drums are GM numbers. A synthetic IR feeds the convolution reverb, followed by a limiter. `MASTER_GAIN` 3.2 makes a medium triad about −15 dBFS RMS, roughly 10 dB louder than v0.4.
  - Samples are cached in `~/.cache/mfl/samples-vN`. Bump `RENDER_VERSION` when changing synthesis.
  - The demo gate (`exercises.base.Context`) waits 0.75 s after the last release, and live note-on cancels demos. Backing tracks use the `backing` tag and are not cancelled.
  - The device opens on a background thread.
  - CPU is about 11–17% of one core with 10 voices. No underflows were observed during cold sample rendering on Omarchy.
- **MIDI:** rtmidi callback with perf_counter timestamps, CC64 as the pedal, channel-10 notes as pads (they play drums and are ignored by exercises), and reconnect retries every 2 s.
- **Storage:** `PRAGMA user_version` 1 adds `skills`, `results`, `sessions` and `settings`. The legacy `attempts` table is preserved, and legacy successful recalls seed `chord/<symbol>` skills.
- **Tests:** 47 tests with fake MIDI, fake audio and temporary databases (`tests/helpers.py` has `FakeAudio`, `Clock` and `Rig`).

### Hardware status and next task

- Verified on Omarchy in a pseudo-terminal with the Launchkey Mini MK3 connected: the app auto-selects the MIDI port, opens audio (default device, 44.1 kHz) and exits cleanly. A 4-bar band stress test during cold sample rendering produced no underflows.
- Not yet verified by playing:
  - the musical feel of the new sounds and levels;
  - whether play-along timing judgement feels fair with real PipeWire latency (`timing_offset` self-calibrates within ±120 ms);
  - Launchkey pad channel and pedal behaviour;
  - Fedora and macOS hardware.

Next, ask the owner to play a few sessions and report sound quality, pacing (new items per day, session length) and whether the grading feels fair. Then continue the roadmap below.

## Subsequent roadmap

1. **Persistent coach and resume.** Largely done in v0.5: skill state, results, sessions, a daily planner and same-day resume. Remaining: resume mid-exercise rather than restarting it, and an explicit placement assessment.
2. **Audio and ear–hand training.** Build on the local synth to teach with original phrases: listen → imagine/sing → play; progressively remove visual cues. Add screen-off or auditory-only tests. Singing cannot be verified from MIDI alone; microphone analysis would be a separate optional capability.
3. **Retrieval and harmonic navigation.** Spaced review across days, interleaving familiar and new keys, short targeted transition exercises, harmonic prediction and disappearing chord charts (symbols → functions → bass cues → no cues). Use functional harmony, not isolated scale drills. Test unfamiliar progressions and keys to measure transfer. Adapt challenge based on accuracy, response time and hint dependence; do not confuse quick responses with learning.
4. **Accompaniment and creativity.** Train reusable pop/rock, Latin pop, ballad and bolero-inspired patterns, economical voice leading, bass movement, rhythmic stability, dynamics, intros/fills, and transposition. Gradually introduce sevenths, ninths, secondary dominants and chromatic approaches. Add constrained improvisation, motif development and an imaginary singer (original melody with pauses and delayed entrances) to teach listening and responsive accompaniment. Keep Mini-compatible tasks and larger-keyboard tasks separate where necessary.
5. **Evaluation and distribution.** Establish baseline and periodic unassisted tests using novel material; assess melody reproduction, harmonic recognition, keyboard navigation, rhythm and creative fluency. A 14-day pilot and longer 12-week experiment were proposed, not validated. Add cross-platform CI, versioned releases, installable wheels, and a diagnostic command if useful. Avoid requiring a cloud LLM for per-note feedback; deterministic music algorithms should handle real-time evaluation. AI coaching can be optional later.

## Development and verification

Use small, testable changes. Keep theory, coach, MIDI, storage and rendering separate; avoid a large rewrite without a demonstrated need. Add tests for phase transitions, MIDI release and zero-velocity note-on, exact vs inversion matching, hint recovery, register/layout mapping, and persistence when touched. Prefer fake MIDI input and temporary SQLite databases in automated tests; never write tests into the owner's real practice database. Preserve the existing CLI and data. Update version, README, and changelog/release notes as appropriate. Report what was tested and what requires physical hardware. Do not publish or push without authorization.

Development commands (from project root):

```sh
uv sync
uv run mfl devices
uv run mfl
uv run --with pytest pytest -q
```

Install/update locally: `uv tool install --force .` then `mfl`. On Fedora the working installation explicitly used `--python /usr/bin/python3`. On Fedora 44, `python-rtmidi==1.5.8` attempted a source build and failed first for missing ALSA headers, then Python development headers. Installing `alsa-lib-devel` and `python3-devel` and using the matching system interpreter resolved the test. JACK absence was only a warning. Other build tools were already available. For Omarchy (Arch-based), inspect the environment and wheel availability first; if compiling, ALSA development files normally come with `alsa-lib`, and compiler/build tools with `base-devel`. Do not blindly run privileged installation commands. On macOS, verify CoreMIDI and Apple Silicon wheel availability; source builds may need Xcode command line tools. Omarchy live playback was confirmed in v0.4. macOS still needs hardware verification.

The tested Fedora device appeared as ALSA client 20, port 0 (`Launchkey Mini MK3 MIDI Port`); port 1 is DAW control. IDs can change. `aconnect -l` and `mfl devices` are useful diagnostics. Real note-on/off and velocity events were observed. Auto-detect by suitable port names, not fixed IDs; retain manual override for exceptional cases.

## Working agreement with the owner

The owner wants to spend time playing, not managing lessons or copying code from chat. Act as a collaborative developer: inspect the repository, implement the next coherent increment, run available tests, explain concise installation/testing steps, and ask only for decisions that materially affect the project. Preserve the owner's ability to verify the work. The software is the teacher, not merely a MIDI examiner. When uncertain about a design choice, favor the simplest path that makes the learner more independent of the software over time.
